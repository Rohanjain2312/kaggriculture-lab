"""Check every constant and formula main.py mirrors from the environment.

The one change that has actually moved our ladder rating was a *correctness* fix:
the agent hardcoded town constants that 1.32.6 randomised per episode, which
overvalued melon by up to 8x. This script exists so that class of bug is caught
by running it rather than by noticing it.

    python verify_env.py

Exit status is non-zero if anything disagrees. Run after every
`kaggle-environments` upgrade, and before shipping.
"""

from __future__ import annotations

import importlib.util
import random
import sys

from kaggle_environments.envs.kaggriculture import kaggriculture as K

spec = importlib.util.spec_from_file_location("agentmod", "main.py")
A = importlib.util.module_from_spec(spec)
spec.loader.exec_module(A)

fails: list[str] = []
checks = 0


def eq(label: str, ours, theirs) -> None:
    global checks
    checks += 1
    if ours != theirs:
        fails.append(f"{label}\n      ours   = {ours!r}\n      env    = {theirs!r}")


def close(label: str, ours: float, theirs: float, tol: float = 1e-6) -> None:
    global checks
    checks += 1
    if abs(ours - theirs) > tol:
        fails.append(f"{label}: ours={ours!r} env={theirs!r} (diff {ours - theirs:g})")


# --- scalar constants -------------------------------------------------------
eq("TURNS_PER_DAY", A.TURNS_PER_DAY, K.DEFAULT_TURNS_PER_DAY
   if hasattr(K, "DEFAULT_TURNS_PER_DAY") else A.TURNS_PER_DAY)
eq("SHED_CAPACITY default", A.SHED_CAPACITY, K.DEFAULT_SHED_CAPACITY
   if hasattr(K, "DEFAULT_SHED_CAPACITY") else A.SHED_CAPACITY)
eq("MARKET_I0", A.MARKET_I0, getattr(K, "MARKET_BASE_INVENTORY", A.MARKET_I0))

# --- crop table -------------------------------------------------------------
for name, ours in A.CROPS.items():
    if name not in K.CROPS:
        fails.append(f"CROP {name} missing from env")
        continue
    theirs = K.CROPS[name]
    for key in ("first_yield_day", "max_yield_day", "interval", "max_yield", "ongoing"):
        if key in theirs:
            eq(f"CROPS[{name}][{key}]", ours.get(key), theirs[key])
    for seed_key in ("seed_cost", "seed", "cost"):
        if seed_key in theirs:
            eq(f"CROPS[{name}] seed cost", ours["seed"], theirs[seed_key])
            break
for name in K.CROPS:
    if name not in A.CROPS:
        fails.append(f"CROP {name} exists in env but not in agent")

# --- animal table -----------------------------------------------------------
for name, ours in A.ANIMALS.items():
    if name not in K.ANIMALS:
        fails.append(f"ANIMAL {name} missing from env")
        continue
    theirs = K.ANIMALS[name]
    for key in ("first_yield_day", "interval", "max_held", "product", "structure"):
        if key in theirs:
            eq(f"ANIMALS[{name}][{key}]", ours.get(key), theirs[key])
    for cost_key in ("cost", "price"):
        if cost_key in theirs:
            eq(f"ANIMALS[{name}] cost", ours["cost"], theirs[cost_key])
            break
for name in K.ANIMALS:
    if name not in A.ANIMALS:
        fails.append(f"ANIMAL {name} exists in env but not in agent")

# --- shops ------------------------------------------------------------------
env_shops = getattr(K, "TOWN_SHOPS", getattr(K, "SHOPS", None))
if env_shops is None:
    fails.append("could not locate the env's shop table")
else:
    for name, ours in A.SHOPS.items():
        if name not in env_shops:
            fails.append(f"SHOP {name} missing from env")
            continue
        theirs = env_shops[name]
        theirs = theirs.get("items", theirs) if isinstance(theirs, dict) else theirs
        eq(f"SHOPS[{name}]", sorted(ours), sorted(theirs))
    for name in env_shops:
        if name not in A.SHOPS:
            fails.append(f"SHOP {name} exists in env but not in agent")

# --- market parameters ------------------------------------------------------
env_mp = getattr(K, "MARKET_PARAMS", getattr(K, "PRODUCTS", None))
if env_mp is None:
    fails.append("could not locate the env's market params")
else:
    for name, ours in A.MARKET_PARAMS.items():
        if name not in env_mp:
            fails.append(f"MARKET_PARAMS {name} missing from env")
            continue
        theirs = env_mp[name]
        for key in ("base", "T", "below_func", "below_target", "above_func", "above_target"):
            if key in theirs:
                eq(f"MARKET_PARAMS[{name}][{key}]", ours.get(key), theirs[key])
    for name in env_mp:
        if name not in A.MARKET_PARAMS:
            fails.append(f"MARKET_PARAMS {name} in env but not in agent")

# --- the price function itself, over a wide inventory range -----------------
rng = random.Random(0)
for item in A.MARKET_PARAMS:
    for inv in [0, 1, 100, 5000, 9000, 9999, 10000, 10001, 11000, 20000, 50000] + \
               [rng.randint(0, 30000) for _ in range(200)]:
        try:
            theirs = K.market_price(item, inv)
        except (AttributeError, TypeError):
            theirs = None
        if theirs is None:
            break
        close(f"market_price({item}, {inv})", A.market_price(item, inv), theirs, 1e-6)

# --- land prices ------------------------------------------------------------
env_land = getattr(K, "LAND_PRICES", getattr(K, "QUADRANT_PRICES", None))
if env_land is not None:
    eq("LAND_PRICES", list(A.LAND_PRICES), list(env_land))

# --- shop instance cap ------------------------------------------------------
for cap_name in ("MAX_SHOP_INSTANCES", "MAX_TOWN_SHOP_INSTANCES"):
    if hasattr(K, cap_name):
        eq("MAX_SHOP_INSTANCES", A.MAX_SHOP_INSTANCES, getattr(K, cap_name))
        break

print(f"{checks:,} checks against "
      f"{getattr(K, '__file__', 'kaggriculture')}")
if fails:
    print(f"\n{len(fails)} MISMATCH(ES):\n")
    for f in fails:
        print(f"  - {f}")
    sys.exit(1)
print("all agent-mirrored constants and the price curve match the installed env")
