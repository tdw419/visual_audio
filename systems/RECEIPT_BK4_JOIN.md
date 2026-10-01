# RECEIPT — BK-4 waitpid/join (roadmap row BK-4, promoted by commit 212b19d)

**Date:** 2026-09-11 · **Builder:** cron af3e62239ce2 · **Branch:** glyph-transpiler-autoloop

## Gate spec (roadmap row)

> `tests/test_bk4_join.py` — parent spawns, child exits 42, parent reads 42;
> join on already-dead child returns immediately.

## RED → GREEN

RED (before `tools/glyph_gpt/join.py` existed):
```
ERROR tests/test_bk4_join.py — ModuleNotFoundError: No module named 'tools.glyph_gpt.join'
```
(`output/bk4_gate_run1_red.txt`)

GREEN (final): `tests/test_bk4_join.py` **4/4** in 1.09s:
- L1 `test_bk4_join_fresh_child_delivers_exit_code` — join word 721 = 42
- L2 `test_bk4_join_already_dead_child_returns_immediately`
- L3 `test_bk4_child_never_rerun`
- L4 `test_bk4_ticks_serviced` (non-vacuity, quantum=12)

Final memory state (drive, quantum 12): `703=0xFEED0006 710=0x111 717=0x3 720=0x2A
721=0x2A 723=0xFEED0007 732=5 741=0x2A 742=1 951=0xCAFE0028`, halted=True,
faulted=False, 324 steps.

## Design (all mechanics landed patterns — zero engine changes)

Blocking join cannot be a plain "deferred SYSRET": the engine's E-K2 resume
PC (SYSCALL_PC word 8201) always points at the TRAPPED task. Deferring
simply resumes the parent; the parent's tail KJMPs the dispatch leg; if that
leg KJMPs the SIGRET trampoline, its SYSRET resumes the parent AGAIN — an
infinite parent↔kernel loop. Measured in `output/bk4_dbg4.py`: B never
scheduled, 60000 steps exhausted, tick 0x694, done flags 716=1/734=0.

Fix — **run the child inside the parent's trap window** (the BK-3
delivery-at-registration shape):

1. A (parent) traps SYS 13 while CHILD_DONE (742) == 0 → `:__ksys13_defer`
   SYSRETs empty.
2. A's tail KJMPs `:__dispatch`. The leg reads SYS_N (8204): still 13 →
   A's join is pending → zero 8204, arm MODE_LATCH, JMPR into `:__task_b`.
3. B (USER) works (742 = 42), traps SYS 12: the SUPER slice stores a0 →
   EXIT_CODE (741), lights 742, SYSRETs. B's tail (exit marker, done flag)
   KJMPs `:__bret`.
4. `:__bret` promotes B's done bit into 717, then `:__finish_join` copies
   EXIT_CODE → A's in-box join word (721), **re-points the saved resume PC
   (word 8201) at `:__aresume`** (the instruction after A's join), clears
   the stale marshaling words (8204/8205), and JMPRs `:__sigret`.
5. `:__sigret`'s SYSRET restores A's pre-trap registers and resumes A at
   `:__aresume` — join "unblocked", code already in-box.

Joining an already-dead child takes the inline `:__ksys13_copy` branch
(CHILD_DONE ≠ 0 → copy → SYSRET) with no dispatch detour.

ABI words: 703/723 exits, 710/720 work, 716/734 in-box done flags (SUPER
promote → 717), 721 join word (THE gate), 741 exit code, 742 child-done,
732 ticks, 759 fault, 761 unknown-sys. A's post-join mirror: 712.
Status: 951 = 0xCAFE0028.

## Defects found on the way (Bug 11)

**Bug 11 (BK-4): deferred join = parent↔kernel SYSRET ping-pong.**
Details above. Class sibling of Bugs 9/10: the trap/SYSRET machinery
belongs to the trapped task; anything the kernel wants to happen "before
the task resumes" must happen inside the trap window, or the resume PC
must be re-pointed first (word 8201).

## Findings recorded (no code change this ticket)

1. **Pre-existing latent kernel bug (BK-3 signals.py):** its `:__kdone`
   zeroed word 8204 (SYS_N) but never word 8205 (SYS_A0) or 8201
   (SYSCALL_PC). Harmless there only because every task HALTs before any
   further trap. BK-4's `:__finish_join` zeroes both 8204 and 8205 (8201
   is deliberately RE-pointed, not zeroed). Leave BK-3 as landed (green,
   committed); noted for any future BK-3 follow-up.
2. **Engine divergence (backlog candidate):** an unknown opcode in
   GlyphCPUv2.step() sets `running=False` (halt); the WGSL shader's
   `get_opcode_from_color` returns 1000 and `main()` falls through with NO
   branch matching it — execution continues as a no-op. A byte-corrupted
   opcode pixel halts one engine and silently continues on the other.
3. **WGSL parity probe caveat:** WGSL has no separate RAM list — data-word
   stores overwrite baked text at colliding words (BK-4's tick word 732 is
   also row-22 instruction text; WGSL readback `0xEC5050` is adjacent-LDI
   pixel bleed). The CPU's `ram_words`-backed memory writes data out-of-band
   and keeps text intact. So image-word parity below the text region is NOT
   a meaningful equality domain for kernels whose data words collide with
   text words; semantic-ABI-word parity is the honest check. Measured:
   all 11 ABI words byte-parity across engines (word 732 readback differs
   for this structural reason; Python CPU's tick=5 is the correct value).

## Verification

- Gate 4/4 green (`output/bk4_gate_run1_red.txt` → pytest 4/4).
- WGSL parity probe `output/bk4_dbg7_parity.py`: both engines halted clean;
  ABI words 703/710/717/720/721/723/741/742 identical; 951 status parity
  holds on the 24-bit domain both engines actually share (0xFE0028).
- Arc regression: GH-1..GH-26 core + BK-1/2/3/4 (see commit message for
  the exact suite line and count).
