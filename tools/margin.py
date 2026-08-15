"""Head-to-head post-mortem: what separates the winner from the loser.

Every other tool in this repo answers "how much did we earn". That is the wrong
question -- scoring is win/loss per episode, so the only thing that matters is
the *margin against the one opponent in that game*. This tool asks, over a
corpus of digests, which observable differences actually travel with winning.

The core statistic is a **paired within-game test**: for each feature, count how
often the winner's value exceeded the loser's, in the same episode, on the same
board, against the same market. Anything that survives that is a candidate edge;
anything at ~50% is noise no matter how good it looks in absolute terms.

    python tools/margin.py docs/analysis/digests/*.json
    python tools/margin.py --me "Rohan Jain" docs/analysis/digests/*.json
"""

from __future__ import annotations

import argparse
import json
import math
import os
import statistics
import sys
from typing import Any

# Shop -> products it buys. Imported from the environment when available so the
# mapping cannot silently drift from the game; the literal is the fallback for
# running against a corpus without the env installed.
SHOP_PRODUCTS: dict[str, list[str]] = {
    "BAKERY": ["EGG", "WHEAT"],
    "PIZZA_SHOP": ["MILK", "TOMATO", "WHEAT"],
    "BRUNCH_SPOT": ["EGG", "WHEAT", "STRAWBERRY"],
    "YARN_STORE": ["WOOL"],
    "ICE_CREAM_SHOP": ["STRAWBERRY", "MILK", "WHEAT"],
    "PET_CAFE": ["CARROT"],
    "SMOOTHIE_SHOP": ["STRAWBERRY", "MILK"],
    "FARMERS_MARKET": ["WHEAT", "CARROT", "TOMATO", "STRAWBERRY"],
}
try:  # pragma: no cover - environment is present in normal use
    from kaggle_environments.envs.kaggriculture.kaggriculture import SHOPS
    SHOP_PRODUCTS = dict(SHOPS)
except Exception:
    pass

ANIMALS = ("GOOSE", "COW", "SHEEP")
MOVES = ("NORTH", "SOUTH", "EAST", "WEST")

# Features derived from market ORDERS rather than from board state. An order is
# intent, not a fill: unfilled stock is re-offered the next turn, so cumulative
# order quantity over-counts. One ladder agent shows 1,872 units of FERTILIZER
# "sold" from a 14-animal herd that can physically produce ~390. Direction is
# usually right, magnitude is not -- never quote these as volumes.
ORDER_DERIVED = {"n_products_sold", "net_sell_value", "fertilizer_net", "wheat_net",
                 "alignment"}


# --------------------------------------------------------------------------- #
# per-episode feature extraction
# --------------------------------------------------------------------------- #

def shop_demand(digest: dict[str, Any]) -> dict[str, int]:
    """Products the drawn shop multiset buys, weighted by how many shops buy them.

    Shops are drawn *with replacement*, so 3x PIZZA_SHOP is three times the
    TOMATO/MILK/WHEAT demand of one. Counting the multiset rather than the set
    is the whole point.
    """
    demand: dict[str, int] = {}
    for shop, count in (digest.get("final_shops") or {}).items():
        for product in SHOP_PRODUCTS.get(shop, []):
            demand[product] = demand.get(product, 0) + count
    return demand


def alignment(net: dict[str, int], demand: dict[str, int]) -> float:
    """Share of a player's sold units that went into shop-demanded products.

    1.0 means every unit sold was something the town's shops actually buy.
    """
    sold = {k: v for k, v in net.items() if v > 0}
    total = sum(sold.values())
    if not total:
        return 0.0
    return sum(v for k, v in sold.items() if demand.get(k)) / total


def first_sell_day(player: dict[str, Any], product: str) -> int | None:
    """First day this player put the product on the market."""
    for row in player.get("orders_by_day") or []:
        if product in (row.get("sell") or {}):
            return row["day"]
    return None


def realised_price(player: dict[str, Any], product: str) -> float | None:
    """Quantity-weighted average price this player's sells of `product` saw."""
    qty = value = 0.0
    for row in player.get("orders_by_day") or []:
        slot = (row.get("sell") or {}).get(product)
        if slot:
            qty += slot["qty"]
            value += slot["qty"] * slot["avg_price"]
    return round(value / qty, 1) if qty else None


