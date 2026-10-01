# RESEARCH — WGSL twin fetch confinement (tick 10, the BK-67 NOT-proved sibling)

Builder: af3e62239ce2 · 2026-09-28 ~04:5x→05:1x CDT · Measured at HEAD 89f0444a
Probe: `.builder_queue/probe_wgsl_fetch_confinement_af3e.py`
Instrument: the proven BK-49/50/51/55 device harness — `run_wgsl`'s real
buffers + `build_shader(OpcodeMapV2())`, probe-only seeded `cpu.mode=1`
(USER), box [1200,1300) BYTES armed via mmio[3]/mmio[4]. RTX 5090, wgpu
compute. Canvas NOT consulted for evidence (geo-obs age 726,746s, tick 0 —
stale; host-side device harness is the instrument).

## Question

Tick 9 (RESEARCH_fetch_confinement_af3e.md, HEAD 2626466d) measured the
ORACLE side of BK-67 and left "WGSL twin (no tile harness, BK-51)" in its
NOT-proved list. Does the WGSL shader likewise fetch and execute code
pixels from anywhere in the image regardless of the armed box — and does
BK-49's measured fence-blind PUSH compose with a jump arm into arbitrary
code injection + execution ON THE GPU, USER end-to-end, no fault channel?

Twin scope note: the twin has NO tile predicate at all (BK-51, measured —
`addr_in_box` contains zero tile references), so the twin-side boundary
under test is the BOX one. The tile composition question remains an
oracle-side result (BK-66/67) plus BK-51's parity leg at landing.

## Source prediction (checked before device runs)

- Fetch: `main()` reads `load_pixel(x..x+3, y)` at wgsl_glyph_isa_v2.py:506-509
  with ZERO `addr_in_box` terms; the only consult in the file lives in
  walk_st (:451) / walk_ld's MMIO gate.
- Jump arms: JMPR :605, JMP :686, CALL, RET, CALLR, KJMP all set `next_pc`
  from raw packed pixel arithmetic with no consult and no bounds beyond
  the image-extent guard at :498-502.
- PUSH :636-638 is `mem_write` (image plane), unguarded — BK-49's measured
  primitive.

## Method / runs

3 pinned runs, stdout byte-identical md5 `b9ab21c8775cb170486595e3d0d346d1`,
results md5 `4940f4344fa679a1a70e8f244b30f4c0`. Verdicts from image/ram/
mmio READBACK BYTES, never stdout. Canary `0x0ADF00D` (same as tick 9);
injected opcode color resolved at runtime from `OpcodeMapV2().opcode_to_rgb("LDI")`
(15487056 = 0xEC5050), never hand-encoded. Bake `cols_instrs=8, min_rows=64`
(32 px/row scanline units, same discipline as the oracle probe).

## Findings

- **S1 (source):** fetch block `addr_in_box` refs = 0; JMPR/JMP/CALL/RET/
  CALLR each 0 refs + each sets `next_pc`; PUSH 0 refs + uses `mem_write`.
- **D1 (on-device, oracle F2's twin):** seeded-USER `LDI r15 (40<<16);
  JMPR r15` with the 4 canary-LDI pixels PRE-PAINTED at image row 40
  (OUT of the armed box [1200,1300) bytes → row-40 pixels are byte
  1280+, outside): exit clean, halted, 4 steps, **r10 = 0x0ADF00D**,
  mode stays USER (1), fault_addr_word = 0, injected opcode pixel
  readback = 15487056 = the real LDI color. The GPU executes out-of-box
  code pixels from USER with no fault.
- **D2 (on-device, oracle F3's twin):** full injection composition —
  seeded-USER program PUSHes the 4 canary-LDI pixels to row 50
  (r31 = base+1..base+4, pre-decrement → pixels base..base+3) through
  BK-49's fence-blind image-plane `mem_write`, then `JMPR r15` to row 50:
  exit clean, 16 steps, **r10 = 0x0ADF00D**, mode USER end-to-end,
  fault_addr_word = 0, injected opcode pixel readback = 15487056 =
  `real_ldi_color`. **Arbitrary code injection + execution on the GPU,
  no fence violation needed to trigger.** (r31 end = 1603 = base+3 —
  the PUSH sequence's own footprint, disclosed.)
- **C1 (E-K1 control):** plain seeded-USER ST to out-of-box RAM word 100
  → fault_addr_word = 400 (raw byte address, the BK-49-D4 shape), mode →
  SUPER (0), 3 steps: **the box arming is LIVE in the exact harness where
  D1/D2 execute out-of-box** — the probe is discriminating, the D-legs
  are a real gap and not a dead harness.
- **C2 (in-box control):** ST to byte 300 (inside the box) clean, no
  fault, mode USER — ordinary boxed work unaffected by the harness.

## Consequence

The twin REPRODUCES the oracle's tick-9 verdict on-device: the code plane
(image pixels) has NO fence on EITHER engine — the tile/box predicates
are DATA-plane only (oracle: `glyph_isa_v2.py:753-764` fetch; twin:
`wgsl_glyph_isa_v2.py:506-509` fetch + :451 being the sole ST consult).
The fence-blind PUSH composition (BK-39 leg 4 / BK-49 D1) closes into
arbitrary code execution on both engines in USER mode. The BK-38..57
sequenced fence commit family therefore CANNOT be Python-only OR
ST-only: the fetch + jump arms are the last unconsulted execute-side
surface family on BOTH engines, and BK-67's gate needs a twin leg.

## Probe defects disclosed (both caught BEFORE the pinned runs)

1. C1 v1's `fired` predicate expected a box-relative fault
   (`100*4-1200`, negative) — the twin's FAULT_ADDR register reports the
   RAW byte address (400), the shape BK-49 D4 already measured. Caught
   by the run-1 verdict showing `fired: false` alongside
   `fault_addr_word: 400` + `mode_final: 0` (fence clearly live);
   predicate fixed, then 3 pinned byte-identical runs taken AFTER the fix.
2. D2's scanline row width taken from the D1 bake dims (same bake
   parameters, but the coupling was implicit) — made explicit before
   evidence; the injected-pixel readback cross-check (== real LDI color)
   independently confirms the row arithmetic.

## What this does NOT prove

- The oracle side is unchanged (tick 9's result stands; this does not
  re-run it).
- Paged fetch (twin walk_ld's PTE-fetch fallback :384-394) — not probed;
  the twin's paged path is itself a measured gap family (BK-60/64/65).
- The tile predicate on the twin doesn't exist (BK-51), so no
  tile-scoped twin leg is possible until BK-51's term lands.
- No engine or shader code changed — probe + receipt + candidate row +
  ledger only. Rule-1 floors do not attach: numbers structural (word
  values, byte addresses, exit codes, md5s).

## Candidate row

Filed as **BK-68** to `systems/GLYPH_BACKLOG.md` (measured-completion
sibling of BK-67): BK-67's gate `tests/test_bk67_fetch_confinement.py`
grows twin legs — T-L1: seeded-USER twin JMPR to out-of-box pre-baked
code pixels → refused/faulted or (if the posture chooses confinement)
trap, RED today (D1's clean r10); T-L2: PUSH-written pixels + JMPR →
injected code must NOT execute, RED today (D2's canary); T-L3: C1 ST
rot-guard green. Posture decision (execute-confine PC vs code-plane box
vs spawn-pinned executable rows) is the SAME design-judgment already
flagged in BK-67 and must be decided once for both engines in the same
round — the twin leg takes that posture mechanically.
