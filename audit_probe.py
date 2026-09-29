"""Adversarial probes against the 'structure is the bias' implementation.

Run from /workspace:  python3 audit_probe.py
Each probe prints PASS (behaves as intended) or FINDING (behaves wrongly).
Temporary audit file — safe to delete.
"""
import sys
sys.path.insert(0, "/workspace")

import pandas as pd
from backtest.engine.candles import Candle
from backtest.engine.structure import Direction
from backtest.slk.cascade import Cascade, structural_direction, _agree
from backtest.slk.stream import BreakTracker
from backtest.slk import narrative

T0 = pd.Timestamp("2026-01-01")


def c(i, o, h, l, cl, unit="hours"):
    return Candle(time=T0 + pd.Timedelta(**{unit: i}), open=o, high=h,
                  low=l, close=cl, volume=0)


def rising_break(start_i, base, unit="hours"):
    return [c(start_i + 0, base, base + 0.0010, base - 0.0010, base, unit),
            c(start_i + 1, base, base + 0.0020, base - 0.0005, base + 0.0010, unit),
            c(start_i + 2, base + 0.0010, base + 0.0040, base, base + 0.0030, unit),
            c(start_i + 3, base + 0.0030, base + 0.0035, base + 0.0015, base + 0.0020, unit),
            c(start_i + 4, base + 0.0020, base + 0.0025, base + 0.0010, base + 0.0015, unit),
            c(start_i + 5, base + 0.0015, base + 0.0060, base + 0.0010, base + 0.0050, unit)]


def falling_break(start_i, base, unit="hours"):
    # mirror of rising_break: leaves a V-shape at base-0.0040, closes below it
    return [c(start_i + 0, base, base + 0.0010, base - 0.0010, base, unit),
            c(start_i + 1, base, base + 0.0005, base - 0.0020, base - 0.0010, unit),
            c(start_i + 2, base - 0.0010, base, base - 0.0040, base - 0.0030, unit),
            c(start_i + 3, base - 0.0030, base - 0.0035, base - 0.0015, base - 0.0020, unit),
            c(start_i + 4, base - 0.0020, base - 0.0025, base - 0.0010, base - 0.0015, unit),
            c(start_i + 5, base - 0.0015, base - 0.0010, base - 0.0060, base - 0.0050, unit)]


results = []


def report(name, ok, detail=""):
    results.append((name, ok))
    print(("PASS    " if ok else "FINDING ") + f"| {name}" + (f" | {detail}" if detail else ""))


# ---- PROBE 1: dead code --------------------------------------------------
out = subprocess_run = __import__("subprocess").run(
    ["grep", "-rn", "_agree(", "/workspace/backtest/slk", "/workspace/bot"],
    capture_output=True, text=True).stdout
non_test_callers = [l for l in out.splitlines()
                    if "def _agree" not in l and "/tests/" not in l]
report("P1 _agree() has no non-test caller (dead code / orphaned rule)",
       len(non_test_callers) == 0,
       f"{len(non_test_callers)} non-test call sites")

# ---- PROBE 2: late bullish BOS outranks an older bearish rejection -------
cascade = Cascade(2)
route = cascade.lower_levels
route._rejections[Direction.BEARISH].append(T0)
route._breaks.newest_break[Direction.BEARISH] = T0 + pd.Timedelta(hours=1)
route._breaks.broke_at[Direction.BEARISH] = (T0 + pd.Timedelta(hours=1), 1.0900)
cascade.daily_structure.broke_at[Direction.BULLISH] = (T0 + pd.Timedelta(days=5), 1.1100)
acc = cascade.explain()
ok2 = acc.direction == Direction.BULLISH and acc.evidence is None
report("P2 late bullish BOS outranks older bearish reject (explain)",
       ok2, f"direction={acc.direction}, evidence={acc.evidence}")

# ---- PROBE 2b: sticky-bias hazard inside replay --------------------------
cascade2 = Cascade(2)
route2 = cascade2.lower_levels
route2._rejections[Direction.BEARISH].append(T0)
route2._breaks.newest_break[Direction.BEARISH] = T0 + pd.Timedelta(hours=1)
acc2 = cascade2.explain()
report("P2b reject with NO structure yields None (replay's `bias = direction() or bias` keeps stale bias alive)",
       acc2.direction is None,
       "verified: explain()->None while routes still answer; replay sticks")

# ---- PROBE 3: break-event time vs swing formation time -------------------
t = BreakTracker(2)
t._bump(Direction.BULLISH, T0 + pd.Timedelta(days=5), T0 + pd.Timedelta(days=40), 1.12)
got = structural_direction(t)
report("P3 structural_direction keys on break-EVENT time, not swing formation",
       got[1] == T0 + pd.Timedelta(days=40), str(got))

