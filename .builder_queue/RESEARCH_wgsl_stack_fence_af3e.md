# RESEARCH — WGSL stack path fence posture measured on-device (BK-49)

- 2026-09-27, builder af3e62239ce2, Phase 1c research tick
- HEAD at probe time: 8f5f2e47 (my BK-48 landing, 03:1x). Tracked tree
  clean at claim; no RULING newer than HEAD; queue empty (Phase 1c
  eligible); monitor fingerprint head-matched at tick start.
- Question: BK-48 (RESEARCH_wgsl_fence_twin_af3e.md) measured the WGSL
  LD/ST core on-device but left three caveats unprobed. This tick closes
  the push/stack-class one: is the WGSL PUSH/POP/CALL stack path
  (`mem_write`/`mem_read` via `addr_to_xy` onto the IMAGE plane,
  wgsl_glyph_isa_v2.py:635-659) a live cross-fence write channel on real
  hardware, the way the oracle's PUSH was measured in BK-39 leg 4?

## Method

- Probe: `.builder_queue/probe_wgsl_stack_fence_af3e.py` (untracked,
  landed modules only: bake_image, GlyphRunner, build_shader,
  make_cpu_state_array — no repo file modified).
- Harness: the BK-48 probe's device-leg harness verbatim (buffers,
  bindings, step loop) + one addition: readback of the mmio buffer so
  the E-K1 FAULT_ADDR word (8199, byte offset 7) is evidence, not
  inference. Box0 armed = byte addresses [1200,1300) via box_mmio words
  3/4. Mode seeded directly in the cpu state array (probe-only posture,
  same disclosure as BK-48: run_wgsl exposes no mode/mmio seed).
- Device: RTX 5090 Laptop GPU, wgpu default adapter. Determinism: 3
  full runs, stdout byte-identical, md5 5b70e65cac5acf4e502e2f161accc6fd
  (results JSON alone: md5 18cb02a8c73421d6ae3f4772da929b9e).

## Findings (measured)

1. S1 (source read): the PUSH, POP, and CALL dispatch arms contain
   ZERO `addr_in_box` references and route exclusively through
   `mem_write`/`mem_read` (image plane) — the E-K1 consult at
   wgsl_glyph_isa_v2.py:451 lives only in walk_st, which the stack
   ops never call. Structurally fence-blind BY CONSTRUCTION.
2. D1 (device): seeded-USER `LDI r31 500; LDI r4 0x0BADF00D; PUSH r4`
   with box [1200,1300) armed — address 500 is OUT of the box
   (byte-range check on addr<<2 = 2000... see finding 5). PUSH landed
   the canary at image address 499 (r31 pre-decrements): readback word
   0x0ADF00D (canary & 0xFFFFFF) at scanline (19,15), halted clean,
   mode stayed USER, fault_addr_word = 0. The value observed is
   11399181 = 0x0ADF00D exactly.
3. D2 (control): identical program with r31=1250 (IN box) — PUSH lands
   the same value at (1,1), clean, fault_addr_word = 0. The two legs
   differ ONLY in box membership; both behave identically ⇒ box
   membership has no effect on the stack path (the bypass), while the
   harness's box arming is proven live by D4.
4. D3 (exfil twin): image address 500 pre-painted with the canary via
   the initial image bake, seeded-USER `POP r5` from r31=500 — r5 read
   back 0x0ADF00D (11399181) from OUT-of-box image memory. The
   follow-up `ST r6(100) r5` was correctly REFUSED by the fence
   (fault_addr_word = 400 = 100<<2, mode→SUPER) — so on THIS twin the
   out-of-box exfil ST is caught; the cross-fence READ into a register
   is not. mode ended 0 (SUPER) because of the ST refusal, not the POP.
5. D4 (E-K1 control): seeded-USER plain `ST` to in-RAM word 100
   outside the box → fault_addr_word = 400, mode 1→0, ram[100]
   unchanged — the box arming and fence are LIVE in this harness
   (matches BK-48's D2). Therefore D1/D2's clean stack writes are a
   genuine bypass class, not a dead-harness artifact.

## Caveats disclosed

- PROBE-DEFECT (found and fixed before evidence taken): the first two
  draft runs used `img_word(500)` assuming mem_write stores at the
  raw address; PUSH pre-decrements r31, so the value actually lands at
  address 499. Runs 1-2 (md5 f38f8662ac02785182865754421b62e8 /
  c5bdc30bbe7f50b6d6273b329a90628f) reported img_word_500 = 0 and were
  re-leged to img_word_499 before any conclusion was drawn. Also
  fixed: an earlier IndexError from resolving addr_to_xy against a
  2-tuple shape, and an unpack bug in the D3 preseed pixel (the
  preseeded value itself was correct in all runs — verified by the
  POP readback).
- Oracle-side asymmetry NOT probed: whether the Python oracle's own
  PUSH (`_mem_write`, glyph_isa_v2.py:702-708) checks byte or word
  granularity against the box. BK-39 leg 4 measured an out-of-tile
  IMAGE-plane PUSH landing host-side, so the class exists on both
  engines; this probe did not re-measure the oracle.
- The D3 "ST refused" outcome is DOOR-DEPENDENT: had the exfil dest
  been INSIDE the box, the popped out-of-box value would have landed
  lawfully (BK-38's read + in-tile write shape). The stack path gives
  a USER task out-of-box READ+WRITE primitives; assembling a full
  exfil chain out of the box is blocked only by the (single) ST fence.
- Numbers structural (image words, register values, mmio words, run
  counts, md5s) — rule-1 floors do not attach.

## Verdict + candidate

The WGSL twin's stack path is a SECOND fence-blind write/read channel
on-device (PUSH writes, POP reads, CALL writes return PCs — all
image-plane, all USER-clean). BK-48's verdict extends: the sequenced
fence commit's consult sites are walk_ld, walk_st, AND the
mem_write/mem_read callers (PUSH :635, POP :639, CALL :648) — or,
cheaper, a consult inside mem_write/mem_read themselves gated to
USER mode (single site, but must not break kernel KJMP/entry stacks;
that posture decision belongs to the landing gate, not this probe).

Candidate filed as BK-49 in systems/GLYPH_BACKLOG.md (gate
tests/test_bk49_stack_fence.py: PUSH/POP out-of-box refusal legs +
in-box controls + D4 E-K1 control + non-vacuity + family; lands IN
the BK-38..45 sequenced engine commit; blast radius
tools/wgsl_glyph_isa_v2.py only).

Research landed NO engine or shader code: probe + this receipt + the
backlog row only.
