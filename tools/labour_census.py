"""Unit-turn census: where every farmer/hand turn goes, per day, per player.

Replays the recorded actions against the recorded prior observation using the
real environment's `_apply_unit_action`, so "effective" means the environment
actually changed state -- not that the action looked plausible.
"""
from __future__ import annotations

import json
import os
import sys
from collections import defaultdict
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kaggle_environments.envs.kaggriculture import kaggriculture as K  # noqa: E402

MOVES = {"NORTH", "SOUTH", "EAST", "WEST"}
TILE_OPS = {
    "PLANT", "WATER", "HARVEST", "FERTILIZE", "DIG", "BUILD_COOP",
    "BUILD_PASTURE", "FEED", "COLLECT_FERTILIZER", "CARE",
}
SHED_OPS = {"PICKUP", "DROP", "PLACE"}


def _tile_copy(t: Any) -> Any:
    return dict(t) if isinstance(t, dict) else t


def census(path: str) -> dict:
    """Return per-player unit-turn census for one replay."""
    with open(path) as fh:
        data = json.load(fh)
    cfg = data["configuration"]
    tpd = int(cfg.get("turnsPerDay", 24))
    bs = int(cfg.get("boardSize", 10))
    shed_cap = int(cfg.get("shedCapacity", 100))
    steps = data["steps"]
    n = len(steps)
    names = data["info"]["TeamNames"]

    out = {}
    for p in range(2):
        out[p] = {
            "name": names[p],
            "reward": data["rewards"][p],
            "cfg_tc": cfg.get("townCenterSellInterval"),
            "op": defaultdict(int),          # op -> effective count
            "op_noop": defaultdict(int),     # op -> ineffective count
            "phantom": 0,                    # action issued for a nonexistent hand
            "unassigned": 0,                 # existing unit given no action at all
            "unit_turns": 0,
            "by_day": defaultdict(lambda: defaultdict(float)),
        }

    for i in range(1, n):
        prev = steps[i - 1]
        cur = steps[i]
        step_idx = i - 1
        day = step_idx // tpd
        hour = step_idx % tpd
        for p in range(2):
            o = prev[p]["observation"]
            if "farms" not in o:
                continue
            farm = o["farms"][p]
            private = o["private"]
            rec = out[p]
            dd = rec["by_day"][day]

            n_units = 1 + len(farm.get("hands", []))
            dd["unit_turns"] += n_units
            rec["unit_turns"] += n_units
            dd["money_last"] = farm["money"]

            # ---- observation-derived state stats, at the last turn of the day
            if hour == tpd - 1:
                plants = watered = 0
                animals = fed = cared = 0
                weeds = 0
                owned = 0
                empty = 0
                per_crop = defaultdict(int)
                for row in farm["tiles"]:
                    for t in row:
                        if t == "LOCKED":
                            continue
                        owned += 1
                        if t is None:
                            empty += 1
                            continue
                        if not isinstance(t, dict):
                            continue
                        k = t.get("kind")
                        if k == "PLANT":
                            plants += 1
                            per_crop[t["crop"]] += 1
                            if t.get("watered_today"):
                                watered += 1
                        elif k == "WEED":
                            weeds += 1
                        if "animal" in t:
                            animals += 1
                            if t.get("fed_today"):
                                fed += 1
                            if t.get("cared_today"):
                                cared += 1
                dd["plants"] = plants
                dd["watered"] = watered
                dd["animals"] = animals
                dd["fed"] = fed
                dd["cared"] = cared
                dd["weeds"] = weeds
                dd["owned_tiles"] = owned
                dd["empty_tiles"] = empty
                dd["hires_today"] = farm.get("hires_today", 0)
                dd["quadrants"] = len(farm.get("unlocked_quadrants", []))
                for c, v in per_crop.items():
                    dd["crop_" + c] = v

            # ---- replay the actions
            act = cur[p].get("action") or {}
            if not isinstance(act, dict):
                act = {}
            farmer_a = act.get("farmer", ["PASS"])
            hands_a = act.get("hands", [])
            if not isinstance(hands_a, list):
                hands_a = []
            unit_actions = [farmer_a, *hands_a]

            plant_demand = defaultdict(int)
            for a in unit_actions:
                if isinstance(a, list) and len(a) >= 2 and a[0] == "PLANT":
                    plant_demand[a[1]] += 1
            seeds = private.get("seeds", {})
            blocked = {c for c, k in plant_demand.items() if k > seeds.get(c, 0)}

            if len(unit_actions) > n_units:
                rec["phantom"] += len(unit_actions) - n_units
                dd["phantom"] += len(unit_actions) - n_units
            if len(unit_actions) < n_units:
                rec["unassigned"] += n_units - len(unit_actions)
                dd["unassigned"] += n_units - len(unit_actions)

            for idx in range(min(len(unit_actions), n_units)):
                a = unit_actions[idx]
                if isinstance(a, list) and len(a) >= 2 and a[0] == "PLANT" and a[1] in blocked:
                    rec["op_noop"]["PLANT_BLOCKED"] += 1
                    dd["op_PLANT_BLOCKED_noop"] += 1
                    continue
                op = a[0] if isinstance(a, list) and a else "NONE"
                pos = K._farmer_position(farm, idx)
                if pos is None:
                    rec["phantom"] += 1
                    continue
                fx, fy = pos[0], pos[1]
                inv = K._farmer_inventory(private, idx)
                if op in MOVES:
                    K._apply_unit_action(farm, private, idx, a, bs, day, tpd, shed_cap)
                    np_ = K._farmer_position(farm, idx)
                    eff = (np_[0], np_[1]) != (fx, fy)
                elif op == "PASS" or op == "NONE":
                    eff = False
                else:
                    before = (
                        _tile_copy(farm["tiles"][fy][fx]),
                        dict(inv),
                        dict(private["shed"]),
                        dict(private.get("seeds", {})),
                    )
                    K._apply_unit_action(farm, private, idx, a, bs, day, tpd, shed_cap)
                    inv2 = K._farmer_inventory(private, idx)
                    after = (
                        _tile_copy(farm["tiles"][fy][fx]),
                        dict(inv2),
                        dict(private["shed"]),
                        dict(private.get("seeds", {})),
                    )
                    eff = before != after
                key = "op" if eff else "op_noop"
                rec[key][op] += 1
                dd[f"op_{op}" + ("" if eff else "_noop")] += 1

    for p in range(2):
        out[p]["op"] = dict(out[p]["op"])
        out[p]["op_noop"] = dict(out[p]["op_noop"])
        out[p]["by_day"] = {d: dict(v) for d, v in sorted(out[p]["by_day"].items())}
    return out


def main() -> None:
    paths = sys.argv[1:]
    res = []
    for path in paths:
        try:
            c = census(path)
        except Exception as exc:  # noqa: BLE001
            print(f"FAIL {path}: {exc}", file=sys.stderr)
            continue
        for p in (0, 1):
            c[p]["file"] = os.path.basename(path)
            c[p]["player"] = p
            res.append(c[p])
        print(f"done {os.path.basename(path)}", file=sys.stderr, flush=True)
    print(json.dumps(res))


if __name__ == "__main__":
    main()
