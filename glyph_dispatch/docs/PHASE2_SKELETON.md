# Phase 2 Skeleton — Glyph Dispatch Integration

**Date:** 2026-08-30
**Status:** ✅ Phase 1 COMPLETE — All skeletons generated
**Next:** Phase 2 — Architectural Lock (add implementation intent comments)

---

## What Was Created

### 1. WGSL Skeleton: `src/riscv/RISCV_CPU_MMU_dispatch.wgsl`

**Purpose:** Extend RISC-V WGSL shader with glyph dispatch MMIO handler.

**Key Components:**
```wgsl
// Extended CPU struct with glyph fields
struct RiscvCPUDispatch {
    // ... original fields ...
    glyph_busy: u32,           // Offset 516
    glyph_last_trigger: u32,  // Offset 520
}

// MMIO handler stubs
fn is_glyph_dispatch_mmio(pa: vec2<u32>) -> bool;
fn handle_glyph_dispatch_write(cpu: ptr<function, RiscvCPUDispatch>, value: u32);
fn validate_glyph_request(cpu: ptr<function, RiscvCPUDispatch>) -> bool;

// Integration point
fn mmio_write_glyph_extension(...);
```

**Constants:** Match `src/dispatch/request_struct.py`:
- `GLYPH_DISPATCH_TRIGGER_MMIO: 0x88000000u`
- `REQUEST_STRUCT_BASE: 0x81001000u`
- Field offsets, flags, result status codes

**Verification:** WGSL compiles with only dead code warnings.

---

### 2. Python Skeleton: `src/offload/run_with_glyph_dispatch.py`

**Purpose:** Extend `qemu_gpu_offload.py` workflow with glyph dispatch checking.

**Key Components:**
```python
class GlyphDispatchHarness:
    def __init__(self, ram, state_buffer, glyph_db_path): # STUB
    def check_and_dispatch(self) -> bool: # STUB
    def get_statistics(self) -> Dict[str, int]: # STUB

def run_with_offload_glyph_extended(
    core, disk_path, ..., enable_glyph_dispatch=False
) -> dict: # STUB
```

**Statistics Tracking:**
- `offload_count`: Total glyph kernels executed
- `error_count`: Failed glyph executions

**Integration Points:**
- Import from `qemu_gpu_offload` (Phase 3)
- Wire `check_and_dispatch()` into main loop
- Return statistics dict with both VirtIO and glyph counts

**Verification:** Python compiles with no errors.

---

### 3. Test Skeleton: `tests/test_sha256_dispatch.py`

**Purpose:** End-to-end verification of SHA-256 glyph dispatch.

**Key Components:**
```python
class MockGpuRam: # STUB
    def read_u32(self, gpa) -> int: # STUB
    def write_u32(self, gpa, val): # STUB
    # ... other methods ...

def create_sha256_glyph_kernel() -> GlyphProgram: # STUB

def generate_sha256_dispatch_assembly(...) -> str: # STUB

def test_sha256_dispatch_mock(): # STUB
def test_sha256_round_trip(): # STUB
def test_sha256_large_input(): # STUB
```

**Test Cases:**
1. **Phase 3:** Mock dispatch with placeholder kernel
2. **Phase 4:** SHA-256 accuracy vs `hashlib.sha256()`
3. **Phase 4:** 10MB initrd speedup (target: ≥10x)

**Verification:** Python compiles with no errors.

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                    RISC-V Guest (Interpreter)                   │
│                                                                  │
│  ┌─────────────────┐    1. Write request structure           │
│  │ Guest Code      │──────► to RAM (0x8100_1000)               │
│  │ (SHA-256 call)  │                                         │
│  └────────┬────────┘                                         │
│           │                                                  │
│           │ 2. Write MMIO trigger (0x8800_0000)             │
│           ▼                                                  │
│  ┌─────────────────┐                                         │
│  │ RISC-V WGSL     │                                         │
│  │ (Interpreter)   │                                         │
│  └─────────────────┘                                         │
│           │                                                  │
│           │ 3. Set glyph_busy = 1                            │
│           ▼                                                  │
└───────────┼──────────────────────────────────────────────────┘
            │
            │ GPU state buffer
            │
