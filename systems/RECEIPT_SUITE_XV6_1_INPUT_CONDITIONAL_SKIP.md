# RECEIPT — SUITE-XV6-1: the boot gate's skip is now INPUT-CONDITIONAL, and the gate file is finally tracked

**Row:** `systems/GLYPH_SELF_HOSTING_ROADMAP.md:357` (SUITE-XV6-1, ⏳ → ✅ 2026-09-13).
**Tick:** builder cron `af3e62239ce2`. Implementation delegated to `agy` (exit 0, 202 s,
`output/agy/agy_impl_20260913_211508.log`, brief `.builder_queue/brief_suite_xv6_1_input_conditional_skip.md`).
**Every number below is the orchestrator's own run**, not the delegate's claim.

## 1. What landed

| artifact | change |
|---|---|
| `tests/test_xv6_boot_regression.py` (**now TRACKED** — see §3) | (a) kernel path is caller-controllable: `XV6_KERNEL = Path(os.environ.get("XV6_KERNEL_PATH", "/tmp/xv6-riscv/kernel/kernel"))` and the check reads the env override too; (b) both skip reasons now carry a machine-readable token first — `KNOWN-BROKEN-INPUT:` for the RVC fallback branch, `INPUT-ABSENT:` when nothing is present; (c) NEW pure-function leg `test_xv6_kernel_check_nonvacuity` (4 sub-cases: ELF ⇒ `exists=True` + exact path; non-ELF ⇒ `False` + "not a valid ELF"; absent primary + relocated fallback ⇒ `False` + `INPUT-ABSENT`; fallback-only ⇒ `False` + `KNOWN-BROKEN-INPUT`). Deterministic: `tmp_path` + `monkeypatch` only, no GPU, no network. |
| `.builder_queue/brief_suite_xv6_1_input_conditional_skip.md` | the brief (`tools/check_brief.py` → PASS, 0 invalid, 2 soft warnings) |
| `.builder_queue/probe_suite_xv6_1_env_override.py`, `.builder_queue/probe_suite_xv6_1_nonvacuity.py` | the two probes below, committed so the RED can be reproduced from the repo |

No locked interface touched: `check_xv6_kernel_exists()` keeps its no-argument call form and its
`(exists, msg, path)` 3-tuple; `run_xv6_boot`, `BOOT_TIMEOUT`, `MAX_INSTRUCTIONS` and both GPU legs are untouched.

## 2. RED → GREEN (the row's burn, measured)

**RED — pre-change, orchestrator probe** (`.builder_queue/probe_suite_xv6_1_env_override.py`; points
`XV6_KERNEL_PATH` at a temp file carrying ELF magic):

```
probe: module XV6_KERNEL=/tmp/xv6-riscv/kernel/kernel
C1 env-override honored : exists=False path=None
PROBE_VERDICT=RED
```

The path was hardcoded, so the "skip" could never be shown to be *input*-conditional — a probe that cannot
go red. That is the defect this row's leg (a)/(b) leave behind once the 601 s fallback burn is removed.

**GREEN — same probe, post-change (mine):** `C1 env-override honored : exists=True path=/tmp/xv6_nonvacuity_a1r5udrp/fake_kernel_elf`
· `C1b non-ELF rejected : exists=False` · `PROBE_VERDICT=GREEN` · rc=0.

**GREEN — gate command (mine):**

```
$ /usr/bin/python3 -m pytest tests/test_xv6_boot_regression.py -q -rs -p no:randomly
SKIPPED [1] …:227: KNOWN-BROKEN-INPUT: Non-RVC xv6 kernel absent at /tmp/xv6-riscv/kernel/kernel. Fallback …/boot_images/xv6.img is KNOWN-BROKEN-INPUT (RVC build: misdecoded by MMU, PC cycles 0x80000c7c …)
SKIPPED [1] …:292: KNOWN-BROKEN-INPUT: …
1 passed, 2 skipped in 0.19s        rc=0, wall 0.99 s
```

Budgets for scale: the 2026-09-13 sweep recorded `[TIMEOUT] … (150.06s, rc=-9)` for this file, and the row's
own correction measurement was 601.30 s / `2 failed` on the known-broken fallback. **That burn is gone:
0.99 s wall, rc=0, and the verdict is SKIP — excluded from pass/fail counts by construction.**

**Non-vacuity of the NEW leg (own run, `.builder_queue/probe_suite_xv6_1_nonvacuity.py`)** — copies the gate
file, mutates the copy, requires the copy to FAIL:

| mutant | mutation | result |
|---|---|---|
| M1 | env override ignored (pre-fix behaviour restored) | `1 failed` at leg (i): `Expected exists=True for valid ELF, got False: INPUT-ABSENT …` |
| M2 | non-ELF file accepted (over-permissive check) | `1 failed` at leg (ii): `Expected exists=False for non-ELF, got True` |

`NONVACUITY_VERDICT=LEG IS DISCRIMINATING` (rc=0). The leg is not decoration.

## 3. Correction to the row text: the file was NOT gitignored — it was simply untracked

SUITE-XV6-1 states the test file "is gitignored via `.gitignore:101 (test_*.py)` and untracked".
Measured: `git check-ignore -v tests/test_xv6_boot_regression.py` → **rc=1 (not ignored)**; the pattern that
line holds is root-anchored (`/test_*.py`, and a sibling session has just root-anchored the other two patterns
in the same block), so it cannot match `tests/…`. The file was never `git add`ed. Consequence that mattered
more than the wording: this gate had **no commit history at all** — its skip logic could change silently and
no diff would show it. It is staged in this commit; `git ls-files tests/test_xv6_boot_regression.py` now
returns the path.

