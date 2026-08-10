"""Build an opponent panel of scripted sparring agents from replay digests.

Every measurement in this project has been made against `pass` (an empty market,
no opponent) or against one of our own past versions (a mirror, which flatters
production cuts and once predicted a 79% win that the ladder scored at +0.3).
Meanwhile we win 40% of real ladder games. This exists to close that gap: a panel
of agents whose *strategy* is copied from real competitors.

    python panel.py --list                 # profiles that can be extracted
    python panel.py --build                # write agents/panel_*.py
    python bench.py main.py --opponents panel

Four things are scripted, because they are the strategic decisions and all four
are visible in a digest: the hiring curve, the land schedule, the herd
composition and the planting schedule. Everything else -- routing, selling,
watering, fertilizer -- stays as `main.py` does it.

**So a panel agent is not a clone of a competitor.** It is that competitor's
*build* run on our machinery. The real ones execute better than we do (they run
~1.14 moves per productive action to our ~1.36), so the panel is a floor on their
strength, not a faithful copy. That is the right trade for our purpose: holding
execution constant is what isolates the strategy being tested.
"""

from __future__ import annotations

import argparse
import collections
import glob
import json
import os
import re
import statistics
from typing import Any

CROPS = ("WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON")
ANIMALS = ("GOOSE", "COW", "SHEEP")
DIGESTS = "docs/analysis/digests"
TEMPLATE = "main.py"
OUT_DIR = "agents"


def load_seasons(version: str = "1.32.6") -> dict[str, list[dict[str, Any]]]:
    """Every player-season from the top-cohort digests, grouped by competitor."""
    by_name: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    for path in sorted(glob.glob(f"{DIGESTS}/*.json")):
        with open(path) as fh:
            d = json.load(fh)
        if version and d.get("module_version") != version:
            continue
        for player in d.get("players", []):
            if player.get("name") and player.get("by_day"):
                by_name[player["name"]].append(player)
    return by_name


def plantings_by_day(season: dict[str, Any]) -> dict[int, dict[str, int]]:
    """Reconstruct plantings from day-over-day increases in the crop census.

    The elite digests predate `digest.py` recording the crop argument on PLANT,
    and the raw replays are pruned, so this is the only route left. It slightly
    under-counts a crop planted and lost within one snapshot interval.
    """
    out: dict[int, dict[str, int]] = {}
    previous: dict[str, int] | None = None
    for row in season["by_day"]:
        current = {c: row["tiles"].get(c, 0) for c in CROPS}
        if previous is not None:
            added = {c: current[c] - previous[c] for c in CROPS
                     if current[c] > previous[c]}
            if added:
                out[row["day"]] = added
        previous = current
    return out


def extract_profile(seasons: list[dict[str, Any]]) -> dict[str, Any]:
    """Median build profile across a competitor's seasons."""
    n_days = max(len(s["by_day"]) for s in seasons)

    hands = []
    for day in range(n_days):
        vals = [s["by_day"][day]["hands"] for s in seasons if day < len(s["by_day"])]
        hands.append(int(round(statistics.median(vals))) if vals else 0)

    land: dict[int, int] = {}
    previous = 1
    for day in range(n_days):
        vals = [s["by_day"][day]["quadrants"] for s in seasons if day < len(s["by_day"])]
        if not vals:
            continue
        want = int(round(statistics.median(vals)))
        if want > previous:
            land[day] = want
            previous = want

    herd: dict[str, int] = {}
    for animal in ANIMALS:
        peak = [max(r["tiles"].get(animal, 0) for r in s["by_day"]) for s in seasons]
        count = int(round(statistics.median(peak)))
        if count:
            herd[animal] = count

    plant: dict[int, list[tuple[str, int]]] = {}
    per_day = [plantings_by_day(s) for s in seasons]
    for day in range(n_days):
        rows = []
        for crop in CROPS:
            vals = [p.get(day, {}).get(crop, 0) for p in per_day]
            count = int(round(statistics.median(vals))) if vals else 0
            if count > 0:
                rows.append((crop, count))
        if rows:
            plant[day] = rows

    return {
        "seasons": len(seasons),
        "mean_money": statistics.mean(s["final_money"] for s in seasons
                                      if s.get("final_money") is not None),
        "hands": hands,
        "land": land,
        "herd": herd,
        "plant": plant,
    }


def slug(name: str) -> str:
    """A filesystem- and import-safe short name."""
    s = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    return (s or "rival")[:18]


