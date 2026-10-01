# RECEIPT — BK-46 + BK-47 sequenced landing (wc + head dynamic seed path)

**Builder:** af3e62239ce2 (Glyph OS Event Chain cron)
**Date:** 2026-10-01 ~04:3x CDT
**Picked at:** HEAD 9fa94508bf2e6cda138a3f0bfdaf77da6c9e34f5 == monitor fingerprint
**Rows:** systems/GLYPH_BACKLOG.md BK-46 (line 74) + BK-47 (line 75) — the
rows themselves direct "same file + fix shape; land together or one
sequenced commit."
**In-flight provenance:** found uncommitted in the mainline tree (fix + gates
+ probe, mtimes 04:10-04:13, no ledger entry) — completed per the
finish-in-flight rule; mailbox clean (no RULING newer than HEAD; newest
RULING mtime 09-29 09:35), ledger STATUS ACTIVE, CLAIM QUEUE empty.

## What landed

1. **`tools/glyph_gpt/coreutils_port.py`** (md5 0be4bfb0634951c7fb37feca36314bb9):
   wc body V2 — `bk11_out_dec` arbitrary-width decimal emitter replaces the
   V1 2-digit `char buf[3]` renderer (measured '310'→'O0' corruption,
   probe_bk46_red_af3e.py P4); single-space `%d %d %d %s` format replaces the
   promotion-era 16-byte padded window; fixture table gains `three_digit`
   (data_len_override — the 3-digit render path without a 600-byte literal)
   and the wc pins move to the new shape.
2. **`experiments/glyph_l1_shell.py`** (md5 2630dd23e77e92685ce71553e7187564):
   - wc + head branches SWAPPED to `_shell_native` (the falsified
     "16-byte window truncates" refusal retired — the refusal comment now
     states the falsification, BK-24 ring carries any report size, past
     the ring's 64-word extent the swap refuses LOUDLY);
   - `_shell_native` prepends `_COMMON` to the dynamic TU for V1 bodies
     (VOL2 grep/tr excluded — they carry `_VOL2_COMMON` internally);
     `wc_name` seed added;
   - `_gcc_err` diagnostic: compile/link failures now return
     `ERR:SHELLNATIVE:<verb>:<first stderr error: line>` (both arms), the
     BK-47 L4 contract — the defect had hidden behind the opaque bare ERR;
   - BK-46 L3b shim fix: `_wc` counts lines POSIX-style (`text.count("\n")`)
     not `splitlines()` — see defect (d) below.
3. **`tests/test_bk46_native_wc_swap.py`** (NEW, 8 legs): L1 swap-returns-
   report, L2 3-digit-render, L3 parity >256B, L3b POSIX no-trailing-newline
   parity (defect d), L4 head/tail posture source-pinned, L5 non-vacuity
   (no-_COMMON TU dies at ld), L7 `_SHELL_NATIVE=False` shim arm, L4b head
   edge shapes.
4. **`tests/test_bk47_head_dynamic_path.py`** (NEW, 6 legs): L1 head -n 1,
   L2 -n 3, L3 n-exceeds→whole file, L4 stderr-excerpt diagnostic
   (source pins + live no-_COMMON TU dies at link with 'bk11_out_ch' +
   selection-rule pin), L5/L5b non-vacuity (source pins + LIVE
   `_COMMON`-neutered device run returns the bare ERR, restored run green).
5. **`tests/test_bk11_coreutils.py`**: wc legs re-pinned to the BK-46
   single-space shape + ring readout for >16-byte wc reports.
6. **`tests/test_l1_shell_personality.py`**: w5 wc pin 3→2 lines (defect d).

## RED-first evidence

- **Landed probe (committed by a prior session at HEAD):**
  `.builder_queue/probe_bk46_red_af3e.py` (md5
  eba40f33a1e4bc447f1ef6c6ecb79670) — measured at HEAD 9fa94508: P1/P1b
  ERR:SHELLNATIVE:wc (cache on AND off), P3 gcc `'_n' undeclared`,
  P4 '40 40 l0' corruption. `.builder_queue/probe_head_dynamic_af3e.py`
  (md5 c2b53f4fa32983c988c54a493629e4d2, measured at ad4f2494, results md5
  43bf2f0366674987708daa3980aa326d): dyn head → ERR:SHELLNATIVE:head,
  exact TU → ld.rc=1 undefined reference to 'bk11_out_ch', control with
  _COMMON → on-glyph 'alpha'. The "empty ring" record: FALSIFIED.
- **BK-46 gate stash-RED (this session, fix stashed at HEAD 9fa94508):**
  2 failed / 5 passed — L4 (posture pins), L5 (non-vacuity) RED. L1/L2/L3
  PASSED on the stashed tree — **receipt-hygiene caveat**: on the unfixed
  tree those legs ride the host-shim arm (the native branch is still
  dead), so their pre-fix passes are vacuous; the probe's ERR-string
  measurements + the committed RED pins in test_bk11's addendum (3 original
  wc legs failed RED pre-body-fix, measured at HEAD 9fa94508) carry the
  defect evidence. Stated plainly; not hidden.
