"""BK-4 WAITPID/JOIN — parent blocks on child exit code via kernel syscall
(roadmap BK-4, promoted from GLYPH_BACKLOG by commit 212b19d).

Module shape mirrors signals.py: the kernel program text + the two-pass
bake live here; baker.py is NOT modified. All mechanics are landed
GH-16/18/22/26.4 + BK-3 patterns — zero engine changes.

JOIN IS ASYNCHRONOUS. The trap must come back before a new slice can be
scheduled, so SYS 13 on a still-running child CANNOT return first and
let the round boundary do the work — a plain deferred-SYSRET resumes the
PARENT (the engine's resume PC always points at the trapped task), the
parent KJMPs :__dispatch, which KJMPs :__sigret, whose SYSRET resumes
the parent AGAIN: an infinite parent↔kernel loop (bk4_dbg4: B never
scheduled, 60000 steps, tick 0x694). Instead, the kernel runs the child
INSIDE A's trap window (BK-3's delivery-at-registration pattern), then
re-points the resume PC:

  SYS 12 (child_exit) = SUPER slice: stores the trapped a0 (the child's
      exit code) into the kernel-owned EXIT_CODE word (741) and lights
      the child-done flag (742). SYSRET drops B back into its own tail
      (work receipt, exit marker, done flag), which KJMPs :__dispatch.

  :__dispatch (SUPER) = A's in-box done promote is shared with the
      child-reaped path, then the kernel checks WHO trapped: A (parent)
      -> run the child NOW: latch=1 + JMPR into :__task_b (USER); B's
      tail KJMPs :__bret (SUPER promote of B's done flag -> jump
      :__finish_join). B (child, joining via exit) -> straight to
      :__kdone. Then :__finish_join re-points the saved resume PC
      (SYSCALL_PC word 8201) at :__aresume and SYSRETs — restoring A's
      registers and landing A AFTER its join, join word already
      delivered. A trapped join inside the run-the-child window is the
      blocking wait; the same SYSRET machinery delivers the result.

Word map (landed ABI, all inside [700,768) box windows / kernel words):
  703 A exit, 710 A work, 716/734 in-box done flags (SUPER promotes
  into 717), 720 B work, 721 B in-box join-result word (THE gate),
  723 B exit, 732 tick count, 741 kernel-owned exit code, 742
  kernel-owned child-done flag, 759 kernel fault receipt.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import List, Optional, Union

import numpy as np

_REPO = Path(__file__).resolve().parent.parent.parent.parent
for _p in (str(_REPO), str(_REPO / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# ── BK-4 word ABI ────────────────────────────────────────────────────────
BK4_STATUS_WORD = 951
BK4_KERNEL_OK = 0xCAFE0028        # 0xCAFE << 16 | 0x28 (BK-4 tail id)
BK4_A_EXIT_OK = 0xFEED0006        # A exit = 0xFEED | slice 6
BK4_B_EXIT_OK = 0xFEED0007        # B exit = 0xFEED | slice 7
BK4_WORK_A = 710                  # A's work word (in BOX0)
BK4_WORK_B = 720                  # B's work word (in BOX1)
BK4_JOIN_WORD = 721               # B-box in-box join result (THE gate)
BK4_EXIT_A = 703
BK4_EXIT_B = 723
BK4_DONE_WORD = 717               # bit0 A, bit1 B
BK4_DONE_A = 716                  # in-box flags (SUPER promotes into 717)
BK4_DONE_B = 734
BK4_EXIT_CODE = 741               # kernel-owned child exit code (SYS 12)
BK4_CHILD_DONE = 742              # kernel-owned child-done flag
BK4_FAULT_WORD = 759
BK4_N_EXIT = 12                   # SYS 12: child exit (a0 = exit code)
BK4_N_JOIN = 13                   # SYS 13: parent join -> in-box word

# BOX geometry (landed ABI facts — baker.py GH-16/GH-18 constants)
_B0_LO, _B0_HI = 2800, 2868       # BOX0 = words [700..717)
_B1_LO, _B1_HI = 2872, 2940       # BOX1 = words [718..735)

# pass-1 PC globals (agent_resident.py two-pass pattern)
_BK4_KSYS_PC = 0
_BK4_KFAULT_PC = 0
_BK4_TICK_PC = 0
_BK4_DISPATCH_PC = 0
_BK4_TASK_A_PC = 0
_BK4_TASK_B_PC = 0
_BK4_SIGRET_PC = 0
_BK4_ARESUME_PC = 0
_BK4_BRET_PC = 0


def _pack_consts(v: int) -> List[str]:
    """Lines building full 32-bit v in r14 (LDI-safe hi/lo split).

    FIXED-SIZE (always 5 lines) — the two-pass bake depends on it.
    """
    hi, lo = (v >> 16) & 0xFFFF, v & 0xFFFF
    return [f"LDI r14 {lo}", f"LDI r13 {hi}", "LDI r4 16", "SHL r13 r4",
            "OR r14 r13"]


def _jump_r30(lines: List[str], v: int) -> None:
    """Append: r14 <- v (full 32-bit), r30 <- r14, KJMP r30 (SUPER tail)."""
    lines.extend(_pack_consts(v))
    lines.append("XOR r30 r30")
    lines.append("OR r30 r14")
    lines.append("KJMP r30")


def _bk4_program_text(status_word: int, timer_quantum: int) -> str:
    """The BK-4 join kernel. Parent A spawns B, then joins: SYS 13 defers
    while the child is alive; the kernel completes the child at the round
    boundary and delivers its exit code (42) into A's in-box join word."""
    a: List[str] = []
    add = a.append
    add(":__entry")
    add("JMP :__kmain")
    add(":__kmain")
    # ---- zero the receipt words ----
    for w in (BK4_EXIT_A, BK4_WORK_A, BK4_EXIT_B, BK4_WORK_B, BK4_JOIN_WORD,
              BK4_DONE_WORD, BK4_DONE_A, BK4_DONE_B, BK4_EXIT_CODE,
              BK4_CHILD_DONE, BK4_FAULT_WORD):
        add(f"LDI r15 {w}")
        add("LDI r14 0")
        add("ST r15 r14")
    # ---- arm BOX0 + BOX1 (bounds ARE the MMIO bound) ----
    add("LDI r15 8195"); add(f"LDI r14 {_B0_LO}"); add("ST r15 r14")
    add("LDI r15 8196"); add(f"LDI r14 {_B0_HI}"); add("ST r15 r14")
    add("LDI r15 8197"); add(f"LDI r14 {_B1_LO}"); add("ST r15 r14")
    add("LDI r15 8198"); add(f"LDI r14 {_B1_HI}"); add("ST r15 r14")
    # ---- vectors: KSYS_PC / KFAULT_PC / KTICK_PC (full-32-bit LDIs) ----
    add("LDI r15 8194")                       # KSYS_PC
    a.extend(_pack_consts(_BK4_KSYS_PC))
    add("ST r15 r14")
    add("LDI r15 8193")                       # KFAULT_PC
    a.extend(_pack_consts(_BK4_KFAULT_PC))
    add("ST r15 r14")
    add("LDI r15 8207")                       # KTICK_PC
    a.extend(_pack_consts(_BK4_TICK_PC))
    add("ST r15 r14")
    # ---- GH-16 preemptive timer ----
    add("LDI r15 8208"); add(f"LDI r14 {timer_quantum}"); add("ST r15 r14")
    add("LDI r15 8209"); add(f"LDI r14 {timer_quantum}"); add("ST r15 r14")
    # ---- enter A (USER): latch=1 then KJMP (latch one-shot arms USER) ----
    add("LDI r15 8192"); add("LDI r14 1"); add("ST r15 r14")
    _jump_r30(a, _BK4_TASK_A_PC)
    add("JMP :__kdone")
    # ---- syscall dispatcher (SUPER) ----
    add(":__ksys")
    add("LDI r15 8204")
    add("LD r5 r15")
    add(f"LDI r4 {BK4_N_EXIT}")
    add("CMP r5 r4")
    add(f"JZ :__ksys{BK4_N_EXIT}")
    add(f"LDI r4 {BK4_N_JOIN}")
    add("CMP r5 r4")
    add(f"JZ :__ksys{BK4_N_JOIN}")
    # unknown: 'E' + clean SYSRET
    add("LDI r15 761")
    add("LDI r14 69")
    add("ST r15 r14")
    add("SYSRET")
    # SYS 12 — child exit: a0 (trapped into SYS_A0) -> kernel EXIT_CODE;
    # light the child-done flag; SYSRET drops B back into its own tail
    # (which KJMPs the round boundary -> :__dispatch -> join completes).
    add(f":__ksys{BK4_N_EXIT}")
    add("LDI r15 8205")
    add("LD r6 r15")
    add(f"LDI r15 {BK4_EXIT_CODE}")
    add("ST r15 r6")
    add(f"LDI r15 {BK4_CHILD_DONE}")
    add("LDI r14 1")
    add("ST r15 r14")
    add("SYSRET")
    # SYS 13 — parent join. If the child is STILL ALIVE (CHILD_DONE==0):
    # defer — SYSRET empty; A's tail KJMPs :__dispatch, which runs the
    # child inside the trap window and completes the join at :__sigret.
    # If the child already exited: copy inline, SYSRET.
    add(f":__ksys{BK4_N_JOIN}")
    add(f"LDI r15 {BK4_CHILD_DONE}")
    add("LD r13 r15")
    add("XOR r4 r4")
    add("CMP r13 r4")
    add("JZ :__ksys13_defer")
    add(":__ksys13_copy")                     # shared inline copy
    add(f"LDI r15 {BK4_EXIT_CODE}")
    add("LD r6 r15")
    add(f"LDI r15 {BK4_JOIN_WORD}")
    add("ST r15 r6")
    add("SYSRET")
    add(":__ksys13_defer")
    add("SYSRET")
    # ---- dispatch (SUPER, re-entry from any task tail via KJMP) ----
    # promote A's in-box done flag (shared: normal A tail + reap path)
    add(":__dispatch")
    add(f"LDI r15 {BK4_DONE_A}")
    add("LD r14 r15")
    add(f"LDI r15 {BK4_DONE_WORD}")
    add("LD r13 r15")
    add("OR r13 r14")
    add("ST r15 r13")
    # WHO trapped? SYS_N == JOIN means A joined (child alive at trap):
    # run the child NOW, inside A's trap window. Otherwise (B exited)
    # the round is over — halt via the done tail.
    add("LDI r15 8204")
    add("LD r5 r15")
    add(f"LDI r4 {BK4_N_JOIN}")
    add("CMP r5 r4")
    add("JZ :__run_child")
    add("JMP :__kdone")
    # run the child: latch=1 + JMPR (USER one-shot). Zero the SYS_N word
    # FIRST so :__dispatch's re-entry from B's tail sees "not join".
    add(":__run_child")
    add("LDI r15 8204")
    add("LDI r14 0")
    add("ST r15 r14")
    add("LDI r15 8192")
    add("LDI r14 1")
    add("ST r15 r14")
    _jump_r30(a, _BK4_TASK_B_PC)
    add("JMP :__kdone")
    # ---- B's SUPER return leg: promote B's flag, complete the join ----
    add(":__bret")
    add(f"LDI r15 {BK4_DONE_B}")
    add("LD r14 r15")
    add("LDI r13 1")
    add("SHL r14 r13")
    add(f"LDI r15 {BK4_DONE_WORD}")
    add("LD r13 r15")
    add("OR r13 r14")
    add("ST r15 r13")
    # fall through: :__finish_join re-points A's resume PC and SYSRETs
    add(":__finish_join")
    # join delivery: EXIT_CODE -> A's in-box join word
    add(f"LDI r15 {BK4_EXIT_CODE}")
    add("LD r6 r15")
    add(f"LDI r15 {BK4_JOIN_WORD}")
    add("ST r15 r6")
    # re-point the saved resume PC (SYSCALL_PC, word 8201) at :__aresume
    a.extend(_pack_consts(_BK4_ARESUME_PC))
    add("LDI r15 8201")
    add("ST r15 r14")
    # clear stale marshaling words so no leg re-reads the dead join trap
    add("LDI r15 8204")
    add("LDI r14 0")
    add("ST r15 r14")
    add("LDI r15 8205")
    add("LDI r14 0")
    add("ST r15 r14")
    # land on the SIGRET trampoline: SYSRET restores A's registers and
    # resumes at :__aresume (join word already delivered)
    a.extend(_pack_consts(_BK4_SIGRET_PC))
    add("XOR r30 r30")
    add("OR r30 r14")
    add("JMPR r30")                           # SUPER: land on SYSRET
    add("JMP :__kdone")
    # ---- tick handler (GH-16 Bug-8: r25-r28 ONLY) ----
    add(":__ktick")
    add(f"LDI r25 {BK4_FAULT_WORD - 27}")     # 732 tick count
    add("LD r26 r25")
    add("LDI r27 1")
    add("ADD r26 r27")
    add("ST r25 r26")
    # the engine only ticks USER slices: arm the latch and return via
    # KJMP (the privilege boundary) so the task resumes in USER.
    add("LDI r25 8192")
    add("LDI r26 1")
    add("ST r25 r26")
    add("LDI r25 8210")                       # TICK_PC (interrupted PC)
    add("LD r28 r25")
    add("KJMP r28")
    add("JMP :__kdone")
    # ---- fault handler: receipt, then route to the round boundary ----
    add(":__kfault")
    add(f"LDI r15 {BK4_FAULT_WORD}")
    a.extend(_pack_consts(0xFA028))
    add("ST r15 r14")
    add("JMP :__dispatch")
    # ---- done tail ----
    add(":__kdone")
    add("LDI r15 8204"); add("LDI r14 0"); add("ST r15 r14")
    add("LDI r3 51966")
    add("LDI r4 16")
    add("SHL r3 r4")
    add(f"LDI r9 {BK4_KERNEL_OK & 0xFFFF}")
    add("ADD r3 r9")
    add(f"LDI r15 {status_word}")
    add("ST r15 r3")
    add("HALT")
    # ---- parent A (USER, BOX0): work, JOIN (blocks), post-join, exit ----
    add(":__task_a")
    add(f"LDI r15 {BK4_WORK_A}")
    add("LDI r14 273")
    add("ST r15 r14")
    # join while the child is alive -> the kernel runs B inside the trap
    # window and resumes A at :__aresume with B's code already in-box
    add(f"LDI r17 {BK4_N_JOIN}")
    add("LDI r10 0")
    add(f"SYSCALL r12 {BK4_N_JOIN}")
    add(":__aresume")
    # post-join receipt: A observed the delivered code (mirror for L1)
    add(f"LDI r15 {BK4_JOIN_WORD}")
    add("LD r13 r15")
    add(f"LDI r15 {BK4_EXIT_A}")              # (overwritten below; mirror)
    add("LDI r15 712")                        # A's post-join receipt word
    add("ST r15 r13")
    # A's own tail: exit marker + done flag, then the dispatch leg
    add(f"LDI r15 {BK4_EXIT_A}")
    add("LDI r14 65261")
    add("LDI r4 16")
    add("SHL r14 r4")
    add("LDI r13 6")
    add("ADD r14 r13")
    add("ST r15 r14")
    add(f"LDI r15 {BK4_DONE_A}")
    add("LDI r14 1")
    add("ST r15 r14")
    _jump_r30(a, _BK4_DISPATCH_PC)
    add("JMP :__kdone")
    # ---- child B (USER, BOX1): work 42, exit(42) via SYS 12 ----
    add(":__task_b")
    add(f"LDI r15 {BK4_WORK_B}")
    add("LDI r14 42")
    add("ST r15 r14")
    add(f"LDI r17 {BK4_N_EXIT}")
    add("LDI r10 42")
    add(f"SYSCALL r12 {BK4_N_EXIT}")
    # B's own tail: exit marker + done flag, then B's SUPER return leg
    add(f"LDI r15 {BK4_EXIT_B}")
    add("LDI r14 65261")
    add("LDI r4 16")
    add("SHL r14 r4")
    add("LDI r13 7")
    add("ADD r14 r13")
    add("ST r15 r14")
    add(f"LDI r15 {BK4_DONE_B}")
    add("LDI r14 1")
    add("ST r15 r14")
    _jump_r30(a, _BK4_BRET_PC)
    add("JMP :__kdone")
    # ---- SIGRET trampoline (SUPER): SYSRET restores A's registers/resume ----
    add(":__sigret")
    add("SYSRET")
    return "\n".join(a) + "\n"


