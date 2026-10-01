#!/usr/bin/env python3
"""Research tick 18 (af3e, 2026-09-28): the GH-16 PREEMPTIVE-TICK handler as
a foothold — TWO measured shapes:

  (a) COMPOSED with the E-K2 syscall gate from INSIDE the tick handler, and
  (b) PERSISTENT via TIMER_RELOAD + the DEFECT-18 JMPR restore — a RESIDENT
      PREEMPTIVE foothold: attacker code re-entering SUPER from HARDWARE TIME
      on a period, forever, while the USER program never issues a single
      SYSCALL.

Named NOT-proved by tick 17 (RESEARCH_super_chain_foothold_af3e.md NOT-proved
bullet: "GH-16 KTICK re-arm from a tick handler + KFAULT_PC chaining under
E-K1 traps ... same family by source-read, unprobed") and by tick 14
(RESEARCH_ktick_paged_rewrite_af3e.md: "TIMER_RELOAD periodic re-fire"
carried). Prior-art grep BEFORE harness build: tick 14 measured the ONE-SHOT
paged rewrite of KTICK_PC (8207)/TIMER_COUNT (8208) with a payload that PRTs
and never returns; tick 17 measured the SYSCALL-side chain. No row composes
tick-entry + E-K2 composition, or tick-entry + proper JMPR return +
TIMER_RELOAD periodicity. Net-new.

Mechanism (tools/glyph_isa_v2.py, source-read, line refs at HEAD a2ac273a):
- Tick arm :1362-1385: after EVERY step where was_user and mode==USER and
  running and not faulted: ktick = memory[8207]; if ktick != 0 and
  TIMER_COUNT (8208) > 0: decrement; on 0 load TIMER_RELOAD (8209) into
  TIMER_COUNT; save interrupted PC to TICK_PC (8210); snapshot regs to
  _tick_regs, interrupted PC to _tick_pc; mode=SUPER; jump to the packed
  pixel PC in word 8207. NO fault, NO guest cooperation beyond spinning.
- JMPR arm :1245-1258: JMPR to the exact _tick_pc restores the snapshot
  register file, clears it, and re-enters USER (DEFECT-18 ruling 2026-09-12
  option (a)) — the handler's designed return path. TICK_PC (8210) holds
  the interrupted PC in the same packing, so `LD r4 <- 8210; JMPR r4` is
  the generic return (the SUPER+window LD takes the :836 exemption).
- SYSCALL arm :1166-1189: fires regardless of how SUPER was entered —
  ksys = memory[8194]; if non-zero: save resume PC to SYSCALL_PC (8201),
  _syscall_regs snapshot, jump ksys. SYSRET (:1193-1207) restores regs,
  sets mode=USER UNCONDITIONALLY, and resumes at the packed PC in 8201.
  CONSEQUENCE (measured here, T1): a tick handler that SYSCALLs loses its
  JMPR return — SYSRET's resume (word 8201 = the handler's own fall-through)
  wins over the pending _tick_pc, mode drops to USER at the WRONG
  continuation point, and the interrupted USER context is never resumed.
  _tick_regs/_tick_pc stay armed (stale snapshot).
- ST/LD arm :968/:836 (identical text): pt_base!=0 and NOT(SUPER and addr
  in MMIO words 8192..8447) -> paged walk. A SUPER access to the window
  falls through BOTH the walk and the E-K1 box arm to the plain unguarded
  load/store (the :968 exemption, measured serving in ticks 16/17).

Legs (all inside the REAL contained-spawn posture, tile (256,19,1,2),
PT armed by the task's lawful in-tile ST to word 8211, tag 0x505447 at
1535, PT base 1536; vpn-12 PIX pfn 7 payload paint; vpn-32 RAM pfn 32;
ALL payload instruction words from the REAL GlyphAssemblerV2, never
hand-encoded; verdicts from exit_status + fault fields + cpu.output +
final PC + RAM readback BYTES, never stdout):

  T1  TICK-CHAIN (composed with E-K2): payload_ktick (31,8) [PRT 77;
      ST ksys<-gadget_g packed PC; SYSCALL r10 7] and gadget_g (30,8)
      [PRT 52; ST ksys<-0; SYSRET]; arm TCOUNT=2, TRELOAD=0, KTICK->
      (31,8); spin in USER. MEASURED (run set, 3x pinned): output [77,52]
      — SUPER payload entered from the TICK path, composed through the
      E-K2 gate — then SYSRET resumes USER at the handler's FALL-THROUGH
      (row 31, col 14), never at the interrupted spin: opcode-None halt,
      _tick_regs/_tick_pc stale, exit 0. The syscall-composed tick
      foothold is STRUCTURALLY ONE-SHOT: the composition destroys the
      tick return.
  T2  RESIDENT PREEMPTIVE FOOTHOLD (the load-bearing leg): payload_ktick
      returns properly [PRT 77; LDI r7 8210; LD r4 r7; JMPR r4 — the
      TICK_PC restore]; TCOUNT=2, TRELOAD=2 (periodic); NO SYSCALL
      ANYWHERE. Expected: output = [77] x N (N >> 1) — attacker code
      re-executes in SUPER on a hardware period for the task's whole
      lifetime, entered from plain USER spinning. If instead the tick
      fires once, the foothold is not resident.
  C1  ONE-SHOT control: identical to T2 but TRELOAD=0 — exactly ONE
      fire; output [77] once, then the spin burns the rest of the budget
      in USER. Isolates TIMER_RELOAD periodicity as the persistence
      mechanism.
  C2  NO-ARM control: identical to T2 minus the count/ktick stores —
      tick never fires, output []. Proves the arming writes (not mere
      PT presence) create the foothold.
  C3  NO-RETURN control: T2's periodic arm but payload PRTs and walks
      off (tick-14 shape + reload) — the tick can only re-fire if the
      handler RETURNS to USER; expected single fire + halt inside the
      handler. Isolates the JMPR return as the second persistence
      condition.
  C4  ROT-GUARD: unpaged out-of-tile USER ST to word 8207, no PT — the
      E-K1 tile fence must trap (fault_addr 8207*4 = 32828, BK-66-C2
      shape, KTICK flavor). The fence is live for the word when
      translation is not armed.

3 pinned runs must be byte-identical (results md5 recorded). Run:
  python3 .builder_queue/probe_ktick_chain_af3e.py
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
WORD_KTICK = 8207                      # KTICK_PC_ADDR >> 2 (BOX_MMIO+0x3C)
WORD_TCOUNT = 8208                     # TIMER_COUNT_ADDR >> 2
WORD_TRELOAD = 8209                    # TIMER_RELOAD_ADDR >> 2
WORD_TICKPC = 8210                     # TICK_PC_ADDR >> 2
WORD_KSYS = 8194                       # KSYS_PC_ADDR >> 2
WORD_SYSPC = 8201                      # SYSCALL_PC_ADDR >> 2
WORD_SYSA0 = 8205                      # SYS_A0_ADDR >> 2
VA_KTICK = (32 << 8) + 15              # vaddr encoding paddr 8207 (vpn 32, off 15)
VA_TCOUNT = (32 << 8) + 16             # paddr 8208
VA_TRELOAD = (32 << 8) + 17            # paddr 8209
KT_ROW, KT_COL = 31, 8                 # tick payload (col<=15, in vpn-12 frame)
KT_PACKED = (KT_ROW << 16) | KT_COL
KT_WORD0 = KT_ROW * 64 + KT_COL * 4    # 31*64+32 = 2016
G_ROW, G_COL = 30, 8                   # syscall gadget (T1 only)
G_PACKED = (G_ROW << 16) | G_COL
G_WORD0 = G_ROW * 64 + G_COL * 4       # 30*64+32 = 1952
SPIN_ROW = 0
assert 1792 <= KT_WORD0 < 2048, "tick payload in vpn-12 PIX pfn 7 frame"
assert 1792 <= G_WORD0 < 2048, "gadget in vpn-12 PIX pfn 7 frame"
assert KT_WORD0 != G_WORD0

GADGET_KTICK_SYSCALL = [               # T1: composes with the E-K2 gate
    "LDI r9 77", "PRT r9",
    "LDI r6 %d" % G_PACKED,
    "LDI r7 %d" % WORD_KSYS,
    "ST r7 r6",                        # :968-exempt SUPER re-arm of KSYS_PC
    "SYSCALL r10 7",                   # compose through the E-K2 gate
]
GADGET_G = [                           # T1: dispatched from inside the handler
    "LDI r2 52", "PRT r2",
    "LDI r6 0",
    "LDI r7 %d" % WORD_KSYS,
    "ST r7 r6",                        # re-arm ksys BACK to 0 (kernel-default)
    "SYSRET",
]
GADGET_KTICK_RETURN = [                # T2/C1: the DEFECT-18 proper return
    "LDI r9 77", "PRT r9",
    "LDI r7 %d" % WORD_TICKPC,
    "LD r4 r7",                        # LD addr in rs2: r4 <- memory[8210]
    "JMPR r4",                         # target == _tick_pc -> restore + USER
]
GADGET_KTICK_NORETURN = ["LDI r9 77", "PRT r9"]  # C3: walks off (tick-14 shape)
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


def assembled_words(lines, width_instrs=16):
    """Instruction words straight from the real assembler."""
    from tools.glyph_isa_v2 import GlyphAssemblerV2, OpcodeMapV2
    img = GlyphAssemblerV2(OpcodeMapV2()).assemble(
        lines, width_instrs=width_instrs)
    words = []
    total = img.shape[0] * img.shape[1]
    for i in range(total):
        px = img[i // img.shape[1], i % img.shape[1]]
        words.append((int(px[0]) << 16) | (int(px[1]) << 8) | int(px[2]))
        if len(words) >= 4 * len(lines):
            break
    assert len(words) == 4 * len(lines)
    return words


def paint_stores(lines, base_word0):
    """Paged STs painting `lines` at base_word0 via vpn 12 -> PIX pfn 7."""
    words = assembled_words(lines)
    frame0 = 1792
    return "\n".join(
        "LDI r5 %d\nLDI r6 %d\nST r6 r5"
        % (words[k], (12 << 8) + (base_word0 - frame0) + k)
        for k in range(len(words)))


def run_leg(text, stamps=None, max_instructions=4000):
    from tools.glyph_process import GlyphProcessTable
    img = bake(text)
    h, w, _ = img.shape
    assert w * h >= 2112, "image must contain the PT window + payload rows"
    if stamps:
        stamp_image(img, stamps)
    table = GlyphProcessTable(cols_instrs=16, memory_words=16384)
    pid = table.spawn(image=img, tile=TILE, max_instructions=max_instructions)
    cpu = table.tasks[pid]["cpu"]
    task = table.tasks[pid]
    table._run_task(pid)
    task_img = task["image"]
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
        "output_len": len(cpu.output),
        "final_pc": [int(cpu.pc[0]), int(cpu.pc[1])],
        "ktick_word_after": int(cpu.memory[WORD_KTICK]),
        "tcount_word_after": int(cpu.memory[WORD_TCOUNT]),
        "treload_word_after": int(cpu.memory[WORD_TRELOAD]),
        "tickpc_word_after": int(cpu.memory[WORD_TICKPC]),
        "ksys_word_after": int(cpu.memory[WORD_KSYS]),
        "syspc_word_after": int(cpu.memory[WORD_SYSPC]),
        "sysa0_word_after": int(cpu.memory[WORD_SYSA0]),
        "kt_pixels": [img_word(task_img, KT_WORD0 + k)
                      for k in range(4 * len(GADGET_KTICK_SYSCALL))],
        "g_pixels": [img_word(task_img, G_WORD0 + k)
                     for k in range(4 * len(GADGET_G))],
    }


def spin_text(n_instr):
    """Infinite USER spin at instr index n_instr: LDI r31 <canary>;
    LDI r30 <packed own pc>; JMPR r30 self-loop."""
    return ("LDI r31 99\nLDI r30 %d\nJMPR r30\n"
            % ((SPIN_ROW << 16) | (n_instr + 1)))


def arm_and_spin(payload_text, count, reload_):
    pre = (ARM_SNIPPET + payload_text
           + "LDI r5 %d\nLDI r6 %d\nST r6 r5\n" % (count, VA_TCOUNT)
           + "LDI r5 %d\nLDI r6 %d\nST r6 r5\n" % (reload_, VA_TRELOAD)
           + "LDI r5 %d\nLDI r6 %d\nST r6 r5\n" % (KT_PACKED, VA_KTICK))
    n = len([l for l in pre.splitlines() if l.strip()])
    return ":__entry\n" + pre + spin_text(n)


STAMPS = lambda: {PT_TAG_WORD: 0x505447,
                  VPN12_PTE_WORD: PTE_PIX_PFN7,
                  VPN32_PTE_WORD: PTE_RAM_PFN32}


def main():
    out = {}

    payload_chain = (paint_stores(GADGET_G, G_WORD0) + "\n"
                     + paint_stores(GADGET_KTICK_SYSCALL, KT_WORD0) + "\n")
    payload_ret = paint_stores(GADGET_KTICK_RETURN, KT_WORD0) + "\n"
    payload_noret = paint_stores(GADGET_KTICK_NORETURN, KT_WORD0) + "\n"

    # T1: TICK-CHAIN — tick fires from the spin: SUPER payload PRTs 77,
    # re-arms ksys -> gadget (30,8), SYSCALLs; gadget PRTs 52, re-arms
    # ksys <- 0, SYSRETs. Measures the composition AND its cost to the
    # tick return path.
    out["T1_tick_chain_syscall_compose"] = run_leg(
        arm_and_spin(payload_chain, count=2, reload_=0), STAMPS())

    # T2: RESIDENT PREEMPTIVE FOOTHOLD — proper JMPR return + reload=2,
    # NO SYSCALL anywhere: attacker SUPER code re-fires on a hardware
    # period for the task's whole lifetime.
    out["T2_periodic_tick_no_guest_syscall"] = run_leg(
        arm_and_spin(payload_ret, count=2, reload_=2), STAMPS())

    # C1: ONE-SHOT control — reload=0: exactly one fire, then USER spin.
    out["C1_one_shot_reload0_single_fire"] = run_leg(
        arm_and_spin(payload_ret, count=2, reload_=0), STAMPS())

    # C2: NO-ARM control — no timer/ktick stores: the tick never fires.
    n_c2 = len((ARM_SNIPPET + payload_ret).strip().splitlines())
    text_c2 = (":__entry\n" + ARM_SNIPPET + payload_ret
               + spin_text(n_c2))
    out["C2_no_timer_arm_never_fires"] = run_leg(text_c2, STAMPS())

    # C3: NO-RETURN control — periodic arm but the payload never returns
    # (tick-14 shape): single fire, halt inside the handler.
    out["C3_periodic_no_return_single_fire"] = run_leg(
        arm_and_spin(payload_noret, count=2, reload_=2), STAMPS())

    # C4: rot-guard — unpaged out-of-tile USER ST to word 8207, no PT.
    text_c4 = (":__entry\nLDI r5 1\nLDI r6 %d\nST r6 r5\nHALT\n"
               % WORD_KTICK)
    out["C4_unpaged_out_of_tile_ktick_ST_traps"] = run_leg(text_c4, None)

    blob = json.dumps(out, sort_keys=True, indent=1)
    md5 = hashlib.md5(blob.encode()).hexdigest()
    print(blob)
    print("results_md5", md5)
    out_path = HERE / "probe_ktick_chain_af3e_results.json"
    out_path.write_text(json.dumps(
        {"results": out, "results_md5": md5}, indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