┌───────────▼──────────────────────────────────────────────────┐
│                     Host Python                                │
│                                                                  │
│  ┌─────────────────┐                                         │
│  │ run_with_       │ 4. Poll GPU state, detect glyph_busy    │
│  │ glyph_dispatch  │─────┐                                    │
│  └─────────────────┘     │                                    │
│                          │                                    │
│  ┌───────────────────────▼──────┐                             │
│  │ GlyphDispatchHarness          │                             │
│  │ - check_and_dispatch()        │                             │
│  │ - Load glyph program          │                             │
│  │ - Execute on GPU              │                             │
│  │ - Write results back          │                             │
│  └───────────────────────┬──────┘                             │
│                          │                                    │
│  ┌───────────────────────▼──────┐                             │
│  │ Glyph ISA (SHA-256 Kernel)   │                             │
│  │ - OpcodeMapV2                 │                             │
│  │ - GlyphAssemblerV2            │                             │
│  │ - GlyphCPUv2                  │                             │
│  └───────────────────────┬──────┘                             │
│                          │                                    │
└──────────────────────────┼────────────────────────────────────┘
                           │
                           │ Write results to RAM
                           │ Clear BUSY flag
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                    RISC-V Guest (Interpreter)                   │
│                                                                  │
│  ┌─────────────────┐                                         │
│  │ Guest Code      │ 5. Poll BUSY flag until cleared            │
│  │ (SHA-256 call)  │─────┐                                    │
│  └────────┬────────┘     │                                    │
│           │              │                                    │
│           │ 6. Read       │                                    │
│           ▼    results   │                                    │
│  ┌─────────────────┐     │                                    │
│  │ Output Buffer   │─────┘                                    │
│  │ (0x8100_3000)   │                                         │
│  └─────────────────┘                                         │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Data Flow

### Step 1: Guest Submit Request
```asm
# RISC-V guest assembly (Phase 4)
li a0, 0x8100_1000          # Request base
li t0, 1
sw t0, 0(a0)                # Set BUSY flag
li t0, 10                    # glyph_id = SHA-256
sw t0, 4(a0)                # Write glyph_id
# ... set input/output buffers ...
li t0, 0x8800_0000
sw zero, 0(t0)               # Trigger MMIO
```

### Step 2: WGSL MMIO Handler
```wgsl
fn mmio_write_glyph_extension(cpu, pa, value, size) {
    if (is_glyph_dispatch_mmio(pa)) {
        handle_glyph_dispatch_write(cpu, value);
        return;
    }
    // ... existing MMIO handling ...
}
```

### Step 3: Host Detect Trigger
```python
# run_with_glyph_dispatch.py
while True:
    # Read GPU state
    state_arr = read_gpu_state()

    # Check glyph_busy (Phase 3)
    if glyph_harness.check_and_dispatch():
        glyph_offloads += 1

    # Step core
    core.step_n(slice_steps)
```

### Step 4: Glyph Execution
```python
# GlyphDispatcher.check_dispatch()
# 1. Read request structure from RAM
# 2. Validate glyph_id, buffers
# 3. Load glyph program
# 4. Execute (Phase 4: SHA-256)
# 5. Write results back
# 6. Clear BUSY flag
```

### Step 5: Guest Poll Completion
```asm
# RISC-V guest assembly (Phase 4)
1:
  lw t1, 0(a0)                # Read flags
  andi t1, t1, 1              # Extract BUSY bit
  bnez t1, 1b                 # Loop if BUSY still set

lw t1, 0x28(a0)              # Read result_status
bnez t1, error               # Non-zero = error

# Output buffer now has SHA-256 hash!
```

---

## Phase 2 Tasks (Architectural Lock)

### Task 1: WGSL Implementation Intent Comments

**File:** `src/riscv/RISCV_CPU_MMU_dispatch.wgsl`

**Add comments to stub functions:**
- `is_glyph_dispatch_mmio()`: How to compare pa with `0x8800_0000`
- `handle_glyph_dispatch_write()`: How to set `glyph_busy`, validate request
- `validate_glyph_request()`: What fields to check, error conditions

### Task 2: Python Integration Intent Comments

**File:** `src/offload/run_with_glyph_dispatch.py`

**Add comments to stub methods:**
- `GlyphDispatchHarness.__init__()`: How to create `GlyphDispatcher`
- `check_and_dispatch()`: When to call, return value meaning
- `run_with_offload_glyph_extended()`: Where to insert into existing loop

### Task 3: Test Verification Intent Comments

**File:** `tests/test_sha256_dispatch.py`

**Add comments to test functions:**
- `MockGpuRam`: Bounds checking logic
- `test_sha256_dispatch_mock()`: What asserts verify
- `test_sha256_round_trip()`: Reference implementation (`hashlib.sha256`)
- `test_sha256_large_input()`: Speedup measurement method

---

## Phase 3 Tasks (Initial Population)

### Task 1: Implement WGSL MMIO Handler

**File:** `src/riscv/RISCV_CPU_MMU_dispatch.wgsl`

**Implement:**
1. `is_glyph_dispatch_mmio()` — compare pa_low with `0x8800_0000`
2. `handle_glyph_dispatch_write()` — set `glyph_busy = 1`
3. `validate_glyph_request()` — read flags, check BUSY flag

**Verification:** WGSL compiles, dead code warnings on unused helpers.

### Task 2: Implement Python Harness

**File:** `src/offload/run_with_glyph_dispatch.py`

**Implement:**
1. `GlyphDispatchHarness.__init__()` — create `GlyphDispatcher`
2. `check_and_dispatch()` — call `dispatcher.check_dispatch()`, track stats
3. Enable imports from `qemu_gpu_offload`

**Verification:** Python compiles, import errors resolved.

### Task 3: Implement Mock RAM

**File:** `tests/test_sha256_dispatch.py`

**Implement:**
1. `MockGpuRam` bounds checking
2. Read/write methods (u32, u64, bytes)
3. `test_sha256_dispatch_mock()` — write request, call dispatch, verify

