# BRIEF: BM-401..404 — Bare-Metal Rung 4 (scale: ≥64 KB payload, loader-side decode)

## Title
Bare-Metal Pixel Boot Ladder, Rung 4 — prove the rung-2 loader-side decode
mechanism at ≥64 KB payload scale under the same gate discipline. Full
roadmap: `tools/bare_metal_poc/ROADMAP.md` (source of record for the ladder).

## Authority (user ask, in-channel 2026-09-17)
"lets make a roadmap for this" → roadmap authored; then "lets get the builder
to process this roadmap". This brief + the BM-401 row in
`systems/GLYPH_SELF_HOSTING_ROADMAP.md` are that ask's implementation. Jericho
authorized this loop working the visual_audio repo on the standing builder
delegation; the roadmap itself was authored in-channel this same session.

## Spec pointers
- `tools/bare_metal_poc/ROADMAP.md` — Rung 4 section (tasks BM401-BM404,
  success criteria). Tasks may be renumbered BM-401..BM-404 in receipts; the
  four deliverables are fixed.
- `tools/bare_metal_poc/rung2/` — the base: `stage1.asm` (MBR loader),
  `stage2.asm`, `rung2_codec.py`, `run_gate2.sh`. Rung 4 extends this
  pattern; do not redesign it.
- `tools/bare_metal_poc/rung3/ANCHORS.md` — machine anchors, measured:
  128 MiB RAM, E820 7 entries, ≤~500 KB conventional budget, Path A decided.
