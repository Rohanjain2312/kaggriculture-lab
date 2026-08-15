"""Benchmark harness for Kaggriculture agents.

Usage:
    python bench.py main.py --seeds 5
    python bench.py main.py --opponents starter,agents/baseline_v0.py,self
    python bench.py main.py --trace --seed 7

Win rate (not mean money) is the headline metric because the competition scores
win/loss only -- margin is irrelevant to rating.
"""

from __future__ import annotations

import argparse
import glob
import sys
import time
from collections import Counter
from typing import Any

from kaggle_environments import make

DEFAULT_OPPONENTS = ["pass", "random", "starter", "agents/baseline_v0.py", "self"]
PRODUCTS = ["WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON", "EGG", "MILK", "WOOL", "FERTILIZER"]


def run_episode(agent: str, opponent: str, seed: int, steps: int = 720) -> Any:
    """Run one episode and return the env. `opponent` of 'self' mirrors `agent`."""
    opp = agent if opponent == "self" else opponent
    env = make("kaggriculture", configuration={"episodeSteps": steps, "seed": seed}, debug=True)
    env.run([agent, opp])
    return env


def episode_result(env: Any) -> tuple[str, str, float, float]:
    """Return (status0, status1, money0, money1) for a finished episode."""
    final = env.steps[-1]
    return (final[0].status, final[1].status, float(final[0].reward or 0), float(final[1].reward or 0))


def max_turn_seconds(env: Any, player: int = 0) -> float:
    """Largest per-turn wall time recorded for `player`, or 0.0 if unavailable.

    Takes the seat explicitly: half of every bench run plays our agent from seat
    1, and reading seat 0 there reports the *opponent's* timing.
    """
    best = 0.0
    for entry in getattr(env, "logs", []) or []:
        if isinstance(entry, list) and len(entry) > player and isinstance(entry[player], dict):
            best = max(best, float(entry[player].get("duration") or 0.0))
    return best


def looks_inert(env: Any, player: int) -> bool:
    """True if this seat never issued a real action all game.

    An agent that fails to load or raises at import still reports `status=DONE`
    and simply passes every turn, finishing on its starting money. Status alone
    therefore cannot tell a crashed agent from a bad one -- a broken variant
    reads as "$3,000, terrible idea" rather than as an error. Verified: a
    module-level `raise` produces DONE/DONE with reward 3000.
    """
    for step in env.steps:
        if player >= len(step):
            continue
        action = step[player]["action"]
        if not isinstance(action, dict):
            continue
        farmer = action.get("farmer") or []
        if farmer and farmer[0] != "PASS":
            return False
        if action.get("market"):
            return False
        for hand in action.get("hands") or []:
            if hand and hand[0] != "PASS":
                return False
    return True


# --------------------------------------------------------------------------- #
# Trace
# --------------------------------------------------------------------------- #

def tile_census(farm: dict) -> tuple[Counter, int, int, int]:
    """Return (census, weeds, structures, occupied_structures)."""
    census: Counter = Counter()
    weeds = structures = occupied = 0
    for row in farm["tiles"]:
        for tile in row:
            if tile is None:
                census["empty"] += 1
            elif tile == "LOCKED":
                census["LOCKED"] += 1
            elif tile.get("kind") == "PLANT":
                census[tile["crop"]] += 1
            elif tile.get("kind") == "WEED":
                weeds += 1
            else:  # COOP / PASTURE
                structures += 1
                if tile.get("animal"):
                    occupied += 1
                    census[tile["animal"]] += 1
    return census, weeds, structures, occupied


def trace(agent: str, opponent: str, seed: int, steps: int = 720) -> dict:
    """Print per-day state for player 0 and return summary problem counters."""
    env = run_episode(agent, opponent, seed, steps)
    s0, s1, m0, m1 = episode_result(env)
    days = steps // 24

    print(f"\n=== TRACE {agent} vs {opponent} (seed {seed}) ===")
    print(f"{'day':>3} {'money':>9} {'hnd':>3} {'hire':>4} {'q':>1} "
          f"{'weed':>4} {'anml':>4} {'die':>3} {'shed':>4}  tiles")

    prev_occupied = 0
    prev_structures = 0
    deaths_total = 0
    max_weeds = 0
    max_shed_late = 0

    for day in range(days):
        idx = min(day * 24 + 12, len(env.steps) - 1)  # mid-day: hands are 0 at boundaries
        obs = env.steps[idx][0].observation
        farm = obs["farms"][0]
        priv = obs["private"]
        census, weeds, structures, occupied = tile_census(farm)
        shed_total = sum(priv["shed"].values())

        # An occupied structure going empty without the structure count dropping
        # means the animal starved (we never DIG an occupied structure).
        deaths = max(0, prev_occupied - occupied) if structures >= prev_structures else 0
        deaths_total += deaths
        max_weeds = max(max_weeds, weeds)
        prev_occupied, prev_structures = occupied, structures

        # Shed pressure at hour 23 is what causes end-of-day overflow discards.
        eod = min(day * 24 + 23, len(env.steps) - 1)
        max_shed_late = max(max_shed_late, sum(env.steps[eod][0].observation["private"]["shed"].values()))

        crops = {k: v for k, v in census.items() if k not in ("empty", "LOCKED")}
        print(f"{day:>3} {farm['money']:>9,.0f} {len(farm['hands']):>3} "
              f"{farm['hires_today']:>4} {len(farm['unlocked_quadrants']):>1} "
              f"{weeds:>4} {occupied:>4} {deaths:>3} {shed_total:>4}  {crops}")

    prices = env.steps[-1][0].observation["market"]["prices"]
    inv = env.steps[-1][0].observation["market"]["inventory"]
    print(f"\nfinal: status={s0}/{s1}  money={m0:,.0f} vs {m1:,.0f}  "
          f"{'WIN' if m0 > m1 else 'TIE' if m0 == m1 else 'LOSS'}")
    print(f"prices: { {k: prices[k] for k in PRODUCTS} }")
    print(f"inv-I0: { {k: inv[k] - 10000 for k in PRODUCTS} }")
    print(f"checks: max_weeds={max_weeds}  animal_deaths={deaths_total}  "
          f"max_shed_at_hour23={max_shed_late}/100  max_turn={max_turn_seconds(env):.3f}s")
    return {"deaths": deaths_total, "max_weeds": max_weeds, "max_shed": max_shed_late}


