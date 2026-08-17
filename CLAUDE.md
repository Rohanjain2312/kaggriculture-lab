# CLAUDE.md — Kaggriculture

Agent for the Kaggle "Kaggriculture" simulation competition. Read
`docs/KAGGRICULTURE_REFERENCE.md` for game rules and `docs/KAGGRICULTURE_SETUP.md`
for environment setup.

## THE ULTIMATE GOAL — beat the opponent, not the money

**Win each individual game against the one opponent sitting across from us.**
Scoring is win/loss per episode: a $1 win scores exactly as much as a $50k win,
and a $200k game lost by $500 scores nothing. Absolute money is a *proxy that
decouples from the objective precisely where games are decided* — in a close
game, +$5k to both sides changes nothing while −$3k to them flips the result.

This is the point we keep drifting away from, and it is the one that matters.
Every analysis, metric and proposed change must answer **"does this turn a loss
into a win against that opponent?"** — not "does this earn more?".

Concretely:
- Analyse the **margin distribution and the mechanism of each loss**, not our
  earnings curve. A change that moves ten −$3k games to +$1k beats one that adds
  $20k to games already won.
- **Opponent-denial counts as profit.** Selling into a market before they do,
  contesting the products their build depends on, and racing them to shop demand
  all score zero on absolute money and full value on the real objective.
- Absolute money vs `pass` stays a **guard** ("did I break it?"), never the
  decision metric. See `docs/ROADMAP.md`.

## Layout

| path | role |
|---|---|
| `main.py` | the agent — single file, submission-ready |
| `bench.py` | win rate / money / timing against an opponent panel, plus `--trace` |
| `sweep.py` | tune constants by playing variants head-to-head against a frozen reference |
| `digest.py` | reduce raw replays (~32 MB each) to ~27 KB digests in `docs/analysis/digests/`; **raw replays are pruned after digesting, the digest is what stays** |
| `analyze.py` | replay post-mortem: no-op audit, wasted motion, market split, fertilizer audit, planting schedule, action mix, opponent reconstruction |
| `tools/margin.py` | **head-to-head post-mortem — what separates winner from loser, paired within-game.** `--focus TEAM` when one agent dominates the corpus. Marks order-derived features `~` (intent, not volume) |
| `tools/ladder.py` | **the decision instrument — real ladder win rate and margin distribution.** `--fetch` refreshes from `ListEpisodes` (reward *is* final money); the band table converts "$Xk of swing" into "+Y points of win rate" |
| `docs/REPLAY_ANALYSIS_CHECKLIST.md` | checklist to work through per analysis — **append new checks to it** |
| `docs/IMPROVEMENT_BACKLOG.md` | candidate changes with evidence + what was already refuted |
| `docs/SUBMISSIONS.md` | one row per submission; snapshot `main.py` to `agents/` when shipping |
| `docs/analysis/` | saved `analyze.py` output per batch — replays are ~26 MB and get pruned, this is what stays |
| `docs/analysis/digests-top10/` | 22 top-cohort episodes at 1.32.6 (2026-08-14), all involving rank 1; source for `panel.py --build` |
| `docs/analysis/digests-ours/` | our own local games, digested, so our build can be compared feature-for-feature against the ladder |
| `docs/brainstorms/` | Rohan's strategy notes; reviewed, then carried into the backlog with the verification appended |
| `agents/baseline_v0.py` | the original greedy agent, kept as a benchmark |
| `replays/` | raw episodes, **pruned once digested** -- see `docs/analysis/digests/` (`index.csv` = one row per player-season). `replays/local/` is locally generated and regenerable |
| `archive/` | superseded files kept for reference, nothing here is live |
| `agents/sweep_ref.py` | frozen reference for `sweep.py` — re-copy after accepting a change |

## Commands

```bash
source venv/bin/activate
```

```bash
python bench.py main.py --seeds 6
```

```bash
python bench.py main.py --trace --seed 7
```

```bash
python sweep.py --seeds 6 "MAX_ANIMALS=12,16,20"
```

```bash
python analyze.py replays/ladder/v2-haul/*.json
```

Set `KAGGRICULTURE_DEBUG=1` to make `agent()` re-raise instead of falling back
to PASS — without it, exceptions are swallowed and look like a passive agent.

## Rules learned the hard way

Evidence for each is in `docs/REPLAY_ANALYSIS_CHECKLIST.md` and `docs/REFUTED.md`
— these are the operating rules, kept short because this file loads every session.

