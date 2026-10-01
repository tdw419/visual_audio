# RECEIPT — BK-25: Workbench Session Root staging primitive (items 22+23
# merged) + landing-time defect fix in the shell's python verb

**Landed:** 2026-09-25 ~01:4x CDT, builder af3e62239ce2 (Glyph OS Event
Chain cron). HEAD at tick start: 78a8c6a5 (this lane's own BK-24
root-cause commit; re-verified at tick start per the parallel-session
rule). Supply: PRODUCT_LANE_STATE.md ROUND 11 ADDENDUM — items 22+23 are
ONE mechanism ("stage files where the shell can see them") with TWO
verification contexts. Claimed the lowest-numbered queue item whose
prerequisites were green: item 18 (BK-24) is ACTIVELY OWNED by a parallel
session in worktree `~/zion/worktrees/bk24-rowfix` (fix option (a)
cols_instrs=32 already applied there, probes run 00:39–00:43 CDT, ~40 min
before this tick — NOT touched, NOT duplicated); item 19 depends on 18;
the Round-10 addendum declares 22 independent of 18/19/20/21.

## What landed

1. `tools/stage_workbench.py` — the staging primitive:
   - `stage_workbench(manifest, base=None)`: builds a SHORT-path session
     root (PATH_CAP=48 checked BEFORE any write — ValueError names the
     measured constraint) with the layout contract
     `w.dat + bin/ + scripts/ + tests/`; manifest entries symlinked
     (tests keep valid REPO anchors); literal `content` entries written.
   - `unpack_manifest(manifest, base=None)`: the item-23 container
     context — SAME layout, but entries are COPIES (a container payload
     must not depend on the staging machine's tree).
   - Import-root contract: both plant `experiments/ tools/ src/` package
     dirs in the root — staged tests import the shell as
     `experiments.glyph_l1_shell`, and the shell's python shim puts the
     session root FIRST on PYTHONPATH.
   - Both default `base` to a short `/tmp/gwb_*` dir: pytest's tmp_path
     is ~90 chars and can NEVER satisfy PATH_CAP (measured during gate
     authoring; the RED legs drive the refusal explicitly).

2. `tests/test_bk25_stage_workbench.py` — the gate (7 legs):
   G1 layout + PATH_CAP under a staged root; G2 the shell boots in the
   staged root (write/ls/cat work); **G3 the Stage-2 gate itself:
   `python -m pytest -q` run AS A SHELL TURN passes 14/14** (hermetic
   lane-family fixtures: BK-22 + item-11 grammar — no toolchain, no
   wgpu, no scipy); G4 the unpack context passes the same contract;
   N1a long-root refusal stays live; N1b layout assert goes RED; N1c
   corrupted staged copy makes G3 FAIL (non-vacuity, run via the COPY
   context so a mutation can never reach the repo through a symlink).

3. `experiments/glyph_l1_shell.py` — landing-time defect fix
   (8 lines, surgical): `_run_python_proc` BUILT the contained env
   (GLYPH_L1_ROOT + session-first PYTHONPATH, line 958-961, landed with
   the python verb at c0931a7d) but NEVER PASSED it to `subprocess.run`
   — every `python` turn silently inherited the parent environment. The
   python verb has been running UNCONTAINED since it landed. Found by
   the G3 leg (shell-turn pytest failed while the identical
   subprocess-with-env call passed); fixed by passing `env=env`.

## Evidence

RED-first (gate pre-landing, module files stashed):
```
ERROR: file or directory not found: tests/test_bk25_stage_workbench.py
no tests ran
```
RED on the un-fixed shell (env bug present, gate + tool staged):
```
FAILED tests/test_bk25_stage_workbench.py::test_g3_inshell_pytest_passes
E  assert 'passed' in 'ERR:PYTHON:1 error in 0.13s'
1 failed, 6 passed in 0.54s
```
GREEN at landing (this tree):
```
7 passed in 0.59s          (tests/test_bk25_stage_workbench.py)
```
Regression family (post-fix):
```
79 passed in 1.82s   (bk25 + l1 personality + bk22 + item11 + l3 pipes + l4 desktop)
4 passed in 1.41s    (tests/test_bk23_dogfood_ci_gate.py)
dogfood: exit=0, 8 PASS, 0 FAIL   (tools/dogfood_gpu_os.py)
```
Discrimination demonstrated: with the shell fix stashed the G3 leg goes
RED (1 failed / 6 passed), with the fix restored it goes GREEN — the
gate provably pins the env-passing fix.

## What this does NOT prove

- The one-file CONTAINER carrier itself is untested: unpack_manifest is
  the payload materialization contract; the actual installer packing
  (item 23's format decision) is explicitly deferred to landing of that
  item.
- Staged pytest still runs on HOST CPython (the shell's python shim is a
  Phase-2 substrate per the round-11 doctrine split). No GPU-image
  execution is claimed.
- No WGSL twin of the staging path (host-side layout primitive; nothing
  spatial to twin).
- The staged pytest legs use two hermetic suites; bigger lane-family
  coverage (scipy/wgpu/toolchain tests) is future work and may need
  content-staging of data fixtures.
- Single host, no floors/rate claims (none cited).

## Discipline notes

- One write-side-effect incident, caught and repaired in-session: the
  original N1c leg corrupted a staged SYMLINK, which wrote through to
  the repo's tests/test_item11_dispatch_grammar.py (tracked file).
  Restored from HEAD immediately (8/8 green re-verified) and the leg was
  rewritten to use the copy context so the corruption physically cannot
  leave /tmp. This is exactly the teleop-discipline failure mode the
  skill warns about — receipted here so the pattern is searchable.
- BK-24 files (tests/test_gh23_libc_runtime.py,
  tools/glyph_gpt/{libc_runtime,baker,autoatlas}.py) untouched by this
  tick; they remain the bk24-rowfix worktree's in-flight surface.
