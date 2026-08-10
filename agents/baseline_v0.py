"""
Kaggriculture greedy heuristic baseline.

Strategy per turn, for every unit (main farmer + hired hands):
  1. If standing on a plant that needs water today -> WATER (avoid weeds, top priority).
  2. If standing on a tile with harvestable yield -> HARVEST.
  3. If standing on an empty tile and we're holding a seed -> PLANT the best crop.
  4. Otherwise, walk toward the nearest tile that needs attention (water / harvest /
     plant), picking distinct targets per unit so hands don't pile on the same tile.

Market actions (every turn):
  - Sell everything sitting in the shed.
  - Buy a seed of the current best-ranked affordable crop if we have an empty tile
    and no seed queued for it.
  - Buy land once we're cash-rich and running out of empty tiles.
  - Hire an extra hand once we can comfortably afford the next hire and have room
    to put them to work.

Crop ranking uses the yield/tile/day figures from the competition docs multiplied
by the *live* market sell price, so the agent naturally shifts away from crops
whose price it has crashed.
"""

# yield/tile/day at max watering, no fertilizer (unfertilized) -- from Object Types table
YIELD_PER_DAY = {
    "WHEAT": 0.80,
    "CARROT": 0.75,
    "TOMATO": 0.33,
    "STRAWBERRY": 0.24,
    "MELON": 0.55,
}
SEED_COST = {"WHEAT": 10, "CARROT": 20, "TOMATO": 50, "STRAWBERRY": 100, "MELON": 80}
FIRST_YIELD_DAY = {"WHEAT": 2, "CARROT": 2, "TOMATO": 8, "STRAWBERRY": 10, "MELON": 10}
MAX_YIELD_DAY = {"WHEAT": 4, "CARROT": 3, "TOMATO": 8, "STRAWBERRY": 10, "MELON": 12}

CASH_BUFFER = 150          # keep this much cash in reserve before spending on land/hires
LAND_MONEY_MULT = 1.3      # buy land once money comfortably covers cost (proactively, not reactively)
TILES_PER_UNIT = 11        # empirical: one farmer/hand can maintain ~11 tiles/day (water+harvest+replant)
MAX_HANDS = 15             # ceiling; fib hire cost grows fast so this is a soft cap in practice


def _fib_hire_cost(n_already_today):
    a, b = 1, 1
    for _ in range(n_already_today):
        a, b = b, a + b
    return a


def rank_crops(prices):
    """Return crop names sorted best -> worst by $ per tile per day at current prices."""
    scored = []
    for crop, ypd in YIELD_PER_DAY.items():
        price = prices.get(crop, 0)
        scored.append((ypd * price, crop))
    scored.sort(reverse=True)
    return [c for _, c in scored]


def is_ready_to_water(tile):
    return isinstance(tile, dict) and tile.get("kind") == "PLANT" and not tile.get("watered_today", False)


def is_ready_to_harvest(tile, day):
    if not isinstance(tile, dict):
        return False
    if tile.get("yield_units", 0) <= 0:
        return False
    # One-time/ongoing crops start with yield_units pre-seeded but aren't
    # actually harvestable until first_yield_day passes -- the env silently
    # no-ops HARVEST until then, so we must gate on it too or the unit gets
    # stuck spamming a no-op instead of watering/moving on.
    if tile.get("kind") == "PLANT":
        return day - tile["planted_day"] >= FIRST_YIELD_DAY[tile["crop"]]
    return True  # animal products: yield_units only accrues when actually ready


def is_empty(tile):
    return tile is None


def find_targets(farm, board_size, day):
    """Collect candidate tiles for watering / harvesting / planting, nearest-first later."""
    water_targets, harvest_targets, empty_targets = [], [], []
    for y in range(board_size):
        row = farm["tiles"][y]
        for x in range(board_size):
            tile = row[x]
            if tile == "LOCKED":
                continue
            if is_ready_to_water(tile):
                water_targets.append((x, y))
            if is_ready_to_harvest(tile, day):
                harvest_targets.append((x, y))
            if is_empty(tile):
                empty_targets.append((x, y))
    return water_targets, harvest_targets, empty_targets


def nearest(pos, candidates, claimed):
    fx, fy = pos
    best, best_d = None, None
    for (x, y) in candidates:
        if (x, y) in claimed:
            continue
        d = abs(x - fx) + abs(y - fy)
        if best_d is None or d < best_d:
            best, best_d = (x, y), d
    return best


def step_toward(pos, target):
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


