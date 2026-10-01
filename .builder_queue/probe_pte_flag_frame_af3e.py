#!/usr/bin/env python3
"""Research tick 6 (af3e, 2026-09-28): PTE_W / PTE_U enforcement on the
paged PIX frame path — the shape no prior probe has driven.

Scope lineage (prior-art grep, rule-5):
  - Tick 2 (RESEARCH_wgsl_paged_fence_af3e.md) measured PTE_U bypass on a
    PLAIN frame (D2) and counted PTE_W refs in walk_ld/walk_st (S1) but
    never DROVE a W-clear or U-clear FRAME PTE on either engine.
  - Tick 3 (RESEARCH_bk60_l4_oracle_remeasure_af3e.md) re-measured D2 on
    the corrected harness — still plain frames only; BK-60's L1 pins the
    plain-frame U bypass.
  - Ticks 4/5 (HILB/PIX frame fences) drove ONLY full-flag V|W|U|frame
    PTEs — they measured BOX-CONSULT absence, deliberately holding flags
    constant. Both receipts' "NOT proved" sections name flag enforcement
    as unprobed.

Source predictions at HEAD 71b4b364:
  CPU (tools/glyph_isa_v2.py): the paged ST path checks
    (not V) or (not W) or (USER and not U) at :1001 BEFORE the frame
    branches (:1033-1037 PIX/HILB arms) — a W-clear frame ST must fault
    pte_invalid (op=ST). The paged LD path checks V + (USER->U) at :873
    before :907-910 — a U-clear frame LD must fault pte_invalid (op=LD)
    in USER mode.
  WGSL (tools/wgsl_glyph_isa_v2.py): walk_ld paged branch checks ONLY
    PTE_V (:389; PTE_U/PTE_W defined :171-172, never consulted — tick 2
    S1); walk_st paged branch checks ONLY PTE_V (:425) then dispatches to
    the PIX arm (:431-434) which mem_writes and returns false. Prediction:
    BOTH flag-cleared legs EXECUTE on the twin — measured write-protect
    bypass (W-clear ST lands) and U-bypass (U-clear LD reads).

Legs (harness IDENTICAL to tick 5's probe_pix_frame_fence_af3e.py —
min_rows=64 image, image-stamped tag/arm/PTE + canaries, USER via
MODE_LATCH+KJMP, box [1200,1300) armed by the prologue, LINEAR PIX
placement; ONLY delta = the PTE flag bits):
  W1: W-clear PIX PTE (V|U), USER ST of canary -> VA_OUT (frame word 1280,
      out-of-box; combines with tick 5's finding that out-box is unfenced —
      the flag is the ONLY thing under test). Controls: PTE = V|W|U shape
      is tick 5 P3 (lands both).
  W2: W-clear IN-BOX control (V|U pfn 1 off 64): isolates flag from the
      out-box geometry — same VA as tick 5 P4 but W cleared.
  U1: U-clear PIX PTE (V|W), USER LD of VA_OUT canary.
  C1: unpaged out-of-box ST control (no arm/tag) — fence LIVE both engines.
  C2: SUPER W-clear ST control: same W-clear PTE, no latch — the oracle's
      :1001 W check is mode-INDEPENDENT, so SUPER must ALSO fault on the
      CPU while the twin (no is_super consult in walk_st's paged branch)
      lands. Pins that the twin's gap is not USER-specific.

CPU fault_reason captured via the tick-3 manual step-loop discipline
(probe defect #4 workaround, probe_faultreason_census_af3e.py:181-207).
Twin verdicts from receipt memory[] word readbacks, never stdout.
3 runs must be byte-identical.

Run: python3 .builder_queue/probe_pte_flag_frame_af3e.py
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
PTE_PIX = 0x8
PAGE_WORDS = 256
RECEIPT_WORD = 720
FRAME_IN_WORD = 320                   # byte 1280: inside [1200, 1300)
FRAME_OUT_WORD = 1280                 # byte 5120: outside the box
PFN_IN, OFF_IN = 1, 64                # word 320
PFN_OUT, OFF_OUT = 5, 0               # word 1280
VA_IN = (12 << 8) | OFF_IN            # vpn 12
VA_OUT = (12 << 8) | OFF_OUT


def pte(pfn_field, flags):
    return flags | PTE_PIX | (pfn_field << 8)


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
    pte_full_out = pte(PFN_OUT, PTE_V | PTE_W | PTE_U)    # tick 5 P3 shape
    prog_ld = ":__task\nLDI r15 %d\nLD r10 r15\n"
    prog_st = ":__task\nLDI r5 %d\nLDI r15 %d\nST r15 r5\n"
    return {
        # W1: W-clear PIX PTE, out-of-box USER ST. Prediction: CPU faults
        # pte_invalid(op=ST) at :1001 (mode-independent W check); twin's
        # walk_st paged branch (V-only) executes the PIX arm — canary LANDS.
        "W1_wclear_outbox_st": (
            kernel_prologue() + prog_st % (CANARY, VA_OUT) + kernel_epilogue(),
            {**tags, **arm, VPN12_PTE_WORD: pte_wclear_out}),
        # W2: W-clear IN-box control — same VA as tick 5's P4 but W cleared.
        # Isolates the flag from the out-box geometry.
        "W2_wclear_inbox_st": (
            kernel_prologue() + prog_st % (CANARY, VA_IN) + kernel_epilogue(),
            {**tags, **arm, VPN12_PTE_WORD: pte_wclear_in}),
        # U1: U-clear PIX PTE, out-of-box USER LD. Prediction: CPU faults
        # pte_invalid(op=LD) at :873 (USER + !U); twin reads the canary.
        "U1_uclear_outbox_ld": (
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
        # walk_st has no is_super consult in its paged branch. NOTE: the
        # PT-arm word (8211) is read from RAM ONLY (glyph_isa_v2.py:834,
        # no image fallback), so the arm must come from the program's own
        # SUPER ST (prologue arm=True); stamping the arm word into the
        # image does nothing (v1 of this probe had exactly that defect —
        # C2 ran UNPAGED, halted clean at 8 steps, disclosed here).
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
