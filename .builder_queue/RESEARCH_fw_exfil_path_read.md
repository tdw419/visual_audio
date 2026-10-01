# RESEARCH — 0x03 FILE_WRITE exfiltration: a tiled USER task can write guest
# RAM bytes to arbitrary HOST paths it names; the PATH decoder is itself a
# fence-blind cross-fence read (BK-42 candidate)

- **Builder:** af3e62239ce2 (Glyph OS event-chain cron, Phase 1c research tick)
- **Date:** 2026-09-27 (~02:0x CDT)
- **Tree:** HEAD a893ad13beb0dff575509f62218ae984317eb962 at probe start;
  probe landed modules only (no engine edits); tracked tree clean at claim.
- **Question:** the last unprobed arm of the fence-bypass family, left
  explicitly open by both prior receipts (RESEARCH_syscall_fence_bypass.md:124,
  RESEARCH_ksys_pc_self_arm.md:102): does 0x03 FILE_WRITE let a USER task
  confined to tile (5,0,8,8) move guest RAM bytes into a HOST file it names?
  BK-40 closed the write-INTO-guest-RAM map; the exfiltration side (guest
  RAM -> host filesystem, OUTSIDE the substrate entirely) was never measured.

## Method

Probe `.builder_queue/probe_fw_exfil_af3e.py` (untracked, landed modules
only), harness = the landed item-29 containment path itself:
`GlyphProcessTable.spawn(image, tile=(5,0,8,8))` (tile = rows 5..11 x cols
0..7, W_MEM=32; first out-of-tile word 168 = row 5 col 8), auto reaper row
30. Handler under test: `tools/glyph_isa_v2.py:1462-1506` — data read from
`self.memory[data_addr..]` (NO `_addr_in_box` consult; the fence consult
table `:720-747` is reached from exactly one execute site, the ST arm
`:1041`), sink = `open(path, "wb")` (`:1499`) where path is decoded by
`_read_path` (`:1381-1408`) from guest RAM words. All verdicts are taken
from HOST FILE CONTENTS (byte-compared), never from exit codes — the
handler swallows all exceptions and returns -1 into r10, so rc is
uninformative. Fixture hygiene: every expected host file is unlinked and
asserted absent before each leg, so stale content cannot false-positive.

Determinism: 3 internal runs, all 5 cases byte-identical (results blob +
file contents), **md5 d7a9aa69260d2173fc2e61c98ef6e511**. Re-derive:
`python3 .builder_queue/probe_fw_exfil_af3e.py`.

## Findings (all quantities structural — file bytes, exit codes, fault_addr, line numbers; NO rate/latency/cost claims, rule-1 floors do not attach)

1. **fw_ram_out — direct host exfil CONFIRMED.** Canary bytes 'F','K'
   seeded host-side at OUT-of-tile words 172/173; guest issues FILE_WRITE
   data_addr=172, len=2, path '/tmp/b4a' -> EXIT_OK, no fault, host file
   /tmp/b4a contains exactly b'FK'. The tile fence never fired: the
   handler's data read has no box consult and the sink is host-side.
2. **fw_ld_stage — exfil via the BK-38 read primitive CONFIRMED.** LD the
   out-of-tile canary word 172 (fence-blind read, BK-38), ST it to in-tile
   word 192 (allowed), FILE_WRITE from 192 -> host file /tmp/b4b contains
   b'F'. Composite chain: even if a future fix fenced the handler's
   data_addr view, the LD read arm feeds the same sink.
3. **fw_path_read — the PATH argument is a fence-blind cross-fence read
   (NEW, unlisted in BK-38/39/40).** Path staged '/tmp/b4d' WITHOUT a NUL
   terminator; `_read_path` (`:1393-1408`) walked past the staged region
   INTO out-of-tile words 168/169 (seeded 'X','Y') and built the filename
   '/tmp/b4dXY' — the host file appeared at that path with the in-tile
   payload b'Z' inside. The syscall PATH decoder reads arbitrary RAM until
   a zero byte, with no box check: a confined task can make the KERNEL's
   own path read smuggle out-of-tile bytes into the host-visible filename
   itself (an exfil channel that needs no FILE_WRITE data argument at
   all — the filename IS the channel).
4. **fw_ctl_in — non-vacuity control.** Same handler, data in-tile
   (words 196/197) -> /tmp/b4c contains b'FK'. The handler path is live;
   legs 1-3 are not vacuously green.
5. **ctl_st_out — E-K1 baseline intact.** Plain ST to out-of-tile word
   172 traps: EXIT_FAULT, fault_addr = 688 = 172*4, mode -> SUPER. Every
   exfil path above flows around a fence that demonstrably works for ST
   on this exact tree.

