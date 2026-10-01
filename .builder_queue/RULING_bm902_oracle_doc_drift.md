# RULING — bm902_oracle_doc_drift (answers REPAIR_PENDING_bm902_oracle_doc_drift.md)

**Ruled by:** host Hermes, 2026-09-18 19:57 CDT, under the 2026-09-18 FULL
decision delegation (internal, doc-only — no reserves touched).
**Ruling:** Option (a) — doc-only commit fixing the five table rows in
`rung9/ORACLE_BOOT_PARAMS.md` to byte-true values.

## Reasoning

- The must-not-touch clause in `brief_bm902_stage2_handoff.md` protects
  ARTIFACT truth (dumps + pins, the frozen oracle). A prose table that
  misparses the artifact it documents is a reference bug, not protected
  state — fixing it STRENGTHENS the freeze.
- Option (b) rejected: fossilizes wrong offsets (root_flags at 0x1f2 not
  0x1f6, ram_size 0xffff0000, vid_mode at 0x1fa, root_dev at 0x1fc) for
  every future reader of the canonical doc.
- Option (c) rejected: five cells don't justify a regeneration script;
  revisit only if further drift is measured elsewhere in the table.

## Execution constraints (for the builder's doc-fix commit)

1. Fix ONLY the five table rows (+ any sentence that repeats a wrong value).
   No binary, no pins, no field-plan edits.
2. Byte-true source of truth = the pinned dumps (c3120d8e / 30cd829f), per
   the canonical layout in REPAIR_PENDING's own table.
3. Separate commit from all BM902 step 2/3 work; commit message cites this
   ruling file.
4. After the commit: re-verify `sha256sum -c` against `oracle_pins.txt`
   (must be unchanged) and re-run `bash rung9/run_oracle.sh` once (must
   stay GATE PASS) — proof the doc fix touched nothing downstream.
5. Close this ticket by appending the doc-fix commit hash to
   REPAIR_PENDING_bm902_oracle_doc_drift.md.

BM902 steps 2/3 proceed under the field plan's byte-true values either way,
as the ticket already noted.
