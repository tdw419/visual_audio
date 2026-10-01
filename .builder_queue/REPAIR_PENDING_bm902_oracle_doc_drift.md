# REPAIR_PENDING_bm902_oracle_doc_drift.md

**Filed:** 2026-09-18, builder cron af3e62239ce2 (BM902 field-plan step)
**Severity:** documentation-only; oracle ARTIFACTS verified sound
**Discoverer:** measured re-read of `rung9/oracle_zp_leg0.bin` while writing
`rung9/BM902_FIELD_PLAN.md` (this ticket's sibling commit).

## Symptom

`rung9/ORACLE_BOOT_PARAMS.md` low-field table disagrees with the frozen dump
it documents:

| Field | Doc says | Measured bytes (leg0, pinned c3120d8e) |
|---|---|---|
| root_flags (0x1f2) | at 0x1f6, value 0x0004 | 0x1f2 = `01 00` → 0x0001; 0x1f6 is syssize byte 2 (0x04) — the doc read syssize's byte as root_flags |
| ram_size (0x1f8) | 0xfffc0000 | `00 00 ff ff` → 0xffff0000 |
| vid_mode | "0xaa44aa00 region" at 0x1fc | vid_mode is at 0x1fa = 0xffff (normal); 0x1fc is root_dev = 0x0200 |
| syssize (0x1f4) | 0x4152a paras | matches (`2a 15 04 00`) — doc value right, but adjacent misparses above |

The canonical protocol layout (setup_sects 0x1f1, root_flags 0x1f2, syssize
0x1f4, ram_size 0x1f8, vid_mode 0x1fa, root_dev 0x1fc, boot_flag 0x1fe) fits
the measured bytes exactly. The doc's table appears to have been written with
root_flags shifted +4.

## Why this is only a doc problem

- The dumps sha256-match their pins (`oracle_pins.txt`, re-verified this run:
  c3120d8e… / 30cd829f…), so the ARTIFACTS are the frozen truth.
- BM902's differ compares bytes at fixed offsets; it never consumes the doc's
  field values. The field plan's whitelist is offset-based.
- Doc is must-not-touch under `brief_bm902_stage2_handoff.md`
  ("oracle_* dumps and ORACLE_BOOT_PARAMS.md … never edit").

## Requested ruling (cheapest first)

1. (a) Authorize a doc-only commit fixing the five table rows in
   `ORACLE_BOOT_PARAMS.md` to byte-true values (10-minute fix; dumps and pins
   untouched). Field plan already records the byte-true values, so nothing
   downstream is blocked either way.
2. (b) Leave the doc as-is; BM902_FIELD_PLAN.md is the corrected reference
   for all BM902+ work (costs: future readers get the wrong field offsets
   from the doc).
3. (c) Regenerate the doc from the dump with a script (most work; only worth
   it if more drift is suspected elsewhere in the table).

**Not blocking:** BM902 step 2/3 (stage2 + differ gate) proceeds under the
field plan's byte-true values either way.
