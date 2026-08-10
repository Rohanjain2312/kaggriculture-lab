# Kaggriculture

Agent for the Kaggle [Kaggriculture](https://www.kaggle.com/competitions/kaggriculture)
simulation competition — two players each run a farm for a 30-day season
(720 turns) and the one with more money at the end wins. **Only win/loss counts;
the margin is irrelevant.** Top 10 are paid, so the target is a consistently
above-average agent rather than a high-variance one.

## Status

| | |
|---|---|
| submitted | `55281835` — score **600.0**, rank ~1220 / 2070 |
| previous | `55256605` (467.3), `55256285` (492.3) |
| local form | beats `pass` / `random` / `starter` / `baseline_v0` **100%** over 48 games |
| typical score | $135k–147k per seed (baseline agent: $28k) |
| entry deadline | 2026-09-30 |

Ratings start at a provisional 600 and take many episodes to settle, so the
current number is a starting point rather than a result.

## Layout

```
main.py                      the agent — single file, submission-ready
bench.py                     win rate / money / timing vs an opponent panel (+ --trace)
sweep.py                     tune constants head-to-head against a frozen reference
analyze.py                   replay post-mortem (no-op audit, waste, market split)

CLAUDE.md                    working notes and hard-won rules — read before editing
docs/KAGGRICULTURE_SETUP.md      one-time environment setup
docs/KAGGRICULTURE_REFERENCE.md  full game rules, mechanics, commands
docs/REPLAY_ANALYSIS_CHECKLIST.md checklist + findings log for every analysis
docs/IMPROVEMENT_BACKLOG.md      candidate changes, ranked, with what was refuted
docs/SUBMISSIONS.md              submission history and ladder results

agents/baseline_v0.py        the original greedy agent, kept as a benchmark
agents/v1_herd.py            previously submitted versions, kept for A/B
agents/sweep_ref.py          frozen reference for sweep.py
replays/ladder/              our own episodes pulled from Kaggle
replays/top/                 top-agent reference games (we are not in these)
replays/local/               locally generated replays
archive/                     superseded files; nothing here is live
```

## Usage

```bash
source venv/bin/activate
```

Benchmark against the full opponent panel:

```bash
python bench.py main.py --seeds 6
```

Trace one game day by day (money, hands, land, tiles, weeds, animals, shed):

```bash
python bench.py main.py --trace --seed 7
```

Tune a constant by win rate against the frozen reference:

```bash
python sweep.py --seeds 6 "MAX_ANIMALS=12,16,20"
```

Post-mortem a replay:

```bash
python analyze.py replays/ladder/*.json --me 0
```

Submit — **limited to 5/day, only the latest 2 are ranked**:

```bash
kaggle competitions submit kaggriculture -f main.py -m "message"
```

## How the agent plays

The town continuously drains market inventory below the baseline, which raises
prices, and capturing that drain is the whole game. Integrating each price curve
over its end-of-season deficit: strawberry ~$129k, milk ~$99k, wool ~$81k,
against carrot ~$18k. Products also differ sharply in how hard they crash when
oversupplied — melon's glut curve is quadratic, wheat's is nearly flat.

So the agent: prices every planting at the **margin** against everything already
committed (which stops it committing the farm to one crop and then crashing it);
clusters livestock on the tiles nearest the shed, where an animal can be fed,
cared for and harvested without moving; and **trickles produce out** rather than
dumping, holding each sale above a reserve that winds down over the closing days.

It is fully stateless — every decision is recomputed from the observation each
turn, and stability comes from deterministic ordering rather than stored plans.

## Known gaps

- **End-of-day shed overflow destroys produce.** Peak shed+carried reaches
  124/100; one measured day lost 66 melon, 15 strawberry and 6 milk. Units only
  drop at the shed on the final day, so produce accumulates in hand. Worth $10k+.
- **Wool is barely sold** — ends ~300 units below baseline, most of ~$81k of
  depth untouched, because cows outrank sheep until milk saturates.

Both are logged in `docs/REPLAY_ANALYSIS_CHECKLIST.md`.
