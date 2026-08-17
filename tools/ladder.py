"""Win rate and margin distribution of our real ladder games -- the decision metric.

The opponent panel is a guard, not a decision metric: panel agents run a
competitor's *build* on our own routing, so they inherit our ceiling and read
98-99% while the ladder reads 45-55%. See `docs/REFUTED.md`. This is the
replacement instrument, and it measures the only thing that scores.

It is also nearly free. `ListEpisodes` returns each agent's `reward`, and reward
*is* final money -- verified exactly on 210/210 player-seasons against the
digests. So a full margin distribution costs one API call per submission and no
replay downloads at all.

    python tools/ladder.py --fetch                 # refresh from Kaggle
    python tools/ladder.py                         # report from cache

The report is a *recoverable* table rather than a win rate: for each margin band
it shows what our win rate would become if changes worth that much swing landed.
That is the roadmap -- it converts "this change is worth $Xk" into "this change
is worth Y points of win rate", which is the number that scores.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import statistics
import time
import urllib.error
import urllib.request
from typing import Any

OUR_TEAM = 16664249  # "Rohan Jain"
CACHE = "docs/analysis/ladder_episodes.json"
LIST_URL = ("https://www.kaggle.com/api/i/competitions.EpisodeService/ListEpisodes")
REPLAY_URL = "https://www.kaggle.com/competitions/episodes/{}/replay.json"
PACE = 25  # ListEpisodes is aggressively rate-limited; 429 costs ~40 minutes

# label -> submission id. Append on every ship; see docs/SUBMISSIONS.md.
SUBMISSIONS: list[tuple[str, int]] = [
    ("v5-pivot", 55340305),
    ("v6-curve", 55518009),
    ("v6-curve-r2", 55560444),
    ("v7-fert", 55567649),
    ("v8-gate", 55585462),
]

BANDS: list[tuple[int, float]] = [
    (0, 1_000), (1_000, 3_000), (3_000, 7_000),
    (7_000, 15_000), (15_000, 30_000), (30_000, math.inf),
]


def _token() -> str:
    """The Kaggle bearer token, which the CLI stores separately from kaggle.json."""
    with open(os.path.expanduser("~/.kaggle/access_token")) as fh:
        return fh.read().strip()


def list_episodes(submission_id: int, tries: int = 8) -> dict[str, Any]:
    """Every episode for one submission, backing off on the 429 rate limit."""
    body = json.dumps({"submissionId": submission_id}).encode()
    for attempt in range(tries):
        req = urllib.request.Request(
            LIST_URL, data=body,
            headers={"Content-Type": "application/json",
                     "User-Agent": "Mozilla/5.0",
                     "Authorization": f"Bearer {_token()}"})
        try:
            with urllib.request.urlopen(req, timeout=180) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as exc:
            if exc.code != 429:
                raise
            wait = 60 * (attempt + 1)
            print(f"    429 -> sleep {wait}s", flush=True)
            time.sleep(wait)
    raise RuntimeError(f"gave up listing episodes for {submission_id}")


def episode_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """One row per completed episode we played, with both sides' final money."""
    names = {t["id"]: t.get("teamName") for t in payload.get("teams", [])}
    rows = []
    for ep in payload.get("episodes", []):
        if ep.get("state") != "COMPLETED":
            continue
        us = them = None
        for agent in ep.get("agents", []):
            if agent.get("teamId") == OUR_TEAM:
                us = agent
            else:
                them = agent
        if not us or not them:
            continue
        if us.get("reward") is None or them.get("reward") is None:
            continue
        rows.append({
            "episode_id": ep["id"],
            "create_time": ep.get("createTime", ""),
            "ours": us["reward"],
            "theirs": them["reward"],
            "seat": us.get("index", 0),
            "opp_team": them.get("teamId"),
            "opp_name": names.get(them.get("teamId")),
            "our_score": us.get("updatedScore"),
        })
    return rows