def render(name: str, profile: dict[str, Any], template: str) -> str:
    """Inject the script and its four hooks into a copy of the template."""
    src = template

    script = f'''
# --------------------------------------------------------------------------- #
# PANEL OPPONENT -- build copied from "{name}"
# --------------------------------------------------------------------------- #
# Extracted by panel.py from {profile["seasons"]} digested 1.32.6 season(s);
# that competitor averaged ${profile["mean_money"]:,.0f}. Only the four strategic
# decisions below are scripted -- hiring, land, herd and planting. Routing,
# selling, watering and fertilizer stay as main.py does them, so this is their
# *build* on our machinery, not a clone of them. They execute better than we do,
# so treat this as a floor on their strength.
PANEL_NAME = {name!r}
SCRIPT_HANDS = {profile["hands"]!r}
SCRIPT_LAND = {profile["land"]!r}
SCRIPT_HERD = {profile["herd"]!r}
SCRIPT_PLANT = {profile["plant"]!r}
RIVAL_SUPPLY_SHARE = 0.0  # the build is fixed, so do not also adapt it
'''
    anchor = "_CACHE = {}"
    assert anchor in src
    src = src.replace(anchor, script + "\n" + anchor, 1)

    # 1. hiring ---------------------------------------------------------------
    old = ('    target_hands = max(MIN_HANDS, min(MAX_HANDS, '
           '-(-work // ACTIONS_PER_UNIT) - 1))')
    assert old in src, "hiring line not found"
    src = src.replace(
        old, '    target_hands = SCRIPT_HANDS[min(obs["day"], len(SCRIPT_HANDS) - 1)]', 1)

    # 2. land -----------------------------------------------------------------
    old_land = "    if owned >= MAX_QUADRANTS:\n        return budget"
    assert old_land in src, "land gate not found"
    src = src.replace(old_land,
                      "    want = 1\n"
                      "    for _day, _q in sorted(SCRIPT_LAND.items()):\n"
                      "        if obs[\"day\"] >= _day:\n"
                      "            want = _q\n"
                      "    if owned >= want:\n"
                      "        return budget", 1)

    # 3. herd -----------------------------------------------------------------
    old_pick = "    best = None\n    for name, a in ANIMALS.items():"
    assert old_pick in src, "pick_animal loop not found"
    new_pick = ("    have = {}\n"
                "    for _row in farm[\"tiles\"]:\n"
                "        for _t in _row:\n"
                "            if isinstance(_t, dict) and _t.get(\"animal\"):\n"
                "                have[_t[\"animal\"]] = have.get(_t[\"animal\"], 0) + 1\n"
                "    for _n, _want in sorted(SCRIPT_HERD.items()):\n"
                "        if have.get(_n, 0) + int(shed.get(_n, 0)) < _want \\\n"
                "                and budget >= ANIMALS[_n][\"cost\"]:\n"
                "            return _n\n"
                "    return None\n\n"
                "    best = None\n    for name, a in ANIMALS.items():")
    src = src.replace(old_pick, new_pick, 1)

    # 4. planting -------------------------------------------------------------
    old_plan = "    committed = dict.fromkeys(proj, 0)\n    plan = []"
    assert old_plan in src, "plant plan body not found"
    new_plan = ("    _want = SCRIPT_PLANT.get(day, [])\n"
                "    if _want:\n"
                "        _out = []\n"
                "        for _crop, _n in _want:\n"
                "            for _ in range(_n):\n"
                "                if len(_out) >= n_tiles:\n"
                "                    break\n"
                "                _out.append((_crop, P_PLANT + 10))\n"
                "        _CACHE[key] = _out\n"
                "        return _out\n"
                "    _CACHE[key] = []\n"
                "    return []\n\n" + old_plan)
    src = src.replace(old_plan, new_plan, 1)

    src = src.replace('AGENT_VERSION = "v5-pivot"',
                      f'AGENT_VERSION = "panel:{slug(name)}"', 1)
    return src


def strategic_key(profile: dict[str, Any]) -> str:
    """Coarse identity of a build: its land schedule and herd composition.

    Six of the seven competitors with >=2 digested 1.32.6 seasons share these
    exactly, differing only by a hand or two per day -- the top of this ladder
    runs one common script. Grouping on it stops the panel being six copies of
    the same opponent wearing different names.
    """
    return json.dumps({"land": profile["land"], "herd": profile["herd"]},
                      sort_keys=True)


def build_groups(version: str, min_seasons: int) -> list[dict[str, Any]]:
    """One pooled profile per distinct build, most-supported first."""
    by_name = load_seasons(version)
    usable = {n: s for n, s in by_name.items() if len(s) >= min_seasons}
    groups: dict[str, list[str]] = collections.defaultdict(list)
    for name, seasons in usable.items():
        groups[strategic_key(extract_profile(seasons))].append(name)

    out = []
    for names in groups.values():
        pooled = [s for n in names for s in usable[n]]
        profile = extract_profile(pooled)
        profile["members"] = sorted(names)
        profile["label"] = max(names, key=lambda n: len(usable[n]))
        out.append(profile)
    return sorted(out, key=lambda p: -p["seasons"])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--list", action="store_true", help="show extractable builds")
    ap.add_argument("--build", action="store_true", help="write agents/panel_*.py")
    ap.add_argument("--min-seasons", type=int, default=2)
    ap.add_argument("--version", default="1.32.6")
    args = ap.parse_args()

    groups = build_groups(args.version, args.min_seasons)
    if not groups:
        print(f"no competitor has >= {args.min_seasons} seasons on {args.version}")
        return 1

    with open(TEMPLATE) as fh:
        template = fh.read()

    for profile in groups:
        planted = sum(c for rows in profile["plant"].values() for _, c in rows)
        print(f"{slug(profile['label']):<20} {profile['seasons']:>2} seasons "
              f"from {len(profile['members'])} competitor(s)  "
              f"${profile['mean_money']:>8,.0f}")
        print(f"    land {profile['land']}  herd {profile['herd']}  "
              f"{planted} plantings")
        print(f"    {', '.join(profile['members'])}")
        if not args.build:
            continue
        path = os.path.join(OUT_DIR, f"panel_{slug(profile['label'])}.py")
        with open(path, "w") as fh:
            fh.write(render(profile["label"], profile, template))
        print(f"    -> {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