def join_image(
    status_word: int = BK4_STATUS_WORD,
    timer_quantum: int = 12,
    cols_instrs: int = 8,
    min_rows: int = 16,
    out_path: Optional[Union[str, Path]] = None,
) -> np.ndarray:
    """Bake ONE image with the BK-4 join kernel (two-pass bake; pass 1
    fixes the packed pixel PCs, pass 2 bakes the final image)."""
    global _BK4_KSYS_PC, _BK4_KFAULT_PC, _BK4_TICK_PC
    global _BK4_DISPATCH_PC, _BK4_TASK_A_PC, _BK4_TASK_B_PC, _BK4_SIGRET_PC
    global _BK4_ARESUME_PC, _BK4_BRET_PC
    from glyph_gpt.baker import bake_image
    from rv64i_to_glyph import assemble_glyph_to_pixels

    txt1 = _bk4_program_text(status_word, timer_quantum)
    _, coords1 = assemble_glyph_to_pixels(txt1, cols_instrs=cols_instrs, min_rows=min_rows)

    def packed(label: str) -> int:
        col, row = coords1[label]
        return (col & 0xFFFF) | ((row & 0xFFFF) << 16)

    _BK4_KSYS_PC = packed(":__ksys")
    _BK4_KFAULT_PC = packed(":__kfault")
    _BK4_TICK_PC = packed(":__ktick")
    _BK4_DISPATCH_PC = packed(":__dispatch")
    _BK4_TASK_A_PC = packed(":__task_a")
    _BK4_TASK_B_PC = packed(":__task_b")
    _BK4_SIGRET_PC = packed(":__sigret")
    _BK4_ARESUME_PC = packed(":__aresume")
    _BK4_BRET_PC = packed(":__bret")
    try:
        txt2 = _bk4_program_text(status_word, timer_quantum)
        return bake_image(
            txt2,
            atlas=None,
            cols_instrs=cols_instrs,
            min_rows=min_rows,
            out_path=out_path,
        )
    finally:
        _BK4_KSYS_PC = _BK4_KFAULT_PC = _BK4_TICK_PC = 0
        _BK4_DISPATCH_PC = _BK4_TASK_A_PC = _BK4_TASK_B_PC = 0
        _BK4_SIGRET_PC = _BK4_ARESUME_PC = _BK4_BRET_PC = 0
