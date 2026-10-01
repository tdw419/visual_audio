# Phase 1 Receipt — Glyph Dispatch Setup Complete

**Date:** 2026-08-30
**Status:** ✅ Phase 1 COMPLETE — Isolated dispatch infrastructure

## What Was Built

### 1. Directory Structure (Isolated)

```
glyph_dispatch/
├── README.md                    # Architecture overview
├── docs/
│   └── ABI.md                   # Dispatch ABI specification
├── src/
│   ├── glyph_isa_v2.py          # Glyph ISA (copied from tools/)
│   ├── wgsl_glyph_isa_v2.py     # GPU shader generator (copied)
│   ├── dispatch/
│   │   ├── __init__.py
│   │   ├── dispatcher.py        # GlyphDispatcher implementation
│   │   └── request_struct.py    # ABI constants & helpers
│   └── riscv/
│       ├── __init__.py
│       ├── cpu_state_mirror.py  # CPU struct with glyph fields
│       └── RISCV_CPU_MMU.wgsl   # Reference (original)
└── tests/
    └── test_dispatch.py         # Dispatcher test suite
```

### 2. Dispatch ABI (Spec & Code)

**Memory Regions:**
- Request structure: `0x8100_1000` (60 bytes)
- MMIO trigger: `0x8800_0000` (write-only)

**Request Structure:**
```python
OFFSET_FLAGS = 0x00           # BUSY, ERROR flags
OFFSET_GLYPH_ID = 0x04        # Kernel identifier
OFFSET_INPUT_BUF_PTR = 0x08   # Input buffer GPA
OFFSET_INPUT_BUF_LEN = 0x10   # Input length
OFFSET_OUTPUT_BUF_PTR = 0x18  # Output buffer GPA
OFFSET_OUTPUT_BUF_LEN = 0x20  # Output length
OFFSET_RESULT_STATUS = 0x28   # 0=success, -1=error
OFFSET_RESERVED = 0x2C        # Reserved (future expansion)
```

**Flags:**
- `FLAG_BUSY = 0x00000001` — glyph executing
- `FLAG_ERROR = 0x00000002` — error occurred

### 3. Dispatcher Implementation

**GlyphDispatcher.check_dispatch()** flow:
1. Read request structure from shared RAM
2. Validate BUSY flag
3. Check glyph_id in registry
4. Read input data (if any)
5. Execute glyph program
6. Write output data (if any)
7. Clear BUSY flag, set result_status
8. Return True (dispatched) or False (no dispatch)

**Error Handling:**
- Invalid glyph_id → result_status = -1
- Input buffer out of bounds → result_status = -1
- Output buffer too small → result_status = -2
- Glyph execution failed → result_status = -3

### 4. CPU State Extension

**Extended CPU_DTYPE:**
```python
CPU_DTYPE_EXTENDED = np.dtype([...,
    ('glyph_busy', np.uint32),           # Offset 516
    ('glyph_last_trigger', np.uint32),  # Offset 520
])
```

**Field Offsets:**
- `GLYPH_BUSY_OFFSET = 516`
- `GLYPH_LAST_TRIGGER_OFFSET = 520`

### 5. Test Suite

**Test Coverage:**
1. ✅ Basic dispatch cycle (guest submit → host execute → guest poll)
2. ✅ Invalid glyph_id error handling
3. ✅ Buffer out of bounds error handling
4. ✅ No BUSY flag = ignored
5. ✅ Glyph output capture verification

**All Tests Pass:**
```
============================================================
ALL TESTS PASSED ✅
============================================================
```

## Verification Gates Passed

| Gate | Status | Evidence |
|------|--------|----------|
| Directory structure created | ✅ | `glyph_dispatch/` exists with all subfolders |
| Glyph ISA copied | ✅ | `src/glyph_isa_v2.py` (28,640 bytes) |
| WGSL shader copied | ✅ | `src/wgsl_glyph_isa_v2.py` (11,499 bytes) |
| Request structure constants | ✅ | `src/dispatch/request_struct.py` validates layout |
| Dispatcher implementation | ✅ | `src/dispatch/dispatcher.py` (11,429 bytes) |
| CPU state extension | ✅ | `src/riscv/cpu_state_mirror.py` adds glyph fields |
| Test suite passes | ✅ | `tests/test_dispatch.py` all 5 tests pass |

## What Was NOT Changed

**Preserved Originals:**
- `tools/glyph_isa_v2.py` — unchanged
- `tools/wgsl_glyph_isa_v2.py` — unchanged
- `tools/RISCV_CPU_MMU.wgsl` — unchanged
- `tools/riscv_gpu_cpu.py` — unchanged
- `tools/qemu_gpu_offload.py` — unchanged

