# RECEIPT — DEFECT-20: publish-path write identity (witness attribution)

**Row:** DEFECT-20, `systems/GLYPH_SELF_HOSTING_ROADMAP.md` (promoted this tick at `0db32fe`)
**Source ticket:** `.builder_queue/DEFECT-20_snapshot_last_write_wins.md` (fix preference (b) + (a))
**Branch:** `glyph-transpiler-autoloop` · **Builder cron:** `af3e62239ce2` · **Date:** 2026-09-12
**Implementer:** `agy` lane (brief `.builder_queue/brief_defect20_write_identity.md`) · verification,
probes, receipt, roadmap and commit: orchestrator (this run).

## What was broken

`tools/geos_emit.py` published with ONE fixed filename (`IMAGE_NAME = "kernel_memory.npy"`, line 40)
and one sidecar (`META_NAME = "surface.meta.json"`, line 41), both overwritten by every publish in
`_commit()`. The committed snapshot therefore only ever represented the LAST writer, and a substrate
witness was identifier-free: it could be a true statement about the wrong write. Measured
2026-09-12 in the BK-14 dual-channel re-verification — word 703 matched across channels because no
later stage touched it, while words 750 (argv, stage 1) and 754 (result) did not, because later
stages rewrote those words for unrelated purposes.

Consequence for the loop: the roadmap's Substrate-witness rule (roadmap line 139, amended at
`bdbda3b`) now *requires* every substrate-verdict row to name the write it corroborates — a clause
no gate could satisfy while this defect stood.

## Mechanism landed

| File | Change |
|---|---|
| `tools/geos_emit.py` | `_commit()` gains a monotonic `write_id` (read from the existing sidecar, `+1`) plus `writer` and `written_at` (ISO-8601 UTC) **added** to `surface.meta.json`; every publish also writes an archived pair `<publish_dir>/archive/kernel_memory.<write_id>.npy` + `surface.meta.<write_id>.json` so an earlier write's words survive a later publish; the intent's optional `"writer"` field is threaded through all four kinds (`post`/`clear`/`claim_ticket`/`signal_done`), default `"unattributed"`. Existing keys (`tick`, `step`, `source_md5`, `canonical`, `emit`) and the `E_ACK` human gate are unchanged. |
| `tools/geos_observation_server.py` | Read path refactored to one `_find_image_path()`/`_load_memory(img_dir=None)` pair (additive default arg) so the served image and its metadata cannot disagree; new `_get_source_info()` surfaces `write_id`, `writer`, `written_at`, `sidecar_file`, `image_md5` in `meta["source"]`, all `null` when no sidecar exists. `geos_surface_meta()` docstring documents the new fields. |
| `tools/geos_witness.py` | NEW. `take_witness(word, expect_write_id=None, image_dir=None)` returns `{word, value, write_id, writer, image_file, sidecar_file, image_md5, age_seconds}` and raises `WitnessMismatch` (`WITNESS_MISMATCH: served write_id <n> != expected <m>`) instead of silently returning a wrong-write reading; `load_archived_write(write_id, publish_dir)` retrieves an earlier write by identity. It imports the observation server's own `_load_memory`/`_get_source_info`, so witness and read share one code path. |
| `tests/test_defect20_write_identity.py` | NEW gate, 4 legs (L1 monotonic identity + archive retrievability, L2 meta exposure incl. the no-sidecar null case, L3 loud attribution, L4 BK-14-class per-stage attribution). |
| `tools/glyph_gpt/runner.py` | Launcher publish path (`_publish()`) now stamps the same identity into its sidecars: `write_id` (`max(existing *.meta.json write_id, 0) + 1`, tolerant of an unreadable sidecar), `writer` (`"canonical"` for the canonical publish, the tag with its leading `_` stripped for per-tick publishes), `written_at` (ISO-8601 UTC). Line-count invariant respected: `runner.py` stays at **200 lines** (the GH-5 gate counts `splitlines()`), paid for by compressing three docstring/comment blocks in the same file — no behaviour change beyond the added keys. |
| `tests/test_defect20_write_identity.py` L5 | NEW leg `test_l5_runner_path_identity`: the BK-14 dual-channel shape (emitter stage writing word 750 into a seeded dir, then `GlyphRunner.drive(publish_dir=...)` into the SAME dir) — every top-level artifact carries a unique `write_id`, the canonical sidecar names the launcher (`writer == "canonical"`) with the highest id, the served meta agrees, `take_witness(750, expect_write_id=<stage-a>)` refuses loudly, and stage-a's bytes remain retrievable and attributed to write 1 from the archive. |

