#!/usr/bin/env python3
"""Research tick 15 (af3e, 2026-09-28): PAGED rewrite of KSYS_PC (RAM word
8194) — the E-K2 syscall-dispatcher control word — from a tile-confined USER
task through plain ST + GH-17 translation. The open NOT-proved sibling named
in ticks 13 AND 14's receipts ("KSYS_PC paged rewrite"; BK-41 measured the
UNPAGED PARALLEL_ST self-arm only, in the no-PT tile=(5,0,8,8) posture).

Why this is a distinct primitive from BK-41: the paged ST path
(glyph_isa_v2.py:968-1074) consults the PTE instead of the tile box for a
USER task once pt_base != 0, so a vpn->pfn mapping that lands BELOW the tile
makes the E-K1 fence irrelevant — no parallel opcode needed, no fence-blind
class, just the sanctioned translation mechanism aimed at the MMIO config
block. If it lands, the task then issues ONE syscall and the engine drops to
SUPER and jumps to the task-chosen pixel (glyph_isa_v2.py:1166-1189) — the
same fence-blind USER->SUPER dispatch class as tick 14's GH-16 tick, but
entered via the SYSCALL arm instead of the preemptive-tick arm.

Statically reachable: spawn(tile=(256,19,1,2)) arms a tile covering RAM
words 8211/8212; KSYS_PC word 8194 = BOX_MMIO_BASE+0x08>>2 sits BELOW the
tile — unmapped, exactly like tick 13's vector word and tick 14's tick block.
vpn 32 (vaddrs 8192..8447) -> RAM frame pfn 32 maps vaddr 8194 -> paddr 8194
in one PTE.

Prior-art grep (rule-5, done BEFORE harness build):
  - BK-41 (probe_ksys_arm_af3e.py): KSYS_PC self-arm via UNPAGED
    PARALLEL_ST (fence-blind write, glyph_isa_v2.py:1298-1329, no box
    consult), tile=(5,0,8,8) posture, NO page table. Different write
    primitive; the PAGED path (which the 2026-09-28 paddr-posture ruling
    9714a363 exists to close) was never measured against word 8194.
  - Ticks 12/13: reaper trampoline + KFAULT_PC (8193) — fault-vectoring,
    different word + different dispatcher.
  - Tick 14: KTICK_PC/TIMER_COUNT (8207/8208) — preemptive-tick dispatcher,
    GH-16 arm; this tick is the E-K2 SYSCALL arm of the same paged-rewrite
    class.
  - No row or receipt measures a paged guest write to KSYS_PC. Net-new.

Legs (oracle only — twin: WGSL walker has no SYSCALL dispatcher at all,
source-read labeled):
  T1  paged KSYS_PC rewrite (ST 1966088 -> vaddr 8194, = pixel row 30
      col 8), then ONE SYSCALL: expected if live, engine reads ksys != 0,
      drops to SUPER, executes the attacker gadget (LDI r2 52; PRT r2;
      HALT painted at words 1952..1963 via vpn-12 PIX pfn 7) ->
      cpu.output == [52], mode SUPER, ksys word 1966088, SYSCALL_PC word
      8205 = the packed USER resume PC.
  C1  control, NO rewrite (identical program minus the rewrite ST pair):
      ksys reads 0 -> the DIRECT fence-blind handler branch runs
      (glyph_isa_v2.py:1190-1192) -> syscall 6 (DEBUG) served inline ->
      output [], mode USER, ksys word 0, SYSCALL_PC word 0 — proves the
      dispatch required the paged write, not the syscall alone.
  C2  control, NO translation (vpn-32 PTE left 0): the rewrite ST faults
      pte_invalid vaddr 0x8010, vectors to the REAL reaper trampoline
      (col 0, row 30), parked exit 1, ksys word stays 0, no dispatch —
      proves the rewrite went through translation; no unpaged fence hole
      for word 8194 in this posture.
  C3  rot-guard, unpaged out-of-tile ST to word 8194 with NO PT armed:
      E-K1 trap (fault_addr 8194*4 = 32776), reaper, exit 1 — the tile
      fence is live for the same word when translation is not armed
      (BK-66-C2 shape, KSYS flavor).

Verdicts from exit_status + fault fields + cpu.output + RAM readback
(words 8194/8205/8210) + final PC BYTES, never stdout. Gadget pixels come
from GlyphAssemblerV2 itself (no hand-encoded opcode colors). 3 pinned runs
byte-identical, results md5 recorded.
Run: python3 .builder_queue/probe_ksys_paged_af3e.py
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

PT_TAG_WORD = 1535
PT_BASE_WORD = 1536
PT_ARM_WORD = 8211                     # PAGE_TABLE_WORD (word index)
TILE = (256, 19, 1, 2)                 # covers RAM words 8211/8212 only
VPN32_PTE_WORD = PT_BASE_WORD + 32     # 1568
VPN12_PTE_WORD = PT_BASE_WORD + 12     # 1548
PTE_RAM_PFN32 = 0x7 | (32 << 8)        # V|W|U, RAM frame pfn 32 -> words 8192..8447
PTE_PIX_PFN7 = 0xF | (7 << 8)          # V|W|U|PIX -> image words 1792..2047
VA_KSYS = (32 << 8) + 2                # 8194 -> paddr 8194 = KSYS_PC
WORD_KSYS = 8194
WORD_SYSPC = 8205                      # SYSCALL_PC_ADDR >> 2
WORD_TICKPC = 8210
KF_WORD = 8193
REDIRECT_ROW, REDIRECT_COL = 30, 8     # NOT the planted trampoline col 0
KSYS_PACKED = (REDIRECT_ROW << 16) | REDIRECT_COL   # 1966088
ATTACKER_WORD0 = REDIRECT_ROW * 64 + REDIRECT_COL * 4  # 1952 (w=64, x=32)
assert 1792 <= ATTACKER_WORD0 < 2048
GADGET_LINES = ["LDI r2 52", "PRT r2", "HALT"]
ARM_SNIPPET = "LDI r15 %d\nLDI r14 %d\nST r15 r14\n" % (PT_ARM_WORD,
                                                        PT_BASE_WORD)


def bake(text):
    from tools.glyph_gpt.baker import bake_image
    return bake_image(text, cols_instrs=16, min_rows=64, out_path=None)


def stamp_image(img, stamps):
    h, w, _ = img.shape
    total = h * w
    for word, val in stamps.items():
        idx = int(word) % total
        img[idx // w, idx % w] = (
            (val >> 16) & 0xFF, (val >> 8) & 0xFF, val & 0xFF)
    return img


def img_word(img, word):
    h, w, _ = img.shape
    idx = word % (h * w)
    px = img[idx // w, idx % w]
    return (int(px[0]) << 16) | (int(px[1]) << 8) | int(px[2])


def gadget_words():
    """The gadget's instruction words, straight from the real assembler."""
    from tools.glyph_isa_v2 import GlyphAssemblerV2, OpcodeMapV2
    img = GlyphAssemblerV2(OpcodeMapV2()).assemble(
        GADGET_LINES, width_instrs=16)
    words = []
    for i in range(img.shape[0] * img.shape[1]):
        px = img[i // img.shape[1], i % img.shape[1]]
        words.append((int(px[0]) << 16) | (int(px[1]) << 8) | int(px[2]))
        if len(words) >= 4 * len(GADGET_LINES):
            break
    assert len(words) == 4 * len(GADGET_LINES)
    return words


def paint_stores():
    """Paged STs painting the gadget via vpn 12 -> PIX pfn 7."""
    words = gadget_words()
    return "\n".join(
        "LDI r5 %d\nLDI r6 %d\nST r6 r5"
        % (words[k], (12 << 8) + (ATTACKER_WORD0 - 1792) + k)
        for k in range(len(words)))


def ksys_store():
    return "LDI r5 %d\nLDI r6 %d\nST r6 r5\n" % (KSYS_PACKED, VA_KSYS)


def run_leg(text, stamps=None, max_instructions=3000):
    from tools.glyph_process import GlyphProcessTable
    img = bake(text)
    h, w, _ = img.shape
    assert w * h >= 1570, "image must contain the PT window unwrapped"
    assert w > (REDIRECT_COL * 4 + 16), "image too narrow for gadget row"
    if stamps:
        stamp_image(img, stamps)
    table = GlyphProcessTable(cols_instrs=16, memory_words=16384)
    pid = table.spawn(image=img, tile=TILE, max_instructions=max_instructions)
    cpu = table.tasks[pid]["cpu"]
    task = table.tasks[pid]
    table._run_task(pid)
    gw = len(GADGET_LINES) * 4
    return {
        "exit_status": task["exit_status"],
        "faulted": bool(cpu.faulted),
        "fault_addr": (int(cpu.fault_addr)
                       if cpu.fault_addr is not None else None),
        "fault_reason": cpu.fault_reason,
        "halt_reason": (None if cpu.halt_reason is None
                        else str(cpu.halt_reason)),
        "mode_final": "USER" if cpu.mode == 1 else "SUPER",
        "output": [int(v) for v in cpu.output],
        "final_pc": [int(cpu.pc[0]), int(cpu.pc[1])],
        "kf_word_after": int(cpu.memory[KF_WORD]),
        "ksys_word_after": int(cpu.memory[WORD_KSYS]),
        "syspc_word_after": int(cpu.memory[WORD_SYSPC]),
        "tickpc_word_after": int(cpu.memory[WORD_TICKPC]),
        "gadget_pixels": [img_word(task["image"], ATTACKER_WORD0 + k)
                          for k in range(gw)],
    }


def main():
    out = {}

    # T1: arm PT -> paint gadget -> paged KSYS_PC rewrite -> SYSCALL.
    # The syscall is the trigger; the gadget is fully painted BEFORE the
    # rewrite (tick-14 ordering discipline: payload before the arm).
    paint = paint_stores() + "\n"
    text_t1 = (":__entry\n" + ARM_SNIPPET + paint + ksys_store()
               + "LDI r17 6\nSYSCALL r10 6\nHALT\n")
    out["T1_ksys_paged_rewrite_dispatch"] = run_leg(
        text_t1,
        {PT_TAG_WORD: 0x505447,
         VPN12_PTE_WORD: PTE_PIX_PFN7,
         VPN32_PTE_WORD: PTE_RAM_PFN32})

    # C1: same program minus the rewrite ST pair — ksys reads 0, the
    # direct fence-blind handler serves syscall 6 inline, no dispatch.
    text_c1 = ":__entry\n" + ARM_SNIPPET + paint \
        + "LDI r17 6\nSYSCALL r10 6\nHALT\n"
    out["C1_no_rewrite_direct_handler"] = run_leg(
        text_c1,
        {PT_TAG_WORD: 0x505447,
         VPN12_PTE_WORD: PTE_PIX_PFN7,
         VPN32_PTE_WORD: PTE_RAM_PFN32})

    # C2: no translation — vpn-32 PTE 0; the rewrite ST faults pte_invalid.
    text_c2 = ":__entry\n" + ARM_SNIPPET + paint + ksys_store() \
        + "LDI r17 6\nSYSCALL r10 6\nHALT\n"
    out["C2_no_translation_rewrite_faults"] = run_leg(
        text_c2,
        {PT_TAG_WORD: 0x505447,
         VPN12_PTE_WORD: PTE_PIX_PFN7})

    # C3: rot-guard — unpaged out-of-tile ST to word 8194, no PT.
    text_c3 = (":__entry\nLDI r5 %d\nLDI r6 %d\nST r6 r5\nHALT\n"
               % (KSYS_PACKED, WORD_KSYS))
    out["C3_unpaged_out_of_tile_ksys_ST_traps"] = run_leg(text_c3, None)

    results = out
    blob = json.dumps(results, sort_keys=True, indent=1)
    md5 = hashlib.md5(blob.encode()).hexdigest()
    print(blob)
    print("results_md5", md5)
    out_path = HERE / "probe_ksys_paged_af3e_results.json"
    out_path.write_text(json.dumps(
        {"results": results, "results_md5": md5}, indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