**Verification:** Test passes, BUSY flag cleared, result_status = success.

---

## Phase 4 Tasks (SHA-256 Implementation)

### Task 1: Implement SHA-256 Glyph Kernel

**File:** `src/offload/sha256_glyph.glyph` (new)

**Implement:**
1. SHA-256 compression function in Glyph ISA
2. Message padding (append 0x80, zero padding, length)
3. Process message in 512-bit blocks
4. Output 32-byte hash

**Verification:** `glyph_sha256("test") == hashlib.sha256(b"test").digest()`

### Task 2: End-to-End Test

**File:** `tests/test_sha256_dispatch.py`

**Implement:**
1. `test_sha256_round_trip()` — compare glyph vs Python
2. `test_sha256_large_input()` — 10MB test, measure speedup

**Verification:** All tests pass, speedup ≥10x.

---

## Verification Gates

### Phase 1 (COMPLETE)
- ✅ WGSL skeleton compiles
- ✅ Python skeleton compiles
- ✅ Test skeleton compiles
- ✅ All stubs return correct types

### Phase 2 (NEXT)
- ⏳ Add implementation intent comments to WGSL
- ⏳ Add implementation intent comments to Python
- ⏳ Add implementation intent comments to tests
- ⏳ Review and lock architecture

### Phase 3
- ⏳ WGSL MMIO handler implements address check
- ⏳ Python harness imports correctly
- ⏳ Mock RAM bounds checking works
- ⏳ Mock dispatch test passes

### Phase 4
- ⏳ SHA-256 glyph kernel accurate
- ⏳ End-to-end test passes
- ⏳ 10MB speedup ≥10x

---

## Integration Plan

### Step 1: Merge WGSL into Original

```bash
# Phase 3: Apply patch to RISCV_CPU_MMU.wgsl
# - Add glyph_busy and glyph_last_trigger fields to RiscvCPU struct
# - Add MMIO handler in mmio_write_fn()
# - Add helper functions (is_glyph_dispatch_mmio, etc.)
```

### Step 2: Extend qemu_gpu_offload.py

```bash
# Phase 3: Add GlyphDispatchHarness integration
# - Import GlyphDispatcher from glyph_dispatch module
# - Create harness in run_with_offload()
# - Call check_and_dispatch() in main loop
# - Report glyph statistics
```

### Step 3: Enable GPU Execution

```bash
# Phase 4: Integrate WGSL shader with GlyphCPUv2
# - Load glyph program into GPU texture
# - Dispatch compute shader
# - Read back results
```

---

## Known Risks & Mitigations

### Risk 1: WGSL Struct Layout Mismatch

**Problem:** `RiscvCPUDispatch` field order doesn't match `CPU_DTYPE_EXTENDED`.

**Mitigation:**
- Phase 2: Verify field order matches exactly
- Phase 3: Run compilation, check for struct size errors
- Phase 3: Test GPU state buffer read/write

### Risk 2: Python Import Path Complexity

**Problem:** `glyph_dispatch` module not in PYTHONPATH.

**Mitigation:**
- Phase 2: Document import paths in comments
- Phase 3: Add sys.path manipulation in harness
- Phase 3: Test imports in isolation before integration

### Risk 3: GPU Execution Fails

**Problem:** WGSL shader won't compile or dispatch fails.

**Mitigation:**
- Phase 3: Test WGSL compilation in isolation
- Phase 3: Verify bind group layout matches CPU state
- Phase 4: Start with simple test glyph (no SHA-256)

### Risk 4: Address Bounds Check Missing

**Problem:** Guest writes request structure at invalid address.

**Mitigation:**
- Phase 2: Document bounds checking requirements
- Phase 3: Implement in `validate_glyph_request()`
- Phase 3: Test with invalid addresses

---

## Files Created

| File | Size | Purpose | Phase |
|------|------|---------|-------|
| `src/riscv/RISCV_CPU_MMU_dispatch.wgsl` | 8.7KB | WGSL MMIO handler skeleton | 1 |
| `src/offload/run_with_glyph_dispatch.py` | 8.5KB | Python integration skeleton | 1 |
| `tests/test_sha256_dispatch.py` | 13.2KB | End-to-end test skeleton | 1 |
| `docs/PHASE2_SKELETON.md` | This file | Architectural lock document | 1 |

**Total Phase 1 Output:** ~30KB of scaffold code

---

## References

- `docs/ABI.md` — Dispatch ABI specification
- `src/dispatch/request_struct.py` — ABI constants
- `src/dispatch/dispatcher.py` — GlyphDispatcher implementation
- `src/riscv/cpu_state_mirror.py` — CPU struct definitions
- `tools/RISCV_CPU_MMU.wgsl` — Original WGSL interpreter
- `tools/qemu_gpu_offload.py` — Original offload harness

---

**Signed off:** 2026-08-30
**Next:** Phase 2 — Add implementation intent comments to all stubs
**After Phase 2:** Phase 3 — Implement MMIO handler and Python harness