**No Modifications To:**
- Existing GPU emulator infrastructure
- Boot scripts
- Any existing tests

## Next Steps (Phase 2)

### Goal: SHA-256 Acceleration

**Tasks:**
1. Implement SHA-256 glyph kernel
2. Add MMIO handler to `RISCV_CPU_MMU_dispatch.wgsl`
3. Extend `qemu_gpu_offload.py` with `GlyphDispatcher`
4. Write RISC-V guest assembly for SHA-256 dispatch
5. Test: glyph result == Python hashlib.sha256()
6. Measure speedup vs interpreter

**Verification Gate:**
```python
# Compute SHA-256 of 10MB initrd
# Compare results
assert glyph_result == hashlib.sha256(initrd).digest()

# Measure speedup
time_interpreter = time_interpreter_sha256()
time_glyph = time_glyph_sha256()
speedup = time_interpreter / time_glyph
assert speedup > 10, "Expected at least 10x speedup"
```

## Architecture Decision Log

### Why Isolation?

**Decision:** Create `glyph_dispatch/` folder instead of modifying existing files.

**Rationale:**
- No risk to existing working infrastructure
- Clear boundary between control plane and accelerator plane
- Easy to rollback if approach changes
- Enables parallel development (dispatcher independent of RISC-V)

**Tradeoffs:**
- Code duplication (`glyph_isa_v2.py` copied)
- Import path complexity
- Future merge may require deduplication

### Why Polling vs IRQs?

**Decision:** Use BUSY flag polling for Phase 1.

**Rationale:**
- Simpler to implement and test
- No IRQ handling in WGSL yet
- Sufficient for crypto kernels (single-shot)

**Future:** IRQ-based completion for long-running kernels (e.g., network packet processing).

### Why Request Structure in RAM vs MMIO?

**Decision:** Store request fields in RAM, use MMIO only for trigger.

**Rationale:**
- MMIO writes are single 32-bit values
- Request structure has 60 bytes (too large for MMIO)
- RAM allows flexible extension (future fields)
- MMIO trigger provides clear "dispatch now" signal

## Performance Estimates

### Phase 1 (Current):
- Mock dispatch: ~100μs (Python overhead)
- No GPU execution yet

### Phase 2 (SHA-256):
- Expected speedup: 10-100x vs interpreter
- Interpreter: ~0.5 MIPS (crypto bottleneck)
- GPU: 10 MIPS (single instruction)

### Phase 3 (eBPF→Glyph):
- Expected speedup: 100-1000x for packet processing
- Massively parallel shader invocations

## Files Created/Modified

**Created:**
- `glyph_dispatch/README.md`
- `glyph_dispatch/docs/ABI.md`
- `glyph_dispatch/src/dispatch/__init__.py`
- `glyph_dispatch/src/dispatch/dispatcher.py`
- `glyph_dispatch/src/dispatch/request_struct.py`
- `glyph_dispatch/src/glyph/__init__.py`
- `glyph_dispatch/src/riscv/__init__.py`
- `glyph_dispatch/src/riscv/cpu_state_mirror.py`
- `glyph_dispatch/tests/test_dispatch.py`
- `glyph_dispatch/docs/PHASE1_RECEIPT.md` (this file)

**Copied:**
- `glyph_dispatch/src/glyph_isa_v2.py` (from `tools/glyph_isa_v2.py`)
- `glyph_dispatch/src/wgsl_glyph_isa_v2.py` (from `tools/wgsl_glyph_isa_v2.py`)
- `glyph_dispatch/src/riscv/RISCV_CPU_MMU.wgsl` (from `tools/RISCV_CPU_MMU.wgsl`)

**Modified:**
- `glyph_dispatch/src/riscv/cpu_state_mirror.py` (extended with glyph fields)
- `glyph_dispatch/src/dispatch/request_struct.py` (fixed REQUEST_STRUCT_SIZE)

## Known Issues

1. **Import path complexity:** Tests need careful PYTHONPATH setup
   - Mitigation: Add wrapper script to set paths

2. **Code duplication:** `glyph_isa_v2.py` copied to `glyph_dispatch/src/`
   - Mitigation: Future merge or symlink

3. **No GPU execution yet:** Dispatcher runs glyph on CPU
   - Mitigation: Phase 2 will integrate GPU shader

4. **MMIO handler not added:** `RISCV_CPU_MMU.wgsl` still original
   - Mitigation: Phase 2 will add handler

## References

- `docs/ABI.md` — Complete ABI specification
- `README.md` — Architecture overview
- `tests/test_dispatch.py` — Test suite
- `src/dispatch/dispatcher.py` — Dispatcher implementation
- `src/dispatch/request_struct.py` — ABI constants

---

**Signed off:** 2026-08-30
**Next:** Phase 2 — SHA-256 Glyph Kernel