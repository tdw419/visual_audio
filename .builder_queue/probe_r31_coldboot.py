"""R3.1 cold-boot gate — cold boot to agent-fleet-ready on the GlyphRunner
substrate, measured against the roadmap's <60s budget.

PRODUCT_ROADMAP.md R3.1: "Cold boot to agent-fleet-ready <60s on this
hardware, measured, receipts with floors attached (policy rule 1)."

Cold chain (rep 1 includes wgpu pipeline creation — that IS the cold
boot): build_default_atlas() -> resident_image(mode="fleet",
timer_quantum=6) -> GlyphRunner(img, ram_words=16384) -> run_wgsl to
halt. "Fleet-ready" = the LANDED fleet gate's own readiness words,
host-verified from receipt["ram"]: receipt 0x5EED0005 @765, done bits
0b1011 @717, results == RES_FLEET_EXPECT (y=x*(x+1), seeds 2/3/4/5).

Exit contract: 0 = GREEN (all reps fleet-ready AND cold total < budget),
1 = RED (budget miss, verifier rejection, or no RAM). RED legs:
--budget-ms 500 (real threshold violation), --corrupt-verify (the
verifier must REJECT a measuredly-good boot when its expectations are
corrupted — proves the readiness check is load-bearing).

No production lines are touched: measurement over the LANDED artifacts
at HEAD, same rule as R1.3.
"""
import argparse
import json
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tools"))

from tools.glyph_gpt.atlas import build_default_atlas          # noqa: E402
from tools.glyph_gpt.runner import GlyphRunner                 # noqa: E402
from tools.glyph_gpt.agent_resident import (                   # noqa: E402
    resident_image, RES_FLEET_RCPT, RES_DONE_WORD, RES_FLEET_DONE,
    RES_FLEET_EXPECT, RES_FAULT_WORD,
)

BUDGET_MS_DEFAULT = 60_000.0  # R3.1's roadmap budget
FLOORS = Path(__file__).resolve().parent / "floors_authoritative.json"
REPS = 3


def floors_age_line() -> str:
    with open(FLOORS) as f:
        d = json.load(f)
    return (f"floors: floors_authoritative.json measured_at="
            f"{d['measured_at']} (12h window); wgsl floor "
            f"{d['floor_us']['glyphrunner_wgsl_step']} us/step spaced, "
            f"{d['floor_us']['glyphrunner_wgsl_step_tput']} us/step tput")


