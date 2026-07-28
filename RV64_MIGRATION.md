# RV64 Migration - Skeleton-Driven Development Plan

## System Architecture Overview

```
Python Host (spatial_rv64i_cpu.py)          WGSL Compute Shader (SPATIAL_RV64I.wgsl)
┌─────────────────────────────────┐      ┌──────────────────────────────────┐
│ 1. Initialize WebGPU Device       │      │ struct CPUState {                │
│ 2. Allocate Buffers:              │      │   pc_low, pc_high: u32,          │ ← 64-bit PC
│    - registers: 32 * 8 bytes      │◄────►│   halted: u32,                   │
│    - cpu_state: ~80 bytes         │◄────►│   steps_remaining: u32,          │
│    - csr: 4096 * 4 bytes          │◄────►│   mode: u32,                     │
│    - uart: 4096 * 4 bytes         │◄────►│   ...                           │
│ 3. Build Bind Group Layout        │      │ }                               │
│ 4. Load WGSL + Create Pipeline    │      │                                  │
│ 5. Dispatch Compute Workgroups    │      │ struct RegisterFile {            │
│ 6. Read Back State (np.uint64)    │◄────►│   regs: array<vec2<u32>, 32>,    │ ← 64-bit regs
│    - regs: vec2<u32> → np.uint64  │◄────►│ }                               │
│    - pc: two u32 → np.uint64      │◄────►│                                  │
│                                  │      │ fn u64_add(a: vec2<u32>,         │ ← 64-bit math
│                                  │      │           b: vec2<u32>) → vec2<u32> │
│                                  │      │ fn u64_sub(a: vec2<u32>,         │
│                                  │      │           b: vec2<u32>) → vec2<u32> │
│                                  │      │ fn u64_shl(a: vec2<u32>,         │
│                                  │      │           shift: u32) → vec2<u32> │
│                                  │      │ fn u64_shr(a: vec2<u32>,         │
│                                  │      │           shift: u32) → vec2<u32> │
└─────────────────────────────────┘      │ fn u64_sar(a: vec2<u32>,         │
                                         │           shift: u32) → vec2<u32> │
                                         │                                  │
                                         │ fn execute_instruction(...) {    │ ← STUB
                                         │   // Placeholder: return 0      │
                                         │ }                               │
                                         └──────────────────────────────────┘
```

## Phase 1: Skeleton Generation (CURRENT)

### WGSL Structure (SPATIAL_RV64I.wgsl)

**Struct Definitions:**
```wgsl
// 64-bit PC split into two u32s (low, high)
struct CPUState {
    pc_low: u32,    // Low 32 bits of 64-bit PC
    pc_high: u32,   // High 32 bits of 64-bit PC
    halted: u32,
    steps_remaining: u32,
    mode: u32,              // 0=U, 1=S, 3=M
    trap_pending: u32,
    reservation_valid: u32,
    reservation_addr_low: u32,
    reservation_addr_high: u32,
    uart_tx_len: u32,
    mtime_low: u32,
    mtime_high: u32,
    mtimecmp_low: u32,
    mtimecmp_high: u32,
    ram_base_low: u32,
    ram_base_high: u32,
    uart_rx_data_pending: u32,
    uart_rx_byte: u32,
    _pad: array<u32, 5>,    // Align to CSR offset (40 bytes)
}

// 32 x 64-bit registers (each as vec2<u32>)
struct RegisterFile {
    regs: array<vec2<u32>, 32>,
}
```

**64-Bit Math Helpers (STUBS ONLY):**
```wgsl
// 64-bit addition: returns (low, high) with carry propagation
fn u64_add(a: vec2<u32>, b: vec2<u32>) -> vec2<u32> {
    // STUB: return a
    return a;
}

// 64-bit subtraction with borrow
fn u64_sub(a: vec2<u32>, b: vec2<u32>) -> vec2<u32> {
    // STUB: return a
    return a;
}

// 64-bit left shift (shift < 64)
fn u64_shl(a: vec2<u32>, shift: u32) -> vec2<u32> {
    // STUB: return a
    return a;
}

// 64-bit logical right shift
fn u64_shr(a: vec2<u32>, shift: u32) -> vec2<u32> {
    // STUB: return a
    return a;
}

// 64-bit arithmetic right shift (sign-extended)
fn u64_sar(a: vec2<u32>, shift: u32) -> vec2<u32> {
    // STUB: return a
    return a;
}

// Sign-extend 32-bit value to 64-bit
fn sext_32_to_64(value: i32) -> vec2<u32> {
    let low = bitcast<u32>(value);
    let high = select(0u, 0xFFFFFFFFu, value < 0);
    return vec2<u32>(low, high);
}
```

