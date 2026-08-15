"""Reduce raw Kaggriculture replays to compact per-episode digests.

A ladder replay is ~32 MB of JSON; 36 of them is 1.1 GB. Nothing in that volume
is needed to answer a strategy question -- the useful content is a per-day
snapshot and a handful of aggregates, which is ~15 KB per episode. This walks
the raw files once and writes those digests, so the corpus becomes queryable
without re-reading (or re-downloading) the originals.

    python digest.py replays/top-cohort/*.json
    python digest.py --out docs/analysis/digests replays/ladder/v5-pivot/*.json

Then prune the raw replays. The digest is what stays.

Two cautions are baked into the output rather than left to the reader:

* `module_version` is recorded per episode because **money is not comparable
  across environment versions** -- 1.32.5 and 1.32.6 differ by ~39% on the same
  play. Always group by it before comparing dollars.
* market rows are **orders, not fills**. A SELL can fill partially, and units
  act before the market resolves. `market_inventory` is the ground truth for
  what the market actually absorbed; the order counts are intent.
"""

from __future__ import annotations

import argparse
import gc
import json
import os
import sys
from typing import Any

SNAPSHOT_HOUR = 12        # mid-day: hands are reset to 0 at the day boundary
CROPS = ("WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON")
ANIMALS = ("GOOSE", "COW", "SHEEP")
PRODUCTS = CROPS + ("EGG", "MILK", "WOOL", "FERTILIZER")


def tile_census(tiles: list[list[Any]]) -> dict[str, int]:
    """Count tiles by crop, animal, structure, weed, empty and locked."""
    out: dict[str, int] = {}
    for row in tiles:
        for cell in row:
            if cell == "LOCKED":
                key = "LOCKED"
            elif cell is None:
                key = "EMPTY"
            elif not isinstance(cell, dict):
                key = "OTHER"
            elif cell.get("animal"):
                key = cell["animal"]
            elif cell.get("kind") == "PLANT":
                key = cell.get("crop", "PLANT")
            else:
                key = cell.get("kind", "OTHER")
            out[key] = out.get(key, 0) + 1
    return out


def plant_detail(tiles: list[list[Any]], day: int) -> dict[str, Any]:
    """Watering and fertilizer state across living plants, for audit checks."""
    total = watered = fertilised = at_risk = 0
    for row in tiles:
        for cell in row:
            if not isinstance(cell, dict) or cell.get("kind") != "PLANT":
                continue
            total += 1
            watered += bool(cell.get("watered_today"))
            fertilised += cell.get("fertilized_until_day", -1) >= day
            at_risk += cell.get("consecutive_unwatered", 0) >= 1
    return {"plants": total, "watered_today": watered,
            "fertilised": fertilised, "at_risk": at_risk}


def collect_actions(steps: list[Any], player: int) -> dict[str, Any]:
    """Aggregate every action this player issued across the episode."""
    ops: dict[str, int] = {}
    orders: dict[str, dict[str, int]] = {}
    order_value: dict[str, float] = {}
    hires = 0
    for step in steps:
        entry = step[player]
        action = entry.get("action")
        if not isinstance(action, dict):
            continue
        prices = entry.get("observation", {}).get("market", {}).get("prices", {})
        farmer = action.get("farmer")
        units = ([farmer] if farmer else []) + list(action.get("hands") or [])
        for op in units:
            if not op or op[0] == "PASS":
                continue
            ops[op[0]] = ops.get(op[0], 0) + 1
            # Keep the argument for ops that name a crop or animal -- without it
            # "what did they plant" can only be back-inferred from census deltas.
            if len(op) > 1 and op[0] in ("PLANT", "PLACE", "PICKUP"):
                key = f"{op[0]}:{op[1]}"
                ops[key] = ops.get(key, 0) + 1
        for order in action.get("market") or []:
            if not order:
                continue
            kind = order[0]
            if kind == "HIRE":
                hires += int(order[1]) if len(order) > 1 else 1
                continue
            if len(order) < 2:
                ops[kind] = ops.get(kind, 0) + 1
                continue
            item = str(order[1])
            qty = int(order[2]) if len(order) > 2 else 1
            orders.setdefault(kind, {})
            orders[kind][item] = orders[kind].get(item, 0) + qty
            order_value[f"{kind}:{item}"] = (
                order_value.get(f"{kind}:{item}", 0.0) + qty * float(prices.get(item, 0)))
    net = {}
    sold = orders.get("SELL", {})
    bought = orders.get("BUY_PRODUCT", {})
    for item in set(sold) | set(bought):
        net[item] = sold.get(item, 0) - bought.get(item, 0)
    return {"unit_ops": ops, "orders": orders, "net_product_units": net,
            "order_value_at_price": {k: round(v) for k, v in order_value.items()},
            "hires": hires}


