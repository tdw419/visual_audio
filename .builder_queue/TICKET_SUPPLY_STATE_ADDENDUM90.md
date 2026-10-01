# TICKET — SE021 held 81st tick; RCA path-length claim MEASURED FALSE

**Orchestrator cron af3e62239ce2, 67th tick (2026-09-16 06:4x CDT).**

## NEW this tick — first substantive delta since addendum 84

Re-ran the SE021 red leg at SIX basetemp depths to probe the RCA's
short-path escape hatch (`.builder_queue/SE021_RED_LEG_RCA_20260916.md`,
§"Why it looked n=1-flaky but isn't"). **The escape hatch does not
reproduce.**

- Runner-path lengths measured: 91, 70, 66, 64, 62, 61/67 — the leg fails
  `['CHILD_OK', '']` at EVERY depth tried, 1F/3P each time, same signature.
- Shortest reachable runner path for this test name is ~58 chars (the
  test-dir name `test_control_returns_to_shell_0` (31) + `glyph_child_runner.py`
  (20) are pytest-fixed), so the RCA's "~50-char paths pass" regime is
  unreachable for this leg and cannot explain the red as written.
- Cross-check: in a /tmp mirror of the tree, the exec leg ALSO failed at
  runner len 61/67 where it passes in-repo at identical lengths — path
  length alone does not cleanly partition pass/fail across environments.
- RCA updated in place with this measured correction; fix options
  (a)/(b)/(c) stand, option (b)'s layout assert is now MORE important
  (short paths are not a safe operating point either).

## Unchanged (re-measured)

- SE021 gate 81st red: `tests/test_glyph_app_glyph_on_glyph.py -q` →
  `1 failed, 3 passed in 0.36s` (HEAD `c556aca`).
- Sibling exec-shell WIP unchanged: mtime 00:05:48, last commit touch
  `051fdd4` (2026-09-15 15:50).
- Maildrop: 4 msgs, w4 `hermes.0001.ruling.md` newest (03:00:24), no ack,
  no acks dir. SE021 option choice still outstanding: (a) variant / (b)+ /
  (c) / GH-25 paging route.
- Snapshot `/tmp/geos_observation/kernel_memory.npy` byte-identical
  md5 `3744eaa7` — no re-emit, no word re-reads.
- Roadmap: `tools/supply_census.py --json` → total=75, open=[]. Backlog
  exhausted. DEFECT-18/17 closed clause stands. /home 100% full.

## HOLD stands

maildrop w4 still awaits Jericho's SE021 ruling; nothing eligible to
implement without it. The RCA correction strengthens the case that this
needs a design call (the measured threshold behind the "flaky" story was
never real), it does not create new builder-eligible supply.

## Not verified this tick

- No GPU/WGSL leg run. No canvas pixel re-read (snapshot byte-identical).
- The exact row-68 overlap threshold was NOT re-derived from the prologue
  formula — only the RCA's external-repro claim was falsified.
- WGSL-side behaviour of the exec shell unprobed (as in every prior tick).
