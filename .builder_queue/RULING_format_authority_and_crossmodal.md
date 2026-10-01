# RULING — two .rts.png formats + the cross_modal contract

**Date:** 2026-09-13 · **Seat:** orchestrator · reversible by Jericho
**Covers:** REPAIR_PENDING_defect28c_container_format_authority.md, DEFECT-28 file (1) cross_modal

## 1. Container formats → OPTION 1 (declare, name, document)

Format A (VCC 1 byte/pixel, Hilbert=byte index, exact round-trip) and
Format B (PXC1 boot, 3 bytes/pixel, LENGTH-LOSSY) are two distinct, deliberate
formats. DECLARE that, name them, and document it. No code change.

- The doc note MUST state the lossiness fact (Format B cannot round-trip a payload
  whose length is not a multiple of 3 — no length metadata), because that fact is
  WHY Format A is the only format allowed to satisfy an exact-round-trip contract.
- `docs/VIRTIO_BACKEND_GUIDE.md`: one line per format, writer and reader named.
- `tools/pixelrts_v2_converter.py` module docstring: state it emits the BOOT variant
  and is NOT VCC-compliant.
- Options 2 (signature/CLI widening on a tracked module) and 4 (adding a length
  header to the bootable layout) stay RESERVED to Jericho.

## 2. cross_modal → fix the real drift; xfail-with-reason the fantasy API

Measured: `extract_tiles` / `text_to_tiles` / `tiles_to_audio_byteperfect` exist in
NO committed revision (history has `extract_tiles_from_frame` in a different module;
`tiles_to_audio_byteperfect` has zero hits). The test is untracked, dated 2026-07-27.
So the 8/8 gate is unreachable without inventing a tile API.

RULED:
- Fix the GENUINE drift test-side: the CLI leg's `--output/--audio-output` vs the live
  `--output-dir`, and the live subcommand set `{from-image,from-audio,from-text}`.
- Re-point a tile leg at the LIVE API only where a real equivalent exists
  (`extract_tiles_from_frame`, `tools/pixel_dedup_optimized.py:45`).
- Where NO real equivalent exists (`tiles_to_audio_byteperfect`): mark the leg
  xfail/skip WITH A NAMED REASON + file a ticket. A missing capability is recorded
  as missing — it must not be silently green and must not count as a regression.
- FORBIDDEN: adding stub API to the module to satisfy the test (fabricating product
  surface for a phantom consumer), and deleting the test.
- Gate: the CLI drift legs flip FAIL->PASS; the capability legs carry the xfail
  marker + ticket id; no module API invented (diff shows consumers only).

## 3. NOT ruled here — DEFECT-27 (0x11 STORE_CODE address space)

The two candidate semantics (RAM word array via LD/PRT vs pixel space via
`_mem_read`) are an ABI/address-space decision. That is POLICY-CLASS by the
standing authorization matrix (`RULING_standing_authorization.md`), so it stays
with Jericho. Until ruled, the 2 legs stay open and must not be "fixed" by
choosing a space implicitly.

## Tickets this ruling answers (cited verbatim so the seat-blocker sensor clears them)

- `.builder_queue/DEFECT-28_suite_fix1_c4_drift_and_defects.md`
- `.builder_queue/brief_defect28f3_griffin_bin_contract.md`
