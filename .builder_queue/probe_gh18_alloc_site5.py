#!/usr/bin/env python3
"""DEFECT-23 follow-on: find the WORD the paged walk used as a page-table entry.

Stage 4 (`output/probe_gh18_alloc_site4_2026091314.json`) pinned the two memory extensions to
step 298 (USER, pc (20,23)) and step 371 (SUPER, pc (24,22)), and stage 3 gave their sizes. From
`paddr = pfn * PAGE_WORDS + offset` the implied page-frame numbers are pfn=67,593 and pfn=526,602.

This probe replays the same image one instruction at a time and, at each extension, scans the
engine's **base RAM** (`cpu.memory[:ram_words]`, where a page table must live) for every word
whose `>> 8` equals the implied pfn -- i.e. the value the walker used as a PTE. It prints each
hit's index, raw value and low-byte flag bits, so the ticket can name the word instead of a range.

Writes output/probe_gh18_alloc_site5_<seed>.json.
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
RAM_WORDS = 16384
MAX_STEPS = 5000
PAGE_WORDS = 256


def main() -> int:
    from tools.glyph_gpt.atlas import build_default_atlas
    from tools.glyph_gpt.baker import syscall_abi_kernel_image
    from tools.glyph_gpt.runner import GlyphRunner

    tmp = Path(tempfile.mkdtemp(prefix="gh18_alloc5_"))
    out = tmp / "paged.npy"
    syscall_abi_kernel_image(build_default_atlas(), mode="paged_dispatch",
                             timer_quantum=35, out_path=out)
    runner = GlyphRunner(out, ram_words=RAM_WORDS)
    cpu = runner.get_cpu()
    cpu.running = True
    events: list[dict] = []
    steps = 0
    while cpu.running and steps < MAX_STEPS:
        before = len(cpu.memory)
        cpu.step(runner.image)
        steps += 1
        after = len(cpu.memory)
        if after != before:
            paddr = after - PAGE_WORDS
            pfn = paddr // PAGE_WORDS
            hits = []
            for i in range(RAM_WORDS):
                v = cpu.memory[i]
                if isinstance(v, int) and (v >> 8) == pfn:
                    hits.append({"index": i, "value": v, "hex": hex(v & 0xFFFFFFFF),
                                 "flags_low8": v & 0xFF})
            events.append({
                "step": steps,
                "pc": [int(cpu.pc[0]), int(cpu.pc[1])],
                "mode": int(cpu.mode),
                "grew_words": after - before,
                "implied_paddr": paddr,
                "implied_pfn": pfn,
                "ram_pte_hits": hits,
            })
            print(f"  step {steps:5d} pc={tuple(events[-1]['pc'])} mode={cpu.mode} "
                  f"pfn={pfn} ram_hits={len(hits)} "
                  f"{[ (h['index'], h['hex'], h['flags_low8']) for h in hits[:6] ]}", flush=True)

    payload = {"seed": SEED, "steps_run": steps, "events": events,
               "ram_words_scanned": RAM_WORDS, "argv": " ".join(sys.argv)}
    art = REPO / "output" / f"probe_gh18_alloc_site5_{SEED}.json"
    art.write_text(json.dumps(payload, indent=1))
    print(f"\nsteps={steps} events={len(events)}")
    print(f"artifact: {art}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
