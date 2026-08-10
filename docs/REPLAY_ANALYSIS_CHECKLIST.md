# Replay Analysis Checklist

Working checklist for post-mortems on Kaggriculture episodes. Run `analyze.py`
first, then walk this list. **Append any new check discovered during an analysis
to the relevant section, and log the finding at the bottom.** The value of this
file is that it accumulates — a check only has to be thought of once.

## Collecting replays

```bash
kaggle competitions submissions kaggriculture
```

```bash
kaggle competitions episodes <SUBMISSION_ID> -v
```

```bash
kaggle competitions replay <EPISODE_ID> -p ./replays/ladder/<version>
```

Replays land as `episode-<id>-replay.json`; rename to `<id>.json`. One folder per
agent version (`replays/ladder/v2-haul/`) — mixing versions makes a batch
uninterpretable. Take the **most recent** episodes: a submission starts at a
provisional 600 and is matched against the wrong tier until it settles, so early
episodes describe a different opponent distribution.

Take **wins and losses in the same batch**. The v1 analysis sampled five losses
and concluded the agent was structurally behind; the settled v2 sample was 5-5.
A loss against a strong agent is worth more than five wins against weak ones, but
a loss-only sample cannot tell you which is which. Pull `kaggle competitions logs
<EPISODE_ID> <0|1>` only when an episode errored or timed out — logs carry
stdout/stderr and per-turn duration, nothing strategic.

## Running

```bash
python analyze.py replays/ladder/v2-haul/*.json
```

Save the output to `docs/analysis/<version>_<source>_<date>.txt` — the replays are
~26 MB each and get pruned, the analysis is what stays.

`--me` marks which seat is ours (omit if unknown; both are analysed either way).
To analyse a local game, dump one with `env.toJSON()` into `replays/local/`.

---

## 1. Config sanity — do this first

- [ ] Config matches SDK defaults; `analyze.py` prints a loud warning if not.
- [ ] `marketParams` absent. **If it is ever overridden, the price model in
      `main.py` and every tuned constant are calibrated to the wrong game** —
      stop and recalibrate before reading anything else.

*Verified 2026-08-05: live config matches defaults exactly, marketParams absent.*

## 2. Wasted motion

- [ ] `moves per useful action` vs opponent. Ours ~1.5; the $60k replay winner
      also ran 1.53, a weak melon agent ran 0.88. Below ~1.2 is good.
- [ ] `wasted no-ops` — should be **0**. Any non-zero value is a straight bug;
      the breakdown names the exact guard that rejected the action.
- [ ] `move reversals` — units flip-flopping between targets. Ours 27 vs an
      opponent's 114. Rising numbers mean `MOVE_PENALTY` needs raising.
- [ ] `idle (PASS)` by phase. Early-game idling is expected (little to do);
      late-game idling means the crew is oversized or work is mis-prioritised.

## 3. Silent failures

- [ ] `animal deaths` — must be **0**. Two missed feeds loses the animal permanently.
- [ ] `peak weeds` — **but only before day 28.** The agent deliberately stops
      watering in the last two days, because a plant that cannot yield again is
      not worth an action, and those tiles weed over on purpose. Measured across
      the v3 batch, weeds sit at **0.0-0.8 through day 27 and jump to 15.7 on day
      28**. The headline "peak weeds 12-22" is almost entirely that intentional
      abandonment, not lost production. Judge weeds on days 2-27 only.
- [ ] **`WATER` actions per living plant per day — must be ≥ 1.0.** A plant needs
      watering every day or it weeds, so this ratio is the real labour constraint
      and it is directly observable. Measured for v3-fert over 10 games:

      | days | water/plant | mean weeds |
      |---|---|---|
      | 0-18 | 0.98-1.07 | 0.0-0.3 |
      | **19-21** | **0.76-0.98** | 0.4-0.8 |
      | 22-27 | 1.03-1.08 | 0.4-0.8 |
      | 28-29 | 0.36-0.63 | 10-16 (intentional) |

      The crew is sized almost exactly right — riding 1.00-1.08 all season is good
      calibration, not luck. The only genuine squeeze is **days 19-21**, and it
      costs under one tile.
- [ ] **`peak shed+carried` vs capacity.** Measure shed **plus everything units
      are holding**, at *every* hour, not just hour 23 — units harvest heavily in
      the closing hours. Anything over 100 is produce destroyed at end of day.
- [ ] `days shed hit capacity` — a shed sitting at exactly 100 at the start of a
      day proves the drop was truncated.
- [ ] `market orders dropped` past the 10/turn cap, and *what* got dropped.
- [ ] Stranded inventory at game end — scores $0.
- [ ] **`fertilizer missed`** — animal fertilizer is one bool per animal tile that
      the env **resets daily**, so anything uncollected at hour 23 is destroyed,
      not banked. Good agents miss 4-10%; we missed **45%** in the v2 batch,
      ~$10k/game. Anything above ~15% is a priority bug, not a tuning question.
