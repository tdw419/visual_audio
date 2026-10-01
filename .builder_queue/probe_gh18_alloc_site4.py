#!/usr/bin/env python3
"""DEFECT-22 follow-on, stage 4: pin the STEP at which the paged run's memory list explodes.

Stage 3 (`output/probe_gh18_alloc_site3_2026091314.json`) showed `GlyphRunner.run()` on the
`paged_dispatch` image grows the engine's flat `memory` list from 16,384 to **134,810,550**
words (1.08 GB of pointers) while holding only **27** nonzero words -- the store path is
`tools/glyph_isa_v2.py:740-743` (`paddr = pfn * PAGE_WORDS + offset` then
`self.memory.extend([0] * (paddr + PAGE_WORDS - len(self.memory)))`).

This stage steps the SAME image one instruction at a time (no max_instructions cap) and
records every step whose store extends `memory`: step index, packed pixel PC, mode
(0=SUPER / 1=USER), and the before/after word counts. Writes
output/probe_gh18_alloc_site4_<seed>.json.

Scope: `syscall_abi_kernel_image(mode="paged_dispatch", timer_quantum=35)` driven by
`GlyphRunner(..., ram_words=16384)` -- the exact shape of
`tests/test_gh18_syscall_abi.py::test_gh18_syscall_table_window_reserved` (the only arc test
that uses this mode).
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
for _p in (str(REPO), str(REPO / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

SEED = int(sys.argv[sys.argv.index("--seed") + 1]) if "--seed" in sys.argv else 0
MAX_STEPS = 5000


def main() -> int:
    from tools.glyph_gpt.atlas import build_default_atlas
    from tools.glyph_gpt.baker import syscall_abi_kernel_image
    from tools.glyph_gpt.runner import GlyphRunner

    tmp = Path(tempfile.mkdtemp(prefix="gh18_alloc4_"))
    out = tmp / "paged.npy"
    syscall_abi_kernel_image(build_default_atlas(), mode="paged_dispatch",
                             timer_quantum=35, out_path=out)
    runner = GlyphRunner(out, ram_words=16384)
    cpu = runner.get_cpu()
    cpu.running = True
    growths: list[dict] = []
    steps = 0
    while cpu.running and steps < MAX_STEPS:
        before = len(cpu.memory)
        cpu.step(runner.image)
        steps += 1
        after = len(cpu.memory)
        if after != before:
            growths.append({
                "step": steps,
                "pc": [int(cpu.pc[0]), int(cpu.pc[1])],
                "mode": int(cpu.mode),
                "before_words": before,
                "after_words": after,
                "grew_words": after - before,
                "grow_gb_pointers": round((after - before) * 8 / 1e9, 3),
            })
            print(f"  step {steps:5d} pc={tuple(growths[-1]['pc'])} mode={cpu.mode} "
                  f"{before:>12} -> {after:>12} words (+{after - before})", flush=True)

    nonzero = sum(1 for m in cpu.memory if m)
    payload = {
        "seed": SEED,
        "steps_run": steps,
        "halted": not cpu.running,
        "growth_events": growths,
        "final_memory_words": len(cpu.memory),
        "final_nonzero_words": nonzero,
        "final_list_mb": round(sys.getsizeof(cpu.memory) / 1e6, 2),
        "argv": " ".join(sys.argv),
    }
    art = REPO / "output" / f"probe_gh18_alloc_site4_{SEED}.json"
    art.write_text(json.dumps(payload, indent=1))
    print(f"\nsteps={steps} halted={not cpu.running} final={len(cpu.memory)} words "
          f"({payload['final_list_mb']} MB list) nonzero={nonzero} events={len(growths)}")
    print(f"artifact: {art}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