def lead_curve(digest: dict[str, Any], winner: int) -> list[float]:
    """Winner-minus-loser money, day by day."""
    players = digest["players"]
    loser = 1 - winner
    days = min(len(players[winner]["by_day"]), len(players[loser]["by_day"]))
    return [(players[winner]["by_day"][d]["money"] or 0)
            - (players[loser]["by_day"][d]["money"] or 0) for d in range(days)]


def decisive_day(curve: list[float]) -> int | None:
    """First day after which the winner's lead never goes negative again."""
    last_bad = None
    for day, lead in enumerate(curve):
        if lead <= 0:
            last_bad = day
    if last_bad is None:
        return 0
    return last_bad + 1 if last_bad + 1 < len(curve) else None


def player_features(digest: dict[str, Any], pid: int) -> dict[str, Any]:
    """Flat feature row for one player-season."""
    p = digest["players"][pid]
    days = p["by_day"]
    last = days[-1] if days else {}
    ops = p["unit_ops"]
    net = p["net_product_units"]
    demand = shop_demand(digest)
    actions = sum(v for k, v in ops.items() if ":" not in k)
    moves = sum(ops.get(m, 0) for m in MOVES)
    useful = actions - moves
    sell_value = sum(v for k, v in (p.get("order_value_at_price") or {}).items()
                     if k.startswith("SELL:"))
    buy_value = sum(v for k, v in (p.get("order_value_at_price") or {}).items()
                    if k.startswith("BUY_PRODUCT:"))

    feats: dict[str, Any] = {
        "money": p["final_money"],
        "peak_animals": max((sum(r["tiles"].get(a, 0) for a in ANIMALS) for r in days), default=0),
        "peak_plants": max((r["plants"] for r in days), default=0),
        "final_hands": last.get("hands", 0),
        "final_quadrants": last.get("quadrants", 0),
        "hires": p["hires"],
        "actions": actions,
        "moves_per_useful": round(moves / useful, 3) if useful else None,
        "alignment": round(alignment(net, demand), 3),
        "n_products_sold": sum(1 for v in net.values() if v > 0),
        "net_sell_value": round(sell_value - buy_value),
        "fertilizer_net": net.get("FERTILIZER", 0),
        "wheat_net": net.get("WHEAT", 0),
        "sell_days": len(p.get("orders_by_day") or []),
    }
    # Day-10 tempo: how much of the build is standing by the third of the season.
    if len(days) > 10:
        feats["money_d10"] = days[10]["money"]
        feats["plants_d10"] = days[10]["plants"]
        feats["animals_d10"] = sum(days[10]["tiles"].get(a, 0) for a in ANIMALS)
        feats["hands_d10"] = days[10]["hands"]
    for product in ("MELON", "STRAWBERRY", "MILK", "WOOL", "WHEAT", "EGG",
                    "TOMATO", "CARROT", "FERTILIZER"):
        feats[f"sold_{product}"] = max(net.get(product, 0), 0)
        day = first_sell_day(p, product)
        if day is not None:
            feats[f"firstsell_{product}"] = day
    return feats


def episode_row(path: str) -> dict[str, Any] | None:
    """Winner/loser feature pair for one episode, or None if it is unusable."""
    d = json.load(open(path))
    rewards = d.get("rewards") or []
    if len(rewards) != 2 or rewards[0] is None or rewards[1] is None:
        return None
    if rewards[0] == rewards[1]:
        return None
    winner = 0 if rewards[0] > rewards[1] else 1
    curve = lead_curve(d, winner)
    names = d.get("team_names") or [None, None]
    return {
        "episode_id": d.get("episode_id"),
        "version": d.get("module_version"),
        "shops": d.get("final_shops") or {},
        "demand": shop_demand(d),
        "winner_name": names[winner],
        "loser_name": names[1 - winner],
        "margin": rewards[winner] - rewards[1 - winner],
        "margin_pct": (rewards[winner] - rewards[1 - winner]) / max(rewards[1 - winner], 1) * 100,
        "decisive_day": decisive_day(curve),
        "lead_curve": curve,
        "W": player_features(d, winner),
        "L": player_features(d, 1 - winner),
    }


# --------------------------------------------------------------------------- #
# reporting
# --------------------------------------------------------------------------- #