## 4. Row-gate side-effect: three FAILs in the previous sweep did not reproduce

`/usr/bin/python3 -m pytest <file> -q -p no:randomly`, this tick, on the files the 21:08 sweep
(`output/SUITE_DEFECT27_SWEEP.txt`, head `39ad5ce`) recorded as FAIL:

| file | sweep (21:08) | this tick |
|---|---|---|
| `tests/test_glyph_wordbook_lookup.py` | FAIL 2 | **2 passed in 0.19 s** |
| `tests/test_glyphlang_integration.py` | FAIL 3 (4 passed) | **7 passed in 4.35 s** |
| `tests/test_glyph_file_io.py` · `test_glyph_audio_io.py` · `test_glyph_orchestrator_speak_to_driver.py` · `test_crc_patch.py` · `test_syscall_handlers.py` | FAIL→PASS history (SUITE-FIX-1 clusters 1–3) | **2 / 1 / 2 / 1 / 7 passed** |

So SUITE-FIX-1's clusters **(1), (2) and (3)** are green at the current tree, by direct measurement.
**No cause is attributed** for the sweep-time FAILs: the previous tick already established that sweep window
was not exclusive (a sibling session wrote `src/pixel_embeddings.py` at 21:05:29 and `tools/speak_glyph.py` at
21:07:38, both inside the sweep). Two of the four remaining sweep FAILs are that sibling's own in-flight files
(`tests/test_mt2_large_scale.py`, `tests/test_synthesis_equivalence.py`, `tests/test_pixel_embeddings.py`,
`tests/test_pixel_os_listener_uart.py` are all dirty in the worktree by that session, not by this tick).

## 5. What this PASS does NOT prove

1. **SUITE-XV6-1's gate leg (c) is NOT verified.** "With the correct kernel present the test must actually
   pass" needs the non-RVC `/tmp/xv6-riscv/kernel/kernel`; it is absent from this box (searched: no `xv6.img`
   /kernel pair outside `boot_images/`). Only the *input-absent* path is exercised. The ELF-magic temp file
   proves the **branch**, not the boot.
2. **No real xv6 boot ran** in this step, on either engine, and no GPU work was done.
3. **No full sweep this tick.** The row-gate's "re-run the SUITE-BASE-1 command and record the before/after
   pair" was done **per file** (§4), not repo-wide: sweeps are exclusive by SUITE-HEAVY-1's own clause and a
   sibling lane was live in this window. "No other file regressed" therefore rests on the previous tick's
   257-file sweep plus these per-file re-runs, not on a fresh denominator.
4. **The CLUSTER-4 side is untouched**: `test_ollama_security_analysis.py` (live service) and
   `test_pixel_lm_train.py` (contention-sensitive) were not measured here; leg **1b of SUITE-FIX-1 remains
   BLOCKED-ON-DESIGN**. SUITE-FIX-1 stays open.
5. `INPUT-ABSENT` is asserted by the new leg via a relocated fallback (`monkeypatch.setattr`), never observed
   on this machine's real configuration.

## 6. Discovery made while measuring this row: the right input was in-repo all along

The row, `tests/XV6_BOOT_STATUS.md` (2026-08-14) and the test's own comment all assume the ONLY in-repo image
is the RVC-broken `boot_images/xv6.img`. Sweeping `boot_images/` for this receipt found two more:

| artifact | measured this tick | why it matters |
|---|---|---|
| `boot_images/xv6-riscv.img` (286328 B) | ELF64 RISC-V, entry `0x80000000`, **`e_flags=0x00000000` ⇒ RVC bit CLEAR, soft-float ABI**; contains the string `xv6 kernel is booting`; sha256 `9ca0c366a69833f511b4a2848cb3038c1e816ee8ce9c3ac9cad07fd726ed6a27` | This is a **non-RVC xv6 kernel** — the class of input leg (c) needs. `boot_images/xv6.img` by contrast measures `e_flags=0x5` (RVC + double-float), matching the documented misdecode. |
| `boot_images/xv6-riscv-fs.img` (2048000 B) | xv6 `FS_MAGIC` `0x10203040` at offset **1024** (block 1, xv6's superblock block), `init` present in the first MB; sha256 `f31516ca7bb190f38d6ef71ef7e488ee4d07d50700dd06c6ecbec53e0d4841ed` | A real xv6 filesystem image — the boot oracle's **second** input, which `tools/boot_xv6_gpu.py:385` currently reads from hardcoded `/tmp/xv6-riscv/fs.img` (absent), i.e. still a volatile-`/tmp` dependency. |

Both files are **gitignored** (`.gitignore:66` → `*.img`), so "tracked + checksummed" needs a force-add.
Consequences, stated plainly:

* Leg (c) is **testable** from this repo — that is why it is promoted as **SUITE-XV6-2** rather than left as prose.
* Leg (c) is **still unverified**: no boot was run this tick. The GPU was at 44 % utilisation with 20 GB in use by
  another lane, and the boot gate needs the loader pointed at the in-repo `fs.img` first (a separate step).
  Nothing in this commit claims the kernel boots.
* A sha256 establishes identity, not provenance: these two files were not built by this tick and their build
  flags are inferred from the ELF header (`e_flags` is authoritative for RVC/ABI, per the RISC-V psABI), not from
  a recorded build command.
