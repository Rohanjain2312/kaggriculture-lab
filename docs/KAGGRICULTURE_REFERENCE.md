# Kaggriculture — Competition Reference

This document is a complete, self-contained reference for building an agent for
the Kaggle "Kaggriculture" competition. It is written for an AI coding agent
(Claude Code) to refer back to repeatedly while building, testing, and
iterating on an agent — game rules, mechanics, and commands you'll use over
and over. For one-time environment setup (venv, kaggle CLI install/auth,
joining the competition), see `KAGGRICULTURE_SETUP.md` instead — do that
first if you haven't already.

- Competition URL: https://www.kaggle.com/competitions/kaggriculture
- Prize pool: $50,000 total — $5,000 each to places 1–10 (not winner-take-all)
- Entry deadline: September 23, 2026
- Type: simulation/agent competition (not a static prediction task) — you submit
  Python code that plays a two-player game repeatedly against a ladder of
  other submitted agents.

---

## 1. What the game is

Two players each manage a separate farm for one 30-day season (720 turns
total: 24 turns/day × 30 days). Each turn, a player's farmer (and any hired
farm hands) can take one action each: move, plant, water, harvest, feed/care
for animals, build structures, etc. Separately, each turn the player can also
queue up to 10 market actions (buy/sell/hire/expand land). The winner is
whoever has the most money in the bank at turn 720. Unsold shed inventory does
not count toward the final score.

## 2. Evaluation and ranking (read this carefully — it shapes strategy)

- Up to 5 submissions/day; only the **latest 2** are actively tracked/matched
  and used for the final leaderboard.
- Each submission plays repeated episodes against similarly-rated opponents
  (skill-rating ladder matchmaking).
- **Only the win/loss/tie outcome affects rating — coin margin does not
  matter.** Winning by $1 and winning by $50,000 are scored identically.
  Rating change scales with the rating gap between opponents (upsets move
  rating more).
- On upload, a validation episode (self-play) must complete without error or
  the submission is marked `Error`.
- At the entry deadline, submissions lock; episodes keep running for ~2 more
  weeks to reduce rating uncertainty, then a **Bradley-Terry tournament**
  produces the final leaderboard from those episodes.
- Because it's top-10-paid (not top-1), a consistently-above-average agent is
  worth pursuing, not just a theoretical-optimum agent.
- Submission constraints: main.py (or a tar.gz with main.py at root) ≤ 100 MiB.
  Runtime resources: 8 GiB HDD, 6.5 GiB RAM, 1.6 vCPUs.
- Per-turn compute budget: `actTimeout` = 1 second per turn, plus a shared
  ~60 second "overage" bank across the whole episode for occasional
  overshoots. A simple heuristic agent uses well under 1% of this; only
  becomes a real constraint if using heavy per-turn compute (e.g. search,
  LLM calls).

## 3. Farm layout

- Grid is `boardSize × boardSize` (default 10×10), split into 4 quadrants
  (NW/NE/SW/SE, 5×5 each). Start owning only NW (25 tiles).
- Buy additional quadrants via market action `BUY_LAND` — cost increases in
  fixed order: $1,000 → $2,000 → $4,000.
- **Locked tiles are passable** (units can walk across/through them) but no
  tile action (PLANT, WATER, BUILD_*, etc.) works on a locked tile — it silently
  no-ops.
- The shed sits at the board's center, occupying the 4 tiles adjacent to the
  exact center point — it is **not** a real tile and never appears in the
  `tiles` array. "Shed-adjacent" means standing on one of those 4 center
  tiles: for `half = boardSize // 2`, they are `(half-1,half-1)`,
  `(half,half-1)`, `(half-1,half)`, `(half,half)` — at default size 10:
  `(4,4)`, `(5,4)`, `(4,5)`, `(5,5)`.
- Weeds can spontaneously spawn on empty unlocked tiles (`weedSpawnChance`,
  default 0.005/tile/day) and must be `DIG`-cleared before replanting.

## 4. Turn structure and processing order (important — affects timing)

Each turn, in this exact order:
1. Action validation
2. **Player actions** (farmer/hands) — resolved simultaneously
3. **Market actions** (buy/sell/hire/land)
4. Town building consumption
5. Observation update
6. Day refresh (plant/animal condition updates, fed/watered flags reset)
7. Market price refresh
8. Income update
9. Farm update (cleared harvested plants, new plants/animals added, etc.)

