# RECEIPT_L1_shell_personality — CLAIM QUEUE ROUND 8, item 14

**Status: LANDED (completed 2026-09-24 ~00:3x CDT, builder cron af3e62239ce2;
final GREEN/RED tails below).**

## Scope (from SUPPLY_ROUND8.json L1-PERSONALITY)

- **May change:** `experiments/glyph_interactive_shell.py` (the dispatch-shell
  builder — new `build_l1_shell` assembled INTO the glyph program), NEW
  `tests/test_l1_shell_personality.py`, this receipt, ledger update.
- **Must not change:** engine syscall handlers (`tools/glyph_isa_v2.py`),
  WGSL twin (`tools/wgsl_glyph_isa_v2.py` + dispatch mirrors — shell programs
  are guest images; parity re-pin is a RUN leg, not an engine edit),
  `glyph_desktop.py`, protected assets, the item-11 grammar contract.

## What actually landed (architecture, disclosed)

- `experiments/glyph_l1_shell.py` (NEW): `GlyphL1Shell` — word-verb routing.
  `build_dispatch_shell` grew two OPTIONAL keyword args (defaults preserve
  the landed signature byte-for-byte: `stamp_paths=True`, `return_layout=False`):
  - `stamp_paths=False` -> NO in-image path stamps; the caller owns the
    FS-window path region (per-turn argv-path routing).
  - `return_layout=True` -> `(image, layout_dict)` exposing FS-window word
    addresses so the caller stamps paths without re-deriving layout.
- **Split, per the brief:** echo/speak/write/read/cat bodies EXECUTE ON THE
  GLYPH (the landed dispatch image, item-11 grammar intact — the harness
  seeds the internal single-letter form into the input ring and stamps the
  resolved absolute path into the FS window before the turn; 0x03/0x04 do
  the I/O against real on-disk paths). ls/pwd/cd/env/which/time/date/wc/
  head/tail/grep/cp/mv/rm are HOST personality shims in L1 — disclosed as
  such; their in-image migration homes are L2 (0x13 FILE_LIST) and L3.
- Single-letter legacy forms (`e/s/w/r/x`) stay live; `ERR:UNKNOWN_CMD`
  marker and grammar class unchanged (natural sentences still refuse).
- Containment: guest paths resolve under the session root (`L1Session.resolve`:
  absolute refused, `..` escape refused, 64-byte components), and missing
  files refuse host-side (`ERR:NOENT:<name>`) BEFORE the GPU turn — the
  engine's read-returns--1 PRT-garbage path is never armed. `mkdir -p` of
  parent dirs on `write` is a disclosed personality op (engine 0x03 cannot
  create parents; returns -1 silently otherwise).
- Ring cap documented: INPUT_DATA_CAP=64 bytes/turn (measured, probe
  `probe_l1_ringcap.py`); test payloads stay <64.

## Design decisions (measured this tick)

1. **Word verbs + live letter forms.** The item-11 grammar gate
   (`tests/test_item11_dispatch_grammar.py`) keys its legs on the letter
   verbs; removing them would stale the gate's subjects. Word forms are
   added AROUND them; the grammar class (any multi-char non-verb line
   refuses with the same marker) re-gated through the word surface (W7).
2. **Steps budget:** measured — a 30-char payload echo turn runs **413
   steps** at HEAD; `run_turn` floor is `max(2048, ...)`. Budget unchanged;
   margin >4x on the longest leg. The twin runs the same image in **115
   steps** (T1, below).
3. **'time'/'date' print the host epoch** (correctness disclosed: the epoch
   word is host-stamped, not engine-synthesized; BK-16 folds in per the
   round-8 order).

## RED leg (rule 4) — measured pre-landing, HEAD f68c251d

`.builder_queue/probe_l1_red.py` (repo copy; throwaway variant ran first):

- 19/19 word-verb legs returned `ERR:UNKNOWN_CMD` on the pre-landing tree
  (`echo hello`, `speak hi`, `write payload`, `read`, `ls`, `cat f`, `wc f`,
  `time`, `date`, `pwd`, `env`, `which echo`, `cp a b`, `mv a b`, `rm a`,
  `head f`, `tail f`, `grep n f`, `cd d`) — re-run by the landing tick, same
  19/19 RED (output above in the ledger session log).
