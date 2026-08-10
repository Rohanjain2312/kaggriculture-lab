# Submission log

One row per Kaggle submission. **Snapshot `main.py` into `agents/<version>.py`
at submission time** and set `AGENT_VERSION` in `main.py` to match — otherwise
the exact code behind a ladder result is unrecoverable, and A/B tests against the
live agent become guesswork.

Limits: **5 submissions/day, only the latest 2 are ranked and matched.**

## Using the two ranked slots

Both ranked agents play the field independently, so the second slot is a free
A/B channel — but only if it is used as **control + experiment**, not two
experiments.

Submitting one new agent leaves the pair as `{previous, new}`, so **the incumbent
stays as the control for free**. Submitting two new agents ejects the incumbent:
if both are worse there is no baseline to compare against and ladder position is
lost for a day. So the cadence is:

1. Validate locally first — the harness runs 16 games/variant in minutes, which is
   far more throughput than the ladder gives in a day. The ladder is for
   *confirming* a change, not finding one.
2. Ship **one** agent per round, bundling everything that passed locally.
3. Read the pair against each other once both have ~30 episodes, and only then
   accept or revert.

Ratings drift as the field resubmits, so **read both scores at the same moment** —
comparing today's experiment against yesterday's remembered baseline is not a
controlled comparison. v2-haul read 940.7 on 2026-08-06 and 920.1 the next day
with no change to the agent.

| version | submission | date | score | local form | notes |
|---|---|---|---|---|---|
| `v0-baseline` | 55256285 | 2026-08-05 | 492.3 | ~$28k vs starter | greedy melon monoculture; 43 weeds, no animals |
| `v0-baseline` | 55256605 | 2026-08-05 | 485.9 | — | minor variant of the above |
| `v1-herd` | 55281835 | 2026-08-05 | 917.9 | $135-147k/seed | herd at shed, strawberry mix, marginal-price selling |
| `v2-haul` | 55286682 | 2026-08-06 | **918.7** | $142-158k/seed; **83% vs v1** | mid-day hauling fixes end-of-day shed overflow |
| `v3-fert` | 55309702 | 2026-08-07 | 913.5 | **$160,908 vs `pass`; 88% vs v2-haul** | collect fertilizer before it expires overnight |
| --- | --- | **1.32.6 balance change** | --- | *scores below are a different game* | --- |
| `v4-gate` | 55338056 | 2026-08-08 | 891.6 | +$3,591/game, 7/8 seed sets | `MIN_PLANT_SCORE=20` |
| `v5-pivot` | 55338743 | 2026-08-08 | 879.5 | 63% over 60 games vs v4-gate | `RIVAL_SUPPLY_SHARE=0.25` |
| `v4-gate-r2` | 55340304 | 2026-08-08 | 905.4 | — | + config fix (melon overvalued up to 8x) |
| `v5-pivot-r2` | 55340305 | 2026-08-08 | **905.7** | 79% over 24 games vs v4-gate-r2 | + config fix; **ranked pair with v4-gate-r2** |

**All scores above read together on 2026-08-10** (rank **1375 / 3545**), because
ratings drift: this same table previously recorded v2-haul at 940.7, v3-fert at
932.3 and v1-herd at 910.5 from different days. Only same-moment readings are
comparable, and **only within one balance** — do not compare across the 1.32.6 row.

### Two results worth keeping in view

**The config fix was the only change that moved the ladder.** Within 1.32.6:
v4-gate 891.6 -> v4-gate-r2 **905.4**, v5-pivot 879.5 -> v5-pivot-r2 **905.7**.
Reading the episode config instead of hardcoding town constants was worth +14 to
+26 rating points. It was a *correctness* fix, not a tuning change.

**The contention pivot was worth 0.3 points.** v5-pivot-r2 905.7 against
v4-gate-r2 905.4, on the ranked pair. `RIVAL_SUPPLY_SHARE` measured 63% and then
79% head-to-head locally and is indistinguishable from zero on the ladder.
**Local mirror head-to-head does not predict ladder movement** -- it is the metric
that has now misled us at 79% confidence. Absolute-vs-`pass` has meanwhile
correctly rejected six changes in one day.