- [ ] Per-turn duration and `remainingOverageTime` drift (only from logs).

## 4. Spend reconciliation — do this before blaming revenue

Hire, land, seed and animal prices are all deterministic, so spend can be
recovered exactly from state transitions and compared per-category against the
opponent. **Run this first.** In the 2026-08-05 batch total revenue was within
0.5% of the opponents' while we lost all five games — the entire gap was spend,
and looking at the market first would have sent the analysis the wrong way.

- [ ] Spend by category, us vs opponent: HIRE / LAND / SEED / ANIMAL / PRODUCT.
- [ ] **Land: how many quadrants, bought on what day.** The 4th costs $4,000 and
      is the farthest from the shed.
- [ ] Utilisation of the last quadrant bought — tiles actually planted, and how
      many days we owned it. Bought after ~day 16 it cannot repay itself:
      strawberry's planting window closes at day 19.
- [ ] Average hands over days 10-29. The fib curve is convex: 11 hands is
      $232/day, 12 is $376, 13 is $609. Each extra hand must earn ~$380/day.
- [ ] Total revenue us vs opponent. If it is level, the loss is spend, full stop.
- [ ] **Reconcile before believing any revenue figure:**
      `implied spend = 3000 + net market revenue - final money`, per player per
      game. It must be **positive** — a negative value proves the revenue estimate
      is wrong, not that the opponent found free money. This caught a bug that had
      been silently inflating our apparent revenue lead by $35k/game.

## 5. Market behaviour

- [ ] **Read the NET column, never gross sells.** `WHEAT` and `FERTILIZER` are the
      only items `BUY_PRODUCT` accepts, and some agents round-trip them dozens of
      times per turn. The env quotes the buy at post-buy inventory so the cash
      nets to ~zero, but a gross sell tally credits the full sale every time.
      This produced a phantom "$148k wheat gap" in the first v2 analysis and sent
      a whole work item down the wrong path. `analyze.py` now prints
      `bought ... -> NET` for any item with buy-backs; if that column is present,
      the gross number on the left is meaningless on its own.
- [ ] Revenue split by product. Ours is roughly milk 36% / strawberry 31% /
      melon 16% / wool 9%.
- [ ] Realised average price per product vs what the curve allowed. Melon at
      ~$166 avg means we are still pushing it down the quadratic glut side.
- [ ] Capture share of the town's drain per product, us vs them. **Wool is the
      known gap** — ends ~300 below I0, i.e. most of ~$81k of depth unsold.
- [ ] Anything sold below its base price (sign the reserve is too loose).

## 5b. Planting schedule and throughput

`analyze.py` prints a per-day planting census for both players. This is where the
strategic difference between two agents is most visible, because it shows *when*
tiles were committed and to what.

- [ ] **Day 0 tile count.** The top agents plant 19 tiles on day 0; we plant 11.
- [ ] **Gaps.** Ours had a dead zone from day 1 to day 8 and again day 15-19.
      Every empty day is a tile-day of production that cannot be recovered.
- [ ] **Wheat rotation.** Wheat is `first_yield 2 / max_yield 4 / max 6 units /
      $10 seed`, one-shot. A 7-tile block replanted every 4 days runs the whole
      game. Top agents plant wheat on days 0, 4, 8, 12, 16, 20, 22-27.
- [ ] **Crop-per-tile efficiency.** Compare units sold against tiles held. In the
      v2 batch we ran 33-35 strawberry tiles to their 23 and sold the *same*
      number of strawberries — a sign of tiles planted too late to yield.
- [ ] Action mix (`water/harvest/plant/...`). Equal watering with 25% fewer
      harvests means the crop mix, not the labour, is the constraint.

## 6. Opponent reconstruction

Replays record each player's own `private` block, so the opponent's shed, seeds
and per-unit inventories are all readable — not just their tiles.

- [ ] Crop mix and planting schedule; herd size and composition; hands per day;
      when they bought land.
- [ ] Anything we have never tried: goose/egg economies, tomato-heavy play,
      buying fertilizer, deliberately withholding stock to let a price recover,
      taking the 4th quadrant, or a very different opening.
- [ ] Their money curve vs ours — *where* the gap opened, not just that it did.

## 7. Meta

- [ ] Win rate against opponent rating; do losses cluster against one style?
- [ ] Rating trajectory — a new submission starts at a provisional 600 and takes
      many episodes to settle. Don't over-read early numbers.

---

## Findings log

Kept as *lessons*, not a diary — full per-batch output lives in `docs/analysis/`.
Each entry is here because it changed how we measure, not just what we found.

### Measurement traps (all of these produced a confident wrong answer)

**Replay indexing is off by one.** A replay pairs each action with the
observation it *produced*. Judge an action against `steps[i-1]` or every
successful action looks like a no-op.

**Gross sells double-count round-trippers.** `WHEAT` and `FERTILIZER` can be
bought back, and strong agents round-trip them constantly. Counting SELL alone
invented a "$148k wheat gap" that survived a full write-up and became the
top-ranked backlog item. `analyze.py` now prints a NET column — read that.