# --------------------------------------------------------------------------- #
# Benchmark
# --------------------------------------------------------------------------- #

def bench(agent: str, opponents: list[str], seeds: list[int], steps: int = 720) -> int:
    """Run agent against each opponent over all seeds. Returns process exit code."""
    print(f"\n=== BENCH {agent}  ({len(seeds)} seeds x {len(opponents)} opponents) ===")
    print(f"{'opponent':<26} {'W-L-T':>9} {'win%':>6} {'mean $':>10} {'opp $':>10} "
          f"{'max turn':>9}  errors")

    any_error = False
    for opp in opponents:
        wins = losses = ties = 0
        mine: list[float] = []
        theirs: list[float] = []
        slowest = 0.0
        errors: list[str] = []
        # Play both seats. Two identical agents in one market diverge
        # chaotically, so a mirror scored from seat 0 alone reads as a sweep
        # either way when the real gap is a fraction of a percent.
        rival = agent if opp == "self" else opp
        games = [(seed, flip) for seed in seeds for flip in (False, True)]
        for seed, flip in games:
            t0 = time.perf_counter()
            env = run_episode(rival if flip else agent, agent if flip else rival, seed, steps)
            wall = time.perf_counter() - t0
            s0, s1, m0, m1 = episode_result(env)
            seat = 1 if flip else 0
            if s0 != "DONE" or s1 != "DONE":
                errors.append(f"seed{seed}:{s0}/{s1}")
                any_error = True
            elif looks_inert(env, seat):
                # Not a bad result -- a broken one. Loud, because it otherwise
                # reads as a plausible "this idea is terrible" number.
                errors.append(f"seed{seed}:INERT(agent never acted)")
                any_error = True
            mine.append(m1 if flip else m0)
            theirs.append(m0 if flip else m1)
            slowest = max(slowest, max_turn_seconds(env, seat) or wall / max(1, steps))
            if mine[-1] > theirs[-1]:
                wins += 1
            elif mine[-1] < theirs[-1]:
                losses += 1
            else:
                ties += 1
        rate = 100.0 * (wins + 0.5 * ties) / len(games)
        print(f"{opp:<26} {wins}-{losses}-{ties:<5} {rate:>5.0f}% "
              f"{sum(mine)/len(mine):>10,.0f} {sum(theirs)/len(theirs):>10,.0f} "
              f"{slowest:>8.3f}s  {','.join(errors) if errors else '-'}")

    return 1 if any_error else 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("agent", nargs="?", default="main.py")
    ap.add_argument("--opponents", default=",".join(DEFAULT_OPPONENTS))
    ap.add_argument("--seeds", type=int, default=3)
    ap.add_argument("--seed", type=int, default=7, help="seed used by --trace")
    ap.add_argument("--steps", type=int, default=720)
    # Disjoint seed sets, for measuring how much of a result is seed noise:
    # the same agent run at several offsets gives the spread a real difference
    # has to clear.
    ap.add_argument("--seed0", type=int, default=7, help="first seed of the set")
    ap.add_argument("--trace", action="store_true")
    ap.add_argument("--trace-opponent", default="starter")
    args = ap.parse_args()

    if args.trace:
        trace(args.agent, args.trace_opponent, args.seed, args.steps)
        return 0

    seeds = [args.seed0 + 13 * i for i in range(args.seeds)]
    opponents = []
    for o in args.opponents.split(","):
        if o == "panel":
            # every scripted rival built by panel.py from replay digests
            opponents += sorted(glob.glob("agents/panel_*.py"))
        elif o:
            opponents.append(o)
    return bench(args.agent, opponents, seeds, args.steps)


if __name__ == "__main__":
    sys.exit(main())
