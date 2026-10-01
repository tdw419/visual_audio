# RESEARCH — GLYPH_FS_ALLOW attack-surface asymmetry MEASURED: under the
# identical empty env, 0x13 FILE_LIST is REFUSED while 0x03 FILE_WRITE
# writes an arbitrary host file and 0x04 FILE_READ exfiltrates host file
# content into (out-of-tile) guest RAM — the containment posture is
# inverted relative to its own landing rationale (BK-44 candidate)

- **Builder:** af3e62239ce2 (Glyph OS event-chain cron, Phase 1c research tick)
- **Date:** 2026-09-27 (~02:3x CDT)
- **Tree:** HEAD d61dc186251f5d4de0c0a492624322952a4f8381 (my BK-43 research
  tick) at probe start; probe landed modules only (no engine edits); tracked
  tree clean at claim; no sibling writes to engine sources.
- **Question:** the explicitly-open honesty item in
  RESEARCH_fw_exfil_path_read.md:115-117 — "no GLYPH_FS_ALLOW-style
  allow-root check exists for 0x03 (unlike 0x13 FILE_LIST, :1779-1786) —
  this is a source-read observation, not a measured attack-surface diff."
  Not answered by any existing RESEARCH receipt or backlog row: BK-42
  measured write-to-arbitrary-path but never in A/B contrast with 0x13
  under the SAME env in one process; BK-40's 0x04 leg ran under
  GLYPH_FS_ALLOW=/tmp (the env's relevance to that arm was never isolated —
  and by source-read it has none to isolate, which is the defect).

## Method

Probe `.builder_queue/probe_fs_allow_asym_af3e.py` (untracked, landed
modules only), harness = the landed item-29 containment path itself:
`GlyphProcessTable.spawn(image, tile=(5,0,8,8))` (tile rows 5..11 x cols
0..7, W_MEM=32; first out-of-tile word 168 = row 5 col 8). Handlers under
test: 0x03 SYSCALL_FILE_WRITE (`tools/glyph_isa_v2.py:1462-1499`), 0x04
SYSCALL_FILE_READ (`:1506-1551`), 0x13 SYSCALL_FILE_LIST
(`:1740-1804`, allow consult at `:1781-1785`); allow-list authority
`_get_fs_allow_roots` (`:575-590`) with the landing rationale
"enumeration is the more invasive primitive, it must not be cheaper to
reach than RUN" (`:577-579`).

GLYPH_FS_ALLOW is popped/set explicitly around every `wait()` and restored
after (env is process-global — the A/B legs must share one process to make
the contrast a real measurement, so env mutation is the instrument and its
restore is the hygiene). Verdicts from HOST FILE CONTENTS + in-RAM syscall
return codes (rc parked at in-tile word 198 by the program itself), never
handler stdout, never task exit codes alone.

Fixtures: private dir `/tmp/b7d` with exactly one file `k1`
(deterministic listing); `/tmp/b7w` unlinked + asserted absent before
every run; `/tmp/b7r` = b'AUTUMN'; rc and dest words zero-seeded.

Determinism: 3 internal runs, all 5 cases byte-identical, **md5
68b44ea7200b3473a45277636b4e4874**. Re-derive:
`python3 .builder_queue/probe_fs_allow_asym_af3e.py`.

## Findings (all quantities structural — file bytes, in-RAM return codes, fault_addr, line numbers; NO rate/latency/cost claims, rule-1 floors do not attach)

1. **list_denied — 0x13's containment is live.** GLYPH_FS_ALLOW unset:
   FILE_LIST '/tmp/b7d' -> syscall rc -1 (word 198 = ffffffff), dest words
   stay zero. The BK-15 gate works as landed.
2. **fw_no_env — 0x03 writes an arbitrary host file with NO allow env.**
   Same task, same empty env: FILE_WRITE '/tmp/b7w', in-tile data 'WX' ->
   rc 0, host file contains exactly b'WX' (hex 5758). No root consult
   anywhere in the handler (`:1462-1499`).
3. **fr_no_env — 0x04 reads an arbitrary host file into OUT-OF-TILE RAM
   with NO allow env.** FILE_READ '/tmp/b7r' dest=168 (row 5 col 8, first
   word outside the tile) -> rc 6, 'AU' (4155) at words 168/169. Two
   defects in one leg: zero host-FS containment AND the BK-40 fence-blind
   dest arm, re-measured here with the env variable explicitly isolated.
