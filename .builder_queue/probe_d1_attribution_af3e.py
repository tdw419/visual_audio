#!/usr/bin/env python3
"""D1 attribution probe (Phase 1c research, af3e tick 2026-09-27 ~21:2x).

Question: RESEARCH_wgsl_paged_fence_af3e.md recorded D1's CPU-side fault
(USER LD, V|W|U identity map, fault_addr=12288) as UNATTRIBUTED — the
GlyphRunner receipt carries no fault_reason, so pte_invalid and
pt_tag_mismatch are indistinguishable at fault_addr granularity (both set
fault_addr = vaddr << 2).

H1 (tag hypothesis): check_pt_tag (glyph_isa_v2.py:841) reads the tag from
RAM first, image fallback. The probe stamps the tag into IMAGE pixels only
(ram_words=16384 zeroed RAM), and ram[1535]==0 falls back to image — the
image tag IS 0x505447 (matches), so H1-as-typo is DEAD; but the tag leg
fires only if the image fallback itself works. H2: the image-fallback tag
read or PTE image-fallback read returns garbage (24-bit stamping of
0x505447 vs RGB channels). H3: pte check itself faults (U/W/V fine in D1 —
so pte_invalid should NOT fire; if fault_reason says pte_invalid the PTE
readback must have returned something else).

Method: re-run D1's exact leg (same prologue/program/stamps/bake), but
drive the CPU via GlyphRunner.drive-style direct cpu.run and read
cpu.fault_reason AFTER the run (receipt drops it — that's probe defect #4,
confirmed by _fill_receipt:122-131 which has no fault_reason field).
Also probe intermediates: ram[1535], image word 1535/1548 via _mem_read.

Readback from returned cpu object + image, never stdout.
"""
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
VPN12_PTE_WORD = PT_BASE_WORD + 12
MODE_LATCH_WORD = 8192
PTE_V, PTE_W, PTE_U = 1, 2, 4
VA_CANARY = 3072
RECEIPT_WORD = 720


def kernel_prologue():
    lines = [":__entry", "JMP :__kmain", ":__kmain",
             "LDI r15 %d" % RECEIPT_WORD, "LDI r14 0", "ST r15 r14",
             "LDI r15 8195", "LDI r14 %d" % BOX_LO, "ST r15 r14",
             "LDI r15 8196", "LDI r14 %d" % BOX_HI, "ST r15 r14",
             "LDI r15 %d" % PT_ARM_WORD, "LDI r14 %d" % PT_BASE_WORD,
             "ST r15 r14",
             "LDI r15 %d" % MODE_LATCH_WORD, "LDI r14 1", "ST r15 r14",
             "LDI r30 0", "KJMP r30"]
    return "\n".join(lines) + "\n"


def kernel_epilogue():
    return ":__kdone\nLDI r3 4660\nLDI r15 %d\nST r15 r3\nHALT\n" % RECEIPT_WORD


def bake_two_pass(text, cols_instrs=8, min_rows=16):
    from tools.rv64i_to_glyph import assemble_glyph_to_pixels
    from tools.glyph_gpt.baker import bake_image
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


def main():
    from tools.glyph_gpt.runner import GlyphRunner
    from tools.glyph_isa_v2 import GlyphCPUv2, OpcodeMapV2, check_pt_tag, \
        PAGE_TABLE_TAG

    pte_vwu_12 = PTE_V | PTE_W | PTE_U | (12 << 8)
    tags = {PT_TAG_WORD: 0x505447}
    arm = {PT_ARM_WORD: PT_BASE_WORD}
    prog = (kernel_prologue()
            + ":__task\nLDI r15 %d\nLD r10 r15\n" % VA_CANARY
            + kernel_epilogue())
    stamps = {**tags, **arm, VPN12_PTE_WORD: pte_vwu_12}

    with tempfile.TemporaryDirectory() as td:
        img = bake_two_pass(prog, cols_instrs=8)
        stamp_image(img, {VA_CANARY: CANARY})
        stamp_image(img, stamps)

        # static intermediates BEFORE any execution (construct runner, then
        # swap in the live image array — no PNG needed yet)
        probe = GlyphRunner.__new__(GlyphRunner)
        probe.cols_instrs = 8
        probe.ram_words = 16384
        probe.image = img
        c = probe.get_cpu()
        c.memory = [0] * 16384
        tag_ok, tag_val, tag_reason = check_pt_tag(c, img, PT_BASE_WORD)
        pte_img = c._mem_read(img, VPN12_PTE_WORD)
        pte_ram = c.memory[VPN12_PTE_WORD]
        canary_img = c._mem_read(img, VA_CANARY)

        png = Path(td) / "d1.png"
        from PIL import Image
        Image.fromarray(img.astype(np.uint8)).save(str(png))
        assert png.exists(), f"PNG save failed: {png}"
        runner = GlyphRunner(str(png), ram_words=16384)
        rec = runner.run(max_instructions=4000)
        png_bytes = png.read_bytes()

    out = {
        "static": {
            "tag_ok": tag_ok, "tag_val": tag_val,
            "tag_reason": tag_reason,
            "tag_expect": PAGE_TABLE_TAG,
            "pte_img_word1548": pte_img, "pte_ram_word1548": pte_ram,
            "canary_img_word3072": canary_img,
        },
        "run": {
            "faulted": rec.get("faulted"),
            "fault_addr": rec.get("fault_addr"),
            "halted": rec.get("halted"),
            "steps": rec.get("steps"),
            "r10": (rec.get("registers_full") or [0] * 11)[10],
            "receipt_720": (rec.get("memory") or [0] * 721)[720],
            "error": rec.get("error"),
        },
    }

    # fault_reason: re-execute one manual step-loop to capture it, since
    # _fill_receipt drops it (probe defect #4). Rehydrate the SAME png bytes
    # outside the tempdir so the step loop runs the identical image.
    png2 = Path("/tmp/d1_attribution_af3e.png")
    png2.write_bytes(png_bytes)
    cpu = GlyphRunner(str(png2), ram_words=16384)
    c2 = cpu.get_cpu()
    steps = 0
    c2.running = True
    while c2.running and steps < 4000:
        c2.step(cpu.image)
        steps += 1
        if c2.faulted:
            break
    out["fault_reason"] = {
        "faulted": bool(c2.faulted),
        "fault_addr": int(c2.fault_addr) & 0xFFFFFFFF if c2.faulted else None,
        "fault_reason": c2.fault_reason,
        "mode_at_fault": "USER" if c2.mode else "SUPER",
        "steps_at_fault": steps,
    }

    import hashlib
    blob = repr(out).encode()
    print(json_dumps(out))
    print("results_md5", hashlib.md5(blob).hexdigest())


def json_dumps(o):
    import json
    return json.dumps(o, indent=1, default=str)


if __name__ == "__main__":
    main()
