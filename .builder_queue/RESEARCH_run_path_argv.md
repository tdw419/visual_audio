# RESEARCH — 0x07/0x12 RUN arm measured: the fence-blind `_read_path`
# decoder SELECTS THE EXECUTED BINARY (allowlist check runs on
# attacker-assembled, out-of-tile bytes), and RUN2's argv args carry
# out-of-tile RAM through execve() with no consult (BK-43 candidate)

- **Builder:** af3e62239ce2 (Glyph OS event-chain cron, Phase 1c research tick)
- **Date:** 2026-09-27 (~02:2x CDT)
- **Tree:** HEAD 6677603bddbc9daa9cabe8d19d7d46532a38cde2 at probe start;
  probe landed modules only (no engine edits); tracked tree clean at claim.
- **Question:** the RUN family was the last unprobed arm of the fence-bypass
  family — left as "source-read inference only" by RESEARCH_fw_exfil_path_read.md
  (NOT-verified list + blast-radius note) and RESEARCH_syscall_fence_bypass.md:124.
  Unlike 0x03 FILE_WRITE, 0x07/0x12 DO have a GLYPH_RUN_ALLOW allowlist
  (deny-by-default, glyph_isa_v2.py:1576-1579 / :1723-1726), so the open
  question was whether that check actually holds from a confined USER task.

## Method

Probe `.builder_queue/probe_run_arg_af3e.py` (untracked, landed modules
only), harness = the landed item-29 containment path itself:
`GlyphProcessTable.spawn(image, tile=(5,0,8,8))` (tile rows 5..11 x cols
0..7, W_MEM=32; first out-of-tile word 168 = row 5 col 8), auto reaper row
30. Handlers under test: 0x07 SYSCALL_RUN (`tools/glyph_isa_v2.py:1567-1586`)
and 0x12 SYSCALL_RUN2 (`:1702-1738`); path decoder `_read_path`
(`:1381-1408`, the exact primitive BK-42 leg fw_path_read proved walks
out-of-tile). Host fixtures created/cleaned by the probe: `/tmp/r5` and
`/tmp/runr5r5` (/bin/sh runners writing `ARG1=[<argv1>]` to a fixed marker),
markers unlinked + asserted absent before EVERY leg. All verdicts from HOST
FILE CONTENTS (byte-compared), never exit codes. Runner body sourced from
`.builder_queue/probe_run_arg_af3e_runner_sh.template` (committed).

Determinism: 3 internal runs, all 5 cases byte-identical (results blob + file
contents), **md5 e238a3ab4ebbfbdbdb4f94dd45cfeb09**. Re-derive:
`python3 .builder_queue/probe_run_arg_af3e.py`.

## Findings (all quantities structural — file bytes, exit codes, fault_addr, line numbers; NO rate/latency/cost claims, rule-1 floors do not attach)

1. **run_path_smuggle — the allowlist check executes on OUT-OF-TILE bytes
   (allowlist defeated by the decoder it checks).** In-tile words 160..167
   staged `/tmp/run` (8 bytes, NO NUL in-tile); out-of-tile words 168..172
   seeded host-side with 'r','5','r','5',0. `_read_path` decoded
   `/tmp/runr5r5`, `os.path.realpath` + allowlist membership PASSED (that
   exact path was in GLYPH_RUN_ALLOW), `_spawn([path])` executed the runner
   (marker written, `ARG1=[]`). Which binary runs was decided by bytes the
   task cannot lawfully address: the fence-blind path read is the
   target-selection primitive for host EXECUTION.
2. **run2_argv_leak — out-of-tile RAM crosses execve() as ARGV.** 0x12 with
   allowed target `/tmp/r5` and arg1_addr=168 (OUT-of-tile) seeded
   'S','R','C','5',0: host marker contains exactly `ARG1=[SRC5]`
   (hex 415247313d5b535243355d). The handler's own comment says args are
   "data, not targets" (:1708) — no consult of any kind. Combined with leg
   1's shape, a confined task feeds an allowed runner BOTH its binary
   identity (via decoder smuggle) and attacker-chosen arguments (via argv)
   from out-of-tile memory.
3. **run_ctl_allow — non-vacuity control.** Same program, env set: marker
   written (`ARG1=[]`). The allowlist path is live; legs 1-2 are not
   vacuously green.
