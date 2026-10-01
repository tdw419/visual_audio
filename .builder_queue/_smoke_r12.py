"""R1.2 fleet smoke — throwaway harness, run manually (not a test file).

Boots the fleet / fleetnaive images on the real GlyphRunner and dumps
the words the brief's gate clause asserts on.
"""
from __future__ import annotations

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
    resident_image, RES_FLEET_DONE, RES_FLEET_RCPT,
    RES_FLEET_ADVERSARY_TARGET, RES_FLEET_BOXES, RES_FLEET_EXPECT,
)

QUANTUM = 6
BUDGET = 200_000


def run(mode: str) -> dict:
    with tempfile.TemporaryDirectory() as d:
        img = Path(d) / f"{mode}.npy"
        resident_image(build_default_atlas(), mode=mode,
                       timer_quantum=QUANTUM, out_path=img)
        runner = GlyphRunner(img, ram_words=16384)
        cpu = runner.get_cpu()
        cpu.running = True
        steps = 0
        while cpu.running and steps < BUDGET:
            cpu.step(runner.image)
            steps += 1
        mem = cpu.memory
        done_w = RES_FLEET_BOXES[0][3] - 1 + 1  # 716 is A's done; fleet done word is 717
        return {
            "mode": mode, "halted": not cpu.running, "steps": steps,
            "714_A_result": mem[714], "728_B_result": mem[728],
            "748_C_result": mem[748], "763_D_result": mem[763],
            "717_done": mem[717],
            "731_fault_receipt": hex(mem[731]) if len(mem) > 731 else "?",
            "765_receipt": hex(mem[RES_FLEET_RCPT]) if len(mem) > RES_FLEET_RCPT else "?",
            "expected": RES_FLEET_EXPECT,
            "status": hex(mem[737]) if len(mem) > 737 else "?",
            "halt_reason": getattr(cpu, "halt_reason", None),
        }


if __name__ == "__main__":
    for m in ("fleet", "fleetnaive"):
        r = run(m)
        print("=" * 60)
        for k, v in r.items():
            print(f"  {k}: {v}")
