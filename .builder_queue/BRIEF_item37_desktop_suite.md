# BRIEF — item-37: interactive multi-tile desktop application suite

## Spec pointer (READ FIRST)

- `.builder_queue/QUEUE_STATE.json` item-37 (schema row: id/title/status/blocks_on/claim_order) — the claim.
- `.builder_queue/PRODUCT_LANE_STATE.md` item-36 entry (2026-09-26 ~17:3x) — the landed substrate this composes,
  plus its honesty block (environment translation is kernel-class; guests cannot sense across fences).
- `tools/glyph_reactive.py` module docstring — the item-35 runtime contract this suite drives per tick.
- `tools/glyph_shell.py` module docstring — the item-33 shell whose launcher/window idiom the suite reuses.
- `tools/glyph_channel.py` module docstring — the item-34 wire (BM905 reuse, seq/CRC/ack).

## Scope

- NEW: `tools/glyph_desktop_suite.py` (the three apps + the suite runtime).
- NEW: `tests/test_item37_desktop_suite.py` (the gate).
- NEW: `.builder_queue/RECEIPT_item37_desktop_suite.md`.
- Allowed edits: `.builder_queue/PRODUCT_LANE_STATE.md` (new ledger entry), `.builder_queue/QUEUE_STATE.json`
  (item-37 -> landed, updated/updated_by).
- MUST NOT touch: `tools/glyph_isa_v2.py` (engine byte-guard), `tools/glyph_reactive.py`,
  `tools/glyph_channel.py`, `tools/glyph_stratum.py`, `tools/glyph_shell.py`, `tools/glyph_input.py`,
  `tools/glyph_loader.py`, `tools/glyph_vfs.py`, `tools/glyph_process.py`, `tools/glyph_containment.py`
  (the landed item-26..36 layers — consumers only), any protected asset (`voicebook/`, `.rts/`,
  `rs_fixtures.json`), any file in the negative scope not listed under allowed edits.

## Gate command

```
SEED=af3e_item37 .venv/bin/python -m pytest tests/test_item37_desktop_suite.py -q -p no:cacheprovider
```

Expected exit: 0 (all legs pass) on the landed tree.

## Gate clause (falsifiable criteria)

The gate file `tests/test_item37_desktop_suite.py` must contain and PASS these legs (names normative):

1. `test_a1_topology` — a GlyphStratum carries, simultaneously, the item-33 status bar
   (GlyphShell.open_bar at its locked rect (8,0,1,20)) and THREE suite windows, each a
   ReactiveRuntime (item-35, full-width 3-row tiles) at disjoint plane rows; no
   StratumError raised; every runtime's six contract words (percept 0..3, act, sensor
   addresses from the runtime's own accessors) decode inside its OWN tile rect; all
   rects disjoint (pairwise `_rects_overlap` False).
2. `test_a2_terminal_echo` — a payload string (>= 32 bytes) seeded by the suite into a
   terminal runtime's percepts as 1-byte-per-word data; a GUEST decoder program
   (assembled by `GlyphAssemblerV2`, XOR-zero/OR-copy/AND-mask/SHR/ST loop — the
   probe-verified `af3e_probe_byteloop3.py` pattern) runs fenced in the terminal's
   tile and produces the byte-identical string in a RAM output buffer
   (asserted word-by-word); the task exits 0.
3. `test_a3_monitor_tracks_live_state` — two ReactiveRuntimes on one stratum; A ticks
   SENSE_WALL -> approach; A's action word crosses to B via GlyphChannel
   (send/commit_outbox/poll); B's environment (the item-36 translate pattern)
   seeds B's percepts from the RECEIVED code; B ticks and its painted color
   changes from the scan-band baseline to the approach band (asserted from the
   runtime's painted_color() / the composite, not host bookkeeping); the monitor
   app's guest program reads B's action slot and writes a normalized metric word
   to its own tile (fenced ST), asserted from monitor-tile RAM.
4. `test_a4_explorer_lists_root` — a GlyphVfs root (GlyphVfs.format) carrying files
   `/etc/motd` and `/etc/hostname` (staged + synced) is attached to an explorer
   runtime's task engine via GlyphVfs.attach; the guest runs syscall 0x13
   (SYSCALL_FILE_LIST, immediate form `SYSCALL r10 0x13` with r1/r2/r3 = dir/dest/max)
   — NO NEW SYSCALL NUMBER (the landed 0x13 arm); the guest's exit status equals the
   entry count (2) via SYSCALL 0x05 EXIT status; a second leg writes the listing to
   RAM and the host asserts `/etc/hostname` and `/etc/motd` appear NUL-separated.
   A missing-directory leg exits nonzero (rc -1 propagated).
5. `test_a5_click_to_app` — the GlyphShell launcher idiom: focus + key() BM905 press
   into a suite window's inbox pre-run; the window's guest program LDs the count
   word from its tile row 0 and exits with status == count (1); asserted via the
   task's exit status AND router.inbox_snapshot(wid)["count"] == 1.
6. `test_c1_cross_app_wire` — terminal A emits ONE GlyphChannel message to monitor B
   whose code/value carry A's own painted-band word; B's translated tick resolves
   approach; the SAME scenario with commit suppressed (encoded, not committed) leaves
   B at scan (the X4 isolation-difference pattern from tests/test_item36_cross_fence.py).
7. `test_c2_migration_item33` — tests/test_item33_shell.py passes GREEN via subprocess
   in this tree (the suite is a pure consumer of the shell layer).
8. `test_c2b_migration_item36` — tests/test_item36_cross_fence.py passes GREEN via
   subprocess in this tree.
9. `test_n1_engine_bytes` — `git show HEAD:tools/glyph_isa_v2.py` byte-compares equal
   to the working file (engine byte-guard).
10. `test_n2_wire_read_not_assumed` — the A3 green is not vacuous: deleting the wire
    slot words (zeroing the 4 committed packet words in B's tile after commit, before
    poll) makes poll() raise ChannelError (CRC) and B's tick stays scan — i.e. the
    monitor green really required the wire-carried word (in-suite negative leg).

## Failure evidence (RED before GREEN — must be demonstrated AT LANDING TIME)

Before trusting a green run, the landing tick must run a RED driver (the
`output/item36_red_driver.py` pattern) proving the gate can FAIL:

- RED 1: `test_a2_terminal_echo` with the byte-loop's mask constant corrupted
  (0xFF -> 0x00) — the leg must FAIL (bytes mismatch).
- RED 2: `test_a3_monitor_tracks_live_state` with the channel commit removed —
  B must stay scan and the assert on the approach band must FAIL.

Both RED runs' tails pasted in the receipt/commit body, then the GREEN tail.

## Definition of done

- Gate command exits 0 with 10/10 passing on the landed tree (tails in receipt).
- RED driver demonstrated (2 sabotaged variants fail as named).
- `git status --short` shows only in-scope files; commit on
  glyph-transpiler-autoloop; ledger + QUEUE_STATE updated in the follow-up commit.
- Receipt `.builder_queue/RECEIPT_item37_desktop_suite.md` includes the honesty
  block (what the PASS does NOT prove) and states rule-1 non-applicability
  (no rates/latencies claimed).

## Must-not-weaken

No live guard may be weakened to make a leg pass (engine byte-guard, wire CRC,
fence EXIT_FAULT legs stay intact). Interfaces are LOCKED: item-26..36 public
signatures are consumed, never edited; a signature that looks wrong is a
REPAIR_PENDING, not an edit.
