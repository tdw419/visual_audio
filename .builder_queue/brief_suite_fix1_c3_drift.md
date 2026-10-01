# BRIEF — SUITE-FIX-1 cluster (3): API/firmware drift, 6 red legs in 3 files

Roadmap row: **SUITE-FIX-1** (`systems/GLYPH_SELF_HOSTING_ROADMAP.md:355`), cluster "(3) API/firmware drift".
Orchestrator: builder cron `af3e62239ce2`. Base revision: `4bcfe15` (branch `glyph-transpiler-autoloop`).

## Read first (spec pointers)

1. `systems/GLYPH_SELF_HOSTING_ROADMAP.md:355` — the row and its GATE cell (no skip-to-green; re-run the
   SUITE-BASE-1 command and record the before/after verdict pair; the named files must flip FAIL→PASS and no
   other file may regress).
2. `tests/test_syscall_handlers.py` — **the ABI spec for 0x10/0x11**. Its byte-order comments (`:52-56`, `:88-89`),
   argument registers and return values are the contract. This file may NOT be edited to go green.
3. `tools/english_to_glyph.py:104-105` — the declared macro forms (`BOOT_LINUX` → `SYSCALL r3 0x10`,
   `STORE_CODE` → `SYSCALL r4 0x11`), i.e. this ABI is published, not novel.

## Measured state at `4bcfe15` (do not re-derive; RED evidence)

`/usr/bin/python3 -m pytest tests/test_crc_patch.py tests/test_sbi_firmware.py tests/test_syscall_handlers.py -q`
→ **6 failed, 3 passed in 4.21s** (`--tb=line`):

| leg | failure line |
|---|---|
| `tests/test_crc_patch.py::test_crc_integrity` | `tests/test_crc_patch.py:87: AssertionError: Failed to load uncorrupted frame` |
| `tests/test_sbi_firmware.py::test_sbi_console_putchar` | `tests/test_sbi_firmware.py:62: AssertionError: Expected 'Hi!', got ''` |
| `tests/test_syscall_handlers.py::TestBootLinuxSyscall::test_boot_linux_invalid_signature` | `tests/test_syscall_handlers.py:39: assert 0 == -1` |
| `...::TestStoreCodeSyscall::test_store_code_basic_copy` | `tests/test_syscall_handlers.py:165: IndexError: list index out of range` |
| `...::TestStoreCodeSyscall::test_store_code_multi_byte` | `tests/test_syscall_handlers.py:214: AssertionError: Expected 0x0000AA, got 0x000000` |
| `...::TestStoreCodeSyscall::test_store_code_invalid_length` | `tests/test_syscall_handlers.py:237: assert 0 == -1` |

The three legs that PASS (`test_boot_linux_valid_vac2_container`, `test_boot_linux_cognitive_payload_flag`,
`test_store_code_overlapping_regions`) pass **vacuously**: they assert `registers[6] == 0`, which is exactly what the
catch-all returns for every unimplemented reserved syscall. They must stay green, but they must stay green *because
the handlers exist*, not because nothing happens.

### Root causes (measured by the orchestrator, three distinct ones)

**(A) `tests/test_crc_patch.py` — the test's own vendored loader drifted.**
The module monkeypatches `TemporalLog.load_state` (`:17,:65`) with a copy that calls the removed **method**
`self.pixels_to_bytes(pixel_bytes)` at `tests/test_crc_patch.py:41`. The module now exposes only the **module-level**
helper `_pixels_to_bytes` (`src/spatial/temporal_log.py:242`), which the real `load_state` (`:128`, helper use around
`:160`) calls. The `AttributeError` is swallowed by the shim's own `except Exception` (`:59-61`), so *both* legs got
`None`; leg 2 (`corrupted_state is None`) has therefore been passing for the wrong reason. **Fix belongs in the test
shim, not in `src/spatial/temporal_log.py`.**

**(B) `tests/test_sbi_firmware.py` — the test captures the wrong channel.**
`tools/spatial_rv32i_cpu.py:323-324` states in its own docstring that legacy SBI ecalls (console putchar, set timer)
are serviced **inside the WGSL shader** and land in the UART TX buffer; `read_uart_output()` (`:218`) drains it.
The test captures `sys.stdout` instead, so it reads `''`. **Fix belongs in the test's capture block.** Watch out: the
shader must actually deliver the bytes — measure `core.read_uart_output()` before asserting; if the UART is empty, that
is a real engine finding, stop and report it rather than weakening the assertion.

**(C) `tools/glyph_isa_v2.py` — the reserved-syscall catch-all makes a claim nothing performs.**
`tools/glyph_isa_v2.py:1212-1215`:
```
elif 0x10 <= syscall_num <= 0xFF:
    # Reserved for GeOS spatial services - bridge to hypervisor
    print(f"[SYSCALL] GEOS_SERVICE 0x{syscall_num:02X}: dispatched to MMIO 0x{SPATIAL_REGISTRY_BASE:08X}")
    return 0
```
No reader of that "dispatch" exists in-tree, so the print is aspiration stated as fact and 0x10/0x11 silently no-op.
Implement the two handlers the pinned tests specify, in the same shape as the 0x03/0x04/0x07/0x08/0x09 handlers landed
at `4bcfe15`:

- **`0x10` SYSCALL_BOOT_LINUX** — `r1 = container_addr`, `r2 = flags`. Read the two container header pixels at
  `container_addr` / `container_addr + 1` through `_mem_read`, reconstruct the 32-bit signature as
  `(p0 | ((p1 & 0xFF) << 24)) & 0xFFFFFFFF` (that is the byte order the test's own comments pin:
  `tests/test_syscall_handlers.py:52-56`, `:88-89`) and compare against `0x56414332` (`'VAC2'`).
  Signature invalid → print a named refusal and `return -1`. Signature valid → `return 0`
  (the test's docstring calls this "successful syscall **recognition**": validate + accept, no boot is performed by the
  engine, and the receipt must say exactly that).