**Pre-action shed under-counts opponents' sales.** Units act *before*
`_process_market`, so anything dropped at the shed that turn is sellable that
turn. Reading the pre-action shed zeroed 77 of one opponent's 162 SELL orders and
made our revenue lead look like +$35k/game when we were level. Fixed 2026-08-07.

**Always reconcile:** `implied spend = 3000 + net revenue - final money` must be
positive for every player in every game. A negative value proves the revenue
estimate is broken. This is what caught the bug above.

**A one-sided sample describes whatever beat you.** Five v1 losses said "the gap
is spend, not revenue"; the balanced v2 sample (5W-5L) inverted it completely —
spend was within $900 of the agent beating us. Sample wins *and* losses, and only
after the rating settles.

**One seed set is not a result.** `MIN_PLANT_SCORE` measured +$9,784 on seed 7
and +$1,732 across ten seed sets. Paired comparisons on identical seeds are far
more sensitive than comparing means across different ones.

### What the metrics actually mean

**`peak weeds` is misleading.** The agent deliberately stops watering on days
28-29, because a plant that cannot yield again is not worth an action, and those
tiles weed over on purpose. Weeds sit at 0.0-0.8 through day 27 and jump to ~16
on day 28. **Judge weeds on days 2-27 only.**

**Watering coverage is the real labour constraint.** `WATER` per living plant per
day must be >= 1.0 or tiles die. Measured across v3-fert: 0.98-1.07 all season,
dipping to 0.76-0.98 on days 19-21. The crew is calibrated tightly — that is why
adding or cutting hands both measure as no better.

**Fertilizer is destroyed nightly if uncollected.** One bool per animal tile,
reset daily. We were losing 40-55% (~$10k/game) because `P_COLLECT_FERT` sat
below `P_PLANT`. Fixed in v3-fert; now 0-4%. This was the single largest win
found so far, and it was an *absence* — no bug, no no-op, just a product line
near-zero for us and large for everyone else.

### About the top archetype

Its build is **fully deterministic** — hands per day, land days, herd and planting
schedule byte-identical across three accounts, three opponents and three seeds.
Reconstructed as `agents/archetype.py`.

**Its build is not its edge.** That same build run with our machinery earns
$132,770 against `pass`, where ours earns $161,673 — 18% *worse*. Yet the real
thing beats us by $44-60k on the ladder. The difference is execution: 1.10 moves
per useful action against our ~1.37. Copying what they build has now been refuted
piece by piece (wheat, 3 quadrants, herd size) and as a whole package.

## Water audit — classify, don't count (added 2026-08-08)

Counting waters per plant per day says nothing. Classify each WATER as:
**critical** (`consecutive_unwatered >= 1`, saves the tile), **paying**
(one-shot inside `(max_yield_day+1)//2 .. max_yield_day`, or ongoing on a
*fertilised* production night), or **dead** (neither). We run 52.8% dead, an
elite agent 0.9%.

Dead waters are **not** a defect to remove — see REFUTED.md, removing them costs
$6,200/game because they fill idle capacity at near-zero travel. Read the ratio
as a **portfolio** diagnostic: a high dead share means too few tiles are in a
paying window, so the fix is the crop mix, not the watering rule.

**A ratio near 1.0 is not evidence the crew is saturated** if dead work is
padding it. Before refuting a hiring or planting change on "no spare capacity",
subtract the dead actions first.

## Version-match before comparing money (added 2026-08-08)

Money is not comparable across `kaggle-environments` versions — 1.32.5 and
1.32.6 differ by ~39% on the same play. `replays/top-cohort/` mixes both. Reading
it unmatched produced "elite agents earn *less* than us"; version-matched they
out-earn us by ~15%. Check the env version in the replay before any $ comparison.

## Identify the opponents before reading margins (added 2026-08-08, corrected)

**Correction: there are no mirror matches in `replays/top-cohort/`.** An earlier
pass claimed 24 of 36 episodes were one agent playing itself and used that to
dismiss the small final margins. Digesting the corpus shows **0 of 72
player-seasons are self-play, across 29 distinct competitors** — the closest
thing to a repeat is `sleepyai.org` at 9 seasons, always against someone else.
The tiny margins are between different people, so whatever explains them, it is
not a mirror. Check `index.csv` (`mirror`, `name`) rather than assuming.

## Use the digests, not the raw replays (added 2026-08-08)

`python digest.py replays/<dir>/*.json` reduces a ~32 MB replay to ~27 KB —
**1066x** across the corpus — keeping per-day money/tiles/herd/shed/plant state,
full action and order counts, the shop draw and the market trajectory. Raw
replays are pruned after digesting; `docs/analysis/digests/` is what stays.

Reading raw replays directly is what made the elite analysis unaffordable: 32 MB
files x a fan-out of agents burned ~2M tokens and returned findings that did not
survive testing. Query `index.csv` first; open a per-episode digest only for
detail it does not carry.
