# BRIEF — SUITE-XV6-2: the xv6 boot oracle gets a committed, checksummed input and a bounded, token-bearing verdict

## Spec pointer (READ FIRST)

1. `systems/GLYPH_SELF_HOSTING_ROADMAP.md:358` — the row you are implementing (read its GATE clause literally; it is the spec).
2. `systems/RECEIPT_SUITE_XV6_1_INPUT_CONDITIONAL_SKIP.md` — §6 is the provenance for this row; §4 lists what the previous unit already landed.
3. `tests/test_xv6_boot_regression.py` — the file you are extending (read all 378 lines first).
4. `tools/boot_xv6_gpu.py:340-395` (kernel segment load + fs.img load) and its `main()` at `:934-963`.

Measured facts you can rely on (re-verified by the orchestrator this tick, no need to re-derive):
- `boot_images/xv6-riscv.img` — 286328 B, sha256 `9ca0c366a69833f511b4a2848cb3038c1e816ee8ce9c3ac9cad07fd726ed6a27`, ELF64 RISC-V, `e_flags=0x0` (RVC CLEAR).
- `boot_images/xv6-riscv-fs.img` — 2048000 B, sha256 `f31516ca7bb190f38d6ef71ef7e488ee4d07d50700dd06c6ecbec53e0d4841ed`, xv6 superblock `0x10203040` at offset 1024.
- Both are ignored by `.gitignore:66` (`*.img`) ⇒ they need `git add -f`.
- `tools/boot_xv6_gpu.py:385` hardcodes `Path('/tmp/xv6-riscv/fs.img')`, and `/tmp/xv6-riscv/` DOES NOT EXIST on this machine.

## Scope (exactly these files may change)

- `tools/boot_xv6_gpu.py` — **ONLY** the fs-image load region (~`:384-390`): make the path caller-controllable as `Path(os.environ.get("XV6_FS_PATH", "/tmp/xv6-riscv/fs.img"))`. Default MUST stay `/tmp/xv6-riscv/fs.img`. Add `import os` only if absent. No other line of this file may change.
- `tests/test_xv6_boot_regression.py` — sha256 pins, fs-path wiring, bounded duration + token-bearing verdict.
- `boot_images/xv6-riscv.img`, `boot_images/xv6-riscv-fs.img` — `git add -f` (binary, no content edit).
- NEW files you may create: one probe under `.builder_queue/` and evidence under `output/`. Nothing else.

MUST NOT touch: `tools/glyph_gpt/baker.py`, `tools/rv64i_to_glyph.py`, `glyph_dispatch/**`, any WGSL shader, any engine file, `systems/GLYPH_SELF_HOSTING_ROADMAP.md` (the orchestrator edits the row), `voicebook/`, `.rts/`, `rs_fixtures.json`. Do NOT commit. Do NOT `git add -A`; stage only the in-scope paths and `git diff --cached --stat` before you stop.

## Gate command (run it; paste the tail literally)

```
XV6_KERNEL_PATH=boot_images/xv6-riscv.img /usr/bin/python3 -m pytest tests/test_xv6_boot_regression.py -q -p no:randomly
```

## Gate clause (falsifiable criteria)

**L1 — committed input, pinned by hash.** `git ls-files boot_images/xv6-riscv.img boot_images/xv6-riscv-fs.img` prints both paths. In-test, both files' sha256 are asserted against the literals above; a mismatch produces a token-bearing refusal (see L4) and never a silent pass. A test that only checks `exists()` does NOT satisfy this.

**L2 — caller-controllable fs path, default unchanged.** `run_xv6_boot()` passes `XV6_FS_PATH` to the child (inheritance is enough — do not rewrite the subprocess call's shape), and the boot leg sets it to the in-repo `boot_images/xv6-riscv-fs.img`, so the boot no longer depends on `/tmp/xv6-riscv/fs.img`. With `XV6_FS_PATH` unset, `tools/boot_xv6_gpu.py` must still resolve `/tmp/xv6-riscv/fs.img` — prove this by a probe that imports/`grep`s the resolved default and prints it (do not run a boot for this leg).

**L3 — bounded duration.** No single pytest invocation of this file may be able to spend more than a bounded wall-clock value that YOU state and assert. Today `BOOT_TIMEOUT = 300` plus the determinism leg booting twice = the 601 s silent burn the row names. Reduce to a stated bound (e.g. one boot ≤ 240 s; the determinism leg must NOT boot twice when the first does not reach the shell) and assert the bound in-test.

**L4 — token-bearing verdict, never a bare AssertionError.** Every terminal outcome maps to a distinct token that appears in the failure text and in stdout, e.g. `XV6_VERDICT: SHELL_REACHED` / `NO_SHELL_STALL_PC_0x…` / `NO_SHELL_TIMEOUT_<secs>s` / `INPUT_SHA_MISMATCH` / `FS_ABSENT` / `LSB_FORMAT_UNSUPPORTED`. The RED message must NAME the class (kernel/toolchain vs MMU/RVC path vs fs/image load) drawing on the captured PC/iteration metrics — `assert False, "xv6 did not reach shell"` is the defect this leg exists to remove.

## Failure evidence (RED first — required)

1. Run the L1/L2/L4 legs against the **pre-fix** source (`git show HEAD:tests/test_xv6_boot_regression.py`) and paste the RED: no sha256 pin, `/tmp` path, bare `AssertionError`.
2. Non-vacuity of L4: corrupt ONE byte of a **temp copy** of the kernel, point `XV6_KERNEL_PATH` at the copy, and paste the token-bearing refusal (`INPUT_SHA_MISMATCH`) — never mutate the real file, and re-verify the real file's sha256 after.
3. Non-vacuity of the bound: state which leg would have to run twice for the budget to be exceeded and show the assertion firing (a unit-level call of the budget predicate is acceptable if it prints the numbers).

## Determinism clause

The gate is CPU-only and must be green with the GPU idle; the one GPU-touching artifact is the **synthetic** non-shell probe below, which must run under 60 s. A parallel sibling lane is using the GPU (measured `nvidia-smi` 36 %, 9.9 GiB used at brief time) — do NOT run the real xv6 boot, do NOT run sweeps, do NOT run `-w >1`. The orchestrator runs the real boot.

**Bounded synthetic probe (allowed, one short run):** an infinite-loop RV64 ELF written to `tmp_path`, booted with a small `BOOT_TIMEOUT`, must terminate with a token-bearing non-shell verdict rather than hanging. This is the proof that L3/L4 work without the real kernel.

## Soft fields

- Interfaces LOCKED: `check_xv6_kernel_exists()` and `extract_boot_metrics()` keep their names and signatures; the `XV6_KERNEL_PATH` contract already landed in SUITE-XV6-1 stays byte-compatible.
- Definition of done: all four legs implemented, RED pasted, `git diff --cached --stat` showing only in-scope paths, and a `output/` evidence file per leg.
- Never weaken a live guard to make a step pass: the existing non-vacuity leg at `:165` and the input-conditional skip semantics from SUITE-XV6-1 stay green and unmodified in substance.
