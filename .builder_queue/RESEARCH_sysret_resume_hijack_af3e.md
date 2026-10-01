# RESEARCH — SYSRET resume-PC hijack via a paged rewrite of SYSCALL_PC (word 8201) from inside the SUPER dispatcher

Tick 16 (v2), builder af3e62239ce2, 2026-09-28 ~04:5x CDT. Measured at HEAD
6fdd5647 (re-verified via `git rev-parse` at claim AND at receipt-write time;
no commits landed mid-tick; all deltas in `.builder_queue/` are this tick's
probe artifacts). Phase 1c research — research proposes, never lands engine
code. **No engine or shader code changed**: probes + results + receipt +
ledger row only.

## Question

Tick 15's NOT-proved list named: "SYSCALL_PC (8205) save/restore behavior
under a hostile dispatcher (T1 readback 0; a SYSRET-based hijack variant is
plausible, unmeasured)." This tick closes it — and corrects the word number
on the way in.

## Finding (one line)

**A guest-painted SUPER dispatcher can rewrite SYSCALL_PC (RAM word 8201,
NOT 8205) through the sanctioned translation path and steal the SYSRET
resume: measured output [77, 52], mode USER, final PC (40,30) = the
attacker gadget's HALT, syspc readback 1966088 = (30<<16)|8, a0 clobbered
to 52 — versus the clean-dispatcher control's [77] at the TRUE saved
resume PC (56,4) with syspc 262157. NO FAULT anywhere.** The full
USER→SUPER→attacker-chosen-USER round trip closes; the paged-rewrite
family now covers all five guest-writable control words below the tile
(8193, 8194, 8201, 8207, 8208) plus the reaper trampoline pixels.

## v1 defect, corrected pre-evidence (disclosed in full)

An uncommitted `probe_sysret_pc_af3e.py` (mtime 04:21, results 04:22,
NEVER landed — no ledger row, no receipt, no commit) targeted word **8205**
believing it was SYSCALL_PC. Live enum read this session pins the E-K2
block (`tools/glyph_isa_v2.py:44-57`): SYSCALL_PC_ADDR = 0x8000+0x24 →
word **8201**; word 8205 is SYS_A0_ADDR (0x8034>>2) — v1's own C2 fault
line (`vaddr=0x8034`) says so. v1 was also double-blind: SYS_A0 is
overwritten by the engine at dispatch marshal (:1178) and consumed at
SYSRET (:1201), so v1's T1 could not have discriminated anything about the
resume PC (its "T1" measured identical to its T2 control apart from the
word value — a dead discriminator). v1's mislabel ALSO propagated into
tick 15's landed receipt and ledger row (both call 8205 "SYSCALL_PC"; the
":1183" line cites are right, the word number is wrong). **This receipt
and the ledger correction note are the fix; v1's probe + results are left
on disk uncommitted as the STRAY artifact the
RULING_bm902_oracle_doc_drift posture exists to catch.** (BM902 owner may
adopt or delete; this lane does not own it.)

## Mechanism (source, verified this session)

- SYSCALL arm `tools/glyph_isa_v2.py:1159-1191`: on ksys != 0, saves
  `_syscall_regs`, marshals SYS_N/SYS_A0/SYS_A1 (:1177-1179), saves the
  resume PC into word 8201 packed (row<<16)|col (:1183-1186), mode→SUPER,
  jumps to the ksys dispatcher pixel.
- SYSRET arm `:1193-1208`: restores regs, sets r10 = memory[8205]
  (:1201), mode→USER, reads word 8201 and sets next_pc =
  (col*INSTR_WIDTH, row) with **no fence/box/tile consult on the packed
  target** — the same unchecked-jump shape as KJMP (:1261-1275)/JMP.
- The dispatcher's rewrite STs ride the SUPER-mode MMIO-window exemption
  `:968` (paged walk bypassed for mode==SUPER and addr in
  [8192,8448) words) → fall through to the plain `memory[addr]` arm
  (:1098-1100, `0 <= addr < len(memory)`).

## Harness

`.builder_queue/probe_sysret_pc_v2_af3e.py` (+ `_r1_control.py`,
`_r2_discrimination.py`): real `GlyphProcessTable.spawn(tile=(256,19,1,2))`
posture (same tile as ticks 12-15; covers RAM words 8211/8212), cols_instrs=16
both baker and table, min_rows=64; tag 0x505447 at word 1535, PT base 1536;
PT armed by the task's lawful in-tile ST to 8211 (BK-66 discipline);
ksys armed HOST-side to (28,8) after spawn — the loader-seed posture the
E-K2 comment describes (`:1171`); dispatcher `LDI r9 77; PRT r9; LDI r6
1966088; LDI r7 8201; ST r7 r6; LDI r6 52; LDI r7 8205; ST r7 r6; SYSRET`
painted by the task at words 1856..1899 via vpn-12 PIX PTE pfn 7; attacker
gadget `LDI r2 52; PRT r2; HALT` at words 1952..1963 (same frame);
instruction words from the REAL GlyphAssemblerV2, never hand-encoded.
Verdicts from exit_status + fault fields + cpu.output + final PC + RAM
readback BYTES (words 8194/8201/8205), never stdout.

