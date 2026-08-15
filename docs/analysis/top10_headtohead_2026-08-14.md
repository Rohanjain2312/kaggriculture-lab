# Top-cohort head-to-head analysis — 2026-08-14

**Question asked:** not "how do the leaders make money" but **"how do they beat
the agent sitting across from them"**. Scoring is win/loss per episode, so the
only quantity that matters is the margin against that one opponent. This is the
first analysis in the project framed that way throughout.

Corpus: **22 episodes, all `kaggle-environments` 1.32.6**, pulled 2026-08-14.
Tooling: `tools/margin.py` (new), digests in `docs/analysis/digests-top10/`.
Our own build measured from 6 local games in `docs/analysis/digests-ours/`.

## Corpus composition — read this before the numbers

Every one of the 22 episodes involves **カワシギ** (rank 1, 3260.7, and **135
rating points clear of rank 2** — the largest gap anywhere in the top 50). They
went **18W-4L**. Opponents were 8 distinct top-cohort teams: researchstudio.site
(13 games), somewhere after, Mohamed abdelrazik, Furious Monk, uri_kkyhr,
Thomas Tschinkel, Ueddy.

This makes a naive "winner vs loser" table useless — it would just re-describe
one agent. `tools/margin.py --focus` pairs by *team* instead, which turns the
confound into the actual question: **what does the #1 agent do differently from
every elite opponent it faces, and what did the four that beat it do?**

The intended pull was "latest 3 games × top 10". Kaggle's `ListEpisodes`
endpoint rate-limited hard (HTTP 429) partway through; these 22 came from a
leaderboard-UI network capture instead. The remaining teams are still queued.

## 1. The games are close, and they are not decided early

| | |
|---|---|
| median winning margin | **6.4%** / **$4,914** |
| decided by ≤10% | **17/22 (77%)** |
| smallest margin | $360 |
| median "decisive day" (after which the winner never trails) | **day 16 of 30** |
| decided in days 0–5 | **0/21 (0%)** |
| games where the day-20 leader still lost | 6/22 (27%) |

On the older 36-episode corpus the margins were tighter still: median **2.2%**,
median **$2,066**, with 44% inside 2%.

**Consequence for how we validate changes.** A change worth $5k/game is not a
rounding error, it is larger than the median margin — it flips the median game.
Equally, our habit of reading mean money over a seed set hides exactly this: a
change that adds $20k to games already won and nothing to the close ones scores
well on mean money and zero on the ladder. That is the shape of every tuning
change we have shipped since v3-fert.

## 2. What the #1 agent does differently

Paired within-game against its opponent, 22 games. `~` marks features derived
from market *orders* — orders are intent and unfilled stock is re-offered each
turn, so trust direction, not magnitude (this corpus shows 1,872 units of
FERTILIZER "sold" from a herd that can physically produce ~390).

| feature | #1 | opponent | higher in | p |
|---|---|---|---|---|
| `firstsell_WHEAT` | **day 0** | day 5 | 100% earlier | <0.001 |
| `peak_animals` | 14 | 12 | 94% | <0.001 |
| `animals_d10` | 12 | 12 | 100% | 0.002 |
| `actions` | 6,354 | 6,648 | **86% fewer** | 0.001 |
| `plants_d10` | 29 | 37 | 82% **fewer** | 0.004 |
| `money_d10` | $2,193 | $1,450 | 77% | 0.017 |
| ~`n_products_sold` | 7 | 6 | 100% | <0.001 |
| ~`sold_CARROT` | 12 | 0 | 91% | <0.001 |
| ~`sold_MELON` | 72 | 108 | 90% **less** | <0.001 |

Read together this is one coherent strategy, and it is **not** "work harder":

- **Fewer actions, fewer early plants, more animals, more cash.** They do *less*
  and hold *more* — 86% of the time they act less than the opponent and still
  end richer. Livestock is front-loaded (herd complete by day 11), crops are
  added after the herd pays for them.
