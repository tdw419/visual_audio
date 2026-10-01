#!/usr/bin/env python3
"""Phase 1c research tick 3 (af3e, 2026-09-27 ~23:0x): COMPLETE fault_reason
classification pass over the oracle's fault sites.

Prior ticks found incidentally that the unpaged E-K1 ST fence site
(glyph_isa_v2.py:1075-1082) sets NO fault_reason — the 6th site in an
unfinished count. This probe ENUMERATES all `self.faulted = True` sites in
GlyphCPUv2.step and drives each one LIVE (manual step-loop, fault_reason +
fault_addr captured at the faulting step), producing the definitive
site -> {sets fault_reason? | string} table that any fault-classification
consumer (L4 oracle-parity pins, System-1 verdict fields) needs.

Static map (source read, HEAD b34ff0e8):
  S1 :845  LD paged pt_tag_mismatch        -> SETS fault_reason (tag_reason)
  S2 :876  LD paged pte_invalid            -> SETS fault_reason
  S3 :932  LD tile-confinement E-K1        -> does NOT set fault_reason  ?
  S4 :977  ST paged pt_tag_mismatch        -> SETS fault_reason (tag_reason)
  S5 :1004 ST paged pte_invalid            -> SETS fault_reason
  S6 :1052 ST paged pfn-ceiling DEFECT-23  -> SETS fault_reason
  S7 :1082 ST E-K1 fence (unpaged/unbox)   -> does NOT set fault_reason  ?
  S8 :1107 ST out-of-RAM-bounds            -> does NOT set fault_reason  ?

Live legs (each drives one site, no engine changes):
  L3 (S3): tile-armed USER LD out-of-tile  -> predict faulted, reason None
  L7 (S7): box-armed USER ST out-of-box    -> predict faulted, reason None
           (re-measures last tick's incidental find under a controlled leg)
  L8 (S8): USER in-box store to addr >= len(memory) with _iso_enabled,
           KFAULT_PC armed (E-K1 reuse branch :1108-1121)
           -> predict faulted, reason None
  L7b (S8 control, iso off): smaller memory (below _ISO_TOP_WORD) =>
           the else branch (:1123-1126) stops running, still no reason.
  PLUS parity controls: L1 (paged pte_invalid LD) and L5 (paged pte_invalid
  ST) predict faulted WITH a reason — proving the probe CAN see a reason
  when one exists (non-echo discrimination).

Verdicts from cpu.fault_reason / cpu.fault_addr / cpu.mode at the faulting
step only. Structural numbers — rule-1 floors do not attach.

Run: python3 .builder_queue/probe_faultreason_census_af3e.py
"""
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
for p in (str(REPO), str(REPO / "tools")):
    if p not in sys.path:
        sys.path.insert(0, p)

import numpy as np  # noqa: E402

from tools.glyph_isa_v2 import (  # noqa: E402
    BOX0_LO_ADDR, BOX0_HI_ADDR, KFAULT_PC_ADDR, MODE_LATCH_ADDR,
    PAGE_TABLE_ADDR, TILE_COL_ADDR, TILE_H_ADDR, TILE_ROW_ADDR, TILE_W_ADDR,
    GlyphCPUv2, OpcodeMapV2,
)
from tools.glyph_gpt.baker import bake_image  # noqa: E402

CANARY = 0x0ADF00D
PT_BASE_WORD = 1536
PT_TAG_WORD = 1535
PT_ARM_WORD = 8211
PTE_V, PTE_W, PTE_U = 1, 2, 4
DEFAULT_REAPER_ROW = 60


def pte(pfn, flags=PTE_V | PTE_W | PTE_U):
    return flags | (pfn << 8)


def prologue(arm=True, box=True, latch=True, tile=None, reaper=False):
    lines = [":__entry", "JMP :__kmain", ":__kmain"]
    if box:
        lines += ["LDI r15 %d" % (BOX0_LO_ADDR >> 2), "LDI r14 1200",
                  "ST r15 r14",
                  "LDI r15 %d" % (BOX0_HI_ADDR >> 2), "LDI r14 1300",
                  "ST r15 r14"]
    if arm:
        lines += ["LDI r15 %d" % PT_ARM_WORD, "LDI r14 %d" % PT_BASE_WORD,
                  "ST r15 r14"]
    if tile is not None:
        trow, tcol, th, tw = tile
        lines += ["LDI r15 %d" % (TILE_ROW_ADDR >> 2), "LDI r14 %d" % trow,
                  "ST r15 r14",
                  "LDI r15 %d" % (TILE_COL_ADDR >> 2), "LDI r14 %d" % tcol,
                  "ST r15 r14",
                  "LDI r15 %d" % (TILE_H_ADDR >> 2), "LDI r14 %d" % th,
                  "ST r15 r14",
                  "LDI r15 %d" % (TILE_W_ADDR >> 2), "LDI r14 %d" % tw,
                  "ST r15 r14"]
    if reaper:
        lines += ["LDI r15 %d" % (KFAULT_PC_ADDR >> 2),
                  "LDI r14 %d" % (DEFAULT_REAPER_ROW << 16), "ST r15 r14"]
    if latch:
        lines += ["LDI r15 %d" % (MODE_LATCH_ADDR >> 2), "LDI r14 1",
                  "ST r15 r14", "LDI r30 0", "KJMP r30"]
    return "\n".join(lines) + "\n"


def epilogue():
    return ":__kdone\nHALT\n"


