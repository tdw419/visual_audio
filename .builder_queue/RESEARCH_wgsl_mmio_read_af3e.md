# RESEARCH — WGSL MMIO-block READ channel: walk_ld's unmode-gated box_mmio
# branch is ORACLE PARITY, not divergence — both engines leak the config
# block to USER reads; only the WRITE side diverges (BK-50)

**Tick:** 2026-09-27, Phase 1c research (builder af3e62239ce2)
**HEAD at measurement:** 4197658c (tracked tree clean at claim; probes
untracked, zero tracked-file mutation)
**Question:** BK-50 measured walk_st's MMIO write door on-device but
disclosed the LD side unmeasured: "walk_ld's MMIO branch (:361-363) is
also unmode-gated by source read — likely a config-read channel, lower
severity, not measured here" (RESEARCH_wgsl_mmio_door_af3e.md:26). Is
the read channel real on-device, and is it divergence or parity?

## Method

- Probe `.builder_queue/probe_wgsl_mmio_read_af3e.py` (untracked, landed
  modules only). Signal command to re-derive:
  `python3 .builder_queue/probe_wgsl_mmio_read_af3e.py`
  (3 runs byte-identical, results md5 c464ef9baff66a9b9ae63e06a00d2cd5;
  GPU = RTX 5090, wgpu default adapter).
- Harness = the BK-50 probe's device harness verbatim (run_wgsl's real
  buffers + build_shader(OpcodeMapV2()), probe-only seeded cpu.mode +
  box_mmio; box [1200,1300) BYTES armed via mmio[3]/mmio[4]; verdicts
  from ram/mmio READBACK BYTES, never stdout).
- Oracle-parity control: `.builder_queue/dbg_mmio_read_oracle_pt_af3e.py`
  — same program on GlyphCPUv2, config words in plain self.memory,
  `cpu.running=True` set before stepping (3 runs identical: faulted
  False, mode 1, word310 == 7).

## Findings (measured, deterministic)

1. **S1 (source): walk_ld is the twin's ONLY fence-gated read, and its
   gate does not cover the MMIO branch.** The inner branch
   (wgsl_glyph_isa_v2.py:361-363) carries no mode term; the only mode
   term (`is_super`) lives on the OUTER condition (:353), which
   `pt_base == 0u ||` short-circuits when paging is disarmed — the
   default on every probe/fleet image (BK-48/49/50 posture). Probe S1
   legs: inner branch mentions mode = False; outer has is_super = True;
   short-circuit on pt0 = True; addr_in_box calls in walk_ld = 0, in
   walk_st = 2 (one comment, one consult).
2. **D1 (on-device): the config-read channel REPRODUCES.** Seeded-USER
   `LD` of word 8196 (BOX0_HI, armed 1300) reads the value and the
   follow-up ST delivers it in-box: ram[310] == 1300, mode stays USER
   (1), fault_addr_word == 0, clean halt in 5 steps.
3. **D2 (on-device, disclosure leg): the guest reads its own fault
   VECTOR.** Same shape for word 8193 (KFAULT_PC, seeded 7):
   ram[310] == 7, mode USER, fault 0, 5 steps. This is exactly the
   aiming value BK-55's hijack needs — the read channel composes with
   the write door into a self-contained attacker toolchain (no kernel
   image introspection required to aim KFAULT_PC).
4. **D3 (oracle-parity control): PARITY, not divergence.** The oracle's
   LD arm (glyph_isa_v2.py:826-933) consults no fence on any path and
   keeps words 8192+ in plain self.memory, so its USER LD reads the
   config block too: word310 == 7, mode stays USER, faulted False. The
   asymmetry with BK-50 is real and directional: on the WRITE side the
   twin lands clean where the oracle traps (BK-50 D1/D2); on the READ
   side both engines leak silently.
5. **D4 (harness control): the box fence is LIVE.** USER ST of 4660 to
   out-of-box word 100 → E-K1 fires (fault_addr_word == 400, mode→SUPER
   0, ram[100] == 0, 3 steps). D1/D2's clean reads are the read
   channel, not a dead harness.
6. **Structural asymmetry (read, path:line): the read channel has NO
   fault path at all.** walk_st's out-of-box consult at least records
   and vectors through E-K1 (wgsl_glyph_isa_v2.py:446-460; and per
   BK-55 that vectoring is itself an escalation primitive) — but the
   LD side of the MMIO range returns the value silently on both
   engines. A read posture for the config block cannot ride the
   existing E-K1 machinery; it needs its own decision (mode-gate the
   branch like walk_st's SUPER-only term, or accept and document the
   block as guest-readable).

## Consequence for the BK-38..45 sequenced fence commit

BK-41's "whole config block kernel-write-only" posture, landed alone,
leaves the block USER-READABLE on BOTH engines. The landing round must
make the READ posture an explicit line item: for the twin, either
mode-gate walk_ld's MMIO branch (mirror the outer condition's
`is_super &&` into the inner check) or pin guest-readability as
documented behavior. Read-gating KFAULT_PC/BOX words also de-fangs the
BK-55 aim step. Nothing in this receipt lands engine/shader code.

## Probe defects disclosed

- **Draft-leg bug (caught by readback, verdicts unaffected):** the first
  device runs STed the LD result to word 1250 believing it "in-box" —
  1250 is a WORD index; its byte address 5000 is outside box
  [1200,1300), so the result store itself took E-K1 (fault_addr_word
  5000, mode→SUPER) and ram_result_word read 0. The trap record is what
  exposed it: fault_addr == 4 × result_word. Fixed by moving the result
  word to 310 (byte 1240, genuinely in-box); post-fix runs are the
  cited md5. Disclosed artifacts kept: dbg_oracle_trace_d2_af3e.py
  (single-step trace showing the LD itself succeeding at step 2, r5=7,
  while the result ST trapped at step 4).
- **Baked-image dead pixel:** the probe's D2/D3 program bakes an
  opcode-None pixel at (28,0) after the HALT row, so the oracle
  run()-form halts with halt_reason opcode-None while faulted flips
  True via the no-handler trap path. The dbg harness sets
  cpu.running=True and steps manually, reading the conviction directly
  (word310 == 7). Device legs unaffected (WGSL stepping is
  dispatch-driven, not pixel-walk past HALT).

## Numbers policy (rule 6)

All cited numbers are structural (word addresses, byte values, fault
codes, step counts, md5s, line numbers) — no rates, latencies, or
ratios — so rule-1 floors do not attach. Signal commands named: probe
run above; `grep -n "addr_in_box" tools/wgsl_glyph_isa_v2.py` (consult
sites); `grep -n "BOX_MMIO_WORD_LO && addr <" tools/wgsl_glyph_isa_v2.py`
(branch sites).

## Candidate backlog item (BK-56, filed to systems/GLYPH_BACKLOG.md)

Config-block READ posture: walk_ld's MMIO branch (:361-363) must either
require is_super (parity with the outer walk_st SUPER-only MMIO term at
:409) or the config block must be documented+gated as guest-readable.
Gate `tests/test_bk56_mmio_read_posture.py` with legs per the backlog
row. NOT landed by this receipt — research proposes, never lands engine
code.
