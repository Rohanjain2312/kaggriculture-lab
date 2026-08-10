"""Kaggriculture agent.

A herd of livestock clustered at the shed, a strawberry-led crop mix, and a
market policy that never dumps. Everything below came out of reading the
environment source rather than the competition docs.

The economics
-------------
The town drains market inventory below I0 all season, which *raises* prices, and
that drain is the prize. Integrating each price curve over its end-of-season
deficit: strawberry ~$129k, milk ~$99k, wool ~$81k -- against carrot ~$18k and
melon ~$40k. Products also differ hugely in how hard they crash when
oversupplied (melon's glut curve is quadratic; wheat's is barely a slope).

So:

* Crops are valued at the *marginal* price of the units a planting would add,
  stacked on everything already committed and measured against an inventory
  projected forward for the town's remaining demand. Melon is worth ~$287/unit
  on the first tile and ~$1 on the thirtieth, so the mix diversifies on its own
  rather than committing the farm to one crop and then crashing it.
* Animals are the best return per action in the game -- one $400 cow yields 36
  milk over a season -- so the herd is built on the tiles nearest the shed,
  including the shed-access tiles themselves, where an animal is fed, cared,
  harvested and collected from without a single move. Every unit spawns
  shed-adjacent each morning, which makes the daily wheat pickup nearly free.
  Fed *and* cared every day matters: the care bonus roughly triples output.
* Produce is trickled out, never dumped: each turn we sell only as many units as
  keep the marginal price above a reserve, and that reserve winds down over the
  closing days because unsold stock scores nothing.
* Labour, not land, is the binding constraint, so plantings are capped at what
  the crew can still water after the animals are served. One missed watering
  turns a plant into a weed and the tile is dead for the rest of the game.

Nothing is remembered between turns: every decision is recomputed from `obs`,
and the module-level dicts are pure caches that are safe to lose. Stability
across turns comes from deterministic sort orders, not from stored plans.

NOTE: kaggle_environments loads a file agent by taking the LAST callable in the
module namespace, so `agent` must stay the final definition in this file and no
callable may be imported at module scope.
"""

import math
import os
import sys
import traceback

AGENT_VERSION = "v4-gate"   # keep in sync with docs/SUBMISSIONS.md

DEBUG = os.environ.get("KAGGRICULTURE_DEBUG") == "1"

# --------------------------------------------------------------------------- #
# Environment constants (mirrored from kaggriculture.py -- keep in sync)
# --------------------------------------------------------------------------- #

TURNS_PER_DAY = 24
LAST_DAY = 29
SHED_CAPACITY = 100
MAX_MARKET_ORDERS = 10
MARKET_I0 = 10000

CROPS = {
    "WHEAT":      {"seed": 10, "first_yield_day": 2, "max_yield_day": 4, "interval": 0, "max_yield": 6, "ongoing": False},
    "CARROT":     {"seed": 20, "first_yield_day": 2, "max_yield_day": 3, "interval": 0, "max_yield": 4, "ongoing": False},
    "TOMATO":     {"seed": 50, "first_yield_day": 8, "max_yield_day": 8, "interval": 1, "max_yield": 4, "ongoing": True},
    "STRAWBERRY": {"seed": 100, "first_yield_day": 10, "max_yield_day": 10, "interval": 2, "max_yield": 4, "ongoing": True},
    "MELON":      {"seed": 80, "first_yield_day": 10, "max_yield_day": 12, "interval": 0, "max_yield": 6, "ongoing": False},
}

ANIMALS = {
    "GOOSE": {"cost": 300, "structure": "COOP",    "first_yield_day": 4, "interval": 1, "max_held": 4, "product": "EGG"},
    "COW":   {"cost": 400, "structure": "PASTURE", "first_yield_day": 8, "interval": 2, "max_held": 6, "product": "MILK"},
    "SHEEP": {"cost": 500, "structure": "PASTURE", "first_yield_day": 6, "interval": 3, "max_held": 6, "product": "WOOL"},
}

PRODUCTS = ["WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON", "EGG", "MILK", "WOOL", "FERTILIZER"]

MARKET_PARAMS = {
    "WHEAT":      {"base":  25, "T": 400, "below_func": "sqrt",   "below_target": 0.80, "above_func": "log",    "above_target": 0.20},
    "CARROT":     {"base":  35, "T": 450, "below_func": "log",    "below_target": 0.20, "above_func": "sqrt",   "above_target": 0.70},
    "TOMATO":     {"base":  60, "T": 200, "below_func": "linear", "below_target": 0.40, "above_func": "sqrt",   "above_target": 0.60},
    "STRAWBERRY": {"base": 120, "T": 100, "below_func": "sqrt",   "below_target": 0.70, "above_func": "linear", "above_target": 1.60},
    "MELON":      {"base": 250, "T": 300, "below_func": "log",    "below_target": 0.20, "above_func": "sq",     "above_target": 3.60},
    "EGG":        {"base":  50, "T": 332, "below_func": "linear", "below_target": 0.40, "above_func": "log",    "above_target": 0.20},
    "MILK":       {"base": 160, "T": 122, "below_func": "sqrt",   "below_target": 0.60, "above_func": "linear", "above_target": 1.60},
    "WOOL":       {"base": 200, "T": 105, "below_func": "log",    "below_target": 0.20, "above_func": "sq",     "above_target": 3.20},
    "FERTILIZER": {"base": 100, "T": 200, "below_func": "linear", "below_target": 0.40, "above_func": "linear", "above_target": 0.40},
}

SHOPS = {
    "BAKERY":         ["EGG", "WHEAT"],
    "PIZZA_SHOP":     ["MILK", "TOMATO", "WHEAT"],
    "BRUNCH_SPOT":    ["EGG", "WHEAT", "STRAWBERRY"],
    "YARN_STORE":     ["WOOL"],
    "ICE_CREAM_SHOP": ["STRAWBERRY", "MILK", "WHEAT"],
    "PET_CAFE":       ["CARROT"],
    "SMOOTHIE_SHOP":  ["STRAWBERRY", "MILK"],
    "FARMERS_MARKET": ["WHEAT", "CARROT", "TOMATO", "STRAWBERRY"],
}

LAND_PRICES = [1000, 2000, 4000]
MOVES = {"NORTH": (0, -1), "SOUTH": (0, 1), "EAST": (1, 0), "WEST": (-1, 0)}

# --------------------------------------------------------------------------- #
# Tuning
# --------------------------------------------------------------------------- #