def fleet_ready(ram, corrupt: bool = False) -> tuple[bool, str]:
    """Host-verified fleet readiness against the frozen words."""
    if not ram:
        return False, "no ram in receipt"
    rcpt_exp = RES_FLEET_DONE ^ 0x5A5A if corrupt else RES_FLEET_DONE
    results = {w: ram[w] for w in RES_FLEET_EXPECT}
    exp = ({w: (v ^ 0x5A5A) for w, v in RES_FLEET_EXPECT.items()}
           if corrupt else RES_FLEET_EXPECT)
    ok = (ram[RES_FLEET_RCPT] == rcpt_exp
          and ram[RES_DONE_WORD] == 0b1011
          and results == exp)
    detail = (f"ram[765]=0x{ram[RES_FLEET_RCPT]:08x} "
              f"(expect 0x{rcpt_exp:08x}) "
              f"ram[717]=0b{ram[RES_DONE_WORD]:b} "
              f"ram[731]=0x{ram[RES_FAULT_WORD]:x} results={results}")
    return ok, detail


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--budget-ms", type=float, default=BUDGET_MS_DEFAULT,
                    help="R3.1 budget in ms (default 60000)")
    ap.add_argument("--corrupt-verify", action="store_true",
                    help="RED leg: corrupt the verifier's expectations; "
                         "a GOOD boot must then be REJECTED (exit 1)")
    args = ap.parse_args()

    print(f"R3.1 cold-boot probe: budget={args.budget_ms:.0f} ms "
          f"reps={REPS} corrupt_verify={args.corrupt_verify}")
    print(floors_age_line())

    colds, warms, steps_all, ready_all = [], [], [], True
    with tempfile.TemporaryDirectory() as d:
        for rep in range(REPS):
            t0 = time.perf_counter()
            atlas = build_default_atlas()
            t1 = time.perf_counter()
            img_path = Path(d) / f"fleet_r31_{rep}.npy"
            resident_image(atlas, mode="fleet", timer_quantum=6,
                           out_path=img_path)
            t2 = time.perf_counter()
            runner = GlyphRunner(img_path, ram_words=16384)
            t3 = time.perf_counter()
            rec = runner.run_wgsl(max_steps=5000)
            t4 = time.perf_counter()
            ok, detail = fleet_ready(rec.get("ram"),
                                     corrupt=args.corrupt_verify)
            cold_ms = (t4 - t0) * 1000.0
            steps = rec.get("steps", 0)
            print(f"rep{rep}: atlas={(t1-t0)*1000:.1f} bake={(t2-t1)*1000:.1f} "
                  f"init={(t3-t2)*1000:.1f} run={(t4-t3)*1000:.1f} "
                  f"COLD={cold_ms:.1f} ms steps={steps} halted="
                  f"{rec.get('halted')} ready={ok}")
            print(f"  {detail}")
            ready_all = ready_all and ok
            if rec.get("error"):
                print(f"  engine error: {rec['error']}")
                ready_all = False
            steps_all.append(steps)
            if rep == 0:
                colds.append(cold_ms)  # rep 1 = THE cold boot (pipeline creation)
                warms = []
            else:
                warms.append(cold_ms)

    if not steps_all:
        print("R3.1 COLD BOOT: FAIL (no reps completed)")
        sys.exit(1)

    cold_total = colds[0]
    steps = steps_all[0]
    secs = cold_total / 1000.0
    rate = steps / secs if secs > 0 else 0.0
    us_per_step = (cold_total * 1000.0) / steps if steps else float("inf")
    # LEG line, boot-shaped (R1.3 hygiene lesson): rate from THIS leg's own
    # wall-clock and step count; path = glyphrunner_wgsl_step (the per-step
    # protocol run_wgsl uses; 1 dispatch + 1 blocking readback per step).
    # check_regime computes implied per-roundtrip = us_per_rep / 1.
    # NOTE: the cold leg necessarily includes bake+init (~tens of ms), so
    # its implied per-step cost sits ABOVE the floor — that is honest:
    # a boot leg costs more than a bare step.
    leg_line = (f"LEG cold_boot {rate:,.0f} steps/s "
                f"{us_per_step:,.1f} us/rep glyphrunner_wgsl_step x1")
    print(leg_line)
    if warms:
        print(f"warm reps (pipeline reused, NOT the gate): "
              + ", ".join(f"{w:.1f} ms" for w in warms))
    print(f"COLD_BOOT_TOTAL={cold_total:.1f} ms "
          f"(budget {args.budget_ms:.0f} ms)")

    budget_ok = cold_total < args.budget_ms
    if args.corrupt_verify:
        # RED leg contract: corrupted verifier MUST reject the good boot.
        if ready_all:
            print("R3.1 COLD BOOT: FAIL-RED (corrupt-verify leg accepted a "
                  "good boot — the readiness check is NOT load-bearing)")
            sys.exit(1)
        print("R3.1 corrupt-verify RED leg: verifier REJECTED the boot "
              "(correct discrimination)")
        sys.exit(1)  # a corrupted-verifier run always ends RED by contract

    if not ready_all:
        print("R3.1 COLD BOOT: FAIL (not fleet-ready within budget)")
        sys.exit(1)
    if not budget_ok:
        print(f"R3.1 COLD BOOT: FAIL (cold {cold_total:.1f} ms >= budget "
              f"{args.budget_ms:.0f} ms)")
        sys.exit(1)
    print(f"R3.1 COLD BOOT: PASS (cold {cold_total:.1f} ms < "
          f"{args.budget_ms:.0f} ms, fleet-ready host-verified)")
    sys.exit(0)


if __name__ == "__main__":
    main()
