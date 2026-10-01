# RESEARCH — the WGSL twin reproduces the fence family's ST-anchored consult:
# walk_ld is fence-blind ON THE GPU, measured on-device (BK-48 proposal)

**Tick:** 2026-09-27 ~04:5x CDT, builder cron af3e62239ce2. Trigger: PHASE 1c —
ledger STATUS ACTIVE, claim queue EMPTY (all items landed, QUEUE_STATE.json has
zero non-landed rows), no RULING newer than HEAD 9e8b1bc0 (newest RULING
mtimes 2026-09-22, all pre-dating the last ten landings), tracked tree clean
at claim, monitor CLAIM_PENDING queue=0 stall_tier=0. One research item per
tick; nothing engine-side landed this tick.

Rule-5 (no re-research) check: BK-38's WGSL twin caveat is "same gap BY SOURCE
READ (not probed on-device)" — no existing RESEARCH_*.md or backlog row
measures the WGSL fence posture on-device. This tick converts that caveat into
a measurement for the LD/ST pair. It does NOT re-measure the oracle (BK-38's
CPU legs stand as landed).

## The question

The whole fence family (BK-38..BK-45) is convicted in the Python oracle with a
shared root cause: `_addr_in_box` is consulted at exactly one execute site
(ST, glyph_isa_v2.py:1041). Every WGSL row carries the same caveat — "twin has
the same gap BY SOURCE READ (not probed on-device)". Does the WGSL twin,
executing on the RTX 5090 through the real compute pipeline, actually reproduce
that posture — or does it diverge (e.g. walk_st's E-K1 arm behaving differently
on-device, or the fence being tighter/looser than source reading suggests)?

## Method (what was measured/read, with path:line)

Probe: `.builder_queue/probe_wgsl_fence_twin_af3e.py` (untracked, research
artifact). Harness = `GlyphRunner`'s real WGSL path internals
(tools/glyph_gpt/runner.py:135-176: same buffers, same
`build_shader(OpcodeMapV2())`, same dispatch loop), extended probe-only with a
seeded `cpu.mode` (run_wgsl always starts mode 0=SUPER; there is no mmio/mode
seed parameter — documented probe posture, not a landed API).

- Box armed via box_mmio words 3/4 = [300, 500) (BOX0_LO_WORD=8195,
  BOX0_HI_WORD=8196, wgsl_glyph_isa_v2.py:209-210; the shader's
  `addr_in_box` compares BYTE addresses — `addr << 2` at walk_st, :451).
- Canary 0x0BADF00D seeded at word 200 (outside the box), via the `ram`
  binding (binding 5, wgsl_glyph_isa_v2.py RAM_WORDS=16384).
- S legs: line-pinned source reads of walk_ld / walk_st bodies.
- Determinism: full probe output byte-identical across 3 runs, md5
  658a55330c8c4b3cf143b30ccca6eda4. Device: NVIDIA RTX 5090 Laptop GPU
  (nvidia-smi -L), wgpu default adapter.

## Findings (measured)

1. **S1 — walk_ld has ZERO `addr_in_box` references** (count = 0 over the
   walk_ld→walk_st span, tools/wgsl_glyph_isa_v2.py:351-405). Its only
   box awareness is the SUPER bypass for the MMIO range — never a fence
   check. Same class as the oracle's LD (BK-38).
2. **S2 — walk_st consults the fence in exactly one arm**: the unpaged-RAM
   branch `if (is_super || addr_in_box(addr << 2u))` (:451) — the precise
   twin of the oracle's single consult at glyph_isa_v2.py:1041. (The
   probe's crude S2 counters read 0 because they counted the whole body
   including the MMIO branch; the string leg
   `S2_walk_st_is_super_or_in_box=False` is likewise a probe artifact —
   the actual source line is `if (is_super || addr_in_box(addr << 2u)) {`
   at :451, verified by direct read. Counting bug in the probe's S2 legs,
   NOT in the device legs; recorded rather than silently "fixed".)
3. **D1 — USER LD from out-of-box word 200 READS the canary on-device**:
   r5 = 195948557 = 0x0BADF00D, and the follow-up ST carried it into
   in-box word 100 (ram_dest = 195948557). halted=True, faulted=False,
   mode stayed USER (mode_final=1). **The cross-fence read + in-tile exfil
   shape of BK-38's oracle probe reproduces on the GPU, clean exit.**
4. **D2 — the E-K1 ST control fires on-device**: USER ST of 0x1234 to
   out-of-box word 200 did NOT land (ram_canary unchanged at 0x0BADF00D,
   no 0x1234 anywhere), mode dropped to SUPER (mode_final=0 — the KFAULT
   vector ran with KFAULT_PC=0, so PC semantics here are probe-posture).
   The ST fence is real on the GPU.
5. **D3 — SUPER LD from the same word reads fine** (r5 = 0x0BADF00D,
   mode_final=0): the LD consult is not "missing everywhere", it is
   absent-by-design for the same mode-gated shape as the oracle.

## Verdict

The WGSL twin is **structurally faithful** to the oracle's fence posture:
one ST-anchored consult (wgsl_glyph_isa_v2.py:451), LD fence-blind
(:576 calls walk_ld with no box consult anywhere in walk_ld). Every WGSL
"source-read" caveat on BK-38/39/40/42/43 is now MEASURED for the LD/ST
core: the family's shared root cause extends to the GPU twin, and the
sequenced engine commit that lands the fence family should treat
`walk_ld` (:351) and `walk_st` (:407) as its second consult site — the
fix is NOT Python-only. Not probed this tick: PARALLEL_ST/PUSH/CALL in
the shader (BK-39 class; the shader's `_OPCODE_ORDER` may not even carry
them — ENG-1 unknown-opcode halt, :851-862), syscall handlers (BK-40/42/
43 — Python-only by construction, source-read stands), KSYS_PC MMIO
self-arm (BK-41 — needs the E-K2 dispatch leg on-device).

## BK-48 (proposed backlog row)

**Title:** WGSL twin fence leg: add LD/ST device-level fence assertions to
the sequenced fence commit (walk_ld has no box consult on the GPU —
measured, not just source-read).

**Gate spec:** `tests/test_bk48_wgsl_fence.py` — L1: seeded-USER WGSL LD
from an out-of-box word returns refused/faults (RED today: value lands,
r5==0x0BADF00D); L2: the exfil shape blocked — LD out-of-box then ST
in-box must not deliver the value (RED today: ram_dest==0x0BADF00D); L3:
SUPER LD control reads fine; L4: USER ST out-of-box control still E-K1
(green today, must stay green); L5: non-vacuity — neuter the new walk_ld
consult in the shader → L1/L2 fire; L6: family — the fence commit's
Python legs (BK-38..43 gates) green. Prereq: lands IN the BK-38..45
sequenced engine commit (same review), blast radius
tools/wgsl_glyph_isa_v2.py only. RED-first is free: this probe IS the
RED (r5 lands today).

**Numbers discipline (rule-1 note):** every number in this receipt is a
structural datum (source-line counts, register/RAM word values, run
counts, one md5 over 3-run output) — no rate, ratio, or cost is cited,
so floors_authoritative.json does not attach. The md5 and word values
are re-derivable in one command:
`python3 .builder_queue/probe_wgsl_fence_twin_af3e.py | md5sum`.
