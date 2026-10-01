# RECEIPT — SUITE-XV6-2: the boot oracle now has committed input, a bounded run, and a token-bearing verdict

**Row:** `systems/GLYPH_SELF_HOSTING_ROADMAP.md:358` (SUITE-XV6-2, SUITE-XV6-1's leg (c))
**Tick:** builder cron `af3e62239ce2`, 2026-09-13 21:2x–22:0x CDT
**Lane:** main checkout (`tools/boot_xv6_gpu.py`, `tests/test_xv6_boot_regression.py`, `boot_images/*.img` — none of these is on the AGENTS.md core-codec list)
**Implemented by:** `agy` delegation (1 attempt, brief `.builder_queue/brief_suite_xv6_2_committed_input_bounded_verdict.md`) for the committed-input + bounded-verdict legs; **orchestrator** for the console-reader repair and the removal of the delegate's opt-in gate (see §5).

## 1. Headline

**The vendored non-RVC xv6 kernel boots to the shell on the GPU emulator.**
Measured by the gate itself:

```
tests/test_xv6_boot_regression.py::test_xv6_boot_to_shell PASSED         [ 85%]
tests/test_xv6_boot_regression.py::test_xv6_boot_deterministic PASSED    [100%]
============================== 7 passed in 50.40s ==============================
```
and, from the same file run with `-s` (`output/SUITE_XV6_2_GATE_TOKENS.txt`):

```
  ✓ XV6_VERDICT: SHELL_REACHED
  ✓ Found shell prompt: 'init: starting sh'
2 passed, 5 deselected in 49.78s
```

The console, read from the repaired reader (`output/SUITE_XV6_2_boot_oracle_GREEN.log`):

```
xv6 kernel is booting

init: starting sh
CPU running: 1
Exit reason: SHELL_PROMPT_REACHED at iter 10
Boot verdict: SHELL_REACHED (exit=SHELL_PROMPT_REACHED at iter 10, instr=21999938, pc=0x80002be4)
```

**The oracle claim SUITE-XV6-1 leg (c) could not make is now made, and it is one command long.**

## 2. Gate (row clause (1))

Committed, hash-pinned input:
- `boot_images/xv6-riscv.img` — 286328 B, sha256 `9ca0c366a69833f511b4a2848cb3038c1e816ee8ce9c3ac9cad07fd726ed6a27`, ELF64 RISC-V, `e_flags=0x0` (RVC clear).
- `boot_images/xv6-riscv-fs.img` — 2048000 B, sha256 `f31516ca7bb190f38d6ef71ef7e488ee4d07d50700dd06c6ecbec53e0d4841ed`.
- Both force-added (`git add -f`); `.gitignore:66` (`*.img`) still matches them, so the exemption is a tracked-file fact, not a `.gitignore` edit.
- Both hashes are asserted in-test (`XV6_KERNEL_PINNED_SHA256`, `XV6_FS_PINNED_SHA256`) and a mismatch fails with `INPUT_SHA_MISMATCH` naming the class.
- `tools/boot_xv6_gpu.py:386` — the fs path is now caller-controllable: `Path(os.environ.get("XV6_FS_PATH", "/tmp/xv6-riscv/fs.img"))`. **Default unchanged**; the test sets it to the in-repo image, so the boot oracle no longer has a volatile-`/tmp` dependency at all (it was the *second* one).

Row gate command, run by the orchestrator:

```
XV6_KERNEL_PATH=boot_images/xv6-riscv.img /usr/bin/python3 -m pytest tests/test_xv6_boot_regression.py -q -p no:randomly
→ 7 passed in 51.22s   (rc=0)
```

## 3. RED before GREEN (the discriminating pair)

The decisive A/B is **one boot, two readers** — the same binary, the same input, only the reader offset changed:

| | reader | result |
|---|---|---|
| RED — pre-fix | `for i in range(4096, …)` | `output/SUITE_XV6_2_baseline_graceful2.log`: `[7] UART CONSOLE OUTPUT` section **EMPTY** after 108M instructions / 54 dispatches |
| GREEN — fixed | `for i in range(0, …)` | `output/SUITE_XV6_2_boot_oracle_GREEN.log`: `xv6 kernel is booting` / `init: starting sh` at 22M instructions |

Pre-fix, whole-run behaviour (`output/SUITE_XV6_2_baseline_tmpfs.log`, kernel given directly, `/tmp/xv6-riscv/fs.img` staged by hand):

```
Iter   171: PC=0x00000000800024b8, RA=0x0000000080000fc4, instr=343999616, timer_irq=325, total_irq=384
rc=124          # killed by the caller's 300 s bound — 172 dispatches, 344M instructions, no console, no verdict
```

The stall PCs decode against the kernel's own symbol table (`riscv64-unknown-elf-objdump`) as `scheduler`, `acquire`, `push_off`, `holding`, `pop_off`, `release`, `mycpu`, `myproc` — **valid kernel text**, i.e. the pre-fix red was *not* the RVC-misdecode class the old status doc assumed (`e_flags=0x0`, AMO implemented in `tools/RISCV_CPU_MMU.wgsl:3557`).

**HONEST BOUNDARY:** the pre-fix *test-leg* red (`assert False, f"xv6 boot execution failed: {stderr}"`, a bare assertion carrying no class) is **read from the pre-fix source plus the measured 300 s tool-level burn above — not reproduced as a full 600 s pytest run.** The 601 s figure in the row is 2 × `BOOT_TIMEOUT` (both GPU legs), which the new bound now caps.

## 4. Mechanism — what actually changed and why the row existed

1. **The instrument was blind, not the guest.** `tools/boot_xv6_gpu.py`'s end-of-run UART reader started at byte **4096**; the console text lives at the **start** of the buffer behind a 2-byte length header. Proof of the layout, independent of the reader: the diagnostic slot word index 1 read `0x656b2036` = `b"6 ke"` — the substring of `"xv6 kernel is booting"` at offset 2. The periodic dump at `:775` already read from index 0; the end-of-run reader disagreed with it. Both now read from 0, and the misleading `Diagnostic Code: 0x…` print now decodes the bytes and says `= UART text b'6 ke' (no diagnostic code latched)`.
2. **The console was command-gated.** The periodic dump only ran `if command_injected` — so a *no-command* boot could succeed and print nothing. The new console poll runs in **all** modes.
3. **The run was infinite.** Only a stall detector, a guest halt, or `Ctrl+C` ended it, so any caller's timeout killed it and destroyed §[7] (console + final state + diagnostics) — the "601 s silently". Added `--max-seconds N` (default `0` = unbounded, so no existing caller changes) which exits **gracefully**, and a prompt-detecting stop so a *successful* boot ends by itself.
4. **The verdict is token-bearing.** The tool now always prints `Exit reason: …` and `Boot verdict: SHELL_REACHED|NO_SHELL (exit=…, instr=…, pc=…)`; the test's classifier maps the outcomes to `XV6_VERDICT: SHELL_REACHED` / `INPUT_SHA_MISMATCH` / `FS_ABSENT` / `NO_SHELL_TIMEOUT_<n>s` / `NO_SHELL_STALL_PC_<addr>`, each with a class. `assert False, "xv6 did not reach shell"` is gone.

## 5. Two orchestrator corrections to the delegate

- **The delegate made the real-boot legs opt-in** (`XV6_RUN_BOOT=1`), honouring my brief's "do NOT run the real xv6 boot; the orchestrator runs it" too literally. That made the row's own gate command vacuous — it would have passed 5 legs in 0.20 s having never booted anything. Both guards removed; the boot now runs by default because it is bounded and self-contained (measured ≈22M instructions / ≈20 s to `init: starting sh`). **The orchestrator expanded the brief's file scope** for this: `tools/boot_xv6_gpu.py` beyond the fs-path line, and the test's subprocess now passes `--max-seconds max(60, timeout-30)` so the child always dies gracefully with its evidence instead of being SIGTERM'd by the parent.
- The delegate's own log is **0 bytes** (`output/agy/agy_impl_20260913_212551.log`) — it wrote real, useful code (368 lines in the test) but reported nothing. Everything above is the orchestrator's own re-run, not the delegate's claim.

## 6. What the PASS does NOT prove

- **Determinism is asserted loosely.** `test_xv6_boot_deterministic` boots twice and compares instruction/IRQ counts with a 10 % variance allowance; IRQ mismatch is a printed warning, not a failure. Two clean runs is not a stability claim.
- **Only `init: starting sh` is proven, not `$ ` interactivity.** The prompt-detect stop fires on the first accepted token, so the run ends before any command round-trip. No shell command was executed; `--command`/`--autonomous` paths were not exercised.
- **The `--max-seconds` graceful-exit path was not exercised end-to-end on the real kernel** — the successful boot exits via prompt detection. The bound is exercised as a unit projection (`output/evidence_l3_bound_nonvacuity.txt`: 240 s × 2 > 240 s budget) and by the delegate's synthetic-ELF probe (`output/evidence_synthetic_probe.txt`: `NO_SHELL_TIMEOUT_10s`, 12.13 s).
- **The classifier's stall class** (`NO_SHELL_STALL_PC_<addr>` → `MMU/RVC path`) is a heuristic attribution. My own decoding of the pre-fix stall PCs puts them in the scheduler/lock path, not the MMU — if a stall verdict is ever produced again, decode the PC against the ELF before quoting the class.
- **No repo-wide sweep ran.** A sibling lane was live in the same tree all tick (`src/pixel_embeddings.py`, `tools/speak_glyph.py`, `tests/test_mt2_large_scale.py`, `tests/test_synthesis_equivalence.py`, `tools/pixel_os_listener.py`, `tools/train_pixel_lm.py`, `tools/ollama_security_analyzer.py`, `.update_proposals.log` dirty, plus a `SUITE_CLEAN_SINK.jsonl` sweep of theirs at 21:33), and sweeps are exclusive by SUITE-HEAVY-1. **Regression status rests on the row gate (7/7) and the untouched-arc argument**, not on a full-width sweep. Nothing outside the three in-scope paths was edited by this tick.
- One seed, one machine (RTX 5090 laptop), one kernel build. The 22M-instruction figure is a single measured run.

## 7. Evidence files

| file | what |
|---|---|
| `output/SUITE_XV6_2_baseline_tmpfs.log` | pre-fix, 300 s bound: 172 dispatches / 344M instr, no console, rc=124 |
| `output/SUITE_XV6_2_baseline_graceful2.log` | pre-fix reader: §[7] EMPTY at 108M instr (the RED half of the A/B) |
| `output/SUITE_XV6_2_console_after.log` | first post-fix run: console visible, rc=124 (reader fixed, exit still unbounded) |
| `output/SUITE_XV6_2_boot_oracle_GREEN.log` | bounded + prompt-detect: `SHELL_REACHED`, console, `Exit reason:` |
| `output/SUITE_XV6_2_GATE_GREEN.txt` | row gate, 7 passed / 50.40 s, per-leg names |
| `output/SUITE_XV6_2_GATE_TOKENS.txt` | gate with `-s`: `✓ XV6_VERDICT: SHELL_REACHED`, `✓ Found shell prompt: 'init: starting sh'` |
| `output/evidence_synthetic_probe.txt` | delegate: synthetic non-shell ELF → `NO_SHELL_TIMEOUT_10s`, 12.13 s |
| `output/evidence_l3_bound_nonvacuity.txt` | delegate: L3 bound arithmetic + dual-boot abort |
| `.builder_queue/probe_suite_xv6_2_red.py`, `.builder_queue/probe_xv6_synthetic.py` | delegate probes |
| `.builder_queue/brief_suite_xv6_2_committed_input_bounded_verdict.md` | the brief (PASSes `tools/check_brief.py`) |