**Critical consequence:** unit actions (step 2) resolve *before* market
actions (step 3) in the same turn. So a seed/wheat/fertilizer/animal bought
via a market order this turn is only available in the unit's inventory
starting *next* turn — you cannot buy a seed and plant it in the same turn.

## 5. Units: farmer and hired hands

- The farmer and any hired hands can each take one action per turn, and can
  occupy the same tile as each other (no collision).
- `HIRE` is a **market action**. Cost = `farmHandCostMult × fib(n)` where `n`
  is the number of hires already made *that same day* (fibonacci: 1, 1, 2, 3,
  5, 8, 13, 21, 34, 55, 89, 144, ...). **This cost resets every day.**
  Multiple `HIRE` orders can be queued in a single turn's market list (subject
  to the 10-order cap), letting you scale up headcount fast and cheaply early
  in a day.
- **Hired hands vanish at the end of each day** and must be re-hired daily to
  keep them. `farm["hands"]` will read `0` at the very start of each new day
  even if you plan to re-hire immediately.
- A newly hired hand spawns on a free shed-adjacent tile (NWSE preference
  order among the 4 center tiles); if none are free it picks the
  least-occupied one. Spawn placement ignores whether that quadrant is
  locked.

## 6. Crops

| Crop | Yield type | Seed cost | Base price | First yield day | Max yield day | Subsequent yields | Max yield (unfert/fert) | Yield/tile/day |
|---|---|---|---|---|---|---|---|---|
| Wheat | one-time | $10 | $25 | 2 | 4 | none | 4 / 6 | 0.80 |
| Carrot | one-time | $20 | $35 | 2 | 3 | none | 3 / 4 | 0.75 |
| Tomato | ongoing | $50 | $60 | 8 | 8 | every day ×4 (days 8–11) | 4 | 0.33 |
| Strawberry | ongoing | $100 | $120 | 10 | 10 | every other day ×4 (days 10,12,14,16) | 4 | 0.24 |
| Melon | one-time | $80 | $250 | 10 | 12 | none | 6 | 0.55 |

Rules:
- All plants need `WATER` every day (no-op if already watered today). **2
  consecutive missed days → weed** (unrecoverable; must `DIG` to clear the
  tile before reusing it).
- A freshly planted seed starts with `consecutive_unwatered = 1` (the
  planting day itself counts as day 1 already missed) — **there is no grace
  period**: plant and fail to water same day → weed that same night.
- One-time crops start with `yield_units = 1` immediately at planting (a
  guaranteed base unit), **but `HARVEST` silently no-ops until
  `first_yield_day` passes**, even though `yield_units` already reads > 0.
  Don't confuse "has yield_units" with "can actually be harvested."
- One-time crop bonus yield: starting at `ceil(max_yield_day / 2)`, each
  watered day within the bonus window adds +1 to the eventual harvest total
  (+2/day if fertilized that day).
- Ongoing crop yield: base 1 unit per scheduled production tick; if
  fertilized AND watered that same day, that tick's yield doubles to 2.
  Fixed cap of 4 scheduled productions total, then the plant decays (loses 1
  unit every other turn until 0, becomes a weed).
- **Important rule easy to violate:** if multiple units all issue `PLANT`
  in the same turn but the shed's seed inventory for that crop is less than
  the number of units trying to plant, **none of them succeed** (not just
  the excess ones). Seed purchases must be sized to cover simultaneous
  planting by your whole workforce, and remember the 1-turn purchase lag
  from section 4.

## 7. Animals

| Animal | Product | Buy cost | Structure | Base price | First yield day | Feed/produce interval | Max held | Yield/day |
|---|---|---|---|---|---|---|---|---|
| Goose | Egg | $300 | COOP | $50 | 4 | daily | 4 | 1.00 |
| Cow | Milk | $400 | PASTURE | $160 | 8 | every 2 days | 6 | 0.50 |
| Sheep | Wool | $500 | PASTURE | $200 | 6 | every 3 days | 6 | 0.33 |

Rules:
- `BUILD_COOP` / `BUILD_PASTURE`: **free action** (no $ cost), builds the
  structure on any currently-empty tile. Once built it's permanent (whether
  occupied or not); a structure with an animal on it cannot be `DIG`-removed.