**Scale check.** The board leads at 3228; we sit at 905.7. But the elite cohort
out-earns us by only ~15% in raw dollars (`docs/analysis/digests/`). A consistent
15% money edge wins nearly every game, and win/loss scoring compounds that into a
3.5x rating gap -- so a $5-6k/game swing is the size of edge that decides the
ladder, which is why the $6,200 and $13,495 losses measured on 2026-08-08 matter.

**Ranked pair is now `v3-fert` + `v2-haul`** (only the latest 2 count), so `v1-herd`
has dropped out of matchmaking. 4 submissions left today.

Ladder scores drift as opponents resubmit — v2-haul read 940.7 on 2026-08-06 and
926.4 the next day, v1-herd 910.5 → 917.9, with no change to either agent. Treat
any single reading as ±15 and only compare versions once both have settled.

## Ladder results

### v2-haul (55286682) — settled at **940.7**, 5W-5L over the last 10 episodes

Replays in `replays/ladder/v2-haul/`, full analysis in
`docs/analysis/v2-haul_ladder_2026-08-06.txt`, findings written up in
`REPLAY_ANALYSIS_CHECKLIST.md`.

| episode | opponent | us | them | result |
|---|---|---|---|---|
| 90406353 | Abdoulaye DIAW | 111,230 | 73,493 | **W** +37,737 |
| 90418372 | Viraj Bakshi | 126,924 | 85,080 | **W** +41,844 |
| 90450224 | luca fregona | 110,857 | 89,874 | **W** +20,983 |
| 90467041 | Sparsh389 | 107,983 | 85,759 | **W** +22,224 |
| 90486814 | FeedMeSeymour | 98,972 | 90,124 | **W** +8,848 |
| 90454808 | Mohit Babel | 98,730 | 105,953 | L −7,223 |
| 90405608 | AravindLochan | 98,106 | 105,660 | L −7,554 |
| 90411421 | Jesy Lu | 88,164 | 132,508 | L −44,344 |
| 90506558 | Dimitri ZABRE | 67,113 | 111,958 | L −44,845 |
| 90450812 | Desyat IO | 106,107 | 165,859 | L −59,752 |