def act_for_unit(pos, tile, water_targets, harvest_targets, empty_targets, claimed,
                  best_crop, seed_budget, day):
    fx, fy = pos

    # 1. Water what we're standing on.
    if is_ready_to_water(tile):
        return ["WATER"], None

    # 2. Harvest what we're standing on.
    if is_ready_to_harvest(tile, day):
        return ["HARVEST"], None

    # 3. Plant if we're on empty land and hold a seed. seed_budget is a
    # shared counter across ALL units acting this turn -- the engine drops
    # every PLANT this turn if there isn't a seed for each one, so we must
    # gate on and decrement a running total rather than the raw inventory
    # count (which every unit would otherwise see as untouched).
    if is_empty(tile) and best_crop and seed_budget.get(best_crop, 0) > 0:
        seed_budget[best_crop] -= 1
        return ["PLANT", best_crop], None

    # 4. Otherwise move toward the closest useful tile (priority: water > harvest > plant).
    target = nearest((fx, fy), water_targets, claimed)
    if target is None:
        target = nearest((fx, fy), harvest_targets, claimed)
    if target is None and best_crop:
        target = nearest((fx, fy), empty_targets, claimed)
    if target is None:
        return ["PASS"], None
    claimed.add(target)
    return step_toward((fx, fy), target), target


def agent(obs):
    player = obs["player"]
    farm = obs["farms"][player]
    private = obs["private"]
    market = obs["market"]
    day = obs["day"]
    board_size = len(farm["tiles"])

    prices = market["prices"]
    crop_order = rank_crops(prices)
    best_crop = crop_order[0] if crop_order else None

    water_targets, harvest_targets, empty_targets = find_targets(farm, board_size, day)
    claimed = set()
    seed_budget = dict(private["seeds"])  # shared, decremented as units claim PLANT this turn

    # --- Unit actions (main farmer + hands) ---
    fx, fy = farm["farmer"]
    farmer_tile = farm["tiles"][fy][fx]
    farmer_action, _ = act_for_unit(
        (fx, fy), farmer_tile, water_targets, harvest_targets, empty_targets,
        claimed, best_crop, seed_budget, day,
    )

    hands_actions = []
    for hx, hy in farm["hands"]:
        h_tile = farm["tiles"][hy][hx]
        h_action, _ = act_for_unit(
            (hx, hy), h_tile, water_targets, harvest_targets, empty_targets,
            claimed, best_crop, seed_budget, day,
        )
        hands_actions.append(h_action)

    # --- Market actions ---
    market_orders = []
    shed = private["shed"]

    # Sell everything in the shed.
    for item, qty in shed.items():
        if qty > 0:
            market_orders.append(["SELL", item, qty])

    # Buy seed of the best crop, sized to the whole workforce -- plant actions
    # are resolved *before* market actions each turn (see turn processing
    # order), so seed bought now is only usable next turn. Keep enough banked
    # that every unit can plant simultaneously.
    total_units = 1 + len(farm["hands"])
    seed_shortfall = max(0, total_units - private["seeds"].get(best_crop, 0)) if best_crop else 0
    seed_spend = 0
    if best_crop and empty_targets and seed_shortfall > 0:
        affordable_qty = int((farm["money"] - CASH_BUFFER) // SEED_COST[best_crop])
        qty = max(0, min(seed_shortfall, affordable_qty))
        if qty > 0:
            market_orders.append(["BUY_SEED", best_crop, qty])
            seed_spend = qty * SEED_COST[best_crop]

    # Hire aggressively -- hire cost is cheap (fibonacci curve, resets daily)
    # and each hand is a full extra 24 actions/day. Size the target to the
    # farm's eventual footprint (all 4 quadrants), not just currently-unlocked
    # land, so we have workers ready the moment new land opens up. Hiring
    # takes priority over land purchases in spending order -- land is useless
    # without workers to work it.
    total_tiles = board_size * board_size
    target_hands = min(MAX_HANDS, max(0, total_tiles // TILES_PER_UNIT - 1))
    current_hands = len(farm["hands"])
    hires_today = farm.get("hires_today", 0)

    available = farm["money"] - CASH_BUFFER - seed_spend

    hires_queued = 0
    h = hires_today
    while current_hands + hires_queued < target_hands and len(market_orders) < 10:
        cost = _fib_hire_cost(h)
        if available < cost:
            break
        market_orders.append(["HIRE"])
        available -= cost
        h += 1
        hires_queued += 1

    # Buy land with whatever's left once hiring is funded -- land compounds
    # once we have workers to farm it, but shouldn't starve the hire budget.
    unlocked = len(farm["unlocked_quadrants"])
    land_costs = [1000, 2000, 4000]
    if unlocked - 1 < len(land_costs) and len(market_orders) < 10:
        land_cost = land_costs[unlocked - 1]
        if available - land_cost >= 0 and farm["money"] - CASH_BUFFER >= land_cost * LAND_MONEY_MULT:
            market_orders.append(["BUY_LAND"])

    market_orders = market_orders[:10]  # respect maxMarketOrdersPerTurn

    return {"farmer": farmer_action, "hands": hands_actions, "market": market_orders}