# Ladder opponents run 10.9-11.5 hands to our 12.4-12.8, but cutting to 11 was
# measured as a net loss (-$4.5k vs `pass`): the payroll saving is real and the
# revenue loss is bigger. They win on efficiency, not on spending less.
MAX_HANDS = 13
MIN_HANDS = 4             # first four hands cost $7/day in total
LIVESTOCK_RESERVE = 900   # cash kept clear of seed while animals still pay
ACTIONS_PER_UNIT = 12     # usable actions per unit per day (24 less slack)
CASH_FLOOR = 250          # never spend below this
RUNWAY_DAYS = 6           # days of payroll to keep banked while waiting on a harvest
DRAIN_SHARE = 0.5         # share of the town's future drain we assume we capture
LAND_CASH_MULT = 1.8
MAX_QUADRANTS = 4         # capping at 3 measured worse (-$7k vs `pass`)
LAND_LATEST_DAY = 16      # but a quadrant bought past this cannot repay itself
SHED_PRESSURE = 78        # sell without regard to reserve above this shed level
HAUL_TRIGGER = 70         # projected shed+carried at which units start hauling
HAUL_PER_UNIT = 12        # units of one item a single haul trip is worth
HAUL_ITEMS = ("MELON", "STRAWBERRY", "MILK", "WOOL", "EGG", "TOMATO", "CARROT")
PLANT_LATEST_HOUR = 21    # a plant must still be watered the day it goes in
LAST_SELL_HOUR = 21       # DONE fires at step 718, so hour 22 is the last sale

MAX_ANIMALS = 16
ANIMAL_ACTIONS = 5        # feed + care + share of harvest/collect + travel, per day
ANIMAL_ROI = 2.0          # required revenue-to-cost ratio before buying one
WHEAT_DAYS_HELD = 2       # days of feed kept in the shed and never sold
FERT_MIN_VALUE = 150      # don't spend an action fertilizing for less than this
FERT_BUY_RATIO = 3.0      # buy fertilizer while a unit returns this much value
FERT_SHED_MARGIN = 25     # shed space never spent on fertilizer
FERT_KEEP_MAX = 12        # fertilizer held back from sale at any one time
MIN_PLANT_SCORE = 16      # a tile is only planted when its marginal score clears
                          # this. At 0 anything better than nothing was planted,
                          # and labour -- not land -- is the binding constraint:
                          # measured watering runs at 1.00-1.08 actions per plant
                          # per day for 28 days straight, so every marginal tile
                          # takes a water action away from a better one. At the
                          # margin, melon scores ~62 and timely strawberry ~24-28,
                          # while wheat is 14.2, tomato 14.1, carrot 10.6 and
                          # strawberry planted past ~day 16 falls to 7.8. A gate
                          # of 16 keeps the first two and drops the rest, which
                          # also means nothing is planted after ~day 20 -- leaving
                          # a tile empty beats filling it with a crop that cannot
                          # repay the watering. Measured +$9,784/game vs `pass`.

# --------------------------------------------------------------------------- #
# ARCHETYPE SCRIPT (measured, not invented)
# --------------------------------------------------------------------------- #
# Extracted from three ladder replays played by three different accounts
# (Jesy Lu, Desyat IO, Dimitri ZABRE) against three different opponents on three
# different seeds. Every value below was byte-identical in all three, which is
# what makes this a fixed script rather than an adaptive agent -- and what makes
# it reconstructible at all.
#
# This clone keeps OUR unit-management and selling machinery and replaces only
# the strategic decisions: headcount, land, herd and planting. So it is not a
# faithful clone of their *execution* -- they run 1.10 moves per useful action
# to our ~1.37, so the real thing is stronger than this. It is a sparring
# partner that reproduces the strategy, not the player.

SCRIPT_HANDS = [5, 0, 4, 5, 5, 1, 4, 6, 9, 10, 8, 14, 7, 9, 5,
                13, 8, 11, 12, 12, 14, 13, 14, 13, 14, 14, 14, 14, 13, 6]
SCRIPT_LAND = {7: 2, 11: 3}          # day -> quadrant count to reach
SCRIPT_HERD = {"COW": 8, "SHEEP": 6}  # never a goose
SCRIPT_PLANT = {
    0:  [("MELON", 12), ("WHEAT", 7)],
    4:  [("WHEAT", 7)],
    7:  [("STRAWBERRY", 8)],
    8:  [("STRAWBERRY", 4), ("WHEAT", 7)],
    9:  [("STRAWBERRY", 7)],
    11: [("STRAWBERRY", 20), ("MELON", 12)],
    12: [("STRAWBERRY", 3), ("WHEAT", 7)],
    16: [("WHEAT", 7)],
    20: [("WHEAT", 7)],
    22: [("WHEAT", 7)],
    23: [("WHEAT", 5)],
    24: [("WHEAT", 12)],
    25: [("WHEAT", 6)],
    26: [("WHEAT", 12)],
    27: [("WHEAT", 8)],
}

# Job priorities (higher runs first).
P_FEED_CRIT = 110         # an unfed animal dies tonight; worth more than any plant
P_WATER_CRIT = 100
P_HARVEST_FINAL = 95
P_HAUL = 92               # produce left in hand overnight is destroyed
P_HARVEST_DUE = 90
P_GET_ANIMAL = 89         # every day an animal sits in the shed is lost production
P_PLACE_ANIMAL = 88
P_FEED = 85
P_GET_WHEAT = 84
P_WATER = 70
P_GET_FERT = 69
P_FERTILIZE = 66          # plus a bump for value; ~$300 on a strawberry tick
P_CARE = 65               # care bonus roughly triples an animal's output
P_COLLECT_FERT = 64       # sits with FEED/CARE: the unit is already standing on
                          # the tile, and the env clears `fertilizer_available`
                          # nightly, so a collect deferred past hour 23 is
                          # destroyed rather than deferred. At the old value of
                          # 45 -- below P_PLANT -- the queue never reached it and
                          # 45% of a game's fertilizer expired uncollected.
P_HARVEST = 60
P_BUILD = 58
P_DIG = 55
P_PLANT = 50
MOVE_PENALTY = 4          # priority charged per tile of travel when assigning
STAY_BONUS = 0            # priority added to a job on the tile a unit already
                          # occupies. Measured against the rank-3 agent over the
                          # same working area (77 vs 75 tiles): it chains 1.65
                          # useful actions per stop to our 1.34, and makes 1,669
                          # travel legs a game to our 2,003. Leg *length* matches
                          # (1.79 vs 1.86) -- we simply make more trips. The gap
                          # between two job priorities often exceeds MOVE_PENALTY,
                          # so a unit walks a tile for a higher-priority job and
                          # returns later (353 water-then-harvest returns per 10
                          # games). Raising MOVE_PENALTY would make every routing
                          # decision stickier; this only rewards finishing the
                          # tile you are standing on.