- `PLACE <animal>`: standing on a matching, unoccupied structure, moves 1
  animal from the acting unit's inventory onto it.
- A newly placed animal starts `consecutive_unfed = 0` — **it survives its
  first day unfed** (unlike plants, which have no grace period).
- `FEED` consumes 1 WHEAT from the **acting unit's own inventory**, not
  directly from the shed — a unit must `PICKUP` wheat from the shed first.
  Once per day (no-op if already fed today).
- **2 consecutive missed feeds → animal escapes, unrecoverable.** Structure
  remains standing, empty, and can hold a new animal via another `PLACE`.
- `CARE`: once/day action, only prerequisite is not already cared today
  (does not require the animal to be fed first). If an animal was **both**
  fed and cared the same day, it banks `+1 pending_care_bonus` (implicitly
  capped by `max_held`). The full banked bonus pays out on the animal's next
  scheduled production **if the animal is fed that day**; if unfed on the
  production day, base yield (1) still occurs but the bank is lost and
  resets to 0.
- `COLLECT_FERTILIZER`: every surviving animal produces exactly 1 fertilizer
  at end of day, **regardless of feed/care status that day**. It does not
  accumulate if left uncollected — still just 1 available, no backlog.
- Only WHEAT and FERTILIZER can be bought back from the market
  (`BUY_PRODUCT`); every other product (including animal products) is
  sell-only. **Animals themselves (COW/SHEEP/GOOSE) are not valid `SELL`
  items at all** — attempting to sell one silently no-ops.

## 8. Fertilizer

- Obtained by buying (`BUY_PRODUCT FERTILIZER`, base price $100) or free via
  `COLLECT_FERTILIZER` from animals.
- `FERTILIZE`, standing on a plant: for one-time crops, doubles the per-day
  bonus-window yield rate for the next 3 days (bonus still only applies on
  days also watered). For ongoing crops, doubles that day's scheduled yield
  if the plant is also watered that same day.

## 9. Market mechanics

- Every product (and fertilizer) starts with market inventory
  `I0 = 10,000` — vastly larger than any single game's realistic production
  volume. Player `SELL` orders add to inventory; town consumption and player
  `BUY_PRODUCT` orders drain it.
- Price formula:
  ```
  price(inv) = base + sign · amp · f(|inv − I0|)
    sign = +1 if inv < I0 (scarce → price rises)
    sign = −1 if inv > I0 (glut → price falls)
    amp  = target · base / f(T)   (derived, not stored directly)
    f ∈ {linear, sq, sqrt, log, log10}  (log uses ln(1+x))
  ```
  Floored at $1, rounded to nearest dollar. `T` = a resource's calibration
  throughput (roughly, what one 5×5 field could produce in 24 days at
  optimal care). Each side of the curve (scarcity vs. glut) has its own
  independent shape function and target-move multiplier — this is why some
  crops crash hard on oversupply and others don't.

| Resource | Base | T | Below func/target | Above func/target | P(I0−T) | P(I0+T) | P(I0+2T) |
|---|---|---|---|---|---|---|---|
| Wheat | 25 | 400 | sqrt / 0.80 | log / 0.20 | $45 | $20 | $19 |
| Carrot | 35 | 450 | log / 0.20 | sqrt / 0.70 | $42 | $10 | $1 |
| Tomato | 60 | 200 | linear / 0.40 | sqrt / 0.60 | $84 | $24 | $9 |
| Strawberry | 120 | 100 | sqrt / 0.70 | linear / 1.60 | $204 | $1 | $1 |
| Melon | 250 | 300 | log / 0.20 | sq / 3.60 | $300 | $1 | $1 |
| Egg | 50 | 332 | linear / 0.40 | log / 0.20 | $70 | $40 | $39 |
| Milk | 160 | 122 | sqrt / 0.60 | linear / 1.60 | $256 | $1 | $1 |
| Wool | 200 | 105 | log / 0.20 | sq / 3.20 | $240 | $1 | $1 |
| Fertilizer | 100 | 200 | linear / 0.40 | linear / 0.40 | $140 | $60 | $20 |

