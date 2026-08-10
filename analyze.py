"""Post-mortem analyzer for Kaggriculture replay JSON.

    python analyze.py replays/ladder/*.json --me 0
    python analyze.py replays/local/*.json

Works through docs/REPLAY_ANALYSIS_CHECKLIST.md. Both players are analysed side by
side, because the most useful signal in a replay is what the opponent did
differently -- a replay records each player's own `private` block, so their
shed, seeds and per-unit inventories are all visible, not just their tiles.

The no-op audit is the centrepiece. Almost every illegal action in this
environment silently does nothing, so a wasted unit-turn is invisible in a
normal run. Rather than diffing state across a step (which would conflate unit
actions with plant decay, the market phase and the day refresh), each action is
tested against the *pre-action* state using the same guard conditions the
interpreter itself applies.
"""

import argparse
import glob
import json
import sys

import main as ag

DEFAULT_CONFIG = {
    "episodeSteps": 720, "boardSize": 10, "startingMoney": 3000,
    "maxMarketOrdersPerTurn": 10, "turnsPerDay": 24, "shedCapacity": 100,
    "weedSpawnChance": 0.005, "townShopUnlockInterval": 3,
    "townShopSellInterval": 4,
    "farmHandCostMult": 1, "actTimeout": 1,
}

MOVES = ("NORTH", "SOUTH", "EAST", "WEST")
OPPOSITE = {"NORTH": "SOUTH", "SOUTH": "NORTH", "EAST": "WEST", "WEST": "EAST"}


# --------------------------------------------------------------------------- #
# Replay access
# --------------------------------------------------------------------------- #

def shared(steps, i, key):
    """Shared observation values live on player 0; fall back across players."""
    for entry in steps[i]:
        obs = entry.get("observation") or {}
        if key in obs and obs[key] is not None:
            return obs[key]
    return None


def unit_positions(farm):
    return [tuple(farm["farmer"])] + [tuple(p) for p in farm.get("hands", [])]


def unit_actions(action):
    if not isinstance(action, dict):
        return []
    hands = action.get("hands") or []
    return [action.get("farmer", ["PASS"])] + list(hands)


# --------------------------------------------------------------------------- #
# No-op detection -- mirrors the interpreter's own guard clauses
# --------------------------------------------------------------------------- #

def classify(act, pos, inv, farm, private, board, day, blocked_crops):
    """Return None if the action does something, else a short reason string."""
    if not isinstance(act, list) or not act:
        return "malformed"
    op = act[0]
    x, y = pos
    tile = farm["tiles"][y][x]

    if op == "PASS":
        return "idle"

    if op in MOVES:
        dx, dy = {"NORTH": (0, -1), "SOUTH": (0, 1), "EAST": (1, 0), "WEST": (-1, 0)}[op]
        if not (0 <= x + dx < board and 0 <= y + dy < board):
            return "move off board"
        return None

    # Every remaining op is a tile op, and the interpreter returns early on
    # LOCKED *before* handling PICKUP/DROP.
    if tile == "LOCKED":
        return "on locked tile"

    shed_adj = ag._is_shed_adjacent(pos, board) if hasattr(ag, "_is_shed_adjacent") \
        else pos in set(ag.shed_tiles(board))
    is_plant = isinstance(tile, dict) and tile.get("kind") == "PLANT"
    is_animal = isinstance(tile, dict) and tile.get("animal")

    if op == "PICKUP":
        if not shed_adj:
            return "pickup away from shed"
        if len(act) < 2 or private["shed"].get(act[1], 0) <= 0:
            return "pickup of empty stock"
        return None

    if op == "DROP":
        if not shed_adj:
            return "drop away from shed"
        if not any(v > 0 for v in inv.values()):
            return "drop with empty hands"
        return None

    if op == "PLANT":
        if len(act) < 2 or act[1] not in ag.CROPS:
            return "malformed"
        if tile is not None:
            return "plant on occupied tile"
        if act[1] in blocked_crops:
            return "plant dropped (seed shortage)"
        if private["seeds"].get(act[1], 0) <= 0:
            return "plant without seed"
        return None

    if op == "WATER":
        if not is_plant:
            return "water on non-plant"
        return "water already watered" if tile["watered_today"] else None

    if op == "HARVEST":
        if not isinstance(tile, dict) or tile.get("yield_units", 0) <= 0:
            return "harvest with no yield"
        if is_plant and day - tile["planted_day"] < ag.CROPS[tile["crop"]]["first_yield_day"]:
            return "harvest before first yield"
        return None

    if op == "FERTILIZE":
        if not is_plant:
            return "fertilize on non-plant"
        return "fertilize without stock" if inv.get("FERTILIZER", 0) <= 0 else None

    if op == "FEED":
        if not is_animal:
            return "feed on non-animal"
        if tile["fed_today"]:
            return "feed already fed"
        return "feed without wheat" if inv.get("WHEAT", 0) <= 0 else None

    if op == "CARE":
        if not is_animal:
            return "care on non-animal"
        return "care already cared" if tile["cared_today"] else None

    if op == "COLLECT_FERTILIZER":
        if not is_animal:
            return "collect on non-animal"
        return None if tile.get("fertilizer_available") else "collect with none ready"

    if op == "DIG":
        if tile is None:
            return "dig on empty tile"
        if is_animal:
            return "dig on occupied structure"
        return None

    if op in ("BUILD_COOP", "BUILD_PASTURE"):
        return "build on occupied tile" if tile is not None else None

    if op == "PLACE":
        if len(act) < 2:
            return "malformed"
        item = act[1]
        if item in ag.ANIMALS:
            structure = ag.ANIMALS[item]["structure"]
            if isinstance(tile, dict) and tile.get("kind") == structure and not is_animal:
                return None if inv.get(item, 0) > 0 else "place without animal"
        if shed_adj:
            return None if inv.get(item, 0) > 0 else "place without stock"
        return "place with no target"

    return None