_CACHE = {}


# --------------------------------------------------------------------------- #
# Market model (mirrors kaggriculture.market_price exactly)
# --------------------------------------------------------------------------- #

def shape(func, x):
    """Price-curve shape function; matches the environment's `_shape`."""
    x = max(0.0, x)
    if func == "linear":
        return x
    if func == "sq":
        return x * x
    if func == "sqrt":
        return math.sqrt(x)
    if func == "log":
        return math.log(1.0 + x)
    if func == "log10":
        return math.log10(1.0 + x)
    return x


def market_price(item, inv):
    """Unit price of `item` at market inventory `inv`, floored at $1."""
    p = MARKET_PARAMS[item]
    base, T = p["base"], p["T"]
    if inv < MARKET_I0:
        f = p["below_func"]
        amp = p["below_target"] * base / shape(f, T)
        price = base + amp * shape(f, MARKET_I0 - inv)
    else:
        f = p["above_func"]
        amp = p["above_target"] * base / shape(f, T)
        price = base - amp * shape(f, inv - MARKET_I0)
    return max(1, int(round(price)))


def sell_count(item, inv, floor_price, cap):
    """How many units can be sold before the marginal price drops below `floor_price`.

    Sell price is quoted at pre-sell inventory, so unit k is priced at inv + k.
    """
    n = 0
    while n < cap and market_price(item, inv + n) >= floor_price:
        n += 1
    return n


def cum_revenue(item, inv, n):
    """Total proceeds from selling `n` units starting at inventory `inv`."""
    inv = int(inv)
    total = 0
    for k in range(int(n)):
        total += market_price(item, inv + k)
    return total


def shop_demand(shop, item):
    """Units of `item` one tick of `shop` consumes (single-product shops pull 2x)."""
    products = SHOPS[shop]
    if item not in products:
        return 0
    return 2 if len(products) == 1 else 1