Key takeaway: **`above_target` (the glut-side multiplier) tells you how hard
a resource's price crashes when you oversupply it.** Melon (3.60) and Wool
(3.20) crash brutally on oversupply despite high base prices; Wheat (0.20)
barely reacts to gluts at all. All 4 of `base/I0/T/below_func/below_target/
above_func/above_target` can be overridden per-resource via
`env.configuration["marketParams"]` at episode creation, sparse-override
style — worth checking if the live competition config differs from these
defaults.

- Orders are processed one unit at a time, concurrently across both players
  — simultaneous same-item orders from both players interleave and each
  incrementally shifts the shared price.
- Buy price is quoted at **post-buy** inventory; sell price is quoted at
  **pre-sell** inventory. An immediate buy immediately followed by a sell of
  the same quantity, with no other market activity in between, nets exactly
  $0.
- `maxMarketOrdersPerTurn` = 10 by default — orders past this limit are
  silently dropped, so prioritize.
- **`shedCapacity` also gates buying.** `BUY_PRODUCT` and `BUY_ANIMAL` both
  fail outright when the shed is at capacity (`_commit_unit` checks
  `sum(shed.values()) >= shed_capacity`), so a shed left full silently stops
  restocking feed and buying livestock — with no error anywhere.

## 10. Town buildings (passive demand)

- A new shop unlocks every `townShopUnlockInterval` days (default 3),
  randomly chosen from remaining unopened shops; stays active permanently
  once unlocked.
- Each unlocked shop consumes 1 of every product it demands every
  `townShopSellInterval` turns (default 4) — single-product shops consume 2×.
- The town center additionally consumes 1 of every product (excluding
  fertilizer) every `townCenterSellInterval` turns (default 12); this
  increases to 2× after day 10, and 4× after day 20.

| Shop | Demands |
|---|---|
| Bakery | Egg, Wheat |
| Pizza Shop | Milk, Tomato, Wheat |
| Brunch Spot | Egg, Wheat, Strawberry |
| Yarn Store | Wool (2×) |
| Ice Cream Shop | Strawberry, Milk, Wheat |
| Pet Cafe | Carrot (2×) |
| Smoothie Shop | Strawberry, Milk |
| Farmers Market | Wheat, Carrot, Tomato, Strawberry |

## 11. Actions reference

**Movement:** `NORTH`/`SOUTH`/`EAST`/`WEST` — one cell; off-board moves are
no-ops.

**Shed interaction:**
- `PICKUP <item> [n]` (default 1) — must be shed-adjacent; moves up to n of
  any item from shed into the acting unit's inventory. Seeds are a separate
  slot and are never picked up this way — `PLANT` consumes seed inventory
  directly.
- `DROP` — shed-adjacent only; dumps the unit's **entire** inventory into the
  shed at once. Overflow past `shedCapacity` (default 100, excludes seeds)
  is discarded, no partial-fit logic.
- **`PICKUP`/`DROP` silently no-op on a `LOCKED` tile.** `_apply_unit_action`
  returns on `tile == "LOCKED"` *before* reaching them. This bites in practice:
  hands spawn onto shed-access tiles in NWSE order and three of those four
  tiles are in quadrants you don't own at the start, so a freshly hired hand
  routinely cannot pick anything up until it steps to an unlocked one.
- **At end of day every unit's inventory is dropped into the shed for free**
  (`_end_of_day` → `_drop_inventories_to_shed`), obeying `shedCapacity` with
  overflow discarded. Units therefore never need a return trip just to deposit
  produce — they can work the far edge of the board all day. The corollary is
  that the shed must have room *before* the day ends or the surplus is
  destroyed, so sell down during the day.

**Plants:** `PLANT <crop>`, `WATER`, `HARVEST`, `FERTILIZE` (all standing on
the target tile).

**Animals:** `PLACE <item> [n]` — dual purpose: standing on a matching empty
structure places 1 animal (n ignored); standing shed-adjacent, moves up to n
of an item from inventory into the shed (this is a *partial*, single-item
alternative to `DROP`'s dump-everything behavior — useful for depositing
produce while keeping wheat/fertilizer in inventory). `FEED`, `HARVEST`,
`COLLECT_FERTILIZER`, `CARE` (all standing on the animal tile).

**Terrain:** `BUILD_COOP`, `BUILD_PASTURE` (empty tile, free), `DIG` (removes
a plant, weed, or empty coop/pasture from a tile; no-op on an occupied
structure).

