# BRIEF — SPINE-R1 Phase 3 · STEP 5 of 6: `WriteRegistry.scan(root)`

**Row id:** SPINE-R1 step 5 of 6 (authority: `.builder_queue/RULING_lane_supply_20260912.md` § Reserved item 3;
parent plan `.builder_queue/brief_spine_r1_phase3.md`; spec of record `systems/GLYPH_SPINE_SKELETON.md`
§7 item 5 / §4 interface contracts, **LOCKED**).

**Steps 1–4 are landed** (`531bfaa`, `2e10286`, `0bc756a`, `8e7878d`; gates `tests/test_spine_r1_plan.py` 9/9,
`tests/test_spine_r1_compact.py` 7/7, `tests/test_spine_r1_refuse.py` 7/7, `tests/test_spine_r1_register.py` 9/9).
You implement **step 5 only**. Prior work is NOT a precedent to copy — read the current file state first
(`tools/geos_registry.py` at HEAD is the authority).

**Files in scope (only these two):**
- EDIT `tools/geos_registry.py` — implement `WriteRegistry.scan()` (plus AT MOST one private module-level
  helper if needed). Do **not** implement `lookup()` or `conflicts()` — both stay stubs (step 6 / later).
  Do **not** touch `registry_key`, `entry_line`, `index_digest`, `line_sha_for`, `_scan_disk_for_key`, the
  `RegistryEntry` / `ArchiveRecord` dataclasses or their fields, `__all__`, or the `__main__` smoke block.
  Do **not** touch `tools/geos_archive.py`, `tools/geos_emit.py`, `tools/geos_observation_server.py`,
  `tools/geos_witness.py`, `tools/glyph_gpt/**`, `tools/rv64i_to_glyph.py`, `glyph_dispatch/**`, any WGSL,
  `systems/GLYPH_SPINE_SKELETON.md`, or `.builder_queue/**`.
- NEW `tests/test_spine_r1_scan.py` — the gate.

**Stdlib only** in `tools/geos_registry.py` (`json`, `os`, `hashlib` fine); `tools/geos_spine_verify.py`
AST-scans for third-party imports and must stay PASS.

## The rule (decided by the orchestrator — implement EXACTLY this)

`scan(root) -> List[ArchiveRecord]` discovers attributable `(image, sidecar)` pairs under `root`.
Six clauses, all load-bearing:

**S1 — discovery mirrors `ArchiveStore.plan()`'s walk verbatim.** Precedent and authority:
`tools/geos_archive.py:284-325` (read it). Same `os.walk` with `dirs.sort()` / `files.sort()`, candidate
images = suffix `.npy` or `.png`, same pairing rule (`"surface.meta.json"` first if present, else
`f"{stem}.meta.json"`), same *claim* rule (a sidecar is claimed by at most one image — `claimed_sidecars`),
same skips (no sidecar → skip; sidecar that fails `parse_record` / `json.load` / any `OSError` → skip, never
an exception). Build each record with `parse_record(sidecar_dict, image_path=..., sidecar_path=...)`
(already imported). Do not re-implement the pairing differently — the anti-drift leg L8 pins this.

**S2 — deterministic order.** Return records sorted by `(write_id, image_path)` — the same ordering rule
`retention_plan` uses. Two scans of an unchanged tree must be list-equal.

**S3 — negative space is empty, never an exception.** Nonexistent `root` → `[]`. `root` that is a regular
file → `[]`. Empty dir → `[]`. These are the cases `geos_spine_verify.py` leg 4 probes
(`reg.scan("/nonexistent") -> list`).

