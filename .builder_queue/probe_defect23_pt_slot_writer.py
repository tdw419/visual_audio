#!/usr/bin/env python3
"""DEFECT-23 follow-on: NAME THE WRITER of RAM words 1538/1539 (PT window vpn 2/3).

Probe 5 (`output/probe_gh18_alloc_site5_2026091314.json`) pinned the *words* the paged walk
used as PTEs: RAM[1538]=0x01080907 and RAM[1539]=0x08090A07, both low byte 0x07 (V|W|U).
`.builder_queue/REPAIR_PENDING_defect23_paged_flat_memory.md` option 1 asks the two questions
this probe answers:

  Q1  Is the word already there BEFORE any instruction retires (bake/load provenance), or is it
      written at run time (and by which step / pc / mode)?
  Q2  If bake-side: does the baked image contain the same 24-bit triple as a pixel (which would
      make this a bake-layout stamp), and do baseline/admit modes carry it too (discrimination)?

Writes output/probe_defect23_pt_slot_writer_<seed>.json. Read-only wrt the repo and engine.
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parent.parent
for _p in (str(REPO), str(REPO / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

SEED = int(sys.argv[sys.argv.index("--seed") + 1]) if "--seed" in sys.argv else 2026091314
RAM_WORDS = 16384
MAX_STEPS = 400
PT_TARGETS = {1538: 0x01080907, 1539: 0x08090A07}
WIN_LO, WIN_HI = 1536, 1792


def bake(mode: str, tq: int = 35):
    from tools.glyph_gpt.atlas import build_default_atlas
    from tools.glyph_gpt.baker import syscall_abi_kernel_image

    tmp = Path(tempfile.mkdtemp(prefix="defect23_writer_"))
    out = tmp / f"{mode}.npy"
    syscall_abi_kernel_image(build_default_atlas(), mode=mode, timer_quantum=tq, out_path=out)
    return out


def image_hits(img: np.ndarray, words: dict) -> dict:
    """Find image pixels whose (r,g,b) equals a target word's low 24 bits."""
    res = {}
    for idx, w in words.items():
        triple = (w & 0xFF, (w >> 8) & 0xFF, (w >> 16) & 0xFF)
        mask = (img[:, :, 0] == triple[0]) & (img[:, :, 1] == triple[1]) & (img[:, :, 2] == triple[2])
        coords = np.argwhere(mask)
        res[str(idx)] = {
            "target_value": w,
            "target_rgb": list(triple),
            "pixel_count": int(coords.shape[0]),
            "pixels": [[int(a), int(b)] for a, b in coords[:8].tolist()],
        }
    return res


def main() -> int:
    from tools.glyph_gpt.runner import GlyphRunner

    payload: dict = {"seed": SEED, "pt_targets": {str(k): v for k, v in PT_TARGETS.items()},
                     "argv": " ".join(sys.argv)}

    # ---- leg 0: mode discrimination -- is the word pre-existing after bake/load? ----
    modes = {}
    for mode in ("baseline", "admit", "paged_dispatch"):
        out = bake(mode)
        runner = GlyphRunner(out, ram_words=RAM_WORDS)
        cpu = runner.get_cpu()
        img = np.asarray(runner.image)
        mem = cpu.memory
        pre = {str(i): {"value": int(mem[i]), "hex": hex(int(mem[i]) & 0xFFFFFFFF)}
               for i in PT_TARGETS if i < len(mem)}
        win_pre = [[i, int(mem[i]), hex(int(mem[i]) & 0xFFFFFFFF)] for i in range(WIN_LO, min(WIN_HI, len(mem)))
                   if isinstance(mem[i], int) and mem[i] != 0]
        scan = [[i, int(mem[i]), hex(int(mem[i]) & 0xFFFFFFFF)] for i in range(min(RAM_WORDS, len(mem)))
                if isinstance(mem[i], int) and mem[i] in PT_TARGETS.values()]
        modes[mode] = {
            "image_shape": list(img.shape),
            "ram_len_pre_step": len(mem),
            "pt_slots_pre_step": pre,
            "pt_window_nonzero_pre_step": win_pre[:24],
            "whole_ram_scan_for_targets_pre_step": scan,
            "image_pixel_hits": image_hits(img, PT_TARGETS),
        }
        print(f"[{mode}] ram_len={len(mem)} slot1538={hex(int(mem[1538]) & 0xFFFFFFFF)} "
              f"slot1539={hex(int(mem[1539]) & 0xFFFFFFFF)} "
              f"targets_in_ram={len(scan)} px_hits="
              f"{ {k: v['pixel_count'] for k, v in modes[mode]['image_pixel_hits'].items()} }", flush=True)
    payload["leg0_mode_discrimination"] = modes

    # ---- leg 1: runtime watch on the paged_dispatch image ----
    out = bake("paged_dispatch")
    runner = GlyphRunner(out, ram_words=RAM_WORDS)
    cpu = runner.get_cpu()
    cpu.running = True
    prev = {i: cpu.memory[i] for i in PT_TARGETS}
    transitions: list[dict] = []
    growths: list[dict] = []
    win_writes: list[dict] = []
    win_snapshot = {i: cpu.memory[i] for i in range(WIN_LO, min(WIN_HI, len(cpu.memory)))}
    steps = 0
    while cpu.running and steps < MAX_STEPS:
        before = len(cpu.memory)
        cpu.step(runner.image)
        steps += 1
        after = len(cpu.memory)
        pc = [int(cpu.pc[0]), int(cpu.pc[1])]
        if after != before:
            growths.append({"step": steps, "pc": pc, "mode": int(cpu.mode),
                            "grew_words": after - before, "ram_len": after})
            print(f"  GROW step {steps} pc={tuple(pc)} mode={cpu.mode} +{after - before} words", flush=True)
        for i, want in PT_TARGETS.items():
            cur = cpu.memory[i]
            if cur != prev[i]:
                transitions.append({"step": steps, "pc": pc, "mode": int(cpu.mode), "slot": i,
                                    "before": int(prev[i]), "before_hex": hex(int(prev[i]) & 0xFFFFFFFF),
                                    "after": int(cur), "after_hex": hex(int(cur) & 0xFFFFFFFF),
                                    "after_equals_target": int(cur) == want})
                print(f"  SLOT {i} step {steps} pc={tuple(pc)} mode={cpu.mode} "
                      f"{hex(int(prev[i]) & 0xFFFFFFFF)} -> {hex(int(cur) & 0xFFFFFFFF)}", flush=True)
                prev[i] = cur
        hi = min(WIN_HI, len(cpu.memory))
        for i in range(WIN_LO, hi):
            if cpu.memory[i] != win_snapshot[i]:
                win_writes.append({"step": steps, "pc": pc, "mode": int(cpu.mode), "index": i,
                                   "before_hex": hex(int(win_snapshot[i]) & 0xFFFFFFFF),
                                   "after_hex": hex(int(cpu.memory[i]) & 0xFFFFFFFF)})
                win_snapshot[i] = cpu.memory[i]

    payload["leg1_runtime_watch"] = {
        "steps_run": steps,
        "pt_slot_transitions": transitions,
        "growth_events": growths[:6],
        "growth_event_count": len(growths),
        "pt_window_writes": win_writes[:40],
        "pt_window_write_count": len(win_writes),
    }
    art = REPO / "output" / f"probe_defect23_pt_slot_writer_{SEED}.json"
    art.write_text(json.dumps(payload, indent=1))
    print(f"\nsteps={steps} transitions={len(transitions)} pt_window_writes={len(win_writes)}")
    print(f"artifact: {art}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
