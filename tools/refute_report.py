import json, statistics as st
from collections import defaultdict

SD = "/private/tmp/claude-501/-Users-rohanjain-Kaggle/42595745-fed2-4e70-8549-75107f5a1ad2/scratchpad"
elite = json.load(open(f"{SD}/elite.json"))
ours = json.load(open(f"{SD}/ours.json"))
ours = [r for r in ours if r["name"] == "Rohan Jain"]


def stats(rows, label):
    T = lambda k: sum(r[k] for r in rows)
    n = len(rows)
    req, mv, tail, pre = T("req"), T("moves"), T("tail"), T("pre_moves")
    print(f"\n=== {label}  (n={n} agent-episodes) ===")
    print(f"  moves/ep            {mv/n:8.0f}")
    print(f"  stops(useful)/ep    {T('stops')/n:8.0f}")
    print(f"  manhattan floor/ep  {req/n:8.0f}")
    print(f"  tail moves/ep       {tail/n:8.0f}   ({100*tail/mv:.1f}% of moves)")
    print(f"  DETOUR all moves    {mv/req:8.3f}   <- analyst's headline")
    print(f"  DETOUR excl. tail   {pre/req:8.3f}   <- tail removed (no double count)")
    print(f"  reversals/1000 mv   {1000*T('rev')/mv:8.1f}")
    print(f"  idle PASS/ep        {T('idle')/n:8.0f}")
    print(f"  no-op (failed)/ep   {T('noop')/n:8.0f}")
    print(f"  unit-turns/ep       {T('unit_turns')/n:8.0f}")
    print(f"  idle share of turns {100*T('idle')/T('unit_turns'):8.1f}%")
    print(f"  unit-days/ep        {T('unitdays')/n:8.1f}")
    print(f"  unit-days w/ 0 stop {T('unitdays_nostop')/n:8.1f}  ({100*T('unitdays_nostop')/T('unitdays'):.1f}%)"
          f"  moves burnt {T('moves_nostop')/n:.0f}/ep")
    print(f"  stops per unit-day  {T('stops')/max(1,T('unitdays')-T('unitdays_nostop')):8.2f}  (working unit-days)")
    # per-episode dispersion of detour
    ds = [r["moves"] / r["req"] for r in rows if r["req"]]
    print(f"  per-ep detour: mean {st.mean(ds):.3f}  sd {st.pstdev(ds):.3f}  min {min(ds):.3f}  max {max(ds):.3f}")
    ds2 = [r["pre_moves"] / r["req"] for r in rows if r["req"]]
    print(f"  per-ep detour-notail: mean {st.mean(ds2):.3f}  sd {st.pstdev(ds2):.3f}  min {min(ds2):.3f}  max {max(ds2):.3f}")
    return {"detour": mv / req, "notail": pre / req}


def stopcount_table(rows, label):
    agg = defaultdict(lambda: [0, 0, 0])
    for r in rows:
        for k, v in r["by_stopcount"].items():
            k = int(k)
            agg[k][0] += v[0]; agg[k][1] += v[1]; agg[k][2] += v[2]
    print(f"\n-- detour (excl tail) by stops-in-that-unit-day: {label}")
    print("  stops  unit-days   floor   moves   detour")
    for k in sorted(agg):
        req, mv, nd = agg[k]
        if req:
            print(f"  {k:5d} {nd:10d} {req:7d} {mv:7d} {mv/req:8.3f}")
    return agg


e = stats(elite, "ELITE (all top-cohort seats)")
o = stats(ours, "OURS (v3-fert-late, our seat only)")

ea = stopcount_table(elite, "elite")
oa = stopcount_table(ours, "ours")

# Mix-adjusted: apply elite's detour-by-stopcount to OUR unit-day mix and vice versa
def mixadj(src, dst, lab):
    num = den = 0
    for k, v in dst.items():
        k = int(k)
        if k in src and src[k][0]:
            rate = src[k][1] / src[k][0]
            num += rate * v[0]; den += v[0]
    print(f"  {lab}: {num/den:.3f}")