## Measured legs (3 pinned runs byte-identical per file)

- **T1** `probe_sysret_pc_v2_af3e_results.json` md5
  97a9828cb6045d4c448767e44df8a6c2 (deterministic results md5 from the
  probe's own print: 24b21e6b9de4a95462c6c965bccc1561): exit 0, no fault,
  output **[77, 52]**, mode USER, final PC **(40,30)** — the gadget's HALT
  (gadget row 30, HALT col 10 → x=40), syspc 1966088, sysa0 52. The
  dispatcher's word-8201 rewrite SURVIVED to SYSRET and chose the resume.
- **T2 clean-dispatcher control**: exit 0, output [77], mode USER, final
  PC (56,4) = the program's own post-SYSCALL HALT, syspc **262157** =
  (4<<16)|13 — the engine's TRUE saved resume PC, decoded and consistent
  with the baked layout. T1 vs T2 differ ONLY in the dispatcher's two
  stores → the deltas (output [77,52] vs [77], PC (40,30) vs (56,4),
  syspc 1966088 vs 262157, sysa0 52 vs 0) isolate the mechanism to those
  stores. Also: T2's sysa0 readback 0 (not the task's r10) — consistent
  with v2's dispatch-leg note that the restore happens on the task's
  saved registers and the marshal value lands at 8205 only transiently.
- **R1 arm-PT-zero-PTE control** (`probe_sysret_pc_v2_r1_control.json`
  md5 66db71c3672852cfbfeb261f29584a9a): SYSCALL under armed PT + tag but
  ZERO PTEs mapped anywhere: exit 0, output [] (guest painted no
  dispatcher), final PC (32,28) = the host-armed ksys dispatch target
  (28*64+32 = word 1824 = SYSRET's own pixel — parked mid-dispatcher,
  running=False on walk-off past the 3-line paint), syspc 5, mode SUPER.
  Confirms a paged-armed task CAN take the :968 exemption branch and
  dispatch (the walk itself breaks nothing); probes no unpaged hole.
- **R2 discrimination** (`probe_sysret_pc_v2_r2_discrimination.json` md5
  29a9b765a4b8aa28dc752a577d2620c4, deterministic print md5
  3bf3ed639e2683000f7e70f9ece9c795):
  - R2a HOST-written full-flag PTEs, same hijack dispatcher: output
    [77,52], PC (40,30), syspc 1966088 — **identical to T1**.
  - R2b stamp fate (task never run): RAM PTE words 0/0, RAM tag 0;
    image words carry the stamps (8199 = 0x2007, 1807 = 0x70f, tag
    5264455). The guest's stamps live ONLY in the image plane; RAM-first
    PTE reads see 0.
  - R2c HOST-written PTE with pfn 0 (wrong frame), same dispatcher:
    output [77,52], PC (40,30), syspc 1966088, **RAM word 0 NOT
    clobbered** (readback 0) — the rewrite did NOT go through the paged
    walk. **` (40,30)` note:** the identical T1==R2a==R2c outcome under
    three different PTE regimes (zero/image-only, correct host-written,
    wrong host-written frame) is the evidence that **the :968
    MMIO-window exemption served the dispatcher's stores, not the paged
    walk** — the frame the PTE names is irrelevant, the paddr-consult
    posture of 9714a363 does not even engage for a SUPER dispatcher.
- **C1 no-translation control** (in the v2 results file): vpn-32 PTE
  left 0 — the dispatcher's own ST faults pte_invalid mid-dispatch
  (fault_addr 32804 = 8201*4) — **but the measured C1 row is exit 0,
  output [77,52]** — see the honest-catch section below.
- **C2 rot-guard**: unpaged out-of-tile ST to word 8201, NO PT: E-K1
  trap, exit 1, mode SUPER, parked at (0,30), syspc 0 — the landed tile
  fence is LIVE for this word when translation is not armed (BK-66-C2
  shape, SYSCALL_PC flavor).

## Honest catch — C1 did NOT behave as predicted (NOT buried)

Pre-registered C1 expectation: dispatcher ST pte_invalids, vectors to the
reaper, output [77] only, exit 1. Measured C1: exit 0, output [77,52],
mode USER, PC (40,30), syspc 1966088 — **byte-identical to T1 in every
recorded field including dispatch_pixels**. Diagnosis (source + R1/R2
evidence, mechanism verdict measured, the fault-line read itself is
reasoned-from-:889-889 RAM-first ordering + R2b, labeled): the :968
exemption fires BEFORE any PTE consult, so the dispatcher's SUPER-mode STs
ignore the PTEs entirely — there is no pte_invalid to take. C1 failed as a
discriminator because its premise (the walk serves the stores) was false —
which is itself the finding R2c pins independently. The receipt's verdict
does not rest on C1; C2 (unpaged fence) and T2 (clean dispatcher) carry
the control weight. **What the PASS does NOT prove:** no leg shows the
walk's own fault path under a hostile SUPER dispatcher (unreachable here —
the exemption short-circuits it); the :889-889 ordering claim is
source-read, not fault-injection-measured.