**Instruction Decode/Execute (STUB ONLY):**
```wgsl
fn execute_instruction(cpu: ptr<function, RiscvCPU>) {
    // STUB: Placeholder
    // Will be populated in Phase 3
}
```

### Python Bridge Structure (spatial_rv64i_cpu.py)

**Buffer Allocation Changes:**
```python
class RegisterFile:
    """
    32 x 64-bit GPU memory representing RV64I registers.
    Each register is stored as vec2<u32> (low, high).
    """
    def __init__(self, device: wgpu.GPUDevice):
        self.buffer = device.create_buffer(
            size=32 * 8,  # 32 registers * 8 bytes each (64-bit)
            usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_DST | wgpu.BufferUsage.COPY_SRC
        )

class SpatialRV64ICore:
    def __init__(self, memory_size_bytes: int = 1024 * 1024, trace_file: Optional[str] = None):
        # ... device setup ...

        # CPUState: 18 fields (2 u32 each for 64-bit values) + 5 pad u32 = ~80 bytes
        self.state_buffer = self.device.create_buffer(
            size=80,  # Matches WGSL CPUState struct size
            usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_DST | wgpu.BufferUsage.COPY_SRC
        )

        # Flat CSR file: still 4096 * 4 bytes (CSRs are 32-bit in RV64I base)
        self.csr_buffer = self.device.create_buffer(
            size=4096 * 4,
            usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_DST | wgpu.BufferUsage.COPY_SRC
        )

        # UART: unchanged
        self.uart_capacity = 4096
        self.uart_buffer = self.device.create_buffer(
            size=self.uart_capacity * 4,
            usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_DST | wgpu.BufferUsage.COPY_SRC
        )
```

**64-Bit Accessors (STUBS ONLY):**
```python
def read_register(self, reg_id: int) -> np.uint64:
    """
    Read a 64-bit register from GPU memory.
    Returns: np.uint64
    """
    # STUB: read low+high from vec2<u32> buffer
    return np.uint64(0)

def write_register(self, reg_id: int, value: np.uint64):
    """
    Write a 64-bit register to GPU memory.
    """
    # STUB: write value as vec2<u32> (low, high)
    pass

def read_pc(self) -> np.uint64:
    """
    Read the 64-bit program counter.
    """
    # STUB: read pc_low + pc_high from CPUState
    return np.uint64(0)

def write_pc(self, value: np.uint64):
    """
    Write the 64-bit program counter.
    """
    # STUB: write pc_low + pc_high to CPUState
    pass
```

## Phase 2: Architectural Lock

**Pre-Test Checklist:**
1. ✅ Does the skeleton define ALL required side effects? YES (buffer sizes, struct layouts)
2. ✅ Are runtime globals/data structures mapped in the skeleton? YES (CPUState, RegisterFile)
3. ✅ Is the memory boundary condition explicit? YES (buffer sizes defined)
4. ✅ Can the skeleton complete initialization without unimplemented dependencies? YES (stubs return defaults)
5. ✅ For opaque interfaces: Has binary analysis revealed what WILL be called? N/A (we own the emulator)

**Verification Steps:**
```bash
# 1. Verify WGSL compiles
python3 -c "
import wgpu
wgsl = Path('tools/SPATIAL_RV64I.wgsl').read_text()
device = wgpu.utils.get_default_device()
shader = device.create_shader_module(code=wgsl)
print('WGSL compiles ✓')
"

# 2. Verify Python initializes without errors
python3 -c "
from tools.spatial_rv64i_cpu import SpatialRV64ICore
core = SpatialRV64ICore(memory_size_bytes=1024*1024)
print('Python skeleton initializes ✓')
"
```

## Phase 3: Iterative Population

**Implementation Order:**

