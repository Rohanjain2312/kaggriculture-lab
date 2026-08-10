"""Run a constant sweep as parallel absolute benchmarks against `pass`.

    python sweeprun.py "STAY_BONUS=0,8,12,16"
    python sweeprun.py --jobs 4 --seeds 6 "MAX_HANDS=12,13" "MOVE_PENALTY=4,6"

Why this exists rather than `sweep.py`: `sweep.py` scores head-to-head against a
reference, which flatters any change that reduces our own output -- a production
cut crashes the shared market less, so it wins the mirror while being absolutely
worse. Two changes have now been caught doing exactly that. This runs each
variant against `pass`, where there is no market to share.

Three failure modes from earlier sessions are guarded here, because each one
silently produced a wrong answer rather than an error:

* A variant file truncated to 0 bytes by an interrupted write. Every variant is
  validated -- non-empty, imports, exposes `agent` last, and actually carries the
  requested constant value -- **before** any benchmark starts.
* A crashed run reported as a blank result. A run that yields no `pass` row is
  recorded as FAILED and counted in the summary.
* A difference smaller than seed noise read as a result. NOISE_FLOOR below is the
  measured spread of an unchanged agent; anything under it is reported as noise.
"""

import argparse
import concurrent.futures
import importlib.util
import itertools
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PYTHON = sys.executable

# Spread of an unchanged agent across four disjoint 6-seed sets, measured
# 2026-08-07: 161,673 / 162,754 / 160,130 / 160,536. Re-measure with
# `--noise` if the agent changes materially.
NOISE_FLOOR = 3000


def parse_settings(specs):
    """["A=1,2", "B=3"] -> ([("A", "1"), ...], ...) one tuple per combination."""
    axes = []
    for spec in specs:
        if "=" not in spec:
            raise SystemExit(f"expected NAME=v1,v2 -- got {spec!r}")
        name, values = spec.split("=", 1)
        axes.append([(name.strip(), v.strip()) for v in values.split(",")])
    return list(itertools.product(*axes))


def make_variant(source, combo, path):
    """Write `source` with each constant reassigned. Adds it if absent."""
    text = source
    for name, value in combo:
        pattern = re.compile(r"^%s = [^\n#]*" % re.escape(name), re.M)
        if pattern.search(text):
            text = pattern.sub(f"{name} = {value} ", text, count=1)
        else:
            raise SystemExit(
                f"constant {name} not found in the base agent -- add it there first, "
                f"with a default that preserves current behaviour")
    with open(path, "w") as fh:
        fh.write(text)
    return path


def validate(path, combo):
    """Load the variant and confirm it is usable. Returns an error string or None."""
    if os.path.getsize(path) == 0:
        return "file is empty (an interrupted write truncates the redirect target)"
    try:
        spec = importlib.util.spec_from_file_location("variant", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    except Exception as exc:
        return f"does not import: {exc}"
    callables = [v for v in vars(module).values() if callable(v)]
    if not callables or callables[-1].__name__ != "agent":
        # Kaggle loads a file agent by taking the last callable in the module.
        return "last callable is not `agent` -- Kaggle would run the wrong function"
    for name, value in combo:
        got = getattr(module, name, None)
        if got is None:
            return f"{name} missing after substitution"
        if str(got) != str(value) and float(got) != float(value):
            return f"{name} is {got!r}, expected {value!r}"
    return None


def run_one(path, seeds, seed0):
    """Benchmark one variant against `pass`. Returns (mean, error)."""
    proc = subprocess.run(
        [PYTHON, os.path.join(HERE, "bench.py"), path,
         "--seeds", str(seeds), "--seed0", str(seed0), "--opponents", "pass"],
        capture_output=True, text=True, cwd=HERE)
    for line in proc.stdout.splitlines():
        if line.startswith("pass"):
            fields = line.split()
            if len(fields) >= 4:
                try:
                    return int(fields[3].replace(",", "")), None
                except ValueError:
                    pass
    tail = (proc.stderr or proc.stdout or "").strip().splitlines()
    return None, (tail[-1] if tail else f"no `pass` row (exit {proc.returncode})")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("settings", nargs="*", help="NAME=v1,v2,v3")
    ap.add_argument("--base", default=os.path.join(HERE, "main.py"))
    ap.add_argument("--seeds", type=int, default=6)
    ap.add_argument("--seed0", type=int, default=7)
    ap.add_argument("--jobs", type=int, default=4, help="variants run at once")
    ap.add_argument("--noise", action="store_true",
                    help="re-measure the noise floor: base agent, 4 disjoint seed sets")
    args = ap.parse_args()

    source = open(args.base).read()
    work = tempfile.mkdtemp(prefix="sweeprun-")

    if args.noise:
        tasks = [(f"seed0={s}", args.base, s) for s in (7, 101, 211, 331)]
    else:
        if not args.settings:
            raise SystemExit("give at least one NAME=v1,v2 (or --noise)")
        tasks = []
        problems = []
        for combo in parse_settings(args.settings):
            label = " ".join(f"{n}={v}" for n, v in combo)
            path = make_variant(source, combo,
                                os.path.join(work, re.sub(r"\W+", "_", label) + ".py"))
            err = validate(path, combo)
            if err:
                problems.append(f"  {label}: {err}")
            else:
                tasks.append((label, path, args.seed0))
        if problems:
            # Refuse to run a partly-broken sweep: a blank row among real ones
            # reads as "no effect" rather than "never ran".
            print("REFUSING TO RUN -- these variants are not valid:")
            print("\n".join(problems))
            return 1

    print(f"{len(tasks)} variants x {args.seeds} seeds vs `pass`, {args.jobs} at a time")
    print(f"(a 6-seed run is ~15 min of wall clock; noise floor +/-${NOISE_FLOOR:,})\n")

    results = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as pool:
        futures = {pool.submit(run_one, p, args.seeds, s): label
                   for label, p, s in tasks}
        for fut in concurrent.futures.as_completed(futures):
            label = futures[fut]
            mean, err = fut.result()
            results[label] = (mean, err)
            print(f"  {label:<34} {('FAILED: ' + err) if err else f'{mean:>9,}'}",
                  flush=True)

    ok = {k: v[0] for k, v in results.items() if v[0] is not None}
    failed = [k for k, v in results.items() if v[0] is None]
    print()
    if args.noise and ok:
        lo, hi = min(ok.values()), max(ok.values())
        print(f"noise floor: spread ${hi - lo:,} over {len(ok)} seed sets "
              f"(mean ${sum(ok.values()) // len(ok):,})")
        print(f"-> treat differences under ~${hi - lo:,} as noise")
    elif ok:
        base = ok.get("STAY_BONUS=0") or max(ok.values())
        print(f"{'variant':<34} {'mean $':>10} {'vs best':>10}   verdict")
        for label, mean in sorted(ok.items(), key=lambda kv: -kv[1]):
            delta = mean - base
            verdict = "noise" if abs(delta) < NOISE_FLOOR else (
                "BETTER" if delta > 0 else "worse")
            print(f"{label:<34} {mean:>10,} {delta:>+10,}   {verdict}")
    if failed:
        print(f"\n{len(failed)} variant(s) FAILED and produced no number: "
              + ", ".join(failed))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
