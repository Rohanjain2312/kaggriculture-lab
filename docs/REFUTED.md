# Refuted — settled questions, do not retry without new evidence

Every entry here was measured and lost. They are kept in full because the cost of
re-litigating a settled question is higher than the cost of the page: three of
these were re-proposed at least once before the numbers were written down.

Read this before adding to `IMPROVEMENT_BACKLOG.md`.

**The pattern to watch for.** Most entries failed the same way — a change looked
good on a metric that was not the objective:

* *Head-to-head flatters production cuts.* Making less crashes the shared market
  less, so a cut can win the mirror while being no better absolutely.
* *Gross sell totals flatter round-trippers.* `WHEAT` and `FERTILIZER` can be
  bought back, so counting sells alone invented a $148k gap that did not exist.
* *One seed set flatters luck.* `MIN_PLANT_SCORE` measured +$9,784 on seed 7 and
  +$1,732 across ten seed sets.

---

**Wheat rotation** (2026-08-06, was item #1, the top-ranked candidate). Refuted
twice over, and the evidence that motivated it was a measurement error of mine.

*The premise was wrong.* The "−$148,236 wheat gap" came from summing **gross SELL
orders**. `WHEAT` and `FERTILIZER` are the only items `BUY_PRODUCT` accepts, and
the archetype round-trips them — 743 wheat sold, 899 bought back in the same game.
Netted, **every agent in the batch is a net wheat buyer**, because wheat is animal
feed: us −130 to −209 units/game, the archetype −156. The real difference is
$2,491/game, not $14,824, and it is a *cost* line, not revenue.

*The mechanism was also wrong.* Our planner already prices wheat correctly, at the
drain-adjusted $37-55/unit — the same price we pay to buy feed, so the avoided-cost
argument is already inside the model. Wheat simply loses per unit of labour:

| crop (day 12, mid drain) | units | $/unit | score |
|---|---|---|---|
| MELON | 6 | 302 | **61.9** |
| STRAWBERRY | 4 | 288 | 28.4 |
| WHEAT | 4 | 45 | 14.2 |

*And forcing it loses money*, monotonically — measured vs `pass`, 6 seeds:

| forced wheat tiles | mean $ |
|---|---|
| **0 (planner's choice)** | **160,908** |
| 3 | 146,528 |
| 7 | 128,085 |
| 12 | 110,266 |

~$4,800 per forced tile. The archetype plants wheat because it has spare tiles and
labour left over from a smaller strawberry/melon allocation and a smaller herd —
not because wheat pays. **Copying an opponent's observable behaviour without its
constraints has now produced two refuted items** (this and "cut hands and land to
match their spend"). Their behaviour is evidence about *their* optimum, not ours.

Retry only if our tile or labour supply changes enough that melon and strawberry
stop absorbing it — i.e. downstream of #7, not before.


**Fractional livestock reserve, to unblock early planting** (2026-08-06, was item
#0b). The *diagnosis* was right and is worth keeping: a flat `LIVESTOCK_RESERVE`
of $900 against $250-330 of early cash does deadlock planting, and the fractional
form does remove it — day-0 plantings went 11 → 20 tiles and the days 1-8 hole
partly closed. **But removing the deadlock loses money**, at every setting tested:

| variant | mean $ vs `pass`, 6 seeds |
|---|---|
| v2-haul baseline | 153,500 |
| **fertilizer fix only (#0)** | **161,130** |
| reserve fix only, `RESERVE_SHARE=0.5` | 143,560 |
| both fixes | 152,296 |
| both, `RESERVE_SHARE=0.25` | 154,714 |
| both, planting allowance tightened to `spare // 3` | 108,309 |

**Why.** The cash reserve was accidentally masking a second problem. The planting
allowance is `spare // 2 - plants_alive`, i.e. it budgets 2 unit-actions per plant
per day — and on day 0 that permits 20 tiles against a real crew of 4-5 hands.
The cash gate meant this was never reached, so `ACTIONS_PER_UNIT = 12` and the
`// 2` were never tuned against a binding case. Unblock the cash and we plant more
than we can water: **peak weeds went 3 → 24**, and a plant lost to one missed
watering kills the tile permanently. The lost tiles cost more than the extra
plantings earn.

Tightening the allowance to `spare // 3` does not rescue it — it collapses
planting everywhere else in the game ($108,309). The two constants would have to
be re-derived together, and against the workload formula in item #7 rather than by
sweeping, since the right budget is *actions per plant per day*, which is a
measurable quantity and not a free parameter.

**Retry only** with item #7 (headcount from the workload formula) in hand, so the
crew is sized to the planting rather than the planting capped by a fixed guess.
The refuted experiment is `RESERVE_SHARE` + the per-tile reserve in
`build_plant_plan`; the working diagnosis is preserved in
`docs/brainstorms/EARLY_GAME_TEMPO.md`.

*Process note:* the head-to-head number for the combined change was **+$31,753**,
which reads as a large win. Absolute against `pass` it was **−$1,204**. Head-to-head
flattered it because over-planting also denies the opponent market share. This is
the second time that trap has caught a change here — always run the absolute test.


**Zone-based routing, and contiguous-block planting** (2026-08-06). Implemented
both and measured against `pass` over 4 seeds. Both are worse than what we have,
and travel gets *worse* the harder either is enforced:

| zone penalty | planting | mean $ | moves/useful |
|---|---|---|---|
| **0 (none)** | **nearest-to-shed** | **151,874** | **1.51** |
| 6 | nearest | 146,764 | 1.65 |
| 15 | nearest | 137,476 | 1.84 |
| 30 | nearest | 126,567 | 2.02 |
| 0 | 4 blocks | 136,242 | 1.70 |
| 0 | 8 blocks | 141,668 | 1.76 |
| 0 | 13 blocks | 144,487 | 1.72 |

Tested with wedge zones radiating from the shed, equal-cost split, units matched
to zones by proximity (matching by index instead cost $70k — worth knowing if
this is ever revisited), and critical/shed work exempt from the penalty.

**Why the theory did not apply.** The `sqrt(U·N·A)` penalty for a shared pool
assumes units pick tasks *without regard to distance*. Ours already assign by
`priority − MOVE_PENALTY × distance`, which is a distributed greedy
nearest-neighbour tour and already near-optimal for scattered tasks. And with 13
units over ~100 tiles a zone is ~7 tiles — finer than a unit's daily reach, since
a unit does ~20 actions and crosses the whole board in ~9 moves. Partitioning
below the scale a unit already covers only removes good local choices: with
7-tile zones, most genuinely-nearest jobs lie across a boundary.

The experimental agent is kept at `agents/exp_zones.py` — set `ZONE_PENALTY` /
`PLANT_BLOCK` to re-run. Would only become relevant on a much larger board or
with a far smaller crew.

**Cutting hands to 11 and land to 3 quadrants** (2026-08-05). Saved ~$12k/game in
spend and lost slightly more in revenue. Measured vs `pass`: 4 quadrants + 13
hands = $148,550; 3 + 11 = $141,461. Ladder opponents win on efficiency, not on
spending less.

**Wheat buy/sell round-trip** (2026-08-06). Ben does `SELL WHEAT n` +
`BUY_PRODUCT WHEAT n` in the same turn ~114 times a game. The environment quotes
buys at post-buy inventory precisely so this nets zero; measured **$346 across a
whole game**. Rounding noise from two rules oscillating, not an exploit.

**`MAX_HANDS` above 13** (2026-08-05). 15 and 17 collapse the farm — mean money
$48k and $12k respectively. The fib payroll bankrupts it. This settles the
"dynamic marginal-cost rule vs simple hard cap" question in the brainstorm's
section 7: **a hard cap around 13–14 is right**, because past it the marginal
hand cannot earn its cost under any workload we can generate. The dynamic rule is
still worth having *below* the cap, to avoid paying for hands before the work
exists — that is item 3/7, not a reason to lift the cap.

---

**`STAY_BONUS` — chaining more actions per stop** (2026-08-07). Diagnosed from
three independent measurements: we make 2,003 travel legs a game to the
archetype's 1,669 over the *same* working area (77 vs 75 tiles), chaining 1.34
useful actions per stop to their 1.65, with leg *length* matching (1.86 vs 1.79).
So we make more trips, not longer ones. A priority bonus for a job on the tile a
unit already occupies is monotonically worse, over 8 seed sets each:

| STAY_BONUS | 0 | 6 | 12 | 18 |
|---|---|---|---|---|
| mean $ | **164,093** | 162,113 | 158,812 | 156,704 |

Watering is time-critical — a missed water kills a tile permanently — so holding
a unit to finish low-priority work on its current tile is a bad trade however
cheap the movement saving looks. **Third travel mechanism to fail** (zone
partitioning, avoidable revisits, action chaining). The 1.10-vs-1.37 gap is real
and measured, but is more likely a symptom of doing different work than waste.

**Copying the archetype's build, as a whole package** (2026-08-07). Reconstructed
its exact script — hands per day, land days, 8 cows + 6 sheep, planting schedule
— verified byte-identical across three accounts, and ran it with our machinery
(`agents/archetype.py`). It earns **$132,770 against `pass` where ours earns
$161,673**, 18% worse, and we beat it 16-0. Their build is not their edge; their
execution is. This closes the loop on three earlier piecemeal refutations.

**Score-aware risk posture via the sell reserve** (2026-08-07, roadmap item 1).
Scoring is win/loss only, so the plan was: ahead late -> drop the sell reserve and
bank certain cash; behind -> raise it and hold for the town's drain. The opponent's
money is visible every turn.

Measured inert, twice. First as a +/-$15k band (mirror head-to-head 8-8, mean money
identical **to the dollar** -- a band only fires on a gap wide enough to have
already decided the game). Then rebuilt proportional and applied on every branch of
`sell_floor`, including the closing-days and shed-pressure paths that were
`return`ing early past it: still 9-9-2, 50%, means within $10.

**Why the lever is dead: the sell reserve is not what limits our selling.** The
ladder replays show **0 dropped market orders** and **0-4 units stranded at game
end** -- we already convert essentially all production to cash, so loosening the
reserve unlocks nothing and tightening it only defers.

The idea is not wrong, the lever is. A version that could work would estimate
standing from *board state* (their tiles and animals are visible, their shed is
not) from mid-season, and modulate **investment** rather than selling. That is a
real build with an uncertain payoff, and it is the only remaining form of this
item.

**The whole sell-timing family** (2026-08-07, roadmap items 2, 3 and part of 1/7).
Three separate ideas, one shared cause.

*Item 2 — sell just after the town's drain tick.* Refuted by arithmetic before
building. The drain schedule is genuinely fixed and predictable (shops every 4
steps, centre every 12, ×2 after day 10 and ×4 after day 20), but **one tick moves
a price by $0-1** while our own 15-unit sale moves it $0-4. The sawtooth amplitude
is noise against $250+ unit prices. The *cumulative* drain is the real prize
(~$129k of strawberry depth) and we already take it by selling late.

*Item 3 — sell ahead of the opponent's harvest.* Built and measured. The premise
checks out: their board is visible, non-ongoing crops carry `planted_day` and
mature on a fixed day, and selling 30 units before their dump rather than after is
worth ~$648 on strawberry, ~$490 on milk — plus their dump then lands in a market
we have already loaded, which counts twice on a relative score. The forecast fires
correctly (melon, milk and wheat floods detected). **It changes nothing:** 16-0
either way against the archetype (+$161, noise), and byte-identical money against
`v3-fert`.

**Why all of them fail — measure this before proposing another.** Instrumented
over a full game, of 939 item-turns holding stock:

| outcome | share |
|---|---|
| sold everything available | **89.4%** |
| reserve capped the quantity | 2.8% |
| reserve blocked the sale entirely | 7.9% |

**The reserve is not a binding constraint.** Any lever that works by moving the
sell floor has ~11% of turns to act on, and those are the low-price moments where
holding is already correct. This also covers item 7 (the final-day liquidation
race): we strand 0-4 units a game, so there is no race to lose.

What is *not* refuted by this: ideas that change **what we produce** or **what we
grow**, rather than when we sell it.

**Everything measured before 2026-08-07 was measured on a different game.**
`kaggle-environments` 1.32.6 changed the town: centre interval 12 -> 24, the
x1/x2/x4 day multiplier deleted entirely, shops drawn with replacement (capped at
8 instances, so `unlocked_shops` is a multiset and a product's only buyer may
never spawn), and the LOCKED guard moved so `PICKUP`/`DROP`/`PLACE` now work from
locked shed tiles.

Our drain model hardcoded the old numbers and never read the config, overvaluing
**MELON by 4.7x at day 0 and 8x at day 20** -- melon sits in no shop, so it took
both cuts at full force. Fixing it was worth +$2,917/game on its own.

**Conclusions in this file that rest on market depth should be treated as
provisional until re-measured.** The one already known to have flipped:
`MIN_PLANT_SCORE` was worth 1.3% on the old balance and **64%** on the new one,
with cliffs on both sides -- shallow markets punish marginal planting far harder.


---

## Skipping waters that produce nothing (2026-08-08)

**The measurement was right and the inference was wrong.** Worth keeping because
the measurement looked like the largest finding of the session.

Env source, confirmed at `_daily_refresh_plants` and the WATER branch of
`_apply_unit_action`:

* a plant weeds only at `consecutive_unwatered >= 2`, so **watering every other
  day keeps it alive** -- the daily water we do is half insurance we never need;
* **ongoing crops (strawberry, tomato) accrue yield at the nightly refresh
  whether or not they were watered.** `was_watered` gates nothing but the
  fertilizer double. Watering an unfertilised strawberry is free yield the env
  hands us anyway;
* non-ongoing crops gain a unit per water only inside
  `(max_yield_day + 1) // 2 <= age <= max_yield_day`.

Classifying every water in 10 of our replays against 4 elite ones:

| class | ours/game | elite/game |
|---|---|---|
| one-shot, outside window, already safe | 256.1 | 3.0 |
| ongoing, unfertilised, already safe | 253.3 | 5.0 |
| **produces nothing and prevents nothing** | **509.4 (52.8%)** | **8.0 (0.9%)** |

So 52.8% of our watering is genuinely dead work, against 0.9% for an elite agent.
Non-overlapping distributions.

**Removing it costs $6,200/game.** Gating the non-paying water to spare capacity
(`P_WATER_IDLE` below `P_PLANT`) measured 146,142 vs 152,349 for always-water,
over 8 paired seeds against `pass`; 45 and 58 landed in the same band (145,962 /
146,627), so it is the restriction itself that costs, not the threshold.

**Head-to-head agrees, over 80 games: 48% (38-42).** Worth stating because the
first read was the opposite. Over 24 games it measured 58%, which is the exact
signature this project has been burned by twice -- a production cut crashes the
shared market less and flatters the mirror. At 24 games that was p ~= 0.27, i.e.
nothing. Extending to 40 seeds collapsed it to 48%. **Both metrics now agree the
change is not an improvement.**

The diagnostic says why. Against the unchanged agent on one seed:

| | gated | always-water | delta |
|---|---|---|---|
| WATER | 681 | 946 | **-265** |
| moves (N/S/E/W) | 4,284 | 3,721 | **+563** |
| FERTILIZE | 119 | 157 | -38 |
| SELL:STRAWBERRY | 244 | 291 | -47 |

**Those waters are absorbing idle capacity at near-zero travel cost.** The crew's
next-best job is further away, so cutting 265 waters bought 563 moves. Labour was
never the binding constraint in the direction assumed.

Two follow-ons died with it:

* **more tiles for the freed crew** -- `PLANT_ACTIONS 2 -> 1` (the `spare // 2`
  planting gate) measured **-$13,495**. More plants overload the crew.
* **rank paying waters above idle ones** at equal volume -- `P_WATER_YIELD`
  70/74/80/86 gave 152,349 / 151,151 / 149,811 / 143,490. 70 (no split) is
  already optimal.

**The elite gap is a portfolio gap, not a discipline gap.** They water about as
often as we do (902 vs 965); they water *paying* tiles because they have more of
them (345 in-window one-shot waters against our 176). Copy the crop mix, not the
watering rule.

**Corollary: "the crew is exactly saturated" (waters/plant/day ~= 1.00-1.08) was
never evidence of saturation** -- the dead waters were padding that ratio. Any
hiring or planting change refuted on that premise is unproven, not settled.

---

## Growing tomato and carrot to serve "unserved" demand (2026-08-08)

**Zero of 72 elite player-seasons ever sold TOMATO, EGG or CARROT.** That looked
like ~$50k/game of town demand nobody was competing for, in games decided by
~$1,629. It is unserved because it is not worth serving.

Instrumenting the marginal score of every crop at every planting decision over 4
seeds — `score = (revenue - seed) / (1 + OCCUPANCY_COST * occupancy + harvests)`,
i.e. dollars per unit-action:

| crop | days offered | days over `MIN_PLANT_SCORE` | best score | units | occ | harv | seed |
|---|---|---|---|---|---|---|---|
| MELON | 7 | 7 | **56** | 6 | 13 | 1 | 80 |
| STRAWBERRY | 7 | 6 | **26** | 4 | 17 | 2 | 100 |
| WHEAT | 15 | 7 | 18 | 4 | 5 | 1 | 10 |
| CARROT | 15 | **0** | 11 | 3 | 4 | 1 | 20 |
| TOMATO | 9 | **0** | 11 | 4 | 12 | 2 | 50 |

Carrot and tomato never clear the bar on any day of any seed — not a near miss.
At ~$11 per action against melon's $56, they are 5x worse use of the same labour,
which tracks the market depth: carrot ~$18k and tomato ~$27k against strawberry
~$129k, milk ~$99k, wool ~$81k.

The denominator was the suspect: `2 * occupancy` charges a water every day, and
the env only weeds after two dry days, so it over-penalises long-occupancy crops.
Parametrised as `OCCUPANCY_COST` and swept jointly with `MIN_PLANT_SCORE`
(they are coupled — the threshold was tuned against the old denominator), 8
paired seeds vs `pass`:

| | MIN=8 | MIN=16 | MIN=24 |
|---|---|---|---|
| **OCCUPANCY_COST=0.5** | 117,056 | 117,056 | 116,965 |
| **OCCUPANCY_COST=1** | 116,029 | 116,046 | 144,089 |
| **OCCUPANCY_COST=2** | 87,018 | **152,349** | 126,853 |

The shipped setting wins by $8,260 over the next best, and **every variant that
admits carrot or tomato is $25k-$36k worse** — they displace melon and
strawberry on the same tiles. At `OCCUPANCY_COST=0.5` the two thresholds give
identical results, because scores inflate until nothing is filtered at all.

**So the "action cost" denominator is not literally an action count** — it also
carries tile opportunity cost, and 2 is the measured optimum for the pair.

Conditioning production on the shop draw — the other half of this item, from
elite wool swinging 5.4x on an identical herd with 90 units dumped at $1 when
YARN_STORE never spawned — **is already implemented and verified live**, for
crops (`build_plant_plan`) and animals (`pick_animal`), both via
`future_drain(product, day, shops, cfg)`. WOOL drain, by draw:

| day | no YARN_STORE | 1x | 2x |
|---|---|---|---|
| 0 | 152 | 480 | 840 |
| 20 | 92 | 198 | 318 |

That elite blind spot is one we do not have.

---

## Transplanting the elite build: strawberry runway, then wheat runway (2026-08-08)

Both built, both fired correctly, both lost. Recording the mechanism because the
*diagnosis* was sound each time and the transplant still failed.

**The observation.** Over 30 version-matched (1.32.6) elite player-seasons against
4 of ours: they hold 60 standing plants on **78** owned tiles to our 40 on **88**,
with 3-6 empty against our 20-40. Same plantings (162 vs 162), same productive
actions (2,678 vs 2,702). The difference is entirely strawberry -- 42.1 plantings
from day 6.8 against our 24.5 from day 11.0, and 679 strawberry tile-days to our
393.

**Strawberry runway** (top standing strawberry up to N tiles from day 6, outside
the marginal scorer and the burn-based cash floor). It worked mechanically --
first strawberry day 11 -> 9, plantings 40 -> 46 -- and lost money:

| `STRAW_RUNWAY_TILES` | 0 | 12 | 24 | 36 |
|---|---|---|---|---|
| mean $ vs `pass` | **152,349** | 151,338 | 145,134 | 145,466 |

**Then the real early-game cause, correctly identified.** Elite hold 6-8 standing
wheat tiles continuously through day 11; we run **zero from day 3 to day 9**.
Wheat matures in 2-4 days, so it is the only early cash engine: theirs funds land
on day 7 and the strawberry mass-planting on days 7-8 (1.4 -> 6.6 -> 18.9 tiles),
while we sit flat near $300 for six days until melon lands on day 10. Our scorer
cannot see it -- early wheat scores 13-15 against `MIN_PLANT_SCORE = 16`, so it
is never planted before day 19, and what wheat is worth early is *liquidity*,
which no term in the score represents.

That diagnosis is correct and the fix still fails, harder than the first:

| `WHEAT_RUNWAY_TILES` | 0 | 4 | 8 | 12 |
|---|---|---|---|---|
| mean $ vs `pass` | **152,349** | 133,205 | 115,119 | 132,452 |

**This was already settled.** The wheat rotation was refuted on 2026-08-06 and is
named in CLAUDE.md's operating rules; it was re-litigated here because the
early-game *timing* evidence looked new. It is the same question. Before building
against an elite-vs-us difference, grep REFUTED.md for the crop first.

**The pattern across six transplants.** Watering discipline, tomato/carrot,
shop-draw conditioning, land level, strawberry timing, wheat rotation -- every
one located a real difference and every one lost when transplanted. Consistent
explanation: our binding constraint is **execution**, not build. Elite spend 1.14
moves per productive action against our 1.36, so they can service 60 standing
plants where the same work only carries us to 40. Their build is downstream of an
efficiency we do not have, which is why forcing the build without the efficiency
makes us worse -- the same reason `PLANT_ACTIONS = 1` cost $13,495.

**So stop transplanting builds.** The open question is movement per productive
action. Note routing has already been attacked three times (zones, revisits,
chaining) and lost, so this needs a different angle, not a fourth pass.

---

## Correctness audit, 2026-08-10: two real defects, neither worth fixing

Run after the ladder showed the **config fix was the only change that ever moved
our rating** (+14 to +26 points, vs the contention pivot's +0.3). The hypothesis
was that another mispricing was hiding. Two were found. Both are real. Fixing
either loses money.

**Tooling: `verify_env.py`.** 2,014 assertions that every constant `main.py`
mirrors from the environment still matches the installed copy -- crop and animal
tables, shop contents, market params, land prices, the shop-instance cap, and
`market_price` itself sampled over ~2,100 inventory points per item. All pass on
1.32.6. **Run it after every `kaggle-environments` upgrade and before shipping**;
it exists so the melon-class bug is caught by running something, not by noticing.

**Defect 1 -- ongoing-crop yield is under-counted by 85%.** `pipeline_units` had
a ternary with two identical branches, and `crop_projection` counts one unit per
tick. A fertilised tick pays **2**, not 1 (env `_daily_refresh_plants`). Measured
on a real game: strawberry returns **7.40 net units sold per tile planted**
against the 4 the model assumes; melon, non-ongoing, measures **6.00 against 6**.
Strawberry is 36.8% of our revenue.

Corrected (`ONGOING_YIELD_MULT`), swept jointly with `DRAIN_SHARE` because the
two are the supply and demand halves of the same projection:

| | DRAIN_SHARE=0.5 | 0.75 | 1.0 |
|---|---|---|---|
| **MULT=1.0** (wrong, shipped) | **152,349** | 147,376 | 149,491 |
| **MULT=1.85** (correct) | 136,445 | 133,830 | 112,553 |

The truth is **$15,904 worse**, and worse at every demand setting. The mechanism:
a higher committed-supply count puts marginal strawberry further up its own glut
curve, so it scores lower and we plant less of it -- away from our best crop and
away from the elite cohort's 42 tiles. **The under-count is load-bearing bias
toward strawberry.**

**Defect 2 -- end-of-day shed overflow destroys produce.** `_drop_inventories_to_shed`
discards anything that will not fit. Measured over 8 seeds: **2.8 units and ~$512
per game**, 5 day-ends across 8 games. Real, but a sixth of the $3,000 noise
floor, so no fix to it can be measured. Recorded, not fixed.

**The structural lesson, now three-for-three.** Watering discipline, the
occupancy-cost denominator, and now the yield multiplier: each was factually
wrong, each was fixed correctly, each lost money. **This agent is a jointly
calibrated heuristic -- its individual terms are not independently meaningful,
because every one was tuned against the others' errors.** Correcting a term in
isolation breaks the calibration that made the whole work. Any future correctness
fix must be swept together with the terms it interacts with, and judged on
measurement, not on being right.

## The "planting schedule bug" is not a bug (2026-08-14)

`docs/analysis/top10_headtohead_2026-08-14.md` reported two defects in the
planting curve and ranked fixing them as the highest-confidence item in the
backlog. **Both were measured and both hypotheses lost.** The curve is a tightly
tuned local optimum, not a defect.

The observations themselves were real and reproduce: days 1-9 pinned at exactly
10 plants, and day 10 dropping to 0 plants / 0 watered in 4 of 6 seeds, against
the rank-1 ladder agent's 19-35 tiles over the same window.

**What the instrumented trace actually showed** (seed 7, `WHY_FILE` logging of
every crop's cash check and score inside `build_plant_plan`) — two *different*
causes, neither the one assumed:

* **Days 1-9:** `WHEAT` is the only crop `crop_projection` returns units for, and
  it scores **13.2-14.8 against `MIN_PLANT_SCORE = 16`**. The board is flat
  because the gate is correctly refusing a low-value crop, not because of cash.
* **Day 10:** `MELON` scores **46.9**, far above the gate, and is refused purely
  on cash — $587 against a floor of $1,678 ($250 hard floor + $900 livestock
  reserve + $528 payroll runway).

### Refutation 1 — exempting fast-payback crops from the livestock reserve

`FAST_CASH_DAYS`: waive `LIVESTOCK_RESERVE` for a crop whose seed returns before
the herd purchase it protects. **Zero effect** — identical to the dollar at
thresholds 0, 3, 4 and 6 ($92,511 mean), because `days_to_cash` returns
`max_yield_day` (WHEAT 4, CARROT 3), and the crops it would have unblocked are
rejected by the score gate anyway. At 10 (which also exempts strawberry) it
collapsed to 6.2% / $57,045.

### Refutation 2 — suspending the reserves below a working-tile minimum

`MIN_WORKING_TILES`: apply only the hard `CASH_FLOOR` until the farm has a
minimum number of tiles working, on the reasoning that a runway protecting a crew
with nothing to water inverts its own purpose.

| `MIN_WORKING_TILES` | win% vs ref | mean $ | worst $ |
|---|---|---|---|
| 0 (control) | 100.0% | **92,511** | 75,394 |
| 12 | 0.0% | 61,334 | 37,067 |
| 24 | 0.0% | 70,108 | 53,079 |
| 36 | 93.8% | 85,353 | 52,760 |

Against the guard that matters: **$95,880 vs `pass`, against main.py's $152,349
— a $56,469/game loss.** `bench.py --trace` gives the mechanism: `max_weeds=12`
and **3 animal deaths**. Planting early with no cash means no hires, which means
plants unwatered and livestock unfed. This is the same failure recorded when the
reserve was removed outright (peak weeds 3 → 24); the reserve is load-bearing.

### Refutation 3 — lowering the gate to admit the early wheat engine

The rank-1 agent runs wheat for early cash flow. Ours scores 13-15 against a gate
of 16, so admitting it looked like the missing engine. Monotonically worse:

| `MIN_PLANT_SCORE` | 10 | 12 | 14 | **16** | 18 |
|---|---|---|---|---|---|
| mean $ | 75,888 | 77,751 | 86,595 | **92,511** | 89,560 |

`RUNWAY_DAYS` was swept in the same pass and is also already at its peak
(2→84,975, 5→87,682, **6→92,511**, 8→83,191).

### What this means — the constants are jointly tuned, in the wrong basin

`MIN_PLANT_SCORE`, `RUNWAY_DAYS` and `LIVESTOCK_RESERVE` are each at a local
optimum and **every single-parameter move in every direction loses money**. They
are jointly tuned around a melon/strawberry economy. The rank-1 agent runs a
different economy (wheat cash engine, herd complete by day 11, carrot, low
melon), and no single threshold move crosses between the two basins — which is
consistent with every tuning change we have shipped being worth ~0 on the ladder.

**The lever is valuation, not thresholds.** The PR #1399 curve fix changes what
crops are *worth* rather than where a cutoff sits, which is why it moves the mix
(0 tomato tiles → up to 14) when no threshold sweep does.

### Methodology defect found in the process

**`agents/sweep_ref.py` is stale — it is `v3-fert`, two versions behind `main.py`
(`v5-pivot`).** `CLAUDE.md` requires re-copying it after accepting a change and
that was missed for two versions. Consequence: win% saturates at 100% for nearly
every variant, so every sweep above was decided on mean money alone. The variant
*rankings* remain valid — all faced the same reference — but win% carried no
information. Re-copy before the next sweep, and treat win% in any sweep recorded
before 2026-08-14 as uninformative.

## UNREFUTED: the sell-timing family's load-bearing number was wrong (2026-08-15)

The entries above kill roadmap items 1, 2, 3 and 7 with one shared cause:

> **The reserve is not a binding constraint.** Instrumented over a full game, of
> 939 item-turns holding stock: sold everything **89.4%**, reserve capped 2.8%,
> reserve blocked 7.9%. Any lever that works by moving the sell floor has ~11% of
> turns to act on.

**That number was measured in an empty market.** Re-measured 2026-08-15 on
1.32.6, 3 seeds per opponent, instrumenting the same decision in `plan_sales`:

| opponent | sold everything | capped | **blocked** | item-turns |
|---|---|---|---|---|
| `pass` | 82.2% | 3.3% | 14.5% | 518 |
| `sweep_ref` (mirror) | 30.0% | 5.4% | **64.7%** | 1,529 |
| `panel_ueddy` | 28.1% | 5.8% | **66.2%** | 1,522 |
| `panel_rival` (rank 1) | 31.4% | 6.6% | **62.0%** | 1,469 |

Against `pass` the old figure roughly reproduces (82.2% vs 89.4%). **Against any
real opponent it inverts: the reserve binds on 68-72% of item-turns.**

The mechanism is not subtle in hindsight. A second agent selling into the same
market holds prices below our reserve, so our floor refuses far more often. An
empty market has no such pressure. The original conclusion generalised from a
one-player game to a two-player one — the same class of error as measuring win
rate against `pass` and the "$148k wheat gap".

**What this does and does not establish.** It voids the *stated reason* items 1,
2, 3 and 7 were closed. It does **not** show any of them works — item 3 was also
measured directly (16-0 either way, byte-identical money vs `v3-fert`), though
that too was on the pre-1.32.6 balance against an archetype we no longer face.

Live again, and now with a large surface to act on — we decline to sell on ~2/3
of item-turns, so anything conditioning *that* decision has real room:

* **Score-aware posture** (item 1). Its surviving form was "modulate investment,
  not selling", because selling was thought saturated. It is not. Ahead late →
  liquidate into the win; behind late → hold for the spike.
* **Denial timing** (items 3 and 8). Selling ahead of their forecastable dump
  changes behaviour now, where before it changed nothing.

The building blocks already exist and are half-used: `rival_pipeline()`
(`main.py:467`) already computes their standing production from their visible
board, and `obs["farms"]` carries their money every turn. v5-pivot feeds the
pipeline into *price discounting* only, and **nothing anywhere conditions on
whether we are ahead or behind.**

**Do not re-close the sell-timing family by citing the 89.4% figure.**

## SELL_ANCHOR — the diagnosis was right, the fix is worth nothing (2026-08-15)

**Diagnosis (stands, independently verified).** `sell_floor` returns
`max(0.97 x price_now, SELL_ANCHOR x slack x base)`. Instrumented over days
10-17 vs `panel_rival`: **100% of blocked item-turns are stopped by the absolute
`0.75 x base` anchor, 0% by the price-relative term.** Confirmed constructively —
relaxing the relative term (0.90 -> 0.86) left mid-game blocking at 84.7% against
a control's 84.0%, i.e. unchanged. The reserve blocks 45.6% / **84.0%** / 64.0% /
22.5% of item-turns across days 0-9 / 10-17 / 18-21 / 22-29.

**The fix does not convert into wins.** `SELL_ANCHOR = 0.60`:

| evidence | result |
|---|---|
| sweep vs `panel_rival`, n=20 | 95.0%, best of 5 values |
| full panel, 12 seeds (n=120) | 92.5% vs control 90.8% — **+2 games** |
| **full panel, 25 DISJOINT seeds (n=250)** | **95.6% vs control 96.0% — −1 game** |
| money vs `pass` | $138,735 vs $138,811 — flat |

The replication used **disjoint seeds (seed0=100) rather than an extension of the
original set**, deliberately: extending would have inherited whatever seed luck
produced the +2 and reported it again as a weak positive. On seeds it had never
seen, the effect is zero.

Note how large the seed effect is — the same control agent reads 90.8% on one
25-seed set and 96.0% on another. **Any panel result below ~5 percentage points
on a single seed set is noise.** Two of today's candidate results were inside
that band.

**What this does not refute:** that conversion timing matters. Elite analysis
(n=79) shows first-to-market going to the winner 60% of the time (p=0.035), and
holding at 90% even when the winner's build is *not* ahead. Selling the same
goods slightly cheaper is only one way to arrive earlier, and it is now measured
flat. Levers that change *when produce exists* — harvest timing, haul cadence —
are untested and are a different mechanism.

## Day-10 tempo: "plant what we can afford" (2026-08-15)

**The observation is real and stands.** Over 45 of our own 1.32.7 ladder games,
opponents hold LESS cash than us on days 0-8 (median $85-450 vs our $251-448) and
still add ~2 plants a day, reaching **30 plants by day 10 against our 3**. They
buy animals later (day 7+) out of crop returns; we buy by day 4 and then sit on
$250 we cannot convert.

Correct root cause, from an instrumented per-crop trace (seed 7): days 1-10
MELON scores **46-47 against a gate of 16** and is refused purely on **cash** --
floor $1,678 vs $255-448 held. It is not the score gate. *(An earlier claim in
this session that the gate was refusing wheat was wrong -- an artifact of `awk`
collapsing the trace to one line per day.)*

**The fix was built and it fails on both counts.** `FILL_WHEN_BLOCKED`: when every
crop clearing `MIN_PLANT_SCORE` is unaffordable, plant the best affordable crop
instead of nothing, on the reasoning that no better tile is being displaced.

| | control | FILL_WHEN_BLOCKED |
|---|---|---|
| plants, days 1-9 | 10 10 10 10 10 10 10 10 10 | **11 8 8 8 8 8 8 8 9** |
| panel (7 opponents, 12 seeds) | **159/168 (94.6%)** | 151/168 (89.9%) |
| **money vs `pass`** | **$148,140** | **$79,454** |

**It does not even raise the plant count** -- it *lowers* it, 10 -> 8. A cheap
crop planted early occupies the tile through the window when melon becomes
affordable, so the board ends up holding less value, and the vs-`pass` guard
collapses by **$68,686/game**. Rejected on the guard alone.

**What remains open:** the opponents' actual mechanism is *sequencing* -- animals
later, cheap plantings continuously -- not "fill empty tiles with whatever is
affordable". Deferring the early herd to fund continuous planting is untested and
is a different change from this one.

## Day-10 tempo, attempt 2: deferring the herd (2026-08-16)

Opponents buy animals from day 7+ and fund continuous planting from crop returns;
we buy by day 4 and go broke. Hypothesis: defer the herd (and lift the livestock
reserve with it, since holding $900 for animals we are not allowed to buy is what
starves planting) so early cash goes into tiles instead.

`HERD_START_DAY` vs `agents/panel_rival.py` on 1.32.7, 20 games per value:

| value | win% | mean $ | worst $ |
|---|---|---|---|
| **0 (current)** | **100.0%** | **78,375** | **50,479** |
| 3 | 75.0% | 75,362 | 37,855 |
| 5 | 75.0% | 76,493 | 34,982 |
| 7 | 75.0% | 76,493 | 34,982 |

**-25 percentage points, lower mean, and a floor $15k worse.** Days 5 and 7 give
identical figures because we finish the early herd by day 4 either way, so both
block the same purchases.

Mechanism: animals are the best return per action in the game -- a $400 cow
yields ~36 milk over a season -- so delaying them forfeits compounding that crop
tiles do not replace. **The opponents' late herd is a consequence of their build,
not a cause of their strength.** That is the third time
`CLAUDE.md`'s rule has bitten: *an opponent's behaviour is evidence about their
optimum, not ours.*

### The day-10 tempo gap now has two refuted fixes

The observation is not in doubt -- 30 plants to our 3 at day 10, from 45 real
ladder games, with opponents holding *less* cash than us throughout. What has
failed is every attempt to close it:

1. `FILL_WHEN_BLOCKED` (plant the best affordable crop rather than nothing):
   **-$68,686/game vs `pass`**, and it lowered the plant count 10 -> 8.
2. `HERD_START_DAY` (defer the herd to free early cash): **-25pp win rate.**

Both assumed the gap is a *resource allocation* problem. Two independent
refutations suggest it is not -- the difference is more likely in how efficiently
they convert the same resources (they reach 30 tiles while poorer), which points
at execution, not at what we spend money on. Do not attempt a third variation on
"spend the early cash differently" without new evidence.

## Wool allocation: more sheep earns more and wins less (2026-08-16)

Ladder analysis over 45 of our 1.32.7 games: we field **3 sheep to our opponents'
6** (exact board state; `wool_net` 66 vs 144), substituting geese. Estimated at
~5 loss-flips. Tested as `SHEEP_BIAS`, a multiplier on SHEEP's marginal score in
`pick_animal`.

Sweep vs `agents/panel_rival.py` was **uninformative**: control sits at 100%
there, so the comparison could only detect regressions. Re-run on the full
7-opponent panel, 16 matched seeds:

| opponent | control | SHEEP_BIAS=1.2 |
|---|---|---|
| kostiantyn | 94% | **100%** |
| mohamed | 100% | 94% |
| **raiden_b** | 78% | **53%** |
| researchstudio | 100% | 100% |
| rival | 100% | 91% |
| thunder | 97% | **100%** |
| **ueddy** | 94% | **75%** |
| **total** | **212/224 (94.6%)** | **196/224 (87.5%)** |
| mean money | $82,637 | **$87,172 (+$4,535)** |
| vs `pass` | $146,645 | $146,793 |

**Money rose $4,535/game against every single opponent while win rate fell 7.1
points -- 16 games.** Optimising money ships this change; the objective rejects
it. It collapses precisely in our two weakest matchups (`raiden_b` 78 -> 53,
`ueddy` 94 -> 75) while padding games already won.

Mechanism: WOOL has the harshest glut curve in the game (`above_target 3.20`,
shape `sq`). More sheep pushes more wool into a market that punishes oversupply
quadratically, so the extra output banks well in comfortable games and crashes
the close ones.

**This is the cleanest demonstration in this file of why absolute money is a
guard and not the decision metric** -- the two moved in opposite directions, hard,
on the same 224 games.

**And it is the fourth time today that copying an opponent's observable choice
has failed:** their 6 sheep is right for *their* build. `CLAUDE.md`: an
opponent's behaviour is evidence about their optimum, not ours.

## Harvest-date price decay, and the exhaustion of the panel (2026-08-17)

**The mispricing is real and stands.** `build_plant_plan` prices every crop off
the curve as it stands TODAY, but crops reach the market days later. Measured
over 45 of our 1.32.7 ladder games -- realised sale price against the median
price during the day 8-15 planting window:

| crop | days to harvest | price at planting | realised | ratio |
|---|---|---|---|---|
| MELON | 12 | 184 | 146 | **0.79** |
| STRAWBERRY | 10 | 188 | 173 | 0.92 |
| WHEAT | 4 | 40 | 53 | **1.35** |
| CARROT | 3 | 44 | 62 | **1.42** |

Perfectly ordered by duration. Long crops realise *below* the price the planner
used; short crops realise *above* it -- a ~70% relative mispricing between melon
and wheat that is systematic across every game.

**The blunt fix is neutral.** `HARVEST_DECAY`, a per-day discount on marginal
value:

| | seeds 600-619 | seeds 800-819 | pooled |
|---|---|---|---|
| control | 263/280 | 278/280 | **541/560** |
| 0.02 | 267/280 | 275/280 | **542/560** |

**+1 game in 560.** Larger values collapse -- 0.05 -> 58%, 0.10 -> 29% -- because
discounted scores fall under `MIN_PLANT_SCORE` and planting shuts down. The lever
is entangled with the gate.

Why the fix does not capture the finding: a uniform per-day discount penalises
long crops but does not *reward* short ones, and wheat/carrot appreciate 35-42%.
The correct form prices each crop against the curve projected to **its own
harvest day**. Untested.

### The panel is exhausted as an instrument

Control read **278/280 (99.3%)** on seeds 800-819. Across today's runs it has
read 90.8%, 93.9%, 94.6%, 95.4% and 99.3% depending only on the seed set. Two
consequences:

1. **There is almost no headroom left.** A change that genuinely improves us has
   nowhere to show it, so every recent candidate reads as a wash.
2. **Seed variance (~8pp) dwarfs any real effect (~1pp).** Anything under ~5pp on
   one seed set is noise, and today three separate candidates flipped sign
   between disjoint seed sets: `SELL_ANCHOR` (+2/120 then -1/250), `v7-fert`
   (-3/224 then +4/280), `HARVEST_DECAY` (+4/280 then -3/280).

**Meanwhile our real ladder win rate is 45.8%.** The panel says 99%, the ladder
says 46%. The panel agents run a competitor's *build* on OUR machinery, so they
inherit our execution -- and the ladder analysis showed mid-field and elite
opponents are identical on build and differ only in conversion efficiency, which
is exactly what reconstruction cannot copy.

**Do not tune against the panel any further.** It cannot distinguish a 1-point
change, and the gap that matters is not in the build it reproduces. The next
useful measurement is on the ladder itself, or against an opponent model built
from execution rather than build parameters.

## Trying to fix the panel: two defects, one of them structural (2026-08-17)

The panel had stopped resolving anything (control 278/280 on one seed set). Two
causes found; one is fixable and one is not.

**Defect 1 -- the scripted plan was re-clamped by OUR labour model.** `panel.py`
capped the scripted planting at `n_tiles` (our `allowance = spare//2 -
plants_alive`) and only ran it `if allowance > 0`. So a panel agent copying a
56-tile opponent was throttled to our ~40-tile ceiling: it inherited the exact
weakness it exists to measure. Unclamped, and the call site no longer gated.

Effect was small: `panel_rival` peak 40 -> 43, `panel_ueddy` 31 -> 34, against the
**56-59** real opponents reach. And **weeds appeared** (21 and 9, from 0) -- the
extra tiles die, because our watering machinery cannot sustain them.

**Defect 2 -- the reconstruction sees about half the planting.** `plantings_by_day`
infers plantings from day-over-day *increases* in the crop census, which cannot
see a tile harvested and resown. Elite players churn heavily. Over 80 elite
seasons:

| | |
|---|---|
| actual `PLANT` actions (exact) | **187** |
| what census-diff reconstructs | **99** |
| share of their planting the panel replays | **52.9%** |

Fixable in principle -- `unit_ops` carries exact `PLANT:<crop>` counts -- but see
below for why it would not help much.

### The structural ceiling: a panel agent cannot be stronger than our machinery

Panel agents are a competitor's *build* running on **our** routing, watering,
selling and fertilizer code. Our per-plant labour cost is 1.87 actions/plant-day
against the elite's 1.34. So when the script asks for 56 tiles, our machinery
waters 43 of them and weeds the rest.

**You cannot construct an opponent stronger than yourself out of your own
execution.** Feeding the script more plantings (defect 2) would produce more
weeds, not a harder opponent. The ladder analysis already showed mid-field and
elite opponents are identical on *build* and differ only in *conversion
efficiency* -- precisely the part reconstruction cannot copy.

That is why the panel reads 99% while our real ladder win rate is **45.8%**.

**Operating conclusion.** Treat the panel as a **guard** ("did I break it?"),
never as a decision metric -- the same status absolute-money-vs-`pass` already
has. It can still detect a regression, which is worth keeping. It cannot confirm
an improvement, and three candidates today flipped sign across disjoint seed sets
while it insisted they were within a point of each other.

**A real improvement now has to be confirmed on the ladder.** That is 5
submissions a day against a local harness that runs hundreds of games in minutes,
which inverts the usual cadence: local runs become a filter for *breakage*, and
the ladder becomes the only place a win is demonstrated.

---

## 2026-08-17 — the replacement instrument, and two hypotheses it killed

`tools/ladder.py`. `ListEpisodes` returns each agent's `reward`, and reward *is*
final money — verified exactly on **210/210** player-seasons against the digests.
So the full win/loss *and margin* record costs one API call per submission and no
replay downloads. This measures the scoring metric directly; the panel never did.

### What it says

| submission | games | record | win% | our $ | opp $ |
|---|---|---|---|---|---|
| v5-pivot | 182 | 83-99 | 45.6% | 81,041 | 81,881 |
| v6-curve | 59 | 26-33 | 44.1% | 77,283 | 78,860 |
| v6-curve-r2 | 40 | 20-20 | 50.0% | 84,903 | 81,737 |
| **v7-fert** | 27 | 15-12 | **55.6%** | 83,003 | 76,725 |
| pooled | 308 | 144-164 | 46.8% | 80,995 | 80,831 |

Pooled, we are at **dead parity on money** ($81.0k vs $80.8k) with a **symmetric**
margin distribution (median loss $14,542, median win $14,685). We are not losing
narrowly and we are not being out-earned; we are a coin flip with a wide spread.

The band table is the roadmap, because it converts dollars into the metric that
scores: a change worth a **$7k swing** is worth **+16 points of win rate**
(46.8% -> 62.7%). Only 9 of 164 losses are inside $1k, so shaving pennies off
close games has almost no ceiling — the mass sits at $3k-$15k.

### Killed: the seat effect

Seat 0 read 38.1% against seat 1's 54.1% over one 182-game submission — a
16-point gap. It **reversed sign** on the next submission (48.4% vs 42.9%),
pooled to p = 0.07, and the environment builds both farms from the same call
(`farms = [_new_farm(...) for _ in range(num_agents)]`). Noise. Seat order *is*
asymmetric for same-turn market fills (actions resolve `for i, s in
enumerate(state)`), but that asymmetry does not reach the scoreboard.

### Killed: stranded end-of-season inventory

The digests show us carrying 44 units on day 29 against opponents' 26, which
looked like produce we never sold. It is not: `digest.py` snapshots at
`SNAPSHOT_HOUR = 12`, so that is **midday in-flight stock**, not what is left at
the end. Measured on exact final-step board state over 5 local games:
**0 units and $0 stranded, on both sides.** `endgame_dropoff` does its job.

### Flagged, not acted on: the $3k-$7k band

Outside one band we are 134W-134L — exactly even. Inside $3k-$7k we are
**13W-30L** (raw p = 0.0095), same sign on all four submissions. But those
submissions share most of their code, so they are not independent tests; neither
half is significant alone (p = 0.06 and p = 0.07), and correcting for the six
bands tested puts the pooled result at p ~ 0.06. A genuine "we lose exactly $Xk"
mechanism should also shift the neighbouring bands, and they are flat.
**Suggestive, not established.** Re-test it as v7-fert's sample grows.
