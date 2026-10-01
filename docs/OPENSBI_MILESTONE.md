# OpenSBI Boot Milestone - July 2026

## Achievement

Real, unmodified OpenSBI 1.7 boots successfully to its ASCII banner on the GPU RISC-V emulator.

**Banner Output:**
```
OpenSBI v1.7
   ____                    _____ ____ _____
  / __ \                  / ____|  _ \_   _|
 | |  | |_ __   ___ _ __ | (___ | |_) || |
 | |  | | '_ \ / _ \ '_ \ \___ \|  _ < | |
 | |__| | |_) |  __/ | | |____) | |_) || |_
  \____/| .__/ \___|_| |_|_____/|____/_____|
        | |
        |_|
```

## Root Causes Discovered and Fixed

### 1. Unmapped Hole "Silent Halt"
**Symptom:** OpenSBI frozen silently when accessing memory below `ram_base_low`.

**Root Cause:** Fetch/load/store operations to unmapped physical addresses returned `valid = false`, cascading into `halted = 1` without raising a proper trap.

**Fix:** Modified `SPATIAL_RV64I.wgsl` to call `raise_trap()` for access faults:
- Instruction Access Fault (cause 1)
- Load Access Fault (cause 5)
- Store/AMO Access Fault (cause 7)

(`RISCV_CPU_MMU.wgsl` also has a `misa` implementation now, applied alongside this work, but the
access-fault conversion and the rest of this milestone's fixes/verification were done against
`SPATIAL_RV64I.wgsl` only — `RISCV_CPU_MMU.wgsl` is a separate, older pipeline and untested here.)

**Impact:** OpenSBI now receives proper M-mode traps for boundary probing instead of ghost freezes.

### 2. Page Table Walker Bug
**Symptom:** SV39 page walks failing with spurious Page Faults.

**Root Cause:** `read_word_phys()` and `read_dword_phys()` indexed the memory array as `byte_addr / 4u` without subtracting `state.ram_base_low`. With `ram_base_low = 0x80000000`, a PTE at `0x80001000` tried to access index 536,871,936 (far out of bounds).

**Fix:** Updated memory accessors to properly subtract `ram_base_low` before indexing.

**Impact:** Page table walks now correctly resolve PTEs for SV39 translations.

### 3. The DTB Lie + Relocation Cliff
**Symptom:** OpenSBI stall at relocation loop (`sd t3, 0(t1)`).

**Root Cause Chain:**
1. `build_minimal_dtb.py` advertised 256MB memory to OpenSBI
2. OpenSBI calculated top-of-memory as `0x8FF00000` based on DTB
3. Generic build's `FW_JUMP_FDT_OFFSET = 0x2200000` (34MB offset) forced relocation to `0x0FF00000`
4. GPU emulator buffer was only 128MB → out-of-bounds store
5. OOB access logic silently halted instead of trapping

**Fix:**
1. Updated `build_minimal_dtb.py` to advertise 128MB (matching buffer size)
2. Fixed OOB access handling to generate Store Access Faults (cause 7)
3. **Later correction:** Switch to `create_dtb.py` (DTC-validated) and use 64MB buffer

**Impact:** OpenSBI completes relocation, stays within bounds, and reaches C code.

### 4. misa CSR Missing
**Symptom:** S-mode payloads failing due to extension detection.