- **Broadest product mix in every single game (100%, 7 lines vs 6).** They are
  never in a two-product race; the opponent always is.
- **They farm carrot; the field does not.** Median 12 vs 0.
- **They deliberately under-produce melon** — 90% of games below their opponent.
  Melon has **no shop demand at all** (`SHOPS` has no MELON entry); its only
  buyer is the town centre at 1/day post-1394. Melon is the product everyone
  crashes and they refuse to join in.
- **Day-0 wheat.** They are in the market on turn one, five days before the field.

### What beat them (the 4 losses)

| episode | opponent | margin |
|---|---|---|
| 92967748 | researchstudio.site | −$360 |
| 93022777 | researchstudio.site | −$3,099 |
| 93101463 | Mohamed abdelrazik | −$1,534 |
| 93125386 | somewhere after | −$4,888 |

The opponents who won ran **more hands (6 vs 4)**, **more fertilizer trade
(+33%)** and **got to wheat earlier (day 2.5 vs day 5)** than opponents who lost
to them. The counter to the leader is more labour and earlier market entry — not
a different crop plan.

## 3. The largest opening on the board: nobody grows tomato

| product | shops demand it, **neither player produced it** |
|---|---|
| **TOMATO** | **21/22 episodes (95%)** |
| EGG | 19/22 (86%) |
| CARROT | 13/18 on the older corpus (72%) |

Across the older 36-episode corpus: TOMATO unproduced in 97%, CARROT 94%, EGG 86%.

**This is not a curiosity, it is the next balance change.** See §5.

## 4. Where our agent actually stands

Our build, measured over 6 local games (seeds 7–12, vs `panel_kakuteki`; we won
6/6). Median values, ours against the ladder cohort:

| feature | **ours** | #1 | their opponents |
|---|---|---|---|
| `peak_plants` | **43.5** | 61.0 | 61.5 |
| `plants_d10` | **0** | 29 | 37 |
| `animals_d10` | **7** | 12 | 12 |
| `money_d10` | **$558** | $2,193 | $1,450 |
| `final_hands` | **13** | 8 | 4 |
| `hires` (season total) | **299** | 277 | 283 |
| `firstsell_STRAWBERRY` | **day 21** | day 16 | day 17 |
| ~`sold_MELON` | **156** | 72 | 108 |
| ~`sold_CARROT` | **0** | 12 | 0 |
| `moves_per_useful` | 1.3 | 1.3 | 1.3 |
| `peak_animals` | 16 | 14 | 12 |

Routing parity is achieved — `moves_per_useful` 1.3 across the board, the gap
flagged in earlier analyses is closed. Everything else says the same thing:

> **We spend more labour (13 hands vs 8) to farm 29% fewer crop tiles (43.5 vs
> 61), and we start ten days late.**

### Two reproducible defects in the planting schedule

Plant count by day, median across our 6 games against the #1's 22:

```
day       0   1   2   3   4   5   6   7   8   9  10  11  12  13  14 ...
ours      9  10  10  10  10  10  10  10  10  10   0  21  36  36  36
#1        9  19  19  19  17  16  19  21  24  35  29  35  53  56  61
```

**(a) Days 1–9 are pinned at exactly 10 plants.** A flat, round 10 for nine
consecutive days is a constraint binding, not a valuation outcome — a cash
floor or planting allowance, not `MIN_PLANT_SCORE` choosing. During that window
the leader runs 16–35 tiles.

**(b) Day 10 collapses to 0 plants and 0 watered — in 4 of 6 seeds.** A full
idle day at the season midpoint: synchronised monoculture harvest with no
replant that turn. Per-seed, days 7–14:

