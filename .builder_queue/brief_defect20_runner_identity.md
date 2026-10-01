# Brief — DEFECT-20 leg 5: write identity on the launcher/runner publish path

ROADMAP ROW: **DEFECT-20** (`systems/GLYPH_SELF_HOSTING_ROADMAP.md`, promoted `0db32fe`).
The emitter/observation half LANDED this tick at `8d73e34` (gate
`tests/test_defect20_write_identity.py` L1–L4, 4/4 green). This brief is the SECOND half, raised by
the ticket's amended acceptance criterion (`.builder_queue/DEFECT-20_snapshot_last_write_wins.md`,
commit `06e5053`): *"Reproduce the BK-14 dual-channel experiment. 'Agreeing' means attributably
agreeing: every substrate-read word must be traced to the stage that wrote it (stage id + write id),
not merely match numerically."*

Do NOT edit `.builder_queue/**` or `systems/**` (the orchestrator owns those). Do NOT commit.

## The measured gap (do not re-derive it)

- `tools/glyph_gpt/runner.py:110-121` — `GlyphRunner._publish()` writes the per-tick images
  (`kernel_memory<tag>.npy`) and the sidecars (`surface.meta.json` canonical, or
  `kernel_memory<tag>.meta.json` tagged) with NO write identity at all.
- Consequence in the real BK-14 flow (`tools/glass_box_demo.py`): Stage 1 uses `GeosEmitter` and
  writes an identified sidecar (`write_id 1`), then Stage 2 drives `GlyphRunner(...).drive(
  publish_dir=pub_dir, ...)`, whose canonical publish OVERWRITES `publish/surface.meta.json`
  (`runner.py:121`). The final snapshot of the dual-channel experiment is therefore unattributed —
  a witness on it cannot name the writing stage. That is exactly what the amended criterion forbids.

## Deliverable

1. **`tools/glyph_gpt/runner.py` — additive write identity in `_publish()`.**
   - Add `write_id` (monotonic within the publish dir: `max(existing "*.meta.json" write_id, 0) + 1`,
     robust to a malformed/unreadable sidecar — never raise), `writer`, and `written_at`
     (ISO-8601 UTC) to the sidecar `meta` dict it already writes. `writer` = the publish's own tag
     identity: for the canonical publish `"canonical"`, for a tagged publish the tag with its
     leading underscore stripped (e.g. `"_tick000123"` → `"tick000123"`). Keep every existing key
     (`tick`, `step`, `source_md5`, `faulted`, `canonical`, `heartbeat`, `heartbeat_tick`) exactly
     as it is.
   - **HARD CONSTRAINT — `tests/test_gh5_launcher_final.py::test_gh5_line_count_le_200` counts
     PHYSICAL LINES and `runner.py` is at 199 today.** Your change must leave the file at **≤ 200
     lines** (compress within `runner.py`: merge short lines, drop redundant blank/comment lines).
     Run that test file and show it green. `test_gh5_zero_dev_imports` must also stay green: only
     stdlib imports are allowed (`datetime` is fine; any import whose name contains
     atlas/spatial_builder/synth/generate/model/tokenizer/corpus/train/pack_dataset/baker FAILS).
   - Do NOT change the runner's behaviour otherwise (same files written, same names, same order).
2. **`tests/test_defect20_write_identity.py` — add leg L5 (`test_l5_runner_path_identity`)** and
   update the module docstring's leg list. L5 must, in one `tmp_path` publish dir:
   - publish through `GeosEmitter` first (intent `{"kind":"post","box":0,"op":1,"payload":2,
     "word":750,"writer":"stage-a"}`, after seeding `kernel_memory.npy` as zeros — copy the
     `_publish_dir`/`_acked` helpers already in this file) → canonical sidecar `write_id == 1`,
     `writer == "stage-a"`;
   - then drive the real launcher publish path into the SAME dir (build an image with the module's
     existing `_bake(tmp_path)` helper and run
     `GlyphRunner(img, ram_words=16384).drive(publish_dir=pub, max_instructions=60000)`) → the
     canonical `surface.meta.json` now carries `write_id == 2` and `writer == "canonical"`, and
     every tagged per-tick sidecar carries a `write_id` with its tag as `writer`;
   - assert the write ids in the dir are strictly increasing / unique (no two artifacts share a
     write id) — this is the "attributably agreeing, not merely numerically matching" clause;
   - assert the served identity through the observation path (`GEOS_IMAGE_DIR=pub`,
     `geos_surface_meta()`) names the runner as last writer (write_id 2, writer `"canonical"`), and
     that `take_witness(750, expect_write_id=1)` now raises `WitnessMismatch` while
     `take_witness(750, expect_write_id=2)` returns `writer == "canonical"` — i.e. the emitter
     stage's words are attributable per stage+write id, not by guessing;
   - restore `GEOS_IMAGE_DIR` in a `finally:` block.

## GATE — the orchestrator re-runs these itself; your own "it passes" is not evidence

- A) `/usr/bin/python3 -m pytest tests/test_defect20_write_identity.py -q` → **5 passed**, exit 0
  (L1–L4 must stay green — do not weaken them).
- B) `/usr/bin/python3 -m pytest tests/test_gh5_launcher_final.py tests/test_gh264c_teleop.py
  tests/test_gh26_live_surface.py tests/test_gh26_resident.py tests/test_bk14_demo.py
  tests/test_gh11_launcher_endtoend.py -q` → all green, exit 0.
- C) `/usr/bin/python3 -m pytest tests/test_gh26_emit_aperture.py tests/test_gh26_emit_admit.py
  tests/test_gh26_glass_box.py tests/test_gh24_s2_mcp_server.py -q` → all green, exit 0.

Use `/usr/bin/python3`. If a leg is impossible without a design decision you were not given, STOP
and report with evidence instead of choosing. End with a DIFF SUMMARY (files changed, exact
commands, literal last lines of output) and state the final line count of `runner.py`.
