"""BK-3 SIGNALS LITE — kernel-delivered SIG_KILL/SIG_USR1 via mailbox word;
handler registration syscall (roadmap BK-3, promoted from GLYPH_BACKLOG).

Module shape mirrors agent_resident.py / gh22_driver_abi.py: the kernel
program text + the two-pass bake live here; baker.py is NOT modified.

Design (all mechanics from live probes output/bk3_probe_*.py, 2026-09-11,
plus landed GH-16/18/22/26.4 kernel patterns — zero engine changes):

  KILL = de-registration. SIG_KILL to a box is a SUPER dispatcher slice
  that zeroes the box's bounds MMIO words (BOX1_LO/HI). A USER store from
  a box with unset bounds ALWAYS faults E-K1 (glyph_isa_v2._addr_in_box:
  "An unset range (HI == 0) never matches"), and the scheduler's dispatch
  leg checks the liveness bitmap before scheduling — a killed box is never
  entered again, so it can never even attempt the (suppressed) store.

  REGISTER = SYSCALL whose SUPER slice copies the trapped a0 (the
  handler's packed pixel PC, marshaled by the engine's E-K2 trap into
  SYS_A0) into the registrant's IN-BOX handler word (733 for BOX1 —
  SUPER stores are unrestricted; the word lives inside the box so the
  kernel's delivery JMPR reads it without crossing a boundary).

  DELIVER (SIGUSR1) = the SUPER dispatch leg arms the MODE_LATCH one-shot
  (USER for the handler's duration), reads the target's handler word, and
  JMPRs into it. The handler posts a receipt word IN ITS BOX and returns
  through the privilege boundary (KJMP to the kernel continuation),
  exactly like a task slice.

  LATCH DISCIPLINE (probe output/bk3_probe_verdict2.py): USER tasks NEVER
  store MODE_LATCH or any MMIO word (E-K1 — word 8192 is outside every
  box). Only SUPER dispatch/slice code touches the latch; task tails exit
  via KJMP, whose latch one-shot is armed by the SUPER code that launches
  them.

  TICK HANDLER (GH-16 Bug-8 discipline): r25-r28 ONLY — no task body ever
  touches those, so no register spill is needed across a preemption.

Word map (landed ABI, all inside [700,768) box windows / kernel words):
  703 A exit, 710 A work, 711 A post-kill receipt,
  716/734 in-box done flags (SUPER promotes into 717),
  720 B work, 721 B handler receipt, 723 B exit,
  732 tick count, 733 B handler PC (registration target),
  759 kernel fault receipt, 760 kill receipt, 761 unknown-syscall marker,
  767 kernel-owned liveness bitmap (bit0 = B killed).
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import List, Optional, Union

import numpy as np

_REPO = Path(__file__).resolve().parent.parent.parent.parent
for _p in (str(_REPO), str(_REPO / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, str(_p))

# ── BK-3 word ABI ────────────────────────────────────────────────────────
BK3_STATUS_WORD = 950
BK3_KERNEL_OK = 0xCAFE0027        # 0xCAFE << 16 | 0x27 (BK-3 tail id)
BK3_A_EXIT_OK = 0xFEED0006        # A exit = 0xFEED | slice 6
BK3_B_EXIT_OK = 0xFEED0007        # B exit = 0xFEED | slice 7
BK3_KILL_RECEIPT = 10             # kernel's kill slice receipt word
BK3_HANDLER_RECEIPT = 555         # B's handler posts this in its box
BK3_FAULT_SEEN = 0xFA027          # adversarial escape-leg verdict
BK3_WORK_A = 710                  # A's work word (in BOX0)
BK3_WORK_A_POST = 711             # A's post-kill receipt (0xBEEF)
BK3_WORK_B = 720                  # B's work word (in BOX1)
BK3_HANDLER_OUT = 721             # B's handler receipt (in BOX1)
BK3_EXIT_A = 703
BK3_EXIT_B = 723
BK3_DONE_WORD = 717               # bit0 A, bit1 B
BK3_DONE_A = 716                  # in-box flags (SUPER promotes into 717)
BK3_DONE_B = 734
BK3_HANDLER_B = 733               # B's registered handler PC (in BOX1)
BK3_FAULT_WORD = 759
BK3_KILL_WORD = 760               # kernel SIG_KILL receipt
BK3_BADSYS_WORD = 761
BK3_TICKS_WORD = 732
BK3_KILLED_FLAG = 767             # kernel-owned liveness bitmap (bit0 = B dead)
BK3_SIG_PENDING = 766             # kernel-owned pending-SIGUSR1 latch (SYS 11)
BK3_N_REGISTER = 9                # SYS 9: register handler (a0 = handler PC)
BK3_N_KILL = 10                   # SYS 10: SIG_KILL to BOX1
BK3_N_SEND = 11                   # SYS 11: SIGUSR1 to BOX1 (delivery leg)

# BOX geometry (landed ABI facts — baker.py GH-16/GH-18 constants)
_B0_LO, _B0_HI = 2800, 2868       # BOX0 = words [700..717)
_B1_LO, _B1_HI = 2872, 2940       # BOX1 = words [718..735)

# pass-1 PC globals (agent_resident.py two-pass pattern)
_BK3_KSYS_PC = 0
_BK3_KFAULT_PC = 0
_BK3_TICK_PC = 0
_BK3_DISPATCH_B_PC = 0
_BK3_DISPATCH_SIG_PC = 0
_BK3_DISPATCH_DONE_PC = 0
_BK3_TASK_A_PC = 0
_BK3_TASK_B_PC = 0
_BK3_BHANDLER_PC = 0
_BK3_SIGRET_PC = 0


def _pack_consts(v: int) -> List[str]:
    """Lines building full 32-bit v in r14 (LDI-safe hi/lo split).

    FIXED-SIZE (always 5 lines) — the two-pass bake depends on it: pass 1
    has all-zero PCs, pass 2 the real ones; if the line count differed
    between passes the labels would shift and every pass-1 coord would be
    stale (bk3_dbg8_verdict.py: `LDI r14 0` vs the 5-line split moved
    :__task_a and the KJMP landed mid-kernel).
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