def binomial_p(k: int, n: int) -> float:
    """Two-sided p-value for k successes in n fair coin flips."""
    if n == 0:
        return 1.0
    tail = sum(math.comb(n, i) for i in range(min(k, n - k) + 1)) / 2 ** n
    return min(1.0, 2 * tail)


def paired_table(rows: list[dict[str, Any]], keys: list[str]) -> None:
    """For each feature, how often did the winner exceed the loser in-game."""
    print(f"\n{'feature':<26} {'W>L':>7} {'n':>4} {'p':>7}   {'W med':>10} {'L med':>10}  "
          f"{'med(W-L)':>10}")
    print("-" * 86)
    scored = []
    for key in keys:
        wins = ties = 0
        wv, lv, diffs = [], [], []
        for r in rows:
            a, b = r["W"].get(key), r["L"].get(key)
            if a is None or b is None:
                continue
            wv.append(a)
            lv.append(b)
            diffs.append(a - b)
            if a > b:
                wins += 1
            elif a == b:
                ties += 1
        n = len(wv) - ties
        if not wv or n == 0:
            continue
        # Rank by how far the paired rate sits from a coin flip, not by effect
        # size -- a large mean gap that wins half the time is noise.
        scored.append((abs(wins / n - 0.5), key, wins, n, binomial_p(wins, n),
                       statistics.median(wv), statistics.median(lv),
                       statistics.median(diffs)))
    for _, key, wins, n, p, wm, lm, dm in sorted(scored, reverse=True):
        flag = "  <<<" if p < 0.05 else ""
        mark = "~" if key in ORDER_DERIVED or key.startswith("sold_") else " "
        print(f"{mark}{key:<25} {wins/n:>6.0%} {n:>4} {p:>7.3f}   {wm:>10.1f} {lm:>10.1f}  "
              f"{dm:>+10.1f}{flag}")
    print("\n  ~ = derived from market ORDERS (intent, re-offered each turn) -- trust the"
          "\n      direction, not the magnitude. Unmarked rows are board state or action"
          "\n      counts and are exact.")


