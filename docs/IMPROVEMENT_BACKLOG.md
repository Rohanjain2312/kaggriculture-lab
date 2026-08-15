# Improvement backlog

Candidate changes to the agent, with the evidence behind each and how to test it.
Add to this as ideas come up; move items to **Rejected** with the numbers when a
test refutes them, so a settled question never gets re-litigated.

**Status:** `idea` → `validated locally` → `shipped` → `confirmed on ladder`

## 0. ~~Planting schedule is broken~~ — **REFUTED 2026-08-14, same day it was filed**

Filed as the highest-confidence item here, then measured. **All three fixes lost,
two of them badly.** Numbers and the instrumented trace are in `docs/REFUTED.md`
→ "The planting schedule bug is not a bug".

Short version: the flat at 10 tiles is `MIN_PLANT_SCORE` correctly refusing wheat
at 13-15 against a gate of 16 — not the cash floor, as guessed above. The day-10
hole *is* the cash floor, refusing a melon that scores 46.9; relaxing that floor
costs **$56,469/game vs `pass`**, with 12 weeds and 3 animal deaths.
`MIN_PLANT_SCORE`, `RUNWAY_DAYS` and `LIVESTOCK_RESERVE` are each already at a
local optimum and every single-parameter move in every direction loses money.

**Also wrong above:** "this refutes labour is the binding constraint". The
tiles-per-hand gap is real (3.3 to the leader's 7.6) but it does not follow that
relaxing the gate helps — it was measured and it does not.

**Kept as a live observation, not a fix:** peak crop area 43.5 tiles to the
leader's 61. The gap is real; it is not reachable by moving a threshold, because
the constants are jointly tuned around a melon/strawberry economy and the leader
runs a different one. Evidence *for* the valuation work below — the #1399 curve
fix moves the crop mix (0 → 14 tomato tiles) where no threshold sweep does.

**Do not re-propose a threshold sweep on these three constants without new
evidence.**

## 0. Version-adaptive market curve for PR #1399 — **`validated locally` 2026-08-14, in `main.py`**

**Implemented and measured.** `main.py` now carries both curve sets and picks per
turn from the board. Numbers below are all measured in this repo, independently
of the analysis that proposed the change.

| check | result |
|---|---|
| our old-curve model vs installed 1.32.6 env | **0 mismatches** across all 9 products × every inventory level |
| detection on a 1.32.6 board | picks OLD (correct) |
| CARROT separates the two tables | **1,482 / 1,499** deficit levels (98.9%) |
| **behaviour on today's env** | **$152,349 vs `pass` — identical to the dollar** to the pre-change agent; also identical vs `starter` and `baseline_v0` |
| post-#1399, paired 12 seeds × 2 seats | **70.8% (17W-7L)**, $86,392 vs $82,889 |
| post-#1399, pinned PIZZA_SHOP ×3 + FARMERS_MARKET ×2 | **100% (14W-0L)**, $201,605 vs $137,480 |
| post-#1399, pinned PET_CAFE ×2 + FARMERS_MARKET ×3 | **92.9% (13W-1L)**, $92,501 vs $88,864 |
| invariants | `agent` still the last callable, no module-scope imports, 0 errors under `KAGGRICULTURE_DEBUG=1`, max turn 0.016-0.088s |

Mechanism verified rather than inferred: on a pinned tomato draw the adaptive
agent holds **65 TOMATO tiles by day 14** where the control holds 1, with tomato
priced at **$469**, and `detect_market_params` reports HINGE. No strategy code
changed — only what the crops are worth.

**The carrot counter-finding did not reproduce.** It was reported as −57 win-rate
points on a carrot-heavy draw and flagged as a blocker. Measured here at
**+92.9%**. The original test paired a naive-swap agent against a never-plant-
carrot agent, which is not the decision in front of us; adaptive-vs-pre-fix is,
and it wins. The per-planting overhead item below is still worth doing on its own
merits, but **it is not a prerequisite for this.**

**Before shipping:** re-copy `agents/sweep_ref.py` from `main.py` (it is currently
the pre-curve-fix control, deliberately, so this change can still be measured
against it), snapshot to `agents/v6_curve.py`, and set `AGENT_VERSION`. The
opponent panel still carries the stale curve — rebuild it or it cannot see this.

### Original entry

Added 2026-08-14. **PR #1399 is still open and targets 1.32.7; PyPI's latest is
1.32.6, verified.** When it lands, tomato/carrot/egg prices go quadratic above a
demand knee: TOMATO at a 500-unit deficit goes **$120 → $552**.

We are unusually exposed *and* unusually well placed. Exposed: on a pinned
PIZZA_SHOP ×3 draw our agent measured **0 wins in 28 games**. Well placed:
`build_plant_plan` is already crop-agnostic and **no gate blocks tomato — the
stale price curve does**, so the fix is three constants and two functions
(`main.py:79-89`, `:196-209`, `:212-224`), not a strategy rewrite.

Keep **both** parameter sets and pick per turn by checking each against
`obs["market"]["prices"]` at the observed inventory. Measured behaviour-identical
on today's ladder (28-28-4, same money to the dollar, same planting) and +26.6
win-rate points post-1399. Also honour `obs["market"]["params"]` when present.

**Must land together with the per-planting overhead fix below** — the naive swap
is **−57 win-rate points on a carrot-heavy draw**.

**Not yet independently reproduced** — those win rates come from the parallel
analysis harness. Re-measure before shipping.

## 0. Charge per-planting overhead in the plant score — `idea`

`main.py:485` scores a tile as `(marginal revenue − seed) / (1 + 2·occupancy +
harvests)`. A 4-day carrot is charged the same per tile-day as a 17-day melon,
so the dig-and-replant overhead is invisible. Latent today (carrot never clears
the gate at current prices); becomes a trap the moment #1399 lifts carrot past
$60/unit — the planner floods 22 carrot tiles and loses 6-22.

## 0. Earlier, larger strawberry — `idea`, structurally blocked

The elite farm is denser on **less** land: 78 owned tiles against our 88, 3-6
empty against our 20-40, holding 60 standing plants where we sag to 40. Same
plantings (162 vs 162) and same productive actions (2,678 vs 2,702). Measured
over 30 version-matched (1.32.6) elite player-seasons vs 4 of ours.

**The whole gap is strawberry**, reconstructed from per-day census deltas:

| crop | elite plantings | ours | elite tile-days | ours |
|---|---|---|---|---|
| STRAWBERRY | **42.1** | 24.5 | **679** | 393 |
| WHEAT | 35.8 | 45.5 | 332 | 205 |
| MELON | 10.0 | 12.2 | 237 | 264 |

They first plant strawberry on **day 6.8**; we wait until **day 11.0**. We plant
*more* wheat and get fewer tile-days from it -- we churn short crops while they
hold long ones.

**They are not richer early.** Days 0-8 they run $59-$581, as broke as we do. The
difference is deployment: at mid-day 0 we are still holding **$1,288** while they
are at **$111**, and they take the 2nd quadrant on day 7 to our day 9-10. They
pull ahead from day 13 ($11,410 vs $4,318). We also fertilise **33.9%** of plants
to their 14.4% -- our early capital goes into fertiliser and buffer, theirs into
land and strawberry.

**Not reachable by tuning.** Every gate that mediates this is already at its
optimum, measured 8 paired seeds vs `pass`:

| knob | tested | result |
|---|---|---|
| `MAX_QUADRANTS` | 3 vs 4 | 3 is **-$9,556** -- their land level is worse for us |
| `LAND_LATEST_DAY` | 10 vs 16 | 10 is **-$24,275** |
| `RUNWAY_DAYS` | 2 / 4 / 6 | 6 best; 2 is -$8,179 |
| `LIVESTOCK_RESERVE` | 0 vs 900 | 900 best; 0 is -$16,608 |
| `MIN_PLANT_SCORE` x `OCCUPANCY_COST` | 9-cell grid | current pair best by $8,260 |
| `PLANT_ACTIONS` | 1 vs 2 | 1 is -$13,495 |

Each one is individually load-bearing, so earlier strawberry needs a **structural**
change, not a constant: the timing is jointly set by the marginal-price scorer
(melon out-scores strawberry 56 to 26 on day 0) and the cash floor (a $100 seed
behind `CASH_FLOOR + LIVESTOCK_RESERVE + burn * RUNWAY_DAYS`). Candidate: a
dedicated strawberry runway from ~day 6 that reserves tiles and seed cash outside
the general scorer, rather than competing inside it.

**Untested. The four elite-derived hypotheses tested so far all died** (watering
discipline, tomato/carrot, shop-draw conditioning, land level), so treat the
causal claim here as unproven until a build measures it.

## 0. The opponent panel — **BUILT 2026-08-10**, and it says the build is not their edge

`panel.py` extracts a competitor's build from replay digests and scripts it onto
our machinery: hiring curve, land schedule, herd composition, planting schedule.
Everything else -- routing, selling, watering, fertilizer -- stays as `main.py`
does it, so a panel agent is **their strategy with execution held constant**.

```bash
python panel.py --build
python bench.py main.py --opponents panel
```

**Finding 1: the top of this ladder runs one script.** Of the seven competitors
with >=2 digested 1.32.6 seasons, **six share an identical build** -- land
`{7:2, 11:3}`, herd `{COW:8, SHEEP:6}`, same planting schedule, differing only by
a hand or two per day. `kakuteki` shows *zero* variation across all six of its
seasons while its money swings $62k-$91k, so that spread is seed and opponent,
not decisions. Only **Seb** differs: 4 quadrants from day 5, 20 animals,
strawberry from day 5. `panel.py` groups on land+herd so the panel is not six
copies of one opponent.

**Finding 2: with execution held constant we beat their build.** 20 seeds:

| opponent | build from | win rate | our $ | their $ |
|---|---|---|---|---|
| `panel_kakuteki` | 21 seasons, 6 competitors | **100%** (40-0) | 82,632 | 61,841 |
| `panel_seb_allegedly` | 4 seasons | **62%** (25-15) | 71,850 | 66,740 |
| `archetype` (old balance) | 3 accounts | 100% (40-0) | 118,203 | 29,805 |

**This is the seventh refutation of "copy what the elites do".** The dominant
meta build loses to ours 40-0 when neither side gets an execution advantage. The
panel agents also earn 13-17% less than the real competitors did ($61,841 vs
$71,366; $66,740 vs $80,123), which is the size of the execution gap -- their
build is worth *less* than ours, and their results are better, so **their entire
edge is execution.**

**Finding 3: we finally have a non-saturated sparring partner.** `pass`,
`archetype` and `panel_kakuteki` are all 100% wins and therefore measure nothing.
`panel_seb_allegedly` at **62%** has room to move in both directions. Use it as
the head-to-head metric instead of a mirror -- mirrors flatter production cuts
and one predicted a 79% win the ladder scored at +0.3.

**Caveats.** The scripts set *intent*: our cash gate still defers land (kakuteki
targets 2 quadrants on day 7 and reaches it on day 9), and Seb's sheep cap at 6
of a targeted 10 on the reserved pasture tiles. Plantings are reconstructed from
per-day census deltas because the elite digests predate `digest.py` recording the
crop on PLANT and the raw replays are pruned. And our 40% *ladder* win rate is
against rating peers (~905), not against these 3000+ competitors, so it is not
the same comparison.

## How to validate (read before testing anything)

**Know the noise floor: ±$1,300.** The same unchanged agent measured 161,673 /
162,754 / 160,130 / 160,536 across four disjoint 6-seed sets
(`bench.py --seed0 7|101|211|331`). **A difference under ~$3,000 is not a result.**
Measured 2026-08-07; re-measure if the agent changes materially.

A single 6-seed run takes **~15 minutes** on this machine. Run one at a time —
parallel runs did not speed it up and made failures hard to see.

Two harnesses, and they answer different questions:

```bash
python sweep.py --ref agents/<live version>.py --seeds 6 "CONST=a,b,c"
```

```bash
python bench.py main.py --seeds 6
```

- **Head-to-head** (`sweep.py`, or `bench.py` against a saved version) measures
  the change *relative* to the live agent. It is the metric the ladder scores.
- **Absolute, against `pass`** measures the change with no market competition.
  **Any change that alters how much we produce must be checked this way too** —
  shrinking our own output hands market share to the opponent, which flatters a
  production cut in head-to-head and hides the revenue loss. This is exactly how
  the "cut land and hands" change slipped through before being caught.

Batch locally-validated changes freely. Anything that can only be judged on the
ladder should ship in a small group, or attribution is impossible — 5
submissions/day, only the latest 2 ranked.

**Check a proposed gate change by solving it, not by running it.** Both fixes
proposed for #0b looked reasonable and one of them is provably a no-op in exactly
the region it targets — five lines of arithmetic caught it before a sweep did.
Any change to a threshold of the form `if x - cost < f(x)` deserves that check.

---

## Candidates, ranked by confidence × impact

Re-ranked 2026-08-06 against the settled v2-haul 10-game batch (5W-5L, rating
940.7). See the findings log in `REPLAY_ANALYSIS_CHECKLIST.md` for the evidence.

### 0. Collect the fertilizer — **`shipped`** as `v3-fert` (55309702, 2026-08-07)
*Awaiting ladder confirmation — needs ~30 episodes before the rating means
anything. Pull a balanced sample then, per the checklist.*

**Measured +$7,408/game (+4.8%) absolute vs `pass` over 10 seeds; 88% win rate
head-to-head against v2-haul over 8 seeds, both seats.** One-line change:
`P_COLLECT_FERT` 45 → 64, just under `P_CARE`.

| | v2-haul | v3-fert |
|---|---|---|
| mean $ vs `pass`, 10 seeds | 153,500 | **160,908** |
| fertilizer missed | 40-43% (~$9,300) | **1-4% (~$300)** |
| moves per useful action | 1.51 | **1.33** |

The travel improvement was unplanned and is the more interesting result: the unit
is already standing on the animal tile after `FEED`/`CARE`, so collecting there
removes a later round trip. That is a genuine dent in item #2 — 1.51 → 1.33
against Ben's 1.23 — from a change that was not about travel at all.

Invariants held: 0 animal deaths, 0 wasted no-ops, 0 days at shed capacity,
max weeds 11, max turn 0.006s.

*Follow-up spotted while measuring:* the season now ends with fertilizer inventory
**+125 above I0** at $75 against a $100 base, i.e. we are pushing it down the glut
side. Diverting more of the collected fertilizer onto strawberry ticks instead of
selling it may be worth more than the marginal sale. Untested.

*Original write-up:*
**We destroy 45% of our own fertilizer, ~138 units ≈ $10,300 per game.** Best
opponents miss 4-6%. `fertilizer_available` is a bool the env resets daily, so
uncollected is destroyed, not deferred. Two of the five losses in the batch were
by $7,223 and $7,554 — both smaller than this leak.

*Cause:* `P_COLLECT_FERT = 45` is the lowest priority in the table, below
`P_PLANT = 50`. On a busy farm the queue never reaches it. But the unit is
already standing on the animal tile after `FEED`/`CARE`, so the collect is a
**zero-movement action** — it should sit with them, not at the bottom.

*Fix:* raise `P_COLLECT_FERT` to just under `P_CARE` (65), or bundle it into the
rancher route so a unit that fed and cared also collects before moving on.

*Test:* absolute vs `pass`; check `fertilizer missed` in `analyze.py` drops under
10% and fertilizer units sold roughly triples. Cheapest change on the list.

### 0. Opponent-supply contention pivot — **`validated locally`** as `v5-pivot`
**63% win rate over 60 games against the shipped agent (p≈0.04)** — the first
change here validated on *win rate* rather than mean money, which is the actual
objective.

Crops and animals were valued against an inventory projected forward for the
town's remaining demand but with **no allowance for what the opponent is about to
land**, even though their whole board is visible. `rival_pipeline()` reads their
tiles and animals and prices `RIVAL_SUPPLY_SHARE` of it into the projection, so a
contested product is worth less at the margin and the mix pivots off it.

| RIVAL_SUPPLY_SHARE | win rate vs shipped |
|---|---|
| **0.25** | **70% (40 games), 63% (60 games)** |
| 0.5 | 60% |
| 0.75 | 62% |

Discounting their *entire* pipeline over-reacts; a quarter tips the margin without
abandoning the product.

*Mechanism confirmed, not just the number:* against the archetype's 8 cows we shift
from 8 sheep/7 cows to **9 sheep/6 cows** — into wool, away from contested milk.

*Guards:* identical to the shipped agent against `pass` (no crops to contest, so
correctly inert — no self-harm); 100% vs the archetype with mean money **+$3,495**;
0 animal deaths, 10 weeds, 0.017s/turn.

*Herd size re-tuned with it on* (the old optimum predates the pivot):
`MAX_ANIMALS` 13 → 28%, **16 → 70%**, 19 → 70%. Unchanged at 16.

### 1. Stop planting strawberry after ~day 14 — `idea`
**Now the top open candidate**, and it survives the wheat correction because it
rests on tile census and harvest counts, not on the sell tally.

We hold **33-35 strawberry tiles at day 26 to the archetype's 23 and both sell
~205 units**. Strawberry's first yield is +10 days, so anything planted after ~day
14 returns at most one tick while consuming a water action every day until then.
Our watering is level with theirs (922 vs 934) but our harvests are 25% lower
(298 vs 374).

`crop_projection` already zeroes strawberry once the season is too short, but the
cutoff is generous: at day 16 it still projects 2 units and scores 4.9, which beats
nothing and so gets planted. The question is whether those tiles are better left
*empty* — the labour they consume is worth more on the tiles already growing.
**Not** wheat: that was tested and costs ~$4,800/tile (see Rejected).

*Test:* absolute vs `pass`. Sweep the effective cutoff and watch harvests per
watering action, not just money.

### 2. Travel efficiency — **CLOSED 2026-08-08, not independently reducible**
Six mechanisms measured, no lever left. The gap is real but every component of it
is either already optimal or load-bearing.

**The gap, normalised.** Over days 2-27 our working area is *the same* as the
elite cohort's (66.6 tiles vs 64.4) — the earlier "they work 75 tiles to our 100"
framing was an artefact of averaging across their faster early expansion. Travel
constant `C = moves / sqrt(N·A)`: **ours 8.72, theirs 7.33** (median 7.17). Real,
19%, and *not* bought with land — within our own four seasons the two with area
75.0 score C 7.87/8.36 while the two with area ~58 score 9.27/9.39. **Bigger area
gives us better C**, so the "4th quadrant buys tiles at the cost of travel"
hypothesis previously recorded here is refuted.

**Three new negative results, all measured on seed 7:**

| test | result |
|---|---|
| greedy assignment vs **exact optimum** (Hungarian, same objective, 664 turns) | greedy within **0.54%**; the optimal assignment travels **+59 moves *more*** |
| planted-tile siting vs the ideal compact set nearest the shed | **+0.33 tiles** per planted tile, season mean |
| target thrash (unit re-targeted mid-route) | **9.9%** of walking turns; bounded upside ~363 moves |
| `MOVE_PENALTY` sweep 2/4/7/11 | 119,929 / **152,349** / 147,783 / 121,824 — sharp peak, 4 is right |

So the matching is optimal, the objective weight is optimal, and the crops are
already sited compactly. Travel is close to what our job set requires.

**Where the travel actually goes** (2,645 executed actions, 3,651 moves):

| half | actions | moves | mv/action |
|---|---|---|---|
| animal (FEED/CARE/HARVEST/COLLECT) | 1,206 | 1,372 | **1.14** |
| crop (WATER/FERTILIZE/PLANT/DIG) | 1,213 | 1,845 | **1.52** |

**Our animal half already matches the elite's overall 1.14.** WATER alone is
**37.6%** of all travel (946 actions, 1.45 moves each). Trips are short — 24.5%
zero-move, 42% one move, 7.8% four or more — so this is trip *count*, not hauls.

**The residual is the dead waters, and they are load-bearing.** ~500 dead waters
a game (REFUTED.md) at 1.45 moves each is ~725 moves, which is the whole
0.25-moves/action gap. But removing them costs **$6,200** — they absorb idle
capacity — and giving the crew more tiles instead costs **$13,495**
(`PLANT_ACTIONS = 1`).

**The real difference is crop density, and it is circular.** They hold 60 plants
in a compact area; we hold ~45 over the same area, so their crop hops are
shorter. We cannot hold 60 because the crew cannot service them — partly because
our crop travel is higher. Entry into that loop is not available through any knob
tested. Anything further here needs a different execution model, not a tuning
change; six mechanisms have now failed (zones, revisits, chaining, assignment,
siting, penalty weight).

### 3. Work-scaled hiring — **REFUTED 2026-08-07**
`MAX_HANDS = 12` measured **$159,884** against 13's **$161,673** on the same seed
set — a $1,789 gap, inside the ±$1,300 noise band. **Keep 13.**

Worth recording *how* this nearly slipped through: head-to-head against v3-fert,
`MAX_HANDS=12` won **75%**, which reads as a large win. Absolute against `pass` it
is a wash. Cutting a hand makes us produce less, which crashes the shared market
less, which flatters the mirror. Same trap as "cut hands and land to match their
spend". **A production cut that wins head-to-head and ties absolute is not a win.**

The watering data in #7 says the same thing independently: we run 1.00-1.08 water
per plant for 28 straight days, so there is no spare labour to give up.

*Original evidence, retained:*
The v2 batch says spend is not where we lose: our hire bill ($11,303-11,769) is
within $900 of the archetype's $10,885, and it out-earns us by $44-60k. Still
worth doing eventually, but it is worth ~$1k/game. Do #0 (shipped) and #1 first.

*Original evidence:*
Ben pays **$9,576** and peaks at **14 hands**; we pay $11,769 and peak at 13. He
hires 4-8 early and 12-14 only from day 18. The fib cost is convex and resets
daily, so deferring the expensive hands until the harvest load exists is close to
free money.

*Note:* `target_hands` already scales with work, but `ACTIONS_PER_UNIT = 12`
makes it saturate early. This is a re-tune, not new machinery.

### 4. Herd mix / size — **REFUTED 2026-08-07**, moved to Rejected below
The size half is now settled: `MAX_ANIMALS` swept head-to-head against v3-fert,
6 seeds x 2 seats — **12 → 16.7% win, 16 → 75.0%, 20 → 66.7%**. The current 16 is
right and the "buy fewer animals to match the archetype" reading of the ladder was
wrong. Original notes kept below for the mix (cow vs sheep) question, which is
separate and also looks dead.


Ben runs a fixed **8 cows + 6 sheep**. We skew cows and sell milk down to
**$112/unit — below its $160 base** — while wool holds $187-245. `pick_animal`
ranks cows above sheep until milk saturates, and the herd cap binds first, so we
never reach the sheep. Milk is heavily contested; wool much less so.

*v2 batch update:* over 10 games we are **ahead** on both milk (+$30,659) and wool
(+$73,238) against the opponent field. The realised prices are shared-market
noise, not a standing weakness — our milk averaged $217 in one game and $83 in
another against the same herd. Deprioritise; the herd is not where the loss is.
The one part still worth acting on is herd *size*: at 15-16 animals we buy ~$3,000
more livestock than the archetype's ~8-14 and produce fertilizer we then throw
away (#0). Re-measure only after #0 lands.

### 5. Crop mix: strawberry up, melon down — `idea`, **reversed**
Ben holds 41 strawberry / 12 melon. We run ~33 / ~20. Melon's glut curve is
quadratic and no town shop demands it.

*v2 batch update — the direction is wrong.* Melon is our **best** line against the
field: 1,727 units for $269,410 against their 1,204 for $173,100, **+$96,310** over
10 games, realising $155 to their $143. And more strawberry tiles bought us no
more strawberries (see #1). Leave the melon allocation alone — and note the wheat
rotation, once thought to be the real trade here, is refuted (see Rejected).

### 5b. The planting dead zones, days 1-8 and 15-19 — `idea`
Two holes in our schedule. The **days 15-19** hole is not cash-related: after
strawberry's window closes the plan collapses to whatever is left. Wheat was the
obvious filler and is refuted (see Rejected), so this hole may simply be correct
behaviour — there may be nothing worth planting that late. Verify before treating
it as a defect.

The **days 1-8** hole is the livestock-reserve deadlock. Diagnosed correctly, but
the direct fix is refuted (see Rejected): unblocking the cash makes us plant more
than the crew can water, and weeds cost more than the plantings earn. Reachable
only via item #7. Their first strawberry also goes in on day 7 against our day 11.

### 6. Early all-in cash posture — `idea`, **blocked on #7**
Ben buys **2 cows + 2 sheep on day 0** ($1,800 of $3,000) and runs at $1-150 cash
through day 8. Our `CASH_FLOOR = 250` plus `LIVESTOCK_RESERVE = 900` is more
conservative and delays the herd.

*Risk:* our runway logic exists because an early version starved itself into a
26-day standstill at $150. Loosen carefully and watch the day 0-10 money trace.

*Update (measured 2026-08-06):* the targeted version of this — a fractional
livestock reserve — was implemented and **refuted**, see Rejected. Loosening the
early cash posture is not the bottleneck; the planting allowance behind it is.
Blocked on #7. What may still be true afterwards is the *seed allocation* on day 0:
the archetype spends ~$1,030 on 19 tiles to our ~$670 on 11.

### 7. Headcount from the workload formula — `idea`, **measured 2026-08-07**
The observable this item asked for is now measured, from the v3-fert ladder batch.

**Unit-actions per plant per day** (`WATER`+`PLANT`+`HARVEST`+`DIG`+`FERTILIZE`):
mean **1.56-1.59**, against the **2.00** that `allowance = spare // 2` assumes.
And it is strongly phase-dependent — ~1.2-1.5 through the growth phase (days
11-20), rising to ~1.9-2.3 once harvesting starts (days 21-29).

**`WATER` actions per living plant per day** — the real constraint, since a plant
must be watered daily or it weeds:

| days | water/plant | mean weeds |
|---|---|---|
| 0-18 | 0.98-1.07 | 0.0-0.3 |
| **19-21** | **0.76-0.98** | 0.4-0.8 |
| 22-27 | 1.03-1.08 | 0.4-0.8 |
| 28-29 | 0.36-0.63 | 10-16 (deliberate end-game abandonment) |

**This mostly argues against changing anything.** Riding 1.00-1.08 for 28 days is
tight calibration, not luck: the flat `// 2` is wrong in detail but the crew and
the planting are in near-perfect balance in practice. It also re-explains the #0b
failure — at days 0-8 we run exactly 1.00 water/plant on 8 plants, so the 20 tiles
the fractional reserve unlocked had nowhere near the labour to cover them.

*What is left:* a genuine squeeze at **days 19-21** (0.76-0.98), worth under one
tile. A phase-aware divisor — budget ~1.3 during growth and ~2.0 from day 21 —
would let us plant slightly more early and protect the harvest window. Small, and
it should be tried only if the noise-floor test shows we can even resolve it.

*Superseded note:* the earlier framing (below) assumed the allowance was far too
generous. Measured, it is somewhat too *strict* during growth and about right at
harvest.

Now blocking two other items. The refuted #0b showed that `allowance =
spare // 2 - plants_alive` budgets 2 unit-actions per plant per day and permits 20
tiles on day 0 against a crew of 4-5 — it was simply never reached while the cash
gate bound first. Both the early-planting hole (#5b) and any attempt to loosen the
cash reserve need this replaced with a derived number rather than a guessed one.
**Measure actions-per-plant-per-day directly from a replay first** — it is
observable, so it should not be a swept parameter at all.

Replace the current `work / ACTIONS_PER_UNIT` heuristic with the section 3
formula, which accounts for how *spread out* the work is rather than only how
much of it there is:

```
turns_needed = task_count + C·sqrt(task_count · active_task_area)
hire while  24·units < turns_needed  AND  next hand's fib cost < its marginal output
```

Two refinements from the brainstorm that matter:

* **`active_task_area`, not `total_unlocked_tiles`.** Only tiles with a task
  pending today plus tiles we intend to plant. This cleanly separates the
  land-buying decision from the hiring one, and is why clustering the herd
  worked: 14 animals spread over 75 tiles needs `42 + 1.23·sqrt(42·75)` ≈ 98
  turns ≈ 4 units, but clustered on ~9 tiles at the shed it is
  `42 + 1.23·sqrt(42·9)` ≈ 66 turns ≈ 2.75 units.
* **Hiring is a cost-benefit stop, not a turns-supply stop.** The fib cost is a
  wall, not a ramp — see Rejected below; we already have the measurements.

*Note:* `target_hands` already scales with work, but `ACTIONS_PER_UNIT = 12`
saturates it early, so it pins to `MAX_HANDS` from ~day 11. Ben instead runs 4–8
hands early and 12–14 only from day 18, paying $9,576 to our $11,769 while
peaking *higher*. Overlaps with item 3.

### 8. Three quadrants — `idea`, now a **coin flip** (re-measured 2026-08-07)
`MAX_QUADRANTS = 3` measured **$162,044** against 4's **$161,673** — a $371 gap,
pure noise. It used to be a clear **−$7,089** for 3. The fertilizer fix freed
enough unit-actions that the 4th quadrant no longer clearly pays for itself.

Not a reason to change anything — but the old "4 is settled" note is stale, and if
anything later frees more labour this should be re-checked rather than assumed.

Also measured and inside noise, same batch: `HAUL_TRIGGER=62` (+$2,175) and
`SHED_PRESSURE=68` (+$268). `HAUL_TRIGGER` is the only one close enough to be
worth one confirmation run on a different seed set.

*Original note:*
No top agent buys the 4th. **Our own test says 4 is better for us**
($148,550 vs $141,461 vs `pass`) — because our tiles sit underused while Ben's
are all in production. So this is downstream of #1 and #2: fix utilisation first,
then re-test. `LAND_LATEST_DAY = 16` already blocks the worst case.

---

---

## Refuted

Moved to [REFUTED.md](REFUTED.md) — settled questions, with the numbers that settled them. **Read it before adding anything here.**

## Open questions

- **Is determinism itself the edge?** Ben's build order is byte-identical across
  six games and six opponents. A fixed plan can be tuned to a sharpness adaptive
  heuristics never reach, but cannot respond to anything. Worth deciding
  deliberately rather than by default.
- **Why is rating 2970 vs our 940 when the money is comparable?** His sales are
  ~$131k/game and final ~$104k, close to ours. He wins narrowly and consistently
  (+11.3k, −17.8k, +4.8k, +3.0k, +9.5k, +3.5k). The gap is reliability, not scale
   — worth understanding before optimising for money.
  *Partial answer from the v2 batch:* the same build appears under at least four
  account names, and it beat us 3/3 by $44-60k, so against *us* it is not narrow.
  Its consistency is what a fixed build order buys; its margin over us is wheat.
- **How widely is the archetype copied?** Four accounts in 16 sampled games ran a
  statistically identical build. If it is the dominant strategy on the ladder, a
  counter tuned specifically against it may be worth more than general strength.
- **Is there still an undiscovered mechanic?** The reference doc was missing
  three load-bearing ones. Nothing new surfaced in Ben's replays.
- **Zone continuity across days.** Hands do not persist, so zones are rebuilt
  each morning. Should the rebuild try to keep the same physical unit on roughly
  the same patch? Units all respawn at the shed regardless, so the outbound leg
  is paid either way — continuity may buy nothing. Cheap to test both ways.
- **Zone partition algorithm.** Greedy nearest-neighbour growth outward from the
  shed, versus bin-packing tiles to a 24-turn budget. Greedy is far simpler and
  the budget constraint is soft; start there.