1. **64-Bit Arithmetic Helpers** (low risk, high utility)
   - Implement `u64_add`, `u64_sub`, `u64_shl`, `u64_shr`, `u64_sar`
   - Test: Basic 64-bit math operations

2. **Python Bridge Accessors** (must match WGSL struct layout)
   - Implement `read_register`, `write_register`, `read_pc`, `write_pc`
   - Test: Round-trip register reads/writes

3. **Instruction Decode Update** (add RV64I opcodes)
   - Add new instruction formats: I-type for 64-bit immediates, S-type for 64-bit stores
   - Implement `decode_instruction_64` function

4. **RV64I Base Instructions** (core set needed for Ubuntu)
   - Load/Store: `ld` (64-bit load), `sd` (64-bit store), `lwu` (32-bit zero-extend)
   - ALU: `addi`, `sltiu` (64-bit operands), `slli`, `srli`, `srai` (6-bit shift)
   - Register: `add`, `sub`, `and`, `or`, `xor`, `slt`, `sltu` (64-bit)
   - Branch: `beq`, `bne`, `blt`, `bge`, `bltu`, `bgeu` (64-bit compare)

5. **RV64M Instructions** (multiply/divide, needed for Ubuntu userland)
   - `mulw`, `divw`, `remw` (32-bit ops producing 32-bit results)
   - `mul`, `mulh`, `mulhu`, `mulhsu`, `div`, `rem` (full 64-bit)

6. **Sv39 MMU** (Ubuntu requirement)
   - 3-level page tables (4096-byte pages)
   - 39-bit virtual addresses (512GB address space)
   - PTE format with permissions (U/X/W/R/V)

7. **CSR Updates** (64-bit CSRs)
   - `mstatus`, `mtvec`, `mepc`, `mcause` → 64-bit variants
   - Add `satp` (Sv39 MMU control CSR)

8. **Integration Testing**
   - Boot Alpine Linux (RV64 port if available, or build minimal RV64 test kernel)
   - Verify CSR preservation
   - Verify 64-bit address space operations

**Verification Gate (before claiming ROADMAP complete):**
```bash
# Run RV64I instruction tests
python3 tests/test_spatial_rv64i_cpu.py

# Boot lightweight RV64 kernel
python3 tools/boot_rv64_kernel.py --kernel boot_images/rv64_alpine_Image

# Compare with QEMU for validation
python3 tools/diff_qemu_gpu_traces.py --trace rv64_boot_trace.txt
```

## Integration with Existing RV32 Codebase

**Preserve RV32 as Reference:**
- `SPATIAL_RV32I.wgsl` and related files remain untouched
- Use RV32 implementation as oracle for instruction semantics
- Cross-reference instruction decode/execute logic during RV64 implementation

**Shared Components (no changes needed):**
- UART buffers and TX ring logic (unchanged)
- Memory region abstraction (unchanged)
- Hilbert curve ordering (unchanged)
- CSR file size (still 4096 * 4 bytes)

## Architectural Constraints

**Non-Negotiable:**
1. **64-bit PC**: Must support >4GB address space for Ubuntu
2. **Sv39 MMU**: Ubuntu requires virtual memory
3. **CSR Offset Stability**: CSRs must remain at offset 40 to preserve Alpine boot path
4. **WGSL vec2<u32> Representation**: No native 64-bit in WGSL, must use low/high pattern

**Performance Targets:**
- Decode speed: ≤8ms per audio second (same as RV32)
- 64-bit ops: 4-6x speedup on GPU (vs QEMU, matching RV32 results)
- Memory footprint: ≤2x RV32 (due to wider registers)

## Next Actions

**Phase 1 (Now):**
- Create WGSL skeleton with widened structs and stubbed 64-bit math helpers
- Update Python bridge buffer sizes and stubbed accessors
- Verify skeleton compiles/initializes

**Phase 2 (Next):**
- Architectural lock review
- CSR offset verification
- Memory boundary validation

**Phase 3 (Subsequent):**
- Iteratively populate implementation following the order above
- Test after each milestone
- Compare with QEMU traces for correctness

---

**Status:** Phase 1 (Skeleton Generation) - IN PROGRESS
**Created:** 2026-07-26
**Next Step:** Apply WGSL struct changes and Python buffer size updates