def _bk3_program_text(kill: bool, status_word: int, timer_quantum: int,
                      escape: bool = False) -> str:
    """The BK-3 signals-lite kernel. Task A signals B mid-round-robin
    (SIG_KILL on the kill leg / SIGUSR1 on the delivery leg); B registers
    its handler via SYS 9; the kernel delivers; B works; both exit."""
    a: List[str] = []
    add = a.append
    add(":__entry")
    add("JMP :__kmain")
    add(":__kmain")
    # ---- zero the receipt words ----
    for w in (BK3_EXIT_A, BK3_WORK_A, BK3_WORK_A_POST, BK3_EXIT_B,
              BK3_WORK_B, BK3_HANDLER_OUT, BK3_HANDLER_B, BK3_DONE_WORD,
              BK3_DONE_A, BK3_DONE_B, BK3_FAULT_WORD, BK3_KILL_WORD,
              BK3_BADSYS_WORD, BK3_TICKS_WORD, BK3_KILLED_FLAG,
              BK3_SIG_PENDING):
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
    a.extend(_pack_consts(_BK3_KSYS_PC))
    add("ST r15 r14")
    add("LDI r15 8193")                       # KFAULT_PC
    a.extend(_pack_consts(_BK3_KFAULT_PC))
    add("ST r15 r14")
    add("LDI r15 8207")                       # KTICK_PC
    a.extend(_pack_consts(_BK3_TICK_PC))
    add("ST r15 r14")
    # ---- GH-16 preemptive timer ----
    add("LDI r15 8208"); add(f"LDI r14 {timer_quantum}"); add("ST r15 r14")
    add("LDI r15 8209"); add(f"LDI r14 {timer_quantum}"); add("ST r15 r14")
    # ---- enter A (USER): latch=1 then KJMP (latch one-shot arms USER) ----
    add("LDI r15 8192"); add("LDI r14 1"); add("ST r15 r14")
    _jump_r30(a, _BK3_TASK_A_PC)
    add("JMP :__kdone")
    # ---- syscall dispatcher (SUPER) ----
    add(":__ksys")
    add("LDI r15 8204")
    add("LD r5 r15")
    add(f"LDI r4 {BK3_N_REGISTER}")
    add("CMP r5 r4")
    add(f"JZ :__ksys{BK3_N_REGISTER}")
    add(f"LDI r4 {BK3_N_KILL}")
    add("CMP r5 r4")
    add(f"JZ :__ksys{BK3_N_KILL}")
    add(f"LDI r4 {BK3_N_SEND}")
    add("CMP r5 r4")
    add(f"JZ :__ksys{BK3_N_SEND}")
    # unknown: 'E' + clean SYSRET
    add(f"LDI r15 {BK3_BADSYS_WORD}")
    add("LDI r14 69")
    add("ST r15 r14")
    add("SYSRET")
    # SYS 9 — handler registration: a0 (trapped into SYS_A0) -> B's
    # in-box handler word (SUPER store; in-box word, no boundary crossed).
    # DELIVERY POINT: if a SIGUSR1 is already pending (A signaled before
    # B ever ran), the kernel delivers the handler INSTEAD of SYSRETing:
    # latch=1 + JMPR into the handler (USER). The handler's tail KJMPs
    # to :__sigret, whose SYSRET restores B's pre-trap registers and
    # resume PC — so B's work slice runs AFTER the handler (signals
    # preempt the round) with the register file intact.
    add(f":__ksys{BK3_N_REGISTER}")
    add("LDI r15 8205")
    add("LD r6 r15")
    add(f"LDI r15 {BK3_HANDLER_B}")
    add("ST r15 r6")
    add(f"LDI r15 {BK3_SIG_PENDING}")
    add("LD r13 r15")
    add("XOR r4 r4")
    add("CMP r13 r4")
    add("JZ :__ksys9_nosig")
    # pending: clear the latch, arm USER, enter the handler
    add(f"LDI r15 {BK3_SIG_PENDING}")
    add("LDI r14 0")
    add("ST r15 r14")
    add(f"LDI r15 {BK3_HANDLER_B}")
    add("LD r30 r15")
    add("LDI r15 8192")
    add("LDI r14 1")
    add("ST r15 r14")
    add("JMPR r30")
    add("SYSRET")                        # (unreachable — handler tail KJMPs)
    add(":__ksys9_nosig")
    add("SYSRET")
    # SYS 11 — SIGUSR1 send: mark pending. Delivery happens at B's
    # registration (ksys9) or, if already registered, right here.
    add(f":__ksys{BK3_N_SEND}")
    add(f"LDI r15 {BK3_SIG_PENDING}")
    add("LDI r14 1")
    add("ST r15 r14")
    # already-registered? deliver NOW instead of deferring
    add(f"LDI r15 {BK3_HANDLER_B}")
    add("LD r30 r15")
    add("XOR r4 r4")
    add("CMP r30 r4")
    add("JZ :__ksys11_defer")
    add(f"LDI r15 {BK3_SIG_PENDING}")
    add("LDI r14 0")
    add("ST r15 r14")
    add("LDI r15 8192")
    add("LDI r14 1")
    add("ST r15 r14")
    add("JMPR r30")
    add("SYSRET")                        # (unreachable — handler tail KJMPs)
    add(":__ksys11_defer")
    add("SYSRET")
    # SYS 10 — SIG_KILL to BOX1: zero its bounds + light the killed
    # bitmap + receipt. De-registration = the box can never again pass
    # the USER box check; the dispatch guard never schedules it again.
    add(f":__ksys{BK3_N_KILL}")
    add("LDI r15 8197"); add("LDI r14 0"); add("ST r15 r14")
    add("LDI r15 8198"); add("LDI r14 0"); add("ST r15 r14")
    add(f"LDI r15 {BK3_KILLED_FLAG}")
    add("LDI r14 1")
    add("ST r15 r14")
    add(f"LDI r15 {BK3_KILL_WORD}")
    add(f"LDI r14 {BK3_KILL_RECEIPT}")
    add("ST r15 r14")
    add("SYSRET")
    # ---- A's SUPER continuation: dispatch B (or the signal leg) ----
    add(":__dispatch_b")
    # kill guard: r0 = (killed == 0). Only JZ exists, so the ALIVE case
    # branches over the dead path; a SIG_KILL'd B falls through to the
    # A-promotion (B is never scheduled again) and the kernel exits.
    add(f"LDI r15 {BK3_KILLED_FLAG}")
    add("LD r13 r15")
    add("XOR r4 r4")
    add("CMP r13 r4")
    add("JZ :__alive")
    # dead path: promote A's flag, kernel done
    add(f"LDI r15 {BK3_DONE_A}")
    add("LD r14 r15")
    add(f"LDI r15 {BK3_DONE_WORD}")
    add("LD r13 r15")
    add("OR r13 r14")
    add("ST r15 r13")
    add("JMP :__kdone")
    # alive path: B never got its own slot yet — schedule it NOW (latch=1
    # arms USER for the KJMP). B registers its handler (SYS 9); because A
    # already marked SIGUSR1 pending (SYS 11 → word 766), ksys9 delivers
    # the handler immediately (signals preempt the round) and its tail
    # KJMPs :__sigret whose SYSRET drops B back into its work slice.
    add(":__alive")
    add("LDI r15 8192")
    add("LDI r14 1")
    add("ST r15 r14")
    _jump_r30(a, _BK3_TASK_B_PC)
    add("JMP :__kdone")
    add(":__adone")
    add(f"LDI r15 {BK3_DONE_A}")
    add("LD r14 r15")
    add(f"LDI r15 {BK3_DONE_WORD}")
    add("LD r13 r15")
    add("OR r13 r14")
    add("ST r15 r13")
    add("JMP :__kdone")
    # ---- SIGUSR1 deliverer (SUPER): latch USER, JMPR into B's handler ----
    add(":__dispatch_sig")
    # delivery guard: handler word 0 = nothing registered → skip straight
    # to B's completion (JMPR 0 would reboot the kernel at :__entry).
    add(f"LDI r15 {BK3_HANDLER_B}")
    add("LD r30 r15")
    add("XOR r4 r4")
    add("CMP r30 r4")
    add("JZ :__nosig")
    add("LDI r15 8192")
    add("LDI r14 1")
    add("ST r15 r14")
    add("JMPR r30")
    add("JMP :__kdone")
    add(":__nosig")
    add("JMP :__dispatch_done")
    # ---- B's SUPER continuation after its slice: promote flag, done ----
    add(":__dispatch_done")
    add(f"LDI r15 {BK3_DONE_B}")
    add("LD r14 r15")
    add("LDI r13 1")
    add("SHL r14 r13")
    add(f"LDI r15 {BK3_DONE_WORD}")
    add("LD r13 r15")
    add("OR r13 r14")
    add("ST r15 r13")
    add("JMP :__kdone")
    # ---- tick handler (GH-16 Bug-8: r25-r28 ONLY) ----
    add(":__ktick")
    add(f"LDI r25 {BK3_TICKS_WORD}")
    add("LD r26 r25")
    add("LDI r27 1")
    add("ADD r26 r27")
    add("ST r25 r26")
    # The engine only ticks USER slices, so the interrupted context is
    # always a task: arm the latch and return via KJMP (the privilege
    # boundary) so the task resumes in USER. A bare JMPR would leave the
    # task in SUPER — every box check after the tick would be void.
    add("LDI r25 8192")
    add("LDI r26 1")
    add("ST r25 r26")
    add("LDI r25 8210")                       # TICK_PC (interrupted PC)
    add("LD r28 r25")
    add("KJMP r28")
    add("JMP :__kdone")
    # ---- fault handler: receipt, then re-dispatch (reap + continue) ----
    # The faulted task's in-box done flag (716) is already set; the
    # dispatch chain promotes it and routes to the next slice. Jumping
    # straight to :__kdone here would strand the round un-promoted.
    add(":__kfault")
    add(f"LDI r15 {BK3_FAULT_WORD}")
    a.extend(_pack_consts(BK3_FAULT_SEEN))
    add("ST r15 r14")
    add("JMP :__dispatch_b")
    # ---- done tail ----
    add(":__kdone")
    # ENG-2 hygiene: clear ALL marshaling words, not just SYS_N. A future
    # BK-3 extension that traps after kdone re-entry must not read stale
    # SYSCALL_PC (8201) or SYS_A0 (8205). join.py re-points 8201 by design;
    # here there is no consumer left, so zero is the honest reset.
    add("LDI r15 8204"); add("LDI r14 0"); add("ST r15 r14")
    add("LDI r15 8205"); add("LDI r14 0"); add("ST r15 r14")
    add("LDI r15 8201"); add("LDI r14 0"); add("ST r15 r14")
    add("LDI r3 51966")
    add("LDI r4 16")
    add("SHL r3 r4")
    add(f"LDI r9 {BK3_KERNEL_OK & 0xFFFF}")
    add("ADD r3 r9")
    add(f"LDI r15 {status_word}")
    add("ST r15 r3")
    add("HALT")
    # ---- task A (USER, BOX0) ----
    add(":__task_a")
    add(f"LDI r15 {BK3_WORK_A}")
    add("LDI r14 273")
    add("ST r15 r14")
    # signal B mid-round-robin: SIG_KILL (kill leg) or SIGUSR1 (delivery)
    add(f"LDI r17 {BK3_N_KILL if kill else BK3_N_SEND}")
    add("LDI r10 0")
    add(f"SYSCALL r12 {BK3_N_KILL if kill else BK3_N_SEND}")
    # A continues UNAFFECTED: real post-signal work + exit
    add(f"LDI r15 {BK3_WORK_A_POST}")
    add("LDI r14 48879")
    add("ST r15 r14")
    add(f"LDI r15 {BK3_EXIT_A}")
    add("LDI r14 65261")
    add("LDI r4 16")
    add("SHL r14 r4")
    add("LDI r13 6")
    add("ADD r14 r13")
    add("ST r15 r14")
    add(f"LDI r15 {BK3_DONE_A}")
    add("LDI r14 1")
    add("ST r15 r14")
    # ADVERSARIAL ESCAPE LEG (L4, escape=True only): after the kill
    # landed, an out-of-box USER store must still E-K1 — proof the box
    # predicate survives a de-registered neighbor. A (USER, BOX0) stores
    # to word 5000, far outside every box. The engine suppresses the
    # store, records FAULT_ADDR/FAULT_PC, and vectors to :__kfault
    # (receipt 759). Gated: the engine's fault flag is sticky, so legs
    # L1/L2 (which assert a clean receipt) bake without this store.
    if escape:
        add("LDI r15 5000")
        add("LDI r14 99")
        add("ST r15 r14")
    _jump_r30(a, _BK3_DISPATCH_B_PC)
    add("JMP :__kdone")
    # ---- task B (USER, BOX1): registers its handler FIRST ----
    add(":__task_b")
    add(f"LDI r17 {BK3_N_REGISTER}")
    a.extend(_pack_consts(_BK3_BHANDLER_PC))
    add("XOR r10 r10")
    add("OR r10 r14")
    add(f"SYSCALL r12 {BK3_N_REGISTER}")
    # B's work slice (runs after the delivered handler — signals preempt)
    add(f"LDI r15 {BK3_WORK_B}")
    add("LDI r14 7")
    add("ST r15 r14")
    add(f"LDI r15 {BK3_EXIT_B}")
    add("LDI r14 65261")
    add("LDI r4 16")
    add("SHL r14 r4")
    add("LDI r13 7")
    add("ADD r14 r13")
    add("ST r15 r14")
    add(f"LDI r15 {BK3_DONE_B}")
    add("LDI r14 1")
    add("ST r15 r14")
    _jump_r30(a, _BK3_DISPATCH_DONE_PC)
    add("JMP :__kdone")
    # ---- B's SIGUSR1 handler (USER, in BOX1) ----
    add(":__bhandler")
    add(f"LDI r15 {BK3_HANDLER_OUT}")
    add(f"LDI r14 {BK3_HANDLER_RECEIPT}")
    add("ST r15 r14")
    _jump_r30(a, _BK3_SIGRET_PC)
    add("JMP :__kdone")
    # ---- SIGRET trampoline (SUPER): SYSRET restores B's registers/resume ----
    add(":__sigret")
    add("SYSRET")
    return "\n".join(a) + "\n"


