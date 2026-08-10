# Kaggriculture — Workload & Hiring Strategy (living doc)

This is a working brainstorm, not a finished spec — it gets updated as the
idea develops. Goal: solve "how many units do we need today, and are we
using every unit's every turn productively" — the core weakness identified
in earlier agent attempts (idle units, or units starved of workers for
critical tasks like animal feeding).

This problem splits into two genuinely separate sub-problems, worth keeping
distinct:
- **(a) Headcount** — how many total units (farmer + hands) do we want today?
  This doc's formulas are aimed at this.
- **(b) Routing** — given that headcount, making sure no unit sits idle on
  any specific turn. Requires per-turn priority/task-assignment logic on top
  of this, not a replacement for it.

---

## 1. State fields to track

**All of these come directly from the current observation (`obs`) by
scanning it — nothing here needs to be remembered across turns or days.**
See section 2 below for exactly where each field lives and how it's kept
current.

### Crops
- count of tiles needing water today
- count of tiles ready to harvest today
- count of empty, plantable tiles
- count of tiles needing fertilizer (not already fertilized/expired)
- count of tiles that have become weeds (need `DIG` to clear)
- **urgent subset:** count of tiles at `consecutive_unwatered == 1` (i.e.
  will become a weed tonight if not watered today) — these should outrank
  a generic "needs water" tile that has more slack

### Animals
- count needing feed today
- count needing care today
- count with fertilizer ready to collect
- count with product ready to harvest
- count of empty structures (built but no animal placed)
- **urgent subset:** count at `consecutive_unfed == 1` (will escape tonight
  if not fed today) — same idea as the weed-risk crops, should outrank a
  generic "needs feed" animal that was just fed yesterday

### Logistics / inventory
- wheat currently in shed
- fertilizer currently in shed
- animals currently in shed, bought but not yet placed
- seed counts in inventory, per crop (needed to avoid over-committing PLANT
  actions across units when supply is short — see reference doc section 6)
- shed fill level vs `shedCapacity` (100) — if near full, produce may get
  silently discarded on drop/end-of-day

### Land / workforce / context
- current unit count (farmer + hands)
- unlocked land area (tile count) — needed for the travel-time formula below
- current money (for affordability checks on hiring/buying)

### Market (context, not "workload" exactly, but needed for other decisions)
- current prices per resource
- current market inventory per resource (for glut-awareness — see reference
  doc section 9)

---

## 2. Where these fields actually come from

No custom state-tracking system is needed for any of the per-tile fields —
the game engine maintains and auto-updates them, and the current `obs` is
always fully up to date:

- `obs["farms"][player]["tiles"][y][x]` — each tile dict already carries
  `watered_today`, `consecutive_unwatered`, `planted_day`, `yield_units`,
  `fertilized_until_day` (plants) or `fed_today`, `consecutive_unfed`,
  `cared_today`, `fertilizer_available` (animals). These reset/increment
  automatically during the game's own daily refresh — just scan the tiles
  array fresh each turn and count.
- `obs["private"]["shed"]` — current shed inventory (wheat, fertilizer,
  animals waiting to be placed, harvested produce).
- `obs["private"]["seeds"]` — current seed inventory per crop.
- `obs["farms"][player]["money"]`, `["hands"]`, `["unlocked_quadrants"]` —
  workforce and land context.
- `obs["market"]["prices"]`, `["inventory"]` — market context.

**The only thing genuinely worth deriving/aggregating yourself is the
*counts* above (e.g. "how many tiles need water") — a single pass over the
tiles array each turn, not a persisted structure.**

---

## 3. Travel-time estimation (Option B — density-aware formula)

Rejected the simpler "N tiles per unit per day" constant in favor of this,
since the flat-constant approach was the direct cause of the animal-feeding
failure in an earlier attempt (it didn't account for tasks being spread
across a larger board once land expanded).

**Core idea:** for `N` tasks scattered across an area of size `A`, the total
travel distance to visit all of them in a sensible order scales roughly with
`sqrt(N × A)`, not `N` itself — tasks stay reachable via short hops as long
as they aren't *too* sparse relative to the area.

```
estimated_travel_turns ≈ C × sqrt(task_count × active_area)
total_turns_needed     ≈ task_count + estimated_travel_turns

turns_available_per_day = 24 × num_units

Hire/keep units until: turns_available_per_day ≥ total_turns_needed
```

`C` is a tunable constant, not yet calibrated — placeholder `C = 1.0` used
in the worked examples below purely to see the shape of the numbers.
`active_area` = current unlocked tile count (25 / 50 / 75 / 100).