def legs():
    """name -> (text, stamps(dict word->val), ram_seeds, memory_words)"""
    tags = {PT_TAG_WORD: 0x505447}
    arm = {PT_ARM_WORD: PT_BASE_WORD}
    vpn12 = {PT_BASE_WORD + 12: pte(12)}
    vpn2 = {PT_BASE_WORD + 2: pte(2)}
    prog_ld = ":__task\nLDI r15 %d\nLD r10 r15\n"
    prog_st = ":__task\nLDI r5 %d\nLDI r15 %d\nST r15 r5\n"
    out = {}

    # C1 parity control: paged pte_invalid on LD (S2) -> reason EXPECTED.
    out["C1_ld_pte_invalid"] = (
        prologue() + prog_ld % (12 * 256 + 64) + epilogue(),
        {**tags, **arm, **vpn2, PT_BASE_WORD + 12: pte(12, PTE_V | PTE_W)},
        {12 * 256 + 64: CANARY}, 16384)
    # C2 parity control: paged pte_invalid on ST (S5) -> reason EXPECTED.
    out["C2_st_pte_invalid"] = (
        prologue() + prog_st % (CANARY, 12 * 256 + 64) + epilogue(),
        {**tags, **arm, **vpn2, PT_BASE_WORD + 12: 0},
        None, 16384)
    # L3 (S3): tile-armed USER LD out-of-tile (word 4000) -> reason ?
    out["L3_ld_tile_ek1"] = (
        prologue(arm=False, box=False, tile=(5, 0, 2, 4)) + prog_ld % 4000
        + epilogue(), {}, {4000: CANARY}, 16384)
    # L7 (S7): box-armed USER ST out-of-box (word 100) -> reason ?
    out["L7_st_ek1_fence"] = (
        prologue(arm=False, box=True) + prog_st % (4660, 100) + epilogue(),
        {}, None, 16384)
    # L8 (S8): USER in-box store past len(memory), KFAULT_PC armed.
    # Box [16300,16320) inside RAM? NO — must be BELOW len(memory) for the
    # fence branch to be reached... actually S8 fires when addr >= len(memory)
    # regardless of box; iso branch reuses E-K1 vector. Use ST to word 20000
    # (past 16384) with box armed so _iso_enabled E-K1-reuse path runs.
    out["L8_st_oob_iso"] = (
        prologue(arm=False, box=True, reaper=True) + prog_st % (4660, 20000)
        + epilogue(), {}, None, 16384)
    # L8b (S8, iso off): memory below _ISO_TOP_WORD (3346 words) -> else
    # branch stops running. NOTE: box stores in the prologue still work
    # (memory large enough for BOX0 words at 8196? NO — 3346 < 8196/4...
    # the MMIO words alias past RAM). Use a 9000-word memory: above
    # _ISO_TOP_WORD? _ISO_TOP_WORD = TILE_W_ADDR>>2 = 8355. 9000 > 8355 so
    # iso IS enabled. For iso OFF use 3000 words and NO box/latch MMIO
    # stores (they'd be plain RAM writes past 3000 -> extension). Keep it
    # minimal: unpaged, no box, direct USER via latch is impossible without
    # MMIO. So L8b runs SUPER-mode ST past RAM -> S8's else branch.
    out["L8b_st_oob_noiso"] = (
        ":__entry\nLDI r5 4660\nLDI r15 20000\nST r15 r5\nHALT\n",
        {}, None, 3000)
    return out


def bake(text, min_rows=64):
    from tools.rv64i_to_glyph import assemble_glyph_to_pixels
    from tools.glyph_gpt.baker import bake_image
    if "KJMP r30" not in text:
        return bake_image(text, cols_instrs=8, min_rows=min_rows,
                          out_path=None)
    _, coords = assemble_glyph_to_pixels(text, cols_instrs=8,
                                         min_rows=min_rows)
    col, row = coords[":__task"]
    packed = (col & 0xFFFF) | ((row & 0xFFFF) << 16)
    final = text.replace("LDI r30 0\nKJMP r30",
                         f"LDI r30 {packed}\nKJMP r30")
    return bake_image(final, cols_instrs=8, min_rows=min_rows,
                      out_path=None)


def stamp(img, stamps):
    h, w, _ = img.shape
    for word, val in stamps.items():
        img[word % (h * w) // w, word % (h * w) % w] = (
            (val >> 16) & 0xFF, (val >> 8) & 0xFF, val & 0xFF)
    return img


def run_leg(name, text, stamps, seeds, memory_words):
    from tools.glyph_gpt.runner import GlyphRunner

    img = bake(text)
    h, w, _ = img.shape
    stamp(img, stamps)
    cpu = GlyphCPUv2(OpcodeMapV2(), cols_instrs=8)
    cpu.memory = [0] * memory_words
    for word, val in (seeds or {}).items():
        cpu.memory[word] = val
    steps = 0
    cpu.running = True
    while cpu.running and steps < 4000:
        cpu.step(img)
        steps += 1
        if cpu.faulted:
            break
    return {
        "dims": [int(w), int(h)],
        "memory_words": memory_words,
        "faulted": bool(cpu.faulted),
        "fault_addr": int(cpu.fault_addr),
        "fault_reason": cpu.fault_reason,
        "mode_at_fault": "USER" if cpu.mode == 1 else "SUPER",
        "steps_to_fault": steps,
        "running_after": bool(cpu.running),
    }


def main():
    out = {}
    for name, (text, stamps, seeds, mw) in sorted(legs().items()):
        out[name] = run_leg(name, text, stamps, seeds, mw)
    blob = json.dumps(out, indent=1, sort_keys=True, default=str)
    print(blob)
    print("results_md5", hashlib.md5(blob.encode()).hexdigest())


if __name__ == "__main__":
    main()