def signals_image(
    kill: bool = True,
    status_word: int = BK3_STATUS_WORD,
    timer_quantum: int = 12,
    cols_instrs: int = 8,
    min_rows: int = 16,
    out_path: Optional[Union[str, Path]] = None,
    escape: bool = False,
) -> np.ndarray:
    """Bake ONE image with the BK-3 signals-lite kernel (two-pass bake;
    pass 1 fixes the packed pixel PCs, pass 2 bakes the final image).
    escape=True appends the L4 adversarial out-of-box store."""
    global _BK3_KSYS_PC, _BK3_KFAULT_PC, _BK3_TICK_PC
    global _BK3_DISPATCH_B_PC, _BK3_DISPATCH_SIG_PC, _BK3_DISPATCH_DONE_PC
    global _BK3_TASK_A_PC, _BK3_TASK_B_PC, _BK3_BHANDLER_PC, _BK3_SIGRET_PC
    from glyph_gpt.baker import bake_image
    from rv64i_to_glyph import assemble_glyph_to_pixels

    txt1 = _bk3_program_text(kill, status_word, timer_quantum, escape)
    _, coords1 = assemble_glyph_to_pixels(txt1, cols_instrs=cols_instrs, min_rows=min_rows)

    def packed(label: str) -> int:
        col, row = coords1[label]
        return (col & 0xFFFF) | ((row & 0xFFFF) << 16)

    _BK3_KSYS_PC = packed(":__ksys")
    _BK3_KFAULT_PC = packed(":__kfault")
    _BK3_TICK_PC = packed(":__ktick")
    _BK3_DISPATCH_B_PC = packed(":__dispatch_b")
    _BK3_DISPATCH_SIG_PC = packed(":__dispatch_sig")
    _BK3_DISPATCH_DONE_PC = packed(":__dispatch_done")
    _BK3_TASK_A_PC = packed(":__task_a")
    _BK3_TASK_B_PC = packed(":__task_b")
    _BK3_BHANDLER_PC = packed(":__bhandler")
    _BK3_SIGRET_PC = packed(":__sigret")
    try:
        txt2 = _bk3_program_text(kill, status_word, timer_quantum, escape)
        return bake_image(
            txt2,
            atlas=None,
            cols_instrs=cols_instrs,
            min_rows=min_rows,
            out_path=out_path,
        )
    finally:
        _BK3_KSYS_PC = _BK3_KFAULT_PC = _BK3_TICK_PC = 0
        _BK3_DISPATCH_B_PC = _BK3_DISPATCH_SIG_PC = _BK3_DISPATCH_DONE_PC = 0
        _BK3_TASK_A_PC = _BK3_TASK_B_PC = _BK3_BHANDLER_PC = 0
        _BK3_SIGRET_PC = 0
