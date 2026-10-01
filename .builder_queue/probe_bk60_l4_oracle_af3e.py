#!/usr/bin/env python3
"""BK-60 L4 prerequisite (af3e, 2026-09-27 tick 2): re-measure the ORACLE side
of D2/D3/D4 under the CORRECTED harness (RESEARCH_d1_paged_fault_attribution_
af3e.md's posture) — image sized to contain the PT window (min_rows=64 ->
2048 words), canary/data words RAM-seeded via drive(seeds=), receipt vpn 2
identity-mapped. The original probe's oracle fault_addr values (D2 12288,
D3 12304) were pt_tag_mismatch ARTIFACTS (every leg died at the tag gate
BEFORE the PTE checks). This probe takes the real oracle verdicts:
  D2 (PTE V|W, U clear, USER LD): predict pte_invalid op=LD, fault_addr
      12288 (the PTE_U check at glyph_isa_v2.py:872-876).
  D3 (PTE V|W|U pfn 32, USER LD of word 8196 THROUGH translation): predict
      CLEAN r10==1300 — the paged branch at :836 exempts only SUPER from
      translation and has NO box consult on the USER paged LD path, so the
      original receipt's "oracle faulted 12304" should FLIP to allowed.
      If it flips, D3 retires as a divergence (both engines allow) and
      BK-60's L2 premise changes shape.
  D4 (PTE 0, USER ST): predict pte_invalid op=ST fault_addr 12288 (:997-1006).
  C1 (unpaged out-of-box USER ST, no arm): predict E-K1 fault_addr 400 —
      proves the corrected harness does not mask the unpaged fence.
The twin side re-runs on the SAME corrected harness (matched pairs), but its
verdicts were already pinned by the original 3-run md5 — a twin flip here
would be a harness delta worth its own receipt.

Verdicts from READBACK BYTES only (receipt fields + fault_reason via manual
step-loop). Run: python3 .builder_queue/probe_bk60_l4_oracle_af3e.py
"""
import hashlib
import json
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
for p in (str(REPO), str(REPO / "tools")):
    if p not in sys.path:
        sys.path.insert(0, p)

import numpy as np  # noqa: E402

CANARY = 0x0ADF00D
BOX_LO, BOX_HI = 1200, 1300
PT_TAG_WORD = 1535
PT_BASE_WORD = 1536
PT_ARM_WORD = 8211
MODE_LATCH_WORD = 8192
VPN12_PTE_WORD = PT_BASE_WORD + 12
VPN2_PTE_WORD = PT_BASE_WORD + 2
PTE_V, PTE_W, PTE_U = 1, 2, 4
VA_CANARY = 3072
VA_MMIO = 12 * 256 + 4
RECEIPT_WORD = 720


def pte(pfn, flags=PTE_V | PTE_W | PTE_U):
    return flags | (pfn << 8)


def kernel_prologue(arm=True, box=True, latch=True):
    lines = [":__entry", "JMP :__kmain", ":__kmain",
             "LDI r15 %d" % RECEIPT_WORD, "LDI r14 0", "ST r15 r14"]
    if box:
        lines += ["LDI r15 8195", "LDI r14 %d" % BOX_LO, "ST r15 r14",
                  "LDI r15 8196", "LDI r14 %d" % BOX_HI, "ST r15 r14"]
    if arm:
        lines += ["LDI r15 %d" % PT_ARM_WORD, "LDI r14 %d" % PT_BASE_WORD,
                  "ST r15 r14"]
    if latch:
        lines += ["LDI r15 %d" % MODE_LATCH_WORD, "LDI r14 1", "ST r15 r14",
                  "LDI r30 0", "KJMP r30"]
    return "\n".join(lines) + "\n"


def kernel_epilogue():
    return (":__kdone\nLDI r3 4660\nLDI r15 %d\nST r15 r3\nHALT\n"
            % RECEIPT_WORD)


def leg_programs():
    """(text, stamps, ram_seeds) — same leg programs as the original probe,
    corrected harness only (sized image + vpn2 identity + RAM seeds)."""
    tags = {PT_TAG_WORD: 0x505447}
    arm = {PT_ARM_WORD: PT_BASE_WORD}
    vpn2 = {VPN2_PTE_WORD: pte(2)}
    prog_ld = ":__task\nLDI r15 %d\nLD r10 r15\n"
    prog_st = ":__task\nLDI r5 %d\nLDI r15 %d\nST r15 r5\n"
    return {
        "D1_control": (
            kernel_prologue() + prog_ld % VA_CANARY + kernel_epilogue(),
            {**tags, **arm, **vpn2, VPN12_PTE_WORD: pte(12)},
            {VA_CANARY: CANARY}),
        "D2_pte_u_bypass": (
            kernel_prologue() + prog_ld % VA_CANARY + kernel_epilogue(),
            {**tags, **arm, **vpn2,
             VPN12_PTE_WORD: pte(12, PTE_V | PTE_W)},
            {VA_CANARY: CANARY}),
        "D3_mmio_read_through_pte": (
            kernel_prologue() + prog_ld % VA_MMIO + kernel_epilogue(),
            {**tags, **arm, **vpn2, VPN12_PTE_WORD: pte(32)},
            {8196: BOX_HI}),
        "D4_unmapped_store": (
            kernel_prologue() + prog_st % (CANARY, VA_CANARY)
            + kernel_epilogue(),
            {**tags, **arm, **vpn2, VPN12_PTE_WORD: 0},
            None),
        "C1_unpaged_ek1": (
            kernel_prologue(arm=False, box=True)
            + prog_st % (4660, 100) + kernel_epilogue(),
            {**vpn2},
            None),
    }


