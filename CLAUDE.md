# CLAUDE.md — Kaggriculture

Agent for the Kaggle "Kaggriculture" simulation competition. Read
`docs/KAGGRICULTURE_REFERENCE.md` for game rules and `docs/KAGGRICULTURE_SETUP.md`
for environment setup.

## Layout

| path | role |
|---|---|
| `main.py` | the agent — single file, submission-ready |
| `bench.py` | win rate / money / timing against an opponent panel, plus `--trace` |
| `sweep.py` | tune constants by playing variants head-to-head against a frozen reference |
| `digest.py` | reduce raw replays (~32 MB each) to ~27 KB digests in `docs/analysis/digests/`; **raw replays are pruned after digesting, the digest is what stays** |
| `analyze.py` | replay post-mortem: no-op audit, wasted motion, market split, fertilizer audit, planting schedule, action mix, opponent reconstruction |
| `docs/REPLAY_ANALYSIS_CHECKLIST.md` | checklist to work through per analysis — **append new checks to it** |
| `docs/IMPROVEMENT_BACKLOG.md` | candidate changes with evidence + what was already refuted |
| `docs/SUBMISSIONS.md` | one row per submission; snapshot `main.py` to `agents/` when shipping |
| `docs/analysis/` | saved `analyze.py` output per batch — replays are ~26 MB and get pruned, this is what stays |
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

**Measure it; don't reason about it.** Every load-bearing number here was
measured with a throwaway agent or a replay audit. Paper reasoning has been wrong
repeatedly — most expensively a "$148k wheat gap" that was a counting artifact.

**Beware the four metrics that lie.** Head-to-head flatters production cuts
(making less crashes the shared market less). Gross sells flatter round-trippers
(net `BUY_PRODUCT` against `SELL`). One seed set flatters luck (use paired
comparisons across >= 8). `peak weeds` counts deliberate end-game abandonment
(judge days 2-27).

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