**Other:** `PASS` (default/optional no-op).

**Market actions** (queued list, up to 10/turn):
- `["BUY_SEED", crop, n]`
- `["BUY_ANIMAL", animal, n]`
- `["BUY_PRODUCT", item, n]` — WHEAT or FERTILIZER only
- `["SELL", item, n]` — any product except animals
- `["HIRE"]` — no args; cost is the fibonacci curve described in section 5
- `["BUY_LAND"]` — no args; buys the next quadrant in fixed cost order

## 12. Observation format

Top-level `obs` passed to the agent function each turn:

```python
{
  "player": int,            # 0 or 1 (which farm is "yours")
  "day":    int,             # 0-indexed in-game day
  "hour":   int,              # 0-indexed turn within the day (0-23)
  "farms":  [farm, farm],    # public state for BOTH players, indexed by id
  "market": {
    "inventory": {"WHEAT": int, ...},
    "prices":    {"WHEAT": int, ...},
  },
  "town": {"unlocked_shops": ["BAKERY", ...]},
  "private": {               # only YOUR data; opponent's private state hidden
    "shed":        {"WHEAT": int, "GOOSE": int, "FERTILIZER": int, ...},
    "seeds":       {"WHEAT": int, "CARROT": int, ...},
    "inventories": [farmer_inv, hand_inv, ...],  # [0]=farmer, then hands in
                                                   # the same order as farm["hands"]
  },
}
```

Each `farm` dict (public — you can see both your own and the opponent's):
```python
{
  "money":              float,
  "tiles":              [[tile, ...], ...],   # tiles[y][x]
  "farmer":             [x, y],
  "hands":              [[x, y], ...],         # this day's hired hands
  "unlocked_quadrants": ["NW", ...],
  "hires_today":        int,                   # drives next HIRE cost
}
```

A `tile` is one of:
- `None` — empty, unlocked
- `"LOCKED"` — in an unpurchased quadrant
- a plant dict: `{"kind":"PLANT", "crop":str, "planted_day":int,
  "watered_today":bool, "consecutive_unwatered":int, "yield_units":int,
  "max_lifespan_step":int, "fertilized_until_day":int}`
- a weed dict: `{"kind":"WEED"}`
- an animal structure dict: `{"kind":"COOP"|"PASTURE", "animal":str|None,
  "placed_day":int, "yield_units":int, "fed_today":bool,
  "consecutive_unfed":int, "cared_today":bool,
  "fertilizer_available":bool, "pending_care_bonus":int}`

Your agent function returns:
```python
{"farmer": [action, ...], "hands": [[action,...], ...], "market": [[op, ...], ...]}
```
`hands` is a list of action-lists, one per currently-alive hand, in the same
order as `farm["hands"]`.

## 13. Configuration defaults

| Parameter | Default | Notes |
|---|---|---|
| `episodeSteps` | 720 | 24 turns × 30 days |
| `boardSize` | 10 | four 5×5 quadrants |
| `startingMoney` | 3000 | |
| `maxMarketOrdersPerTurn` | 10 | extras silently dropped |
| `turnsPerDay` | 24 | |
| `shedCapacity` | 100 | non-seed items; overflow discarded on deposit |
| `weedSpawnChance` | 0.005 | per empty tile per day |
| `townShopUnlockInterval` | 3 days | |
| `townShopSellInterval` | 4 turns | |
| `townCenterSellInterval` | 12 turns | doubles after day 10, 4× after day 20 |
| `seed` | null | optional deterministic episode seed |

**Verify these against the live competition config before assuming they
match** — this doc reflects the SDK defaults as of this writing; the actual
competition may run with different overrides. Check via
`kaggle competitions pages kaggriculture --content` or by inspecting an
episode replay's `configuration` field.

---

## 14. What we've explored so far (context, not a prescription)

This is background on prior exploration in this project, given so a fresh
agent doesn't repeat the same investigation from zero — **not** a strategy to
follow blindly. Form your own view of the best approach; these are just data
points.

- A simple greedy heuristic (rank crops/actions by immediate $ value, execute
  the best legal action each turn) is enough to comfortably beat the
  built-in `random`, `pass`, and `starter` baseline agents, landing in the
  roughly $25–35k final-money range in self-tests.
- We reviewed a real competition replay where the winning agent scored
  ~$164k (vs. our ~$25-35k), roughly 5x higher. Some directly observable
  facts from that replay (via the full action log in the replay JSON, not
  speculation): it built and maintained a stable herd of ~14 animals (only
  cows and sheep — no geese observed), applied fertilizer regularly and
  continuously (hundreds of `FERTILIZE` and `COLLECT_FERTILIZER` actions
  across the game), scaled its hired workforce to ~12 units by day 11,
  capped land expansion at 3 of 4 quadrants despite large cash reserves, and
  favored strawberry heavily over melon in its planting mix despite melon's
  higher raw yield/day — plausibly related to how hard each crop's price
  crashes on oversupply (see the `above_target` values in section 9), though
  we didn't confirm the exact reasoning the winning agent used.
- We attempted to replicate a similarly large animal operation (multiple
  hired "hauler" units ferrying wheat/fertilizer between the shed and
  scattered pasture tiles) and ran into real difficulty keeping a
  large herd (10+ animals) reliably fed once land expanded across a
  larger board — animals kept starving (2 missed feeds = permanent loss)
  faster than a couple of dedicated logistics units could keep up with
  visiting every animal daily, especially once animals were spread across
  75+ tiles. Repeatedly re-buying dead animals ($400-500 each) ate into
  profitability faster than the herd was generating. We scaled back to a
  much smaller, reliably-fed animal footprint (1-2 animals) as a stopgap,
  which stabilized results but captured little of the apparent upside from
  the high-scoring replay.
- **RESOLVED (see `main.py`): a large herd needs neither persistent roles nor
  RL/search.** It needs three mechanics from the source, all of them cheap:
  (1) end-of-day auto-drop means units never make a return trip to deposit;
  (2) every unit spawns shed-adjacent each morning, so the daily wheat pickup
  costs one action at hour 0; (3) `COOP`/`PASTURE` can be built *on* the
  shed-access tiles, where an animal is fed, cared, harvested and collected
  from with zero movement. Build the herd on the tiles nearest the shed,
  charge travel against job priority when assigning units, and give
  "this animal starves tonight" (`consecutive_unfed == 1`) the top priority.
  A fully stateless agent doing this holds **zero starvation deaths across
  every seed tested**. The earlier failure was spatial, not architectural:
  animals scattered over 75+ tiles cannot be serviced, wherever the logic lives.
- Two things that cost ~2x when we got them wrong, both worth checking in any
  successor: valuing the *standing* herd with "what would an animal placed
  today yield" understates it badly and causes runaway cow buying (use
  `placed_day`); and animal-count caps must include animals in transit (bought,
  picked up, not yet placed) or the herd overshoots by one per unit in flight.