- **`0x11` SYSCALL_STORE_CODE** — `r1 = dest_addr`, `r2 = src_addr`, `r3 = length` (pixel words). `length <= 0` →
  named refusal, `return -1`. Otherwise copy `length` words `src_addr → dest_addr` in pixel space through the
  existing `_mem_read`/`_mem_write` pair (the mutations must land on the caller's `image`, which is how the test reads
  them back at `:210-216`). `return 0`.

Keep the `0x10 <= n <= 0xFF` catch-all for every other reserved number, unchanged.

## Scope (files in scope — positive)

- `tools/glyph_isa_v2.py` — **only** the `_handle_syscall` dispatch region: the docstring syscall list (~`:1048`) and
  the reserved-range branch (~`:1212`). No other engine behaviour, no other branch, no signature change, no new
  public API.
- `tests/test_crc_patch.py` — the monkeypatch shim (`:19-61`, i.e. the drifted helper call and, if needed, its import).
- `tests/test_sbi_firmware.py` — the output-capture/assert block (`:48-63`).
- `output/` scratch probes, if you want them.

## Must NOT touch (negative scope)

- `tests/test_syscall_handlers.py` — it is the ABI spec; do not edit it to go green. If it is genuinely
  self-contradictory, **stop and report**; do not "fix" the test.
- `src/spatial/temporal_log.py` (read-only; the drift is in the test), `src/codec/phy.py`.
- `tools/glyph_gpt/baker.py`, `tools/rv64i_to_glyph.py`, `glyph_dispatch/**`, every WGSL shader (`*.wgsl`).
- `pytest.ini`, `tools/arc_lega.sh`, `tools/suite_iso_harness.py`, `tools/suite_sweep.sh`, `tools/supply_census.py`,
  the DEFECT-17/18 guards, and any file outside the two test files + the one dispatch region above.

**Interfaces LOCKED:** `GlyphCPUv2._handle_syscall(self, syscall_num: int, image: np.ndarray, imm: int = 0) -> int`
signature unchanged; return convention unchanged (`0` success, `-1` error, byte count where already documented);
the existing handlers' semantics unchanged. Do not refactor, do not rename, do not reformat neighbouring code.

## Gate command and legs (the orchestrator re-runs every one of these)

RED first (already measured at `4bcfe15`, above — paste your own re-run in the hand-back):
`/usr/bin/python3 -m pytest tests/test_crc_patch.py tests/test_sbi_firmware.py tests/test_syscall_handlers.py -q`

- **L1** `/usr/bin/python3 -m pytest tests/test_crc_patch.py -q` → **1 passed** (leg 1 green, leg 2 still green).
- **L2** `/usr/bin/python3 -m pytest tests/test_sbi_firmware.py -q` → **1 passed**, and the assertion reads the UART
  bytes exactly (`b"Hi!"`), with the drained bytes quoted in your hand-back.
- **L3** `/usr/bin/python3 -m pytest tests/test_syscall_handlers.py -q` → **9 passed** (all nine legs; the three
  previously-vacuous ones included, now backed by real handlers).
- **L4** the combined command above → **11 passed, 0 failed**.
- **L5 non-vacuity, four separate probes**, each shown RED and then reverted byte-identical (record md5 before/after):
  - N1: shunt the corrupted-frame rejection (force the CRC/`crc_valid` acceptance in the shim) → `test_crc_integrity`
    must go RED. State plainly which mechanism actually rejects the corrupted file (CRC vs PIL decode failure) —
    if PIL decode fails first, say so; do not claim the CRC check is load-bearing if it is not.
  - N2: drop one of the three SBI putchar ecalls (or change a character) → the UART assertion must go RED.
  - N3: revert the 0x11 branch to the old catch-all → `test_store_code_basic_copy` and `test_store_code_multi_byte`
    must go RED; remove only the `length <= 0` guard → `test_store_code_invalid_length` must go RED.
  - N4: bypass the VAC2 signature check (always `return 0`) → `test_boot_linux_invalid_signature` must go RED.
- **L6 no regression, engine consumers:** `/usr/bin/python3 -m pytest tests/test_gh4_wgsl_parity.py
  tests/test_gh18_syscall_abi.py tests/test_gh21_posix_shim.py tests/test_glyph_file_io.py
  tests/test_glyph_audio_io.py tests/test_glyph_orchestrator_speak_to_driver.py -q -m "not live_smoke"` → all green,
  0 failed. (Report the exact passed/deselected counts you observe.)
- **L7** `git status --short -- tools/ tests/ src/` → only the in-scope files appear; report the exact listing.

## Failure evidence (RED-first is mandatory)

Show the gate RED at `4bcfe15` **before** your change (the orchestrator has it: `6 failed, 3 passed`) and paste the
four N-probes' RED tails literally. A green that was never shown able to fail is not evidence.

## Definition of done / hand-back

- The three files: 11/11 legs green under `/usr/bin/python3`; L6 green; L5's four probes measured with md5 evidence.
- Report line counts of the diff (`git diff --stat`), the exact commands you ran, and the **honest boundary**: what
  the PASS does not prove (e.g. no WGSL leg for 0x10/0x11, `0x10` validates and records but performs no boot, the
  reserved catch-all still claims an MMIO dispatch for every other reserved number, `test_sbi_firmware` needs a
  working wgpu/GPU, no arc run).
- **Do NOT commit.** The orchestrator verifies the gate itself and commits. Do not run `git add`/`git commit`/`git
  checkout`/`git stash` on tracked files.
