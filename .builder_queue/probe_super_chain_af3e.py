#!/usr/bin/env python3
"""Research tick 17 (af3e, 2026-09-28): SUPER-CHAINED DISPATCH — can a
hostile guest-painted dispatcher, running in SUPER via the :968 MMIO-window
exemption, re-arm KSYS_PC (word 8194) to ANOTHER guest gadget and re-enter
via a second SYSCALL, N dispatch levels deep — a persistent USER<->SUPER
foothold instead of a one-shot round trip?

Named NOT-proved by tick 15 (RESEARCH_ksys_paged_rewrite_af3e.md:43:
"SUPER-mode re-arm chaining ... :971-972 exempts SUPER stores to BOX_MMIO
from translation — unmeasured") and tick 13 (:133). Tick 16 sharpened the
surface: the :968 exemption serves a SUPER accessor BEFORE any PTE consult
(R2c wrong-frame PTE identical to T1) — the exemption site is the serving
branch. Unmeasured everywhere: the CHAIN.

Mechanism (tools/glyph_isa_v2.py, source-read):
- ST arm :968: pt_base!=0 and NOT(SUPER and addr in MMIO words 8192..8447)
  -> the paged walk. A SUPER store to the window falls through BOTH the
  walk and the E-K1 box arm to the plain unguarded store.
- SYSCALL arm :1166-1190: ksys = memory[8194]; if non-zero, save resume PC
  to word 8201, mode=SUPER, jump to the packed PC in ksys.
- SYSRET arm :1193-1208: restore regs, a0=memory[8205], mode=USER, resume
  at packed PC in word 8201.

Chain primitive: a dispatcher in SUPER writes KSYS_PC (8194) -> gadget2
(one plain unguarded ST, the exemption admits it), then executes SYSCALL
itself — the engine re-dispatches to gadget2 with a FRESH register-file
save (_syscall_regs overwritten :1173) and resume-PC save. gadget2 writes
KSYS_PC back -> dispatcher1 and SYSRETs (or HALTs). If this composes N
deep, a hostile task holds a RE-ENTRANT foothold: any SYSCALL re-enters
attacker SUPER code, and the kernel's own dispatch mechanism is the
attacker's call gate.

Legs (all inside the REAL contained-spawn posture, tile (256,19,1,2),
PT armed by the task's lawful in-tile ST to word 8211, tag 0x505447 at
1535, PT base 1536; ksys armed HOST-side to dispatcher1 at (24,8) — the
loader-seed posture; ALL dispatcher/gadget instruction words from the
REAL GlyphAssemblerV2, never hand-encoded; verdicts from exit_status +
fault fields + cpu.output + final PC + RAM readback BYTES, never stdout):

  T1  THE CHAIN: dispatcher1 (24,8) [PRT 77; ST 8194<-gadget2 packed PC;
      SYSCALL r10 7] -> engine dispatches gadget2 (32,8) [PRT 52; ST
      8194<-dispatcher1 packed PC (re-arm for next time); SYSRET] ->
      SYSRET resumes USER at the TRUE saved resume PC (the post-SYSCALL
      LDI r3 99 -> HALT at :post_sys). Expected if the family holds:
      output [77, 52], mode USER, final PC = post_sys HALT, ksys word
      8194 readback = dispatcher1's packed PC (the RE-ARM landed — next
      SYSCALL re-enters the chain), no fault anywhere. T3 then proves
      the re-arm is LIVE.
  T2  CONTROL, single-level (identical minus dispatcher1's re-arm ST +
      second SYSCALL — dispatcher1 PRT 77; SYSRET): output [77], resume
      at TRUE saved PC — isolates the chain's two extra steps. Also the
      probe's own tick-16-T2-shape rot-guard (E-K2 clean path green).
  T3  THE RE-ARM IS LIVE (the foothold discriminator): T1's program
      CONTINUES after :post_sys with `SYSCALL r10 8` again. Expected if
      the re-arm landed: output [77, 52, 77, 52] — the chain re-executes
      END-TO-END from a plain USER SYSCALL, because dispatcher1 re-armed
      ksys to itself before SYSRET. If ksys were zeroed/consumed at
      dispatch, the second SYSCALL would take the DIRECT fence-blind
      inline handler (output grows by nothing, r10 = imm) — the
      foothold does NOT persist. This leg is the difference between a
      one-shot hijack (tick 15/16) and a RESIDENT one (this tick).
  C1  NO-EXEMPTION control: identical to T1 but the re-arm ST targets
      word 165 (a plain RAM word OUTSIDE the MMIO window, out-of-tile)
      instead of 8194 — under the SAME armed PT with vpn-32 PTE 0, a
      SUPER store to a non-window word takes the paged walk pte_invalids
      mid-dispatch (the tick-16-C1 shape): output [77], fault
      pte_invalid vaddr 660, parked at the REAL trampoline (0,30),
      exit 1. Proves the exemption (SUPER+window), not SUPER alone,
      served the re-arm store.
  C2  ROT-GUARD: unpaged out-of-tile USER ST to word 8194, no PT — the
      E-K1 tile fence must trap (fault_addr 8194*4 = 32776, BK-66-C2
      shape, KSYS flavor). The fence is live for the word when
      translation is not armed.

3 pinned runs byte-identical, results md5 recorded. Run:
  python3 .builder_queue/probe_super_chain_af3e.py
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
WORD_KSYS = 8194                       # KSYS_PC_ADDR >> 2 (BOX_MMIO+0x08)
WORD_SYSPC = 8201                      # SYSCALL_PC_ADDR >> 2
WORD_SYSA0 = 8205                      # SYS_A0_ADDR >> 2
WORD_CTRL = 165                        # C1: plain out-of-tile RAM word, NON-window
D1_ROW, D1_COL = 28, 8                 # dispatcher1 (host-armed ksys target)
D1_PACKED = (D1_ROW << 16) | D1_COL
D1_WORD0 = D1_ROW * 64 + D1_COL * 4    # 28*64+32 = 1824
G2_ROW, G2_COL = 31, 8                 # gadget2 (re-arm target; col<=15!)
G2_PACKED = (G2_ROW << 16) | G2_COL
G2_WORD0 = G2_ROW * 64 + G2_COL * 4    # 31*64+32 = 2016
assert 1792 <= D1_WORD0 < 2048, "dispatcher1 in vpn-12 PIX pfn 7 frame"
assert 1792 <= G2_WORD0 < 2048, "gadget2 in vpn-12 PIX pfn 7 frame"
assert D1_WORD0 != G2_WORD0
assert WORD_CTRL < 8192, "C1 control word must be OUTSIDE the MMIO window"

DISPATCH1_CHAIN = [                    # at (24,8)
    "LDI r9 77", "PRT r9",
    "LDI r6 %d" % G2_PACKED,
    "LDI r7 %d" % WORD_KSYS,
    "ST r7 r6",                        # THE RE-ARM: SUPER+window -> :968 exempt
    "SYSCALL r10 7",                   # re-enter via the engine's own gate
]
DISPATCH1_CLEAN = ["LDI r9 77", "PRT r9", "SYSRET"]
GADGET2 = [                            # at (32,8)
    "LDI r2 52", "PRT r2",
    "LDI r6 %d" % D1_PACKED,
    "LDI r7 %d" % WORD_KSYS,
    "ST r7 r6",                        # re-arm BACK to dispatcher1 (foothold)
    "SYSRET",                          # resume USER at the TRUE saved PC
]
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
    assert w * h >= 2112, "image must contain the PT window + gadget rows"
    if stamps:
        stamp_image(img, stamps)
    table = GlyphProcessTable(cols_instrs=16, memory_words=16384)
    pid = table.spawn(image=img, tile=TILE, max_instructions=max_instructions)
    cpu = table.tasks[pid]["cpu"]
    task = table.tasks[pid]
    # kernel-shaped posture: host-arms KSYS_PC to dispatcher1 at (24,8).
    cpu.memory[WORD_KSYS] = D1_PACKED
    table._run_task(pid)
    # The spawn image is task["image"] — possibly wrap_with_reaper's TALL
    # COPY, not the `img` we baked. Verdicts read from task["image"].
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
        "final_pc": [int(cpu.pc[0]), int(cpu.pc[1])],
        "ksys_word_after": int(cpu.memory[WORD_KSYS]),
        "syspc_word_after": int(cpu.memory[WORD_SYSPC]),
        "sysa0_word_after": int(cpu.memory[WORD_SYSA0]),
        "ctrl_word_after": int(cpu.memory[WORD_CTRL]),
        "d1_pixels": [img_word(task_img, D1_WORD0 + k)
                      for k in range(4 * len(DISPATCH1_CHAIN))],
        "g2_pixels": [img_word(task_img, G2_WORD0 + k)
                      for k in range(4 * len(GADGET2))],
    }


def main():
    out = {}

    payload = (paint_stores(GADGET2, G2_WORD0) + "\n"
               + paint_stores(DISPATCH1_CHAIN, D1_WORD0) + "\n")
    payload_clean = (paint_stores(GADGET2, G2_WORD0) + "\n"
                     + paint_stores(DISPATCH1_CLEAN, D1_WORD0) + "\n")

    # T1: THE CHAIN — task SYSCALLs; dispatcher1 (SUPER) re-arms ksys ->
    # gadget2 and re-enters via SYSCALL; gadget2 re-arms ksys -> d1 and
    # SYSRETs; USER resumes at the TRUE saved PC.
    text_t1 = (":__entry\n" + ARM_SNIPPET + payload
               + "SYSCALL r10 6\n:post_sys\nLDI r3 99\nHALT\n"
                 "LDI r3 0\nLDI r3 0\nHALT\n")
    out["T1_super_chain_rearm_and_reenter"] = run_leg(
        text_t1,
        {PT_TAG_WORD: 0x505447,
         VPN12_PTE_WORD: PTE_PIX_PFN7,
         VPN32_PTE_WORD: PTE_RAM_PFN32})

    # T2: single-level control — clean dispatcher1 (no re-arm ST, no
    # second SYSCALL). Isolates the chain's two extra steps.
    text_t2 = (":__entry\n" + ARM_SNIPPET + payload_clean
               + "SYSCALL r10 6\n:post_sys\nLDI r3 99\nHALT\n")
    out["T2_control_single_level_dispatch"] = run_leg(
        text_t2,
        {PT_TAG_WORD: 0x505447,
         VPN12_PTE_WORD: PTE_PIX_PFN7,
         VPN32_PTE_WORD: PTE_RAM_PFN32})

    # T3: THE RE-ARM IS LIVE — same as T1 plus a SECOND plain USER
    # SYSCALL after :post_sys. Foothold persists iff output grows
    # [77, 52, 77, 52].
    text_t3 = (":__entry\n" + ARM_SNIPPET + payload
               + "SYSCALL r10 6\n:post_sys\nLDI r3 99\nSYSCALL r10 8\n"
                 "HALT\nLDI r3 0\nLDI r3 0\nHALT\n")
    out["T3_foothold_persists_second_syscall"] = run_leg(
        text_t3,
        {PT_TAG_WORD: 0x505447,
         VPN12_PTE_WORD: PTE_PIX_PFN7,
         VPN32_PTE_WORD: PTE_RAM_PFN32})

    # C1: NO-EXEMPTION control — re-arm store aimed at plain word 165
    # (non-window, out-of-tile, vpn-32 PTE 0): the SUPER store takes the
    # paged walk and pte_invalids MID-CHAIN.
    d1_c1 = DISPATCH1_CHAIN[:4] + ["LDI r7 %d" % WORD_CTRL] + \
        DISPATCH1_CHAIN[5:]
    payload_c1 = (paint_stores(GADGET2, G2_WORD0) + "\n"
                  + paint_stores(d1_c1, D1_WORD0) + "\n")
    text_c1 = (":__entry\n" + ARM_SNIPPET + payload_c1
               + "SYSCALL r10 6\n:post_sys\nLDI r3 99\nHALT\n")
    out["C1_nonwindow_super_store_takes_walk"] = run_leg(
        text_c1,
        {PT_TAG_WORD: 0x505447,
         VPN12_PTE_WORD: PTE_PIX_PFN7,
         VPN32_PTE_WORD: PTE_RAM_PFN32})

    # C2: rot-guard — unpaged out-of-tile USER ST to word 8194, no PT.
    text_c2 = (":__entry\nLDI r5 %d\nLDI r6 %d\nST r6 r5\nHALT\n"
               % (G2_PACKED, WORD_KSYS))
    out["C2_unpaged_out_of_tile_ksys_ST_traps"] = run_leg(text_c2, None)

    blob = json.dumps(out, sort_keys=True, indent=1)
    md5 = hashlib.md5(blob.encode()).hexdigest()
    print(blob)
    print("results_md5", md5)
    out_path = HERE / "probe_super_chain_af3e_results.json"
    out_path.write_text(json.dumps(
        {"results": out, "results_md5": md5}, indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