def report(rows: list[dict[str, Any]], me: str | None) -> None:
    """Print the full head-to-head report."""
    print("=" * 84)
    print(f"HEAD-TO-HEAD ANALYSIS  --  {len(rows)} episodes")
    versions = sorted({r["version"] for r in rows})
    print(f"env versions: {versions}"
          + ("   <-- MIXED, money is not comparable across these" if len(versions) > 1 else ""))
    print("=" * 84)

    # ---- margins: how close are these games actually decided? ---------------
    margins = sorted(r["margin_pct"] for r in rows)
    print("\n## MARGIN OF VICTORY  (winner over loser, %)")
    print(f"  median {statistics.median(margins):.1f}%   mean {statistics.mean(margins):.1f}%"
          f"   min {margins[0]:.1f}%   max {margins[-1]:.1f}%")
    for cut in (2, 5, 10, 20):
        n = sum(1 for m in margins if m <= cut)
        print(f"  decided by <= {cut:>2}%: {n:>3}/{len(margins)}  ({n/len(margins):.0%})")
    abs_margins = sorted(r["margin"] for r in rows)
    print(f"  absolute $: median ${statistics.median(abs_margins):,.0f}"
          f"   p10 ${abs_margins[len(abs_margins)//10]:,.0f}   min ${abs_margins[0]:,.0f}")

    # ---- when is the game decided? -----------------------------------------
    decisive = [r["decisive_day"] for r in rows if r["decisive_day"] is not None]
    if decisive:
        print("\n## WHEN THE GAME IS DECIDED  (day after which the winner never trails)")
        print(f"  median day {statistics.median(decisive):.0f} of 30"
              f"   mean {statistics.mean(decisive):.1f}")
        for lo, hi, label in ((0, 5, "days 0-5   (build)"), (6, 14, "days 6-14  (mid)"),
                              (15, 23, "days 15-23 (late)"), (24, 30, "days 24-29 (endgame)")):
            n = sum(1 for d in decisive if lo <= d <= hi)
            print(f"  {label}: {n:>3}/{len(decisive)}  ({n/len(decisive):.0%})")
        flips = sum(1 for r in rows
                    if any(x > 0 for x in r["lead_curve"][:20]) and r["decisive_day"]
                    and r["decisive_day"] > 20)
        print(f"  games where the day-20 leader still lost: {flips}/{len(rows)}")

    # ---- the paired test ---------------------------------------------------
    print("\n## WHAT SEPARATES WINNER FROM LOSER  (paired, same board, same market)")
    print("   'W>L' = share of episodes where the winner's value was higher.")
    print("   50% = no signal. '<<<' marks p<0.05.")
    keys = [k for k in rows[0]["W"] if k != "money"]
    for r in rows:
        for k in list(r["W"]) + list(r["L"]):
            keys.append(k) if k not in keys and k != "money" else None
    paired_table(rows, keys)

    # ---- shop draw and adaptation ------------------------------------------
    print("\n## SHOP DRAW  (sampled WITH replacement -- the multiset is the board)")
    dup_games = 0
    for r in rows:
        counts = list(r["shops"].values())
        if counts and max(counts) >= 2:
            dup_games += 1
    print(f"  episodes with a duplicated shop: {dup_games}/{len(rows)} ({dup_games/len(rows):.0%})")
    spread = [max(r["shops"].values()) if r["shops"] else 0 for r in rows]
    print(f"  max copies of one shop: median {statistics.median(spread):.0f}, worst {max(spread)}")
    print("\n  shop multiset -> did the winner produce what the town wanted?")
    aligned_wins = sum(1 for r in rows if r["W"]["alignment"] > r["L"]["alignment"])
    both = sum(1 for r in rows if r["W"]["alignment"] != r["L"]["alignment"])
    if both:
        print(f"  winner more shop-aligned in {aligned_wins}/{both} ({aligned_wins/both:.0%})"
              f"  p={binomial_p(aligned_wins, both):.3f}")

    # ---- unmet demand: products the shops want that nobody makes -----------
    print("\n## UNCONTESTED DEMAND  (shops want it, NEITHER player produced it)")
    gaps: dict[str, int] = {}
    for r in rows:
        for product, weight in r["demand"].items():
            made = r["W"].get(f"sold_{product}", 0) + r["L"].get(f"sold_{product}", 0)
            if made == 0:
                gaps[product] = gaps.get(product, 0) + 1
    if gaps:
        for product, n in sorted(gaps.items(), key=lambda x: -x[1]):
            print(f"  {product:<12} demanded but unproduced in {n:>3}/{len(rows)} episodes"
                  f"  ({n/len(rows):.0%})")
    else:
        print("  (none -- every demanded product had a producer)")

    # ---- market timing -----------------------------------------------------
    print("\n## MARKET TIMING  (who hit each product first, and what price they got)")
    print(f"  {'product':<12} {'W first':>8} {'L first':>8} {'W earlier':>10}  {'W price':>9} {'L price':>9}")
    for product in ("MELON", "STRAWBERRY", "MILK", "WOOL", "WHEAT", "FERTILIZER"):
        wd = [r["W"][f"firstsell_{product}"] for r in rows if f"firstsell_{product}" in r["W"]]
        ld = [r["L"][f"firstsell_{product}"] for r in rows if f"firstsell_{product}" in r["L"]]
        pairs = [(r["W"][f"firstsell_{product}"], r["L"][f"firstsell_{product}"]) for r in rows
                 if f"firstsell_{product}" in r["W"] and f"firstsell_{product}" in r["L"]]
        earlier = sum(1 for a, b in pairs if a < b)
        if not wd and not ld:
            continue
        print(f"  {product:<12} {statistics.median(wd) if wd else float('nan'):>8.0f}"
              f" {statistics.median(ld) if ld else float('nan'):>8.0f}"
              f" {f'{earlier}/{len(pairs)}' if pairs else '-':>10}")

    # ---- our own agent, if present -----------------------------------------
    if me:
        mine = [(r, "W") for r in rows if r["winner_name"] == me]
        mine += [(r, "L") for r in rows if r["loser_name"] == me]
        if mine:
            wins = sum(1 for _, side in mine if side == "W")
            print(f"\n## OUR AGENT ({me})  {wins}W-{len(mine)-wins}L over {len(mine)} episodes")
            losses = [r for r, side in mine if side == "L"]
            if losses:
                lm = sorted(r["margin_pct"] for r in losses)
                print(f"  losing margins: median {statistics.median(lm):.1f}%,"
                      f" closest {lm[0]:.1f}%, worst {lm[-1]:.1f}%")
                near = sum(1 for m in lm if m <= 10)
                print(f"  losses within 10%: {near}/{len(lm)} -- these are the winnable ones")