**S4 — read-only means read-only (this step's BINDING clause).** `scan()` must not create, modify, truncate,
delete, `chmod`, or `touch` anything under `root`, must not create `self.index_path` or its parent directory,
and must not mutate `self.entries` or any other instance state. No `open(..., "a"/"w")`, no `os.makedirs`, no
`os.remove`, no `shutil`.

**S5 — paths are joins, not normalisations.** Use `os.path.join(root, name)` exactly as the walk yields them
(no `abspath`, no `realpath`, no `normpath`), so a caller passing the same root string to
`ArchiveStore.plan()` sees literally the same paths. `bytes_len` / `written_at` / `tags` come from the
sidecar via `parse_record` (no defaults invented here).

**S6 — the ground-truth clause.** The gate must include a **sha256 tree snapshot taken before and after
`scan()` that is byte-identical** (recursive listing of every file's relative path → sha256 + size +
`st_mtime_ns`, plus the sorted directory set), and a *liveness control* proving that same snapshot
function reports a difference when a file is deliberately written between snapshots. A read-only claim
whose checker cannot detect a write is vacuous.

## Gate command (the gate is the deliverable — 8 legs, this exact command)

```
/usr/bin/python3 -m pytest tests/test_spine_r1_scan.py -q
```

Required legs (name them `test_l1_...` … `test_l8_...` in the module):

| Leg | Clause |
|---|---|
| L1 | **discovery basics** — temp root with 3 pairs (`surface.meta.json`): `scan()` returns 3 `ArchiveRecord`s with exact `write_id` / `writer` / `image_path` / `sidecar_path` / `bytes_len` / `written_at` from the sidecars |
| L2 | **read-only proof (S6, BINDING)** — recursive sha256 snapshot before vs after `scan()` identical: same relpath set, same sha256, same size, same `st_mtime_ns`, same dir set; no new file appears anywhere under the root |
| L3 | **snapshot liveness control** — the same snapshot function run around a deliberate write reports a difference (non-vacuous checker) |
| L4 | **skip, not crash** — image with no sidecar skipped; sidecar with no `write_id` skipped; malformed-JSON sidecar skipped; nonexistent root `[]`; root-is-a-file `[]`; empty dir `[]` — and in every case a sibling valid pair is still returned |
| L5 | **pairing rule** — `<stem>.meta.json` fallback when no `surface.meta.json`; `surface.meta.json` preferred when both exist; one sidecar claimed by at most one image (two images whose stem collides → exactly one record) |
| L6 | **determinism** — two scans of the same tree are list-equal (order included); a scan after unrelated `register()` calls on the same instance is unchanged |
| L7 | **no side effects outside `root`** — `scan()` does not create `self.index_path` (assert `not os.path.exists(...)`) even when its parent dir does not exist, and leaves `self.entries` unchanged |
| L8 | **anti-drift equivalence** — on one fixture tree, the record set from `scan(root)` equals the record set `ArchiveStore(root).plan(<evict-everything policy>)` condemns. Measure in a scratch probe which bound actually evicts everything (`keep_total=0` or `keep_per_writer=0`) and state in the test docstring which one you used; compare as sets of `(write_id, writer, image_path, sidecar_path, bytes_len, written_at)` |

## Evidence you must produce (do not paste long output into your report)

1. **RED first:** write the gate, run it against the CURRENT stub `scan()` before implementing →
   `output/spine_r1_step5_red_agy.txt` (must be real assertion failures, not collection errors).
2. **GREEN after:** `output/spine_r1_step5_green_agy.txt` (`-q` tail).
3. **Steps 1–5 gates together:** `/usr/bin/python3 -m pytest tests/test_spine_r1_plan.py tests/test_spine_r1_compact.py tests/test_spine_r1_refuse.py tests/test_spine_r1_register.py tests/test_spine_r1_scan.py -q` → `output/spine_r1_step5_all_gates.txt`, exit 0.
4. **Structural harness:** `/usr/bin/python3 tools/geos_spine_verify.py` → must still print
   `SKELETON VERIFY: PASS` → `output/spine_r1_step5_spine_verify.txt`.
5. **Arc regression:** `/usr/bin/python3 -m pytest tests/test_gh*.py tests/test_bk*.py tests/test_eng*.py -q` → exit 0 → `output/spine_r1_step5_arc.txt` (this takes ~140 s; run it once, save, do not re-run).

## Hard constraints

- **Interfaces are frozen.** No signature or dataclass-field changes; if one seems wrong, STOP and report
  (that is a skeleton-sign-off change, not a builder call).
- **Additive only. Do NOT COMMIT.** Leave the tree dirty; the orchestrator re-runs the gate, checks
  `git status --short`, and commits.
- Report **≤30 lines**: what you implemented, the literal last line of the gate run, which L-legs failed
  before the fix, evidence file paths, and anything you did NOT verify.