The three heavy losses are the **same agent on three accounts** (byte-identical
hire spend, headcount curve, land days, planting schedule and 1.12 moves per
useful action — also identical to Ben Hamilton's rank-3 profile). We are 0/3
against it and 5/2 against everything else.

The v2 hauling fix is confirmed: **0 truncated end-of-day drops in 10/10 games**
(opponents 0-10 per game), 0 wasted no-ops, 0 animal deaths.

The deficit is smaller than it first looked: **$3,208/game on average**, not the
$91,769-across-the-batch revenue gap first reported. That figure came from summing
gross SELL orders, which double-counts agents that round-trip `WHEAT` and
`FERTILIZER` through `BUY_PRODUCT`. Netted, we are *ahead* of the field on market
dollars and the wheat "gap" is a $2,491/game cost difference, not a revenue line.
`analyze.py` now reports a NET column so this cannot recur.

What survives: **45% of our fertilizer destroyed uncollected (~$10.3k/game)** —
fixed in v3-fert — and a strawberry allocation that holds 50% more tiles than the
archetype for the same output.

### v1-herd (55281835) — settled at **910.5**, rank 770 / 2139

The five replays analysed below were all losses, but they were pulled while the
rating was still provisional, so matchmaking was pairing it against opponents
well above its eventual level. Rating settled at 910.5 against ~486 for the
baseline. **Do not read a small early replay sample as the agent's true form** —
pull replays once the rating has stopped moving, and sample wins as well as
losses or the analysis skews toward whatever beat it.

Sampled games (all losses, hence the skew):

| episode | opponent | us | them | margin |
|---|---|---|---|---|
| 90294798 | Rashi Jain07 | 121,336 | 128,467 | −7,131 |
| 90294048 | IsaacJinyu | 94,501 | 99,507 | −5,006 |
| 90295635 | Ertuğrul Özer | 113,314 | 118,310 | −4,996 |
| 90293319 | wataru420 | 99,350 | 120,301 | −20,951 |
| 90297656 | Baran Kucuk | 77,604 | 132,577 | −54,973 |

Revenue was level with the opponents ($735k vs $732k across the batch); the
losses came from spend and from produce destroyed at the end-of-day shed drop.
Full analysis in `REPLAY_ANALYSIS_CHECKLIST.md`.

## Version history

**`v5-pivot`** — prices the opponent's visible pipeline (`rival_pipeline()`) into
the inventory projection used to value crops and animals, at
`RIVAL_SUPPLY_SHARE = 0.25`. Their whole board is visible every turn; we had never
read it. A contested product is now worth less at the margin, so the mix pivots:
against the archetype's 8 cows we build 9 sheep / 6 cows instead of 8/7. **63% win
rate over 60 games** against v4-gate (p≈0.04) — the first change validated on win
rate rather than mean money. Inert against `pass` (nothing to contest). Kept as
`agents/v5_pivot.py`.

**`v4-gate`** — `MIN_PLANT_SCORE = 20`: only plant a tile whose marginal score
clears the gate, dropping wheat/tomato/carrot/late-strawberry and keeping melon and
timely strawberry. Labour is the binding constraint (watering runs 1.00-1.08 per
plant per day all season), so a marginal tile takes water from a better one.
+$3,591/game over 8 paired seed sets, 7/8 positive. Kept as `agents/v4_gate.py`.

**`v3-fert`** — one line: `P_COLLECT_FERT` 45 → 64, moving it from the bottom of
the priority table to just under `P_CARE`. Animal fertilizer is one bool per tile
that the env clears nightly, so a collect that never gets scheduled is destroyed,
not deferred; at priority 45 (below `P_PLANT`) the queue never reached it and 40–45%
of a game's fertilizer expired. Measured **+$7,408/game absolute vs `pass`** over 10
seeds and **88% head-to-head** against v2-haul over 8 seeds, both seats. Fertilizer
missed fell 40% → 1%. Unexpectedly, **moves per useful action improved 1.51 → 1.33**:
the unit is already on the animal tile after `FEED`/`CARE`, so collecting there
removes a return trip. Kept as `agents/v3_fert.py`.

Rejected alongside it: unblocking the early-game livestock cash reserve. It removed
a genuine deadlock (day-0 plantings 11 → 20) but lost $9,940/game, because the
planting allowance then permits more tiles than the crew can water — peak weeds
3 → 24. Full numbers in the backlog's Rejected section.

**`v0-baseline`** — greedy heuristic ranking crops by spot price × yield. Planted
melon almost exclusively, crashed melon to $115, never dug weeds (43 dead tiles),
kept no animals. Collapsed to ~$2k in self-play because both copies crashed the
same market. Kept as `agents/baseline_v0.py`.

**`v1-herd`** — full rewrite. Marginal-price crop valuation against a projected
end-of-season inventory; livestock clustered on the tiles nearest the shed;
price-aware trickle selling; fertilizer on strawberry ticks; labour-capped
planting. Stateless. Kept as `agents/v1_herd.py` (reconstructed from `v2` by
neutralising the v2 changes — functionally equivalent, not byte-identical).

**`v2-haul`** — units ferry produce to the shed mid-day (`PLACE <item> n`, which
deposits one item type and so preserves a rancher's wheat and fertilizer) once
projected shed+carried passes `HAUL_TRIGGER`. Sell pressure now reads shed +
carried rather than the shed alone. Truncated end-of-day drops went 11 → 0 across
three seeds. Also added `LAND_LATEST_DAY = 16` so the 4th quadrant is never
bought too late to repay itself.

Rejected in testing: cutting to 3 quadrants and 11 hands to match ladder
opponents' spend. It saved ~$12k/game and lost slightly more in revenue — see
the findings log. They win on efficiency, not on spending less.
