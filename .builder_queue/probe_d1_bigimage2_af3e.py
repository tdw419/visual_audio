#!/usr/bin/env python3
"""D1 attribution CONTROL v2: big image + identity-map EVERY vpn the program
touches. The v1 control proved the original D1 fault was pt_tag_mismatch
(image too small, 672 words < PT window 1535/1548 -> check_pt_tag's bounds
guard blocks the image fallback; tag stays 0). But the epilogue's receipt
store (word 720, vpn 2) then pte_invalid-faults because vpn 2 is unmapped.

v2: identity-map vpn 2 (PTE V|W|U pfn 2) as well, and the canary vpn 12.
Prediction: FULL clean run — LD returns canary (r10==0x0ADF00D), receipt
720==4660, no fault. That is the CPU control the original receipt lacked:
on a correctly-sized image with a properly tagged table, the oracle paged
walker agrees with the twin on the V|W|U identity map — D1 is NOT a third
engine divergence; it is a probe-harness artifact (probe defect #6).
"""
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
PTE_V, PTE_W, PTE_U = 1, 2, 4
VA_CANARY = 3072
RECEIPT_WORD = 720


def pte(pfn):
    return PTE_V | PTE_W | PTE_U | (pfn << 8)


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

    stamps = {PT_TAG_WORD: 0x505447, PT_ARM_WORD: PT_BASE_WORD,
              PT_BASE_WORD + 12: pte(12),   # canary vpn: identity V|W|U
              PT_BASE_WORD + 2: pte(2)}     # receipt vpn: identity V|W|U
    prog = (kernel_prologue()
            + ":__task\nLDI r15 %d\nLD r10 r15\n" % VA_CANARY
            + kernel_epilogue())

    img = bake_two_pass(prog, cols_instrs=8, min_rows=64)
    h, w, _ = img.shape
    assert w * h >= 1549, "image must contain the PT window unwrapped"
    stamp_image(img, {VA_CANARY: CANARY})
    stamp_image(img, stamps)

    out = {"dims": [int(w), int(h)], "words": int(w * h)}

    with tempfile.TemporaryDirectory() as td:
        png = Path(td) / "d1_big3.png"
        from PIL import Image
        Image.fromarray(img.astype(np.uint8)).save(str(png))
        runner = GlyphRunner(str(png), ram_words=16384)
        # v3: seed the canary via runner.drive(seeds=...) — RAM seed, the
        # same way run_wgsl's ram_seed delivers it on the twin side. The
        # plain-frame paged LD reads RAM (glyph :912-914), so the image
        # stamp was always the wrong channel for a pfn 12 plain PTE.
        rec = runner.drive(seeds={VA_CANARY: CANARY}, max_instructions=4000)
        png_bytes = png.read_bytes()

    out["run"] = {
        "faulted": rec.get("faulted"),
        "fault_addr": rec.get("fault_addr"),
        "halted": rec.get("halted"),
        "steps": rec.get("steps"),
        "r10": (rec.get("registers_full") or [0] * 11)[10],
        "receipt_720": (rec.get("memory") or [0] * 721)[720],
        "canary_word3072": (rec.get("memory") or [0] * 3073)[3072],
        "error": rec.get("error"),
    }

    png2 = Path("/tmp/d1_big2_af3e.png")
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
        "fault_reason": c2.fault_reason,
        "mode_at_fault": "USER" if c2.mode else "SUPER",
        "steps": steps,
    }

    import hashlib
    blob = json.dumps(out, sort_keys=True, default=str).encode()
    print(json.dumps(out, indent=1, default=str))
    print("results_md5", hashlib.md5(blob).hexdigest())


if __name__ == "__main__":
    main()