4. **list_allowed — non-vacuity control.** Same listing program with
   GLYPH_FS_ALLOW=/tmp/b7d -> rc 1, dest = b'k1\0'. Leg 1's refusal is the
   containment firing, not a broken harness or an unspawnable task.
5. **ctl_st_out — E-K1 baseline intact.** Plain ST to out-of-tile 168
   traps: EXIT_FAULT, fault_addr = 672 = 168*4, mode -> SUPER.

**The measured inversion:** the posture's own rationale says enumeration
must NOT be cheaper to reach than the destructive primitives; measurement
shows the opposite — the primitive that OVERWRITES host files (0x03) and
the one that EXFILTRATES host file CONTENT (0x04) are reachable with the
env empty, while the one that only NAMES files (0x13) is refused. A
confined USER task under the default env can destroy host state and copy
host secrets into guest RAM, but cannot list the directory it is
destroying.

## Verdict

The asymmetry is measured, not inferred. BK-44 filed to
systems/GLYPH_BACKLOG.md: extend the `_get_fs_allow_roots` consult to 0x03
and 0x04 (deny-by-default like 0x13), or re-scope the BK-15 containment
claim. The fix likely shares the BK-42/BK-43 `_read_path` consult site and
lands in the same sequenced engine commit (prereq BK-42 + BK-43). Research
landed NO engine code.

## Probe-hygiene disclosure (caught BEFORE any finding was recorded)

- Draft 1 (caught on read-back of the file, before the first run): two
  assembler-staging bugs — the byte value placeholder was not interpolated
  into the `LDI r6 %d` template (would have assembled literal `%d` or
  raised), and `stage_bytes` was passed a list of 1-tuples instead of
  ints. Both would have failed every leg at assemble time; fixed before
  any run.
- Geometry pre-check (the documented PARALLEL_ST write-through mirror
  trap): 9-byte staged paths = 27 staging instructions + 7 tail = 34 < 40,
  clear of mirror row 5 = instruction slots 40..47. Program length
  asserted by construction (paths <= 8 chars + NUL).
- Env-leak check: GLYPH_FS_ALLOW popped/restored in a finally block per
  leg; host fixtures unlinked in a finally block; no state left behind
  (verified: /tmp/b7w absent, /tmp/b7d removed after the run).

## NOT verified

- WGSL twin on-device (syscall handlers are Python-only; source-read only).
- 0x01 WRITE / 0x08 AUDIO_OUT / 0x09 AUDIO_IN path arms (same
  no-consult family by source-read; not probed).
- The VFS-attached twins (`vfs_write`/`vfs_read`/`vfs_list`, item-25):
  the probe ran with no VFS attached; whether the VFS layer re-implements
  or inherits the root check is unmeasured.
- The L1/L2 shell surface: `glyph_l1_shell.py` routes its file verbs
  host-side (source-read), so operator-facing verbs are not exposed to
  this asymmetry — NOT probed end-to-end this tick.
- Interaction with an armed KSYS_PC posture (BK-41 shape) — direct
  `_handle_syscall` branch measured, as in BK-40..43.
- Whether any landed fixture relies on un-root-checked 0x03/0x04 (the
  BK-44 gate's family leg checks that at landing time).

## Backlog candidate (filed as BK-44, systems/GLYPH_BACKLOG.md)

Gate: `tests/test_bk44_fs_allow_roots.py` — L1: 0x03 with env unset ->
refused/fault, host file absent (RED today: b'WX' lands); L2: 0x04 with
env unset -> refused/fault (RED today: 'AU' lands); L3: 0x13 env-unset
refusal stays green (BK-15 baseline); L4: all three arms succeed under a
leg-scoped allow root (non-vacuity: the fix must not brick the shell's
own L2 verbs); L5: ST out-of-tile trap control; L6: non-vacuity — delete
the new consults -> L1/L2 fire; L7: family — BK-15 + L2-files + BK-38..42
gates green; disclose whether any landed fixture relies on un-root-checked
0x03/0x04. Prereq: BK-42 + BK-43 (same sequenced engine commit; the fix
may share the `_read_path` consult). NOT claimable without Jericho per the
backlog header.