## C1 surprise, quantified

The v2 probe's expected-if-live for C1 ("output [77] only") is FALSIFIED
by its own printed leg — the probe file's docstring line "C1 ... output
[77] only" does not match the results file's C1 row. Both are committed
verbatim; the docstring records the pre-registered prediction, the results
file the measurement, and this section the adjudication. Never-edit-
after-the-fact discipline: the mismatch stays visible.

## Consequence

1. The paged-rewrite family is now measured at FIVE control words +
   the trampoline: 8193 (tick 13), 8194 (tick 15), 8201 (this tick),
   8207/8208 (tick 14), 960..963 (tick 12). One fence shape covers them
   all; the recommended BK-66 gate leg should fence the WHOLE 8192..8210
   span (every word in it is now individually measured guest-rewritable
   from a tile-confined task) — and this tick adds that the fence must
   ALSO cover SUPER-mode accessors, because :968 exempts them from the
   walk a paddr-consult would live in. The 9714a363 posture closes the
   USER arms mechanically; the SUPER-dispatcher arm is a NEW posture
   question its wording does not yet name.
2. SYSRET's unchecked packed-PC resume is a second delivery surface with
   the dispatcher hijack: even with KFAULT_PC/KTICK_PC pinned, a hostile
   dispatcher chooses where USER execution resumes. The BK-66 landing
   gate should grow a SYSPC leg: paged OR exempt SUPER ST to 8201 must
   trap, and SYSRET must refuse a word-8201 value the engine did not
   write (value-pinning is plausible here — unlike GH-16, the kernel IS
   the only legitimate writer of the resume PC).
3. a0 delivery (:1201 r10 ← memory[8205]) lets the hostile dispatcher
   feed the resumed USER code a chosen register value (T1's 52) — the
   round trip is not just control flow, it is a data channel.

## Recommended additive BK-66 gate legs (RED today, per the measured shapes)

- SYSPC-L1: guest-stamped-PTE dispatcher rewrite of 8201 → SYSRET must
  NOT resume at the rewritten PC (RED today: T1's [77,52] at (40,30)).
- SYSPC-L2: same under HOST-written correct PTE (RED today: R2a) and
  wrong-frame PTE (RED today: R2c — pins the :968 exemption as the
  serving branch; the fix must gate the exemption site itself, e.g.
  consult the tile/paddr fence for MMIO-window stores in SUPER too).
- SYSPC-L3: T2 clean-dispatcher control stays green (never weaken E-K2).
- SYSPC-L4: C2 unpaged rot-guard stays green (never weaken the tile
  fence).

## NOT proved (labeled)

- Twin side: the WGSL walker has no SYSCALL/SYSRET dispatcher at all
  (tick-15 source-read label stands) — oracle-only.
- The exact fault-path ordering claim for C1's counterfactual (:889-889
  RAM-before-image PTE read) — source-read + R2b-adjacent, not
  fault-injection-measured.
- SYSRET-hijack WITHOUT a hostile dispatcher (i.e. a USER-side race
  against :1183's save) — structurally impossible in a single-task
  single-stepped engine; not probed and probably not expressible.
- TIMER_RELOAD periodic re-fire, MODE_LATCH/BOX lo-hi words (carried
  from ticks 14/15, still unprobed individually).
- Whether xv6-nano's real C dispatcher ever executes guest-painted
  pixels (the hostile-dispatcher posture is synthetic by construction;
  the E-K2 comment describes the dispatcher as "a plain C function").

## Rule-1 floors

Numbers in this receipt are structural (word values, addresses, exit
codes, PC coordinates, md5s) — rule-1 measurement floors do not attach.

## Provenance

- HEAD at claim and at landing: 6fdd5647 (monitor fingerprint matched).
- Mailbox: no RULING_*.md newer than HEAD at claim (newest mtime
  1790550013 < 1790586900).
- Queue: QUEUE_STATE.json 25/25 landed, active null → Phase 1c eligible.
- Probe files: probe_sysret_pc_v2_af3e.py (md5 0e584b7578853fa9dc92a2d89
  f8dd56b), probe_sysret_pc_v2_r1_control.py (4b3c82e42b88a8feb9019827a
  3450cfd), probe_sysret_pc_v2_r2_discrimination.py (4231b552992164f074
  0e88ea9ee1e8d6). Stray v1 (probe_sysret_pc_af3e.py, 3d7f137161e07a16b
  634c09dd6700295) left on disk, disclosed above.
- 3 pinned runs byte-identical per results file (md5s above).