# --------------------------------------------------------------------------- #
# Per-player analysis
# --------------------------------------------------------------------------- #

def analyze_player(steps, pid, cfg):
    board = int(cfg.get("boardSize", 10))
    tpd = int(cfg.get("turnsPerDay", 24))
    cap = int(cfg.get("shedCapacity", 100))
    max_orders = int(cfg.get("maxMarketOrdersPerTurn", 10))

    s = {
        "noops": {}, "ops": {}, "moves": 0, "useful": 0, "idle": 0,
        "reversals": 0, "orders_dropped": 0, "turns_order_capped": 0,
        "sold_units": {}, "sold_est": {}, "bought_units": {}, "bought_est": {},
        "peak_hands": 0, "peak_animals": 0,
        "animal_deaths": 0, "weeds_seen": 0, "plants_lost": 0,
        "overflow_days": [], "money_by_day": [], "hands_by_day": [],
        "quadrants": 0, "final_money": 0.0, "stranded": {}, "spend": {},
        "max_shed_eod": 0,
        # animal fertilizer is 1 per animal per day and is *lost* if not
        # collected that day (`fertilizer_available` is a bool the env resets),
        # so uncollected-at-hour-23 is money left on the ground, not deferred.
        "fert_animal_days": 0, "fert_missed": 0,
        "plantings": {}, "hire_dollars": 0,
    }
    prev_dir = {}
    prev_occupied = prev_structures = None
    prev_plants = None
    prev_crops = {}
    fert_last_day = -1
    hands_by_day = {}

    # A replay pairs each action with the observation it *produced*, so the
    # state an action was chosen from -- and must be judged against -- is the
    # previous step's. Reading them off the same index makes every successful
    # action look like a no-op (a WATER shows the tile already watered).
    for i in range(len(steps) - 1):
        entry = steps[i][pid]
        obs = entry.get("observation") or {}
        farms = obs.get("farms") or shared(steps, i, "farms")
        market = obs.get("market") or shared(steps, i, "market")
        day = obs.get("day", shared(steps, i, "day") or 0)
        hour = obs.get("hour", shared(steps, i, "hour") or 0)
        if not farms or pid >= len(farms):
            continue
        farm = farms[pid]
        private = obs.get("private") or {"shed": {}, "seeds": {}, "inventories": [{}]}
        inventories = private.get("inventories") or [{}]
        action = steps[i + 1][pid].get("action")

        # --- board census -------------------------------------------------- #
        occupied = structures = plants = weeds = 0
        crops = {}
        for r, row in enumerate(farm["tiles"]):
            for c, t in enumerate(row):
                if isinstance(t, dict):
                    kind = t.get("kind")
                    if kind == "PLANT":
                        plants += 1
                        crops[(r, c)] = t.get("crop") or t.get("plant")
                    elif kind == "WEED":
                        weeds += 1
                    elif kind in ("COOP", "PASTURE"):
                        structures += 1
                        if t.get("animal"):
                            occupied += 1
                            # sampled once per day, at the last hour
                            if hour == tpd - 1 and day != fert_last_day:
                                s["fert_animal_days"] += 1
                                if t.get("fertilizer_available"):
                                    s["fert_missed"] += 1
        if hour == tpd - 1:
            fert_last_day = day
        # a tile whose crop changed since the previous turn was just planted
        for pos, crop in crops.items():
            if prev_crops.get(pos) != crop:
                s["plantings"][(day, crop)] = s["plantings"].get((day, crop), 0) + 1
        prev_crops = crops
        hands_by_day[day] = max(hands_by_day.get(day, 0), len(farm.get("hands", [])))
        s["peak_animals"] = max(s["peak_animals"], occupied)
        s["peak_hands"] = max(s["peak_hands"], len(farm.get("hands", [])))
        s["weeds_seen"] = max(s["weeds_seen"], weeds)
        s["quadrants"] = max(s["quadrants"], len(farm.get("unlocked_quadrants", [])))
        if prev_occupied is not None and structures >= prev_structures:
            s["animal_deaths"] += max(0, prev_occupied - occupied)
        if prev_plants is not None and hour == 0:
            # plants that vanished across a day boundary without being harvested
            s["plants_lost"] += max(0, prev_plants - plants - 1) if weeds else 0
        prev_occupied, prev_structures, prev_plants = occupied, structures, plants

        if hour == tpd // 2:
            s["money_by_day"].append((day, farm["money"]))
            s["hands_by_day"].append(len(farm.get("hands", [])))

        # --- shed pressure --------------------------------------------------- #
        # What gets dropped at end of day is shed + everything the units are
        # holding, and the overflow is destroyed. Units harvest heavily in the
        # closing hours, so peak pressure has to be tracked across every hour --
        # sampling the shed alone, or only at hour 23, badly understates it.
        shed_total = sum(private.get("shed", {}).values())
        carried = sum(sum(v.values()) for v in inventories)
        s["max_shed_eod"] = max(s["max_shed_eod"], shed_total + carried)
        s["peak_carried"] = max(s.get("peak_carried", 0), carried)
        if shed_total >= cap and hour == 0:
            # a full shed at the start of a day means the drop was truncated
            s["overflow_days"].append((day, shed_total + carried - cap))

        if not isinstance(action, dict):
            continue

        # --- unit actions --------------------------------------------------- #
        acts = unit_actions(action)
        positions = unit_positions(farm)
        demand = {}
        for a in acts:
            if isinstance(a, list) and len(a) >= 2 and a[0] == "PLANT":
                demand[a[1]] = demand.get(a[1], 0) + 1
        blocked = {c for c, n in demand.items()
                   if n > private.get("seeds", {}).get(c, 0)}

        for u, a in enumerate(acts):
            if u >= len(positions):
                break
            inv = inventories[u] if u < len(inventories) else {}
            op = a[0] if isinstance(a, list) and a else "?"
            s["ops"][op] = s["ops"].get(op, 0) + 1
            reason = classify(a, positions[u], inv, farm, private, board, day, blocked)
            if reason == "idle":
                s["idle"] += 1
            elif reason is not None:
                s["noops"][reason] = s["noops"].get(reason, 0) + 1
            elif op in MOVES:
                s["moves"] += 1
            else:
                s["useful"] += 1

            if op in MOVES:
                key = (day, u)
                if prev_dir.get(key) == OPPOSITE[op]:
                    s["reversals"] += 1
                prev_dir[key] = op
            else:
                prev_dir.pop((day, u), None)

        # --- market actions -------------------------------------------------- #
        orders = action.get("market") or []
        if len(orders) > max_orders:
            s["orders_dropped"] += len(orders) - max_orders
            s["turns_order_capped"] += 1
        # The interpreter applies every unit action *before* `_process_market`,
        # so anything a unit DROPs or PLACEs at the shed this turn is sellable
        # this turn. Reading the pre-action shed alone zeroed out 77 of one
        # opponent's 162 SELL orders and made their implied spend negative --
        # any agent that deposits and sells in the same turn was undercounted,
        # ours (which sells from stock banked earlier) was not. Replay the
        # deposits onto a working copy first.
        shed = dict(private.get("shed", {}))
        for u, a in enumerate(acts):
            if not (isinstance(a, list) and a) or u >= len(inventories):
                continue
            inv_u = inventories[u]
            if a[0] == "DROP":
                for item, n in inv_u.items():
                    if n > 0:
                        shed[item] = shed.get(item, 0) + n
            elif a[0] == "PLACE" and len(a) >= 2 and a[1] in ag.MARKET_PARAMS:
                n = int(a[2]) if len(a) >= 3 else 1
                n = min(n, inv_u.get(a[1], 0))
                if n > 0:
                    shed[a[1]] = shed.get(a[1], 0) + n
        if sum(shed.values()) > cap:                 # shedCapacity still applies
            over = sum(shed.values()) - cap
            for item in sorted(shed, key=lambda k: -shed[k]):
                cut = min(over, shed[item])
                shed[item] -= cut
                over -= cut
                if over <= 0:
                    break
        for order in orders[:max_orders]:
            if not isinstance(order, list) or not order:
                continue
            kind = order[0]
            if kind == "SELL" and len(order) >= 3 and order[1] in ag.MARKET_PARAMS:
                item = order[1]
                filled = min(int(order[2]), shed.get(item, 0))
                if filled > 0 and market:
                    inv_now = market["inventory"][item]
                    s["sold_units"][item] = s["sold_units"].get(item, 0) + filled
                    s["sold_est"][item] = s["sold_est"].get(item, 0) + \
                        ag.cum_revenue(item, inv_now, filled)
            elif kind in ("BUY_SEED", "BUY_ANIMAL", "BUY_PRODUCT", "HIRE", "BUY_LAND"):
                s["spend"][kind] = s["spend"].get(kind, 0) + 1
                # WHEAT and FERTILIZER can be bought back, and some agents
                # round-trip them dozens of times a turn. Counting SELL alone
                # credits them the gross sale each time; the cash nets to ~zero
                # because the env quotes the buy at post-buy inventory. Track the
                # buy side so the market table can report a net position.
                if (kind == "BUY_PRODUCT" and len(order) >= 3
                        and order[1] in ag.MARKET_PARAMS and market):
                    item = order[1]
                    qty = int(order[2])
                    if qty > 0:
                        inv_now = market["inventory"][item]
                        s["bought_units"][item] = s["bought_units"].get(item, 0) + qty
                        s["bought_est"][item] = s["bought_est"].get(item, 0) + \
                            ag.cum_revenue(item, inv_now - qty, qty)

    # Hiring is re-paid in full every day, and the cost of the n-th hand is
    # fib(n), so the daily bill is recoverable exactly from the headcount.
    s["hire_dollars"] = sum(sum(ag.fib(i) for i in range(n))
                            for n in hands_by_day.values())
    s["hands_early"] = _mean(hands_by_day, range(0, 10))
    s["hands_late"] = _mean(hands_by_day, range(10, 30))

    final = steps[-1][pid]
    s["final_money"] = float(final.get("reward") or 0)
    last_private = (final.get("observation") or {}).get("private") or {}
    s["stranded"] = {k: v for k, v in (last_private.get("shed") or {}).items() if v > 0}
    return s