**Why the second half was needed:** the ticket's amended acceptance criterion (`.builder_queue/DEFECT-20_snapshot_last_write_wins.md`, commit `06e5053`, landed mid-run by a parallel session) requires the BK-14 dual-channel reads to be *attributably* agreeing — "every substrate-read word traced to the stage that wrote it (stage id + write id), not merely match numerically". Before this half, the launcher's canonical publish overwrote the emitter's identified sidecar in the demo's publish dir, so the final snapshot of the dual-channel flow was unattributed (`runner.py:117-121` had no identity at all). The delegation for this second kind of change correctly STOPPED rather than guessing the id arithmetic (agy's report: "Files changed: None", 200-line file, gates untouched); with the delegation budget for this defect spent, the orchestrator implemented it under the loop's fallback rule and verified it with the probes below. |

## Gate A — the row's gate (own run, not agy's claim)

```
$ /usr/bin/python3 -m pytest tests/test_defect20_write_identity.py -q
....                                                                     [100%]
GATE_A_EXIT=0
```
junit (`output/defect20_gate_run3_green.xml`): **tests=4, errors=0, failures=0, skipped=0**
(legs: `test_l1_monotonic_identity`, `test_l2_meta_exposure`, `test_l3_loud_attribution`,
`test_l4_per_stage_attribution`).

After the runner half (final run on the committed tree):

```
$ /usr/bin/python3 -m pytest tests/test_defect20_write_identity.py -q
.....                                                                    [100%]
GATE_A_EXIT=0
```
junit (`output/defect20_gate_run4_l5.xml`): **tests=5, errors=0, failures=0, skipped=0** — L1..L5.
(Interim RED, kept for the record: adding the launcher identity first made L1..L4 fail
(`assert 4 == 2` at `:151`) because the gate's `_publish_dir` helper left the launcher's own
sidecars in the dir and `GeosEmitter` derives its counter from them; the helper now removes them,
with the reason in its docstring, and L5's uniqueness assertion was corrected to match the defect's
actual shape — the emitter's write-1 sidecar is *replaced* by the launcher's canonical publish,
surviving only in the archive. `output/defect20_gate_run4_l5.txt` records the final green.)

RED first (this run, before the delegation): `output/defect20_gate_run1_red.txt` —
`ERROR: file or directory not found: tests/test_defect20_write_identity.py`, pytest exit **4**.
(Note: `.gitignore`'s `test_*.py` rule hides test files from `git status`; the gate file is
force-added at commit time.)

## Gate B — regression on the touched surface (own run)

```
$ /usr/bin/python3 -m pytest tests/test_gh24_s2_mcp_server.py tests/test_gh264c_teleop.py \
    tests/test_gh26_emit_admit.py tests/test_gh26_emit_aperture.py tests/test_gh26_glass_box.py \
    tests/test_gh26_live_surface.py tests/test_bk14_demo.py -q
.............................................                            [100%]
GATE_B_EXIT=0
```
Baseline measured by the orchestrator on the clean tree **before** the brief was issued: same 45
dots, exit 0 (no delta). `output/defect20_gateB_green.txt`.

## Arc regression (own run)

```
$ /usr/bin/python3 -m pytest tests/test_gh*.py tests/test_bk*.py tests/test_defect*.py \
    tests/test_eng1*.py -q --junitxml=output/arc_verify_defect20.xml
....................s.                                                   [100%]
ARC_EXIT=0
```
junit: **tests=342, errors=0, failures=0, skipped=1, 142.2 s** (55 files). The previous recorded arc
(`output/arc_verify_wf1_junit.txt`, `3e2bd8e`+WF-1) was 328 passed / 2 skipped; the delta is the
tests landed since (WF-1's 5 + this row's 4 + …), and 0 failures either way.

## Non-vacuity probes (orchestrator, on temporary copies — both reverted)

Both probes mutated the landed file in place, ran ONE leg, then restored the file from a backup;
`md5sum -c /tmp/pre_defect20.md5` confirmed both files byte-identical afterwards.

| Probe | Mutation | Result |
|---|---|---|
| archive leg | `archive_img_scratch.write_bytes(data)` / `os.replace(...)` → `pass` in `tools/geos_emit.py` | **L1 FAILED** — `AssertionError` at `tests/test_defect20_write_identity.py:113` (`archive/kernel_memory.1.npy` missing), pytest exit 1 (`output/defect20_falsification_archive_probe.txt`) |
| refusal leg | `if expect_write_id is not None and served_write_id != expect_write_id:` → `if False:` in `tools/geos_witness.py` | **L3 FAILED** — `Failed: DID NOT RAISE WitnessMismatch` at `tests/test_defect20_write_identity.py:212`, pytest exit 1 (`output/defect20_falsification_witness_probe.txt`) |
| launcher identity | `write_id` / `writer` / `written_at` removed from `tools/glyph_gpt/runner.py::_publish()`'s sidecar dict | **L5 FAILED** (`KeyError: 'writer'` at `tests/test_defect20_write_identity.py:314`) while **L1..L4 stayed green** — the leg is specific to the launcher path, not a global crutch (`output/defect20_falsification_runner_identity_probe.txt`) |

So the gate is load-bearing on both the fix and the refusal, not vacuous.

## Orchestrator probes beyond the gate

1. **Real deployment dir, no sidecar** (`output/defect20_live_probe.txt`) — `geos_surface_meta()`
   against the live default `/tmp/geos_observation`:
   `{"image_file": "kernel_memory.npy", "age_seconds": 162277.5, "write_id": null, "writer": null,
   "written_at": null, "sidecar_file": null, "image_md5": null}` → no crash, and the image is
   correctly reported as **unattributed** rather than silently inheriting an identity. The live
   canonical snapshot is ~45 h stale (teleop discipline: freshness is a property of the
   relationship).
2. **Archive cannot leak into the read path** (`output/defect20_archive_visibility_probe.txt`) —
   a dir containing only `archive/kernel_memory.1.npy` (no top-level image) resolves to
   `_find_image_path -> None` and all-null source fields: the glob is non-recursive, so archived
   writes can never be served as "the newest .npy".

## Honest boundaries (not claimed)

1. The counter is a read-modify-write on the sidecar with **no locking**: it is monotonic per
   writer, but two concurrent emitters publishing into one dir can collide on a `write_id`. The
   publish path's blast radius is one directory and the loop is single-writer today.
2. Attribution quality is the caller's `"writer"` field; an emitter that never sets it produces
   `"unattributed"` — machine-readable, but not self-describing.
3. Archives accumulate without a retention policy (one `.npy` + one `.json` per publish; the GH-26
   image is 256×256 ints — 128 KB/word-block per write here).
4. The read path still falls back to the newest `*.npy` by mtime when `kernel_memory.npy` is
   absent; a foreign `.npy` dropped in the dir can still be served — now at least with its
   (possibly null) identity reported.
5. Nothing here delivers a *resident* witness relation: the witness is still taken by a teleoperator
   from outside (B-state), and `age_seconds` remains the only freshness signal for an unattributed
   image. Tier C stays parked (`RULING_TIERC_substrate_initiated_prompt.md`).
6. "Attributably agreeing" is per publish directory: the launcher keeps one top-level artifact per
   tag plus the canonical one, and the emitter archives its writes, so per-stage retrieval is by
   identity within one dir. Cross-directory/global ordering is not claimed (no shared registry), and
   the ticket's own line in `.builder_queue/DEFECT-20_snapshot_last_write_wins.md` is literally
   truncated mid-sentence (`...criterion....[truncated]`) as committed by the parallel session — this
   receipt satisfies the criterion as written up to that point.
