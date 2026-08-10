"""Independent recomputation of the 'detour factor / tail moves' finding.

Per (episode, player, day, unit) we reconstruct:
  - the realised stop sequence (positions where a NON-no-op tile action happened)
  - the Manhattan floor through that same sequence in that same order
  - moves actually spent, split into pre-last-stop and tail (after last stop)
  - idle turns (PASS / no-op) and reversals

Everything is reported both pooled and per-episode so the sample can be judged.
"""
import glob
import json
import os
import sys
from collections import defaultdict

sys.path.insert(0, "/Users/rohanjain/Kaggle")
import analyze as AZ

MOVES = {"NORTH": (0, -1), "SOUTH": (0, 1), "EAST": (1, 0), "WEST": (-1, 0)}
OPP = {"NORTH": "SOUTH", "SOUTH": "NORTH", "EAST": "WEST", "WEST": "EAST"}


def man(a, b):
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def analyse_episode(path):
    d = json.load(open(path))
    S = d["steps"]
    cfg = dict(AZ.DEFAULT_CONFIG)
    cfg.update(d.get("configuration") or {})
    board = int(cfg["boardSize"])
    tpd = int(cfg["turnsPerDay"])
    names = (d.get("info") or {}).get("TeamNames") or ["?", "?"]
    rewards = d.get("rewards") or [None, None]

    out = []
    for p in (0, 1):
        # unit-day accumulator: key (day, unit_idx)
        seq = defaultdict(lambda: {"spawn": None, "stops": [], "moves": [],
                                   "idle": 0, "noop": 0, "acts": 0,
                                   "move_steps": []})
        for i in range(1, len(S)):
            pre = S[i - 1]
            obs0 = pre[0].get("observation") or {}
            if "farms" not in obs0:
                continue
            farm = obs0["farms"][p]
            priv = (pre[p].get("observation") or {}).get("private") or {}
            act = S[i][p].get("action")
            if not isinstance(act, dict):
                continue
            pre_step = i - 1
            day = pre_step // tpd
            positions = AZ.unit_positions(farm)
            uacts = AZ.unit_actions(act)

            # replicate the interpreter's atomic-PLANT blocking
            demand = defaultdict(int)
            for a in uacts:
                if isinstance(a, list) and len(a) >= 2 and a[0] == "PLANT":
                    demand[a[1]] += 1
            seeds = priv.get("seeds", {}) or {}
            blocked = {c for c, n in demand.items() if n > seeds.get(c, 0)}

            invs = priv.get("inventories") or [{}]
            for u, a in enumerate(uacts):
                if u >= len(positions):
                    break
                pos = positions[u]
                rec = seq[(day, u)]
                if rec["spawn"] is None:
                    rec["spawn"] = pos
                inv = invs[u] if u < len(invs) else {}
                if not isinstance(a, list) or not a:
                    rec["noop"] += 1
                    continue
                op = a[0]
                if op in MOVES:
                    dx, dy = MOVES[op]
                    nx, ny = pos[0] + dx, pos[1] + dy
                    if 0 <= nx < board and 0 <= ny < board:
                        rec["moves"].append((pre_step, op))
                    else:
                        rec["noop"] += 1
                    continue
                if op == "PASS":
                    rec["idle"] += 1
                    continue
                try:
                    reason = AZ.classify(a, pos, inv, farm, priv, board, day, blocked)
                except Exception:
                    reason = "err"
                rec["acts"] += 1
                if reason is None:
                    rec["stops"].append((pre_step, pos))
                else:
                    rec["noop"] += 1

        # aggregate
        agg = {"req": 0, "moves": 0, "tail": 0, "pre_moves": 0, "stops": 0,
               "idle": 0, "noop": 0, "rev": 0, "unitdays": 0,
               "unitdays_nostop": 0, "moves_nostop": 0,
               "unit_turns": 0}
        by_stopcount = defaultdict(lambda: [0, 0, 0])  # nstops -> [req, premoves, unitdays]
        for (day, u), rec in seq.items():
            if rec["spawn"] is None:
                continue
            agg["unitdays"] += 1
            mv = rec["moves"]
            stops = rec["stops"]
            agg["moves"] += len(mv)
            agg["stops"] += len(stops)
            agg["idle"] += rec["idle"]
            agg["noop"] += rec["noop"]
            agg["unit_turns"] += len(mv) + rec["idle"] + rec["noop"] + rec["acts"]
            for a, b in zip(mv, mv[1:]):
                if OPP[a[1]] == b[1]:
                    agg["rev"] += 1
            if not stops:
                agg["unitdays_nostop"] += 1
                agg["moves_nostop"] += len(mv)
                agg["tail"] += len(mv)
                continue
            last_stop_step = stops[-1][0]
            tail = sum(1 for st, _ in mv if st > last_stop_step)
            agg["tail"] += tail
            agg["pre_moves"] += len(mv) - tail
            pts = [rec["spawn"]]
            for _, pos in stops:
                if pos != pts[-1]:
                    pts.append(pos)
            req = sum(man(a, b) for a, b in zip(pts, pts[1:]))
            agg["req"] += req
            k = min(len(stops), 12)
            by_stopcount[k][0] += req
            by_stopcount[k][1] += len(mv) - tail
            by_stopcount[k][2] += 1
        agg["by_stopcount"] = {k: v for k, v in by_stopcount.items()}
        agg["name"] = names[p]
        agg["reward"] = rewards[p]
        agg["episode"] = os.path.basename(path).split(".")[0]
        agg["player"] = p
        agg["tci"] = cfg.get("townCenterSellInterval")
        out.append(agg)
    return out


def main(patterns, label):
    rows = []
    for pat in patterns:
        for f in sorted(glob.glob(pat)):
            rows.extend(analyse_episode(f))
    return label, rows


if __name__ == "__main__":
    label = sys.argv[1]
    _, rows = main(sys.argv[2:], label)
    json.dump(rows, open(f"/private/tmp/claude-501/-Users-rohanjain-Kaggle/42595745-fed2-4e70-8549-75107f5a1ad2/scratchpad/{label}.json", "w"))
    print(label, "episodes*players:", len(rows))
