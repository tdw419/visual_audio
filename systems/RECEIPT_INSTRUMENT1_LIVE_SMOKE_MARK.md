# RECEIPT — INSTRUMENT-1: the `live_smoke` mark is registered

**Row:** `systems/GLYPH_SELF_HOSTING_ROADMAP.md` INSTRUMENT-1 · **Ticket:**
`.builder_queue/INSTRUMENT-1_live_smoke_mark_unregistered.json` · **Landed:** `73f8559`
(promotion `34934c6`) · **Builder cron:** `af3e62239ce2` · **Delegate:** `agy`
(exit 0, 783 s, `output/agy/agy_impl_20260913_160228.log`)

## Symptom

`/usr/bin/python3 -m pytest tests/test_arc_determinism_audit.py tests/test_gh20_fs_v2.py -q`
→ `14 passed, 5 warnings in 43.34s`, every warning
`PytestUnknownMarkWarning: Unknown pytest.mark.live_smoke - is this a typo?` raised at the decorator
(`tests/test_gh20_fs_v2.py:475` and its four migrated siblings). 22 `pytest.mark.live_smoke` usages
existed across 5 files; `pytest.ini` declared no `markers` entry.

## Why it was worth a row

pytest filters `-m` by mark **name**, so an unregistered mark still deselects — 9 legs were correctly
deselected at arc `SEED=2026091321`. But an unregistered mark is also the state in which a **typo**
(`live_smok`, `live-smoke`) or a renamed marker deselects **nothing** and silently re-gates arc leg A
on a live Ollama draft, with no error at all. That is precisely the failure class DEFECT-24 and
DEFECT-25 removed; registration (plus `--strict-markers` in the gate) turns it from silent into loud.

## Fix (exactly two files)

- `pytest.ini` — one entry added, every pre-existing line byte-identical:
  ```
  markers =
      live_smoke: non-blocking live model probe excluded from deterministic arc runs
  ```
  No `addopts`, no `--strict-markers` in the config: making strict markers repo-wide would change
  collection behaviour for unrelated runs (e.g. `tests/disabled/test_ollama_discriminator.py` carries
  a second unregistered mark, `slow`) and had no place in this row.
- `tests/test_instrument1_mark_registration.py` (NEW, 154 lines) — L1 registered / L2 discriminating
  RED / L3 non-vacuity / L4 name-match. Force-added: `.gitignore`'s `test_*.py` rule hides it.

## Gate evidence — the orchestrator's own runs, not the delegate's report

| Run | Command (repo root) | Result |
|---|---|---|
| RED, pre-fix tree | `/usr/bin/python3 -m pytest tests/test_arc_determinism_audit.py tests/test_gh20_fs_v2.py -q` | **14 passed, 5 warnings**, all `PytestUnknownMarkWarning: Unknown pytest.mark.live_smoke` |
| GREEN, gate 1 | `/usr/bin/python3 -m pytest tests/test_instrument1_mark_registration.py -q` | **4 passed in 5.91 s**, exit 0 |
| GREEN, gate 2 | `/usr/bin/python3 -m pytest tests/test_instrument1_mark_registration.py tests/test_arc_determinism_audit.py tests/test_gh20_fs_v2.py -q --strict-markers` | **18 passed in 66.75 s**, exit 0 |
| Discriminating leg | the same collect over `tests/test_gh20_fs_v2.py` with the registration synthetically removed (`--strict-markers -o markers=`) | **rc != 0** — `ERROR … Failed: 'live_smoke' not found in \`markers\` configuration option`; `no tests collected, 1 error` |
| Warning delta | unknown-mark warnings over the 4 `live_smoke` files | **5 → 0** |
| Module-absent RED | `git ls-tree 34934c6 tests/test_instrument1_mark_registration.py` | **0 lines** (absent at the promotion commit; absent module ⇒ pytest rc 4, `no tests ran`) |

`agy` reported the same two numbers (4 passed / 18 passed) before I re-ran them; the delegate's report
was not used as evidence.

## What the PASS does NOT prove

- The strict-markers check is **per-invocation**, not in `addopts` — a future unregistered mark used
  outside this four-file set is still only a warning on an ordinary run.
- Only the four collected files are covered; the 22 usages are spelled consistently today, and a new
  misspelling introduced in a *new* file would be caught only where the audit's own Signal 4 looks.
- L4 pins the arc-runner token (`-m "not live_smoke"`) — it does not prove `arc_lega.sh` is the only
  consumer, nor that pytest's `-m` matching semantics stay stable across major versions.
- Nothing about live-model draft quality, and no arc run accompanies a config-only change: the arc was
  not re-run this tick (no engine/transpiler/WGSL/arc file touched; the change is additive config plus
  a new test module, which `tests/test_arc_determinism_audit.py` collects).
