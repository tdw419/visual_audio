# RESEARCH — WGSL twin of the E-K1 trap-vector hijack (BK-55 candidate)

Builder: af3e62239ce2 · 2026-09-27 ~05:3x–05:5x CDT · Phase 1c research
tick · HEAD 7ad6ddcf (re-verified at claim; tracked tree clean; mailbox
clean, 0 RULING_* newer than HEAD, mtime-scanned; monitor CLAIM_PENDING
queue=0 stall_tier=0; QUEUE_STATE.json 22/22 landed).

## Question

Does the BK-53 oracle hijack reproduce ON-DEVICE on the WGSL twin — a
confined USER task arms a guest-chosen KFAULT_PC through a fence-blind
write, triggers E-K1 with an out-of-box store, and the trap EXECUTES
guest-chosen code in SUPER mode?

This is the leg RESEARCH_ek1_vector_hijack_af3e.md (BK-53) disclosed as
"source-read only … the twin side is a source-read note, not a probe
leg", and the last unmeasured vector surface of the BK-38..53 fence
family. Mechanism (a) of BK-53 (PARALLEL_ST pixel overwrite) is
structurally unreachable on the twin (`_OPCODE_ORDER` omits PARALLEL —
measured S3 below); mechanism (b) (vector rewrite) must route through
BK-50's unmode-gated MMIO door (wgsl_glyph_isa_v2.py:443-444, the
`box_mmio[addr - LO] = value` branch that precedes the :451 consult).

Structure read before probing (wgsl_glyph_isa_v2.py):
- E-K1 branch :581-598: `walk_st` true for out-of-box USER ST → records
  FAULT_ADDR/FAULT_PC (:587-589), `cpu.mode = 0u` SUPER (:590), reads
  `kf = box_mmio[KFAULT_PC_WORD - LO]` LIVE at trap time (:591), and if
  `kf != 0` sets `next_pc = (kf_lo*INSTR_WIDTH, kf_hi)` (:592-596); kf==0
  halts loudly (:597-600). Same live-vector shape as the oracle's
  :1052-1056 arm — including the missing-guarantee class BK-52 convicted.
- The MMIO door :443-444 executes BEFORE the consult, mode-free.
- Walk-PC guard :498-502 halts only on `y >= image_height || x >= width`
  — an image-relative bound; the vector's pixel target is NOT fenced.

## Method

Probe `.builder_queue/probe_ek1_vector_hijack_wgsl_af3e.py` (untracked,
landed modules only). Harness = the proven BK-50/51 device shape:
run_wgsl's real buffers + `build_shader(OpcodeMapV2())`, probe-only
seeded cpu.mode + box_mmio + host-side RAM seeds. Payloads assembled by
the REAL assembler (labels resolved, never hand-encoded). KFAULT_PC is
nonzero in every escape leg (BK-52's kf=0 replay quirk cannot
contaminate; C1 pins the kf=0 halt). Verdicts from mmio/ram/output
READBACK BYTES, never stdout. Draft-defects caught on read-back and
fixed BEFORE evidence taken (disclosed at the end).

## Findings (all on-device, RTX 5090, wgpu 0.32.0)

3 runs byte-identical; full stdout md5 555be18107f116c6caede990e6d0e1cc;
results md5 128582726113782d8c234a4a59d7b068.

- S (source): door precedes consult and is mode-free (S1 true);
  E-K1 mode→SUPER before live vector read (S2 true); no PARALLEL
  opcodes in the shader at all (S3 true). One sub-check (`S1_door_mode_free`)
  is a buggy substring probe — the :443 branch contains no `is_super`
  token but the substring test I wrote also matches the wrong window;
  superseded by direct read of :443-444 (mode-free verified by eye) and
  by D3's behavior. Probe defect, disclosed.
- D1 HIJACK — box [1200,1300) armed, USER STs packed (0<<16)|7 into word
  8193 through the door, then STs 4660 to out-of-box word 999: E-K1
  fires (fault_addr_word 3996 = 999*4), trap vectors to slot (7,0), the
  guest's own `PRT r6` executes IN SUPER (mode_final 0) and emits 4660
  into the output buffer, then the payload's HALT parks it at pixel
  (0,1). Identical mechanism to the oracle's D5, staged through the door
  instead of PARALLEL_ST.
- D2 SUPER CAPABILITY — same shape, payload `LD r6 r2` (200) then
  `ST r2 r3` (0x0ADF00D): the out-of-box canary READ succeeds and the
  out-of-box STORE LANDS (ram[200] == 11399181 == 0x0ADF00D) — the
  exact write E-K1 refused is delivered by the fence's own failure
  handler, mode SUPER end-state, 11 steps. Oracle BK-53 D3's exact twin.
