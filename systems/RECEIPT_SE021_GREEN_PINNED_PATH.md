# RECEIPT — SE021 gate green (pinned interpreter), residual red is a PATH artifact

**Measured 2026-09-16 21:4x–22:0x CDT (builder cron `af3e62239ce2`, addendum 147 tick).**
Read-only diagnosis + environment measurement. No engine/shell/test files modified.

## Chain of custody

- The 38-tick red `tests/test_glyph_app_glyph_on_glyph.py::test_control_returns_to_shell_after_exec`
  (`['CHILD_OK', '']`, RCA `.builder_queue/SE021_RED_LEG_RCA_20260916.md`) was fixed by
  the exec-shell lane's landed commits — all ancestors of HEAD `d48ee79`:
  - `d009e0c` 07:47 feat(SE021): green gate — RUN2 (0x12), `_read_path` view-merge, layout v5.1
  - `85922f8` / `a2b0ba4` / `42cd8ff` / `e898bc2` (12:xx) — the (d) handler series:
    SYSCALL 0x03/0x04/0x08/0x09 data dests migrate from image pixels to RAM
    (`tools/glyph_isa_v2.py`), i.e. RCA option (a′) — "file contents are DATA" —
    plus RUN2 and the v5.1/v6 out-of-window dest layout.
- The RCA's maildrop re-ruling ask (`.geos/maildrop/content/hermes.0001.ruling.md`,
  03:00, "pick (a)/(b)+/(c)/GH-25-paging") is **overtaken by events**: the lane landed
  (a′)+(d) and the gate is green under the pinned sweep convention. No ruling needed.

## Measured this tick (own runs, `/usr/bin/python3`, main tree, dirty sib files present)

- Bare-environment run (this cron's inherited PATH):
  `tests/test_glyph_app_glyph_on_glyph.py` → **2 failed / 2 passed** with a NEW
  signature: `['ERR:RUN_DENIED', ' hello']` / `['ERR:RUN_DENIED']` at `:154/:169` —
  **not** the old aliasing red. `[SYSCALL] RUN2: executed glyph_child_runner.py
  (2 args), exit code 1` — the runner itself exits 1.
- Root cause (probe chain `output/se021_repro_147.py` → `se021_spawn_147.py` →
  `se021_diag2_147.py` → `se021_env_147.py`):
  1. `tools/glyph_child_runner.py` is spawned via its shebang
     `#!/usr/bin/env python3` (engine `_spawn`, `tools/glyph_isa_v2.py:603`, argv
     `[resolved] + args`, no explicit interpreter).
  2. This session's inherited PATH puts `/home/jericho/br_scratch/buildroot/output/host/bin`
     FIRST; its `python3` is a symlink to **python3.14** (buildroot cross host tool,
     created 2026-08-12) with **no numpy**.
  3. Copied runner (`GLYPH_REPO`-anchored sys.path is correct) → `import numpy` →
     `ModuleNotFoundError` → rc=1 → shell PRTs `ERR:RUN_DENIED`. A direct
     `[sys.executable, runner]` spawn of the same copied runner returns rc=0 and
     writes `CHILD_OK`; a no-shebang probe import under the same env succeeds.
- Pinned run (the repo's own SUITE-BASE-1 interpreter convention):
  `PATH=/usr/bin:$PATH /usr/bin/python3 -m pytest tests/test_glyph_app_glyph_on_glyph.py -q`
  → **4 passed in 0.36s** (both formerly-red legs, allowlist-deny, dispatch
  regression). n=1 at ~21:5x; the 38-tick determinism of the OLD failure does not
  transfer to this new one — but the mechanism (shebang × PATH order) is
  deterministic given PATH, which the host now carries.

## What this PASS does not prove

- Not a sweep: no repo-wide re-gate this tick (sweeps are exclusive; nothing in
  this lane changed).
- The green is pinned-environment green. Under a PATH where a numpy-less
  `python3` precedes `/usr/bin`, the two exec legs flake by environment —
  a latent fragility, filed as
  `.builder_queue/REPAIR_PENDING_se021_spawn_interpreter_resolution.md`
  (engine `_spawn` resolves the runner's interpreter through the *caller's*
  PATH; cheapest-first options for the exec-shell lane / Jericho).
- `hermes.0001.ruling.md` stays unacked (ack is Jericho's); this receipt only
  records that its question is mooted by `d009e0c`+`a2b0ba4`..`e898bc2`.