**Blast-radius note (fenced speculation, not load-bearing):** the same
no-consult shape almost certainly covers 0x01 WRITE (guest RAM -> output
buffer), 0x07/0x12 RUN (path argument -> program execution), and the VFS
twin `vfs_write` (`:1481-1484`); those are source-read inferences in the
same handler family, NOT separately probed this tick.

## Verdict

The exfiltration side is open and measured: a tiled USER task can move
out-of-tile guest RAM bytes to a host path of its choosing, clean-exit,
and can additionally use the path decoder itself as a cross-fence read
channel. BK-40's verdict text ("every guest-reachable RAM/image write
path is fence-blind except ST") described the write-in arms; with BK-42
the read/exfil arms are measured closed too: LD (BK-38), PARALLEL_LD/ST
+ PUSH/CALL (BK-39), syscall data writes (BK-40), and now FILE_WRITE's
data read, its host sink, and the `_read_path` decoder. BK-38/39/40/41/42
share the same fix family — every guest-influenced host or cross-tile
access must consult the box predicate — and should land as ONE sequenced
engine commit; BK-42 adds two consult sites: the FILE_WRITE data loop
(`:1474-1499`) and `_read_path` (`:1393-1408`, called by ALL path-taking
syscalls: 0x03/0x04/0x07/0x12/0x13).

## Probe-hygiene disclosure (all caught BEFORE any finding was recorded)

- Draft 1: 14-byte paths -> 48 instructions; the PARALLEL_ST write-through
  pixel mirror (`:1291-1295`) hit pixel 160 = row 5 = instructions 40-47:
  staging overwrote the program's own tail mid-run (the exact trap BK-40's
  probe disclosure documents). Also packed a 2-byte canary into ONE word
  while the handler reads one byte per word. Fixed: 8-byte paths + byte-
  per-word seeds.
- Draft 2: paths staged without NUL terminators. First runs showed
  "no file" — a debug twin with an open-spy revealed the handler actually
  WROTE '/tmp/b4aFK' (path decoder ran through the canary). This accident
  was promoted to leg fw_path_read. Same draft: the terminator staged at
  word 168 clobbered a canary seeded at 168 (canary -> 172), and the LD
  leg stored to word 176 = row 5 col 16 — OUTSIDE the 8-wide tile — and
  trapped (E-K1 correctly firing); stage word -> 192. Note the draft-2
  debug twin's in-process `os.path.exists` used the WRONG probe filename
  (debug harness artifact only); final verdicts byte-compare the files.
- The probe asserts `tile_h_word == 8` in every result (fence armed) and
  the ST control traps with the exact expected fault_addr.

## NOT verified

- WGSL twin on-device (syscall handlers are Python-only; source-read only).
- 0x07/0x12 RUN and the VFS `vfs_write` twin (source-read inference only).
- Whether FILE_WRITE under an armed KSYS_PC posture (BK-41 shape) changes
  the exfil — the direct `_handle_syscall` branch was measured; the E-K2
  dispatch of guest-chosen pixels is BK-41's leg 1 finding, not re-run here.
- Host-side enforcement beyond the handler: no GLYPH_FS_ALLOW-style allow-
  root check exists for 0x03 (unlike 0x13 FILE_LIST, `:1779-1786`) — this
  is a source-read observation, not a measured attack-surface diff.
- Whether any landed fixture relies on unconfined FILE_WRITE (the BK-40
  family leg checks that at landing).

## Backlog candidate (filed as BK-42, systems/GLYPH_BACKLOG.md)

Gate: `tests/test_bk42_fw_exfil_fence.py` — L1: fw_ram_out shape ->
out-of-tile data bytes must NOT reach the host file (drop, refuse, or
fault — one posture documented), RED today (b'FK' lands); L2: fw_ld_stage
shape -> LD-fed exfil blocked the same way, RED today; L3: fw_path_read —
an unterminated staged path must NOT decode past the tile into the
filename, RED today ('/tmp/b4dXY' appears); L4: fw_ctl_in non-vacuity
control (in-tile data + in-tile path lands, stays green); L5: ST
out-of-tile trap control; L6: non-vacuity — neuter the new consults ->
L1-L3 fire; L7: family — BK-38/39/40/41 + item-29 gates green. Prereq:
BK-38 + BK-39 + BK-40 + BK-41 (same consult sites + the path-decoder
class; ONE sequenced commit). NOT claimable without Jericho per the
backlog header.
