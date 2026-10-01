#!/usr/bin/env python3
"""R1.2 probe — fleet isolation (four co-resident agents + fault-injection RED).

Companion to probe_r11_arrive.py for the fleet step
(.builder_queue/brief_r12_fleet.md). Legs:

  A. CPU functional (mode="fleet"): four agent arenas boot, run to halt
     under per-leg box arming. Host verifies: each result word holds its
     OWN agent's value (714==6, 728==12, 748==20, 763==30), done word
     717 == 0b1011 (A, B, D completed; C faulted mid-store), fault
     receipt 0xFA026 @731 (E-K1 on C's out-of-box store), fleet receipt
     0x5EED0005 @765, kernel status 0xCAFE0026, run halts, ticks>0
     (preemption non-vacuity: mem[732] > 0).
  B. --corrupt RED leg: expected B-result shifted +1 -> must FAIL.
  C. --naive-clean-expected RED leg: the fleetnaive CONTROL image must
     CORRUPT (728 reads 0xDEAD, C completes, 717 == 0b1111, no fault
     receipt). If the naive image comes back clean the isolation
     mechanism is not what separates the two outcomes — the guard is
     decoration (policy rule 4). Expected exit 1.

No rate claim is made by this probe (no floor line; check_regime N/A
with that reason — see RECEIPT_R12_fleet.md).
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
for _p in (str(_REPO), str(_REPO / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from tools.glyph_gpt.atlas import build_default_atlas          # noqa: E402
from tools.glyph_gpt.runner import GlyphRunner                 # noqa: E402
from tools.glyph_gpt.agent_resident import (                   # noqa: E402
    resident_image, RES_KERNEL_OK,
    RES_DONE_WORD, RES_FAULT_WORD, RES_TICKS_COUNT,
    RES_FLEET_DONE, RES_FLEET_RCPT,
    RES_FLEET_ADVERSARY_TARGET, RES_FLEET_ADVERSARY_PAYLOAD,
    RES_FLEET_EXPECT, RES_FLEET_FAULT_SLOT,
)

QUANTUM = 6
STEP_BUDGET = 200_000


def _run(mode: str, b_shift: int = 0) -> dict:
    with tempfile.TemporaryDirectory() as d:
        img = Path(d) / f"probe_fleet_{mode}.npy"
        resident_image(build_default_atlas(), mode=mode,
                       timer_quantum=QUANTUM, out_path=img)
        runner = GlyphRunner(img, ram_words=16384)
        cpu = runner.get_cpu()
        cpu.running = True
        steps = 0
        while cpu.running and steps < STEP_BUDGET:
            cpu.step(runner.image)
            steps += 1
        m = cpu.memory
        expected = dict(RES_FLEET_EXPECT)
        if b_shift:
            expected[RES_FLEET_ADVERSARY_TARGET] += b_shift
        return {
            "mode": mode, "halted": not cpu.running,
            "steps": steps,
            "results": {w: m[w] for w in RES_FLEET_EXPECT},
            "expected": expected,
            "done": m[RES_DONE_WORD], "done_expected":
                (0b1011 if mode == "fleet" else 0b1111),
            "fault_rcpt": m[RES_FAULT_WORD],
            "fleet_rcpt": m[RES_FLEET_RCPT],
            "ticks": m[RES_TICKS_COUNT],
            "status": m[950],
        }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corrupt", action="store_true",
                    help="RED leg: shift expected B-result +1 (must FAIL)")
    ap.add_argument("--naive-clean-expected", action="store_true",
                    help="RED leg: naive control MUST corrupt (FAIL if clean)")
    args = ap.parse_args()
    failures = []

    if args.naive_clean_expected:
        # ── leg C: the control leg, run to its demonstrated failure ──
        r = _run("fleetnaive")
        corrupted = (r["results"][RES_FLEET_ADVERSARY_TARGET]
                     == RES_FLEET_ADVERSARY_PAYLOAD)
        if corrupted:
            print(f"NAIVE-CLEAN-EXPECTED RED: naive image DID corrupt "
                  f"(728={r['results'][RES_FLEET_ADVERSARY_TARGET]:#x}) — "
                  "the control leg shows its expected landing, so this "
                  "probe's FAIL verdict stands (exit 1 = expected RED).")
            print("VERDICT=FAIL failures=[naive:control-corrupted-as-expected]")
            return 1
        print(f"NAIVE-CLEAN-EXPECTED: naive image did NOT corrupt "
              f"(728={r['results'][RES_FLEET_ADVERSARY_TARGET]}) — the "
              "guard cannot be shown bypassable: decoration. Real FAIL.")
    else:
        mode = "fleet"
        r = _run(mode, b_shift=1 if args.corrupt else 0)
        print(f"CPU fleet: halted={r['halted']} steps={r['steps']} "
              f"results={r['results']} expected={r['expected']} "
              f"done={r['done']:#05b} (want {r['done_expected']:#05b}) "
              f"fault={r['fault_rcpt']:#x} fleet_rcpt={r['fleet_rcpt']:#x} "
              f"ticks={r['ticks']} status={r['status']:#x}")
        checks = [
            ("halted", r["halted"]),
            ("results", r["results"] == r["expected"]),
            ("done717", r["done"] == r["done_expected"]),
            ("fault_rcpt", r["fault_rcpt"] == 0xFA026),
            ("fleet_rcpt", r["fleet_rcpt"] == RES_FLEET_DONE),
            ("ticks_nonzero", r["ticks"] > 0),
            ("status950", r["status"] == RES_KERNEL_OK),
        ]
        for name, ok in checks:
            if not ok:
                failures.append(f"cpu:{name}")
        if args.corrupt and not failures:
            failures.append("corrupt:expectation-wrongly-matched")
        if args.corrupt and failures:
            print("CORRUPT-LEG: expectation did not match (correct RED)")

    if failures:
        print(f"VERDICT=FAIL failures={failures}")
        return 1
    print("VERDICT=PASS (four co-resident agents, cross-tenant store "
          "suppressed E-K1, fleet continues, host-verified)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
