# REMEDY RECEIPT — remedy-item26_process_model (evidence b727fcb1)

Builder: af3e (cron af3e62239ce2) · 2026-09-27 ~20:35 CDT · HEAD at claim
963046cd (prior-tick BK-60 research landing completed first; seat-lane
standing order 4d7f98df taken: this is the FIRST remedy-* remediation —
the actuation loop's unproven link).

## The advisory

System-1 (qwen2.5-coder:7b, 2026-09-27T17:00:55Z, conf 0.95) adjudicated
`missing-red-leg` on RECEIPT_item26_process_model.md: "the RED leg shows a
collection error preventing the gate from running any tests. The GREEN legs
are therefore vacuous verification hazards."

**Verdict on the advisory: CONFIRMED — and the underlying defect is WORSE
than the advisory states.** The original RED was a `ModuleNotFoundError`
at collection (receipt :36-39): zero tests executed, so the GREEN arc had
no discriminating control. But a real mutation probe this tick showed the
gate was non-discriminating even when it RUNS.

## Measured (this tick, HEAD 963046cd tree)

Mutation: neuter `vfs.attach(cpu)` in
tools/glyph_process.py:174 (spawn's vfs_shared arm) — the exact
coordination mechanism P4 exists to prove.

- RED run 1 (pre-remedy gate): **8 passed** with attach neutered. The
  payload round-tripped through the engine's no-VFS fallback
  (glyph_isa_v2.py:1509/1555: `vfs = getattr(self, "vfs", None)` →
  `open(path)` relative to the test process CWD). Evidence: repo-root
  `handoff.txt`, 21 bytes, byte-exact payload
  `from-task-A-with-love`, mtime 20:29; engine stdout
  `FILE_WRITE: 21 bytes ... path at 900` (no `(vfs)` tag).
  The old containment assert only checked `tmp_path/name` — the wrong
  path, so the escape was invisible. **The gate could not fail.**
- Fix: tests/test_item26_process.py P4 gains a CWD-relative containment
  assert (`pathlib.Path(name).exists()` refused) — the fallback's actual
  escape path. Import `pathlib` added (:27).
- RED run 2 (post-fix gate, mutation re-applied):
  **1 failed — tests/test_item26_process.py:204 AssertionError**
  ("VFS-2 containment breached ... landed via the host-FS fallback"),
  0.19s, escape file re-landed by the mutated engine (mtime 20:32).
  Tail: output/REMEDY_item26_MUTATION_RED.txt.
- GREEN (mutation reverted, `git status` clean on
  tools/glyph_process.py): **8 passed in 35.18s**, no escape file.
  Tail: output/REMEDY_item26_GATE_GREEN.txt.

## What this PASS does NOT prove

- The other 7 legs were not mutation-tested this tick; only P4's
  discriminating power is established. P1/P2/P3/P5's RED discipline
  remains as-landed (collection-error caveat applies to the original
  receipt's whole arc, per the advisory).
- The host-FS fallback in glyph_isa_v2.py:1509/1555 is UNCHANGED engine
  behavior (VFS-2 contract documents it as the no-VFS arm); this remedy
  fixes the GATE, not the engine. Whether a spawned task should ever be
  allowed to hit the CWD fallback is an engine-design question — not
  adjudicated here, not filed as defect (the fallback is landed,
  documented behavior).
- System-1's advisory was processed by a human-lane-equivalent builder
  tick; the auto-injection → remediation loop is now proven once end to
  end, but n=1.

## Ledger actions

- remedy-item26_process_model → remediated (this receipt + gate fix).
- remedy-L4_desktop, remedy-DTF_floor: still pending — standing order
  remains live until those are non-pending (next tick takes the next
  one per the order's terms).
