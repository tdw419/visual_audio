"""GH-26.4 RESIDENT — the agent daemon as a real box citizen (Tier 3).

The agent's *program* runs as a USER task in its own box on the GH-16
preemptive timer, receives work via the mailbox (argv @750/@752), and
publishes results via the mailbox (result @754, GH-22 word semantics).
This is NOT the LLM in the box — it is the box's deterministic hands
(spec systems/GH26_AGENT_IN_THE_LOOP_SPEC.md §26.4).

Mechanism receipts baked into this implementation (all from live probes,
output/dbg_gh264_probe*.py, 2026-09-11):
  - PC seeding: module globals between assemble passes (the baker.py
    GH-16/GH-18 pattern). A string-replace relocation that matches on
    inline comments NEVER fires — the comment lives in the Python source,
    not in the assembled text — and every vector stayed 0xDEAD (the run
    died at cell 17 with KTICK_PC still 0xdead).
  - SYSCALL delivery: CORRECTED 2026-09-11 (Bug 7) — the claim below
    this line previously read that `SYSCALL 6`'s immediate carries the
    syscall number and `LDI r17 N` is unnecessary. That is WRONG for
    this kernel: glyph_isa_v2.py's SYSCALL opcode has TWO paths — an
    immediate-driven one (`syscall_num = imm`) used only when no kernel
    dispatcher is armed, and the E-K2 TRAP path (`if ksys:`, which is
    what fires here, since KSYS_PC is armed) that marshals SYS_N from
    **r17** (`self.memory[SYS_N_ADDR>>2] = self.registers[17]`),
    ignoring the immediate entirely. Removing `LDI r17 N` (as this file
    did) left SYS_N reading r17's stale value (0) on every SYSCALL,
    so the dispatcher's number comparison always missed and fell
    through to `:__ksys_unknown` — silently, since no test checked the
    UART mirror or (until Bug 6) SYSRET's a0 value. Fix: `LDI r17 N`
    before every SYSCALL, same as before, immaterial whether the
    instruction's own immediate operand is also present.
  - The dispatcher is a TRAP RETURN, not a chain: SYSRET resumes the
    task at its saved PC. A task's post-syscall `KJMP :__g18dispatch`
    re-entering the SAME task loops forever (all SYSCALLs drain before
    the first KJMP; every dispatcher leg's KJMP target was unreached).
  - Ticks land ONLY in USER code (the engine defers while SUPER), so
    the handler resumes with mode-preserving `JMPR` (KJMP is the
    privilege boundary and faults on its own latch store — GH-18
    receipt debug_gh18_tickfix). No register spill is needed: the CPU
    object carries the register file across the handler untouched.
  - E-K1 fault vectors to KFAULT_PC; a faulted task is reaped by NEVER
    being re-entered (an in-handler re-entry replays the faulting ST
    forever — 60k steps, no HALT).
  - GH-25 PT writes happen BEFORE the PAGE_TABLE_WORD arming store
    (pre-arming discipline): once pt_base is live, every later store to
    the PT region itself walks the table and lands elsewhere (GH-20
    receipt probe22). PT entries use plain LD/ST word ops.
  - argv seeding: a kernel-mode boot store to mailbox words 750/752
    (RAM, direct). The tasks run entirely in-box; no host seeds.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional, Union

import numpy as np

_REPO = Path(__file__).resolve().parent.parent.parent.parent
for _p in (str(_REPO), str(_REPO / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from tools.glyph_gpt.baker import (                    # noqa: E402
    bake_image,
    BOX0_LO_WORD, BOX1_LO_WORD, BOX2_LO_WORD,
    KTICK_PC_WORD, TIMER_COUNT_WORD, TIMER_RELOAD_WORD, TICK_PC_WORD,
    MODE_LATCH_WORD, KFAULT_PC_WORD, KSYS_PC_WORD, SYS_A0_WORD,
    SYS_N_ADDR, PAGE_TABLE_WORD, PAGE_TABLE_BASE_WORD,
    PTE_V, PTE_W, PTE_U, PTE_PIX,
    GH18_BOX0_LO_BYTE, GH18_BOX0_HI_BYTE,
    GH18_BOX1_LO_BYTE, GH18_BOX1_HI_BYTE,
    GH18_BOX2_LO_BYTE, GH18_BOX2_HI_BYTE,
    GH18_TABLE_WORD, GH18_N_A, GH18_N_B, GH9_N_INSTRS,
)
from glyph_isa_v2 import PTE_HILB                     # noqa: E402
from tools.geos_aspace import PAGE_TABLE_TAG          # noqa: E402

# ── resident-word ABI (GH-16/GH-18 legacy facts) ────────────────────────
RES_STATUS_WORD = 950
RES_KERNEL_OK = 0xCAFE0026        # 0xCAFE << 16 | 0x26 (the GH-26 tail id)
RES_ABI_WORD = 952
RES_ABI_VERSION = 0x00020026      # resident-kernel ABI (0x18 base, 26 = GH-26)
RES_EXIT_A = 703                  # BOX0's exit word (GH-16 legacy)
RES_EXIT_B = 723                  # BOX1's exit word
RES_UART_A = 710                  # BOX0's uart word (kernel slice write-back)
RES_UART_B = 720                  # BOX1's uart word
RES_DONE_WORD = 717               # agent done flags: bit0 BOX0, bit1 BOX1
#    717 is NOT inside either box (landed GH-16 fact, baker.py: BOX0 =
#    words [700,717), BOX1 = [718,735) -- 717/735 are the inter-box guard
#    gaps). A USER-mode ST to 717 is always E-K1-rejected (measured
#    2026-09-11, fault_addr 0xb34 = 717*4). Each daemon instead posts to
#    its own IN-BOX flag word below; the SUPER-mode dispatcher leg that
#    regains control after each task's KJMP promotes that flag into the
#    externally-observed combined word 717 (a SUPER store is unrestricted
#    -- no box check applies there).
RES_DONE_A = 716                  # last word inside BOX0 [700,717)
RES_DONE_B = 734                  # last word inside BOX1 [718,735)
#    Bug 4 (2026-09-11): both daemons originally wrote their result to
#    the SAME shared word 754 ("the tile-ABI window... the same word A
#    writes"). B always runs after A (round-robin), so 754 ended up
#    holding B's value, clobbering A's -- but tests/test_gh26_resident.py
#    asserts mem[754] == RESULT0 (A's value) on every full run, so this
#    was a real bug, not a documented "last writer wins" design. UNLIKE
#    RES_DONE_WORD/717, word 754 IS legally inside BOX2's armed range
#    [736,768) -- A's direct USER store there already works fine (no
#    E-K1 issue). The fix is narrower than Bug 2's: only B needs to move
#    off the shared word. B gets its own in-box result word; 754 stays
#    exclusively A's published result, matching the test contract as
#    written. (A symmetric "promote both into 754, last-completed wins"
#    design was considered and rejected: it would make 754 hold B's
#    value after a full run and fail every existing assertion that
#    checks RESULT0 there -- if a future session wants a combined/last-
#    writer semantics for 754, that needs the test file updated first,
#    not just the implementation.)
RES_RESULT_B = 733                # BOX1's OWN result word (last free word
#    inside BOX1 [718,735) besides RES_DONE_B=734); 754 stays A's alone.
RES_FAULT_WORD = 731
RES_TICKS_COUNT = 732
RES_ARGV0 = 750                   # the GH-22 argv post lands here (BOX2 window)
RES_ARGV1 = 752                   # BOX1's verb input (inside BOX1)
RES_RESULT = 754                  # the tile-ABI result word
RES_FAULT_TARGET = 800            # fault-leg violation word (outside boxes)
RES_FAULT_SEEN = 0xFA026          # verdict: faulted in the resident image
RES_FAULT_PAYLOAD = 0x0BAD        # what the suppressed store would have written
RES_VPN_PAGED = 13                # paged working memory: words 3328..3583
RES_VADDR_PAGED = RES_VPN_PAGED * 256
RES_PAGED_OFFSET = 5              # the daemon's frame word (vaddr 3328)
RES_HILB_PAYLOAD = (3 * (0x2A & 0xFF)) << 8 | (3 * (0x2A & 0xFF))  # frame
#    word 5 on the paged leg = (3p << 8) | (3p & 0xFF) with p = argv byte.
#    Bug 5 (2026-09-11): this was 0x2A112A -- payload byte (0x2A) right,
#    but NOT the GH-22 mailbox word format (cksum[31:24]=(op+payload)&0xFF
#    | op[15:8] | payload[7:0]) the tests/spec actually require: for
#    op=0x11, payload=0x2A, cksum=(0x11+0x2A)&0xFF=0x3B, so the correct
#    word is 0x3B00112A. Task A only ever unwraps the low byte
#    (`AND r1 255`), so this never affected RESULT0 -- it only ever broke
#    the test's own `mem[750] == _argv_word(ARGV0)` receipt-integrity
#    check, not the computed verb result.
RES_ARGV_SEED0 = 0x3B00112A       # kernel-seeded argv word @750 (GH-22 fmt)
RES_ARGV_SEED1 = 42               # kernel-seeded argv word @752

# ── R1.1 task-queue drain (queue mode, additive 2026-09-21) ─────────────
# The anchor workload's "one full agent task" = a QUEUE of jobs posted to
# the mailbox, not one deterministic triple. BOX0's daemon loops: while
# mailbox depth > 0, pop one job, compute triple(job), publish to the
# next result-history slot. All queue words sit inside BOX2's armed range
# [736,768) so the USER-mode stores are E-K1-legal (same argument as
# Bug 4's "754 IS legally inside BOX2" note above).
RES_QUEUE_DEPTH = 740             # mailbox depth (count of queued jobs)
RES_QUEUE_RESULT_BASE = 756       # result history: slot i -> 756+i (i=0..2)
RES_QUEUE_SLOTS = 3               # jobs the daemon drains per boot
#    740 and 756..758 are free BOX2 words: the baseline asserts only
#    750/752/754, 717, 732, 736/755 (glass-box "BOX2 window dirtied" check
#    uses 736 and 755 specifically) -- 740/756/757/758 collide with none.
RES_QUEUE_SEED = [7, 11, 13]      # kernel-seeded job payloads (byte values)
#    Kernel-boot stores seed depth=3 then the three job bytes; the host
#    posts NOTHING post-boot in queue mode -- the drain is fully in-guest.
#    Queue depth seed is stored directly (plain count word, not GH-22
#    format): the daemon's loop counter needs the count, not a mailbox
#    unwrap. Job payloads are plain bytes for the same reason.
RES_QUEUE_DONE_WORD = 759         # drain-complete receipt (0x5EED0003)
RES_QUEUE_DONE = 0x5EED0003       # "3 results published" verdict

# ── R1.1 post-boot job ARRIVAL (arrive mode, additive 2026-09-21) ────────
# The queue-drain step proved a daemon can LOOP over pre-seeded work.
# The anchor workload's remaining R1.1 gap is the OTHER half of the
# mailbox story: work that ARRIVES after boot, while the daemon is
# live. arrive mode = queue drain FIRST, then a BOUNDED wait loop: the
# daemon polls an arrival flag @742 (0 = none, 1 = post pending, the
# seat clears it by the daemon's own store after claiming the job)
# with payload @760, up to 2000 polls; on a claim it triples the
# payload in place @760 and publishes the arrival receipt 0x5EED0004
# @761. All new words inside BOX2 [736,768) so every USER-mode access
# stays E-K1-legal (same argument as queue mode).
RES_ARRIVE_FLAG = 742             # arrival flag: 0 none, 1 post pending
RES_ARRIVE_PAYLOAD = 760          # arriving job payload / result in place
RES_ARRIVE_RCPT = 761             # arrival receipt (0x5EED0004)
RES_ARRIVE_DONE = 0x5EED0004      # "post-boot arrival serviced" verdict
RES_ARRIVE_POLLS = 2000           # bounded wait: polls before giving up
RES_ARRIVE_SEED_JOB = 9           # the seat's post-boot job payload
#    759 is inside BOX2 [736,768); BK-3 uses 759 as ITS fault word only
#    in its own images (signals_image), never resident_image -- no clash.
#    Hilbert frame slot 5 on the 64x64 grid: d2xy(64, 5) = (col 0, row 3)
#    -> pfn field (row << 8) | col = 0x0300 (bake/geometry-independent).
RES_HILB_PFN_FIELD = 0x0300
RES_HILB_SLOT_WORD = 5            # payload lands in frame word 5

# ── R1.2 fleet demo (fleet/fleetnaive modes, additive 2026-09-21) ─────────
# Four agent arenas, pairwise disjoint, on the four hardware isolation
# regions _addr_in_box() actually provides (glyph_isa_v2.py: BOX0 + BOX1
# + BOX2 + the GO-2 tile rect). Isolation is ENFORCED BY THE DISPATCHER:
# in fleet mode the kernel SUPER-re-arms the box registers to exactly the
# CURRENT agent's range before every KJMP (the other boxes' HI words = 0
# => unset => never matches, per _addr_in_box). With all boxes armed
# simultaneously (the pre-fleet status quo) a USER store into a
# NEIGHBOR's arena is LEGAL — fleetnaive mode is that control image: the
# same adversarial store LANDS. The fleet/naive pair is the falsifiable
# isolation claim (R1.2 "no cross-tile fault propagation").
#   A [700,717) argv@713 result@714 done@716   (BOX0's range)
#   B [718,735) argv@727 result@728 done@734   (BOX1's range)
#   C [736,752) argv@747 result@748 done@751   (BOX2 span, first half)
#   D [752,768) argv@762 result@763 done@766   (BOX2 span, second half)
# Verbs distinct so any cross-tenant result write is visible: A triple
# (2->6), B quadruple (3->12), C quintuple (4->20), D sextuple (5->30).
# Agent C is the fault-injection tenant: its body ATTEMPTS a USER store
# of 0xDEAD into B's result word 728 (outside C's armed box in fleet
# mode => E-K1, suppressed, C reaped; inside armed BOX1 in fleetnaive =>
# lands, B's result corrupted, C completes). Honesty notes for the
# receipt: WRITE-isolation only (LD is not box-checked — the engine
# checks USER STORES only); the four agents are CO-RESIDENT
# TIME-MULTIPLEXED (one PC, one register file, dispatcher legs), not
# simultaneously parallel; the supervisor is the in-guest kernel, the
# seat remains the host.
RES_FLEET_DONE = 0x5EED0005       # fleet-completion receipt word value
RES_FLEET_RCPT = 765              # receipt word (free word in D's span)
#    done word 717 bits: A=1, B=2, C=4, D=8 (C never sets its bit when
#    the fault reaps it — fleet GREEN expects 0b1011 = 11).
RES_FLEET_ADVERSARY_TARGET = 728  # B's result word — the attempted write
RES_FLEET_ADVERSARY_PAYLOAD = 0xDEAD  # what the suppressed store would write
#    (name, argv, result, done, lo_word, hi_word, verb). lo/hi are BYTE
#    ranges times 4 at use (the box regs take bytes; resident words are
#    word indices — GH-16 layout).
RES_FLEET_BOXES = [
    ("A", 713, 714, 716, 700, 717, 3),
    ("B", 727, 728, 734, 718, 735, 4),
    ("C", 747, 748, 751, 736, 752, 5),
    ("D", 762, 763, 766, 752, 768, 6),
]
RES_FLEET_ARGV_SEEDS = {713: 2, 727: 3, 747: 4, 762: 5}
RES_FLEET_EXPECT = {714: 6, 728: 12, 748: 20, 763: 30}
RES_FLEET_FAULT_SLOT = 2          # agent C = the fault-injection tenant
#    Word-map audit (measured this session): 700..768 is the legacy box
#    span; C/D SUBDIVIDE BOX2's armed span [736,768) — no new RAM is
#    claimed. Fleet images store none of 740..742/756..761 (queue/
#    arrive words) and none of 750/752/754: word 752 falls inside D's
#    NUMERIC span but D never writes it, and the baseline coexist gate
#    never runs fleet images (same isolation-of-images argument as the
#    759 note above). GH14's word 760 belongs to other kernels' images,
#    never resident_image.
#    PAGED mode: wide canvas is NOT needed and breaks instruction row-wrap
#    (deriving cols_instrs = width // 4 = 1024 kills row wrap at x=32).
#    Native width (32 px, cols_instrs=8) with vertical padding (min_rows=100)
#    allows slot 5 (word 1285 at row 40, col 5) to land cleanly in image pixels.
_PAGED_IMG_SHAPE = (100, 32)      # frame slot 5 origin = pixel word 1285 (row 40, col 5)

# pass-1 PCs (module globals between the two assemble passes; the
# baker.py GH-16/GH-18 seeding pattern — NOT a text rewrite).
_RES_DISPATCH_PC = 0
_RES_DISPATCH1_PC = 0
_RES_KSYS_PC = 0
_RES_FAULT_PC = 0
_RES_TICK_PC = 0
_RES_TASK_A_PC = 0
_RES_TASK_B_PC = 0
# R1.2 fleet: pass-1 PCs of the four fleet agent bodies and the four
# dispatcher phase labels (phase i arms agent i then KJMPs into it).
_RES_FLEET_LEG0_PC = 0
_RES_FLEET_BODIES = {}            # phase -> packed PC of :__fleet_<phase>
_FLEET_COORDS = {}                # pass-1 label coords map (fleet only)


def resident_pack_const(v: int):
    """(reg, lines) building v (32-bit) in that reg: HI<<16 | LO, LDI-safe."""
    hi, lo = (v >> 16) & 0xFFFF, v & 0xFFFF
    if not hi:
        return "r14", [f"LDI r14 {lo}"]
    return "r14", [f"LDI r14 {lo}", f"LDI r13 {hi}", "LDI r4 16",
                   "SHL r13 r4", "OR r14 r13"]


def _agent_task_a() -> list:
    """BOX0's resident daemon: triple() verb.

    argv @750 arrives as a GH-22 mailbox word (op 0x11): the daemon
    unwraps the payload byte (AND 0xFF), triples it, writes the result
    to the BOX2 window's result word 754 (argv-in/result-out via the
    GH-9/GH-18 tile ABI), posts SYS 6 (the kernel's fixed slice mirrors
    the box payload into the box's uart — the receipt channel), lights
    its done bit, and exits through the dispatcher leg (which runs BOX1
    and then the barrier). Dirty-register discipline: XOR-zero before
    computing, LDI'd small shift amounts (SHL is rs2[4:0]; receipts
    debug_gh18_stepwind/gh23).
    """
    a: list = []
    add = a.append
    add(":__task_6")
    # r1 = argv word @750; unwrap the GH-22 payload byte
    add(f"LDI r15 {RES_ARGV0}")
    add("LD r1 r15")
    add("LDI r13 255")
    add("AND r1 r13")                 # r1 = payload byte
    # r2 = 3 * payload
    add("XOR r2 r2")
    add("ADD r2 r1")                  # r2 = p
    add("LDI r4 1")
    add("SHL r2 r4")                  # r2 = 2p
    add("ADD r2 r1")                  # r2 = 3p
    # result -> the BOX2 tile-ABI window
    add(f"LDI r15 {RES_RESULT}")
    add("ST r15 r2")
    # SYS 6: the kernel slice mirrors the box payload to the uart word.
    # Bug 7 (2026-09-11): the E-K2 trap path (glyph_isa_v2.py SYSCALL,
    # `if ksys:` branch -- the one that fires whenever a kernel dispatcher
    # is armed, which it always is here) marshals SYS_N from r17
    # (`self.memory[SYS_N_ADDR>>2] = self.registers[17]`), NOT from
    # SYSCALL's immediate operand -- the immediate is only read by the
    # OTHER branch (no kernel dispatcher installed), which never runs in
    # this kernel. A prior pass removed `LDI r17 N` believing the
    # immediate replaced it (see the module docstring above, itself now
    # corrected) -- with r17 never set, SYS_N always read as its stale
    # value (0), the dispatcher's `CMP r5 r4` against GH18_N_A/B always
    # missed, and every SYSCALL silently fell through to
    # :__ksys_unknown for the entire session, masked by the fact no test
    # checked the UART mirror or (until Bug 6) the a0 return value.
    add(f"LDI r17 {GH18_N_A}")        # a7 = syscall number (E-K2 marshals THIS, not the imm)
    add(f"LDI r10 {RES_ARGV0}")       # a0 = this box's staged buffer word
    add("LDI r11 4")
    add("SYSCALL r12 6")
    # light MY done flag -- IN-BOX word (717 itself is outside every box;
    # the dispatcher leg promotes this into the combined word 717)
    add(f"LDI r15 {RES_DONE_A}")
    add("LDI r14 1")
    add("ST r15 r14")
    # exit word
    add(f"LDI r15 {RES_EXIT_A}")
    add("LDI r14 65261")              # 0xFEED
    add("LDI r4 16")
    add("SHL r14 r4")
    add(f"LDI r13 {GH18_N_A}")
    add("ADD r14 r13")
    add("ST r15 r14")
    # privilege boundary back into the dispatcher leg (BOX1, then barrier)
    add(f"LDI r30 {_RES_DISPATCH_PC}")
    add("KJMP r30")
    return a


def _agent_task_b() -> list:
    """BOX1's resident daemon: quadruple() verb.

    argv @752 (plain word, the BOX1 window), computes 4*argv with
    in-box arithmetic, writes the result word 754 in-box, posts SYS 7
    (the kernel's fixed slice copies the box's staged word to the uart),
    lights its done bit (bit1), and exits through dispatcher leg B
    (straight to the barrier). BOX2 (the driver box) is never written
    by this agent.
    """
    a: list = []
    add = a.append
    add(":__task_7")
    add(f"LDI r15 {RES_ARGV1}")
    add("LD r1 r15")
    add("XOR r2 r2")
    add("ADD r2 r1")                  # r2 = v
    add("LDI r13 1")
    add("SHL r2 r13")                 # r2 = 2v
    add("SHL r2 r13")                 # r2 = 4v
    # result -> BOX1's OWN in-box word (Bug 4: this used to be the SAME
    # word A writes, 754 -- B always runs after A, so it clobbered A's
    # result; tests/test_gh26_resident.py asserts mem[754]==RESULT0
    # (A's value) after a FULL run, so 754 stays exclusively A's)
    add(f"LDI r15 {RES_RESULT_B}")
    add("ST r15 r2")
    # SYS 7: the kernel slice mirrors the box word to uart + SYSRET a0
    # (Bug 7: r17 = syscall number is what E-K2 actually marshals to
    # SYS_N -- see the r17 comment on task A's SYSCALL 6 site)
    add(f"LDI r17 {GH18_N_B}")
    add(f"LDI r10 {RES_ARGV1}")       # a0 = this box's staged buffer word
    add("LDI r11 4")
    add("SYSCALL r12 7")
    # light MY done flag -- IN-BOX word (717 itself is outside every box)
    add(f"LDI r15 {RES_DONE_B}")
    add("LDI r14 1")
    add("ST r15 r14")
    add(f"LDI r15 {RES_EXIT_B}")
    add("LDI r14 65261")
    add("LDI r4 16")
    add("SHL r14 r4")
    add(f"LDI r13 {GH18_N_B}")
    add("ADD r14 r13")
    add("ST r15 r14")
    add(f"LDI r30 {_RES_DISPATCH1_PC}")
    add("KJMP r30")
    return a


def _agent_task_a_paged() -> list:
    """BOX0's resident daemon, PAGED working-memory leg.

    Same verb as :__task_6 (triple), but the daemon's working set
    exceeds its box: the computed result is written to vpn 13 (word
    3328 — outside every box, outside identity-mapped pages 0..3),
    which walks the PTE_HILB mapping and lands in Hilbert frame slot
    5 IN THE IMAGE. Only then does it write the in-box result word and
    proceed down the identical done/exit/KJMP path.
    """
    a: list = []
    add = a.append
    add(":__task_6")
    add(f"LDI r15 {RES_ARGV0}")
    add("LD r1 r15")
    add("LDI r13 255")
    add("AND r1 r13")                 # r1 = payload byte
    add("XOR r2 r2")
    add("ADD r2 r1")                  # r2 = p
    add("LDI r4 1")
    add("SHL r2 r4")                  # r2 = 2p
    add("ADD r2 r1")                  # r2 = 3p
    # ── the paged working-set write: ST 3328 <- (3p << 8) | (3p & 0xFF)
    #    (24-bit pixel-safe payload; frame word 5 = 0x7E7E for p = 0x2A).
    add("XOR r4 r4")
    add("ADD r4 r2")                  # r4 = 3p
    add("LDI r13 8")
    add("SHL r4 r13")                 # r4 = 3p << 8
    add("LDI r13 255")
    add("AND r2 r13")                 # r2 = 3p & 0xFF
    add("OR r4 r2")                   # r4 = (3p << 8) | (3p & 0xFF)
    add(f"LDI r15 {RES_VADDR_PAGED + RES_PAGED_OFFSET}")
    add("ST r15 r4")                  # PTE_HILB walk -> image slot 5
    # rebuild r2 = 3p for the in-box ABI write
    add("XOR r2 r2")
    add("ADD r2 r1")
    add("LDI r4 1")
    add("SHL r2 r4")
    add("ADD r2 r1")
    add(f"LDI r15 {RES_RESULT}")
    add("ST r15 r2")
    # Bug 7: r17 = syscall number is what E-K2 actually marshals to
    # SYS_N -- see the r17 comment on task A's (non-paged) SYSCALL site
    add(f"LDI r17 {GH18_N_A}")
    add(f"LDI r10 {RES_ARGV0}")
    add("LDI r11 4")
    add("SYSCALL r12 6")
    add(f"LDI r15 {RES_DONE_A}")
    add("LDI r14 1")
    add("ST r15 r14")
    add(f"LDI r15 {RES_EXIT_A}")
    add("LDI r14 65261")
    add("LDI r4 16")
    add("SHL r14 r4")
    add(f"LDI r13 {GH18_N_A}")
    add("ADD r14 r13")
    add("ST r15 r14")
    add(f"LDI r30 {_RES_DISPATCH_PC}")
    add("KJMP r30")
    return a


def _agent_task_a_fault() -> list:
    """BOX0's resident daemon, ADVERSARIAL fault leg: an out-of-box
    USER store to word 800 (outside EVERY box). The engine suppresses
    the store and vectors to :__g18fault; the kernel reaps the agent
    (fault receipt 731 = 0xFA026) and never re-enters it (re-entry
    would replay the faulting store — probe dbg_gh264_probe5), while
    BOX1 still completes through its own leg."""
    a: list = []
    add = a.append
    add(":__task_6")
    add(f"LDI r15 {RES_FAULT_TARGET}")
    add("LDI r14 4809")               # 0x0BAD — never lands (E-K1)
    add("ST r15 r14")
    add("XOR r2 r2")
    add(f"LDI r15 {RES_RESULT}")
    add("ST r15 r2")
    # Bug 7: r17 = syscall number is what E-K2 actually marshals to
    # SYS_N -- see the r17 comment on task A's (non-paged) SYSCALL site
    add(f"LDI r17 {GH18_N_A}")
    add(f"LDI r10 {RES_ARGV0}")
    add("LDI r11 4")
    add("SYSCALL r12 6")
    add(f"LDI r15 {RES_DONE_A}")
    add("LDI r14 1")
    add("ST r15 r14")
    add(f"LDI r30 {_RES_DISPATCH_PC}")
    add("KJMP r30")
    return a


def _agent_task_a_queue() -> list:
    """BOX0's resident daemon, TASK-QUEUE drain leg (R1.1 anchor work).

    The mailbox (@750/752 argv pattern) is replaced by a JOB QUEUE:
    kernel-mode boot stores seed mailbox depth @740 = 3 and job payloads
    @756..758 (inside BOX2's armed window, so the daemon's in-box reads
    and result stores are E-K1-legal). The daemon LOOPS: while depth > 0,
    read job slot [3-depth] (i.e. slot 0 first), triple it, write the
    result back into the same slot (result history in place), decrement
    depth. When the queue drains: publish RES_QUEUE_DONE @759, post SYS 6
    (the receipt channel), light the done flag, exit through the
    dispatcher leg exactly like :__task_6.

    Why a loop is safe here when the kernel's fixed schedule was not
    loop-shaped: the loop lives ENTIRELY inside the USER task; the
    GH-16 tick preempts it register-transparently (Bug 8 fix: handler
    touches r25-r28 only) and SYS 6/7 dispatch happens once, after the
    drain -- the replay-loops-forever hazard (module docstring) only
    bites a post-syscall KJMP re-entering the SAME task, which never
    happens in this design.

    Registers: r1 = job value, r2 = tripled result, r3 = slot index,
    r4 = scratch (shift amounts / constants), r5 = depth counter,
    r6 = zero constant. r13/r14/r15 as the LDI/ST idiom requires.
    No r25-r28 (tick-isolation contract).
    """
    a: list = []
    add = a.append
    add(":__task_6")
    # r5 = depth = mem[740]; r6 = 0
    add(f"LDI r15 {RES_QUEUE_DEPTH}")
    add("LD r5 r15")
    add("XOR r6 r6")
    # slot index r3 = 3 - depth (jobs queued 0,1,2; pop from the front)
    add("LDI r4 3")
    add("SUB r4 r5")
    add("XOR r3 r3")
    add("ADD r3 r4")
    # ---- loop head ----
    add(":__qloop")
    add("CMP r5 r6")                  # r0 = (depth == 0)
    add("JZ :__qdrained")
    # r1 = mem[756 + slot]  (address = base + r3 in r15)
    add(f"LDI r15 {RES_QUEUE_RESULT_BASE}")
    add("ADD r15 r3")
    add("LD r1 r15")
    # triple it (AND 0xFF first: seeds are plain bytes)
    add("LDI r13 255")
    add("AND r1 r13")
    add("XOR r2 r2")
    add("ADD r2 r1")
    add("LDI r4 1")
    add("SHL r2 r4")
    add("ADD r2 r1")
    # publish: mem[756 + slot] = r2 (result history in place)
    add(f"LDI r15 {RES_QUEUE_RESULT_BASE}")
    add("ADD r15 r3")
    add("ST r15 r2")
    # slot += 1; depth -= 1; PUBLISH the new depth so the drain is
    # host-observable word-by-word (mem[740] 3 -> 2 -> 1 -> 0), not just
    # a register-internal countdown.
    add("LDI r4 1")
    add("ADD r3 r4")
    add("SUB r5 r4")
    add(f"LDI r15 {RES_QUEUE_DEPTH}")
    add("ST r15 r5")
    add("JMP :__qloop")
    # ---- drained: receipt + the :__task_6 exit sequence ----
    add(":__qdrained")
    add(f"LDI r15 {RES_QUEUE_DONE_WORD}")
    for line in resident_pack_const(RES_QUEUE_DONE)[1]:
        add(line)
    add("ST r15 r14")
    # SYS 6 (kernel slice mirrors the box payload to the uart; r17 = the
    # marshaled syscall number -- Bug 7, see :__task_6's comment)
    add(f"LDI r17 {GH18_N_A}")
    add(f"LDI r10 {RES_QUEUE_DONE_WORD}")
    add("LDI r11 4")
    add("SYSCALL r12 6")
    add(f"LDI r15 {RES_DONE_A}")
    add("LDI r14 1")
    add("ST r15 r14")
    add(f"LDI r15 {RES_EXIT_A}")
    add("LDI r14 65261")              # 0xFEED
    add("LDI r4 16")
    add("SHL r14 r4")
    add(f"LDI r13 {GH18_N_A}")
    add("ADD r14 r13")
    add("ST r15 r14")
    add(f"LDI r30 {_RES_DISPATCH_PC}")
    add("KJMP r30")
    return a


def _agent_task_a_arrive() -> list:
    """BOX0's resident daemon, POST-BOOT ARRIVAL leg (R1.1 anchor work).

    Phase 1 is the queue drain VERBATIM from _agent_task_a_queue
    (identical instruction sequence, same gate semantics). Phase 2 is
    the new part -- receive-while-live: a BOUNDED wait loop (2000
    polls) watching the arrival flag @742. The SUPERVISOR (host seat)
    posts WHILE the daemon is in that loop: flag @742 = 1, payload
    @760 = job byte. The daemon claims the job (stores flag = 0 back,
    its own USER-mode store -- legal because 742 is inside BOX2's
    armed window), triples the payload IN PLACE @760, and publishes
    the arrival receipt RES_ARRIVE_DONE @761. If the seat never posts,
    the loop exits with @761 still 0 -- the --no-post RED leg keys on
    exactly that (a boot-state or drain residue could never mint a
    receipt, so a nonzero @761 without a post is impossible by
    construction and the probe refuses such a run).

    Why the wait loop is safe where the module docstring's
    replay-hazard bites: the loop lives entirely inside the USER task
    (GH-16 ticks preempt it register-transparently, Bug 8: handler
    touches r25-r28 only); no SYSCALL happens inside the loop -- the
    SYS 6 receipt post happens ONCE after a claim (or never, if the
    seat stays silent), then the daemon exits through the dispatcher
    leg exactly like the drain leg. Polls are cheap memory reads, so
    2000 iterations fit comfortably in the drive() budget.

    Registers: phase 1 identical to queue mode (r1 job, r2 result,
    r3 slot, r4 scratch, r5 depth, r6 zero). Phase 2: r7 = poll
    counter, r8 = flag value, r13/r14/r15 as the LDI/ST/pack idiom
    requires. No r25-r28 (tick-isolation contract).
    """
    a: list = []
    add = a.append
    add(":__task_6")
    # ============ phase 1: the seeded queue drain (verbatim) =========
    add(f"LDI r15 {RES_QUEUE_DEPTH}")
    add("LD r5 r15")
    add("XOR r6 r6")
    add("LDI r4 3")
    add("SUB r4 r5")
    add("XOR r3 r3")
    add("ADD r3 r4")
    add(":__aloop")
    add("CMP r5 r6")
    add("JZ :__adrained")
    add(f"LDI r15 {RES_QUEUE_RESULT_BASE}")
    add("ADD r15 r3")
    add("LD r1 r15")
    add("LDI r13 255")
    add("AND r1 r13")
    add("XOR r2 r2")
    add("ADD r2 r1")
    add("LDI r4 1")
    add("SHL r2 r4")
    add("ADD r2 r1")
    add(f"LDI r15 {RES_QUEUE_RESULT_BASE}")
    add("ADD r15 r3")
    add("ST r15 r2")
    add("LDI r4 1")
    add("ADD r3 r4")
    add("SUB r5 r4")
    add(f"LDI r15 {RES_QUEUE_DEPTH}")
    add("ST r15 r5")
    add("JMP :__aloop")
    # ============ phase 2: the bounded post-boot wait loop ===========
    add(":__adrained")
    add(f"LDI r15 {RES_QUEUE_DONE_WORD}")
    for line in resident_pack_const(RES_QUEUE_DONE)[1]:
        add(line)
    add("ST r15 r14")
    add(f"LDI r7 {RES_ARRIVE_POLLS}")
    add(":__apoll")
    add("CMP r7 r6")                  # polls exhausted?
    add("JZ :__agiveup")
    add(f"LDI r15 {RES_ARRIVE_FLAG}")
    add("LD r8 r15")
    add("CMP r8 r6")                  # flag == 0 -> keep polling
    add("JZ :__anext")
    # ---- claim: flag = 0 (own USER store inside BOX2, legal) ----
    add(f"LDI r15 {RES_ARRIVE_FLAG}")
    add("ST r15 r6")
    # ---- triple the payload in place: r1 = mem[760] & 0xFF ----
    add(f"LDI r15 {RES_ARRIVE_PAYLOAD}")
    add("LD r1 r15")
    add("LDI r13 255")
    add("AND r1 r13")
    add("XOR r2 r2")
    add("ADD r2 r1")
    add("LDI r4 1")
    add("SHL r2 r4")
    add("ADD r2 r1")
    add(f"LDI r15 {RES_ARRIVE_PAYLOAD}")
    add("ST r15 r2")
    # ---- arrival receipt @761 ----
    add(f"LDI r15 {RES_ARRIVE_RCPT}")
    for line in resident_pack_const(RES_ARRIVE_DONE)[1]:
        add(line)
    add("ST r15 r14")
    add("JMP :__afinish")
    add(":__anext")
    add("LDI r4 1")
    add("SUB r7 r4")
    add("JMP :__apoll")
    add(":__agiveup")
    add("XOR r2 r2")                  # no arrival: SYS 6 mirrors 0
    # ---- finish: drain-style receipt channel + done flag + exit ----
    add(":__afinish")
    add(f"LDI r17 {GH18_N_A}")
    add(f"LDI r10 {RES_ARRIVE_RCPT}")
    add("LDI r11 4")
    add("SYSCALL r12 6")
    add(f"LDI r15 {RES_DONE_A}")
    add("LDI r14 1")
    add("ST r15 r14")
    add(f"LDI r15 {RES_EXIT_A}")
    add("LDI r14 65261")              # 0xFEED
    add("LDI r4 16")
    add("SHL r14 r4")
    add(f"LDI r13 {GH18_N_A}")
    add("ADD r14 r13")
    add("ST r15 r14")
    add(f"LDI r30 {_RES_DISPATCH_PC}")
    add("KJMP r30")
    return a


def _fleet_packed(label: str) -> int:
    """Packed pixel PC of a fleet label, from the CURRENT pass-1 coords.

    resident_image runs assemble_glyph_to_pixels in pass 1 to fix label
    coordinates; this reads the coords map pass 1 left behind (module
    global, same seeding pattern as the GH-16/GH-18 PC globals). Pass 2
    regenerates the SAME layout — mode + constants are pinned — so the
    packed values are valid in the final image.

    Pass 1 ALSO generates text (before any coords exist), so on a cold
    process this returns the (0, 0) placeholder — same seeding discipline
    as the _RES_*_PC globals (width-stable LDI operand; pass 1's value is
    never consumed, only pass 2's, which runs after coords are fixed).
    """
    col, row = _FLEET_COORDS.get(label, (0, 0))
    return (col & 0xFFFF) | ((row & 0xFFFF) << 16)


def _fleet_agent_body(
    slot: int,
    ret_pc: int,
) -> list:
    """ONE fleet agent body, parameterized by slot (R1.2 fleet work).

    slot indexes RES_FLEET_BOXES: (name, argv, result, done, lo, hi,
    verb). The body: unwrap the argv byte @argv_word, compute
    verb * argv via MUL (SE023, pinned color), store the result to the
    agent's OWN result word, then — ONLY for the fault slot — attempt
    the adversarial cross-tenant store into B's result word 728. In
    fleet mode that store is outside the agent's armed box => E-K1,
    suppressed, reaped (execution never reaches the done flag); in
    fleetnaive mode it lands (agent completes, B's result corrupted).
    Non-fault agents exit through the drain-style SYS 6 / done-flag /
    KJMP channel.

    The fault slot's adversarial store happens BEFORE its own result
    store and SYS — mirroring _agent_task_a_fault's discipline (the
    faulting store is the agent's second act; the kernel reaps and
    never re-enters).

    Registers: r1 argv, r2 result, r13/r14/r15 as the LDI/ST idiom
    requires, r4 scratch. No r25-r28 (tick-isolation contract, Bug 8).
    `ret_pc` is the packed PC this agent's exit KJMP returns to (the
    dispatcher's :__fret<slot> promote block; the last agent's return
    label falls through to :__fleetfin).
    """
    _, argv_w, result_w, done_w, _lo, _hi, verb = RES_FLEET_BOXES[slot]
    a: list = []
    add = a.append
    add(f":__fleet_{slot}")
    # r1 = argv byte (plain seed word, no GH-22 unwrap needed — but AND
    # 255 anyway so a byte-typed seed can never overflow the verb)
    add(f"LDI r15 {argv_w}")
    add("LD r1 r15")
    add("LDI r13 255")
    add("AND r1 r13")
    # r2 = verb * argv
    add(f"LDI r13 {verb}")
    add("MUL r1 r13")
    add("XOR r2 r2")
    add("ADD r2 r1")
    # publish MY result to MY arena word — BEFORE the adversarial store,
    # so fleet mode can show C's own result intact (748 == 20) while C's
    # done bit stays 0 (the fault reaps C mid-body, after the result).
    add(f"LDI r15 {result_w}")
    add("ST r15 r2")
    if slot == RES_FLEET_FAULT_SLOT:
        # THE ADVERSARIAL STORE (the R1.2 fault-injection leg): a USER
        # store into B's result word — a NEIGHBOR's arena. In fleet
        # mode the dispatcher armed only THIS agent's box, so the
        # engine suppresses the store and vectors :__g18fault; the
        # agent is reaped (never completes, bit stays 0, B intact).
        # In fleetnaive mode all boxes are armed, the store is legal,
        # it LANDS: B's result becomes 0xDEAD and this agent lights
        # its done bit — the corruption made visible.
        add(f"LDI r15 {RES_FLEET_ADVERSARY_TARGET}")
        for line in resident_pack_const(RES_FLEET_ADVERSARY_PAYLOAD)[1]:
            add(line)
        add("ST r15 r14")
    # SYS 6 receipt channel + in-box done flag + exit (drain-style)
    add(f"LDI r17 {GH18_N_A}")
    add(f"LDI r10 {result_w}")
    add("LDI r11 4")
    add("SYSCALL r12 6")
    add(f"LDI r15 {done_w}")
    add("LDI r14 1")
    add("ST r15 r14")
    add(f"LDI r30 {ret_pc}")
    add("KJMP r30")
    return a


def _fleet_arm_box(lo_word: int, hi_word: int, which: int) -> list:
    """SUPER-mode box re-arming instructions for `_fleet_dispatch`.

    which selects the box register pair: 0 = BOX0, 1 = BOX1,
    2 = BOX2 (glyph_isa_v2 box regs live in MMIO words 8195/8196,
    8197/8198, 8202/8203; byte = word * 4). Arming pair `which` to
    [lo,hi) does NOT unarm the other pairs — the caller zeroes every
    HI word first (dispatch leg does an arm-all-others-zero pass).
    """
    lo_addr, hi_addr = ((8195, 8196), (8197, 8198), (8202, 8203))[which]
    a: list = []
    a.append(f"LDI r15 {lo_addr}")
    a.append(f"LDI r14 {lo_word * 4}")
    a.append("ST r15 r14")
    a.append(f"LDI r15 {hi_addr}")
    a.append(f"LDI r14 {hi_word * 4}")
    a.append("ST r15 r14")
    return a


def _fleet_dispatch_leg(naive: bool) -> list:
    """The R1.2 dispatcher, as an inline phase chain (R1.2 fleet work).

    Layout (all labels resolved by the two-pass bake in resident_image):

        :__fleg0     ; phase i: (fleet) disarm-all + arm agent i's range
        ...arming... ;           latch USER, KJMP into agent i's body
        :__fleg1     ; phase i+1 label — ALSO where agent i's exit KJMP
        ...          ;           lands? No: agent i's exit KJMP targets
                     ;           :__fret<i> (below), which promotes bit i
                     ;           and falls through into :__fleg<i+1>.
        ...
        :__fleetfin  ; all four ran: fleet receipt, JMP :__g18done
        :__fret0 .. :__fret3  ; promote blocks (routed to via bodies)

    The bodies' exit KJMPs and the fault handler's reaping JMP are
    wired by resident_image's pass-1 PC packing (same discipline as
    the GH-16/GH-18 vectors).

    fleet (naive=False): each phase SUPER-stores 0 to ALL box HI words,
    then arms exactly the upcoming agent's range (byte = word * 4).
    fleetnaive (naive=True): no re-arming — the boot-time arm-all
    (emitted in __kmain) stays live, which is the pre-fleet status quo
    the control leg exists to expose.
    """
    a: list = []
    add = a.append
    for phase in range(len(RES_FLEET_BOXES)):
        _name, _argv_w, _result_w, done_w, lo, hi, _verb = \
            RES_FLEET_BOXES[phase]
        add(f":__fleg{phase}")
        if not naive:
            # disarm all three box ranges (HI = 0 -> unset -> never
            # matches; measured _addr_in_box semantics), then arm ONLY
            # this agent's. Box regs are plain RAM words 8195..8203 —
            # SUPER stores are direct, no box check applies.
            add("LDI r15 8196")           # BOX0_HI
            add("XOR r14 r14")
            add("ST r15 r14")
            add("LDI r15 8198")           # BOX1_HI
            add("ST r15 r14")
            add("LDI r15 8203")           # BOX2_HI
            add("ST r15 r14")
            which = 0 if lo < 717 else (1 if lo < 735 else 2)
            for line in _fleet_arm_box(lo, hi, which):
                add(line)
        # latch USER mode and enter the agent (KJMP is the one-shot
        # latch consumer — glyph_isa_v2 KJMP branch). The KJMP target
        # is emitted as a marker line "__FLEET_ENTER_<phase>" (no
        # leading colon => it would be assembled as an instruction and
        # fail loudly if the pass-1 substitution below ever missed).
        add(f"LDI r15 {MODE_LATCH_WORD}")
        add("LDI r14 1")
        add("ST r15 r14")
        add(f"__FLEET_ENTER_{phase}")
        add("KJMP r30")
        # ---- the promote block the agent's exit KJMP returns to ----
        add(f":__fret{phase}")
        add(f"LDI r15 {RES_DONE_WORD}")
        add("LD r13 r15")
        add(f"LDI r15 {done_w}")
        add("LD r14 r15")
        add(f"LDI r4 {phase}")
        add("SHL r14 r4")                 # bit `phase` (SHL is rs2[4:0])
        add(f"LDI r15 {RES_DONE_WORD}")
        add("OR r13 r14")
        add("ST r15 r13")
    # ---- all four agents ran (faulted C reaped, skipped by the fault
    # handler's reaping JMP to :__fleg3): fleet receipt + done tail ----
    add(":__fleetfin")
    add(f"LDI r15 {RES_FLEET_RCPT}")
    for line in resident_pack_const(RES_FLEET_DONE)[1]:
        add(line)
    add("ST r15 r14")
    add("JMP :__g18done")
    return a


def _resident_kernel_program_text(
    mode: str = "resident",
    status_word: int = RES_STATUS_WORD,
    timer_quantum: int = 12,
) -> str:
    """The resident kernel: GH-16 preemptive scheduler + GH-18 ABI
    dispatcher (fixed slices 6/7 + tile-ABI window) + two resident
    agent daemons + the done-flag barrier. PC labels are the module
    globals seeded between assemble passes by resident_image()."""
    a: list = []
    add = a.append

    def const_lines(v: int) -> list:
        return resident_pack_const(v)[1]

    add(":__entry")
    add("JMP :__kmain")
    add(":__kmain")
    # ---- zero the receipt words ----
    for w in (RES_EXIT_A, RES_UART_A, 711, RES_EXIT_B, RES_UART_B,
              RES_DONE_WORD, RES_DONE_A, RES_DONE_B, RES_RESULT, RES_RESULT_B,
              RES_FAULT_WORD, RES_TICKS_COUNT, RES_ARGV0, RES_ARGV1,
              RES_QUEUE_DEPTH, RES_QUEUE_DONE_WORD,
              RES_QUEUE_RESULT_BASE, RES_QUEUE_RESULT_BASE + 1,
              RES_QUEUE_RESULT_BASE + 2):
        add(f"LDI r15 {w}")
        add("LDI r14 0")
        add("ST r15 r14")
    if mode == "arrive":
        # arrive-mode-only words (kept out of the shared zero list so
        # every pre-existing mode image stays byte-for-byte identical)
        for w in (RES_ARRIVE_FLAG, RES_ARRIVE_PAYLOAD, RES_ARRIVE_RCPT):
            add(f"LDI r15 {w}")
            add("LDI r14 0")
            add("ST r15 r14")
    if mode in ("queue", "arrive"):
        # ---- seed the JOB QUEUE (kernel-mode boot stores, RAM direct):
        # depth = 3, job bytes @756..758. The daemon drains them in-guest;
        # the host posts nothing post-boot. ----
        add(f"LDI r15 {RES_QUEUE_DEPTH}")
        add(f"LDI r14 {RES_QUEUE_SLOTS}")
        add("ST r15 r14")
        for i, job in enumerate(RES_QUEUE_SEED):
            add(f"LDI r15 {RES_QUEUE_RESULT_BASE + i}")
            add(f"LDI r14 {job}")
            add("ST r15 r14")
    if mode in ("fleet", "fleetnaive"):
        # ---- fleet: zero the fleet-private receipt words (additive
        # list keeps every pre-existing mode image byte-identical) and
        # seed the four argv words. NOTE: kmain's UNCONDITIONAL boot
        # arming above (BOX0 [700,717) / BOX1 [718,735) / BOX2
        # [736,768)) is the arm-all state BOTH fleet modes boot with:
        # fleetnaive keeps it (the control leg's whole point), fleet's
        # per-leg dispatcher DISARMS and re-arms to one agent at a time. ----
        for w in (RES_FLEET_RCPT, 714, 728, 748, 763):
            add(f"LDI r15 {w}")
            add("LDI r14 0")
            add("ST r15 r14")
        for w, v in RES_FLEET_ARGV_SEEDS.items():
            add(f"LDI r15 {w}")
            add(f"LDI r14 {v}")
            add("ST r15 r14")
        if mode == "fleetnaive":
            for lo, hi in ((700, 717), (718, 735), (736, 768)):
                for line in _fleet_arm_box(lo, hi, 0 if lo == 700 else
                                           (1 if lo == 718 else 2)):
                    add(line)
    # ---- seed the argv mailbox words (kernel-mode boot stores, RAM) ----
    # The session's GH-22 argv post arrives BEFORE the daemon ever runs:
    # word 750 is the full mailbox word (op 0x11, payload 0x2A), word 752
    # BOX1's plain verb input. RAM 750/752 sit inside the BOX2 window —
    # kernel stores are direct, no box check applies.
    for line in const_lines(RES_ARGV_SEED0):
        add(line)
    add(f"LDI r15 {RES_ARGV0}")
    add("ST r15 r14")
    add(f"LDI r15 {RES_ARGV1}")
    add(f"LDI r14 {RES_ARGV_SEED1}")
    add("ST r15 r14")
    # ---- ABI version word (0x00020026) ----
    for line in const_lines(RES_ABI_VERSION):
        add(line)
    add(f"LDI r15 {RES_ABI_WORD}")
    add("ST r15 r14")
    # ---- program BOX0/BOX1 (the agent arenas) ----
    add(f"LDI r15 {BOX0_LO_WORD}")
    add(f"LDI r14 {GH18_BOX0_LO_BYTE}")
    add("ST r15 r14")
    add(f"LDI r15 {BOX0_LO_WORD + 1}")
    add(f"LDI r14 {GH18_BOX0_HI_BYTE}")
    add("ST r15 r14")
    add(f"LDI r15 {BOX1_LO_WORD}")
    add(f"LDI r14 {GH18_BOX1_LO_BYTE}")
    add("ST r15 r14")
    add(f"LDI r15 {BOX1_LO_WORD + 1}")
    add(f"LDI r14 {GH18_BOX1_HI_BYTE}")
    add("ST r15 r14")
    # ---- arm BOX2 = the tile-ABI window [736..768): the argv word 750,
    # BOX1's argv word 752 and the result word 754 live here/adjacent ----
    add(f"LDI r15 {BOX2_LO_WORD}")
    add(f"LDI r14 {GH18_BOX2_LO_BYTE}")
    add("ST r15 r14")
    add(f"LDI r15 {BOX2_LO_WORD + 1}")
    add(f"LDI r14 {GH18_BOX2_HI_BYTE}")
    add("ST r15 r14")
    # ---- arm the vectors ----
    add(f"LDI r15 {KSYS_PC_WORD}")
    add(f"LDI r14 {_RES_KSYS_PC}")
    add("ST r15 r14")
    add(f"LDI r15 {KFAULT_PC_WORD}")
    add(f"LDI r14 {_RES_FAULT_PC}")
    add("ST r15 r14")
    # ---- arm the GH-16 preemptive timer ----
    add(f"LDI r15 {KTICK_PC_WORD}")
    add(f"LDI r14 {_RES_TICK_PC}")
    add("ST r15 r14")
    add(f"LDI r15 {TIMER_COUNT_WORD}")
    add(f"LDI r14 {timer_quantum}")
    add("ST r15 r14")
    add(f"LDI r15 {TIMER_RELOAD_WORD}")
    add(f"LDI r14 {timer_quantum}")
    add("ST r15 r14")
    if mode == "paged":
        # ---- GH-25 PTE_HILB: identity-map vpn 0..3, PT window (vpn 6),
        # then vpn 13 -> Hilbert frame slot 5 (V|W|U|HILB). Every PT
        # write happens BEFORE the arming store (pre-arming discipline,
        # GH-23 receipt dbg_gh23_brk2); plain LD/ST word ops.
        for p in range(4):
            add(f"LDI r15 {PAGE_TABLE_BASE_WORD + p}")
            add(f"LDI r14 {(p << 8) | PTE_V | PTE_W | PTE_U}")
            add("ST r15 r14")
        add(f"LDI r15 {PAGE_TABLE_BASE_WORD + 6}")
        add(f"LDI r14 {(6 << 8) | PTE_V | PTE_W}")
        add("ST r15 r14")
        # vpn 13: pfn field = packed 2D frame origin of slot 5 on the
        # 64x64 Hilbert frame grid; PTE = 0x0102 << 8 | V|W|U|HILB.
        add(f"LDI r15 {PAGE_TABLE_BASE_WORD + RES_VPN_PAGED}")
        add(f"LDI r14 {(RES_HILB_PFN_FIELD << 8) | PTE_V | PTE_W | PTE_U | PTE_HILB}")
        add("ST r15 r14")
        # ---- container tag at PAGE_TABLE_BASE_WORD - 1 (DEFECT-23-ROOT
        # Option 1): the engine's check_pt_tag refuses an armed page table
        # whose window lacks the tag; same discipline as gh25_hilbert_paging.
        add(f"LDI r15 {PAGE_TABLE_BASE_WORD - 1}")
        add(f"LDI r14 {PAGE_TABLE_TAG}")
        add("ST r15 r14")
        add(f"LDI r15 {PAGE_TABLE_WORD}")
        add(f"LDI r14 {PAGE_TABLE_BASE_WORD}")
        add("ST r15 r14")
    # ---- enter agent A (BOX0) in USER mode ----
    if mode in ("fleet", "fleetnaive"):
        # fleet entry: boot ends by entering the fleet dispatcher's
        # FIRST phase label in SUPER mode — NO latch here. The per-leg
        # disarm/arm stores (MMIO 8195..8203) sit outside every box and
        # would E-K1 instantly if they ran in USER mode (measured:
        # fault_addr 0x8010 = BOX0_HI, infinite fault loop). Each phase
        # leg latches USER itself immediately before its KJMP into the
        # agent body; KJMP returns to SUPER on the way out.
        add(f"LDI r30 {_RES_FLEET_LEG0_PC}")
        add("KJMP r30")
        add("JMP :__g18done")
    else:
        # ---- enter agent A (BOX0) in USER mode ----
        add(f"LDI r15 {MODE_LATCH_WORD}")
        add("LDI r14 1")
        add("ST r15 r14")
        add(f"LDI r30 {_RES_TASK_A_PC}")
        add("KJMP r30")
        add("JMP :__g18done")
    # ---- syscall dispatcher (GH-18 ABI: fixed slices 6/7 only) ----
    add(":__ksys")
    add(f"LDI r15 {SYS_N_ADDR >> 2}")
    add("LD r5 r15")
    add(f"LDI r4 {GH18_N_A}")
    add("XOR r13 r13")
    add("CMP r5 r4")
    add(f"JZ :__ksys_{GH18_N_A}")
    add(f"LDI r4 {GH18_N_B}")
    add("CMP r5 r4")
    add(f"JZ :__ksys_{GH18_N_B}")
    # -- unknown syscall: 'E', clean SYSRET --
    add(f"LDI r15 {730}")
    add("LDI r14 69")
    add("ST r15 r14")
    add(f"LDI r15 {SYS_A0_WORD}")
    add("LDI r14 0")
    add("ST r15 r14")
    add("SYSRET")
    for line in _gh18_ksys_slice_local(GH18_N_A):
        add(line)
    for line in _gh18_ksys_slice_local(GH18_N_B):
        add(line)
    # ---- dispatcher leg A: re-enter the BOX1 daemon, then barrier ----
    # (leg A is where agent A's KJMP lands: SYSRET already resumed A
    # past its syscall, so leg A runs B — a KJMP back into A would
    # replay A's post-syscall tail forever; probe dbg_gh264_probe4.)
    add(":__g18dispatch")
    # SUPER-mode promote: A's in-box done flag (716) -> bit0 of the
    # externally-observed combined word 717 (a SUPER store is
    # unrestricted; the box check only fires for USER-mode stores).
    add(f"LDI r15 {RES_DONE_A}")
    add("LD r14 r15")
    add(f"LDI r15 {RES_DONE_WORD}")
    add("LD r13 r15")
    add("OR r13 r14")
    add("ST r15 r13")
    add(f"LDI r15 {MODE_LATCH_WORD}")
    add("LDI r14 1")
    add("ST r15 r14")
    add(f"LDI r30 {_RES_TASK_B_PC}")
    add("KJMP r30")
    add("JMP :__g18done")
    # ---- dispatcher leg B: promote B's flag, then straight to the
    # barrier (A already promoted its own flag above -- both agents done)
    add(":__g18dispatch1")
    add(f"LDI r15 {RES_DONE_B}")
    add("LD r14 r15")
    add("LDI r13 1")
    add("SHL r14 r13")                # r14 = bit1 value (0 or 2)
    add(f"LDI r15 {RES_DONE_WORD}")
    add("LD r13 r15")
    add("OR r13 r14")
    add("ST r15 r13")
    add("JMP :__g18done")
    # ---- tick handler (GH-16 pattern: mode-preserving JMPR resume) ----
    # Bug 8 (2026-09-11): the handler previously used r13/r14/r15/r30 --
    # the SAME registers task bodies hold live across multi-instruction
    # sequences (e.g. task B: `LDI r15 752` then `LD r1 r15` -- if a
    # tick lands between those two, the interrupted task resumes with
    # r15 clobbered to TICK_PC_WORD's address, and `LD r1 r15` loads the
    # wrong word). "The CPU object carries the register file" (the old
    # comment here) is true but irrelevant -- carrying it across the
    # trap doesn't help when the HANDLER ITSELF overwrites live task
    # registers before resuming into the middle of the task's own
    # sequence. Confirmed empirically: quantum=12 (tick lands mid-task)
    # corrupts BOX1's result; quantum=1000000 (no mid-task tick) doesn't;
    # single-stepped the exact corrupting instruction (`LD r1 r15` after
    # r15 was left at TICK_PC_WORD=8210 by this handler).
    #
    # Fix: use ONLY registers no task body ever touches (r25-r28,
    # confirmed zero occurrences elsewhere in this file) so the
    # interrupted task's register file needs no save/restore at all --
    # it's simply never written by the handler in the first place. This
    # is a GH-16 preemption-contract fix, not GH-26.4-specific; any
    # future daemon that (like task A) also holds r13 live across
    # instructions was equally exposed.
    add(":__g18tick")
    add(f"LDI r25 {RES_TICKS_COUNT}")
    add("LD r26 r25")
    add("LDI r27 1")
    add("ADD r26 r27")
    add("ST r25 r26")
    add(f"LDI r25 {TICK_PC_WORD}")
    add("LD r28 r25")
    add("JMPR r28")
    add("JMP :__g18done")
    # ---- fault handler: receipt + reap ----
    add(":__g18fault")
    add(f"LDI r15 {RES_FAULT_WORD}")
    for line in const_lines(RES_FAULT_SEEN):
        add(line)
    add("ST r15 r14")
    if mode in ("fleet", "fleetnaive"):
        # fleet reaping: the faulted agent is never re-entered (its
        # done bit stays 0), but the FLEET CONTINUES — jump to the next
        # dispatch phase label. The label is fixed at bake time: the
        # fault slot is always phase 2 (agent C), so the next phase is
        # the phase-3 label (:__fleg3). Re-entry of C never happens —
        # a re-entry would replay the faulting store forever (the
        # _agent_task_a_fault reap discipline, probe dbg_gh264_probe5).
        add(f"JMP :__fleg{RES_FLEET_FAULT_SLOT + 1}")
    # the faulted agent is reaped (never re-entered -- its own done flag
    # stays unset), but the NEIGHBOR must still run: route to the SAME
    # dispatch leg a normal completion would have used. Promoting A's
    # (unset) in-box flag is harmless -- bit0 of 717 stays 0, matching
    # "the faulted agent never completed" -- and B still gets launched
    # and completes normally (test requires mem[717] & 2 after a fault).
    add("JMP :__g18dispatch")
    # ---- done tail: status = 0xCAFE0026, halt ----
    add(":__g18done")
    add(f"LDI r15 {SYS_N_ADDR >> 2}")
    add("LDI r14 0")
    add("ST r15 r14")
    add(f"LDI r15 {SYS_A0_WORD}")
    add("LDI r14 0")
    add("ST r15 r14")
    add("LDI r3 51966")
    add("LDI r4 16")
    add("SHL r3 r4")
    add("LDI r9 38")                  # 0x26
    add("ADD r3 r9")
    add(f"LDI r15 {status_word}")
    add("ST r15 r3")
    add("HALT")
    # ---- the resident daemons ----
    if mode in ("fleet", "fleetnaive"):
        # four fleet agent bodies + the inline dispatcher phase chain.
        # The dispatcher's entry markers (__FLEET_ENTER_<phase>) are
        # relinked by resident_image AFTER pass 1 packs the body PCs;
        # the exit-KJMP and fault-handler routing bake in directly (the
        # :__fret<i> labels are ordinary pass-2 label refs).
        naive = mode == "fleetnaive"
        for line in _fleet_dispatch_leg(naive):
            add(line)
        for slot in range(len(RES_FLEET_BOXES)):
            # EVERY agent's exit (including the last) lands on its own
            # :__fret<slot> promote block, which sets that agent's done
            # bit and falls through: fret3 falls into :__fleetfin, which
            # is exactly where the receipt block sits (end of
            # _fleet_dispatch_leg). Sending slot 3's exit straight to
            # :__fleetfin (the original wiring) SKIPPED D's promote, so
            # bit3 of 717 never lit (measured: done=0b0011, not 0b1011).
            ret_label = f":__fret{slot}"
            for line in _fleet_agent_body(slot, _fleet_packed(ret_label)):
                add(line)
    elif mode == "paged":
        for line in _agent_task_a_paged():
            add(line)
    elif mode == "fault":
        for line in _agent_task_a_fault():
            add(line)
    elif mode == "queue":
        for line in _agent_task_a_queue():
            add(line)
    elif mode == "arrive":
        for line in _agent_task_a_arrive():
            add(line)
    else:
        for line in _agent_task_a():
            add(line)
    for line in _agent_task_b():
        add(line)
    # ---- the tile rect (GH-18 ingest target; HALTs until admitted) ----
    add(":__g18tile")
    for _ in range(GH9_N_INSTRS):
        add("HALT")
    return "\n".join(a) + "\n"


def _gh18_ksys_slice_local(n: int) -> list:
    """The GH-18 SUPER-mode fixed slices (mirror of baker's
    _gh18_ksys_slice, but diverges from it deliberately): read the task's
    staged buffer word (SYS_A0), copy its payload into the task's uart,
    return the daemon's COMPUTED VERB RESULT (r2) for SYSRET -- not the
    generic byte-count-4 the shared baker.py slice returns.

    Bug 6 (2026-09-11, Jericho's call): tests/test_gh26_resident.py
    asserts registers_full[10] (a0, post-SYSRET) == the verb result
    (3x/4x), not a byte count. The register file is NOT cleared or
    swapped across the SYSCALL trap (glyph_isa_v2.py: `_syscall_regs =
    self.registers[:]` is a SAVE for later restore, not a reset) -- r2
    still holds the daemon's just-computed result (3p/4v) at the exact
    moment this SUPER-mode slice runs, since nothing between the task's
    "r2 = result" arithmetic and its SYSCALL touches r2. So `ST r15 r2`
    here is safe and needs no extra marshaling. This intentionally
    changes the "SYS 6/7 returns 4" convention baker.py's shared slice
    documents -- this copy is LOCAL to agent_resident.py (confirmed no
    other file imports it), so the change has zero blast radius outside
    this ticket.
    """
    a: list = []
    add = a.append
    add(f":__ksys_{n}")
    add(f"LDI r15 {SYS_A0_WORD}")
    add("LD r6 r15")                  # r6 = a0 = the task's buffer WORD index
    add("LD r7 r6")                   # r7 = the staged payload
    add(f"LDI r15 {RES_UART_A if n == GH18_N_A else RES_UART_B}")
    add("ST r15 r7")                  # the task's uart/read-out
    add(f"LDI r15 {SYS_A0_WORD}")
    add("ST r15 r2")                  # result -> SYS_A0 for SYSRET (verb result, not a byte count)
    add("SYSRET")
    return a


def resident_image(
    atlas,
    mode: str = "resident",
    status_word: int = RES_STATUS_WORD,
    timer_quantum: int = 12,
    cols_instrs: int = 8,
    min_rows: int = 16,
    out_path: Optional[Union[str, Path]] = None,
    img_shape: Optional[tuple] = None,
) -> np.ndarray:
    """Bake ONE image with the resident agent-daemon kernel.

    Two passes: pass 1 fixes the packed pixel PCs (module globals),
    pass 2 bakes the final image (the baker.py GH-16/GH-18 discipline).
    mode = 'resident' (the coexist gate image), 'fault' (the
    adversarial out-of-box leg), 'paged' (the GH-25 PTE_HILB
    working-memory leg; forces the wide geometry so Hilbert frame
    slot 5's frame origin (pixel word 1285) clears the program text).
    'queue' (R1.1 anchor work, 2026-09-21): BOX0's daemon drains a
    kernel-seeded job queue in-guest (loop with per-slot result
    history) instead of one deterministic triple.
    'fleet'/'fleetnaive' (R1.2, 2026-09-21): four co-resident isolated
    agents under per-leg box arming (fleet) or boot-time arm-all
    (fleetnaive, the control image the isolation claim is falsified
    against).
    """
    global _RES_DISPATCH_PC, _RES_DISPATCH1_PC, _RES_KSYS_PC
    global _RES_FAULT_PC, _RES_TICK_PC, _RES_TASK_A_PC, _RES_TASK_B_PC
    global _RES_FLEET_LEG0_PC, _RES_FLEET_BODIES, _FLEET_COORDS
    from rv64i_to_glyph import assemble_glyph_to_pixels as _ag2p

    def _relink_markers(text: str, pass1: bool) -> str:
        """Replace each __FLEET_ENTER_<phase> marker with the one-slot
        'LDI r30 <pc>' the following KJMP consumes.

        The marker is NOT a label (a label would occupy zero instruction
        slots in pass 1 but the relinked LDI occupies one in pass 2 —
        every packed PC would shift). Instead BOTH passes see exactly one
        slot per marker: pass 1 gets 'LDI r30 0' (placeholder, discarded),
        pass 2 gets the real packed PC. Layout-identical, operand-only.
        """
        for phase in range(len(RES_FLEET_BOXES)):
            marker = f"__FLEET_ENTER_{phase}"
            sub = (f"LDI r30 0" if pass1
                   else f"LDI r30 {_RES_FLEET_BODIES[phase]}")
            assert marker in text, f"fleet wiring: {marker} missing"
            text = text.replace(marker, sub, 1)
        assert "__FLEET_ENTER_" not in text, \
            "fleet wiring: leftover entry marker(s)"
        return text

    try:
        txt = _resident_kernel_program_text(mode, status_word, timer_quantum)
        if mode in ("fleet", "fleetnaive"):
            txt = _relink_markers(txt, pass1=True)
        _, coords1 = _ag2p(txt, cols_instrs=cols_instrs, min_rows=min_rows)

        def packed(label: str) -> int:
            col, row = coords1[label]
            return (col & 0xFFFF) | ((row & 0xFFFF) << 16)

        _RES_DISPATCH_PC = packed(":__g18dispatch")
        _RES_DISPATCH1_PC = packed(":__g18dispatch1")
        _RES_KSYS_PC = packed(":__ksys")
        _RES_FAULT_PC = packed(":__g18fault")
        _RES_TICK_PC = packed(":__g18tick")
        # fleet images have no task_6/task_7 daemon bodies (the four
        # fleet agent bodies replace them); those PC globals are only
        # consumed by non-fleet text, so skip when the labels are absent.
        if ":__task_6" in coords1:
            _RES_TASK_A_PC = packed(":__task_6")
        if ":__task_7" in coords1:
            _RES_TASK_B_PC = packed(":__task_7")
        if mode in ("fleet", "fleetnaive"):
            _FLEET_COORDS.clear()
            _FLEET_COORDS.update(coords1)
            _RES_FLEET_LEG0_PC = packed(":__fleg0")
            for phase in range(len(RES_FLEET_BOXES)):
                _RES_FLEET_BODIES[phase] = packed(f":__fleet_{phase}")
                assert f":__fret{phase}" in coords1, f":__fret{phase} missing"
            assert ":__fleetfin" in coords1, ":__fleetfin missing"

        if mode == "paged" and img_shape is None:
            img_shape = _PAGED_IMG_SHAPE
        txt2 = _resident_kernel_program_text(mode, status_word, timer_quantum)
        if mode in ("fleet", "fleetnaive"):
            # pass-2 relink: markers -> real packed PCs (same one-slot
            # discipline as pass 1's placeholder — see _relink_markers).
            txt2 = _relink_markers(txt2, pass1=False)
        img = bake_image(
            txt2,
            atlas=None,
            cols_instrs=cols_instrs,
            min_rows=min_rows,
            out_path=None,
        )
        if img_shape is not None:
            h_t, w_t = img_shape
            canvas = np.zeros((h_t, w_t, 3), dtype=np.uint8)
            hh, ww, _ = img.shape
            canvas[:min(hh, h_t), :min(ww, w_t)] = \
                img[:min(hh, h_t), :min(ww, w_t)]
            img = canvas
        if out_path is not None:
            p = Path(out_path)
            if p.suffix == ".npy":
                np.save(p, img)
            elif p.suffix == ".npz":
                np.savez(p, image=img)
            else:
                from PIL import Image
                Image.fromarray(img.astype(np.uint8)).save(p)
        return img
    finally:
        _RES_DISPATCH_PC = _RES_DISPATCH1_PC = _RES_KSYS_PC = 0
        _RES_FAULT_PC = _RES_TICK_PC = 0
        _RES_TASK_A_PC = _RES_TASK_B_PC = 0
        _RES_FLEET_LEG0_PC = 0
        _RES_FLEET_BODIES.clear()
        _FLEET_COORDS.clear()
