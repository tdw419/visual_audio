# TICKET SUPPLY STATE — ADDENDUM 109 (builder cron af3e62239ce2, 2026-09-16 ~14:55 CDT)

**Head at commit time:** `e898bc2` (handler 5/5 LANDED). Monitor: `DIRTY_ACTIVE`.

## Handler 5/5 (0x09 AUDIO_IN): LANDED — e898bc2. BACKLOG (d) IS COMPLETE.

Pickup condition (addendum 108): sibling last engine contact 14:07:13
(`tools/pxc1/src/lib.rs`; `virtio lib.rs` 14:05:59); 30-min window expired
14:37:13 with no 0x09 commit in any branch and no index.lock. Engine diff
verified (pasted in the commit body) to contain ONLY this rung's change.
Commit landed ~14:52; pre-commit hook re-verified twin sync + 38-test
differential (transpiler+ISA) green.

Implementation (identical shape to 0x04's dest side, a2b0ba4):
`dest` writes bounded-indexed into `self.memory`; OOR dest bytes dropped;
`IMAGE_SPACE_WRITE_SYSCALLS` retires 0x09 → map `{0x11: 1}` (0x11 excluded
per DEFECT-27 forever). Twins md5 `5c2e801c…` identical. WGSL: no 0x09
branch (Unknown → -1), documented-stub leg, same shape as 0x08.

Gate + sweep (all own runs):
- RED first: `tests/test_defect_d_ram_scoped_handlers.py -k 0x09` →
  3 failed / 2 passed (0.93s) on a stashed pre-fix engine.
- GREEN: 25 passed (was 20, +5 for 0x09), 0.91s. One authoring defect
  fixed in-flight: surgical-swap assertion needle
  `self._mem_write(image, dest_addr + i)` missing the real call's third
  arg `', byte_val'` — probe worked, assertion could never match;
  debugged by character-level zip of the mismatch window.
- Blast radius: 45 passed / 0 xfailed (audio-io, ram-pixel-space, voice,
  dispatch shell, speak-to-driver, handler suite).
  - test_glyph_audio_io.py: readback dest-side fix (image → cpu.memory).
  - test_glyph_ram_pixel_space_check.py: test_l1b flipped to
    post-migration must-NOT-raise (map entry retired); test_l1 keeps real
    image-space coverage via 0x11.
  - test_glyph_orchestrator_speak_to_driver.py: BOTH strict xfails
    XPASSed exactly as the 85922f8 tripwire predicted — chain
    AUDIO_IN→FILE_WRITE→RUN executed the spatially-written driver end to
    end (rc 0, marker written) — xfails REMOVED, legs live again.
- Arc leg A: SEED=202609161442, head 742ab44 (pre-commit, tree = head +
  5/5 diff), rc=0, **373 passed** / 1 skipped / 9 deselected / 2 xfailed
  (both pre-existing: test_defect23_pte_acceptance.py), 74.70s,
  crashes=0, oom_kill_delta=0, mem_peak=772198400.

## Backlog (d) final ledger

| Handler | Commit | Migrated side |
|---|---|---|
| 0x01 WRITE | fd24c76 | data (r2) reads RAM |
| 0x03 FILE_WRITE | 85922f8 | data (r2) reads RAM |
| 0x04 FILE_READ | a2b0ba4 | dest (r2) writes RAM |
| 0x08 AUDIO_OUT | 42cd8ff | data (r2) reads RAM |
| 0x09 AUDIO_IN | e898bc2 | dest (r2) writes RAM |

Standing gate `tests/test_defect_d_ram_scoped_handlers.py`: 25 legs
(5/handler). `IMAGE_SPACE_WRITE_SYSCALLS = {0x11: 1}` is terminal.
path_addr-side `_read_path` view-merge remains RUN2/GH-9 in-flight work
(explicitly out of scope for all five rungs).

## Next

- Roadmap census remains TOTAL=75 OPEN=0; backlog (d) was the promoted
  work item and is now done. No self-promotion of a new backlog item
  this tick — next rung requires Jericho's backlog triage or a fresh
  promotion scan next run.

## Not verified this tick

- WGSL/GPU legs beyond the documented-stub assertion (determinism rule:
  non-blocking, never gate).
- No full repo-wide sweep (exclusivity clause; arc leg A is the standing
  regression gate).
- Whether sibling 3845928 was idle vs. suspended during the window
  (file-contact protocol only measures mtimes/commits, per prior addenda).