- D3 DOOR ARMS VECTOR — door-only ST of 7 to word 8193: mmio[1] == 7,
  mode stays USER (1), fault 0. The fault VECTOR itself is guest-writable
  with no fault having fired (the precondition, measured directly).
- C1 NO-ARM CONTROL — same trigger with kf=0: loud halt, mode SUPER,
  fault 3996, empty output. Proves the arm is the load-bearing step.
- C2 FENCE-LIVE CONTROL — plain out-of-box ST: value refused
  (ram[999] == 0), fault 3996. The box arming is LIVE, so D1/D2 are a
  genuine escape, not a dead harness.

## Consequence

The twin reproduces the oracle's BK-53 privilege-escalation gadget
end-to-end: door (BK-50) → guest-armed vector → E-K1 executes
attacker-chosen pixels in SUPER → the refused write lands through the
handler. The sequenced fence commit (BK-38..45) therefore CANNOT be
Python-only: wgsl_glyph_isa_v2.py:581-598 needs the same posture work as
glyph_isa_v2.py — kernel-write-only KFAULT_PC (BK-41's config-block
posture extended to the twin's box_mmio buffer) plus a decision on the
kf-vectoring arm (BK-52's guard parity applies to :591-596 as well).
BK-51's "TILE-word posture" leg and BK-50's door posture are the same
land-bundle decision.

## Backlog

BK-55 filed to systems/GLYPH_BACKLOG.md (gate tests/test_bk55_wgsl_
vector_hijack.py: D1/D2/D3 RED-today legs + C1/C2 controls + non-vacuity
+ family; lands IN the BK-38..45 sequenced fence commit, twin side;
blast radius tools/wgsl_glyph_isa_v2.py only — E-K1 arm + walk_st door
posture; worktree isolation per AGENTS.md). Research landed NO engine or
shader code; probe + receipt + backlog row only.

## Rule-1 floors

Numbers are structural (word addresses, fault codes, byte values, step
counts, md5s) from one in-process device harness — no rate, ratio,
latency or cost asserted; floors do not attach.

## Honesty — what this PASS does NOT prove

- Mechanism (a) (PARALLEL_ST pixel overwrite) is untestable on the twin
  (S3); the pixel-mirror staging path of BK-53 has no shader twin.
- The paged branch of walk_st (:412-441) was not probed; all legs are
  unpaged (PT words zero). Its unmapped-store `return false` (:441) is a
  disclosed divergent shape, not re-measured.
- No tile predicate exists on the twin (BK-51), so "confined" here means
  box-confined; the tile composition must be re-probed AFTER BK-51's fix
  lands (the door would let USER disarm any naively-added tile term —
  D4 of BK-51 already showed that for TILE_H).
- GH-16 tick interaction (a tick firing between arm and trigger) not
  probed; TIMER words stayed 0.
- Non-blocking smoke: the whole probe requires a live GPU (wgpu); on a
  GPU-less runner every leg fails at device acquisition — this is a
  known non-gating smoke lane for any CI adoption.

## Probe defects (disclosed)

1. Draft vector target: first three drafts pointed KFAULT_PC at slot
   (3,1)/(0,1) while `:payload` actually lands at instruction index 7
   (slot (7,0)) for a 6-instr main + HALT — the trap correctly vectored
   to the WRONG slot I had chosen and halted on an unknown-opcode pixel.
   Caught by single-step tracing (dbg_ek1_wgsl_draft6_af3e.py: pc stops
   at (0,1) with running=0, output empty) and bake dumps (draft5/8);
   PAYLOAD_PACKED corrected to 7 (draft7 proved the fix on-device).
   Artifacts kept: dbg_ek1_wgsl_draft{2..8}_af3e.py + dbg_assemble_d1.py
   (in /tmp for the standalone assembler dump).
2. Draft D2 used bake_image(data_words=...): the baker PREPENDS 3 init
   STs after :__entry, and those seed stores are themselves out-of-box →
   E-K1 fired at step 3 with kf=0 before the arm ran (dbg draft8 bake
   shows the 3-instr shift). Fix: host-side RAM seeds only (run_prog
   writes ram[200] directly); the program shape stays 6-instr main.
3. S1_door_mode_free substring check is buggy (see S above); superseded
   by direct source read of :443-444 + D3 behavior. Kept in output with
   its false value for transparency.

## Files this tick (all untracked; no tracked file touched)

- .builder_queue/probe_ek1_vector_hijack_wgsl_af3e.py (probe)
- .builder_queue/dbg_ek1_wgsl_draft{2,3,4,5,6,7,8}_af3e.py (defect
  artifacts; draft1 superseded by draft7 in place)
- .builder_queue/RESEARCH_ek1_vector_hijack_wgsl_af3e.md (this receipt)
- systems/GLYPH_BACKLOG.md BK-55 row (1-line append)
- .builder_queue/PRODUCT_LANE_STATE.md ledger entry