- We have not yet attempted: goose/egg farming, tomato-heavy strategies,
  active price-timing (e.g. deliberately withholding sales to let a crashed
  price recover), fertilizer purchased from the market (as opposed to
  relying solely on free animal-collected fertilizer), or any multi-turn
  lookahead/planning as opposed to purely greedy per-turn decisions.

## 15. Submission workflow (commands you'll use repeatedly while iterating)

One-time environment setup (venv, kaggle CLI install, auth, joining the
competition) is in `KAGGRICULTURE_SETUP.md` — do that first if not already
done. Everything below is what you'll actually run over and over as you
iterate on the agent.

### Local testing (before every submission)
```bash
python3 -c "
from kaggle_environments import make
env = make('kaggriculture', configuration={'episodeSteps': 720}, debug=True)
env.run(['main.py', 'starter'])   # also test against 'random' and 'pass'
final = env.steps[-1]
for i, s in enumerate(final):
    print(f'Player {i}: status={s.status}, reward={s.reward}')
"
```
Confirm `status=DONE` for both players (not `ERROR`) before submitting. Also
worth tracing money/land/hands/animals over time at fixed intervals (e.g.
every 24 steps = once per day) to sanity-check the agent is actually
progressing, not stuck — see section 17 for a pitfall specific to this (hired
hands correctly show `0` at the exact start of each day before that day's
re-hiring happens — this is normal, not a bug, if sampling exactly at day
boundaries).

### Single-file submission
```bash
kaggle competitions submit kaggriculture -f main.py -m "description of this version"
```