- `tools/bare_metal_poc/RECEIPT.md` — rung-1 findings (COW journal; "corrupt
  → fail needs the failure SPECIFIED").

## WHERE YOU ARE
Main checkout `/home/jericho/projects/zion/projects/visual_audio`, branch
`glyph-transpiler-autoloop`. The entire `tools/bare_metal_poc/` tree is
currently UNCOMMITTED (untracked). This row's work lands INSIDE it and
commits the rung-4 subtree; landing the REST of the tree is TASK_BM001,
explicitly HOLD for Jericho's verbatim ratification — do not `git add` the
other rungs' sources/receipts as part of this row.

## MEASURED STATE (do not re-derive; verify only what you touch)
- Rung-2 gate: GATE PASS ×2 consecutive; 144 B payload; CKSUM=4541;
  RED-A pixel corruption → `GATE=FAIL SUM=4640` (host arithmetic agrees);
  RED-B 55AA destroyed → 0 serial bytes; boot-to-receipt 0.082 s (TCG).
- Rung-3 probe: `EXT88=FC00`, `E801A=3C00 E801B=06FE` (=128 MiB),
  `E820=0007` entries from real mode.
- QEMU 8.2.2 + nasm + python3 (PIL 10.2.0, numpy 1.26.4) present on host.
- Tools are cheap here: gate runs take seconds, not minutes.

## Operational traps (each paid for once — cost noted)
1. E820 SMAP magic is `0x534D4150`. Byte-reversed → SeaBIOS rejects every
   call silently (`E820=0000`). Cost: one full debug cycle (rung 3).
2. nasm: `%%` local labels only inside `%macro`; bottom-of-file data labels
   attach to the last NON-LOCAL label, not `start:` — use non-local names
   for data (rung-1 `msg1` convention). Cost: one assemble-fail cycle.
3. RED legs must SPECIFY the failure. Corrupting a byte that assembles to a
   same-length NOP still EXECs (rung-1 RED-A). At 64 KB scale pick the
   corrupted pixel so the effect is a known CRC mismatch — assert the
   computed-vs-expected values, never "it failed somehow".
4. `qemu-io -P` takes DECIMAL patterns (`-P 90` writes 0x5A). Cost: a wrong
   corruption theory in rung 1.
5. SeaBIOS IDE requires a writable disk; keep the writable-raw + frozen-PNG
   archive pattern from rung 2 (`bake` re-derives raw from PNG).
6. Context economy: run gates as `bash rung4/run_gate4.sh 2>&1 | tail -30`.
   The medium is 64 MB+ raw — never cat/hexdump it wholesale; use the codec
   tooling for byte probes.

## Scope
POSITIVE (exclusive write set):
- `tools/bare_metal_poc/rung4/` (new directory — everything in it)
- `tools/bare_metal_poc/ROADMAP.md` (status-cell updates only)
- `systems/GLYPH_SELF_HOSTING_ROADMAP.md` (BM-401 row state cell only)
- `tools/bare_metal_poc/.gitignore` (new, for rung artifacts)
- `.builder_queue/brief_bm_rung4_scale.md` (this brief; corrections only)
NEGATIVE (must-not-touch):
- `voicebook/`, `.rts/`, `rs_fixtures.json` (AGENTS.md protected assets)
- `tools/bare_metal_poc/rung2/`, `rung3/`, rung-1 files (reference only —
  extend by copy into rung4/, never edit in place)
- Any other roadmap row, ledger addendum, or maildrop state
- The rest of the untracked bare_metal_poc tree (TASK_BM001 is HOLD)

## Tasks
1. **BM-401** `rung4/stage1.asm` + `rung4/stage2.asm` + codec: stream a
   ≥64 KB stage2 through the EDD AH=42h chunk loop into a segment window,
   scatter de-interleave streaming, sum/CRC gate, jump only on PASS.
   Unreal mode ONLY if windowing proves insufficient — the receipt must
   state which shipped.
2. **BM-402** Integrity gate v2: build-time CRC32 in `stage1_const.inc`
   (rung-2 twin pattern), checked before control transfer; refusal prints
   computed AND expected CRC. (sum16 may stay as a cheap pre-filter.)
3. **BM-403** Performance baseline: boot-to-receipt wall time at 64 KB and
   256 KB payloads; effective decode KB/s; recorded in
   `rung4/RECEIPT_RUNG4.md`. No target — this rung SETS the baseline.
4. **BM-404** `rung4/run_gate4.sh`: build+encode → host roundtrips
   (bake/decode byte-identical) → GREEN → RED-A (specified CRC refusal,
   host arithmetic cross-check) → RED-B (55AA → zero exec) → scaled
   absence probe (payload windows not contiguous on medium) → RE-GREEN
   byte-identical. Then `rung4/RECEIPT_RUNG4.md` with every number, and
   status-cell updates in both roadmaps.

## Gates (RED-first)
- Every RED leg starts RED by construction: verify the corrupted run
  REFUSES before the fix exists — at 64 KB the refusal must name the CRC
  delta, and the host-side recomputation must agree with the guest's.
- Non-vacuity: the gate must fail if the checksum check is neutered
  (spot-verify by locally tampering EXPECTED_SUM once, observing RED-A
  style refusal, restoring).
- GREEN ×2 consecutive from clean before any commit; both runs' serial
  excerpts in the commit body (rung-2 receipt discipline).
- Run from `tools/bare_metal_poc/`: `bash rung4/run_gate4.sh` → GATE PASS.

## DONE WHEN
- `rung4/run_gate4.sh` → GATE PASS ×2 consecutive (pasted in commit body).
- `rung4/RECEIPT_RUNG4.md` carries: which address mode shipped, CRC32
  refusal evidence with host cross-check, absence-probe counts, 64 KB and
  256 KB decode timings, honest boundaries (what was NOT verified).
- BM-401 row state cell updated with commit hash; roadmap Rung 4 marked
  with measured numbers; commit lands on `glyph-transpiler-autoloop`.

## STOP-and-file-defect hatch
If real-mode windowing cannot reach 64 KB without unreal mode AND unreal
mode misbehaves under SeaBIOS (or any design fork beyond "extend rung 2's
pattern" appears), STOP: write the RED evidence to
`.builder_queue/REPAIR_PENDING_bm401_addressing.md`, leave the row ⏳ with
a defect note, and report. Do not invent a Path B pivot inside this row.