```
seed 7   [10, 10, 10,  0, 21, 36, 36, 36]      watered [9, 8, 9, 0, 19, 31, 30, 29]
seed 8   [10, 10, 10,  0, 20, 36, 40, 40]      watered [9, 8,10, 0, 17, 34, 36, 33]
seed 10  [10, 10, 10,  0, 20, 35, 35, 35]      watered [9, 9, 9, 0, 17, 31, 32, 30]
seed 11  [10, 10, 10,  0, 21, 34, 34, 34]      watered [9, 8, 9, 0, 19, 29, 29, 28]
```

We run **13 hands over 43 tiles (3.3 tiles/hand)** while the #1 runs **8 hands
over 61 tiles (7.6 tiles/hand)**.

> **Corrected 2026-08-14, same day.** This section originally concluded from that
> ratio that labour has stopped being the binding constraint and the gate should
> therefore be relaxed. **The ratio stands; the conclusion was measured and
> refuted** — `docs/REFUTED.md` → "The planting schedule bug is not a bug".
> Relaxing the cash floor costs **$56,469/game vs `pass`** (12 weeds, 3 animal
> deaths), and `MIN_PLANT_SCORE` is already optimal in both directions. The tile
> gap is a symptom of running a different crop economy, not of a loose gate.

## 5. The balance changes

Verified against the environment source and PyPI, not the announcement.

