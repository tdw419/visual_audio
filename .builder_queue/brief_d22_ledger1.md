# BRIEF — D22-LEDGER-1: one ledger, one append path

## Spec pointer (READ FIRST)
- Roadmap row D22-LEDGER-1: `systems/GLYPH_SELF_HOSTING_ROADMAP.md:360` — the gate clause there is the contract.
- Live data shapes to match (measured 2026-09-14):
  - Ledger: `.builder_queue/DEFECT-22_arc_legA_instability.json` — 148 keys; leg entries are PROSE STRINGS under keys like `ledger_2026_09_14_1336_leg79`; `series_state` is hand-written: `{"legs_run": 79, "consecutive_worker_scope_green": 51, "last_red": "...", "updated": "2026-09-14 13:3x"}` (unparseable timestamp, prose-derived streak).
  - Example per-leg one-shot writer: `.builder_queue/append_d22_ledger_leg79.py` (49 tracked siblings + 4 untracked).
  - Example per-leg runner (OUT OF SCOPE, do not touch): `.builder_queue/run_d22_leg79.sh`.

## Scope
MAY create/change:
- NEW `.builder_queue/d22_ledger.py` — the single append tool (CLI, argparse). Interface:
  `python3 .builder_queue/d22_ledger.py append --leg N --seed S --head H --crashes C --oom-kill-delta D --mem-peak B --verdict green|red [--note "..."]`
  and `python3 .builder_queue/d22_ledger.py recompute` (rebuilds derived streak fields from the result objects).
  Each append writes a MACHINE-READABLE result object (dict, not prose) under key `ledger_leg<N>` with fields: ts (ISO-8601, parsed at write time), leg, seed, head, crashes, oom_kill_delta, mem_peak, verdict, note.
  Rules: (1) REFUSE an unparseable/inconsistent timestamp — assert or exit nonzero, ledger unchanged on refusal; (2) `series_state.legs_run` and `series_state.consecutive_worker_scope_green` are DERIVED by counting the result objects' `verdict` fields (consecutive green counted from the newest leg backwards to the first non-green) — never hand-written; (3) idempotent per leg — appending an already-present leg exits nonzero without writing.
- NEW `tests/test_d22_ledger_tool.py` — the gate (see below).
- MODIFY `.builder_queue/DEFECT-22_arc_legA_instability.json` — migrate existing `series_state` to derived form; PRESERVE all 148 existing keys/history as-is (old prose entries stay, they are history).
- DELETE the 49 tracked `.builder_queue/append_d22_ledger_*.py` one-shot scripts (git rm) and the 4 untracked ones (`append_d22_ledger.py`, `append_d22_ledger_leg44.py`, `_leg61.py`, `_leg62.py`).

MUST NOT touch:
- `tools/arc_lega_capture.sh`, `tools/gate_arc_lega_capture.sh`, any `run_d22_leg*.sh`, `tools/glyph_gpt/**`, `glyph_dispatch/**`, WGSL shaders, `voicebook/`, `.rts/`, `rs_fixtures.json`. Do NOT commit.

## Gate command
```
python3 -m pytest tests/test_d22_ledger_tool.py -q
```
Expected: all legs pass, exit 0.

## Gate clause (each leg must be a real assertion, falsifiable)
- L1 append: a valid `append` call on a COPY of the ledger adds a dict entry with all eight fields populated and `verdict: green`; exit 0.
- L2 derive: after appends of legs n=green, n+1=green, n+2=red, n+3=green (on a copy), `recompute` yields `consecutive_worker_scope_green == 1` and `legs_run == 4` — computed from fields, not stored by hand.
- L3 refuse: an append with timestamp `2026-09-14 13:3x` (or any unparseable ts) exits nonzero and the ledger file bytes are UNCHANGED (compare before/after).
- L4 single-writer: `git ls-files '.builder_queue/append_d22_ledger*'` returns ONLY `.builder_queue/d22_ledger.py` after the change (this leg runs against the real tree, not a copy).
- L5 idempotence: appending a leg number that already exists exits nonzero, ledger unchanged.

## Failure evidence (RED first)
Before implementing, run the gate against the pre-fix tree and capture the RED: `tests/test_d22_ledger_tool.py` cannot exist yet, so RED = pytest collection error (exit 2) for the missing gate PLUS a stated reason each leg would fail today (prose entries are str not dict; streak is hand-written; no tool exists to refuse timestamps). Paste the RED tail in your report. The gate must be DISCRIMINATING: L2 and L3 must be shown able to fail (e.g. a variant that hand-writes the counter or accepts a bad ts must make them go red — a code-level reasoning statement is acceptable here, a real negative run is better).

## Determinism
Pure file operations, no network, no GPU, no LLM sampling. Pin nothing else.

## Definition of done
Gate green on the real tree; `git status --short` shows only the files listed in Scope; no commit made by you.