- **BK-47 gate stash-RED (this session):** 3 failed / 3 passed — L4 source
  pins, L5, L5b RED at HEAD 9fa94508. L1-L3 passed pre-fix only because
  the head branch still routed to the host shim on the stashed tree (same
  vacuity caveat as above; the probe carries the true RED).
- **L3b RED (this session, pre-shim-fix):** `('2 3 8 noeol.txt',
  '3 3 8 noeol.txt')` — native==POSIX wc, shim==splitlines-phantom.
- **Family gate caught a real defect (defect d):** the landed
  test_l1_shell_personality w5 went RED after the swap — the HOST SHIM
  counted lines with `splitlines()` (phantom line on no-trailing-newline
  files) where the native body and real `wc` count '\n'. Measured:
  file 'aa\nbb\ncc' (8 B) → native '2 3 8 noeol.txt' == host `wc`; shim
  '3 3 8 noeol.txt'. Fixed in `_wc` (POSIX count), w5 pin migrated 3→2,
  L3b added to the BK-46 gate. The shim was the defect; real wc is the
  oracle.

## GREEN evidence (this session, twice for each gate where noted)

- BK-46 gate 7/7 → 8/8 (after L3b) ×2 (15.8s, 15.6s; second pinned run
  17.5s inside the combined run).
- BK-47 gate 6/6 ×2 (7.4s, 7.8s).
- Family: BK-46 + BK-47 + BK-11 (byte-exact fixtures) + l1_shell_personality
  = 35/35 (60.97s, one run).
- Regressions on this tree: BK-50 twin door 6/6, BK-45 VFS fence 7/7,
  monitor worktree-blindness + fingerprint hygiene suites green — 26 passed
  (49.4s).
- Engine mirrors untouched: tools/glyph_isa_v2.py ==
  glyph_dispatch/src/glyph/glyph_isa_v2.py == 8dd8ce806e07249b570d2539a1260612
  (the BK-44-era engine md5 — no engine change in this landing).

## What the PASS does NOT prove

- tail's native path (no native source exists — posture pinned host-side).
- Pipe/stdin wc/head forms (host shim consumers by design).
- WGSL twin (Python-host surface; run_wgsl unaffected).
- head's BK-27 cache-hit path beyond the shared collector leg.
- BK-11 fixtures remain byte-exact under the new wc format (they were
  re-pinned to it — the gate proves the new shape, not the old one).
- The pre-fix L1/L2/L3 vacuity caveat above (probe carries the true RED).

## Row updates

- BK-46, BK-47: RESOLUTION tails appended in systems/GLYPH_BACKLOG.md.
- Next per row order: BK-54 blast-radius work is receipted; check
  GLYPH_BACKLOG for the next open row on the next tick (or any new CLAIM
  QUEUE item / binding RULING first).