def bake_two_pass(text, cols_instrs=8, min_rows=64):
    from tools.rv64i_to_glyph import assemble_glyph_to_pixels
    from tools.glyph_gpt.baker import bake_image
    if "KJMP r30" not in text:
        return bake_image(text, cols_instrs=cols_instrs, min_rows=min_rows,
                          out_path=None)
    assert "LDI r30 0\nKJMP r30" in text
    _, coords = assemble_glyph_to_pixels(text, cols_instrs=cols_instrs,
                                         min_rows=min_rows)
    col, row = coords[":__task"]
    packed = (col & 0xFFFF) | ((row & 0xFFFF) << 16)
    final = text.replace("LDI r30 0\nKJMP r30",
                         f"LDI r30 {packed}\nKJMP r30")
    return bake_image(final, cols_instrs=cols_instrs, min_rows=min_rows,
                      out_path=None)


def stamp_image(img, stamps):
    h, w, _ = img.shape
    for word, val in stamps.items():
        img[word % (h * w) // w, word % (h * w) % w] = (
            (val >> 16) & 0xFF, (val >> 8) & 0xFF, val & 0xFF)
    return img


def fault_view(rec, cpu=None):
    out = {
        "faulted": rec.get("faulted"),
        "fault_addr": rec.get("fault_addr"),
        "halted": rec.get("halted"),
        "steps": rec.get("steps"),
        "r10": (rec.get("registers_full") or [0] * 11)[10],
        "receipt_720": (rec.get("memory") or [0] * 721)[720],
        "mem_3072": (rec.get("memory") or [0] * 3073)[3072],
        "mem_100": (rec.get("memory") or [0] * 101)[100],
        "mem_8196": (rec.get("memory") or [0] * 8197)[8196],
    }
    if cpu is not None:
        out["fault_reason"] = cpu.fault_reason
        out["mode_at_fault"] = "USER" if cpu.mode else "SUPER"
    return out


def run_leg(name, text, stamps, ram_seeds):
    from PIL import Image
    from tools.glyph_gpt.runner import GlyphRunner

    img = bake_two_pass(text, cols_instrs=8, min_rows=64)
    h, w, _ = img.shape
    assert w * h >= 1549, "image must contain the PT window unwrapped"
    stamp_image(img, stamps)
    png = Path("/tmp/bk60_l4_%s_af3e.png" % name)
    Image.fromarray(img.astype(np.uint8)).save(str(png))

    # CPU receipt via drive(seeds=) — the corrected data channel.
    runner = GlyphRunner(str(png), ram_words=16384)
    rec = runner.drive(seeds=dict(ram_seeds or {}), max_instructions=4000)

    # fault_reason via manual step-loop on the same PNG bytes.
    cpu2 = GlyphRunner(str(png), ram_words=16384)
    cpu = cpu2.get_cpu()
    steps = 0
    cpu.running = True
    while cpu.running and steps < 4000:
        cpu.step(cpu2.image)
        steps += 1
        if cpu.faulted:
            break
    cpu_view = fault_view(rec, cpu)

    # Twin on the SAME corrected image, matched ram_seed channel.
    try:
        rec_w = runner.run_wgsl(max_steps=4000,
                                ram_seed=dict(ram_seeds or {}))
        ram = rec_w.get("ram") or []
        wgsl_view = {
            "halted": rec_w.get("halted"),
            "r10": (rec_w.get("registers_full") or [0] * 11)[10],
            "receipt_720_ram": ram[720] if len(ram) > 720 else None,
            "ram_3072": ram[3072] if len(ram) > 3072 else None,
            "ram_100": ram[100] if len(ram) > 100 else None,
            "ram_8196": ram[8196] if len(ram) > 8196 else None,
            "steps": rec_w.get("steps"),
            "error": rec_w.get("error"),
        }
    except Exception as e:  # noqa: BLE001
        wgsl_view = {"error": "%s: %s" % (type(e).__name__, e)}

    return {"dims": [int(w), int(h)], "cpu": cpu_view, "wgsl": wgsl_view}


def main():
    out = {}
    for name, (text, stamps, seeds) in sorted(leg_programs().items()):
        out[name] = run_leg(name, text, stamps, seeds)
    blob = json.dumps(out, indent=1, sort_keys=True, default=str)
    print(blob)
    print("results_md5", hashlib.md5(blob.encode()).hexdigest())


if __name__ == "__main__":
    main()
