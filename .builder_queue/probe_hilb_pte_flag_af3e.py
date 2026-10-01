#!/usr/bin/env python3
"""Research tick 7 (af3e, 2026-09-28): PTE_W / PTE_U enforcement on the
paged HILB frame path — the surface tick 6's receipt explicitly did NOT
prove ("HILB-frame flag legs not driven: PIX measurement pins the shared
check site by check-order source read, not a measured HILB leg").

Scope lineage (prior-art grep, rule-5):
  - Tick 2 (RESEARCH_wgsl_paged_fence_af3e.md) measured PTE_U bypass on a
    PLAIN frame and counted PTE_W refs — no frame PTE flags driven.
  - Ticks 4/5 (HILB/PIX frame fences) drove ONLY full-flag V|W|U|frame
    PTEs — box-consult absence measured, flags held constant.
  - Tick 6 (RESEARCH_pte_flag_frame_af3e.md / BK-64) drove W-clear/U-clear
    PTEs on the PIX (LINEAR) frame path ONLY. Its NOT-proved section names
    the HILB flag legs as the remaining unmeasured sibling.

Source predictions at HEAD 84a23929 (identical check order to tick 6's
HEAD — walk sites untouched between 71b4b364 and 84a23929):
  CPU (tools/glyph_isa_v2.py): paged ST checks (not V)|(not W)|(USER and
    not U) at :1001 BEFORE the HILB arm (:1027-1032) — a W-clear HILB ST
    must fault pte_invalid (op=ST), mode-independently. Paged LD checks
    V + (USER->U) at :873 BEFORE the HILB arm (:901-906) — a U-clear
    HILB LD must fault pte_invalid (op=LD) in USER.
  WGSL (tools/wgsl_glyph_isa_v2.py): walk_ld paged branch checks ONLY
    PTE_V (:389) then dispatches the HILB arm (:393-394); walk_st paged
    branch checks ONLY PTE_V (:425) then HILB arm (:427-429). Prediction:
    BOTH flag-cleared legs EXECUTE on the twin — W-clear ST LANDS at the
    Hilbert frame word; U-clear LD RETURNS the canary.

Legs (harness IDENTICAL to tick 6's probe_pte_flag_frame_af3e.py —
min_rows=64 image, image-stamped tag/arm/PTE + canaries, USER via
MODE_LATCH+KJMP, box [1200,1300) armed by the prologue; ONLY delta =
PTE flag HILB 0x10 instead of PIX 0x8, and pfn_field packed col|row<<8
with Hilbert placement; target frame words UNCHANGED: in-box word 320 =
byte 1280, out-box word 1280 = byte 5120 — the SAME pfn encodings tick 4
CONFIRMED against both engines via its H1/H4 in-box controls: pfn 0x1 ->
xy2d(1,0)=1 -> word 1*256+64=320; pfn 0x300 -> xy2d(0,3)=5 -> word 5*256=1280):
  H1w: W-clear HILB PTE (V|U), USER ST of canary -> VA_OUT.
  H2w: W-clear IN-BOX control (V|U, word 320): isolates flag from geometry.
  H1u: U-clear HILB PTE (V|W), USER LD of VA_OUT canary.
  C1:  unpaged out-of-box ST control (no arm/tag) — fence LIVE both engines.
  C2:  SUPER W-clear ST control — :1001's W check is mode-INDEPENDENT, so
       the CPU must fault even in SUPER; the twin's walk_st paged branch
       has no is_super consult. PT-arm via the program's own SUPER ST
       (tick 6 probe defect #1 avoided: image-stamped arm is invisible,
       glyph :834 reads the arm from RAM only).

CPU fault_reason via the tick-3 manual step-loop. Twin verdicts from
receipt memory[] word readbacks, never stdout. 3 runs byte-identical.

Run: python3 .builder_queue/probe_hilb_pte_flag_af3e.py
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
BOX_LO, BOX_HI = 1200, 1300          # BYTE addresses of the armed box
PT_TAG_WORD = 1535
PT_BASE_WORD = 1536
PT_ARM_WORD = 8211                    # PAGE_TABLE_WORD
VPN12_PTE_WORD = PT_BASE_WORD + 12    # 1548
MODE_LATCH_WORD = 8192
PTE_V, PTE_W, PTE_U = 1, 2, 4
PTE_HILB = 0x10
RECEIPT_WORD = 720
FRAME_IN_WORD = 320                   # byte 1280: inside [1200, 1300)
FRAME_OUT_WORD = 1280                 # byte 5120: outside the box
PFN_IN, OFF_IN = 0x1, 64              # xy2d(1,0)=1 -> word 1*256+64 = 320
PFN_OUT, OFF_OUT = 0x300, 0           # xy2d(0,3)=5 -> word 5*256 = 1280
VA_IN = (12 << 8) | OFF_IN            # vpn 12
VA_OUT = (12 << 8) | OFF_OUT


def pte(pfn_field, flags):
    return flags | PTE_HILB | (pfn_field << 8)


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
    """(text, image_stamps) — stamps applied post-bake: PT words + canaries."""
    tags = {PT_TAG_WORD: 0x505447}
    arm = {PT_ARM_WORD: PT_BASE_WORD}
    pte_wclear_out = pte(PFN_OUT, PTE_V | PTE_U)          # W CLEARED
    pte_wclear_in = pte(PFN_IN, PTE_V | PTE_U)            # W CLEARED
    pte_uclear_out = pte(PFN_OUT, PTE_V | PTE_W)          # U CLEARED
    prog_ld = ":__task\nLDI r15 %d\nLD r10 r15\n"
    prog_st = ":__task\nLDI r5 %d\nLDI r15 %d\nST r15 r5\n"
    return {
        # H1w: W-clear HILB PTE, out-of-box USER ST. Prediction: CPU faults
        # pte_invalid(op=ST) at :1001 before the HILB arm; twin's walk_st
        # paged branch (V-only) executes the HILB arm — canary LANDS at
        # Hilbert word 1280.
        "H1w_wclear_outbox_st": (
            kernel_prologue() + prog_st % (CANARY, VA_OUT) + kernel_epilogue(),
            {**tags, **arm, VPN12_PTE_WORD: pte_wclear_out}),
        # H2w: W-clear IN-box control — same pfn encoding as tick 4's H1
        # but W cleared. Isolates the flag from the box geometry.
        "H2w_wclear_inbox_st": (
            kernel_prologue() + prog_st % (CANARY, VA_IN) + kernel_epilogue(),
            {**tags, **arm, VPN12_PTE_WORD: pte_wclear_in}),
        # H1u: U-clear HILB PTE, out-of-box USER LD. Prediction: CPU faults
        # pte_invalid(op=LD) at :873; twin returns the canary.
        "H1u_uclear_outbox_ld": (
            kernel_prologue() + prog_ld % VA_OUT + kernel_epilogue(),
            {**tags, **arm, VPN12_PTE_WORD: pte_uclear_out,
             FRAME_OUT_WORD: CANARY}),
        # C1: unpaged out-of-box ST control (no arm/tag) — fence LIVE.
        "C1_unpaged_ek1_control": (
            kernel_prologue(arm=False, box=True)
            + prog_st % (4660, 100) + kernel_epilogue(),
            {}),
        # C2: SUPER W-clear ST control — :1001's W check is mode-
        # independent, so the CPU must fault even in SUPER; the twin's
        # walk_st paged branch has no is_super consult. PT-arm comes from
        # the program's own SUPER ST (arm word 8211 is read from RAM only,
        # glyph :834 — tick 6 probe defect #1).
        "C2_super_wclear_st": (
            kernel_prologue(arm=True, box=False, latch=False)
            + prog_st % (CANARY, VA_OUT) + "HALT\n",
            {**tags, VPN12_PTE_WORD: pte_wclear_out}),
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
    total = h * w
    for word, val in stamps.items():
        idx = word % total
        img[idx // w, idx % w] = (
            (val >> 16) & 0xFF, (val >> 8) & 0xFF, val & 0xFF)
    return img


def img_word(img, word):
    h, w, _ = img.shape
    idx = word % (h * w)
    px = img[idx // w, idx % w]
    return (int(px[0]) << 16) | (int(px[1]) << 8) | int(px[2])


def run_cpu_manual(img, memory_words=16384):
    """Tick-3 manual step-loop: captures fault_reason at the faulting step."""
    from tools.glyph_isa_v2 import GlyphCPUv2, OpcodeMapV2
    cpu = GlyphCPUv2(OpcodeMapV2(), cols_instrs=8)
    cpu.memory = [0] * memory_words
    steps = 0
    cpu.running = True
    while cpu.running and steps < 4000:
        cpu.step(img)
        steps += 1
        if cpu.faulted:
            break
    return {
        "faulted": bool(cpu.faulted),
        "fault_addr": int(cpu.fault_addr) if cpu.fault_addr is not None else None,
        "fault_reason": cpu.fault_reason,
        "mode_at_end": "USER" if cpu.mode == 1 else "SUPER",
        "steps": steps,
        "running_after": bool(cpu.running),
    }


def run_leg(name, text, stamps):
    from PIL import Image
    from tools.glyph_gpt.runner import GlyphRunner

    img = bake_two_pass(text, cols_instrs=8, min_rows=64)
    h, w, _ = img.shape
    assert w * h >= 1549, "image must contain the PT window unwrapped"
    stamp_image(img, stamps)
    with tempfile.TemporaryDirectory() as td:
        png = Path(td) / f"{name}.png"
        Image.fromarray(img.astype(np.uint8)).save(str(png))

        runner = GlyphRunner(str(png), ram_words=16384)
        rec_w = runner.run_wgsl(max_steps=4000)
        twin_mem = rec_w.get("memory") or []

        def twin_word(word):
            return twin_mem[word] if len(twin_mem) > word else None

        # CPU: same PNG bytes, manual step-loop for fault_reason.
        cpu = run_cpu_manual(img.copy())

    cpu_img = runner.image
    view = {
        "dims": [int(w), int(h)],
        "pte_flag_word_1548": img_word(img, VPN12_PTE_WORD),
        "cpu": {
            **cpu,
            "r10": None,
            "img_in_post": img_word(cpu_img, FRAME_IN_WORD),
            "img_out_post": img_word(cpu_img, FRAME_OUT_WORD),
        },
        "wgsl": {
            "halted": rec_w.get("halted"),
            "steps": rec_w.get("steps"),
            "r10": (rec_w.get("registers_full") or [0] * 11)[10],
            "img_in_post": twin_word(FRAME_IN_WORD),
            "img_out_post": twin_word(FRAME_OUT_WORD),
            "error": rec_w.get("error"),
        },
    }
    return view


def main():
    out = {}
    for name, (text, stamps) in sorted(leg_programs().items()):
        out[name] = run_leg(name, text, stamps)
    blob = json.dumps(out, indent=1, sort_keys=True, default=str)
    print(blob)
    print("results_md5", hashlib.md5(blob.encode()).hexdigest())


if __name__ == "__main__":
    main()
