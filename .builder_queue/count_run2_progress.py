#!/usr/bin/env python3
"""DEFECT-22 instrument cross-check (builder cron af3e62239ce2, 2026-09-13).

Two instruments disagree about which test owned the run-2 SIGSEGV:
  (a) pytest's -q progress stream (dots)  -> crash position by counting completions
  (b) faulthandler's Python traceback     -> crash position by naming the frame
this script quantifies (a) exactly and maps it onto the deterministic collection
order. CORRECTED 2026-09-13 06:2x tick (builder cron af3e62239ce2): the premise
that stood here — "no pytest-randomly is installed, so order == collection order"
— is FALSE. pytest-randomly 4.0.1 IS loaded for /usr/bin/python3, so the arc's
run order is a per-run random permutation and this script's mapping is onto the
COLLECTION order, not run 2's order. See
systems/RECEIPT_DEFECT22_ORDER_RANDOMIZATION_MEASURED.md § 1-2. So the
disagreement can be reported as a number instead of an eyeballed dot count —
but it must be read as a lower bound on position, never as "test #N ran here".
"""
import sys
from pathlib import Path

run_file = Path(sys.argv[1])
order_file = Path(sys.argv[2])

# collection order (1-based)
order = []
for ln in order_file.read_text().splitlines():
    if "::" in ln:
        order.append(ln.split(":", 1)[1].strip())  # strip the grep -n index

dots = skips = 0
crash_line_no = None
for i, ln in enumerate(run_file.read_text().splitlines(), start=1):
    if "Fatal Python error" in ln:
        crash_line_no = i
        # count only the progress chars that precede the faulthandler text
        head = ln.split("Fatal Python error")[0]
        dots += head.count(".")
        skips += head.count("s")
        break
    if ln.strip() and all(c in ".s" for c in ln.strip()):
        dots += ln.count(".")
        skips += ln.count("s")
    else:
        # progress lines carry a "[ NN%]" suffix; count their leading dots
        lead = ln.split("[")[0]
        if lead and all(c in ".s " for c in lead):
            dots += lead.count(".")
            skips += lead.count("s")

completed = dots + skips
print(f"faulthandler text first appears on line {crash_line_no}")
print(f"progress chars captured before it: {dots} dots + {skips} skips = {completed} completed")
nxt = completed  # 0-based index of the test that was executing when it died
if 0 <= nxt < len(order):
    print(f"=> dot-position inference: executing item #{nxt + 1} = {order[nxt]}")
else:
    print(f"=> dot-position inference: item #{nxt + 1} (out of {len(order)} collected)")
for i, item in enumerate(order, start=1):
    if "gh22_driver_abi_image_bakes" in item:
        print(f"=> faulthandler inference:   executing item #{i} = {item}")
print(f"=> disagreement span: {abs(nxt + 1 - i)} items" if 0 <= nxt < len(order) else "")