def fetch(force: bool = False) -> dict[str, Any]:
    """Refresh the episode cache, skipping submissions already stored."""
    cache: dict[str, Any] = {}
    if os.path.exists(CACHE) and not force:
        with open(CACHE) as fh:
            cache = json.load(fh)
    for label, sub in SUBMISSIONS:
        if label in cache and not force:
            print(f"  {label}: {len(cache[label]['episodes'])} cached", flush=True)
            continue
        rows = episode_rows(list_episodes(sub))
        cache[label] = {"submission_id": sub, "episodes": rows}
        os.makedirs(os.path.dirname(CACHE), exist_ok=True)
        with open(CACHE, "w") as fh:
            json.dump(cache, fh, ensure_ascii=False, indent=1)
        print(f"  {label}: {len(rows)} completed episodes", flush=True)
        time.sleep(PACE)
    return cache


def band_label(lo: int, hi: float) -> str:
    """`$3k-$7k` / `$30k+`."""
    return f"${lo//1000}k-${int(hi)//1000}k" if hi != math.inf else f"${lo//1000}k+"


def report(label: str, rows: list[dict[str, Any]]) -> None:
    """Win rate plus what each margin band would be worth if it flipped."""
    if not rows:
        print(f"\n=== {label}: no completed episodes")
        return
    wins = [r for r in rows if r["ours"] > r["theirs"]]
    losses = [r for r in rows if r["ours"] < r["theirs"]]
    ties = len(rows) - len(wins) - len(losses)

    print(f"\n=== {label}   {len(rows)} games   "
          f"{len(wins)}W-{len(losses)}L-{ties}T   {100*len(wins)/len(rows):.1f}%")
    print(f"    money: ours ${statistics.mean(r['ours'] for r in rows):,.0f}   "
          f"theirs ${statistics.mean(r['theirs'] for r in rows):,.0f}")
    print(f"    {'margin':<12}{'losses':>7}{'wins':>6}   if a swing this size landed")

    recovered = 0
    for lo, hi in BANDS:
        n_loss = sum(1 for r in losses if lo <= r["theirs"] - r["ours"] < hi)
        n_win = sum(1 for r in wins if lo <= r["ours"] - r["theirs"] < hi)
        recovered += n_loss
        rate = 100 * (len(wins) + recovered) / len(rows)
        print(f"    {band_label(lo, hi):<12}{n_loss:>7}{n_win:>6}   -> {rate:5.1f}%")

    if losses:
        print(f"    median loss margin "
              f"${statistics.median(r['theirs'] - r['ours'] for r in losses):,.0f}")
    if wins:
        print(f"    median win  margin "
              f"${statistics.median(r['ours'] - r['theirs'] for r in wins):,.0f}")


def seat_split(rows: list[dict[str, Any]]) -> None:
    """Seat 0 acts before seat 1 each turn (env line ~913), so check for a bias.

    Measured 2026-08-17 and it did not hold: a 16-point gap in one 182-game
    submission reversed sign in the next, pooled p = 0.07, and the env builds
    both farms identically. Kept because the check is one line and the
    turn-order asymmetry is real even if its effect is not.
    """
    for seat in (0, 1):
        sub = [r for r in rows if r.get("seat", r.get("our_seat", 0)) == seat]
        if not sub:
            continue
        wins = sum(1 for r in sub if r["ours"] > r["theirs"])
        print(f"    seat {seat}: {wins:>3}/{len(sub):<4} {100*wins/len(sub):5.1f}%")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--fetch", action="store_true", help="refresh from Kaggle")
    ap.add_argument("--force", action="store_true", help="re-fetch cached rows too")
    ap.add_argument("--seats", action="store_true", help="also show the seat split")
    args = ap.parse_args()

    if args.fetch or args.force:
        cache = fetch(force=args.force)
    elif os.path.exists(CACHE):
        with open(CACHE) as fh:
            cache = json.load(fh)
    else:
        print(f"no cache at {CACHE}; run with --fetch")
        return 1

    pooled: list[dict[str, Any]] = []
    for label, _sub in SUBMISSIONS:
        if label not in cache:
            continue
        rows = cache[label]["episodes"]
        report(label, rows)
        if args.seats:
            seat_split(rows)
        pooled.extend(rows)

    if len(cache) > 1:
        seen: dict[int, dict[str, Any]] = {r["episode_id"]: r for r in pooled}
        report("ALL VERSIONS POOLED", list(seen.values()))
        if args.seats:
            seat_split(list(seen.values()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