def orders_by_day(steps: list[Any], player: int, turns_per_day: int) -> list[dict[str, Any]]:
    """Per-day SELL/BUY flow for one player, with the price each order saw.

    The whole-episode aggregate in `collect_actions` cannot answer *when* a
    player hit the market, and market timing is a head-to-head weapon: selling
    into a product before the opponent does moves the price against them. This
    keeps the day resolution that question needs.
    """
    per_day: dict[int, dict[str, Any]] = {}
    for index, step in enumerate(steps):
        entry = step[player]
        action = entry.get("action")
        if not isinstance(action, dict):
            continue
        orders = action.get("market") or []
        if not orders:
            continue
        day = index // turns_per_day
        prices = entry.get("observation", {}).get("market", {}).get("prices", {})
        row = per_day.setdefault(day, {"day": day, "sell": {}, "buy": {}, "value": 0.0})
        for order in orders:
            if not order or len(order) < 2 or order[0] in ("HIRE",):
                continue
            kind, item = order[0], str(order[1])
            qty = int(order[2]) if len(order) > 2 else 1
            price = float(prices.get(item, 0))
            if kind == "SELL":
                bucket = row["sell"]
                row["value"] += qty * price
            elif kind == "BUY_PRODUCT":
                bucket = row["buy"]
                row["value"] -= qty * price
            else:
                continue
            slot = bucket.setdefault(item, {"qty": 0, "price_sum": 0.0})
            slot["qty"] += qty
            slot["price_sum"] += qty * price
    out = []
    for day in sorted(per_day):
        row = per_day[day]
        for side in ("sell", "buy"):
            for item, slot in row[side].items():
                slot["avg_price"] = round(slot.pop("price_sum") / max(slot["qty"], 1), 1)
        row["value"] = round(row["value"])
        out.append(row)
    return out


def digest_episode(path: str) -> dict[str, Any]:
    """Reduce one replay file to its digest dict."""
    with open(path) as fh:
        raw = json.load(fh)

    steps = raw["steps"]
    info = raw.get("info") or {}
    config = raw.get("configuration") or {}
    turns_per_day = int(config.get("turnsPerDay", 24))

    out: dict[str, Any] = {
        "source_file": os.path.basename(path),
        "episode_id": info.get("EpisodeId"),
        "module_version": raw.get("module_version"),
        "seed": info.get("seed"),
        "team_names": info.get("TeamNames"),
        "rewards": raw.get("rewards"),
        "statuses": raw.get("statuses"),
        "n_steps": len(steps),
        "config": {k: v for k, v in config.items()
                   if k not in ("marketParams", "agentTimeout")},
        "players": [],
        "shop_draw": [],
        "market_by_day": [],
    }

    # Shop draw: record only when the multiset changes -- it is small and the
    # draw is with replacement, so duplicates matter.
    previous = None
    for step in steps:
        obs = step[0].get("observation") or {}
        shops = (obs.get("town") or {}).get("unlocked_shops")
        if shops is None:
            continue
        current = sorted(shops)
        if current != previous:
            out["shop_draw"].append({"day": obs.get("day"), "hour": obs.get("hour"),
                                     "shops": current})
            previous = current
    if previous is not None:
        counts: dict[str, int] = {}
        for shop in previous:
            counts[shop] = counts.get(shop, 0) + 1
        out["final_shops"] = counts

    n_players = len(steps[0])
    for player in range(n_players):
        days = []
        for day in range(30):
            index = day * turns_per_day + SNAPSHOT_HOUR
            if index >= len(steps):
                break
            obs = steps[index][player].get("observation") or {}
            farms = obs.get("farms") or []
            if player >= len(farms):
                break
            farm = farms[player]
            private = obs.get("private") or {}
            shed = private.get("shed") or {}
            row = {
                "day": day,
                "money": farm.get("money"),
                "hands": len(farm.get("hands") or []),
                "hires_today": farm.get("hires_today"),
                "quadrants": len(farm.get("unlocked_quadrants") or []),
                "tiles": tile_census(farm.get("tiles") or []),
                "shed_total": sum(v for v in shed.values() if isinstance(v, int)),
                "shed": {k: v for k, v in shed.items() if v},
                "carried": sum(sum(i.values()) for i in (private.get("inventories") or [])),
                "seeds": {k: v for k, v in (private.get("seeds") or {}).items() if v},
            }
            row.update(plant_detail(farm.get("tiles") or [], day))
            days.append(row)

        entry = {"player": player,
                 "name": (info.get("TeamNames") or [None] * n_players)[player]
                 if info.get("TeamNames") else None,
                 "final_money": (raw.get("rewards") or [None] * n_players)[player],
                 "by_day": days}
        entry.update(collect_actions(steps, player))
        entry["orders_by_day"] = orders_by_day(steps, player, turns_per_day)
        out["players"].append(entry)

    # Market trajectory is shared, so record it once.
    for day in range(30):
        index = day * turns_per_day + SNAPSHOT_HOUR
        if index >= len(steps):
            break
        market = (steps[index][0].get("observation") or {}).get("market") or {}
        out["market_by_day"].append({
            "day": day,
            "prices": market.get("prices"),
            "inventory": market.get("inventory"),
        })

    del raw, steps
    gc.collect()
    return out


