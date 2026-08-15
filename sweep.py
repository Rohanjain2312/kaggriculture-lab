"""Tune agent constants by playing variants head-to-head against a reference.

Each variant is main.py with one or more module-level constants rewritten. The
metric is win rate against a frozen reference agent, because that is what the
competition actually scores -- mean money can improve while win rate does not.

    python sweep.py --seeds 6 FERT_MIN_VALUE=150,999999
    python sweep.py --ref agents/v1_herd.py MAX_HANDS=13,15,16 MOVE_PENALTY=6,8,12
"""

import argparse
import itertools
import os
import re
import sys

from kaggle_environments import make

from bench import looks_inert

SCRATCH = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".sweep")


def make_variant(source, settings, path):
    """Write `source` with each named constant reassigned, and return the path."""
    text = source
    for name, value in settings.items():
        pattern = re.compile(r"^%s = [^\n#]*" % re.escape(name), re.M)
        if not pattern.search(text):
            raise SystemExit("constant not found in main.py: %s" % name)
        text = pattern.sub("%s = %s " % (name, value), text, count=1)
    with open(path, "w") as fh:
        fh.write(text)
    return path


def score(agent, ref, seeds, steps):
    """Play `agent` as both seats against `ref`; return (win_rate, mean, worst, broken).

    A variant that fails to load still reports `status=DONE` and passes every
    turn, finishing on its starting money -- so without an explicit check a
    broken variant reads as a plausible "terrible idea" rather than an error.
    `broken` counts episodes where the variant never issued a single action.
    """
    wins = 0.0
    monies = []
    broken = 0
    for seed in seeds:
        for flip in (False, True):
            env = make("kaggriculture", configuration={"episodeSteps": steps, "seed": seed})
            env.run([ref, agent] if flip else [agent, ref])
            final = env.steps[-1]
            me, them = (1, 0) if flip else (0, 1)
            if final[me].status != "DONE" or looks_inert(env, me):
                broken += 1
            mine = float(final[me].reward or 0)
            theirs = float(final[them].reward or 0)
            monies.append(mine)
            wins += 1.0 if mine > theirs else 0.5 if mine == theirs else 0.0
    n = len(monies)
    return 100.0 * wins / n, sum(monies) / n, min(monies), broken


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("settings", nargs="+", help="NAME=v1,v2,v3")
    ap.add_argument("--ref", default="agents/sweep_ref.py")
    ap.add_argument("--base", default="main.py")
    ap.add_argument("--seeds", type=int, default=5)
    ap.add_argument("--steps", type=int, default=720)
    args = ap.parse_args()

    names, options = [], []
    for spec in args.settings:
        name, _, values = spec.partition("=")
        names.append(name)
        options.append(values.split(","))

    with open(args.base) as fh:
        source = fh.read()
    os.makedirs(SCRATCH, exist_ok=True)
    seeds = [7 + 13 * i for i in range(args.seeds)]

    print("reference: %s   %d seeds x 2 seats = %d games per variant"
          % (args.ref, len(seeds), 2 * len(seeds)))
    print("%-42s %7s %11s %11s" % ("variant", "win%", "mean $", "worst $"))

    results = []
    for combo in itertools.product(*options):
        settings = dict(zip(names, combo))
        label = " ".join("%s=%s" % kv for kv in settings.items())
        # Per-process filename: two sweeps running at once would otherwise both
        # write the same variant file and score each other's agent.
        path = make_variant(source, settings,
                            os.path.join(SCRATCH, "v_%d.py" % os.getpid()))
        win, mean, worst, broken = score(path, args.ref, seeds, args.steps)
        results.append((win, mean, label))
        flag = "  !! BROKEN in %d/%d episodes -- this number is not a result" % (
            broken, 2 * len(seeds)) if broken else ""
        print("%-42s %6.1f%% %11s %11s%s" % (
            label, win, format(int(mean), ","), format(int(worst), ","), flag))

    results.sort(reverse=True)
    print("\nbest: %s  (%.1f%%, $%s)" % (results[0][2], results[0][0], format(int(results[0][1]), ",")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
