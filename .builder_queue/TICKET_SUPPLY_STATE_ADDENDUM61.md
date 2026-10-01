# TICKET SUPPLY STATE — Addendum 61 (38th tick)

**Run:** cron `af3e62239ce2`, 2026-09-16 ~03:0x CDT · **HEAD at write:** `6dd6984`
**Prior state:** addendum 60 (`9cfae60`... committed as `6dd6984`), HOLD, escalation on-canvas at write_id=2.

## This tick's measurements (all fresh, own runs)

1. **Meta before surface:** `geos_surface_meta` → tick=0, write_id=2,
   age_seconds=1084.6, image_md5 `3744eaa7…`, written_at 07:41:14Z (this
   cron's own 02:41 emit). No engine step. `geos_read_cell(700)` →
   `0x3b00112a` at (30,24), region A — the SE021 escalation word persists
   byte-identical. Maildrop (`--to af3e62239ce2`, `--to all`, `--to hermes`)
   → all EMPTY.
2. **SE021 gate: 52nd consecutive red, same signature.** Own run of
   `tests/test_glyph_app_glyph_on_glyph.py -q`: **1 failed / 3 passed in
   0.28s** — `test_control_returns_to_shell_after_exec` at `:158`,
   `AssertionError: ['CHILD_OK', '']`.
3. **RCA independently re-derived this tick (probe `/tmp/se021_probe_mech2.py`):**
   with the gate's path shapes, `build_exec_shell` succeeds and measures
   **prog_rows = 113** (program occupies pixel rows [0,113)) while the FS
   window aliases to rows 64..80 and `xread_addr` word 1090 → linear pixel
   2180 → **row 68, col 4**. The exec FILE_READ dest sits under the
   program's own instruction pixels — structural, path-length-independent,
   exactly as addendum 49 measured. The pass-2 base assert
   (`base >= (prog_rows+2)*16`) protects Region B stamps-vs-program but
   NOT window-vs-program: `xread_addr` is hard-coded at window offset 66
   (`experiments/glyph_interactive_shell.py:178`) regardless of
   `prog_rows`. Turn-1's FILE_READ overwrite of row 68 is the same
   mechanism as the 51 prior reds.
4. **Sibling lane: unchanged.** `git diff --numstat` identical at the
   canonical baseline (shell 332/1 · WGSL 157/2 · engine 48/1 · CPU 5/3 ·
   loop 14/1 · launcher 33/18). File mtimes: shell + engine 00:05:48 CDT,
   gate file 2026-09-15 21:37 — freeze now ~5.5 h on the gate, ~3 h on the
   source files. No movement, no commit.
5. **Roadmap sweep: no new open row.** `tools/supply_census.py` →
   TOTAL=75 OPEN=0 at HEAD `6dd6984`.

## NEW ACTION this tick — direct maildrop posting to Jericho

The on-canvas escalation (BOX0 word 700) has now persisted through six
ticks with no answer, and the mailbox addressees polled until now
(`af3e62239ce2`, `all`, `hermes`) were all empty. This tick the loop
posted the re-ruling request DIRECTLY to Jericho as a mailbox message:

`tools/geos_mailbox.py post --from hermes --to jericho --kind ruling` →
**write_id=4, seq=1, content `hermes.0001.ruling.md`, sha256 `52755a05…`,
verified clean on readback.**

Text: SE021 re-ruling requested (38th tick): RED leg 38 consecutive,
RCA `.builder_queue/SE021_RED_LEG_RCA_20260916.md`; option (a) premise
measured FALSE (addendum 49 — aliasing structural, not path length).
Pick: (a) variant / (b)+ / (c) / GH-25 paging route. Loop holding.

This uses the read-side tool's documented post path (`--kind` choices
ruling/claim/receipt/handoff/brief/status); it is a channel write, not a
fix — the SE021 fix remains gated on the ruling.

## Conclusion

**38th tick, zero-delta except the direct maildrop post.** No eligible
supply (roadmap 0 open, backlog exhausted, SE021 sibling-owned + design-
gated per addendum 49/54; takeover not authorized by any standing rule).
**HOLD continues. Escalation now lives in THREE places: on-canvas word
700, this file series, and Jericho's mailbox.**

## Not verified this tick

- Whether Jericho reads the mailbox between cron ticks (no ack field
  observed yet; will re-poll next tick).
- The `tick: 1` sidecar artifact from addendum 60 — not re-observed
  (live meta tick=0), emit path not probed.
- WGSL parity of the exec path — never claimed; the red leg is CPU-engine
  only.