def summary_row(d: dict[str, Any], player: int) -> dict[str, Any]:
    """One flat row per player-season for the index CSV."""
    p = d["players"][player]
    days = p["by_day"]
    last = days[-1] if days else {}
    peak_animals = max((sum(r["tiles"].get(a, 0) for a in ANIMALS) for r in days),
                       default=0)
    peak_plants = max((r["plants"] for r in days), default=0)
    ops = p["unit_ops"]
    row = {
        "episode_id": d["episode_id"],
        "module_version": d["module_version"],
        "player": player,
        "name": p["name"],
        "final_money": p["final_money"],
        "opponent_money": (d["rewards"] or [None, None])[1 - player],
        "won": (None if not d.get("rewards")
                else int(d["rewards"][player] > d["rewards"][1 - player])),
        "mirror": int(len(set(d.get("team_names") or [])) == 1),
        "town_centre_interval": d["config"].get("townCenterSellInterval"),
        "peak_animals": peak_animals,
        "peak_plants": peak_plants,
        "final_hands": last.get("hands"),
        "final_quadrants": last.get("quadrants"),
        "hires": p["hires"],
        "actions_total": sum(ops.values()),
        "moves": sum(ops.get(k, 0) for k in ("NORTH", "SOUTH", "EAST", "WEST")),
    }
    for op in ("WATER", "PLANT", "HARVEST", "FEED", "CARE", "COLLECT_FERTILIZER",
               "FERTILIZE", "DIG", "BUILD", "PLACE", "PICKUP", "DROP"):
        row[f"op_{op}"] = ops.get(op, 0)
    for item in PRODUCTS:
        row[f"net_{item}"] = p["net_product_units"].get(item, 0)
    return row


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("replays", nargs="+", help="raw replay .json files")
    parser.add_argument("--out", default="docs/analysis/digests",
                        help="directory for per-episode digests and index.csv")
    parser.add_argument("--force", action="store_true",
                        help="re-digest episodes that already have a digest")
    args = parser.parse_args()

    os.makedirs(args.out, exist_ok=True)
    rows: list[dict[str, Any]] = []
    failed: list[str] = []

    for path in args.replays:
        stem = os.path.splitext(os.path.basename(path))[0]
        target = os.path.join(args.out, f"{stem}.json")
        if os.path.exists(target) and not args.force:
            with open(target) as fh:
                d = json.load(fh)
        else:
            try:
                d = digest_episode(path)
            except (OSError, ValueError, KeyError, IndexError, TypeError) as exc:
                print(f"  FAILED {os.path.basename(path)}: {type(exc).__name__}: {exc}",
                      file=sys.stderr)
                failed.append(path)
                continue
            with open(target, "w") as fh:
                json.dump(d, fh, separators=(",", ":"), sort_keys=True)
        src = os.path.getsize(path) if os.path.exists(path) else 0
        print(f"  {os.path.basename(path):>18}  {src / 1e6:7.1f} MB -> "
              f"{os.path.getsize(target) / 1e3:7.1f} KB  v{d.get('module_version')}")
        for player in range(len(d["players"])):
            rows.append(summary_row(d, player))

    if rows:
        import csv
        index = os.path.join(args.out, "index.csv")
        fields = list(rows[0].keys())
        with open(index, "w", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
        print(f"\n{len(rows)} player-seasons -> {index}")
        versions: dict[str, int] = {}
        for r in rows:
            key = str(r["module_version"])
            versions[key] = versions.get(key, 0) + 1
        print("by env version:", versions,
              " (money is NOT comparable across these)")
        mirrors = sum(r["mirror"] for r in rows)
        print(f"mirror-match player-seasons: {mirrors}/{len(rows)}")
    if failed:
        print(f"\n{len(failed)} FAILED: {[os.path.basename(f) for f in failed]}",
              file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