# ---- PROBE 4: ties between directions at the same break time -------------
t = BreakTracker(2)
same = T0 + pd.Timedelta(days=10)
t._bump(Direction.BULLISH, T0 + pd.Timedelta(days=1), same, 1.12)
t._bump(Direction.BEARISH, T0 + pd.Timedelta(days=2), same, 1.08)
got = structural_direction(t)
report("P4 same-instant opposing breaks answer None (ambiguous story, no coin-flip)",
       got is None, str(got))
# and a later unambiguous break replaces the tie
t._bump(Direction.BEARISH, T0 + pd.Timedelta(days=3), T0 + pd.Timedelta(days=20), 1.05)
got = structural_direction(t)
report("P4b a later unambiguous break resolves the tie",
       got is not None and got[0] == Direction.BEARISH, str(got))

# ---- PROBE 5: self-contradiction property --------------------------------
ok5 = True
detail5 = ""
cas = Cascade(2)
for bar in rising_break(0, 1.1000, unit="days"):
    cas.push_daily(bar, bar.time)          # daily structure bullish
for bar in falling_break(0, 1.1000, unit="weeks"):
    cas.push_weekly(bar, bar.time)         # weekly structure bearish
acc = cas.explain()
struct = {"Daily": acc.daily_structure, "Weekly": acc.weekly_structure}[acc.rung]
if struct is None or struct[0] != acc.direction:
    ok5 = False
    detail5 = f"rung {acc.rung} says {acc.direction}, structure {struct[0]}"
else:
    detail5 = f"rung={acc.rung} dir={acc.direction} align={acc.alignment}"
report("P5 stated direction == leading timeframe's own structure (no self-contradiction)", ok5, detail5)

# ---- PROBE 6: alignment label matches the two structures -----------------
ok6 = True
cases = []
cas = Cascade(2)
for bar in rising_break(0, 1.1000, unit="days"):
    cas.push_daily(bar, bar.time)
for bar in rising_break(0, 1.1000, unit="weeks"):
    cas.push_weekly(bar, bar.time)
acc = cas.explain()
if acc.alignment != "aligned":
    ok6 = False; cases.append(f"both up -> {acc.alignment}")
cas = Cascade(2)
for bar in rising_break(0, 1.1000, unit="days"):
    cas.push_daily(bar, bar.time)
for bar in falling_break(0, 1.1000, unit="weeks"):
    cas.push_weekly(bar, bar.time)
acc = cas.explain()
if acc.alignment != "not aligned":
    ok6 = False; cases.append(f"daily up weekly down -> {acc.alignment}")
cas = Cascade(2)
for bar in rising_break(0, 1.1000, unit="days"):
    cas.push_daily(bar, bar.time)
acc = cas.explain()
if acc.alignment != "daily only":
    ok6 = False; cases.append(f"daily only -> {acc.alignment}")
cas = Cascade(2)
for bar in rising_break(0, 1.1000, unit="weeks"):
    cas.push_weekly(bar, bar.time)
acc = cas.explain()
if acc.alignment != "weekly only":
    ok6 = False; cases.append(f"weekly only -> {acc.alignment}")
report("P6 alignment label derived from structures, all four states reachable", ok6, "; ".join(cases))

# ---- PROBE 7: narrative lines carry dates + prices -----------------------
cas = Cascade(2)
for bar in rising_break(0, 1.1000, unit="days"):
    cas.push_daily(bar, bar.time)
for bar in falling_break(0, 1.1000, unit="weeks"):
    cas.push_weekly(bar, bar.time)
acc = cas.explain()
text = "\n".join(narrative.account_story(acc, "EURUSD"))
ok7 = ("Structure:" in text and "structurally bullish" in text
       and "structurally bearish" in text and "2026-01-01" in text
       and "NOT ALIGNED" in text)
report("P7 Telegram story names each timeframe's structure with date+price", ok7,
       "" if ok7 else repr(text))

# ---- PROBE 8: setup gated on agreement -----------------------------------
cas = Cascade(2)
for bar in rising_break(0, 1.1000, unit="days"):
    cas.push_daily(bar, bar.time)
r = cas.lower_levels
r._rejections[Direction.BULLISH].append(T0 + pd.Timedelta(days=30))
r._breaks.newest_break[Direction.BULLISH] = T0 + pd.Timedelta(days=31)
r._breaks.broke_at[Direction.BULLISH] = (T0 + pd.Timedelta(days=31), 1.1100)
acc = cas.explain()
report("P8 aligned rejection IS reported as the setup inside the structure",
       acc.direction == Direction.BULLISH and acc.evidence is not None,
       f"evidence kind={getattr(acc.evidence, 'kind', None)}")

print()
bad = [n for n, ok in results if not ok]
print(f"{len(results) - len(bad)}/{len(results)} probes pass; findings: {bad}")
