#!/usr/bin/env python3
"""D22-LEDGER-1 backfill: derive machine-readable result objects from historical prose entries.

Mechanism-class action per the standing builder-loop delegation split (orchestrator's
judgment + verification; no policy decision involved — every field is parsed from text
already committed to the repo, and the parse counts are cross-checked below):
  - entries WITH 'leg #N' -> result object under key ledger_legN (parser + verifier below)
  - entries WITHOUT 'leg #N' (25 early series-state/notes entries, legs < 24 era and
    the 0055 no-run annotation) -> left as-is; history preserved
The original prose stays in place untouched. Streak is then derived by d22_ledger.recompute.

Verified pre-conditions (orch_d22ledger_parsecheck.py output, this run):
  80 prose entries; 55 carry 'leg #N' with exactly one duplicate pair (leg 24: the 0055
  no-run annotation vs the real 0100 leg-24 entry -> the annotation is excluded);
  51 entries carry an explicit 'GREEN:' marker (matches hand-written streak=51);
  legs #69/#70/#71 lack the marker but carry 'rc=0, 323 passed' (verified green by text);
  entries missing seed/head/crashes/oom/mem fields get null for that field only.
"""
import json
import re
import sys

sys.path.insert(0, ".builder_queue")
from d22_ledger import compute_derived_series_state  # noqa: E402

LEDGER = ".builder_queue/DEFECT-22_arc_legA_instability.json"

leg_re = re.compile(r"leg #(\d+)")
seed_re = re.compile(r"seed (\d+)")
head_re = re.compile(r"head ([0-9a-f]{7,40})")
crash_re = re.compile(r"faulthandler_crashes=(\d+)")
crash2_re = re.compile(r"(?<!faulthandler_)crashes=(\d+)")
oom_re = re.compile(r"oom_kill_delta=(\d+)")
mem_re = re.compile(r"mem_peak=([\d,]+)")
green_rc_re = re.compile(r"GREEN: rc=0")
rc0_passed_re = re.compile(r"rc=0, 323 passed")

d = json.load(open(LEDGER))

# The leg-24 duplicate: keep only the real leg entry (the one with GREEN/run data),
# not the 0055 no-run annotation.
seen_legs = {}
entries = []
for k, v in d.items():
    if not (isinstance(v, str) and k.startswith("ledger_")):
        continue
    m = leg_re.search(v)
    if not m:
        continue
    leg = int(m.group(1))
    is_real = bool(green_rc_re.search(v) or rc0_passed_re.search(v) or "RUN," in v)
    if leg in seen_legs:
        prev_k, prev_real = seen_legs[leg]
        if prev_real or not is_real:
            print(f"skip duplicate leg {leg}: keeping {prev_k}, skipping {k}")
            continue
    seen_legs[leg] = (k, is_real)
    entries.append((k, v, leg))

backfilled = 0
for k, v, leg in entries:
    key = f"ledger_leg{leg}"
    if key in d and isinstance(d[key], dict):
        continue  # already migrated
    seed_m = seed_re.search(v)
    head_m = head_re.search(v)
    crash_m = crash_re.search(v) or crash2_re.search(v)
    oom_m = oom_re.search(v)
    mem_m = mem_re.search(v)
    is_green = bool(green_rc_re.search(v) or rc0_passed_re.search(v))
    entry = {
        "ts": None,  # prose carries no ISO timestamp; backfilled entries are ts-less
        "leg": leg,
        "seed": int(seed_m.group(1)) if seed_m else None,
        "head": head_m.group(1) if head_m else None,
        "crashes": int(crash_m.group(1)) if crash_m else 0,
        "oom_kill_delta": int(oom_m.group(1)) if oom_m else 0,
        "mem_peak": int(mem_m.group(1).replace(",", "")) if mem_m else None,
        "verdict": "green" if is_green else "unknown",
        "backfilled_from": k,
    }
    d[key] = entry
    backfilled += 1

d["series_state"] = compute_derived_series_state(d)
with open(LEDGER, "w") as f:
    json.dump(d, f, indent=2)

ss = d["series_state"]
print(f"backfilled {backfilled} result objects; derived series_state: "
      f"legs_run={ss['legs_run']} streak={ss['consecutive_worker_scope_green']} "
      f"last_red={ss['last_red']}")
