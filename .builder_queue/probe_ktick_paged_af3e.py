#!/usr/bin/env python3
"""Research tick 14 (af3e, 2026-09-28): paged rewrite of the GH-16 KTICK_PC
VECTOR WORD (RAM word 8195 = 0x8008, BOX_MMIO_BASE+0x3C) — the open
NOT-proved sibling from tick 13 (its receipt explicitly labels KTICK_PC /
KSYS_PC "same LIVE-read family by source read (:1166, :1364), not probed
this tick"). Tick 13 rewrote KFAULT_PC (word 8193); the tick arm at
glyph_isa_v2.py:1364 reads KTICK_PC LIVE from RAM the same way, and a
guest-driven timer (TIMER_COUNT word 8196 is likewise plain guest RAM) can
fire the tick arm ON DEMAND — no kernel, no fault needed.

Source posture (read, not assumed):
  - Tick arm :1363-1385: fires only when `_iso_enabled and was_user and
    mode==USER and running and not faulted`; reads
    ktick = self.memory[KTICK_PC_ADDR >> 2] (:1364) LIVE; if ktick != 0
    decrements TIMER_COUNT (:1366-1369); on count==0 reloads from
    TIMER_RELOAD (:1371-1372), saves TICK_PC (:1375), snapshots the
    register file (DEFECT-18, :1379-1380), drops to SUPER (:1381) and
    jumps to (ktick_col*INSTR_WIDTH, ktick_row) (:1382-1385).
  - The GH-16 gate's own privilege claim (tests/test_gh16_preemption.py
    docstring, item 4): "USER task cannot disable the timer or tick
    handler ... USER store traps to KFAULT_PC". In the paged posture that
    is exactly what should FAIL: the vector word is plain RAM and a paged
    USER ST reaches any paddr.
  - Paged ST plain-page arm :1038-1074 (the tick-13 V1 path): a full-flag
    plain PTE admits the landing; PTE_W is checked (:1001) so the PTE
    must carry W — tick 13's V|W|U pfn-32 PTE is reused verbatim.
  - Prior family findings that make the compose interesting: BK-41
    measured KSYS_PC guest-writable via UNPAGED PARALLEL_ST (self-arm);
    tick 13 measured KFAULT_PC paged-writable via a single translated ST.
    KTICK_PC is the remaining vector word in the family with no measured
    row at all (KSYS_PC's paged variant is also open, noted in the
    receipt's NOT-proved: this tick does NOT close it).

Prior-art grep (rule-5, before harness build):
  - BK-41 (RESEARCH_ksys_pc_self_arm.md): KSYS_PC word 8194, UNPAGED
    PARALLEL_ST primitive, armed-dispatcher posture — different vector,
    different primitive, no paging.
  - Tick 13 (BK-71): KFAULT_PC word 8193, paged ST — explicitly leaves
    KTICK_PC/KSYS_PC unprobed.
  - tests/test_gh16_preemption.py + tests/test_defect18_tick_regfile.py:
    the GH-16 gates arm KTICK_PC host-side and never probe guest
    writeability of the vector word in the paged posture.
  - No RESEARCH_*.md or backlog row touches KTICK_PC at all (grep). Net-new.

Legs (oracle only — twin has no tile predicate, BK-51; the twin's paged
walker is also flag-blind per BK-64/65 so the compose shape differs;
spawn(tile=(256,19,1,2)) posture identical to ticks 12/13; PT armed by
the task's own lawful in-tile ST to word 8211, tag 0x505447 at word 1535,
PT base 1536; PT words are image-stamped per the corrected BK-60-L4
discipline):

  T1  hostile re-arm: the task paged-STs its own packed PC
      (ATTACK_ROW<<16)|0 into vaddr 8451 (=(33<<8)|3 -> paddr 8193+2 =
      word 8195 = KTICK_PC; SAME V|W|U pfn-32 PTE as tick 13's V1 — one
      PTE covers 8193/8194/8195), and paged-STs TIMER_COUNT (word 8196,
      vaddr 8452) to 1. The next in-tile instruction completion then
      decrements 1 -> 0 and the tick arm FIRES with ktick = the attacker
      PC: execution lands at the task-chosen pixel in SUPER (the
      DEFECT-18 register snapshot happens; TICK_PC word 8197 records the
      interrupted PC — engine-written, the leg's internal control).
      Observable: tick_pc_word_after != 0 (the arm fired), final PC on
      ATTACK_ROW, mode SUPER.
  T2  full compose: T1 plus PIX-frame paged stores painting a PRT
      payload at the attacker pixel, so the tick handler itself executes
      attacker code in SUPER: cpu.output non-empty with the payload
      signature. Loud opcode-None tail after the payload disclosed.
  D1  disable-leg (the GH-16 gate item-4 claim, paged posture): the task
      paged-STs 0 into KTICK_PC and TIMER_COUNT=1, then runs an
      instruction budget an armed timer would preempt; observable:
      tick_pc_word_after == 0 (timer disabled by a USER task — the
      documented privilege property inverted through translation).
  C1  control, no translation (vpn-33 PTE left 0): the T1 rewrite ST
      pte_invalids (vaddr 0x8454 byte-space) BEFORE any tick can fire,
      vectors through the LIVE kf read (word 8193 untouched, 1966080)
      to the REAL trampoline (0,30), parked exit 1, tick never fires
      (tick_pc stays 0) — proves the rewrite went through TRANSLATION.
  C2  rot-guard, honest tick: arm KTICK_PC host-side to a benign
      in-image handler row (row 40, col 0: PRT 0x5150 then HALT),
      TIMER_COUNT=2 host-side; task = ARM_SNIPPET + HALT. Expected:
      tick fires, TICK_PC written, mode returns via the handler's
      JMPR/TICK_PC restore... the engine's restore is DEFECT-18's
      _tick_regs/_tick_pc on the NEXT JMPR to _tick_pc — the handler
      here just PRTs and HALTs (running=False; snapshot discarded —
      same shape as the defect-18 L1 handler WITHOUT the return leg).
      Verdicts: tick fired once (handler output seen), TICK_PC nonzero,
      exit clean. Pins the honest-tick shape so T1/T2/D1 are measured
      against a LIVE mechanism, not a dead one.

Verdicts from exit_status + fault fields + cpu.output + RAM readbacks of
words 8195/8196/8197 + final PC BYTES, never stdout. Opcode colors
resolved at runtime from OpcodeMapV2, never hand-encoded. 3 pinned runs,
results md5 recorded.
Run: python3 .builder_queue/probe_ktick_paged_af3e.py
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
PT_ARM_WORD = 8211                 # PAGE_TABLE_WORD (word index)
TILE = (256, 19, 1, 2)             # covers RAM words 8211/8212 only
VPN33_PTE_WORD = PT_BASE_WORD + 33  # 1569
PTE_RAM_PFN32 = 0x7 | (32 << 8)    # V|W|U, RAM frame pfn 32 -> words 8192..8447
PTE_PIX_PFN3 = 0xF | (3 << 8)      # pfn 3 -> image words 768..1023
VA_KF = (33 << 8) | 1              # 8449 -> paddr 8193 (KFAULT_PC, tick 13)
VA_KTICK = (33 << 8) | 3           # 8451 -> paddr 8195 (KTICK_PC)
VA_TCOUNT = (33 << 8) | 4          # 8452 -> paddr 8196 (TIMER_COUNT)
KF_WORD = 8193
KTICK_WORD = 8195
TCOUNT_WORD = 8196
TICK_PC_WORD = 8197
ARM_SNIPPET = "LDI r15 %d\nLDI r14 %d\nST r15 r14\n" % (PT_ARM_WORD,
                                                        PT_BASE_WORD)
ATTACK_ROW = 20                    # task-chosen tick-handler row (in-image)
ATTACK_COL = 0
ATTACK_PC = (ATTACK_ROW << 16) | ATTACK_COL
REDIRECT_ROW = 30                  # the spawn-armed reaper row (C1)
HONEST_ROW = 40                    # C2's benign handler row


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


def payload_pixel_words():
    """4 pixel-words: `PRT r6` + r6 + canary + 0 (tick-13 V2 shape)."""
    from tools.glyph_isa_v2 import OpcodeMapV2
    r, g, b = (int(v) for v in OpcodeMapV2().opcode_to_rgb("PRT"))
    return [(r << 16) | (g << 8) | b, 6, 0x5150, 0]


def run_leg(text, stamps=None, seed=None):
    """Real spawn(tile=...) posture: the TABLE arms the reaper
    (KFAULT_PC = 30<<16) and wraps the image (HALT at (0,30)).
    `seed` = host-side post-spawn MMIO seeds (word -> value) for C2."""
    from tools.glyph_process import GlyphProcessTable

    img = bake(text)
    h, w, _ = img.shape
    assert w * h >= 1570, "image must contain the PT window unwrapped"
    assert h > ATTACK_ROW, f"image too short for attack row {ATTACK_ROW}"
    assert h > HONEST_ROW, f"image too short for honest row {HONEST_ROW}"
    if stamps:
        stamp_image(img, stamps)
    table = GlyphProcessTable(cols_instrs=16, memory_words=16384)
    pid = table.spawn(image=img, tile=TILE, max_instructions=500)
    cpu = table.tasks[pid]["cpu"]
    task = table.tasks[pid]
    if seed:
        for word, val in seed.items():
            cpu.memory[word] = val
    table._run_task(pid)
    return {
        "program": text,
        "exit_status": task["exit_status"],
        "faulted": bool(cpu.faulted),
        "fault_addr": (int(cpu.fault_addr)
                       if cpu.fault_addr is not None else None),
        "fault_reason": cpu.fault_reason,
        "halt_reason": cpu.halt_reason,
        "mode_final": "USER" if cpu.mode == 1 else "SUPER",
        "output": [int(v) for v in cpu.output],
        "final_pc": [int(cpu.pc[0]), int(cpu.pc[1])],
        "kf_word_after": int(cpu.memory[KF_WORD]),
        "ktick_word_after": int(cpu.memory[KTICK_WORD]),
        "tcount_word_after": int(cpu.memory[TCOUNT_WORD]),
        "tick_pc_after": int(cpu.memory[TICK_PC_WORD]),
        "regs_snapshot": {"r10": int(cpu.registers[10]),
                          "r6": int(cpu.registers[6])},
    }


def legs():
    out = {}
    rw = payload_pixel_words()

    # T1: hostile re-arm. Rewrite KTICK_PC (word 8195, via vaddr 8451)
    # to the task-chosen PC and TIMER_COUNT (word 8196, vaddr 8452) to 1.
    # The very next instruction completion fires the tick arm with
    # ktick = ATTACK_PC: SUPER-mode vector to (ATTACK_COL*4, ATTACK_ROW).
    rearm = ("LDI r5 %d\nLDI r6 %d\nST r6 r5\n"   # KTICK_PC = attack PC
             % (ATTACK_PC, VA_KTICK)
             + "LDI r5 1\nLDI r6 %d\nST r6 r5\n"  # TIMER_COUNT = 1
             % VA_TCOUNT)
    out["T1_ktick_paged_rearm_vector"] = run_leg(
        ":__entry\n" + ARM_SNIPPET + rearm + "HALT\n",
        {PT_TAG_WORD: 0x505447, VPN33_PTE_WORD: PTE_RAM_PFN32})

    # T2: full compose — ALSO paint a PRT payload at the attack pixel
    # (ATTACK_COL*4 .. +3, ATTACK_ROW) via a PIX-frame PTE, so the tick
    # vector EXECUTES attacker code in SUPER.
    attack_word0 = ATTACK_ROW * 64 + ATTACK_COL * 4   # (w=64, x=0)
    # PIX pfn = attack_word0 // 256 (LINEAR pfn*256+offset, tick-4 H-legs);
    # vaddr = (pfn<<8) + offset; PTE at PT_BASE + pfn.
    attack_pfn = attack_word0 // 256
    frame_base = attack_pfn * 256
    assert frame_base <= attack_word0 < frame_base + 256, (
        "attack pixels span a frame boundary")
    attacker_stores = "\n".join(
        "LDI r5 %d\nLDI r6 %d\nST r6 r5"
        % (rw[k], (attack_word0 - frame_base) + k)
        for k in range(4))
    attack_va_base = attack_pfn << 8
    out["T2_ktick_paged_rearm_plus_payload"] = run_leg(
        ":__entry\n" + ARM_SNIPPET + rearm + attacker_stores + "\nHALT\n",
        {PT_TAG_WORD: 0x505447,
         PT_BASE_WORD + attack_pfn: PTE_PIX_PFN3,
         VPN33_PTE_WORD: PTE_RAM_PFN32})

    # D1: the GH-16 privilege claim, paged posture — USER zeroes the
    # tick vector + timer through translation; nothing fires.
    disable = ("LDI r5 0\nLDI r6 %d\nST r6 r5\n"  # KTICK_PC = 0
               % VA_KTICK
               + "LDI r5 1\nLDI r6 %d\nST r6 r5\n" % VA_TCOUNT)
    out["D1_ktick_paged_disable"] = run_leg(
        ":__entry\n" + ARM_SNIPPET + disable + "HALT\n",
        {PT_TAG_WORD: 0x505447, VPN33_PTE_WORD: PTE_RAM_PFN32})

    # C1: vpn-33 PTE left 0 — the first rewrite ST pte_invalids; vectors
    # to the REAL trampoline; tick never armed (word 8195 stays 0);
    # tick_pc stays 0.
    out["C1_no_translation_rewrite_faults"] = run_leg(
        ":__entry\n" + ARM_SNIPPET + rearm + "HALT\n",
        {PT_TAG_WORD: 0x505447})

    # C2 rot-guard: honest tick — host arms KTICK_PC to a benign handler
    # at (0, HONEST_ROW), TIMER_COUNT=2; task arms paging then HALTs...
    # but a task HALTing in USER after count hits 0: the tick fires on
    # the instruction BEFORE the HALT (ADD r0 r0 filler), handler PRTs,
    # HALTs (running=False). Tick observable: tick_pc nonzero + handler
    # output [0x5150] + tcount reloaded to 2.
    honest_va = [(40 * 64) + k for k in range(4)]  # image words 2560..2563
    # honest handler pixels stamped directly into the image (host-side,
    # like wrap_with_reaper's HALT): PRT r6 / r6=6 / 0x5150 / 0
    honest_stamp = {word: val for word, val
                    in zip(honest_va, rw)}
    honest_stamp[PT_TAG_WORD] = 0x505447
    honest_stamp[VPN33_PTE_WORD] = PTE_RAM_PFN32
    out["C2_honest_tick_rotguard"] = run_leg(
        ":__entry\n" + ARM_SNIPPET + "ADD r0 r0\nHALT\n",
        honest_stamp,
        seed={KTICK_WORD: (HONEST_ROW << 16) | ATTACK_COL,
              TCOUNT_WORD: 2,
              TICK_PC_WORD: 0})

    return out


def main():
    results = legs()
    blob = json.dumps(results, sort_keys=True, indent=1)
    md5 = hashlib.md5(blob.encode()).hexdigest()
    print(blob)
    print("results_md5", md5)
    out_path = HERE / "probe_ktick_paged_af3e_results.json"
    out_path.write_text(json.dumps(
        {"results": results, "results_md5": md5}, indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
