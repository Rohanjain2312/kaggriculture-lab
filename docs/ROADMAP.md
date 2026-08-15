# Strategy roadmap

**The objective is to out-earn the opponent in each game, not to maximise money.**
The competition scores win/loss only, so a $1 win is worth exactly as much as a
$50k win. Every item below is judged against that.

This file holds *strategic direction* — themes, and why they matter.
`IMPROVEMENT_BACKLOG.md` holds *concrete tuning candidates* with measurements.
When a theme here produces a specific testable change, it goes there.

---

## What that objective changes

Most of this project has been tuned on **mean money against `pass`**, which
measures how much we can extract from an *uncontested* market. That is not the
objective, and in a shared market the two can disagree: producing less crashes
prices less, which can lift both scores or neither.

**So: absolute-vs-`pass` is a guard, not a decision metric.** It answers "did I
break the agent?". Win rate against a *strong, varied* opponent panel answers
"is this better?". We have not had such a panel, which is why mirror-tuning has
repeatedly misled us (see the Rejected list).

A worked example: `MAX_HANDS = 12` won **75% head-to-head** and tied on absolute
money, and was dismissed as a production-cut artifact. Under the correct
objective that dismissal is unproven and should be re-run once the panel exists.

---

## What we can see about the opponent

Verified against the live environment. Every turn, `obs["farms"][1 - player]`
exposes:

| field | meaning |
|---|---|
| `money` | **their exact cash — the running score** |
| `tiles` | every crop, its planted day and growth, animals, structures |
| `hands` | their headcount today |
| `unlocked_quadrants` | their land |
| `hires_today` | hiring activity |

Hidden (their `private` block): shed contents, carried inventory, seed counts.

**The agent currently reads its own farm twice and the opponent zero times.** We
play blind against a fully visible opponent in a game scored purely on relative
outcome. Everything in "Now" below follows from closing that gap.

---

## Now

### 5. An opponent model to measure against — `in progress`
The top archetype is **deterministic**: identical spend to the dollar across six
replays, same build order, same hiring curve, land on days 7 and 11, 8 cows + 6
sheep. That makes it reconstructible as a local agent.

Without it, our opponent panel is `pass`/`random`/`starter` (trivial) plus our own
past versions (mirrors, which are biased). With it we can measure **win rate
against a real strategy**, which is the metric that matters.

*This is the measuring instrument for everything else — hence first.*

### 1. Score-aware risk posture — `REOPENED 2026-08-15`
Only win/loss counts, so the shape of the distribution matters more than its
mean. We can see their money all game and never look at it.

* **Ahead late** → minimise variance: liquidate early, stop speculative planting,
  bank the win.
* **Behind late** → maximise variance: hold stock for a price spike, plant
  aggressively, take the tail. A bigger loss costs nothing extra.

Measured and dead **through the sell reserve** — we already sell ~100% of what we
produce (0 dropped orders, 0-4 units stranded), so there is nothing to unlock. See
REFUTED.md. Only surviving form: estimate standing from *board state* mid-season
and modulate **investment**, not selling. Unbuilt, uncertain.

---

## Next

### 2. Sell timing against the drain schedule — `REFUTED`
The drain is on a **known calendar**, not a guess: shops consume every 4 turns,
the town centre every 12, doubling after day 10 and ×4 after day 20. Each drain
cuts inventory and lifts the price, so price is a predictable sawtooth. We sell
on a price-vs-reserve rule that does not know the calendar — selling just after a
drain rather than just before is free margin.

### 3. Anticipate the opponent's dumps — `REOPENED 2026-08-15`
Melon is non-ongoing with `max_yield_day 12`, so it matures **all at once**, and
their tiles carry `planted_day`. Their dump is forecastable to the day. Sell into
the market ahead of it rather than after.

### 4. Adaptive build sizing — `delivered by item 6, sizing unchanged`
Measured over the latest 10 ladder games: in **losses** we run 15.2 animals and
3.7 quadrants; in **wins**, 13.8 and 3.5. We build the same farm regardless of
the opponent, so when they contest the same products we have overspent ~$5k into
a market we then crash together. Their build is visible from day one.

### 6. Product contention pivot — **`validated`**, in `v5-pivot`
Their pastures, coops and crops are visible immediately. Built as
`RIVAL_SUPPLY_SHARE = 0.25`: their visible pipeline is priced into the inventory
projection, so a contested product is worth less at the margin. **63% win rate over
60 games** against the shipped agent. Against the archetype's 8 cows we shift to
9 sheep / 6 cows — into wool, off contested milk.

This also delivers item 4's substance: *composition* adapts to the opponent. Its
*sizing* half is not needed — herd size re-tuned with the pivot on still prefers
16 (13 → 28%, 16 → 70%, 19 → 70%).

>  **REOPENED 2026-08-15 — the number below was measured in an empty market.**
>  Re-measured on 1.32.6 against real opponents, the reserve **blocks 62-66%** of
>  item-turns and we sell everything on only 28-31% (vs `pass`: 82%). The sell
>  floor is the *dominant* constraint, not a slack one. This voids the stated
>  reason items 1, 2, 3 and 7 were closed — it does not show they work. See
>  REFUTED.md, "the sell-timing family's load-bearing number was wrong".

**All three of the above, plus item 1, died of one cause.** Instrumented over a
full game, we sell everything available on **89.4%** of item-turns holding stock;
the reserve blocks a sale entirely on 7.9% and caps it on 2.8%. **The sell floor
is not a binding constraint**, so no lever that moves it can do much. Measure the
constraint before proposing a fourth timing idea. Details in REFUTED.md.

What survives: changes to **what we produce and grow**, not when we sell it —
items 4 and 6 below.

---

## Later

### 7. The final-day liquidation race — `REFUTED by the same measurement`
Unsold stock scores $0, so both agents dump on day 29 and whoever sells first
gets the better price. We wind our reserve down but do not race them.

### 8. Denial
Because scoring is relative, crashing a product they depend on can be worth more
than the revenue it costs us. Only sensible once we can see their exposure and
measure win rate — it will always look wrong on an absolute-money benchmark.

---

## Origin

Items 1-4 and 6-7 in Rohan's framing, 2026-08-07; the opponent model (5),
score-aware posture (1), contention pivot (6) and denial (8) added in review.
Sequencing agreed: **5, then 1.**
