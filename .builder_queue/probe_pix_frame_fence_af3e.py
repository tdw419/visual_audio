#!/usr/bin/env python3
"""Research tick 5 (af3e, 2026-09-28): the PTE_PIX plane-path fence posture —
the PIX-frame sibling of tick 4's PTE_HILB measurement. Tick 4's receipt
(RESEARCH_hilb_frame_fence_af3e.md, "What this receipt does NOT prove")
left the PIX arms "the same consult-free shape by source read but NOT probed
on-device". This tick converts that label into a measurement.

Question: when a USER task's paged access resolves through a PTE with
PTE_PIX (0x8) set, does the linear frame path respect the GO-2 box fence
on either engine?

Source-read facts under test (verified by direct file read before probing):
  - Oracle paged LD PIX arm (glyph_isa_v2.py:908-910): after the PTE V/W/U
    checks (:872-876), the PIX branch does pix_word = pfn*PAGE_WORDS+offset;
    _mem_read(image, pix_word) — NO _addr_in_box consult (same shape as the
    HILB arm :901-906).
  - Oracle paged ST PIX arm (glyph_isa_v2.py:1034-1036): same shape, NO
    box consult after the PTE checks (mirrors :1027-1032 HILB).
  - Twin walk_ld PIX arm (wgsl_glyph_isa_v2.py:396-398): mem_read(
    pfn*PAGE_WORDS + offset) directly — zero addr_in_box references.
  - Twin walk_st PIX arm (wgsl_glyph_isa_v2.py:431-434): mem_write(
    pfn*PAGE_WORDS + offset) then `return false` (no E-K1), zero consults.

So BOTH engines are predicted to let a box-confined USER task read AND
write arbitrary image-plane words through a PIX PTE the task's page table
happens to map — engine PARITY on the read, and the fence-blind WRITE is
the new measured shape (identical posture to tick 4's HILB result, now
for the LINEAR addressing mode GH-25 workloads also take).

Harness = IDENTICAL to tick 4's probe (the corrected BK-60 L4 discipline):
image min_rows=64 (2048 words, contains the PT window unwrapped), two-pass
bake, tag/PT-arm/PTE stamped into the image post-bake, USER via
MODE_LATCH+KJMP, box [1200,1300) BYTES armed by the kernel prologue,
canaries stamped into the image (PIX frame words resolve on the image
plane of both engines).

Frame placement (LINEAR, no Hilbert transform): pfn*PAGE_WORDS + offset.
  P1/P4 (in-box):  pfn 1, offset 64  -> word 320  (byte 1280, IN box)
  P2/P3 (out-box): pfn 5, offset 0   -> word 1280 (byte 5120, OUT box)
Note the deliberate symmetry with tick 4: the HILB probe used xy2d to
place d==1/d==5 frames at the SAME word addresses (320/1280), so the two
receipts differ ONLY in the PTE flag and the addressing transform — any
verdict difference is attributable to the path, not the placement.

Verdicts from READBACK BYTES only: r10 for LD legs, post-run image words
for ST legs (CPU runner.image; twin receipt["memory"]), never stdout.

Run: python3 .builder_queue/probe_pix_frame_fence_af3e.py
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

# LINEAR frame placement: word = pfn * PAGE_WORDS + offset. Same target
# words as tick 4 (320 / 1280) so the receipts differ only in PTE flag +
# transform.
PFN_IN, OFF_IN = 1, 64                # word 320
PFN_OUT, OFF_OUT = 5, 0               # word 1280
VA_IN = (12 << 8) | OFF_IN            # vpn 12
VA_OUT = (12 << 8) | OFF_OUT


def pte(pfn_field, flags=PTE_V | PTE_W | PTE_U):
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
    pte_in = pte(PFN_IN)
    pte_out = pte(PFN_OUT)
    prog_ld = ":__task\nLDI r15 %d\nLD r10 r15\n"
    prog_st = ":__task\nLDI r5 %d\nLDI r15 %d\nST r15 r5\n"
    return {
        # P1: in-box frame LD (word 320, byte 1280 in box). Translation
        # works; both engines should return the canary — proves the probe's
        # linear pfn/offset mapping matches both engines.
        "P1_inbox_pix_ld": (
            kernel_prologue() + prog_ld % VA_IN + kernel_epilogue(),
            {**tags, **arm, VPN12_PTE_WORD: pte_in, FRAME_IN_WORD: CANARY}),
        # P2: OUT-of-box frame LD (word 1280, byte 5120). Prediction: BOTH
        # engines return the canary — the paged PIX path has no box consult
        # on either side (parity with tick 4 H2).
        "P2_outbox_pix_ld": (
            kernel_prologue() + prog_ld % VA_OUT + kernel_epilogue(),
            {**tags, **arm, VPN12_PTE_WORD: pte_out, FRAME_OUT_WORD: CANARY}),
        # P3: OUT-of-box frame ST — the fence-violating write. Prediction:
        # lands clean on BOTH engines (twin walk_st PIX arm returns false;
        # oracle's PIX ST arm writes through). C1 pins the unpaged fence.
        "P3_outbox_pix_st": (
            kernel_prologue() + prog_st % (CANARY, VA_OUT) + kernel_epilogue(),
            {**tags, **arm, VPN12_PTE_WORD: pte_out}),
        # P4: in-box frame ST control — the lawful write lands.
        "P4_inbox_pix_st": (
            kernel_prologue() + prog_st % (CANARY, VA_IN) + kernel_epilogue(),
            {**tags, **arm, VPN12_PTE_WORD: pte_in}),
        # C1: PT NOT armed — plain unpaged USER ST to word 100 (byte 400,
        # outside the box). BOTH engines must E-K1: the fence is LIVE, so
        # P2/P3 are a genuine path gap, not a dead harness.
        "C1_unpaged_ek1_control": (
            kernel_prologue(arm=False, box=True)
            + prog_st % (4660, 100) + kernel_epilogue(),
            {}),
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
        rec = runner.run(max_instructions=4000)

        # Twin on the SAME image bytes.
        rec_w = runner.run_wgsl(max_steps=4000)
        twin_mem = rec_w.get("memory") or []

        def twin_word(word):
            return twin_mem[word] if len(twin_mem) > word else None

    cpu_img = runner.image
    view = {
        "dims": [int(w), int(h)],
        "frame_words": {"in": FRAME_IN_WORD, "out": FRAME_OUT_WORD},
        "pfn": {"in": PFN_IN, "out": PFN_OUT},
        "cpu": {
            "halted": rec.get("halted"),
            "faulted": rec.get("faulted"),
            "fault_addr": rec.get("fault_addr"),
            "steps": rec.get("steps"),
            "r10": (rec.get("registers_full") or [0] * 11)[10],
            "img_in_post": img_word(cpu_img, FRAME_IN_WORD),
            "img_out_post": img_word(cpu_img, FRAME_OUT_WORD),
            "receipt_720": (rec.get("memory") or [0] * (RECEIPT_WORD + 1))[RECEIPT_WORD],
            "error": rec.get("error"),
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