print("\n-- mix adjustment (same stops-per-unit-day distribution)")
print("  our actual detour-notail:", f"{sum(r['pre_moves'] for r in ours)/sum(r['req'] for r in ours):.3f}")
mixadj(ea, oa, "elite's per-bucket rates applied to OUR unit-day mix")
print("  elite actual detour-notail:", f"{sum(r['pre_moves'] for r in elite)/sum(r['req'] for r in elite):.3f}")
mixadj(oa, ea, "our per-bucket rates applied to ELITE unit-day mix")

# per-agent breakdown among elite
print("\n-- per-agent (elite), agents with >=3 seats")
by = defaultdict(list)
for r in elite:
    by[r["name"]].append(r)
for nm, rs in sorted(by.items(), key=lambda kv: -len(kv[1])):
    if len(rs) < 3:
        continue
    req = sum(r["req"] for r in rs); mv = sum(r["moves"] for r in rs)
    pre = sum(r["pre_moves"] for r in rs); tl = sum(r["tail"] for r in rs)
    idle = sum(r["idle"] for r in rs); ut = sum(r["unit_turns"] for r in rs)
    print(f"  {nm[:28]:30s} n={len(rs):2d} detour {mv/req:.3f} notail {pre/req:.3f} "
          f"tail% {100*tl/mv:4.1f} idle% {100*idle/ut:4.1f} moves/ep {mv/len(rs):5.0f} "
          f"stops/ep {sum(r['stops'] for r in rs)/len(rs):5.0f} money {st.mean([r['reward'] for r in rs]):,.0f}")

# does detour predict winning WITHIN elite games?
print("\n-- within-episode: does the lower-detour seat win? (elite games)")
byep = defaultdict(list)
for r in elite:
    byep[r["episode"]].append(r)
wins_for_lower = 0; tot = 0; diffs = []
for ep, rs in byep.items():
    if len(rs) != 2:
        continue
    a, b = rs
    if a["req"] == 0 or b["req"] == 0:
        continue
    da, db = a["moves"] / a["req"], b["moves"] / b["req"]
    if da == db:
        continue
    lower = a if da < db else b
    higher = b if da < db else a
    tot += 1
    if lower["reward"] > higher["reward"]:
        wins_for_lower += 1
    diffs.append((da - db, a["reward"] - b["reward"]))
print(f"  lower-detour seat won {wins_for_lower}/{tot}")
import math
xs = [d[0] for d in diffs]; ys = [d[1] for d in diffs]
mx, my = st.mean(xs), st.mean(ys)
cov = sum((x-mx)*(y-my) for x, y in diffs)
sx = math.sqrt(sum((x-mx)**2 for x in xs)); sy = math.sqrt(sum((y-my)**2 for y in ys))
print(f"  corr(detour_diff, money_diff) = {cov/(sx*sy):.3f}   n={len(diffs)}")

print("\n-- within our own 10 games: detour vs win")
ourall = json.load(open(f"{SD}/ours.json"))
byep = defaultdict(list)
for r in ourall:
    byep[r["episode"]].append(r)
for ep, rs in sorted(byep.items()):
    me = [r for r in rs if r["name"] == "Rohan Jain"][0]
    op = [r for r in rs if r["name"] != "Rohan Jain"][0]
    print(f"  {ep} me detour {me['moves']/me['req']:.3f} notail {me['pre_moves']/me['req']:.3f} "
          f"tail% {100*me['tail']/me['moves']:4.1f} idle% {100*me['idle']/me['unit_turns']:4.1f} "
          f"money {me['reward']:>8,.0f} vs {op['reward']:>8,.0f} "
          f"{'WIN ' if me['reward']>op['reward'] else 'loss'}  opp detour {op['moves']/op['req']:.3f}")