### Worked example 1 — small early-game crop operation
~12 planted tiles all needing water/harvest, land = NW only (25 tiles).
```
task_count = 12, active_area = 25
travel ≈ 1.0 × sqrt(12 × 25) = sqrt(300) ≈ 17.3
total_turns_needed ≈ 12 + 17.3 ≈ 29.3
```
One unit provides 24 turns/day → **not quite enough**, need 2 units
(48 turns available) to comfortably cover it. Matches the rough shape of
what we saw empirically (a single farmer struggled to keep ~12 tiles
serviced without falling behind).

### Worked example 2 — the animal-feeding failure case
14 animals, each needing ~3 daily actions (feed, care, collect fertilizer)
≈ 42 tasks/day, spread across land = 3 quadrants (75 tiles).
```
task_count = 42, active_area = 75
travel ≈ 1.0 × sqrt(42 × 75) = sqrt(3150) ≈ 56.1
total_turns_needed ≈ 42 + 56.1 ≈ 98.1
```
At 24 turns/unit/day, that's **~4.1 units needed just for animal upkeep
alone** (round up to 5). We had allocated only 2 "hauler" units to this job
— roughly half of what the math says was actually required. This lines up
directly with why animals kept starving despite having dedicated logistics
units.

### Worked example 3 — full-scale mixed operation
~50 planted crop tiles (watering + some harvesting ≈ 60 crop tasks/day) +
the 42 animal tasks from example 2, land = 75 tiles.
```
task_count = 102, active_area = 75
travel ≈ 1.0 × sqrt(102 × 75) = sqrt(7650) ≈ 87.5
total_turns_needed ≈ 102 + 87.5 ≈ 189.5
```
At 24 turns/unit/day that needs **~7.9 units** (round up to 8), and with
farmer + 8 hands (9 units, 216 turns available) we'd be just barely covering
it — 216 vs. 189.5 needed, ~13% slack. Matches the sense that our
actual workforce was stretched thin trying to run the full operation.

**Not yet done, flagged for later:** calibrating `C` against real gameplay
(the examples above use an untuned placeholder), and validating whether
`sqrt(task_count × active_area)` is actually the right shape once tested
against real agent runs vs. just a plausible starting guess.

---

## 4. Open items / not yet resolved

- Calibrate `C` in the travel-time formula against actual measured
  performance (run the agent, compare estimated vs. actual turns needed).
- Decide how urgency-weighted tasks (the "about to fail today" subsets in
  section 1) should factor into the headcount formula itself, vs. just
  being used for turn-by-turn task *priority* (problem (b), not (a)).
- Zone sizing/shape: fixed tile count per zone, or dynamic sizing driven by
  the section 3 formula (a zone with several animals in it should probably
  be smaller than a zone that's pure wheat, since it carries more turns of
  work per tile)?
- Since hired hands vanish and are re-hired daily, zone assignment can't
  persist on its own — needs to be reconstructed fresh each day. Worth
  deciding whether reconstruction should try to keep the same unit on
  roughly the same patch day-to-day (less disruption, shorter travel to
  get back to work) or is fully free to reassign.

## 5. Candidate answer to problem (b) — zone-based routing

Rather than a shared farm-wide task pool with units competing/claiming
targets (what an earlier attempt did, including a separate roaming
"hauler" role for feed/fertilizer logistics), a simpler candidate: assign
each unit a fixed patch of tiles (a "zone") and have it handle *every*
function for its own zone — watering, harvesting, weeding, feeding,
fertilizing, all of it — rather than splitting duties by task type across
the whole farm.

Why this looks promising:
- A unit only ever competes for its own small patch, so idle units and
  duplicate-targeting conflicts (two units walking toward the same tile)
  are avoided by construction, not by extra coordination logic.
- Feed/fertilize logistics become local: a unit only needs to detour to the
  shed when its *own* zone has an animal/fertilizable plant in it, and can
  restock once (a batch pickup) to cover multiple tiles in that same zone
  before needing to return — no separate dedicated "hauler" role competing
  against generalist units for priority.
- Most non-carry actions (HARVEST, WATER, DIG) need nothing pre-loaded, so a
  unit can freely chain them across its zone with zero shed trips; only
  FEED/FERTILIZE/PLACE require a prior pickup.
- Zone count directly determines headcount: number of zones needed ≈ number
  of units to hire, and (per the open item above) zone size should ideally
  be derived from the section 3 workload formula rather than picked
  arbitrarily.

Not yet resolved: exact zone-sizing rule, how zones get laid out
geometrically across the farm (contiguous blocks seems the natural choice,
to keep in-zone travel low), and how zones get reconstructed each day given
hands aren't persistent.

### 5a. Zone-sizing formula (refined)

Two game mechanics make this concrete rather than a rough guess:

- **The farmer also respawns at the shed at the start of every day, not
  just hired hands.** So every unit, every day, starts back at the shed and
  must travel out to its zone fresh — this is a *daily recurring* cost per
  zone, not a one-time setup cost.
