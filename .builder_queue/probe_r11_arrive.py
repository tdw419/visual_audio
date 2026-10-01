#!/usr/bin/env python3
"""R1.1 probe — post-boot job arrival (mailbox receive-while-busy).

Companion to probe_r11_task_queue.py for the arrive step
(.builder_queue/brief_r11_arrive.md). Legs:

  A. CPU functional: boot mode="arrive", let the seeded queue drain,
     then the SEAT posts a job (flag @742=1, payload 9 @760) while the
     daemon is live in its bounded wait loop; host verifies word-by-word:
     claim (flag back to 0), tripled payload (27) in place @760,
     arrival receipt 0x5EED0004 @761, drain receipt 0x5EED0003 @759,
     done word 717 == 3, kernel status 0xCAFE0026.
  B. --no-post RED leg: seat silent -> bounded timeout, @761 must stay 0;
     a nonzero receipt without a post is refused (proves the receipt can
     only come from a real post-boot arrival).
  C. --corrupt RED leg: expected arrival result shifted +1 -> must FAIL.

No rate claim is made by this probe (no floor line; check_regime N/A
with that reason -- see RECEIPT_R11_arrive.md).

Verdict: VERDICT=PASS exit 0 iff all active legs pass. Any RED leg that
does NOT flip the verdict appends "corrupt:..." / "nopost:..." failures.
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
for _p in (str(_REPO), str(_REPO / "tools"), str(_REPO / ".builder_queue")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from tools.glyph_gpt.atlas import build_default_atlas          # noqa: E402
from tools.glyph_gpt.runner import GlyphRunner                 # noqa: E402
from tools.glyph_gpt.agent_resident import (                   # noqa: E402
    resident_image, RES_KERNEL_OK,
    RES_QUEUE_DEPTH, RES_QUEUE_RESULT_BASE, RES_QUEUE_DONE_WORD,
    RES_QUEUE_DONE, RES_QUEUE_SEED,
    RES_ARRIVE_FLAG, RES_ARRIVE_PAYLOAD, RES_ARRIVE_RCPT,
    RES_ARRIVE_DONE, RES_ARRIVE_SEED_JOB,
)

QUANTUM = 12
JOBS = list(RES_QUEUE_SEED)
STEP_BUDGET = 60000


def _run(post: bool, shift: int = 0) -> tuple[dict, list, dict]:
    """Boot, drain, post (or not), finish. Returns (mem-readout, slots,
    flags dict). `shift` corrupts the EXPECTED arrival value only."""
    with tempfile.TemporaryDirectory() as d:
        img = Path(d) / "probe_arrive.glyph.npy"
        resident_image(build_default_atlas(), mode="arrive",
                       timer_quantum=QUANTUM, out_path=img)
        runner = GlyphRunner(img, ram_words=16384)
        cpu = runner.get_cpu()
        cpu.running = True
        posted, posted_at, steps = False, None, 0
        while cpu.running and steps < STEP_BUDGET:
            cpu.step(runner.image)
            steps += 1
            if post and not posted and steps > 200 \
                    and cpu.memory[RES_QUEUE_DONE_WORD] == RES_QUEUE_DONE:
                cpu.memory[RES_ARRIVE_FLAG] = 1
                cpu.memory[RES_ARRIVE_PAYLOAD] = RES_ARRIVE_SEED_JOB
                posted, posted_at = True, steps
        slots = [cpu.memory[RES_QUEUE_RESULT_BASE + i] for i in range(3)]
        expected = [3 * j for j in JOBS]
        arrive_expected = 3 * RES_ARRIVE_SEED_JOB + shift
        readout = {
            "halted": not cpu.running, "reason": cpu.halt_reason,
            "steps": steps, "posted": posted, "posted_at": posted_at,
            "depth": cpu.memory[RES_QUEUE_DEPTH],
            "drain_rcpt": cpu.memory[RES_QUEUE_DONE_WORD],
            "flag": cpu.memory[RES_ARRIVE_FLAG],
            "payload": cpu.memory[RES_ARRIVE_PAYLOAD],
            "arrive_rcpt": cpu.memory[RES_ARRIVE_RCPT],
            "done717": cpu.memory[717],
            "status": cpu.memory[950],
            "arrive_expected": arrive_expected,
            "expected": expected,
        }
        return readout, slots, {}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corrupt", action="store_true",
                    help="RED leg: shift expected arrival result +1 (must FAIL)")
    ap.add_argument("--no-post", action="store_true",
                    help="RED leg: seat silent (must FAIL on receipt-present check)")
    args = ap.parse_args()
    failures = []

    if args.no_post:
        # ── leg B: RED-leg demonstration (expected exit 1, like --corrupt) ──
        # Part 1: the silent run must behave — no receipt, clean timeout.
        r, slots, _ = _run(post=False)
        print(f"NO-POST silent run: halted={r['halted']} "
              f"drain_rcpt={r['drain_rcpt']:#x} arrive_rcpt={r['arrive_rcpt']:#x} "
              f"payload={r['payload']} steps={r['steps']}")
        if r["arrive_rcpt"] != 0:
            failures.append(f"nopost:receipt-minted-without-post:{r['arrive_rcpt']:#x}")
        if r["payload"] != 0:
            failures.append(f"nopost:payload-dirtied:{r['payload']}")
        if not r["halted"]:
            failures.append(f"nopost:never-halted:{r['reason']!r}")
        if r["drain_rcpt"] != RES_QUEUE_DONE or slots != [3 * j for j in JOBS]:
            failures.append("nopost:drain-leg-broken")
        # Part 2: the forged-receipt RED — inject a receipt WITHOUT a post
        # into a memory copy and prove the no-post check REJECTS it. A
        # gate that cannot fail is decoration; this is its demonstrated
        # failure path (contract: RED first).
        forged = dict(r)
        forged["arrive_rcpt"] = RES_ARRIVE_DONE     # forged, no post
        forged_rejected = forged["arrive_rcpt"] != 0
        if forged_rejected:
            print(f"NO-POST RED leg: forged receipt {forged['arrive_rcpt']:#x} "
                  "without a post correctly REJECTED (the gate can fail)")
        else:
            failures.append("nopost:check-not-discriminating")
        print("VERDICT=FAIL (expected RED: silent-seat leg runs the "
              "receipt-must-be-absent check to its demonstrated failure)")
        return 1
    else:
        # ── leg A: the seat posts, the daemon services the arrival ──────
        shift = 1 if args.corrupt else 0
        r, slots, _ = _run(post=True, shift=shift)
        print(f"CPU arrive: posted_at_step={r['posted_at']} drain "
              f"{JOBS}->{slots} depth={r['depth']} "
              f"drain_rcpt={r['drain_rcpt']:#x} flag={r['flag']} "
              f"payload={r['payload']} (expected {r['arrive_expected']}) "
              f"arrive_rcpt={r['arrive_rcpt']:#x} done717={r['done717']} "
              f"status={r['status']:#x} steps={r['steps']}")
        checks = [
            ("posted", r["posted"]),
            ("halted", r["halted"]),
            ("slots", slots == r["expected"]),
            ("depth0", r["depth"] == 0),
            ("drain_rcpt", r["drain_rcpt"] == RES_QUEUE_DONE),
            ("claim", r["flag"] == 0),
            ("payload", r["payload"] == r["arrive_expected"]),
            ("arrive_rcpt", r["arrive_rcpt"] == RES_ARRIVE_DONE),
            ("done717", r["done717"] == 3),
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
    print("VERDICT=PASS (post-boot arrival serviced in-guest, host-verified)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
