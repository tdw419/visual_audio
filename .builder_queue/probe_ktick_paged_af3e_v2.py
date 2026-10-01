#!/usr/bin/env python3
"""Research tick 14 (af3e, 2026-09-28): paged rewrite of the GH-16
PREEMPTIVE-TICK control block — KTICK_PC (RAM word 8207), TIMER_COUNT
(8208), TIMER_RELOAD (8209) — the open NOT-proved sibling named in tick
13's receipt ("KTICK_PC/KSYS_PC same-family re-vectoring, source-read
labeled"). Tick 13 redirected the reaper: a POST-FAULT vector (the task
must trap first). The GH-16 tick arm (glyph_isa_v2.py:1362-1389) is a
DIFFERENT, stronger mechanism: it runs PREEMPTIVELY at ANY USER
instruction boundary, reads ktick/tcount LIVE from RAM, and vectors to
(ktick&0xFFFF, ktick>>16) in SUPER with the fence DISABLED — the same
"one mechanism that runs with the fence off" class as the reaper, but
reachable WITHOUT ever faulting. This tick measures whether a
tile-confined USER task can rewrite that dispatcher through translation
in the spawn(tile=...) posture.

Statically reachable: the tile covers RAM words 8211/8212 (the PT-arm
window of ticks 8-13), so words 8207-8210 sit just below the tile —
unmapped, exactly like tick 13's vector word. vpn 32 (vaddrs 8192..8447)
-> RAM frame pfn 32 maps all four words in one PTE. spawn() leaves the
timer block zeroed, so the TASK must also ARM the timer — the count
rewrite IS the arming (a second paged ST, same frame).

Source posture (read, not assumed):
  - ST paged arm :968-1034: USER translation applies; plain frame (no
    PIX flag) writes RAM at pfn*256+offset.
  - Tick arm :1362-1389: fires when _iso_enabled && was_user && mode
    USER && running && !faulted && ktick != 0 && tcount > 0; on fire it
    DECREMENTS/REWRITES TIMER_COUNT (engine-side guest-RAM write),
    saves TICK_PC (word 8210), snapshots regs, drops to SUPER, jumps to
    (ktick col, ktick row). One-shot when TIMER_RELOAD (8209) is 0.
  - The dispatcher VECTORS to raw (col, row) pixels: (8,30) -> pixel
    x = 8*4 = 32. Payload painted at words 1952..1955 (vpn 12 PIX pfn 7,
    tick-12/13 shape). PRT rd prints rd.

Prior-art grep (rule-5, before harness build):
  - BK-41: KSYS_PC guest SELF-ARM via UNPAGED PARALLEL_ST (syscall
    dispatcher; different block, different primitive).
  - Ticks 12/13: trampoline pixels + KFAULT_PC word — both POST-FAULT
    vectoring. GH-16 preemptive dispatch never probed paged or unpaged
    from a contained task (DEFECT-18 gate arms it host-side,
    cooperative, no containment).
  - No row composes paging x the GH-16 block. Net-new.

Legs (oracle only — twin has no tile predicate (BK-51) and the WGSL
walker has no GH-16 at all (no KTICK ref in wgsl_glyph_isa_v2.py;
source-read, labeled)):
  T1  paged timer self-arm + tick redirect + payload paint, then an
      INFINITE USER SPIN (LDI r31 1; :s JMPR r31 loop) — the tick MUST
      fire preemptively or the task never reaches anything observable.
      Expected if the mechanism is live: tick fires, SUPER executes the
      attacker PRT at (32,30) -> cpu.output == [canary 52], mode SUPER,
      tcount engine-decremented to 0, TICK_PC word 8210 = interrupted
      spin PC, loud opcode-None halt on the zero pixel after the payload.
  C1  control, no timer arm (count-rewrite ST removed; ktick still
      rewritten): tcount stays 0 -> tick arm never fires -> spin burns
      max_instructions in USER, output [], tcount 0 — proves firing
      needed the paged COUNT write, not the ktick rewrite alone.
  C2  control, no translation (vpn-32 PTE left 0): both control-block
      STs fault pte_invalid immediately, vector to the REAL reaper
      trampoline (col 0, row 30), parked exit 1, control words stay 0 —
      proves the rewrite went through translation, no unpaged fence hole
      for the MMIO RAM words.
  C3  rot-guard, unpaged out-of-tile ST to word 8208 with NO PT armed:
      traps E-K1 (fault_addr 8208*4 = 32832), vectors to the real
      trampoline — the tile fence is live for the same words when
      translation is not armed (the BK-66-C2 shape, GH-16 flavor).

Verdicts from exit_status + fault fields + cpu.output + RAM readback
(words 8193/8207/8208/8209/8210) + final PC BYTES, never stdout. PRT
color resolved at runtime from OpcodeMapV2, never hand-encoded. 3 pinned
runs byte-identical, results md5 recorded.
Run: python3 .builder_queue/probe_ktick_paged_af3e_v2.py
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
VA_KTICK = (32 << 8) + 15              # 8207 -> paddr 8207 = KTICK_PC
VA_TCOUNT = (32 << 8) + 16             # 8208 -> paddr 8208 = TIMER_COUNT
WORD_KTICK, WORD_TCOUNT, WORD_TRELOAD, WORD_TICKPC = 8207, 8208, 8209, 8210
KF_WORD = 8193
REDIRECT_ROW, REDIRECT_COL = 30, 8     # NOT the planted trampoline col 0
REDIRECT_PC = (REDIRECT_ROW << 16) | REDIRECT_COL   # 1966344
ATTACKER_WORD0 = REDIRECT_ROW * 64 + REDIRECT_COL * 4  # 1952 (w=64, x=32)
assert 1792 <= ATTACKER_WORD0 < 2048
PRT_CANARY = 52                        # what the attacker PRT prints
ARM_SNIPPET = "LDI r15 %d\nLDI r14 %d\nST r15 r14\n" % (PT_ARM_WORD,
                                                        PT_BASE_WORD)
# Infinite USER spin: r31 = pixel-PC of the spin JMPR itself.
# The spin sits at the END of the program; we compute its address from
# the baked layout below instead of hand-counting (tick-13 discipline).
SPIN_VAL = 1                           # JMPR r31 with r31 = packed pc


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


def attacker_pixel_words():
    """`PRT r6` (opcode color) + r6 selector + canary + zero."""
    from tools.glyph_isa_v2 import OpcodeMapV2
    r, g, b = (int(v) for v in OpcodeMapV2().opcode_to_rgb("PRT"))
    return [(r << 16) | (g << 8) | b, 6, PRT_CANARY, 0]


def paint_stores():
    """4 paged STs painting the payload via vpn 12 -> PIX pfn 7."""
    rw = attacker_pixel_words()
    return "\n".join(
        "LDI r5 %d\nLDI r6 %d\nST r6 r5"
        % (rw[k], (12 << 8) + (ATTACKER_WORD0 - 1792) + k)
        for k in range(4))


def count_store():
    return "LDI r5 2\nLDI r6 %d\nST r6 r5\n" % VA_TCOUNT


def ktick_store():
    return "LDI r5 %d\nLDI r6 %d\nST r6 r5\n" % (REDIRECT_PC, VA_KTICK)


def spin(suffix):
    # spin loop: LDI r31 <packed pc of next instr> ; JMPR r31
    # packed pc = (row<<16)|col-in-instrs. We don't know the row yet;
    # instead spin on a self-contained loop: LDI r31 0 is (0,0) — wrong.
    # Use JZ-style absolute JMP: assembler packs (x,y) label-free via
    # numeric coords. We emit a numeric JMP to our own line instead.
    return suffix  # placeholder, replaced per-leg below


def run_leg(text, stamps=None, max_instructions=3000):
    from tools.glyph_process import GlyphProcessTable
    img = bake(text)
    h, w, _ = img.shape
    assert w * h >= 1570, "image must contain the PT window unwrapped"
    assert w > REDIRECT_COL * 4 + 4, "image too narrow for redirect col"
    if stamps:
        stamp_image(img, stamps)
    table = GlyphProcessTable(cols_instrs=16, memory_words=16384)
    pid = table.spawn(image=img, tile=TILE, max_instructions=max_instructions)
    cpu = table.tasks[pid]["cpu"]
    task = table.tasks[pid]
    table._run_task(pid)
    return {
        "program_tail": text.splitlines()[-6:],
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
        "ktick_word_after": int(cpu.memory[WORD_KTICK]),
        "tcount_word_after": int(cpu.memory[WORD_TCOUNT]),
        "treload_word_after": int(cpu.memory[WORD_TRELOAD]),
        "tickpc_word_after": int(cpu.memory[WORD_TICKPC]),
        "redirect_pixels": [img_word(task["image"], ATTACKER_WORD0 + k)
                            for k in range(4)],
    }


def main():
    out = {}

    # T1: paged timer self-arm + tick redirect + payload paint + spin.
    # ORDER DISCIPLINE (learned from run-1, fixed pre-evidence): the tick
    # fires on the 2nd USER boundary after the count lands — i.e. MID-
    # paint if the payload is painted after the arm (run-1: tick fired
    # at the first paint LDI, redirected onto still-zero pixels). The
    # payload must be painted BEFORE the timer is armed, and the tick
    # must land in the SPIN so the preemptive nature is what's tested.
    paint = paint_stores() + "\n"
    pre = (ARM_SNIPPET + paint)
    n_instr = len([l for l in pre.splitlines() if l.strip()])
    # spin: LDI r31 <canary> at col n_instr, LDI r32 <packed own pc>, then
    # JMPR r32 self-loop. packed pc = (row<<16)|col; LDI at row 0 col
    # n_instr -> JMPR at n_instr+2 targets n_instr.
    spin_text = ("LDI r31 %d\nLDI r30 %d\nJMPR r30\n"
                 % (PRT_CANARY, n_instr))
    text_t1 = (":__entry\n" + pre + count_store() + ktick_store()
               + spin_text)
    out["T1_tick_redirect_preemptive"] = run_leg(
        text_t1,
        {PT_TAG_WORD: 0x505447,
         VPN12_PTE_WORD: PTE_PIX_PFN7,
         VPN32_PTE_WORD: PTE_RAM_PFN32})

    # C1: same ORDER but NO count store — timer never arms, spin burns
    # budget in USER with the tick armed-but-countless.
    pre_c1 = ARM_SNIPPET + paint
    n1 = len([l for l in pre_c1.splitlines() if l.strip()])
    spin_c1 = "LDI r31 %d\nLDI r30 %d\nJMPR r30\n" % (PRT_CANARY, n1)
    text_c1 = ":__entry\n" + pre_c1 + ktick_store() + spin_c1
    out["C1_no_timer_arm_spin_only"] = run_leg(
        text_c1,
        {PT_TAG_WORD: 0x505447,
         VPN12_PTE_WORD: PTE_PIX_PFN7,
         VPN32_PTE_WORD: PTE_RAM_PFN32},
        max_instructions=3000)

    # C2: no translation — vpn-32 PTE 0; the count ST faults immediately.
    text_c2 = ":__entry\n" + ARM_SNIPPET + count_store() + ktick_store() \
        + paint_stores() + "\nHALT\n"
    out["C2_no_translation_rewrite_faults"] = run_leg(
        text_c2,
        {PT_TAG_WORD: 0x505447,
         VPN12_PTE_WORD: PTE_PIX_PFN7})

    # C3: rot-guard — unpaged out-of-tile ST to the timer word, no PT.
    text_c3 = (":__entry\nLDI r5 2\nLDI r6 %d\nST r6 r5\nHALT\n"
               % WORD_TCOUNT)
    out["C3_unpaged_out_of_tile_timer_ST_traps"] = run_leg(text_c3, None)

    results = out
    blob = json.dumps(results, sort_keys=True, indent=1)
    md5 = hashlib.md5(blob.encode()).hexdigest()
    print(blob)
    print("results_md5", md5)
    out_path = HERE / "probe_ktick_paged_af3e_v2_results.json"
    out_path.write_text(json.dumps(
        {"results": results, "results_md5": md5}, indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
