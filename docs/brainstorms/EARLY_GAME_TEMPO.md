# Early-Game Planting Stall — Root Cause & Fix Options

## Root Cause

`build_plant_plan()` gates every crop behind a cash floor:

```python
floor = CASH_FLOOR + extra_reserve + burn * min(RUNWAY_DAYS, days_to_cash(crop, day))
if cash - seed < floor:
    continue
```

`extra_reserve` = `LIVESTOCK_RESERVE` (900) whenever `livestock_open` is true — which it is for
almost the entire first 9 days (herd stays at 4-6 animals, cap is 10-12).

Result: the floor sits around **$1,500–3,600**, but early cash hovers at **$250–400**
(animals don't pay out until day 6-8, so nothing is funding the reserve yet).
The agent reserves cash for animals it can't afford to buy, which blocks the crop income
that would let it afford them — a self-imposed deadlock.

## Evidence (replayed against actual game state)

| Day | Cash on hand | Wheat's floor | Tiles planted this turn |
|---|---|---|---|
| 1 | $250 | ~$1,150+ | 0 |
| 4 | $251 | ~$1,300+ | 0 |
| 7 | $330 | ~$1,400+ | 0 |
| 9 | $1,375 | $1,502 | 0 (missed by $127) |
| 10 | $1,891 | $1,502 | 28 |

Labor capacity was never the constraint — 9-13 open planting slots sat idle every turn
for 8.5 straight days. Opponent had both first quadrants at 100% tile use by day 10.

## Fix Options (ranked by how surgical they are)

1. **Delay the reserve until crop income exists.**
   Skip `extra_reserve` entirely until `plants_alive > 0`, or for the first N days.
2. **Scale the reserve to available cash instead of a flat $900.**
   `extra_reserve = min(LIVESTOCK_RESERVE, cash - CASH_FLOOR)` — discourages spending the
   whole balance on seed, but never fully blocks planting.
3. **Lower `LIVESTOCK_RESERVE`.**
   Bluntest option — reduces the block but also weakens the animal-buying pattern the
   reserve was designed to protect.

**Recommended starting point:** Option 1 or 2 — both directly remove the deadlock without
touching the livestock logic that's working fine once cash is flowing.

---

## Review notes (2026-08-06)

Root cause **confirmed** against `main.py:388` and `main.py:1073`, and the symptom
independently reproduced from ladder replay `replays/ladder/v2-haul/90506558.json`:
11 tiles planted day 0, nothing days 1-8, 28 tiles day 10.

One measurement refines the diagnosis: at 4-6 hands the daily burn is only
**$7-20**, so the `burn * min(RUNWAY_DAYS, days_to_cash)` term contributes ~$130
at most. The floor is essentially `CASH_FLOOR + 900` and is flat across days 0-9 —
the reserve is ~78% of it. The diagnosis is right and the runway term is a
red herring.

Both proposed fixes need amending:

* **Option 1** never fires — `plants_alive` is already 11 from day 0, so the
  reserve applies throughout the stall. Needs a realised-income trigger.
* **Option 2** is provably a no-op in the stall region. For `cash < CASH_FLOOR +
  LIVESTOCK_RESERVE` it reduces to `floor = cash + burn·d`, making the test
  `cash - seed >= floor` equivalent to `-seed >= burn·d` — false always. Verified
  at $250 / $330 / $400 / $1,000: byte-identical behaviour to today.

The working form reserves a **fraction** of free cash:
`extra_reserve = min(LIVESTOCK_RESERVE, int(RESERVE_SHARE * max(0, cash - CASH_FLOOR)))`.
At `RESERVE_SHARE = 0.5` wheat clears from $330 while the full reserve still binds
above ~$2,050, leaving the day-0 livestock buy untouched.

Carried into `docs/IMPROVEMENT_BACKLOG.md` as **item #0b**.

## Outcome (2026-08-06, measured)

Implemented as the fractional reserve and measured. **The diagnosis holds; the fix
loses money.** Day-0 plantings went 11 → 20 tiles and days 2 and 4 started planting
again, so the deadlock is real and was removed — but mean money vs `pass` fell from
$153,500 to $143,560.

The reserve was masking a second problem. `allowance = spare // 2 - plants_alive`
budgets two unit-actions per plant per day, which on day 0 permits 20 tiles against
a real crew of 4-5 hands; the cash gate meant that ceiling was never reached, so it
was never tuned. With the cash freed we plant more than we can water and **peak
weeds go 3 → 24**. A plant lost to one missed watering kills the tile for good, and
those losses exceed what the extra plantings earn. Tightening the allowance to
`spare // 3` makes it far worse ($108,309) by starving planting for the rest of the
game.

Moved to **Rejected** in the backlog with the full table. The route back is item #7
— derive headcount and the planting budget from the workload formula, then the
early cash posture can be revisited with a crew that is actually sized to it.

Worth recording: head-to-head against v2-haul the combined change looked like a
**+$31,753 win**; absolute against `pass` it was **−$1,204**. Over-planting denies
the opponent market share, which flatters it. Always run the absolute test.