- **Inventory auto-drops into the shed for free at end of day, regardless
  of where the unit is standing.** So a zone's shed-cost is really a
  **one-way** trip (walking out, and picking up wheat/fertilizer at the
  start if the zone contains animals/fertilizable crops) — not a round
  trip, unless the zone runs out of carried supplies mid-day and needs a
  second restock.

This gives a per-zone daily cost:
```
zone_daily_cost = shed_to_zone_travel(distance)                [one-way, incurred fresh every day]
                 + sum(per_tile_task_cost(tile) for tile in zone)   [task-type dependent]
                 + intra_zone_travel(zone)                     [moving between tiles inside it]
                 + extra_shed_trips (if the zone runs out of carried supplies mid-day)

per_tile_task_cost ≈
  empty tile about to be planted:  ~1   (just the PLANT action, only on planting days)
  crop tile:                        ~1/day (water) + occasional harvest
  animal tile:                      ~3/day (feed + care + collect_fertilizer) + occasional harvest

Constraint: zone_daily_cost ≤ 24  (one unit's daily turn budget)
```

Since `shed_to_zone_travel` eats a fixed chunk of the 24-turn budget for
distant zones, less budget remains for tiles — matching the original
intuition: far zones should be smaller and/or lighter (crop-heavy), near
zones can afford more tiles or the costlier animal tiles. This is really
the same `sqrt(N × A)` idea from section 3, just applied **per zone**
instead of farm-wide — each zone's own local task density and shed-distance
determines its own affordable size, rather than one farm-wide average.

Reconstruction: since this only depends on data readable fresh from `obs`
each morning (tile contents, positions, distances), zone layout can be
(and probably should be) recomputed from scratch at the start of every day
— no persistence needed, consistent with hands not persisting either.

Still unresolved: the actual clustering/partition algorithm to turn "a pile
of tiles with costs and positions" into "a set of zones each fitting the
24-turn budget" (e.g. greedy nearest-neighbor growth from shed outward,
vs. a more formal bin-packing/clustering approach), and whether it's worth
trying to keep the same physical unit on roughly the same zone day-to-day
for continuity, or treat every day as a fully clean slate.

## 6. `active_area` definition (resolved direction, not yet implemented)

Two distinct fields, not one:
- **`total_unlocked_tiles`** — full land currently owned, regardless of
  whether work is happening there. Relevant to land-buying decisions.
- **`active_task_area`** — the tighter area actually relevant to the
  section 3 travel-time formula: tiles with a task pending today, plus
  tiles that will need a new plant/animal (i.e. empty tiles we intend to
  put to use), rather than blank tiles with no plan for them at all.

This keeps land-ownership strategy (how much to buy) cleanly separate from
the workload/hiring formula (how many units to service what's actually
being worked).

## 7. Hiring cost curve — headcount has a real ceiling, not just a workload floor

Section 3's hiring rule ("hire until `turns_available_per_day ≥
total_turns_needed`") is incomplete as written — it treats every unit's 24
turns as equally cheap to acquire, but hire cost is fibonacci and resets
daily (see reference doc section 5), so it isn't. The real question is a
cost-benefit one, not just a turns-supply one.

Cumulative daily cost to reach a given hand count (fibonacci: 1,1,2,3,5,8,
13,21,34,55,89,144,233,377,610,...), cost resets every day so this is a
**recurring daily cost**, not one-time:

| Hands hired | Cost of that hire | Cumulative cost that day |
|---|---|---|
| 5 | $5 | $12 |
| 8 | $21 | $54 |
| 10 | $55 | $143 |
| 12 | $144 | $376 |
| 13 | $233 | $609 |
| 14 | $377 | $986 |
| 15 | $610 | $1,596 |

Marginal cost roughly multiplies ~1.6x (fibonacci ratio) per additional
hand — this isn't a gentle ramp, it's a wall. Sustaining 15 hands for a
full 30-day game costs roughly $1,596/day × 30 ≈ $48,000 in hire fees
alone, which could consume most of a game's total profit.

**Two approaches worth testing, not yet decided between:**
- **"Correct" dynamic version:** keep hiring only while the next hand's
  marginal cost is less than that hand's expected marginal daily output
  (in $) — requires estimating $ value per unit of workload, harder to get
  right but properly accounts for cases where workload legitimately
  justifies expensive hands (e.g. very high-value tasks piled up).
  This means section 3's rule should really be reframed as a cost-benefit
  stopping condition, not just a turns-supply stopping condition.
- **Simple hard cap:** just refuse to hire past some fixed number (e.g.
  12-13, where the cost curve visibly steepens) regardless of workload.
  Easier to implement and reason about, but a blunt instrument — worth
  testing empirically whether a hard cap actually loses meaningful value
  vs. the dynamic version, or whether the cost curve makes going past ~13
  a bad idea in practice anyway (in which case the simple version is good
  enough).

Flagged as something to test empirically once an agent exists, not resolved
here.