# --------------------------------------------------------------------------- #
# Report
# --------------------------------------------------------------------------- #

def _mean(by_day, days):
    vals = [by_day.get(d, 0) for d in days]
    return sum(vals) / max(1, len(vals))


def top(d, n=8):
    return sorted(d.items(), key=lambda kv: -kv[1])[:n]


OUR_TEAM = "Rohan Jain"
FOCUS_TEAM = None          # set by --team to study someone else's agent


def detect_seat(data, override):
    """Which seat to mark as the subject. Ladder replays carry `info.TeamNames`."""
    if override is not None:
        return override
    names = (data.get("info") or {}).get("TeamNames") or []
    for target in (FOCUS_TEAM, OUR_TEAM):
        if not target:
            continue
        for i, name in enumerate(names):
            if name == target:
                return i
    return None


def report(path, data, me):
    cfg = data.get("configuration") or {}
    steps = data["steps"]
    rewards = data.get("rewards") or []
    n_players = len(steps[0])
    names = (data.get("info") or {}).get("TeamNames") or []

    print("=" * 78)
    print(f"REPLAY {data.get('id', path)}   ({path})")
    print("=" * 78)

    drift = {k: (cfg.get(k), v) for k, v in DEFAULT_CONFIG.items()
             if k in cfg and cfg[k] != v}
    if drift:
        print("!! CONFIG DIFFERS FROM DEFAULTS -- tuned constants may be invalid:")
        for k, (got, want) in drift.items():
            print(f"     {k}: {got}  (expected {want})")
    else:
        print(f"config: matches SDK defaults   "
              f"[townCenterSellInterval={cfg.get('townCenterSellInterval', 24)} "
              f"-> {'SHALLOW' if int(cfg.get('townCenterSellInterval', 24)) >= 24 else 'DEEP'} market]")
    if cfg.get("marketParams"):
        print(f"!! marketParams overridden: {json.dumps(cfg['marketParams'])[:200]}")

    stats = [analyze_player(steps, p, cfg) for p in range(n_players)]
    labels = []
    for p in range(n_players):
        who = names[p] if p < len(names) else f"P{p}"
        if me is not None:
            who += " *" if p == me else ""
        labels.append(who[:24])

    print(f"statuses: {data.get('statuses')}   rewards: {rewards}")
    if len(rewards) >= 2:
        win = 0 if rewards[0] > rewards[1] else 1 if rewards[1] > rewards[0] else None
        print(f"winner: {labels[win] if win is not None else 'TIE'}"
              f"   margin: ${abs(rewards[0] - rewards[1]):,.0f}")

    w = 26
    def row(name, fn):
        print(f"  {name:<26}" + "".join(f"{fn(s):>{w}}" for s in stats))

    print("\n--- OUTCOME " + "-" * 64)
    print(f"  {'':<26}" + "".join(f"{l:>{w}}" for l in labels))
    row("final money", lambda s: f"{s['final_money']:,.0f}")
    row("quadrants owned", lambda s: s["quadrants"])
    row("peak hands", lambda s: s["peak_hands"])
    row("peak animals", lambda s: s["peak_animals"])

    print("\n--- ACTION EFFICIENCY " + "-" * 54)
    row("useful actions", lambda s: f"{s['useful']:,}")
    row("moves", lambda s: f"{s['moves']:,}")
    row("moves per useful action", lambda s: f"{s['moves']/max(1,s['useful']):.2f}")
    row("idle (PASS)", lambda s: f"{s['idle']:,}")
    row("wasted no-ops", lambda s: f"{sum(s['noops'].values()):,}")
    row("move reversals", lambda s: f"{s['reversals']:,}")

    print("\n--- SILENT FAILURES " + "-" * 56)
    row("animal deaths", lambda s: s["animal_deaths"])
    row("peak weeds", lambda s: s["weeds_seen"])
    row("peak shed+carried", lambda s: f"{s['max_shed_eod']}/{cfg.get('shedCapacity',100)}")
    row("peak units carried", lambda s: s.get("peak_carried", 0))
    row("days shed hit capacity", lambda s: len(s["overflow_days"]))
    row("market orders dropped", lambda s: s["orders_dropped"])
    # Fertilizer does not accumulate: the env stores one bool per animal tile
    # and resets it daily, so anything still uncollected at the last hour is
    # destroyed. A high miss rate is pure lost revenue at ~$75/unit.
    row("fertilizer missed", lambda s: (
        f"{s['fert_missed']}/{s['fert_animal_days']} "
        f"({100.0 * s['fert_missed'] / max(1, s['fert_animal_days']):.0f}%)"))
    row("  = $ left on ground", lambda s: f"~{s['fert_missed'] * 75:,}")

    print("\n--- LABOUR & LAND " + "-" * 58)
    row("hire spend (fib, daily)", lambda s: f"{s['hire_dollars']:,}")
    row("avg hands day 0-9", lambda s: f"{s['hands_early']:.1f}")
    row("avg hands day 10-29", lambda s: f"{s['hands_late']:.1f}")

    print("\n--- PLANTING SCHEDULE " + "-" * 54)
    for p, s in enumerate(stats):
        print(f"\n  {labels[p]}")
        days = sorted({d for d, _ in s["plantings"]})
        for d in days:
            crops = {c: n for (dd, c), n in s["plantings"].items() if dd == d}
            print(f"     day {d:<2} " + "  ".join(f"{c}:{n}" for c, n in
                                                  sorted(crops.items(), key=lambda kv: -kv[1])))

    print("\n--- ACTION MIX " + "-" * 61)
    verbs = ["WATER", "HARVEST", "PLANT", "DIG", "FEED", "CARE",
             "COLLECT_FERTILIZER", "FERTILIZE", "BUILD", "PLACE", "PICKUP", "DROP"]
    for v in verbs:
        if any(s["ops"].get(v) for s in stats):
            row(v.lower(), lambda s, v=v: f"{s['ops'].get(v, 0):,}")

    for p, s in enumerate(stats):
        if s["noops"]:
            print(f"\n  {labels[p]} wasted actions:")
            for reason, n in top(s["noops"]):
                print(f"     {n:>6}  {reason}")
        if s["overflow_days"]:
            days = [d for d, _ in s["overflow_days"]]
            print(f"  {labels[p]} !! shed saturated at start of days {days} "
                  f"-- end-of-day drop was truncated, produce destroyed")

    print("\n--- MARKET " + "-" * 65)
    print("  net = sell revenue - buy-back cost. Read the NET column: WHEAT and")
    print("  FERTILIZER can be repurchased, and a round-trip nets ~zero cash while")
    print("  still adding its full value to the gross sell side.")
    for p, s in enumerate(stats):
        total = sum(s["sold_est"].values())
        net_total = total - sum(s["bought_est"].values())
        print(f"\n  {labels[p]}  gross sales ${total:,.0f}   NET ${net_total:,.0f}")
        rows = sorted(s["sold_est"].items(), key=lambda kv: -kv[1])
        for item, rev in rows:
            units = s["sold_units"].get(item, 0)
            share = 100.0 * rev / total if total else 0
            bu = s["bought_units"].get(item, 0)
            be = s["bought_est"].get(item, 0)
            tail = (f"   bought {bu:>5} for ${be:>9,.0f}  ->  NET {units - bu:>6} units"
                    f"  ${rev - be:>10,.0f}") if bu else ""
            print(f"     {item:<12} {units:>6} units  ${rev:>10,.0f}  "
                  f"avg ${rev/max(1,units):>6,.0f}  {share:>5.1f}%{tail}")
        for item, be in sorted(s["bought_est"].items(), key=lambda kv: -kv[1]):
            if item not in s["sold_est"]:
                print(f"     {item:<12} {'':>6}        {'':>11}  "
                      f"{'':>12}        bought {s['bought_units'][item]:>5} "
                      f"for ${be:>9,.0f}  ->  NET ${-be:>10,.0f}")
        if s["stranded"]:
            lost = sum(s["stranded"].values())
            print(f"     stranded at end (scores $0): {lost} units {s['stranded']}")

    print("\n--- MONEY BY DAY " + "-" * 59)
    print(f"  {'day':>4}" + "".join(f"{l:>{w}}" for l in labels))
    series = [dict(s["money_by_day"]) for s in stats]
    for day in sorted(set().union(*[set(x) for x in series])):
        print(f"  {day:>4}" + "".join(f"{x.get(day, 0):>{w},.0f}" for x in series))
    print()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="+", help="replay JSON files (globs ok)")
    ap.add_argument("--me", type=int, default=None, help="which player is ours")
    ap.add_argument("--team", default=None, help="study this team instead of ours")
    args = ap.parse_args()
    if args.team:
        globals()["FOCUS_TEAM"] = args.team

    files = []
    for pattern in args.paths:
        files.extend(sorted(glob.glob(pattern)) or [pattern])
    for path in files:
        try:
            with open(path) as fh:
                data = json.load(fh)
        except Exception as exc:
            print(f"skipping {path}: {exc}")
            continue
        if "steps" not in data:
            print(f"skipping {path}: not a replay (no 'steps')")
            continue
        report(path, data, detect_seat(data, args.me))
    return 0


if __name__ == "__main__":
    sys.exit(main())
