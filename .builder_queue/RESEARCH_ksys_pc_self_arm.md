# RESEARCH — KSYS_PC is guest-writable: the E-K2 "armed dispatcher" posture
# is guest-defeatable AND guest-self-armable (BK-41 candidate)

- **Builder:** af3e62239ce2 (Glyph OS event-chain cron, Phase 1c research tick)
- **Date:** 2026-09-27 (~02:0x CDT)
- **Tree:** HEAD 3ba4ad771427ad235fd482e66f2d4bf0392b2539 at probe start;
  probe landed modules only (no engine edits).
- **Question:** BK-40's gate spec offers a cheaper alternative posture —
  "arm KSYS_PC by default on tiled spawns (E-K2 dispatcher) — must be
  measured ... before choosing". Does the armed E-K2 posture contain a
  tiled USER task, given BK-39 measured PARALLEL_ST fence-blind and the
  KSYS_PC control word lives at word 8194 in guest-visible RAM?

## Method

Probe `.builder_queue/probe_ksys_arm_af3e.py` (untracked, landed modules
only), harness = the landed item-29 containment path itself:
`GlyphProcessTable.spawn(image, tile=(5,0,8,8))` (words rows 5-12 x cols
0-7, W_MEM=32), auto reaper row 30. KSYS_PC word 8194 =
`KSYS_PC_ADDR>>2` (`tools/glyph_isa_v2.py:45`, `BOX_MMIO_BASE+0x08`).
Dispatch target packing `(row<<16)|col`; gadget pasted at pixel row 6.
Staging/out-of-tile target word 176 (row 5, col 16). E-K2 dispatch site
`tools/glyph_isa_v2.py:1132-1158`; ST fence (mode-gated) `:1041`;
SYSRET register restore `:1164-1173`; disarm observed via direct
`_handle_syscall` branch `:1156-1158`.

Determinism: 3 runs, 4 cases each, results byte-identical,
**md5 831ea1d8714f9f87c7a608e540618cdd** (results dict blob;
`/tmp/ksys_probe.txt`). Re-derive: `python3
.builder_queue/probe_ksys_arm_af3e.py`.

## Findings (all quantities structural — word values, exit codes, booleans; NO rate/latency/cost claims, rule-1 floors do not attach)

1. **A. ctl_ksys_dispatch** (posture armed host-side to gadget (6,0),
   gadget = plain `ST` of 0xC0FFEE to word 176 then HALT; user program
   issues one syscall): EXIT_OK, faulted=False, mode ends SUPER,
   `memory[176]==0xC0FFEE` — the E-K2 dispatch executes guest-placed
   code in SUPER mode, and the ST fence is mode-gated
   (`elif self.mode == MODE_USER and not self._addr_in_box(...)`,
   `glyph_isa_v2.py:1041`), so the gadget's store lands out-of-tile.
   The posture routes ALL syscalls to guest-chosen pixels.
2. **B. disarm_then_read** (posture armed; user program first
   `PARALLEL_ST`s 0 into word 8194, then issues 0x02 READ with
   dest=176, ring seeded 'K','F'): EXIT_OK, `ksys_after=0`, the DIRECT
   fence-blind handler branch runs (`:1156-1158`), 0x4B/0x46 land at
   words 176/177 clean. **One instruction defeats the armed posture** —
   the control word is writable by the same fence-blind write BK-39
   measured.
3. **C. self_arm** (posture OFF at spawn; user program
   `PARALLEL_ST`s 393216 = (6<<16)|0 into word 8194 itself, then
   issues a syscall): EXIT_OK, mode ends SUPER, `ksys_after=393216`,
   gadget's 0xC0FFEE lands at word 176 clean. **The guest turns the
   posture on for itself and points it at its own tile** — no kernel
   involvement at any point.
4. **D. ctl_st_out** (no posture, plain ST to 176): EXIT_FAULT,
   faulted=True — the E-K1 store fence is live on this tree; every
   bypass above flows around a fence that demonstrably works for ST.
5. **Docstring falsified (measured):** `tools/glyph_containment.py`
   (item-29 landing docstring) states "A task that never exits USER
   mode cannot reach SUPER: mode changes only via the E-K1 trap, KJMP,
   SYSRET, tick — none of which the fence-crossing store itself can
   trigger". Leg C shows a task reaching SUPER from USER with no
   kernel image, no KJMP from a kernel, no SYSRET return: the guest
   arms its own E-K2 vector with a fence-blind PARALLEL_ST and the
   SYSCALL opcode does the rest. The item-26/29 containment claim
   inherits this hole exactly as items 26/29/34/35/38 inherited the
   BK-38/39 ones.

## Verdict

The "arm KSYS_PC on tiled spawns" posture is NOT a cheaper BK-40 fix:
measured, it is (a) defeatable by the same PARALLEL_ST primitive BK-39
measured, and (b) invertible — the guest can arm it at an arbitrary
in-tile gadget to mint itself a USER→SUPER escape. The BK-40 fence-the-
handlers posture (consult `_addr_in_box` in the four DATA write arms)
and the BK-39 consult-site fix remain the only measured-viable shape;
BK-38/39/40 must land together or in one sequenced engine commit, and
word 8194 (plus the whole BOX_MMIO config block) must become
kernel-write-only in the same round — else the fence is still guest-
editable.

## Probe-hygiene disclosure

- Draft 1: numpy `img[6:8] = gadget` on a 2-row image — out-of-range
  slice, SILENT no-op; legs A/C/D jumped to black pixels and reported
  nothing. Caught on read-back (dispatch-target pixel black) before any
  finding recorded; draft 2 builds a 32-row canvas and asserts the
  gadget dispatch pixel is non-black.
- Draft 2 first run: host-side KSYS arming had been dropped in the
  rewrite — leg A never armed the posture, leg B "disarmed" an
  already-zero word (leg B as-run was a BK-40 L1 reproduction, not the
  disarm claim). Caught by comparing run output against the claimed
  leg semantics; arming parameter restored before evidence taken.
- Docstring-falsification leg (C) is directional on one gadget shape
  (plain ST in SUPER); CALL-class image-plane writes in SUPER are not
  separately probed.

## NOT verified

- WGSL twin on-device (E-K2 exists in `tools/wgsl_glyph_isa_v2.py:181,723`
  by source read only; nothing spatial was run on the shader path).
- 0x03 FILE_WRITE exfiltration side (still unprobed from the BK-40 tick).
- Whether MODE_LATCH one-shot (`:1236-1240`) re-entry semantics change
  the posture under a real kernel scheduler (no kernel image was run).
- Blast radius of SUPER-mode CALL/PUSH image-plane writes from a
  self-armed dispatch (same class as BK-39 leg 4, not re-measured here).

## Backlog candidate (filed as BK-41, systems/GLYPH_BACKLOG.md)

Gate: `tests/test_bk41_ksys_fence.py` — L1: tiled USER with armed
KSYS_PC + hostile gadget → syscall must NOT execute guest-chosen code
with fence privileges (RED today: 0xC0FFEE lands); L2: disarm leg —
PARALLEL_ST 0 -> word 8194 must trap once the MMIO block is kernel-
write-only (RED today: ksys reads 0, direct handler runs); L3: self-arm
leg — guest PARALLEL_ST into 8194 must trap (RED today: dispatch
fires); L4: benign-dispatch control stays green for a kernel-owned
posture; L5: non-vacuity (neuter the kernel-write-only consult → L2/L3
fire); L6: family — BK-38/39/40 + item-29 gates green. Prereq: BK-38 +
BK-39 + BK-40 (same consult sites + the MMIO write-only class). NOT
claimable without Jericho per the backlog header.
