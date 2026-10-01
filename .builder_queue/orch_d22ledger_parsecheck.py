"""Assess parseability of historical ledger prose entries (D22-LEDGER-1 backfill feasibility)."""
import json
import re

d = json.load(open(".builder_queue/DEFECT-22_arc_legA_instability.json"))
entries = [(k, v) for k, v in d.items() if isinstance(v, str) and k.startswith("ledger_")]
print("prose entries:", len(entries))

leg_re = re.compile(r"leg #(\d+)")
seed_re = re.compile(r"seed (\d+)")
head_re = re.compile(r"head ([0-9a-f]{7,40})")
crash_re = re.compile(r"faulthandler_crashes=(\d+)")
crash2_re = re.compile(r"(?<!faulthandler_)crashes=(\d+)")
oom_re = re.compile(r"oom_kill_delta=(\d+)")
mem_re = re.compile(r"mem_peak=([\d,]+)")

missing_leg, parsed, unparsed = [], [], []
for k, v in entries:
    m = leg_re.search(v)
    if not m:
        missing_leg.append(k)
        continue
    leg = int(m.group(1))
    seed_m = seed_re.search(v)
    head_m = head_re.search(v)
    crash_m = crash_re.search(v) or crash2_re.search(v)
    oom_m = oom_re.search(v)
    mem_m = mem_re.search(v)
    rec = {
        "key": k,
        "leg": leg,
        "seed": seed_m.group(1) if seed_m else None,
        "head": head_m.group(1) if head_m else None,
        "green": "GREEN:" in v,
        "red": bool(re.search(r"\bRED\b", v)),
        "crashes": crash_m.group(1) if crash_m else None,
        "oom": oom_m.group(1) if oom_m else None,
        "mem": mem_m.group(1) if mem_m else None,
    }
    parsed.append(rec)

print("entries with leg #:", len(parsed))
print("entries missing 'leg #':", missing_leg)
legs = sorted(r["leg"] for r in parsed)
print("leg range:", legs[:5], "...", legs[-5:], "count unique:", len(set(legs)))
dupes = [l for l in set(legs) if legs.count(l) > 1]
print("duplicate leg numbers:", dupes)
n_green = sum(1 for r in parsed if r["green"])
n_red = sum(1 for r in parsed if r["red"] and not r["green"])
n_amb = sum(1 for r in parsed if not r["green"] and not r["red"])
print(f"green={n_green} red={n_red} ambiguous={n_amb}")
fields_missing = {
    "seed": sum(1 for r in parsed if not r["seed"]),
    "head": sum(1 for r in parsed if not r["head"]),
    "crashes": sum(1 for r in parsed if not r["crashes"]),
    "oom": sum(1 for r in parsed if not r["oom"]),
    "mem": sum(1 for r in parsed if not r["mem"]),
}
print("fields missing across parsed:", fields_missing)
maxleg = max(legs)
# consecutive green from newest leg backwards
by_leg = {r["leg"]: r for r in parsed}
streak = 0
for l in range(maxleg, 0, -1):
    r = by_leg.get(l)
    if r is None:
        print("gap at leg", l, "- streak computation stops")
        break
    if r["green"]:
        streak += 1
    else:
        print("first non-green from top: leg", l, "green=", r["green"], "red=", r["red"])
        break
print("recomputed consecutive green from prose:", streak, "(hand-written was 51, legs_run 79)")
