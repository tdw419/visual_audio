# Glyph Dispatch — Hybrid RISC-V/GPU Acceleration

**Status:** Phase 0 — Setup & isolation

## Architecture

```
RISC-V Interpreter (Control Plane)
    ↓
MMIO Dispatch Trigger (0x8800_0000)
    ↓
Host Python Dispatcher
    ↓
Glyph ISA Kernel (GPU Compute Shader)
    ↓
Results back to Shared RAM
```

**Pattern:** Strangler-fig migration — keep RISC-V running, accelerate hot paths with glyph kernels.

## Directory Structure

```
glyph_dispatch/
├── src/
│   ├── glyph/          # Glyph ISA tooling
│   │   ├── glyph_isa_v2.py         # OpcodeMap, Assembler, CPU (copied/adapted)
│   │   └── wgsl_glyph_isa_v2.py    # GPU shader generator (copied/adapted)
│   │
│   ├── riscv/          # RISC-V WGSL interpreter extensions
│   │   ├── RISCV_CPU_MMU.wgsl      # Original, read-only reference
│   │   └── RISCV_CPU_MMU_dispatch.wgsl  # Patched with glyph dispatch MMIO
│   │
│   ├── dispatch/       # Dispatch ABI implementation
│   │   ├── dispatcher.py           # GlyphDispatcher class
│   │   └── request_struct.py       # Request structure constants
│   │
│   └── offload/        # Offload harness
│       └── run_with_glyph_dispatch.py  # Main loop integration
│
├── tests/
│   ├── fixtures/       # Test glyph programs (.glyph, .png)
│   └── test_dispatch.py  # Dispatch tests
│
└── docs/
    ├── ABI.md          # Dispatch ABI specification
    └── PHASE1_RECEIPT.md  # Phase 1 completion verification
```

## Copy Policy

**What gets copied:**
- `tools/glyph_isa_v2.py` → `src/glyph/` (isolated, no changes to original)
- `tools/riscv_gpu_cpu.py` → `src/riscv/` (for CPU struct mirroring)

**What gets patched (new files):**
- `src/riscv/RISCV_CPU_MMU_dispatch.wgsl` — adds glyph MMIO handler
- `src/dispatch/dispatcher.py` — new dispatcher implementation

**What stays as reference (read-only):**
- `tools/RISCV_CPU_MMU.wgsl` → `src/riscv/RISCV_CPU_MMU.wgsl` (for comparison)

**What we don't touch:**
- `tools/qemu_gpu_offload.py` — extends it via import, doesn't modify
- All existing boot scripts
- All existing GPU emulator infrastructure

## Memory Layout

### Request Structure (Guest RAM)

```
Base: 0x8100_1000 (reserved region in shared RAM)
Size: 48 bytes

Offset | Size | Field            | Direction
-------|------|------------------|------------
0x00   | 4    | flags            | RISC-V→Host
       |      |  BIT0: BUSY (1=executing, 0=done)
       |      |  BIT1: ERROR (1=failed)
0x04   | 4    | glyph_id         | RISC-V→Host (which glyph kernel)
0x08   | 8    | input_buf_ptr    | RISC-V→Host (guest physical address)
0x10   | 8    | input_buf_len    | RISC-V→Host
0x18   | 8    | output_buf_ptr   | RISC-V→Host (guest physical address)
0x20   | 8    | output_buf_len   | RISC-V→Host
0x28   | 4    | result_status    | Host→RISC-V (0=success, -1=error)
0x2C   | 4    | reserved[4]      | —
```

### MMIO Trigger

```
Base: 0x8800_0000
Size: 4 bytes (write-only)

Write any value to trigger dispatch. Sets BUSY flag in request structure.
```

## Phase 1 Goals

1. ✅ Directory structure created
2. ⏳ Copy/adapt `glyph_isa_v2.py` (preserve original behavior)
3. ⏳ Create `RISCV_CPU_MMU_dispatch.wgsl` with glyph MMIO handler
4. ⏳ Implement `GlyphDispatcher.check_dispatch()`
5. ⏳ Write minimal test glyph program
6. ⏳ Verify RISC-V→Glyph→RISC-V round trip
7. ⏳ Generate receipt documenting successful dispatch

## Verification Gates

### Test 1: Basic Dispatch
```python
# Guest writes request structure
# Guest triggers MMIO
# Host detects trigger
# Host runs glyph
# Host writes results
# Guest reads results
assert result == expected_value
```

### Test 2: SHA-256 Acceleration (Phase 2)
- Compute SHA-256 of 10MB initrd
- Verify: glyph result == interpreter result
- Measure: speedup factor

### Test 3: eBPF→Glyph (Phase 3)
- Parse eBPF bytecode
- Transpile to glyph assembly
- Verify output matches eBPF interpreter

## Non-Goals (What We're NOT Doing)

- ❌ Replacing the RISC-V interpreter (it stays forever)
- ❌ Compiling the whole kernel to WGSL (impossible)
- ❌ MMU/page-table walks on GPU (stays on RISC-V)
- ❌ Unbounded control flow on GPU (eBPF verifier restricts this)
- ❌ Modifying existing tools (everything new/patched in this folder)

## Related Skills

- `glyph-spatial-isa` — Glyph ISA opcodes and patterns
- `gpu-riscv-emulator` — RISC-V WGSL interpreter
- `geometry-os-hypervisor-bridge` — Spatial syscall integration

## Contact

For questions about the dispatch ABI, see `docs/ABI.md`.