**Root Cause:** `misa` CSR was never implemented — read as 0, so `misa_extension('S')` failed and `next_mode_supported` was false. (This alone did not block cold-boot — `sbi_platform_cold_boot_allowed`/hart-count/lottery logic were independently correct — but it's required for any S-mode payload to be accepted.)

**Fix:** Added proper `RV64IMAC+S+U` misa value (0x8000000000141105):
- MXL=2/RV64 (bits 63:62)
- A (bit 0)
- C (bit 2)
- I (bit 8)
- M (bit 12)
- S (bit 18)
- U (bit 20)

**Impact:** S-mode payloads can now boot correctly.

### 5. fetch-path Trap Handler Bug
**Symptom:** Instruction access faults (translated.x < ram_base_low) were raised but never executed the handler.

**Root Cause:** `raise_trap()` call in `fetch()` discarded the return value and never set `trap_pending`. `raise_trap` redirects PC as a side effect, but without `trap_pending`, main()'s loop fell through to execute the garbage 0 return value as a real instruction.

**Fix:** Match the pattern used elsewhere — check `raise_trap()` return value and set `trap_pending = 1u` if true.

**Impact:** Instruction access faults now properly route to trap handlers.

## Verification

**Correction (this revision):** an intermediate handoff introduced `tests/test_opensbi_boot.py`
and `tests/test_opensbi_setup.py` versions that targeted `tools/RISCV_CPU_MMU.wgsl` +
`tools/riscv_gpu_cpu.py` — a separate, older RV32-oriented pipeline that never received any of
the five fixes above. That version never reached the banner (it stalled at PC 0x80000578,
described at the time as "expected"), and `test_opensbi_boot.py` wasn't even collected by
pytest (no `test_*` function — it was a standalone script). Both files have been rewritten to
exercise the actual fixed pipeline (`tools/spatial_rv64i_cpu.py` + `tools/SPATIAL_RV64I.wgsl`).

### Full Boot Test
- **File:** `tests/test_opensbi_boot.py`
- **Requirements:** 64MB memory buffer, OpenSBI binary (`/usr/lib/riscv64-linux-gnu/opensbi/generic/fw_jump.bin`), WebGPU
- **Status:** PASSES — asserts `"OpenSBI v1.7"` literally appears in UART output
- **Runtime:** ~1-2 minutes (GPU-heavy; run in background / with an extended timeout)

### Regression-Safe Setup Test
- **File:** `tests/test_opensbi_setup.py`
- **Requirements:** Python only
- **Status:** Passes in <1 second
- **Validates:**
  - OpenSBI binary exists and fits in buffer
  - DTB generation works with correct magic
  - OpenSBI's own footprint doesn't overlap the DTB placement offset
  - Buffer size exceeds the hardcoded 34MB `FW_JUMP_FDT_OFFSET`

## Key Requirements Discovered

### Memory Buffer Size
- **Minimum:** 64MB (not 128MB as initially thought)
- **Reason:** OpenSBI generic build's `FW_JUMP_FDT_OFFSET = 0x2200000` (34MB offset)
- **Action:** Any real OpenSBI boot test must use ≥64MB buffer

### DTB Truthfulness
- **Requirement:** DTB must declare actual memory size
- **Tool:** Use `create_dtb.py` (validated by dtc), not `build_minimal_dtb.py`
- **Reason:** OpenSBI trusts DTB for memory layout decisions

### Access Fault Handling
- **Requirement:** All OOB/unmapped accesses must raise traps, not silent halts
- **Causes:** 1 (I), 5 (L), 7 (S/AMO)
- **Action:** Verify trap handlers are reachable and execute correctly

## Testing Guidance

### Unit Tests (Small Buffers)
- **Size:** 1MB - 4MB buffers
- **Use:** Hand-built test programs, RISC-V assembly
- **Fine for:** CSR tests, MMU unit tests, instruction-level tests

### Real Firmware Tests (Large Buffers)
- **Size:** ≥64MB buffer
- **Use:** OpenSBI, xv6, Alpine Linux
- **Required for:** FDT relocation, full cold-boot sequences

## Files Modified

1. **WGSL:** `tools/SPATIAL_RV64I.wgsl` (the verified pipeline)
   - Fixed unmapped hole → access fault conversion
   - Fixed page table walker (read_word_phys / read_dword_phys)
   - Added misa CSR implementation
   - Fixed fetch-path trap_pending bug
   - (`tools/RISCV_CPU_MMU.wgsl` also gained a `misa` implementation, but is a separate,
     unverified pipeline — see the Verification section above.)

2. **DTB Generation:** `tools/create_dtb.py` (DTC-validated; use this, not `build_minimal_dtb.py`,
   which produces a structurally invalid DTB that `dtc` itself rejects)

3. **Tests:**
   - `tests/test_opensbi_boot.py` (full GPU boot test, asserts the actual banner text)
   - `tests/test_opensbi_setup.py` (regression-safe setup test)

## Session History

- **Session 20260727_160119_a309de:** Original investigation and fixes
- **Session 20260727_173526_b474d6:** Introduced regression tests, but against the wrong
  (RISCV_CPU_MMU.wgsl) pipeline — never actually verified the banner
- **Session 20260727 (this correction):** Rewrote both test files against the actual verified
  pipeline; confirmed `test_opensbi_boot.py` passes for real

## Future Work

1. Add Alpine Linux boot test with 64MB buffer
2. Add xv6 kernel boot test with proper DTB
3. Document UART output verification patterns
4. Create performance benchmarks for boot times

---

**Last Updated:** 2026-07-27
**Status:** Milestone Complete ✓
**Regression Tests:** `tests/test_opensbi_setup.py`