**Change 1 (PR #1394 — town demand cut, shops drawn with replacement):
already live in 1.32.6, and we already absorbed it.** That was the `v4-gate-r2`
/ `v5-pivot-r2` config fix — the only change we have ever shipped that moved the
ladder (+14 to +26 points). `main.py`'s `future_drain()` counts the shop
multiset correctly; no `set()` is ever applied to shops. Confirmed empirically:
**22/22 episodes in this corpus contain a duplicated shop**, median 2 copies of
some type, worst 3.

**Change 2 (PR #1399 — tomato/carrot/egg price spike): NOT SHIPPED YET.**
- PR #1399 is **still open**, head `1fbd3b7`, and bumps the version to **1.32.7**.
- **PyPI's latest is 1.32.6** (uploaded 2026-08-07). 1.32.7 does not exist.
- The installed source still has the pre-1399 `MARKET_PARAMS`; there is no
  `hinge` branch in `_shape`.

The diff is small and contained: `MARKET_PARAMS`, `_shape` (adds a `hinge`
shape and a `T` parameter) and `market_price`. `hinge` is linear below a knee at
`I0 − T` and **quadratic above it**, so "large shop demand, no production" stops
being a mild premium and becomes a spike:

| deficit → | 200 | 300 | 500 | 700 | 1000 |
|---|---|---|---|---|---|
| TOMATO today | 84 | 96 | 120 | 144 | 180 |
| TOMATO under 1399 | 84 | **144** | **552** | **1,344** | **3,252** |
| MELON (unchanged) | 296 | 300 | 304 | 307 | 311 |

Against a real ladder board: episode 90823863 (PIZZA_SHOP ×3) ended at a tomato
deficit of 483 → **$118 today, $502 under 1399**.

**Why this matters more to us than to anyone else.** Our planting path is
already crop-agnostic — `build_plant_plan` (`main.py:432-499`) prices every tile
off `market_price`, and `MIN_PLANT_SCORE` (`main.py:486`) is a single scalar
with no per-crop term. **No gate blocks tomato. The stale price curve does.**
Give the agent the right curve and it picks tomato up by itself.

Measured by the parallel analysis (its harness, not yet independently
reproduced — flagged for confirmation):

| scenario | our win rate |
|---|---|
| post-1399 env, `main.py` vs same agent with the curve fix | **36.7%** |
| pinned PIZZA_SHOP ×3 + FARMERS_MARKET ×2 draw | **0.0% (0-28)** |
| current 1.32.6, curve-fix agent vs `main.py` | 50.0%, **identical to the dollar** |

The fix is **version-adaptive**: keep both parameter sets and pick per turn by
checking each against `obs["market"]["prices"]` at the observed inventory. On
today's ladder it is provably behaviour-identical (same money, same planting,
28-28-4); when 1.32.7 lands it switches itself. That removes any need to time
the rollout.

**One counter-finding that must not be skipped.** A naive parameter swap is
+26.6 win-rate points on random draws but **−57 points on a carrot-heavy draw**.
Carrot only needs $60/unit to clear `MIN_PLANT_SCORE` where tomato needs $120,
because the score denominator `1 + 2·occupancy + harvests` (`main.py:485`)
charges a 4-day crop the same per tile-day as a 17-day one — the dig-and-replant
overhead is never charged. Under `hinge` the planner floods 22 carrot tiles.
Tomato, a 12-day crop, is not exposed to this. **Fix the per-planting overhead
term before or with the curve swap.**

**Methodology warning.** `agents/panel_*.py` are parameterised copies of our own
file and carry the same stale `MARKET_PARAMS`. Benching against the panel after
1399 lands would read ~50% and conclude "no change needed". The panel must get
the curve fix too or it is blind to the largest swing in the game.

## 6. What to do, in order

Ranked by expected effect on **win rate**, correctness before tuning.

**1. ~~Fix the planting schedule~~ — REFUTED the same day. See `docs/REFUTED.md`.**
It is not a bug. The flat at 10 tiles is `MIN_PLANT_SCORE` correctly refusing
wheat at 13-15 against a gate of 16 (*not* the cash floor, as guessed here); the
day-10 hole is the cash floor refusing a melon scoring 46.9, and relaxing it
costs **$56,469/game vs `pass`** with 12 weeds and 3 animal deaths. All three
constants — `MIN_PLANT_SCORE`, `RUNWAY_DAYS`, `LIVESTOCK_RESERVE` — are already
at a local optimum; every single-parameter move in every direction loses.

The 43.5-vs-61 tile gap in §4 is still real. What is now established is that it
is **not reachable by moving a threshold**: the three constants are jointly tuned
around a melon/strawberry economy and the leader runs a different one. That
promotes item 2 — changing what crops are *worth* is the only lever measured to
move the mix.

**2. Ship the version-adaptive market curve.** Behaviour-identical today,
worth ~27 win-rate points the day 1.32.7 lands, and removes rollout timing
risk. Must land with item 3.

**3. Charge per-planting overhead in the plant score** (`main.py:485`).
Currently a 4-day carrot is charged like a 17-day melon. This is latent today
and becomes a −57-point trap under 1399.

**4. Re-examine `MIN_PLANT_SCORE` once 1 and 3 are in.** It was tuned against a
labour constraint that no longer binds (3.3 tiles/hand vs the leader's 7.6).
Per `CLAUDE.md`: tune only after the bugs are out.

**5. Cut melon exposure.** We sell 2.2× the #1's melon volume into a product
with **zero shop demand** whose only buyer is now the town centre at 1/day. The
leader beats the field while deliberately producing less of it.

**6. Rebuild the opponent panel from this corpus.** `panel.py --build` against
`docs/analysis/digests-top10/` gives sparring partners with the current #1's
build (herd-first, day-0 wheat, carrot, low melon) instead of week-old profiles
— and every panel agent needs the curve fix from item 2.

## Refuted / do not pursue

- **"Copy the leader's fertilizer volume."** The 12× fertilizer figure is an
  order-counting artifact: 1,872 order-units against a 14-animal herd that can
  produce ~390. Same class of error as the "$148k wheat gap".
- **"Winners hire more."** True on the older corpus (93%, p=0.002) but
  `hands_d10` shows no signal (50%) — the hiring edge appears *after* the money
  gap opens, so it is an effect of winning, not a cause. On this corpus the sign
  reverses (28%).
- **"Match their shop alignment."** Our `alignment` metric puts the #1 *below*
  its opponents (14%, p=0.001) purely because fertilizer and melon are not
  shop-demanded. The metric is confounded; do not optimise it as written.