### Multi-file submission (modular code)
Bundle everything into a tar.gz with `main.py` at the root; `main.py` can
import sibling files normally, exactly as it would running locally from that
same folder.
```bash
tar -czf submission.tar.gz main.py <other .py files...>
kaggle competitions submit kaggriculture -f submission.tar.gz -m "description"
```

### Checking status
```bash
kaggle competitions submissions kaggriculture      # list your submissions + status
kaggle competitions episodes <SUBMISSION_ID>       # episodes a submission has played
kaggle competitions episodes <SUBMISSION_ID> -v    # CSV output
kaggle competitions leaderboard kaggriculture -s   # current leaderboard
```
Submission status flow: `pending` (running self-play validation) →
`complete` (validated, now in matchmaking pool) or `error` (crashed —
download logs to debug, see below).

### Debugging a specific episode
```bash
kaggle competitions replay <EPISODE_ID> -p ./replays   # full game state + actions JSON
kaggle competitions logs <EPISODE_ID> 0 -p ./logs       # stdout/stderr for player 0
kaggle competitions logs <EPISODE_ID> 1 -p ./logs       # stdout/stderr for player 1
```
The **replay** JSON (`kaggle competitions replay`) contains the full
game — `rewards`, `statuses`, and a `steps` array where each step has
`observation` (full game state that turn) and `action` (what was submitted
that turn) per player. This is what you want to actually understand *why* a
game was won or lost — the **logs** file only has stdout/stderr/duration per
turn, useful for catching crashes/timeouts but not strategic analysis.

## 16. Built-in test opponents

The `kaggle_environments` package ships 3 agents you can test against by
name (no need to write them yourself): `"pass"` (always no-ops — tests raw
solo performance with zero competitive pressure), `"random"` (random legal
actions — a very low bar), and `"starter"` (the deterministic baseline
agent shown in the competition's own Quick Start docs — the most meaningful
of the three, but still a weak baseline). None of these represent real
competitive opponents; treat beating all three easily as a sanity check, not
a sign of competitiveness — real opponents on the ladder are agents other
competitors have submitted, of unknown but likely much greater
sophistication.

## 17. General debugging principles for this environment

- **Most invalid actions silently no-op rather than raising errors** — e.g.
  planting on a locked tile, harvesting an immature plant, digging an
  occupied structure, moving off the board edge, feeding an already-fed
  animal, or exceeding `maxMarketOrdersPerTurn`. There is usually no
  exception or log message; the action just has no effect. This makes bugs
  easy to miss silently — when an agent seems to be "doing things" but not
  progressing, trace actual game state (money/tiles/inventory) over time
  rather than trusting that queued actions did what was intended.
- `env.run([...])` can swallow exceptions inside your agent and simply mark
  the episode `ERROR` without a full traceback in an easy-to-read place. For
  detailed debugging, drive the loop manually instead, which surfaces
  exceptions immediately with a full traceback:
  ```python
  from kaggle_environments import make
  import main as agent_mod

  env = make("kaggriculture", configuration={"episodeSteps": 100}, debug=True)
  env.reset(2)
  for step in range(100):
      obs = env.state[0].observation
      action = agent_mod.agent(dict(obs))   # exceptions surface here directly
      env.step([action, {"farmer": ["PASS"], "hands": [], "market": []}])
  ```
- When sampling game state at fixed step intervals to trace progress over
  time (e.g. `env.steps[i]` every 24 steps to check once per day), sampling
  exactly on a day boundary will show hired hands as freshly reset to `0`
  even when the agent is hiring normally every day — hands are re-hired
  within that same day's later turns. This is expected, not a bug. Sample
  mid-day (e.g. offset by 12 steps) or check `hires_today` for a truer
  read.
- For short quick-iteration tests, pass a smaller `episodeSteps` to `make()`
  (e.g. 48–100) rather than always running the full 720-turn game — a full
  game takes a few seconds locally, which adds up over many debug iterations.
- The installed SDK also ships a second, apparently simpler environment
  called `kaggriculture_beginner` alongside `kaggriculture` — worth a quick
  look if faster/simpler local iteration during early development is useful,
  but note **the actual competition runs on `kaggriculture`**, not the
  beginner variant — final testing and submission must target
  `kaggriculture`.