**The environment changes under you — diff it, don't trust a changelog.**
**Current pin: `kaggle-environments==1.32.7`** (2026-08-15). Diffed on arrival:
it is exactly PR #1399 — `hinge` curves for TOMATO/CARROT/EGG (CARROT also takes
`below_target` 0.20 → 1.00) and a `T` argument threaded through `_shape` — and
**nothing else**. `main.py` detects the live curve set per turn, so it needed no
change; verified 0 mismatches over 61,803 price checks against the installed env.

`kaggle-environments` 1.32.6 (2026-08-07) cut town demand hard and the post
described three changes; the source diff showed four. The fourth silently deleted
one of the three mechanics this agent was built around (`PICKUP` no longer no-ops
on LOCKED tiles). **Pin the version, and diff `kaggriculture.py` against the
installed copy after any upgrade.** Config values are now randomised per episode,
so `agent(obs, config)` must read them — nothing about the town may be hardcoded.

**Read the environment source, not the docs.**
`venv/lib/python3.*/site-packages/kaggle_environments/envs/kaggriculture/` is
ground truth, ~1000 lines. Three mechanics that decide the strategy are absent
from the competition docs: the free end-of-day inventory drop, `PICKUP` no-op on
LOCKED tiles, and `shedCapacity` blocking `BUY_PRODUCT`/`BUY_ANIMAL`.

**Optimise win rate, not mean money.** Scoring is win/loss only, so a $1 win
equals a $50k win. Absolute money vs `pass` is a *guard* ("did I break it?"), not
the decision metric. See `docs/ROADMAP.md`.

**The opponent panel is a guard too, not a decision metric.** It reads 98-99%
while the ladder reads 45-55%, because panel agents run a competitor's *build* on
**our** routing — they inherit our own ceiling, so they cannot be stronger than
us. Reconstruction also sees only 52.9% of their planting. Local runs now filter
for *breakage*; `tools/ladder.py` is where a win is demonstrated. That inverts the
cadence — 5 submissions a day instead of hundreds of local games in minutes.

**Measure it; don't reason about it.** Every load-bearing number here was
measured with a throwaway agent or a replay audit. Paper reasoning has been wrong
repeatedly — most expensively a "$148k wheat gap" that was a counting artifact.

**A submission's first ~30 ladder games are inflated.** New submissions enter on a
*descending* provisional rating, so early opponents are weak. v6-curve opened
64.3% against $64.9k opponents and settled at 44.1%; v5-pivot is flat across 182
games, so the ladder is sound and only the early games mislead. **Read a win rate
at ~100 games, and never compare two submissions at different game counts.**

**Beware the six metrics that lie.** Head-to-head flatters production cuts
(making less crashes the shared market less). Gross sells flatter round-trippers
(net `BUY_PRODUCT` against `SELL`). One seed set flatters luck (use paired
comparisons across >= 8). `peak weeds` counts deliberate end-game abandonment
(judge days 2-27). **Order quantities are intent, not volume** — unfilled stock
is re-offered every turn, so cumulative orders over-count; a 2026-08-14 corpus
showed 1,872 fertilizer "sales" from a herd that can produce ~390. Build
conclusions on board state and action counts, which are exact; use order rows for
direction only. This error class has now appeared three times.

**Tune only after the bugs are out, and check what a removed gate was masking.**
`MAX_ANIMALS` optimised to 8 against a counting bug; the true optimum was 16.
Removing the cash reserve exposed a planting allowance that had never bound.
Fixing one limit routinely promotes the next into load-bearing.

**Trace state, don't trust "it ran".** Almost every illegal action silently
no-ops. `bench.py --trace` asserts on weeds, animal deaths and shed level daily.

**Audit what the agent doesn't do.** The largest win found was an absence — 45%
of fertilizer expiring uncollected, visible only as a product line near-zero for
us and large for everyone else.

**An opponent's behaviour is evidence about their optimum, not ours.** Copying
their observable choices has produced three refutations (their spend levels, the
wheat rotation, and their whole build as a package). Their build run with our
machinery earns 18% *less* than ours. Ask what constraint makes their choice
correct before importing it.

**Benchmarks are ~30s per 6-seed run — but only outside iCloud.** The project
must stay out of `~/Desktop` (iCloud-synced): there the same run took 10-15
minutes at 0.3% CPU, blocked on the sync daemon.

## Agent invariants

- `agent` must be the **last callable defined** in `main.py` and no callable may
  be imported at module scope — Kaggle loads a file agent by taking the last
  callable in the module namespace.
- `agent()` must never raise; a crash marks the whole submission `Error`.
- Stateless by design: everything recomputed from `obs` each turn, module-level
  dicts are pure caches. Turn-to-turn stability comes from deterministic sort
  orders.

## Submissions

Limited to **5/day**, and only the latest 2 count. Always confirm with Rohan
before running `kaggle competitions submit`.