def future_drain(item, day, unlocked_shops):
    """Expected town consumption of `item` from `day` through the end of the season.

    Shops already unlocked are counted exactly; the ones still to open are
    averaged, since which unlocks next is random.
    """
    unlocked = list(unlocked_shops or [])
    remaining = [s for s in SHOPS if s not in unlocked]
    known_rate = sum(shop_demand(s, item) for s in unlocked)
    rem_rate = sum(shop_demand(s, item) for s in remaining)
    rem_n = len(remaining)

    total = 0.0
    for d in range(day, LAST_DAY + 1):
        opened = max(0, min(rem_n, d // 3 - len(unlocked)))
        rate = known_rate + (rem_rate * opened / rem_n if rem_n else 0.0)
        total += 6.0 * rate                      # 24 turns / 4-turn shop interval
        if item != "FERTILIZER":
            mult = 4 if d >= 20 else 2 if d >= 10 else 1
            total += 2.0 * mult                  # 24 turns / 12-turn center interval
    return total


# --------------------------------------------------------------------------- #
# Geometry
# --------------------------------------------------------------------------- #

def shed_tiles(board_size):
    """The four shed-access tiles, in the environment's NWSE spawn order."""
    half = board_size // 2
    return [(half - 1, half - 1), (half, half - 1), (half - 1, half), (half, half)]


def dist(a, b):
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def shed_distance(pos, board_size):
    return min(dist(pos, t) for t in shed_tiles(board_size))


def step_toward(pos, target):
    """One move action toward `target`, or PASS if already there."""
    fx, fy = pos
    tx, ty = target
    if fx < tx:
        return ["EAST"]
    if fx > tx:
        return ["WEST"]
    if fy < ty:
        return ["SOUTH"]
    if fy > ty:
        return ["NORTH"]
    return ["PASS"]


def open_shed_tile(farm, board_size, pos):
    """Nearest shed-access tile that is not LOCKED (PICKUP/DROP no-op on locked)."""
    best = None
    for t in shed_tiles(board_size):
        if farm["tiles"][t[1]][t[0]] == "LOCKED":
            continue
        d = dist(pos, t)
        if best is None or d < best[0]:
            best = (d, t)
    return best[1] if best else None


# --------------------------------------------------------------------------- #
# Crop valuation
# --------------------------------------------------------------------------- #

def crop_projection(crop, day):
    """(units, occupancy_days, harvests) for planting `crop` today, watered daily.

    Returns units == 0 when the season is too short for the crop to pay out.
    """
    c = CROPS[crop]
    if c["ongoing"]:
        units = sum(1 for k in range(c["max_yield"])
                    if day + c["first_yield_day"] + k * c["interval"] <= LAST_DAY)
        if units <= 0:
            return 0, 0, 0
        last = day + c["first_yield_day"] + (units - 1) * c["interval"]
        return units, last - day + 1, max(1, units // 2)

    harvest_day = min(day + c["max_yield_day"], LAST_DAY)
    age = harvest_day - day
    if age < c["first_yield_day"]:
        return 0, 0, 0
    window_start = (c["max_yield_day"] + 1) // 2
    bonus = max(0, min(age, c["max_yield_day"]) - window_start + 1)
    units = min(c["max_yield"], 1 + bonus)
    return units, age + 1, 1


def pipeline_units(farm, shed, board_size):
    """Units of each crop already committed: in the shed plus still growing."""
    pipe = {c: float(shed.get(c, 0)) for c in CROPS}
    for row in farm["tiles"]:
        for tile in row:
            if isinstance(tile, dict) and tile.get("kind") == "PLANT":
                c = CROPS[tile["crop"]]
                pipe[tile["crop"]] += c["max_yield"] if not c["ongoing"] else c["max_yield"]
    return pipe


def days_to_cash(crop, day):
    """Days from planting today until this crop first turns into sellable produce."""
    c = CROPS[crop]
    if c["ongoing"]:
        return c["first_yield_day"]
    return min(c["max_yield_day"], max(0, LAST_DAY - day))


def hire_burn(target_hands):
    """Cost of hiring `target_hands` hands, which is the daily payroll."""
    return sum(fib(i) for i in range(target_hands))


def build_plant_plan(obs, farm, shed, board_size, n_tiles, money, burn, extra_reserve=0):
    """Choose a crop for each of the next `n_tiles` plantings, one tile at a time.

    Every tile is priced at the *margin*: the units it would add sit on top of
    everything already committed (shed stock, growing plants, and the tiles
    chosen earlier in this same plan). So the first melon tile is valued at
    ~$287/unit and the thirtieth at ~$1, and the plan diversifies on its own
    instead of committing the whole farm to one crop that it then crashes.

    A crop is also skipped when paying for its seed would leave us unable to
    make payroll until it pays out -- the failure that starved the first
    version into a 26-day standstill at $150.
    """
    day = obs["day"]
    key = ("plan", obs["player"], day, obs["hour"] // 8, n_tiles, extra_reserve > 0)
    if key in _CACHE:
        return _CACHE[key]

    inv = obs["market"]["inventory"]
    shops = obs["town"].get("unlocked_shops", [])
    pipe = pipeline_units(farm, shed, board_size)

    proj = {}
    prefix = {}
    for crop in CROPS:
        units, occupancy, harvests = crop_projection(crop, day)
        if units <= 0:
            continue
        proj[crop] = (units, occupancy, harvests)
        base_inv = int(inv[crop] - DRAIN_SHARE * future_drain(crop, day, shops))
        need = min(900, int(pipe.get(crop, 0)) + units * n_tiles + 2)
        arr = [0] * (need + 1)
        for k in range(need):
            arr[k + 1] = arr[k] + market_price(crop, base_inv + k)
        prefix[crop] = arr

    committed = dict.fromkeys(proj, 0)
    plan = []
    cash = money
    for _ in range(n_tiles):
        best = None
        for crop, (units, occupancy, harvests) in proj.items():
            seed = CROPS[crop]["seed"]
            floor = CASH_FLOOR + extra_reserve + burn * min(RUNWAY_DAYS, days_to_cash(crop, day))
            if cash - seed < floor:
                continue
            start = int(pipe.get(crop, 0)) + committed[crop]
            arr = prefix[crop]
            if start + units >= len(arr):
                continue
            score = (arr[start + units] - arr[start] - seed) / float(1 + 2 * occupancy + harvests)
            if score > MIN_PLANT_SCORE and (best is None or score > best[0]):
                best = (score, crop)
        if best is None:
            break
        score, crop = best
        # Carry the score through as a priority so a $700 strawberry tile
        # outranks routine chores, while a marginal wheat tile does not.
        plan.append((crop, P_PLANT + max(0, min(25, int(score) - 10))))
        committed[crop] += proj[crop][0]
        cash -= CROPS[crop]["seed"]

    _CACHE.clear()
    _CACHE[key] = plan
    return plan


# --------------------------------------------------------------------------- #
# Tile classification
# --------------------------------------------------------------------------- #

def animal_units(animal, day):
    """Product units one animal placed today yields over the rest of the season.

    Fed and cared every day, the care bonus banks one extra unit per day between
    productions, so a scheduled tick pays 1 + interval rather than 1. Measured
    against the environment: cow 36, sheep 34, goose 52 over a full season.
    """
    a = ANIMALS[animal]
    prods = 0
    d = day + a["first_yield_day"]
    while d <= LAST_DAY:
        prods += 1
        d += a["interval"]
    return prods * (1 + a["interval"])


def animal_remaining(tile, day):
    """Units an already-placed animal still has left to give this season.

    Valuing the standing herd with `animal_units(..., today)` understates it --
    that asks what an animal placed *now* would yield -- so the marginal price
    looked better than it was and the agent kept buying cows it did not need.
    """
    a = ANIMALS[tile["animal"]]
    prods = 0
    d = tile.get("placed_day", 0) + a["first_yield_day"]
    while d <= LAST_DAY:
        if d > day:
            prods += 1
        d += a["interval"]
    return prods * (1 + a["interval"]) + tile.get("yield_units", 0)


def animal_slots(farm, board_size, want):
    """The `want` unlocked tiles closest to the shed, reserved for structures.

    Animals cost ~5 actions a day against a plant's ~2, and a unit must ferry
    wheat to each one, so they take the shortest routes. The shed-access tiles
    themselves are included: an animal there is fed, cared, harvested and
    collected from without a single move.
    """
    if want <= 0:
        return []
    tiles = []
    for y in range(board_size):
        for x in range(board_size):
            if farm["tiles"][y][x] != "LOCKED":
                tiles.append((shed_distance((x, y), board_size), x, y))
    tiles.sort()
    return [(x, y) for _, x, y in tiles[:want]]


def pick_animal(obs, farm, shed, board_size, budget, n_animals, workforce):
    """Best animal to buy now, or None. Priced at the margin like crops are."""
    day = obs["day"]
    have = {"COW": 0, "SHEEP": 0, "GOOSE": 0}
    for row in farm["tiles"]:
        for tile in row:
            if isinstance(tile, dict) and tile.get("animal"):
                have[tile["animal"]] = have.get(tile["animal"], 0) + 1
    for name in ANIMALS:
        have[name] = have.get(name, 0) + shed.get(name, 0)
    for name, want in SCRIPT_HERD.items():
        if have.get(name, 0) < want and budget >= ANIMALS[name]["cost"]:
            return name
    return None
    if n_animals >= min(MAX_ANIMALS, workforce * 2):
        return None
    inv = obs["market"]["inventory"]
    shops = obs["town"].get("unlocked_shops", [])

    # Count what is already committed to each product so a herd that has
    # saturated milk stops buying cows and moves to another product.
    committed = {}
    for row in farm["tiles"]:
        for tile in row:
            if isinstance(tile, dict) and tile.get("animal"):
                product = ANIMALS[tile["animal"]]["product"]
                committed[product] = committed.get(product, 0) + animal_remaining(tile, day)

    best = None
    for name, a in ANIMALS.items():
        units = animal_units(name, day)
        if units <= 0:
            continue
        cost = a["cost"] + units * 4          # rough wheat-feed overhead
        if budget < cost:
            continue
        product = a["product"]
        start = int(committed.get(product, 0)) + int(shed.get(product, 0))
        base_inv = int(inv[product] - DRAIN_SHARE * future_drain(product, day, shops))
        gross = cum_revenue(product, base_inv, start + units) - cum_revenue(product, base_inv, start)
        if gross < cost * ANIMAL_ROI:
            continue
        score = gross / float(cost)
        if best is None or score > best[0]:
            best = (score, name)
    return best[1] if best else None


def fertilize_gain(tile, day):
    """Extra product units one FERTILIZE on this plant would produce.

    Coverage runs for `day`, `day+1`, `day+2`. Ongoing crops double a scheduled
    tick that is also watered; one-time crops double each watered day inside
    their bonus window. Melon gains nothing -- watering alone already reaches
    its cap of 6 -- and the yield cap bounds everything else.
    """
    c = CROPS[tile["crop"]]
    if tile.get("fertilized_until_day", -1) >= day:
        return 0
    held = tile.get("yield_units", 0)
    room = c["max_yield"] - held
    if room <= 0:
        return 0

    if c["ongoing"]:
        gain = 0
        for d in range(day, day + 3):
            since = (d + 1) - tile["planted_day"] - c["first_yield_day"]
            if since < 0 or since % c["interval"]:
                continue
            if since // c["interval"] + 1 <= c["max_yield"]:
                gain += 1
        return min(gain, room)

    window_start = (c["max_yield_day"] + 1) // 2
    gain = 0
    for d in range(day, day + 3):
        age = d - tile["planted_day"]
        if window_start <= age <= c["max_yield_day"]:
            gain += 1
    return min(gain, room)


def fertilizer_demand(farm, day, prices):
    """How many plants are worth fertilizing right now."""
    n = 0
    for row in farm["tiles"]:
        for tile in row:
            if not (isinstance(tile, dict) and tile.get("kind") == "PLANT"):
                continue
            gain = fertilize_gain(tile, day)
            if gain > 0 and gain * prices.get(tile["crop"], 0) >= FERT_MIN_VALUE:
                n += 1
    return n


def plant_state(tile, day):
    """(needs_water, water_is_critical, can_harvest, harvest_is_due) for a plant tile."""
    c = CROPS[tile["crop"]]
    age = day - tile["planted_day"]
    needs_water = not tile["watered_today"]
    critical = needs_water and tile["consecutive_unwatered"] >= 1
    can_harvest = tile.get("yield_units", 0) > 0 and age >= c["first_yield_day"]
    if c["ongoing"]:
        due = can_harvest and tile["yield_units"] >= c["max_yield"]
    else:
        due = can_harvest and (age >= c["max_yield_day"] or tile["yield_units"] >= c["max_yield"])
    return needs_water, critical, can_harvest, due


def build_jobs(obs, farm, private, board_size, seed_budget, plan, reserved, build_needs):
    """All actionable tiles this turn as (priority, pos, action, required_item).

    `required_item` names something the acting unit must be carrying -- FEED
    needs wheat in hand (not in the shed) and PLACE needs the animal itself.
    """
    day = obs["day"]
    final_day = day >= LAST_DAY
    shed = private["shed"]
    prices = obs["market"]["prices"]
    inventories = private.get("inventories", [])
    jobs = []
    plantable = []
    build_sites = []
    unfed = 0
    fert_demand = 0
    empty_structures = {"COOP": 0, "PASTURE": 0}

    for y in range(board_size):
        for x in range(board_size):
            tile = farm["tiles"][y][x]
            if tile == "LOCKED":
                continue
            pos = (x, y)
            if tile is None:
                (build_sites if pos in reserved else plantable).append(pos)
                continue
            if not isinstance(tile, dict):
                continue
            kind = tile.get("kind")
            if kind == "WEED":
                jobs.append((P_DIG, pos, ["DIG"], None))
            elif kind == "PLANT":
                needs_water, critical, can_harvest, due = plant_state(tile, day)
                if can_harvest and final_day:
                    jobs.append((P_HARVEST_FINAL, pos, ["HARVEST"], None))
                    continue
                if critical:
                    jobs.append((P_WATER_CRIT, pos, ["WATER"], None))
                if due:
                    jobs.append((P_HARVEST_DUE, pos, ["HARVEST"], None))
                elif can_harvest:
                    jobs.append((P_HARVEST, pos, ["HARVEST"], None))
                if needs_water and not critical:
                    jobs.append((P_WATER, pos, ["WATER"], None))
                # Fertilizer is free from the herd and worth ~$300 on a
                # strawberry tick, versus under $80 sold on a glutted market.
                gain = fertilize_gain(tile, day)
                if gain > 0:
                    value = gain * prices.get(tile["crop"], 0)
                    if value >= FERT_MIN_VALUE:
                        prio = P_FERTILIZE + min(12, value // 100)
                        jobs.append((prio, pos, ["FERTILIZE"], "FERTILIZER"))
                        fert_demand += 1
            elif tile.get("animal"):
                a = ANIMALS[tile["animal"]]
                if not tile["fed_today"]:
                    unfed += 1
                    # consecutive_unfed == 1 means a second miss tonight loses
                    # the animal permanently, structure and all.
                    critical = tile["consecutive_unfed"] >= 1
                    jobs.append((P_FEED_CRIT if critical else P_FEED, pos, ["FEED"], "WHEAT"))
                if tile["yield_units"] > 0:
                    full = tile["yield_units"] >= a["max_held"]
                    prio = P_HARVEST_FINAL if final_day else (P_HARVEST_DUE if full else P_HARVEST)
                    jobs.append((prio, pos, ["HARVEST"], None))
                if not tile["cared_today"] and not final_day:
                    jobs.append((P_CARE, pos, ["CARE"], None))
                if tile.get("fertilizer_available"):
                    jobs.append((P_COLLECT_FERT, pos, ["COLLECT_FERTILIZER"], None))
            elif kind in empty_structures:
                empty_structures[kind] += 1
                if not final_day:
                    for name, a in ANIMALS.items():
                        if a["structure"] == kind:
                            jobs.append((P_PLACE_ANIMAL, pos, ["PLACE", name], name))

    open_shed = [t for t in shed_tiles(board_size) if farm["tiles"][t[1]][t[0]] != "LOCKED"]

    if open_shed and not final_day:
        # Collect animals waiting in the shed, but only as many as we have
        # somewhere to put -- an unplaced animal just drifts back to the shed.
        slot = 0
        for name, a in ANIMALS.items():
            room = empty_structures.get(a["structure"], 0)
            for _ in range(min(shed.get(name, 0), room)):
                jobs.append((P_GET_ANIMAL, open_shed[slot % len(open_shed)],
                             ["PICKUP", name, 1], None))
                slot += 1

        # Wheat for feeding must be in a unit's own hands, so top up whoever is
        # near the shed. Every unit spawns shed-adjacent each morning, which
        # makes the hour-0 pickup essentially free.
        for item, need, prio in (("WHEAT", unfed, P_GET_WHEAT),
                                 ("FERTILIZER", fert_demand, P_GET_FERT)):
            held = sum(i.get(item, 0) for i in inventories)
            deficit = need - held
            stock = shed.get(item, 0)
            if deficit <= 0 or stock <= 0:
                continue
            take = max(1, min(6, stock))
            for k in range(min(len(open_shed), -(-deficit // take))):
                jobs.append((prio, open_shed[k], ["PICKUP", item, take], None))

        # Ferry produce to the shed before the end-of-day drop overflows it.
        # Anything a unit is still holding at nightfall past `shedCapacity` is
        # destroyed -- one measured day lost 66 melon, 15 strawberry and 6 milk
        # to a drop with 77 slots free against 167 units carried. Produce in
        # hand also cannot be sold at all, so hauling turns dead stock into
        # something `plan_sales` can move.
        #
        # `PLACE <item> n` deposits one item type, unlike `DROP` which dumps the
        # whole inventory -- ranchers keep the wheat and fertilizer they carry.
        carried_by_item = {}
        for unit_inv in inventories:
            for item, n in unit_inv.items():
                if item in HAUL_ITEMS and n > 0:
                    carried_by_item[item] = carried_by_item.get(item, 0) + n
        # One haul job moves one unit's holding of one item, so a single job per
        # item type cannot keep up with a harvest burst -- melon matures across
        # every tile on the same day. Scale the number of haulers to the load.
        projected = sum(shed.values()) + sum(sum(v.values()) for v in inventories)
        if projected > HAUL_TRIGGER and carried_by_item:
            slot = 0
            for item, n in sorted(carried_by_item.items(), key=lambda kv: -kv[1]):
                for _ in range(max(1, min(len(open_shed), -(-n // HAUL_PER_UNIT)))):
                    jobs.append((P_HAUL, open_shed[slot % len(open_shed)],
                                 ["PLACE", item, SHED_CAPACITY], item))
                    slot += 1

    build_sites.sort(key=lambda p: (shed_distance(p, board_size), p))
    for kind, pos in zip(build_needs, build_sites):
        jobs.append((P_BUILD, pos, ["BUILD_COOP" if kind == "COOP" else "BUILD_PASTURE"], None))

    # Planting: work the tiles nearest the shed first (short watering routes),
    # taking crops off the plan in order and skipping any we lack seed for.
    if plan and not final_day and obs["hour"] <= PLANT_LATEST_HOUR:
        plantable.sort(key=lambda p: (shed_distance(p, board_size), p))
        budget = dict(seed_budget)
        pending = list(plan)
        for pos in plantable:
            entry = next((e for e in pending if budget.get(e[0], 0) > 0), None)
            if entry is None:
                break
            pending.remove(entry)
            budget[entry[0]] -= 1
            jobs.append((entry[1], pos, ["PLANT", entry[0]], None))

    return jobs, plantable


# --------------------------------------------------------------------------- #
# Assignment
# --------------------------------------------------------------------------- #

def assign(jobs, units, unit_invs, seed_budget):
    """Match units to jobs by value net of travel, best pair first.

    Distance is charged against priority rather than used only as a tiebreak.
    Ranking jobs purely by priority and then handing each one its nearest *free*
    unit drags units across the board -- measured at 91 moves for 36 waterings,
    with units switching targets mid-route as priorities shifted each turn.
    Charging travel keeps work local and stops the thrash.

    Units already on the tile execute; others take one step toward it. PLANT
    consumes the shared seed budget only when actually executed, because the
    environment drops *every* PLANT for a crop if seeds run short.
    """
    pairs = []
    for j, (priority, pos, action, req) in enumerate(jobs):
        for i, upos in enumerate(units):
            if req is not None and unit_invs[i].get(req, 0) <= 0:
                continue
            d = dist(upos, pos)
            score = priority - MOVE_PENALTY * d + (STAY_BONUS if d == 0 else 0)
            pairs.append((score, d, j, i))
    pairs.sort(key=lambda p: (-p[0], p[1], p[2], p[3]))

    actions = {}
    used_units = set()
    used_jobs = set()
    for _, d, j, i in pairs:
        if i in used_units or j in used_jobs:
            continue
        action = jobs[j][2]
        if d == 0:
            if action[0] == "PLANT":
                if seed_budget.get(action[1], 0) <= 0:
                    used_jobs.add(j)
                    continue
                seed_budget[action[1]] -= 1
            actions[i] = action
        else:
            actions[i] = step_toward(units[i], jobs[j][1])
        used_units.add(i)
        used_jobs.add(j)
        if len(used_units) == len(units):
            break
    return actions


def endgame_dropoff(obs, farm, private, board_size, units, actions):
    """On the final day, walk carried produce back to the shed so it can be sold.

    End-of-day auto-drop is free but happens after the last scoring turn, so
    anything still in a unit's hands on day 29 is worth nothing.
    """
    if obs["day"] < LAST_DAY:
        return
    hour = obs["hour"]
    inventories = private.get("inventories", [])
    for i, upos in enumerate(units):
        inv = inventories[i] if i < len(inventories) else {}
        if not any(v > 0 for v in inv.values()):
            continue
        target = open_shed_tile(farm, board_size, upos)
        if target is None:
            continue
        # Leave exactly enough of the day to walk back, so units on the far
        # edge keep harvesting as long as they can still make it in.
        if hour + dist(upos, target) < LAST_SELL_HOUR:
            continue
        actions[i] = ["DROP"] if tuple(upos) == target else step_toward(upos, target)


# --------------------------------------------------------------------------- #
# Market
# --------------------------------------------------------------------------- #

def fib(n):
    a, b = 1, 1
    for _ in range(n):
        a, b = b, a + b
    return a


def affordable_hands(farm):
    """How many hands today's cash could still hire, given what we already hired."""
    money = farm["money"] - CASH_FLOOR
    n = farm.get("hires_today", 0)
    count = len(farm["hands"])
    while count < MAX_HANDS:
        cost = fib(n)
        if money < cost:
            break
        money -= cost
        n += 1
        count += 1
    return count


def sell_floor(item, price_now, day, pressured):
    """Minimum acceptable marginal price, decaying to $1 as the season closes."""
    left = LAST_DAY - day
    if left <= 0:
        return 1
    if left <= 3:
        # Wind the reserve down over the closing days rather than dumping the
        # whole shed into one turn: unsold stock scores nothing, but a single
        # day's dump walks the price to the $1 floor.
        return max(1, int(price_now * (0.45 + 0.15 * left)))
    if pressured:
        return max(1, int(0.5 * price_now))
    slack = max(0.0, min(1.0, (LAST_DAY - 2 - day) / 8.0))
    return max(1, int(max((0.90 + 0.07 * slack) * price_now,
                          0.75 * slack * MARKET_PARAMS[item]["base"])))


def plan_sales(obs, private, orders, keep, carried):
    """Trickle produce out, never pushing a price below its reserve.

    `keep` holds back stock we need for ourselves -- chiefly wheat, which is
    animal feed first and a commodity second.

    `carried` is what the units are holding. Everything they hold is dumped into
    the shed at end of day and anything past `shedCapacity` is *discarded*, so
    room has to exist before then. Selling a strawberry cheaply always beats
    throwing it away, and a shed that is merely near full silently blocks
    BUY_PRODUCT and BUY_ANIMAL as well.
    """
    shed = private["shed"]
    inv = obs["market"]["inventory"]
    day = obs["day"]
    total = sum(shed.values())
    overflow = max(0, total + carried - SHED_CAPACITY)
    # Pressure is the *projected* end-of-day load, not the shed alone: units
    # harvest in bursts and everything they hold lands in the shed at nightfall.
    pressured = total + carried >= SHED_PRESSURE

    holdings = []
    for item, qty in shed.items():
        if item not in MARKET_PARAMS:
            continue
        sellable = qty - (0 if day >= LAST_DAY else keep.get(item, 0))
        if sellable > 0:
            holdings.append((item, sellable))
    # Clear the cheapest stock first when forced, the most valuable first
    # otherwise: a forced sale should give up as little value as possible.
    holdings.sort(key=lambda kv: market_price(kv[0], inv[kv[0]]) * (1 if overflow else -1))

    for item, qty in holdings:
        if len(orders) >= MAX_MARKET_ORDERS:
            break
        price_now = market_price(item, inv[item])
        n = sell_count(item, inv[item], sell_floor(item, price_now, day, pressured), qty)
        if overflow > n:
            n = min(qty, overflow)          # dump at any price rather than lose it
        if n > 0:
            orders.append(["SELL", item, n])
            overflow = max(0, overflow - n)


def plan_fertilizer(obs, private, orders, budget, demand, free_supply):
    """Top up fertilizer when a unit of it is worth well more than it costs.

    On a watered strawberry tick one unit is ~$300 of extra fruit; the glut side
    of the fertilizer curve puts it well under $100. Buying is only worthwhile
    while there are plants queued up that would actually use it.
    """
    shed = private["shed"]
    if obs["day"] >= LAST_DAY - 2 or len(orders) >= MAX_MARKET_ORDERS:
        return budget
    held = shed.get("FERTILIZER", 0) + sum(i.get("FERTILIZER", 0)
                                           for i in private.get("inventories", []))
    # The herd hands us one unit per animal per day for free; only top up what
    # that will not cover, or the shed fills with fertilizer we already had.
    short = demand - held - free_supply
    room = SHED_CAPACITY - sum(shed.values()) - FERT_SHED_MARGIN
    if short <= 0 or room <= 0:
        return budget
    price = market_price("FERTILIZER", obs["market"]["inventory"]["FERTILIZER"])
    best_crop_price = max(obs["market"]["prices"].get(c, 0) for c in ("STRAWBERRY", "TOMATO"))
    if best_crop_price < price * FERT_BUY_RATIO:
        return budget
    qty = min(short, room, int(budget // max(1, price)))
    if qty > 0:
        orders.append(["BUY_PRODUCT", "FERTILIZER", qty])
        budget -= qty * price
    return budget


def plan_livestock(obs, farm, private, orders, budget, n_animals, workforce, board_size):
    """Buy one animal at a time, and keep the shed stocked with feed.

    Wheat is bought rather than always grown: a tile of wheat costs ~10 unit
    actions per 4 units of feed, while the same actions on strawberry are worth
    far more than the wheat's price.
    """
    shed = private["shed"]
    if obs["day"] >= LAST_DAY or len(orders) >= MAX_MARKET_ORDERS:
        return budget, None

    # Count animals in transit as well as in the shed. A unit that has picked
    # one up holds it for a few turns; missing those let the herd overshoot its
    # cap by one per unit in flight (measured: 11 animals against a cap of 8).
    pending = sum(shed.get(name, 0) for name in ANIMALS)
    pending += sum(inv.get(name, 0) for inv in private.get("inventories", [])
                   for name in ANIMALS)
    want_feed = (n_animals + pending) * WHEAT_DAYS_HELD
    have_feed = shed.get("WHEAT", 0) + sum(i.get("WHEAT", 0) for i in private.get("inventories", []))
    shed_room = SHED_CAPACITY - sum(shed.values())

    if want_feed > have_feed and shed_room > 0 and len(orders) < MAX_MARKET_ORDERS:
        price = market_price("WHEAT", obs["market"]["inventory"]["WHEAT"])
        qty = min(want_feed - have_feed, shed_room, int(budget // max(1, price)))
        if qty > 0:
            orders.append(["BUY_PRODUCT", "WHEAT", qty])
            budget -= qty * price

    # One purchase per turn keeps placement (pickup, walk, place) from backing up.
    choice = None
    if pending == 0 and shed_room > 0 and len(orders) < MAX_MARKET_ORDERS:
        choice = pick_animal(obs, farm, shed, board_size, budget, n_animals, workforce)
        if choice:
            orders.append(["BUY_ANIMAL", choice, 1])
            budget -= ANIMALS[choice]["cost"]
    return budget, choice


def plan_hires(obs, farm, orders, budget, target_hands):
    """Hire early in the day -- a hand hired at hour 20 barely works."""
    if obs["hour"] > 3:
        return budget
    have = len(farm["hands"])
    n = farm.get("hires_today", 0)
    while have < target_hands and len(orders) < MAX_MARKET_ORDERS:
        cost = fib(n)
        if budget < cost:
            break
        orders.append(["HIRE"])
        budget -= cost
        n += 1
        have += 1
    return budget


def plan_seeds(obs, private, orders, budget, plan, workforce):
    """Bank enough seed that the whole crew can plant simultaneously next turn.

    Sized per crop: the environment drops *every* PLANT for a crop when the
    shed holds fewer seeds than the number of units trying to use it.
    """
    if not plan:
        return budget
    want = {}
    for crop, _ in plan[:max(workforce, 1)]:
        want[crop] = want.get(crop, 0) + 1
    for crop, n in sorted(want.items(), key=lambda kv: -kv[1]):
        if len(orders) >= MAX_MARKET_ORDERS:
            break
        short = n - private["seeds"].get(crop, 0)
        seed = CROPS[crop]["seed"]
        qty = max(0, min(short, int(budget // seed)))
        if qty > 0:
            orders.append(["BUY_SEED", crop, qty])
            budget -= qty * seed
    return budget


def plan_land(obs, farm, orders, budget, used_tiles, owned_tiles):
    """Expand once the ground we own is mostly in use and the cash is spare.

    Gating on "how many empty tiles are left" deadlocks: the planner declines to
    plant marginal tiles, those tiles stay empty, and the empty count then blocks
    the purchase that would give us tiles worth planting.
    """
    owned = len(farm["unlocked_quadrants"])
    if owned - 1 >= len(LAND_PRICES) or len(orders) >= MAX_MARKET_ORDERS:
        return budget
    # No ladder opponent buys the 4th quadrant, but copying them measured worse
    # for us -- at our efficiency the tiles still pay. What does not pay is
    # buying it too late: we bought it on days 19 and 20 in two ladder games,
    # after strawberry's planting window shuts, and used 3 of its 25 tiles.
    want = 1
    for day, quads in sorted(SCRIPT_LAND.items()):
        if obs["day"] >= day:
            want = quads
    if owned >= want:
        return budget
    cost = LAND_PRICES[owned - 1]
    if budget >= cost * LAND_CASH_MULT:
        orders.append(["BUY_LAND"])
        budget -= cost
    return budget


# --------------------------------------------------------------------------- #
# Agent
# --------------------------------------------------------------------------- #

def play(obs):
    """Decide this turn's actions. Raises on bug; `agent` wraps it."""
    player = obs["player"]
    farm = obs["farms"][player]
    private = obs["private"]
    board_size = len(farm["tiles"])
    shed = private["shed"]

    units = [tuple(farm["farmer"])] + [tuple(p) for p in farm["hands"]]
    units_count = len(units)
    inventories = private.get("inventories", [])
    unit_invs = [inventories[i] if i < len(inventories) else {} for i in range(units_count)]

    plants_alive = weeds = plantable_count = n_animals = 0
    structures = 0
    empty_by_kind = {"COOP": 0, "PASTURE": 0}
    for row in farm["tiles"]:
        for t in row:
            if t is None:
                plantable_count += 1
            elif isinstance(t, dict):
                kind = t.get("kind")
                if kind == "PLANT":
                    plants_alive += 1
                elif kind == "WEED":
                    weeds += 1
                elif kind in empty_by_kind:
                    structures += 1
                    if t.get("animal"):
                        n_animals += 1
                    else:
                        empty_by_kind[kind] += 1

    # Size the crew to the work that actually exists, in action-equivalents. A
    # fixed crew was the second failure of the first version: $609/day of
    # payroll while the whole farm was 25 tiles and had no income for 12 days.
    # Size the crew to the work that exists, but never below a floor: four
    # hands cost $7/day total and the early game needs bodies to build pens
    # and place animals, not just to water 25 tiles.
    work = 2 * (plants_alive + weeds + plantable_count) + ANIMAL_ACTIONS * n_animals
    target_hands = SCRIPT_HANDS[min(obs["day"], len(SCRIPT_HANDS) - 1)]
    burn = hire_burn(target_hands)
    workforce = max(units_count, min(target_hands + 1, 1 + affordable_hands(farm)))

    # Reserve the tiles closest to the shed for livestock and keep crops off
    # them; animals cost ~5 actions a day each and need wheat carried to them.
    reserved = set(animal_slots(farm, board_size,
                                min(MAX_ANIMALS, structures + 4)))

    # Hold cash back for livestock while animals are still worth buying: a cow
    # bought on day 2 returns ~$10k, and letting melon seed soak up the opening
    # bankroll leaves the herd stuck at four head until day nine.
    pending_animals = sum(shed.get(name, 0) for name in ANIMALS)
    pending_animals += sum(inv.get(name, 0) for inv in unit_invs for name in ANIMALS)
    herd_cap = min(MAX_ANIMALS, workforce * 2)
    livestock_open = (n_animals + pending_animals < herd_cap
                      and obs["day"] <= LAST_DAY - 10)
    extra_reserve = LIVESTOCK_RESERVE if livestock_open else 0

    # Plant only what the crew can still water after the animals are served:
    # one missed day turns a plant into a weed and the tile is dead for good.
    spare = workforce * ACTIONS_PER_UNIT - ANIMAL_ACTIONS * n_animals
    allowance = max(0, min(spare // 2 - plants_alive, plantable_count))
    plan = build_plant_plan(obs, farm, shed, board_size, allowance, farm["money"],
                            burn, extra_reserve) if allowance > 0 else []

    fert_want = fertilizer_demand(farm, obs["day"], obs["market"]["prices"])

    orders = []
    keep = {}
    if n_animals:
        keep["WHEAT"] = (n_animals + 1) * WHEAT_DAYS_HELD
    if fert_want:
        keep["FERTILIZER"] = min(fert_want, FERT_KEEP_MAX)
    carried = sum(sum(i.values()) for i in unit_invs)
    plan_sales(obs, private, orders, keep, carried)
    budget = farm["money"] - CASH_FLOOR
    budget = plan_hires(obs, farm, orders, budget, target_hands)
    budget, buying = plan_livestock(obs, farm, private, orders, budget,
                                    n_animals, workforce, board_size)
    budget = plan_fertilizer(obs, private, orders, budget, fert_want, n_animals)
    budget = plan_seeds(obs, private, orders, budget, plan, workforce)
    owned_tiles = 25 * len(farm["unlocked_quadrants"]) * (board_size * board_size) // 100
    budget = plan_land(obs, farm, orders, budget, plants_alive + structures, owned_tiles)

    # Build housing for animals already bought, plus a spare for the next one.
    build_needs = []
    for name in ANIMALS:
        need = shed.get(name, 0) - empty_by_kind[ANIMALS[name]["structure"]]
        build_needs.extend([ANIMALS[name]["structure"]] * max(0, need))
    if buying and empty_by_kind[ANIMALS[buying]["structure"]] == 0:
        build_needs.append(ANIMALS[buying]["structure"])

    seed_budget = dict(private["seeds"])
    jobs, plantable = build_jobs(obs, farm, private, board_size, seed_budget,
                                 plan, reserved, build_needs)
    actions = assign(jobs, units, unit_invs, seed_budget)
    endgame_dropoff(obs, farm, private, board_size, units, actions)

    return {
        "farmer": actions.get(0, ["PASS"]),
        "hands": [actions.get(i, ["PASS"]) for i in range(1, units_count)],
        "market": orders[:MAX_MARKET_ORDERS],
    }


def agent(obs):
    """Entry point. Never raises: a crash would mark the whole submission Error."""
    try:
        return play(obs)
    except Exception:
        if DEBUG:
            raise
        traceback.print_exc(file=sys.stderr)
        hands = 0
        try:
            hands = len(obs["farms"][obs["player"]]["hands"])
        except Exception:
            pass
        return {"farmer": ["PASS"], "hands": [["PASS"]] * hands, "market": []}
