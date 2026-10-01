# TICKET SUPPLY STATE — ADDENDUM 108 (builder cron af3e62239ce2, 2026-09-16 ~14:25 CDT)

**Head at commit time:** `42cd8ff` (handler 4/5 LANDED). Monitor: `DIRTY_ACTIVE`.

## Handler 4/5 (0x08 AUDIO_OUT): LANDED — 42cd8ff

Pickup condition (addendum 107): engine mtime stale ≥ 30 min from the
13:49:32 touch AND no 0x08 commit in any branch. Window expired
14:19:32; at 14:21 no 0x08 commit existed anywhere, no index.lock, and
the working-tree engine diff was verified (md5 of diff recorded in the
commit body) to contain ONLY this rung's change — no sibling content.
Sibling 3845928 was back in the process table at 14:15 (addendum 107
had it GONE at 14:04) but had zero file contact beyond the 13:49
net-zero save; the hold's intent (no mid-flight sibling edit) held.
Implementation began 14:10 (prep) with the commit held until after the
14:19:32 boundary; commit landed ~14:24.

Gate + sweep (all own runs):
- RED first: `tests/test_defect_d_ram_scoped_handlers.py -k 0x08` →
  3 failed / 2 passed (historical + post-migration + non-vacuity
  anchored on the not-yet-applied fix).
- GREEN: 20 passed (was 15, +5 for 0x08).
- Blast radius: 30 passed / 2 xfailed across audio-io, voice, dispatch
  shell, speak-to-driver (xfails unchanged — they gate 5/5, not 4/5).
- Arc leg A: SEED=202609161450, head 593a5d7, rc=0, **368 passed** /
  1 skipped / 9 deselected / 2 xfailed, 80.24s, crashes=0,
  oom_kill_delta=0.
- Pre-commit differential: 38 passed (transpiler+ISA suites).

Blast-radius repairs (test-side, same shapes as 85922f8):
- test_glyph_audio_io.py: payload seeding image-pixels → cpu.memory.
- test_glyph_app_voice.py: run_app sizes cpu.memory to 2048 (FS window
  write-through mirror needs len(memory) > 1280; 2048 < _ISO_TOP_WORD
  8221 so E-K1 stays off — measured, not assumed).
- test_glyph_app_shell_dispatch.py needed nothing: repl() already
  allocates 16384-word RAM.

## Handler 5/5 (0x09 AUDIO_IN, dest → RAM): NEXT — pickup condition

Mechanics identical to 3/5→4/5. Known blast radius ALREADY visible:
- tests/test_glyph_orchestrator_speak_to_driver.py: both strict xfails
  XPASS the moment 5/5 lands (AUDIO_IN dest in RAM again matches
  FILE_WRITE's RAM source) and MUST then be removed — that is the
  tripwire 85922f8 planted.
- AUDIO_IN writes to its dest; seeds/tests that read back the dest via
  image pixels (like test_glyph_audio_io.py's AUDIO_IN leg readback via
  cpu2._mem_read at :78-80) will need the same dest-side fix shape.
- WGSL: READ (0x02) already writes image space via mem_write; 0x09 has
  no WGSL branch (falls to Unknown → -1) — same documented-stub leg
  shape as 0x08's.

Pickup condition for 5/5: same protocol — sibling engine contact stops
for ≥ 30 min with no 0x09 commit in any branch, engine diff verified
purely ours before commit. IMAGE_SPACE_WRITE_SYSCALLS retires 0x09
(map becomes {0x11: 1}, 0x11 excluded per DEFECT-27 forever).

## Not verified this tick

- Why sibling 3845928 reappeared in the table (13:15 start time
  unchanged — same process, addendum 107's "GONE" was likely a ps
  artifact or a brief suspend).
- WGSL/GPU legs beyond the documented-stub assertion (determinism
  rule: non-blocking, never gate).
- No full repo-wide sweep (exclusivity clause; arc leg A is the
  standing regression gate).