- Keep-legs held pre- and post-landing: `e hello` -> `' hello'`,
  `z bogus` -> ERR, `what time is it` -> ERR (item-11 intact).
- Gate-internal RED: W1's echo assertion is load-bearing (mutated
  expectation ` hello w0rld` fails against the real `' hello world'`,
  shown by direct comparison at landing time); N1 proves a router that
  refuses every word verb cannot pass W1's legs.

## GREEN tails — this landing tick (13/13 + regression, real exits)

```
.venv/bin/python -m pytest tests/test_l1_shell_personality.py -q
=> 13 passed in 0.82s          (W1..W7, N1, T1, RED leg)

.venv/bin/python -m pytest tests/test_glyph_interactive_shell.py \
    tests/test_item11_dispatch_grammar.py tests/test_glyph_text_console.py \
    tests/test_bk2_wgsl_syscall_parity.py tests/test_bk7_fs_grow.py -q
=> 33 passed in 1.96s          (builder-family + item-11 grammar + DTF-2 band
                                + WGSL parity corpus + BK-7 FS)

.venv/bin/python -m pytest tests/test_bk11_coreutils.py -q   (prior tick)
=> 6 passed in 22-23s
```

## T1: WGSL twin parity (the receipt's open item, closed same-commit)

- Probe `.builder_queue/probe_l1_wgsl_pin.py` on the L1 image
  (stamp_paths=False, padded seed, return_layout): `run_wgsl(max_steps=2048,
  input_ring=b"e hello twin")` -> error None, halted True, steps 115,
  PRT = `b' hello twin'` — byte-identical to the CPU engine's turn.
- **Seeding-path truthing (probe-defect kept):** `ram_seed=` of
  LEN/CURSOR/DATA words does NOT drive the twin — the input ring lives in
  the BOX_MMIO mirror (SE022a slots 96-159), and run_wgsl's ram binding is
  the RAM analogue. First probe attempt returned 256 zero words (silently
  never ran the payload); re-routed to `run_wgsl(input_ring=...)` (the
  `test_glyph_text_console.py:186` shape) -> clean parity. The landed T1
  leg uses `input_ring=` and pins this in its docstring.
- T1 is `pytest.importorskip("wgpu")` — GPU-present lane runs it as a
  binding leg (it ran GREEN in the 13/13 above on this host's GPU); a
  GPU-less run records SKIP explicitly, never silent.

## What this PASS does NOT prove (honesty)

- No L2 (dirs, ls -l columns, append), no L3 (pipes), no L4 (desktop).
- ls/cp/mv/rm/wc/head/tail/grep/time/date/pwd/env/which/cd are HOST shims
  in L1 (the brief's own architecture: "parsed host-side"; their GPU-side
  migration is L2/L3 supply). Only echo/speak/write/read/cat execute
  glyph-side — verified by construction (they route through run_turn on
  the dispatch image) and by the twin leg for the echo body.
- `time`/`date` are host-stamped; no engine clock exists.
- WGSL parity is pinned for the echo body + the shared image; the file
  arms (0x03/0x04) twin behavior is carried by the standing BK-2 corpus
  (4 passed, included in the 33), not re-proven here per-verb.
- Benchmarks/floors: no rate claims in this receipt; rule-1 floors N/A
  (no performance number is load-bearing in the gate).
- Single host, single GPU (this host's wgpu device).

## Files touched (scope check at landing)

- `experiments/glyph_l1_shell.py` (NEW)
- `experiments/glyph_interactive_shell.py` (build_dispatch_shell: two
  optional kwargs, defaults byte-identical — the 27 standing
  interactive-shell/grammar/console gates green)
- `tests/test_l1_shell_personality.py` (NEW, 13 legs)
- `.builder_queue/RECEIPT_L1_shell_personality.md` (this file)
- `.builder_queue/probe_l1_red.py`, `probe_l1_steps.py`,
  `probe_l1_ringcap.py`, `probe_l1_name_dispatch.py`, `probe_l1_speak.py`,
  `probe_l1_wgsl_pin.py` (probes, receipted)
- `.builder_queue/PRODUCT_LANE_STATE.md` (ledger update)
- Engine syscall handlers, WGSL twin sources, glyph_desktop.py, protected
  assets: UNTOUCHED.
