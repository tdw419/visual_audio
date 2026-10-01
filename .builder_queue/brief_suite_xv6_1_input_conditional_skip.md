# BRIEF — SUITE-XV6-1: make the xv6 boot gate's skip path INPUT-CONDITIONAL and land the gate file in git

## Spec pointer (read first)
- `systems/GLYPH_SELF_HOSTING_ROADMAP.md:357` — row **SUITE-XV6-1**. Its GATE has three legs; legs (a) and (b) are already implemented in the working tree (the test skips loudly naming `KNOWN-BROKEN-INPUT`); leg (c) is unreachable here (no non-RVC kernel on this box). This brief lands (a)+(b) as a **tracked** artifact **plus the non-vacuity leg that proves the skip is input-conditional** (today it is not — see RED below).
- `tests/XV6_BOOT_STATUS.md` — why `boot_images/xv6.img` (275248 B, present) is KNOWN-BROKEN-INPUT.
- `AGENTS.md` — Evidence Discipline: a verification that cannot fail is not a verification.

## RED (measured this tick, 2026-09-13, /usr/bin/python3 — do not "fix" this by deleting the probe)
```
$ /usr/bin/python3 /tmp/orch_probe_suite_xv6_1.py     # sets XV6_KERNEL_PATH to a temp file with ELF magic
probe: module XV6_KERNEL=/tmp/xv6-riscv/kernel/kernel
C1 env-override honored : exists=False path=None
PROBE_VERDICT=RED
```
The check is hardcoded to `/tmp/xv6-riscv/kernel/kernel`: no caller can present a kernel, so the "skip" is
**unconditional in practice** — it can never be shown to be input-conditional, i.e. it is a probe that cannot
go red. Also measured: the file is **untracked** (`git ls-files` → no match; `git check-ignore -v tests/test_xv6_boot_regression.py` → rc=1, NOT ignored), so the gate artifact has no commit history.

## Scope
**MAY change (one file, exclusive write set):**
- `tests/test_xv6_boot_regression.py`

**MUST NOT change:** `boot_images/xv6.img` (protected input, do not add/remove/replace), any other test file,
any file under `src/`, `tools/`, `glyph_dispatch/`, or the WGSL shaders. Do **not** delete, weaken, xfail, or
skip any existing assertion. Do **not** run the GPU boot path. Do **not** `git add` or commit (the orchestrator
stages and commits after its own verification).

## Required changes (all in that one file)
1. **Kernel path becomes caller-controllable, default unchanged:**
   `XV6_KERNEL = Path(os.environ.get("XV6_KERNEL_PATH", "/tmp/xv6-riscv/kernel/kernel"))`
   (add `import os` if needed). Call sites stay working: keep `check_xv6_kernel_exists()` callable with **no
   arguments** and with the same 3-tuple return `(exists: bool, msg: str, path: Optional[Path])`.
2. **Machine-readable verdict token in the skip reason**, prefix each reason with exactly one of:
   - `INPUT-ABSENT` — no kernel at the checked path and no fallback present
   - `KNOWN-BROKEN-INPUT` — the RVC `boot_images/xv6.img` fallback exists and is being deliberately not run
   Keep the existing human explanation (RVC misdecode, PC cycling 0x80000c7c, pointer to XV6_BOOT_STATUS.md).
   The KNOWN-BROKEN-INPUT branch must NEVER return `exists=True` and must NEVER launch a boot.
3. **Non-vacuity leg (pure function, no GPU, always runs — this is the leg that makes the skip falsifiable):**
   a test in the same file that points `XV6_KERNEL_PATH` at temp files it creates and asserts:
   - (i) ELF-magic file → `check_xv6_kernel_exists()` returns `exists=True` and `path` == that file (skip does NOT fire);
   - (ii) non-ELF file → returns `exists=False`, reason contains `not a valid ELF`;
   - (iii) nonexistent path with the fallback temporarily pointed elsewhere (use a monkeypatched module
     attribute, e.g. `monkeypatch.setattr(mod, "XV6_KERNEL_FALLBACK", Path(tmp)/"absent.img")`) → returns
     `exists=False`, reason starts with `INPUT-ABSENT`;
   - (iv) fallback-only case → returns `exists=False` and reason contains `KNOWN-BROKEN-INPUT`.
   The leg must be deterministic (tmp_path fixture only, no network, no GPU, no randomness) and must not
   mutate `os.environ` in a way that leaks (use `monkeypatch.setenv`).
4. Do not raise `BOOT_TIMEOUT`/`MAX_INSTRUCTIONS`; do not touch the boot execution path at all.

## Gate command (orchestrator runs it; delegate must run it too and paste tails)
```
cd /home/jericho/projects/zion/projects/visual_audio
/usr/bin/python3 /tmp/orch_probe_suite_xv6_1.py                      # expect PROBE_VERDICT=GREEN (RED above)
/usr/bin/python3 -m pytest tests/test_xv6_boot_regression.py -q -rs -p no:randomly
```
Expected: the probe prints `GREEN` (exit 0); pytest reports the new pure-function leg(s) **passing**, the 2
GPU legs **skipped** with the token-bearing reason, **exit code 0**, and the whole run finishing in **under
5 s** wall clock (measured pre-change: `2 skipped in 0.14s`; the 2026-09-13 sweep recorded `TIMEOUT` at
150.06 s for this file — that is the burn this row exists to end).

## Gate clause (falsifiable)
- `PROBE_VERDICT=GREEN` — with `XV6_KERNEL_PATH` set to an ELF file the check returns `exists=True`; with a
  non-ELF file it returns `False` + "not a valid ELF". Before this change it returns `False` in both cases.
- pytest exit code 0, no `failed`, no `error`, ≥1 pure-function test passed, exactly 2 skipped carrying
  `KNOWN-BROKEN-INPUT`, wall clock <5 s.
- **REFUSED by design:** running `boot_images/xv6.img`; deleting/skipping the GPU legs outright; any change
  outside `tests/test_xv6_boot_regression.py`.

## Failure evidence requirement
The gate must be shown able to go RED before it is trusted: the RED tail above is the orchestrator's, and the
delegate must confirm it reproduced (`PROBE_VERDICT=RED` on the pre-edit file) or state plainly that it could
not. A green that cannot be made red is decoration.

## Deliverable
Files changed: `tests/test_xv6_boot_regression.py` only. No commit. Reply with a DIFF SUMMARY block naming the
file, the change, and both gate tails (RED before, GREEN after).
