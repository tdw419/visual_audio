# RULING_defect29_tile_abi_retire — the 16×16×4 tile ABI is RETIRED, not pending

**Status:** RULED 2026-09-14 — Option 3 (retire) adopted; landed in the commit carrying this file.
**Seat basis:** standing defect-fix-policy delegation (reaffirmed 2026-09-14) plus an explicit
"you lead" grant from Jericho given this session in response to a written summary of exactly this
decision. Test retirement is normally seat-reserved; this named action is covered by the grant.
**Decision:** the 5 strict-xfail legs in `tests/test_cross_modal.py` demanding
`cross_modal.extract_tiles` / `text_to_tiles` / `tiles_to_audio_byteperfect` /
`tiles_to_audio_semantic` are RETIRED — removed from the file, with this ruling as the record
(this is the ruling the standing no-delete-without-one rule requires; nothing goes silently green).
The 3 CLI legs (`from-text` / `from-image` / `from-audio`) exercising `tools/cross_modal.py`'s
tracked, live MFSK transport remain untouched and remain the file's whole collected set.
**Reasoning (all measured 2026-09-13 in DEFECT-29):** the demanded ABI exists in zero committed
revisions (`git log -S` 0 hits; 0 providers); there is no product intent for a standalone
PPM→audio tile slicer; the native pipeline already owns image↔audio transport (spatial
`.glyph`→`.rts.png`; `speak.py` MFSK/phoneme). The xfail-as-forcing-function posture from
DEFECT-28 file (1) was interim; with no intent to build, the legs only misstate the suite
(8 collected ≈ 5 capabilities nobody is building).
**Restore path:** if product intent for the tile slicer ever materializes, do NOT resurrect the
removed bodies — write fresh legs against the real ABI (the July 2026 contract — 16×16×4 RGBA
tiles, no-PIL PPM — was never a validated design target). The removed legs remain in git history
at the pre-ruling commit.
**Gate:** `pytest tests/test_cross_modal.py -q` → 3 passed / 0 xfail / 0 phantom legs collected;
`grep -c xfail tests/test_cross_modal.py` → 0. Non-vacuity of the retirement is structural:
`--runxfail` previously failed all 5 (`RECEIPT_DEFECT28_1_CROSS_MODAL_XFAIL.md`), and this action
removes marker AND body together, so no leg can silently xpass afterward.
**Ticket sync:** `DEFECT-29_cross_modal_tile_abi_missing.json` OPEN→CLOSED(retired) in the same
commit; SUITE-FIX-1 roadmap status cell appended (row open only for leg 1b, BLOCKED-ON-DESIGN).
