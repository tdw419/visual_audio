# RECEIPT — gh12 gate determinism, OPTION 3 (split the claim)

**Authority:** `.builder_queue/RULING_gh12_gate_determinism.md` (Jericho, 2026-09-13) — decision: **option 3, split the claim**.
**Ticket it closes a component of:** `.builder_queue/DEFECT-22_arc_legA_instability.json` (the **gh12 LLM-gate leg** only).
**Brief:** `.builder_queue/brief_gh12_option3_split.md` (written 2026-09-13 07:0x by cron `af3e62239ce2`; implemented this tick).
**Head when verified:** `d64f509` (branch `glyph-transpiler-autoloop`).
**Implementer:** `agy` lane (`.builder_queue/brief_gh12_option3_split.md`, `TIMEOUT=45m`, exit 0, 472 s,
log `output/agy/agy_impl_20260913_065131.log`). **Gate re-run, probes, arc run and this receipt: the orchestrator.**

## What changed (2 files, `git diff --stat`: 194 insertions / 45 deletions)

- `tests/test_gh12_autoatlas.py` — the model-dependent legs were split:
  - **Deterministic legs (load-bearing, stay in the arc).** `SCRIPTED_POPCOUNT_CANDIDATE` is a fixed glyph program
    (contract + admission-vector + kernel-ABI correct); the legs force the model unavailable
    (`_ollama_available → False`, `OLLAMA_URL → http://127.0.0.1:9`, `_ollama` → returns the scripted text) through
    **both** escalate module identities (`glyph_gpt.escalate`, `tools.glyph_gpt.escalate`) so `ingest()` runs its
    real admission → oracle → kernel re-dispatch → register path against a fixed candidate. Replay leg now compares
    the written atlas **byte-identically** (`reloaded_path.read_bytes() == written_bytes`) instead of "contains".
  - **Live-draft smoke (non-blocking, out of the arc).** `test_live_draft_smoke_nonblocking`
    (`@pytest.mark.live_smoke`) keeps the real `_ollama_available()` path when ollama is up, writes
    `output/gh12_live_smoke_<head>.txt` (`model`, `candidates_tried`, `rc`, `seconds`), and contains **no
    assertion** — its rc cannot fail the module or the arc.
- `tools/arc_lega.sh` — ARGS gain `-m "not live_smoke"` (both the quiet and `VERBOSE=1` forms) and the exclusion
  comment next to the existing `glass_box|gh24_s2_mcp` note names `live_smoke` as the non-blocking model probe.

## Gate legs (each one executed by the orchestrator, output files in-tree)

Gate command: `/usr/bin/python3 -m pytest tests/test_gh12_autoatlas.py -q --tb=line -p no:randomly`

| Leg | Result | Evidence |
|---|---|---|
| **RED before the change** (same head, same command) | `1 failed, 3 passed in 36.76s` — `tests/test_gh12_autoatlas.py:141: AssertionError: no candidate verified in 6 attempts; last: no-halt: 5000 steps without HALT` | `output/gh12_prefix_red_d64f509.txt` |
| **GREEN after, full module** (live smoke included, model reachable) | `6 passed, 1 warning in 11.33s` (rc=0) | `output/gh12_gate_postfix_full.txt` |
| **GREEN after, the arc's own args** (`-m "not live_smoke"`, random seed) | `5 passed, 1 deselected, 1 warning in 1.11s` (rc=0) | `output/gh12_gate_postfix_arcargs.txt` |
| **1. Model-free proof** (orchestrator probe, out-of-tree plugin `/tmp/gh12_probe_plugin.py`) — every escalate identity pointed at port 9 **and** `_ollama` raising, i.e. no reachable model anywhere | `5 passed, 1 deselected` (rc=0) | `output/gh12_orch_probe_model_dead.txt` |
| **2/3. Non-vacuity + negative leg RED** — same plugin, scripted candidate replaced by a candidate that cannot reach the bar | `2 failed, 3 passed, 1 deselected` (rc=1): `test_full_loop_miss_to_verified_kernel_dispatch` + `test_registered_tile_persists_and_replays_offline` both FAIL → the candidate really is executed through admission + replay, and the existing `E_ATLAS_UNVERIFIED` / "atlas unchanged" leg is a live falsifier | `output/gh12_orch_probe_candidate_mutated.txt` |
| **4. Smoke artifact + non-blocking property** | `output/gh12_live_smoke_d64f509.txt` / `..._f2eae4a.txt` written (model tag / candidates / rc / seconds). Injected-failure demonstration: with the live endpoint forced dead (`GH12_PROBE_MODE=smoke_fail`, nothing substituted), the smoke leg records `rc: 1, candidates_tried: 0` and **pytest still reports `1 passed`** — the leg cannot gate | artifact in-tree; `output/gh12_orch_probe_smoke_nonblocking.txt` |
| **5. Arc instrument gate** | `bash tools/gate_arc_lega_naming.sh` rc=0 (4 GREEN lines) | run output |
| **Arc leg A with the change** | **rc=0, crashes=0, 325 passed / 1 skipped / 1 deselected in 123.89 s** at head `d64f509`, seed `2671119501` | `output/arc_lega_seed2671119501_d64f509.txt` + `.json` |

The 1 deselected test is the live smoke; the 1 skipped is the pre-existing py3.11/3.12 `mcp` skip, not a regression.

## Honest boundaries

- **This closes only the gh12 component of DEFECT-22.** The ticket's other measurement — a SIGSEGV inside
  `GlyphCPUv2.step` (`tools/glyph_isa_v2.py:561`, victim frame in `test_gh22_device_driver_abi.py:174`) — is
  **untouched**: it did not reproduce in this tick's arc run (rc=0, crashes=0), and no engine file was modified.
  DEFECT-22 stays open for that leg.
- The smoke leg's non-gating property is **measured, not assumed**: with the live endpoint forced dead by the
  probe plugin (nothing substituted), the leg wrote `rc: 1, candidates_tried: 0` and the pytest run still reported
  `1 passed` (`output/gh12_orch_probe_smoke_nonblocking.txt`). A first attempt at that probe silently used a stale
  copy of the plugin without the `smoke_fail` mode, i.e. it patched nothing — the invalid run is why the artifact
  now records the probe command verbatim. Local check: `PYTHONPATH` must contain the directory holding
  `gh12_probe_plugin.py` (`/tmp` here) **and** the plugin must be the repo copy (`.builder_queue/probe_gh12_gate_split.py`).
- `@pytest.mark.live_smoke` is **not registered** in `pytest.ini`, so the run emits
  `PytestUnknownMarkWarning`. Harmless here (`pytest.ini` sets no `--strict-markers` and no
  `filterwarnings = error`), and `pytest.ini` was left untouched because TEST-COL-1 owns it. Registering the
  marker is a one-line follow-up if the arc ever turns warnings into errors.
- The deterministic candidate is *one* program. The legs prove the admission/replay contract is model-independent;
  they do not claim the live draft path is deterministic — that is exactly what the ruling refused to claim.