def focus_report(paths: list[str], team: str) -> None:
    """Pair one team against whoever it faced, instead of winner against loser.

    When a single agent dominates a corpus, `report` conflates "what winners do"
    with "what that agent does". This asks the two separable questions: what
    does the focus agent do differently from the field, and -- in the subset it
    lost -- what did the opponent do differently from its own norm.
    """
    focus_rows, opp_rows, results = [], [], []
    for path in paths:
        try:
            d = json.load(open(path))
        except Exception:
            continue
        names = d.get("team_names") or []
        rewards = d.get("rewards") or []
        if team not in names or len(rewards) != 2 or rewards[0] == rewards[1]:
            continue
        pid = names.index(team)
        won = rewards[pid] > rewards[1 - pid]
        focus_rows.append(player_features(d, pid))
        opp_rows.append(player_features(d, 1 - pid))
        results.append({"won": won, "opponent": names[1 - pid],
                        "margin": rewards[pid] - rewards[1 - pid],
                        "episode_id": d.get("episode_id")})

    n = len(focus_rows)
    wins = sum(1 for r in results if r["won"])
    print("=" * 86)
    print(f"FOCUS: {team}  --  {wins}W-{n - wins}L over {n} episodes")
    print("=" * 86)

    paired = [{"W": f, "L": o} for f, o in zip(focus_rows, opp_rows)]
    print(f"\n## {team} VS THE FIELD  ('W>L' = share of games where {team} was higher)")
    keys = sorted({k for row in focus_rows for k in row} | {k for row in opp_rows for k in row})
    paired_table(paired, [k for k in keys if k != "money"])

    losses = [i for i, r in enumerate(results) if not r["won"]]
    if losses:
        print(f"\n## THE {len(losses)} LOSSES -- what the opponent did that the field does not")
        print(f"  {'episode':>10}  {'opponent':<24} {'margin':>10}")
        for i in losses:
            r = results[i]
            print(f"  {r['episode_id']:>10}  {r['opponent']:<24} {r['margin']:>10,.0f}")
        print(f"\n  {'feature':<26} {'in losses':>12} {'in wins':>12} {'delta':>12}")
        print("  " + "-" * 64)
        wins_idx = [i for i, r in enumerate(results) if r["won"]]
        deltas = []
        for key in keys:
            lose_vals = [opp_rows[i][key] for i in losses if opp_rows[i].get(key) is not None]
            win_vals = [opp_rows[i][key] for i in wins_idx if opp_rows[i].get(key) is not None]
            if len(lose_vals) < 2 or len(win_vals) < 2:
                continue
            a, b = statistics.median(lose_vals), statistics.median(win_vals)
            scale = max(abs(a), abs(b), 1)
            deltas.append((abs(a - b) / scale, key, a, b))
        for _, key, a, b in sorted(deltas, reverse=True)[:14]:
            print(f"  {key:<26} {a:>12.1f} {b:>12.1f} {a - b:>+12.1f}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("digests", nargs="+", help="digest .json files")
    parser.add_argument("--me", default=None, help="our team name, for a per-agent section")
    parser.add_argument("--json", default=None, help="also write the raw rows here")
    parser.add_argument("--focus", default=None, metavar="TEAM",
                        help="pair by this team vs its opponent instead of winner vs loser. "
                             "Use when one agent dominates the corpus: pairing by winner then "
                             "just re-describes that agent, while this asks what it does "
                             "differently and separately what beat it.")
    args = parser.parse_args()

    rows = []
    for path in args.digests:
        if not os.path.isfile(path):
            continue
        try:
            row = episode_row(path)
        except Exception as exc:  # a malformed digest must not kill the batch
            print(f"  skip {os.path.basename(path)}: {type(exc).__name__}: {exc}", file=sys.stderr)
            continue
        if row:
            rows.append(row)
    if not rows:
        print("no usable episodes", file=sys.stderr)
        return 1

    if args.focus:
        focus_report(args.digests, args.focus)
        return 0

    report(rows, args.me)
    if args.json:
        json.dump(rows, open(args.json, "w"), ensure_ascii=False, indent=1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