4. **run_denied — deny-by-default holds.** Env unset: refused ("not in
   GLYPH_RUN_ALLOW"), no marker. The 0x07/0x12 posture is STRICTER than
   0x03's (which has no allow-root check at all) — but leg 1 shows the
   stricter check is enforced on decoder-assembled bytes.
5. **ctl_st_out — E-K1 baseline intact.** Plain ST to out-of-tile 168
   traps: EXIT_FAULT, fault_addr = 672 = 168*4, mode -> SUPER.

**Blast-radius note (fenced speculation, not load-bearing):** 0x01 WRITE's
path argument and 0x08 AUDIO_OUT's sink share `_read_path`; 0x04 FILE_READ
takes both a path and a data DEST (BK-40 already measured the dest side).
Those are source-read inferences in the same handler family, NOT probed
this tick.

## Verdict

The RUN arm is measured open: the GLYPH_RUN_ALLOW containment for 0x07/0x12
checks a path string assembled by the same fence-blind decoder BK-42
convicted, and RUN2's argv path arguments have no consult at all. BK-42's
fix family ("every guest-influenced host or cross-tile access must consult
the box predicate") extends verbatim: `_read_path` consults the CALLER'S
box at :1393-1408 (one site covers all path-taking syscalls:
0x03/0x04/0x07/0x08/0x12/0x13), and RUN2's argv decoder (:1716-1719) is
covered by the same fix because it calls `_read_path` three times. BK-43
adds NO new consult sites beyond BK-42's `_read_path` one — it is the
measured motivation for fixing the shared decoder rather than only the
FILE_WRITE data loop.

## Probe-hygiene disclosure (all caught BEFORE any finding was recorded)

- Draft 1: 32-byte paths -> 103 instructions; PARALLEL_ST write-through
  pixel mirror (glyph_isa_v2.py:1291-1295) maps words 160..191 to pixel
  row 5 = instruction slots 40..47 — staging clobbered the program's own
  tail and only 13 path bytes landed (detected by the CONTROL leg failing;
  the BK-40/BK-42 documented trap class). No finding recorded off draft 1.
- Draft 2: `b"\x00"` literals escaped wrong in write_file (\x00 landed as
  literal backslash-x00), caught by the probe's own path-length/NUL
  asserts before any run.
- Draft 3: runner template wrote marker2 but control legs checked marker —
  control leg FAILED again, correctly, and the mismatch was found by
  testing the runner fixture standalone in /tmp. All exec-proving legs now
  check the one file the runner actually writes. Lesson: a failing CONTROL
  leg in this lane has now twice been the probe's own bug, not the
  substrate's.

## NOT verified

- WGSL twin on-device (syscall handlers are Python-only; source-read only).
- 0x01 WRITE / 0x08 AUDIO_OUT / 0x04 FILE_READ path arms (source-read
  inference only, same decoder).
- Whether the RUN arms behave differently under an armed KSYS_PC posture
  (BK-41 shape) — direct `_handle_syscall` branch measured.
- Whether any landed fixture depends on out-of-tile path/argv bytes
  (checked at BK-38..42 landing per family convention).
- The smuggle leg required GLYPH_RUN_ALLOW to contain the smuggled target's
  realpath — the attack ASSUMES an allowlisted near-collision path exists.
  That is the realistic posture (the operator allowlists their runners; the
  guest names a prefix-collision), but a fully attacker-chosen arbitrary
  binary path with an empty allowlist was NOT measured (deny-by-default
  holds there, leg 4).

## Backlog candidate (filed as BK-43, systems/GLYPH_BACKLOG.md)

Gate: `tests/test_bk43_run_path_fence.py` — L1: run_path_smuggle shape ->
out-of-tile path bytes must NOT complete the decoded filename (decode stops
at tile boundary: refuse/fault, one posture documented), RED today
('/tmp/runr5r5' executes); L2: run2_argv_leak shape -> argv decoder must
not read past the tile (empty/zero-length arg or fault), RED today
('SRC5' crosses execve()); L3: in-tile path + in-tile argv control stays
green (allowlist path live); L4: deny-by-default control stays green;
L5: ST out-of-tile trap control; L6: non-vacuity — neuter the shared
`_read_path` consult -> L1/L2 fire; L7: family — BK-38/39/40/41/42 +
item-29 gates green. Prereq: BK-38 + BK-39 + BK-40 + BK-41 + BK-42 (the
`_read_path` consult is BK-42's second site; BK-43 lands in the same
sequenced engine commit). NOT claimable without Jericho per the backlog
header.
