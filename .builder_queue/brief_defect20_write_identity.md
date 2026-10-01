# Brief — DEFECT-20: publish-path write identity (witness attribution)

ROADMAP ROW: **DEFECT-20** in `systems/GLYPH_SELF_HOSTING_ROADMAP.md` (promoted this tick at
`0db32fe`; source ticket `.builder_queue/DEFECT-20_snapshot_last_write_wins.md`).
Do NOT edit the roadmap or `.builder_queue/**` — the orchestrator owns those.

## The defect (already measured, do not re-derive)

`tools/geos_emit.py` publishes with ONE fixed filename (`IMAGE_NAME = "kernel_memory.npy"`,
line 40) plus a sidecar (`META_NAME = "surface.meta.json"`, line 41) written in `_commit()`
(line 101). Every publish overwrites both, so the committed snapshot only ever represents the
LAST writer and a substrate witness is identifier-free: it can be a true statement about the
wrong write. Measured 2026-09-12 in the BK-14 dual-channel re-verification — word 703 matched
across channels because no later stage touched it, but words 750 (argv, stage 1) and 754
(result) did NOT, because later stages rewrote those words for unrelated purposes.

## Deliverable: make the publish path write-identified (ticket fix (b) + (a)), additive only

FILES IN SCOPE — touch nothing else:
- `tools/geos_emit.py` (additive)
- `tools/geos_observation_server.py` (additive)
- `tools/geos_witness.py` (NEW)
- `tests/test_defect20_write_identity.py` (NEW — this is the gate)
- `output/defect20_*.txt` (scratch evidence you produce; untracked, fine)

FORBIDDEN: `tools/glyph_gpt/**`, `tools/rv64i_to_glyph.py`, `glyph_dispatch/**`, any WGSL
shader, any existing `tests/*.py`, `systems/**`, `.builder_queue/**`.

Read `tests/test_gh26_emit_aperture.py` FIRST — it is the pattern for constructing
`GeosEmitter(publish_dir=..., ack_file=...)` and for pointing `GEOS_IMAGE_DIR` at a temp dir.

Required mechanism:
1. **Write identity in the sidecar.** `_commit()` must allocate a monotonically increasing
   `write_id` (read the existing `surface.meta.json` `write_id` if present, else 0, then +1) and
   record it, plus `writer` and `written_at` (ISO-8601 UTC), in `surface.meta.json`. `writer`
   comes from the caller: accept an optional `"writer"` key on the intent (e.g.
   `{"kind":"post","box":0,"op":1,"payload":2,"word":750,"writer":"stage-a"}`); when absent use
   the deterministic default `"unattributed"`. **Additive only** — the existing keys `tick`,
   `step`, `source_md5`, `canonical`, `emit` must keep their current names/meaning, and the
   existing `E_ACK` human gate must keep refusing without the ack file/env.
2. **Per-write archive (fix (a)).** Each publish ALSO writes `<publish_dir>/archive/
   kernel_memory.<write_id>.npy` (same bytes) with its own per-write sidecar
   (`<publish_dir>/archive/surface.meta.<write_id>.json`) so an earlier write's words survive a
   later publish. Provide a documented loader for a given write id (a small function in
   `tools/geos_witness.py` is fine) returning (words, write_id, writer, image path, md5).
3. **Read-path surfacing.** `geos_surface_meta()` in `tools/geos_observation_server.py` must add
   to `meta["source"]`: `write_id`, `writer`, `written_at`, `sidecar_file`, `image_md5`. When the
   served image has no sidecar (bare `.npy` in the dir) these MUST be `null` and the tool MUST
   NOT crash.
4. **Loud witness attribution.** New `tools/geos_witness.py` exporting
   `take_witness(word, expect_write_id=None, image_dir=None)` → dict with
   `{word, value, write_id, writer, image_file, sidecar_file, image_md5, age_seconds}`, raising a
   NAMED error class `WitnessMismatch` whose message contains
   `WITNESS_MISMATCH: served write_id <n> != expected <m>` when `expect_write_id` is given and
   does not match the served image. It must read state through the SAME load path the observation
   server uses (import `_load_memory` or share the helper) so witness and read cannot disagree.
   A witness for the wrong write must NEVER be returned silently.

## GATE — the orchestrator re-runs both commands; your own "it passes" is not evidence

**Gate A (primary):** `/usr/bin/python3 -m pytest tests/test_defect20_write_identity.py -q`
→ must be `4 passed` (or more), exit 0. Legs, exactly:

- **L1 monotonic identity** — one `GeosEmitter` into a `tmp_path` publish dir with its ack file;
  two consecutive publishes (publish 1: `word 750`, `writer "stage-a"`; publish 2: `word 754`,
  `writer "stage-b"`). Assert the sidecar `write_id` is 1 then 2, the two artifacts are
  distinguishable, and after publish 2 the words written by publish 1 are STILL retrievable and
  attributed to `write_id 1` (archive leg — this is fix (a), the leg that must fail if the
  archive is missing).
- **L2 meta exposure** — with `GEOS_IMAGE_DIR` pointed at that publish dir, call
  `geos_surface_meta()` directly (import the function; no MCP transport needed) and `json.loads`
  it: `source.write_id == 2`, `source.writer == "stage-b"`, `source.image_md5` non-null and equal
  to an md5 you compute yourself over the served `.npy`, `source.sidecar_file` non-null. Then a
  second dir holding a bare `.npy` and NO sidecar: the same keys exist with `null` values and no
  exception. Restore `GEOS_IMAGE_DIR` in a `finally:` block (other suites read that env var).
- **L3 loud attribution** — while write 1 is current, `take_witness(750, expect_write_id=1)`
  returns `write_id 1` with its value; after a further publish (write 2),
  `take_witness(750, expect_write_id=1)` raises `WitnessMismatch` whose message contains
  `WITNESS_MISMATCH` and both ids; `take_witness(750, expect_write_id=2)` returns `write_id 2`.
- **L4 per-stage attribution (BK-14 class)** — after the two stage publishes, the served meta
  names `stage-b` as last writer (`write_id 2`) while stage-a's word-750 value is named as
  `write_id 1`, i.e. the dual-channel disagreement is attributable per stage by IDENTITY, not
  inferred from mtime.

**Gate B (regression):** `/usr/bin/python3 -m pytest tests/test_gh24_s2_mcp_server.py
tests/test_gh264c_teleop.py tests/test_gh26_emit_admit.py tests/test_gh26_emit_aperture.py
tests/test_gh26_glass_box.py tests/test_gh26_live_surface.py tests/test_bk14_demo.py -q`
→ must stay at `45 passed`, exit 0 (baseline measured by the orchestrator on the clean tree
before this brief was issued; do not "fix" those files if they fail — report instead).

Use `/usr/bin/python3` (the `mcp` module lives in the py3.12 user site, not the repo venv).

HARD RULES: never `git commit`; additive changes only; if a leg needs a design decision that is
not specified above, STOP and report it with evidence rather than guessing. End your reply with a
DIFF SUMMARY (files changed, exact commands run, literal last lines of their output).
