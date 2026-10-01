# RECEIPT — L3 sub-step 4: `&&`/`;` sequencing and `$?` exit status

Status: LANDED
Date: 2026-09-24 ~09:4x CDT
Layer: SUPPLY_ROUND8.json → L3-PROCESS, sub-step 4 (`&&`/`;` command sequencing, short-circuit on failure, and `$?` exit status expansion).

## Scope

POSITIVE:
- experiments/glyph_l1_shell.py —
  - `self.last_status: int`: tracks the 0x05 / POSIX exit status across turns (0 on success, 1 on error/ERR:).
  - `$?` expansion: replaced with `str(self.last_status)` before command execution.
  - `;` sequencing: commands execute unconditionally in order, outputs joined with newline.
  - `&&` conditional sequencing: commands execute in order; if any segment fails (returns `ERR:` or sets non-zero status), execution short-circuits immediately.
  - Single turn dispatch isolated to `_turn_single(stripped)`.
- tests/test_l3_pipes.py — extended with S1–S8 test legs (32/32 passing).
- .builder_queue/probe_l3_seq_red.py — RED probe (kept artifact; 4 failing legs pre-fix -> 0 failing legs post-fix).
- .builder_queue/RECEIPT_L3_pipes_sequencing.md — this file.
- .builder_queue/PRODUCT_LANE_STATE.md — updated to reflect L3 complete.

NEGATIVE (git diff --stat at landing): tools/ (except dogfood updates), glyph_dispatch/, WGSL shaders, docs/, rot-guard, protected assets (voicebook/, .rts/, rs_fixtures.json) — untouched.

## Design

- Precedence: `;` splits at the outermost boundary (lowest precedence), followed by `&&` conditional sequencing, followed by pipes (`|`) and input redirection (`<`).
- Short-circuit semantics: for `cmd1 && cmd2`, if `cmd1` returns `ERR:...` or leaves `last_status != 0`, `cmd2` never executes (verified by `test_s2_and_short_circuit_on_failure`).
- Exit status variable: `$?` allows scripts and AI agents to inspect the exit code of the preceding operation (0 for success, 1 for errors).

## Gate Arc

RED-first, measured via `.builder_queue/probe_l3_seq_red.py`:
- 4 failing legs pre-fix:
  - Leg 1: `&&` did not sequence (treated as literal echo payload).
  - Leg 2: `&&` failed to short-circuit.
  - Leg 3: `;` failed to sequence.
  - Leg 4: `$?` was not expanded to exit code.
- Post-fix: 4/4 GREEN, 0 failing legs, 0 keep failures (exit code 0).
- Pytest gate: `tests/test_l3_pipes.py` 32/32 passed.
- Regression family: `test_l1_shell_personality` + `test_l2_files` + `test_l3_pipes` + `test_bk15_file_list` + `test_glyph_interactive_shell` + `test_glyph_text_console` = 93 passed, 0 failed.
- Parity & WGSL sanity: `test_bk12_wgsl_tier` + `test_bk2_wgsl_syscall_parity` + `test_gh4_wgsl_parity` + `test_glyph_app_shell_dispatch` + `test_item11_dispatch_grammar` + `test_wgsl_triple_sync` = 30 passed, 0 failed.
- Continuous Dogfood: `tools/dogfood_gpu_os.py` = 7/7 passed in 613ms.
- Ollama Interactive Test: `tools/test_ollama_gpu_os_interactive.py` = 9/9 passed, Overall Verdict: PASS.

## What the PASS does NOT prove (honesty)

- Only `&&` and `;` are supported; `||` (OR chaining) and subshell grouping `(cmd)` are left for later layers.
- `$?` expands the immediate prior integer status; environment variable expansion (`$VAR`) is not implemented.
