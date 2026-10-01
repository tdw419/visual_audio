# RECEIPT — GL6-BUILD (OSS GL-6): recorded demo cast + capture-authenticity gate

**Date:** 2026-09-12 · **Cron:** af3e62239ce2 (builder orchestrator) · **Row:** `GL6-BUILD`
(provenance: `.builder_queue/RULING_next_lane_OSS_GL6_GL7.md` `8c56f43`; binding gate legs:
`.builder_queue/NEXT_TARGET_gl6.md` § BINDING GATE CONDITION, `f6b7d19`)
**Artifact repo:** `/home/jericho/zion/worktrees/glyph-isa` → `github.com/tdw419/glyph-isa`
**Artifact commit:** `b5aa3f2` (local; **unpushed** — publishing is Jericho's step)

## What was built

Four new files, no existing file modified:

| file | role |
|---|---|
| `tools/record_cast.py` | stdlib-only pty recorder → asciinema v2 `.cast` |
| `docs/demo/gl6_bake_and_run.cast` | the committed artifact (produced by running the recorder) |
| `tests/test_gl6_demo_cast.py` | the gate (L1–L4) |
| `docs/DEMO.md` | how to regenerate / view; publication noted as the maintainer's step |

The demo session (fixed, in `DEMO_SESSION`): the repo's own `./glyphc build` + `./glyphc run` on
`examples/01_hello.glyph` (→ `OUTPUT: 42`, `[HALTED] in 3 steps`) and `examples/03_fibonacci.glyph`
(→ `OUTPUT: 13`, `[HALTED] in 513 steps`).

Every event payload is a chunk read off a pty; **no event line is typed or templated**. The recorder
also records the child's exit status in the cast header.

## Evidence (all runs by the orchestrator, not the delegate)

| check | command | result | file |
|---|---|---|---|
| Gate GREEN | `/usr/bin/python3 -m pytest tests/test_gl6_demo_cast.py -q` | **4/4**, junit `tests=4 failures=0 errors=0`, exit 0 | `output/gl6_gate_run2_green.txt`, `output/gl6_gate.xml` |
| Gate RED (artifact absent) | same, with the cast moved aside | **4 failed** (all four legs) | `output/gl6_gate_run1_red.txt` |
| Repo regression | `/usr/bin/python3 -m pytest tests -q` | **40 tests / 0 failures / 0 errors**, exit 0, 9.27 s | `output/gl6_fullsuite.txt`, `output/gl6_fullsuite.xml` |
| Out-of-tree falsification | `.builder_queue/probe_gl6_cast_authenticity.py` | **5/5** | `output/gl6_orch_probe.txt` |

Falsification detail (`output/gl6_orch_probe.txt`): a **hand-authored cast that satisfies L1 structure
and every L2 anchor** is still caught by L3 — its payload is 570 B against the fresh real run's 606 B —
and a **single-character** payload mutation (`OUTPUT: 42` → `OUTPUT: 92`) turns the gate red through the
same checker the assertions use. So the gate is not satisfiable by authorship, which was the whole point
of the binding condition.

## Provenance

- Cast: 16 events, payload **606 bytes**, `payload_sha256 = 18688ea8abc11bc4620691e8d084f592fc557ea7bbfdb34ff1e0d0f947b1ed16`, recorded child `exit_code = 0`, header `version 2`, `80x24`, title set.
- Recorded against the tree at `1284022` (the OSS repo HEAD when the session ran) + the four new files, which the demo does not touch.
- Regenerate: `python3 tools/record_cast.py --out docs/demo/gl6_bake_and_run.cast`.
- Interpreter used for all gate numbers: `/usr/bin/python3` 3.12.3 (PIL 10.2.0, numpy 1.26.4, pytest 8.3.5). Recorder and gate are stdlib-only, so they also run under the repo's default `python3`.

## Honest boundaries (what this is NOT)

1. **No shareable URL.** GL-6's oracle ("a shareable URL or asciinema link that plays back the demo end to
   end") is **unmet**. `systems/GLYPH_OSS_ROADMAP.md:41` stays `QUEUED`; flipping that row is Jericho's,
   because the ruling (`.builder_queue/RULING_next_lane_OSS_GL6_GL7.md`, condition 2) fences publishing
   and hosting to him.
2. **`asciinema` itself was not used** — it is absent on this host and `pip install --user` is refused
   under PEP 668. The cast is the v2 format written by the committed recorder, which asciinema.org accepts
   as an upload; but I did **not** verify playback with the real `asciinema` binary.
3. **CI has not seen it.** The gate will run in GitHub Actions only after the commit is pushed (GL-4's
   matrix runs `pytest tests`), so the badge claim for this test is untested here.
4. **The cast is bound to this tree.** Regenerating at a different commit changes the payload; L3 then
   fails by design — re-record when the demo's output changes. The recorder is the demo's definition, so
   command drift is a single-file edit plus one re-record.
5. The committed L4 mutation changes two characters (`42`→`43`); the one-character mutation is proven
   out-of-tree (probe file above), not inside the committed gate.

## Loop-side conclusion

The loop's deliverable for GL-6 (artifact + gate) is **done and verified**; GL6-BUILD is marked ✅ in the
self-hosting ledger with this boundary, and the next eligible supply per the same ruling is **GL-7**
(honest benchmark doc: methodology + raw numbers regenerable from the repo).
