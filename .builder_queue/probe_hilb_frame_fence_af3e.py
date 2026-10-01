#!/usr/bin/env python3
"""Research tick 4 (af3e, 2026-09-28): the PTE_HILB frame-path fence posture —
the last walk surface BK-60's honesty note left as "source read, labeled, NOT
probed" (systems/GLYPH_BACKLOG.md BK-60 HONESTY: "paged x tile composition and
PTE_HILB frame-path fence posture NOT probed").

Question: when a USER task's paged access resolves through a PTE_HILB mapping,
does the HILB frame path respect the GO-2 box fence on EITHER engine?

Source-read facts under test (verified by direct file read before probing):
  - Oracle paged LD HILB arm (glyph_isa_v2.py:901-906): after the PTE V/W/U
    checks (:872-876), the HILB branch does _mem_read(image, pix_word) with
    NO _addr_in_box consult — the consult exists only on the UNPAGED ST arm
    (:1041).
  - Oracle paged ST HILB arm (glyph_isa_v2.py:1027-1032): same shape, NO
    box consult after the PTE checks.
  - Twin walk_ld HILB arm (wgsl_glyph_isa_v2.py:393-394): mem_read(
    hilb_frame_word(...)) directly — zero addr_in_box references anywhere in
    the paged branch.
  - Twin walk_st HILB arm (wgsl_glyph_isa_v2.py:427-429): mem_write(
    hilb_frame_word(...)) then `return false` (no E-K1), zero consults.

So BOTH engines are predicted to let a box-confined USER task read AND write
arbitrary frame words through a HILB PTE the task's page table happens to
map — the same posture BK-60 already measured for plain-frame paged accesses
(D3: both engines allow), now measured for the HILB frame path, which is the
path GH-25's Hilbert-coherent workloads actually take.

Harness = the CORRECTED BK-60 L4 discipline (RESEARCH_d1_paged_fault_
attribution_af3e.md): image sized to contain the PT window (min_rows=64),
two-pass bake with the LDI-r30 placeholder, tag/PT-arm/PTE stamped into the
image post-bake, USER via MODE_LATCH+KJMP, box [1200,1300) bytes armed by the
kernel prologue itself, canaries RAM/image-seeded before the run.

Frame-word placement: the probe computes xy2d locally (8-line Hacker's
Delight loop replicated from glyph_isa_v2._hilb_frame_pix_word) and searches
for frame origins whose d lands the frame word in the desired region —
  H1/H4: d==1, offset 64  -> frame word 320  (byte 1280, INSIDE the box)
  H2/H3: d==5, offset 0   -> frame word 1280 (byte 5120, OUTSIDE the box)
The engine's own d is never assumed; H1 returning the canary proves the
probe's mapping matches both engines.

Verdicts from READBACK BYTES only: registers (r10) for LD legs, post-run
image words for ST legs (CPU: runner.image; twin: receipt["memory"]), receipt
fault fields for the E-K1 control. Never handler stdout.

Run: python3 .builder_queue/probe_hilb_frame_fence_af3e.py
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
PAGE_WORDS = 256
HILB_SIDE = 64
RECEIPT_WORD = 720
FRAME_IN_WORD = 320                   # byte 1280: inside [1200, 1300)
FRAME_OUT_WORD = 1280                 # byte 5120: outside the box


def hilb_d(col, row):
    """Hacker's Delight xy2d, replicated from glyph_isa_v2._hilb_frame_pix_word."""
    d = 0
    s = HILB_SIDE >> 1
    x, y = col, row
    while s > 0:
        rx = 1 if (x & s) else 0
        ry = 1 if (y & s) else 0
        d += s * s * ((3 * rx) ^ ry)
        if ry == 0:
            if rx == 1:
                x = HILB_SIDE - 1 - x
                y = HILB_SIDE - 1 - y
            x, y = y, x
        s >>= 1
    return d


def find_frame(d_target):
    """Smallest (col,row) whose d == d_target; returns the packed pfn field."""
    for row in range(HILB_SIDE):
        for col in range(HILB_SIDE):
            if hilb_d(col, row) == d_target:
                return col | (row << 8)
    raise AssertionError("no frame origin with d=%d" % d_target)


PFN_IN = find_frame(1)                # frame word base 256
PFN_OUT = find_frame(5)               # frame word base 1280
VA_IN = (12 << 8) | 64                # vpn 12, offset 64 -> word 320 via PFN_IN
VA_OUT = (12 << 8) | 0                # vpn 12, offset 0  -> word 1280 via PFN_OUT


def pte(pfn_field, flags=PTE_V | PTE_W | PTE_U):
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
    """(text, image_stamps) — stamps applied post-bake: PT words + canaries.

    HILB frame words resolve on the IMAGE plane of BOTH engines, so frame
    canaries are stamped into the image (not ram_seed)."""
    tags = {PT_TAG_WORD: 0x505447}
    arm = {PT_ARM_WORD: PT_BASE_WORD}
    pte_in = pte(PFN_IN)
    pte_out = pte(PFN_OUT)
    prog_ld = ":__task\nLDI r15 %d\nLD r10 r15\n"
    prog_st = ":__task\nLDI r5 %d\nLDI r15 %d\nST r15 r5\n"
    return {
        # H1: in-box frame LD (word 320, byte 1280 in box). Translation works;
        # both engines should return the canary. Also proves the probe's
        # xy2d/pfn mapping matches both engines.
        "H1_inbox_frame_ld": (
            kernel_prologue() + prog_ld % VA_IN + kernel_epilogue(),
            {**tags, **arm, VPN12_PTE_WORD: pte_in, FRAME_IN_WORD: CANARY}),
        # H2: OUT-of-box frame LD (word 1280, byte 5120). Prediction: BOTH
        # engines return the canary — the paged HILB path has no box consult
        # on either side (parity with BK-60 D3, now for the frame path).
        "H2_outbox_frame_ld": (
            kernel_prologue() + prog_ld % VA_OUT + kernel_epilogue(),
            {**tags, **arm, VPN12_PTE_WORD: pte_out, FRAME_OUT_WORD: CANARY}),
        # H3: OUT-of-box frame ST — the fence-violating write. Prediction:
        # lands clean on BOTH engines (twin walk_st HILB arm returns false;
        # oracle's HILB ST arm writes through). The unpaged ST to the same
        # BYTE would E-K1 on both (C1 pins that).
        "H3_outbox_frame_st": (
            kernel_prologue() + prog_st % (CANARY, VA_OUT) + kernel_epilogue(),
            {**tags, **arm, VPN12_PTE_WORD: pte_out}),
        # H4: in-box frame ST control — the lawful write lands.
        "H4_inbox_frame_st": (
            kernel_prologue() + prog_st % (CANARY, VA_IN) + kernel_epilogue(),
            {**tags, **arm, VPN12_PTE_WORD: pte_in}),
        # C1: PT NOT armed — plain unpaged USER ST to word 100 (byte 400,
        # outside the box). BOTH engines must E-K1: the fence is LIVE, so
        # H2/H3 are a genuine path gap, not a dead harness.
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
