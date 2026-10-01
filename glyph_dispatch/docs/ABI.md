# Glyph Dispatch ABI Specification

## Overview

The Glyph Dispatch ABI defines the contract between the RISC-V interpreter (control plane) and glyph kernels (accelerator plane) running on GPU.

**Key principle:** Asynchronous, non-blocking dispatch. RISC-V guest triggers, continues, polls for completion.

## Memory Regions

### 1. Request Structure (Guest RAM)

**Base:** `0x8100_1000`
**Size:** `48 bytes`
**Access:** RISC-V (read/write) ↔ Host (read/write)

| Offset | Size | Field           | Type    | Direction      | Description |
|--------|------|-----------------|---------|----------------|-------------|
| 0x00   | 4    | flags           | u32     | RISC-V→Host    | Control flags |
|        |      |                 |         |                | BIT0: BUSY (1=executing, 0=done) |
|        |      |                 |         |                | BIT1: ERROR (1=failed) |
|        |      |                 |         |                | BIT2-31: Reserved (must be 0) |
| 0x04   | 4    | glyph_id        | u32     | RISC-V→Host    | Glyph kernel identifier |
| 0x08   | 8    | input_buf_ptr   | u64     | RISC-V→Host    | Guest physical address of input buffer |
| 0x10   | 8    | input_buf_len   | u64     | RISC-V→Host    | Input buffer length in bytes |
| 0x18   | 8    | output_buf_ptr  | u64     | RISC-V→Host    | Guest physical address of output buffer |
| 0x20   | 8    | output_buf_len  | u64     | RISC-V→Host    | Output buffer length in bytes |
| 0x28   | 4    | result_status   | u32     | Host→RISC-V    | 0=success, -1=error |
| 0x2C   | 4    | reserved[4]     | u32[4]  | —              | Must be zero (for future expansion) |

**Alignment:** All fields are naturally aligned (u32 on 4-byte boundary, u64 on 8-byte boundary).

### 2. MMIO Dispatch Trigger

**Base:** `0x8800_0000`
**Size:** `4 bytes` (write-only)
**Access:** RISC-V (write) → Host (detect)

**Behavior:**
- RISC-V guest writes any 32-bit value to trigger dispatch
- Host detects trigger via GPU state read
- Host sets BUSY flag in request structure
- Host clears BUSY flag when glyph execution completes

**Note:** The written value is ignored; only the write side-effect matters.

### 3. CPU State Extension (GPU Buffer)

**Location:** `RiscvCPU` struct in WGSL shader
**Fields added:**

```wgsl
struct RiscvCPU {
    // ... existing fields ...

    // Glyph dispatch state
    glyph_busy: u32,           // 1 = glyph kernel running, 0 = idle
    glyph_last_trigger: u32,   // Last value written to MMIO trigger
}
```

**Access:** Host reads/writes via state buffer sync.

## Dispatch Protocol

### Step-by-Step Flow

#### 1. Guest Prepare Request (RISC-V)

```asm
# Write request structure
li a0, 0x8100_1000      # a0 = request base

# Set BUSY flag
li t0, 1
sw t0, 0(a0)

# Set glyph_id (e.g., 1 for SHA-256)
li t0, 1
sw t0, 4(a0)

# Set input buffer
li t0, 0x8100_2000      # input buffer address
sd t0, 8(a0)
li t0, 1024             # input length
sd t0, 16(a0)

# Set output buffer
li t0, 0x8100_3000      # output buffer address
sd t0, 24(a0)
li t0, 32               # output length
sd t0, 32(a0)

# Trigger dispatch
li t0, 0x8800_0000
sw zero, 0(t0)          # Write any value (zero)
```

#### 2. Host Detect Trigger (Python)

```python
# Read CPU state from GPU
state_bytes = core.queue.read_buffer(core.state_buffer)
state_arr = np.frombuffer(state_bytes, dtype=np.uint32)

# Check glyph_busy flag
glyph_busy = state_arr[GLYPH_BUSY_OFFSET]
if glyph_busy == 1:
    # Trigger detected, process dispatch
    process_glyph_dispatch()
```

#### 3. Host Process Dispatch (Python)

```python
def process_glyph_dispatch():
    # Read request structure from shared RAM
    req_base = 0x8100_1000

    flags = ram.read_u32(req_base)
    glyph_id = ram.read_u32(req_base + 4)
    input_ptr = ram.read_u64(req_base + 8)
    input_len = ram.read_u64(req_base + 16)
    output_ptr = ram.read_u64(req_base + 24)
    output_len = ram.read_u64(req_base + 32)

    # Validate request
    if flags & 1 == 0:
        return  # BUSY flag not set? Spurious trigger
    if glyph_id not in glyph_registry:
        # Mark error
        ram.write_u32(req_base, flags | 2)  # Set ERROR
        ram.write_u32(req_base + 0x28, -1)  # result_status = -1
        clear_glyph_busy()
        return

    # Load input data
    input_data = ram.read_bytes(input_ptr, input_len)

    # Execute glyph kernel
    glyph_program = glyph_registry[glyph_id]
    output_data = run_glyph_program(glyph_program, input_data)

    # Write output data back
    ram.write_bytes(output_ptr, output_data[:output_len])

    # Mark completion
    ram.write_u32(req_base, flags & ~1)  # Clear BUSY
    ram.write_u32(req_base + 0x28, 0)   # result_status = success

    # Clear glyph_busy in CPU state
    clear_glyph_busy()
```

#### 4. Guest Poll for Completion (RISC-V)

```asm
# Poll BUSY flag until cleared
1:
  lw t1, 0(a0)
  andi t1, t1, 1        # Extract BUSY bit
  bnez t1, 1b           # Loop if BUSY still set

# Check result status
lw t1, 0x28(a0)
bnez t1, error         # Non-zero = error

# Output buffer now has result!
# Continue execution...
```

### Synchronization Guarantees

1. **Guest must set BUSY flag before triggering** — ensures host sees complete request
2. **Host must clear BUSY flag before clearing glyph_busy** — ensures guest sees completion
3. **Guest must check result_status after BUSY cleared** — handles error cases
4. **Host must clear glyph_busy after writing results** — prevents guest from seeing stale state

## Error Handling

### Error Conditions

| Error Condition               | Host Action                              | Guest Detection |
|-------------------------------|------------------------------------------|-----------------|
| Invalid glyph_id              | Set ERROR bit, result_status = -1        | Check result_status != 0 |
| Input buffer out of bounds    | Set ERROR bit, result_status = -1        | Check result_status != 0 |
| Output buffer too small       | Write partial output, result_status = -2 | Check result_status == -2 |
| Glyph execution failed        | Set ERROR bit, result_status = -3        | Check result_status == -3 |
| BUSY flag not set (spurious)  | Ignore trigger (no action)               | None (no dispatch) |

### result_status Values

| Value | Meaning                  |
|-------|--------------------------|
| 0     | Success                  |
| -1    | Generic error            |
| -2    | Output buffer too small  |
| -3    | Glyph execution failure  |
| Other | Reserved (do not use)    |

## Performance Considerations

### Polling Overhead

Guest polling in a tight loop wastes cycles. For long-running glyphs, use:

```asm
# Yield to host between polls
li t0, 0x8800_0001    # Different MMIO address: "check pending interrupts"
sw zero, 0(t0)        # Triggers host interrupt check

# Then poll
1:
  lw t1, 0(a0)
  andi t1, t1, 1
  bnez t1, 1b
```

### Batching

For multiple independent glyph calls, batch requests:

```asm
# Submit request 1
submit_glyph_request(1, input1, output1)

# Submit request 2
submit_glyph_request(2, input2, output2)

# Poll both
poll_both_completions()
```

## Extension Points

### Future: Asynchronous Completion (IRQs)

Instead of polling, host could raise an IRQ when glyph completes:

```asm
# Guest enables glyph IRQ
li t0, 0x8800_0002
sw t0, 0(t0)            # Enable glyph completion IRQ

# Wait for IRQ (no polling)
wait_for_irq()
```

### Future: Persistent Glyph Kernels

Long-running kernels (e.g., network packet processing) stay resident:

```asm
# Launch persistent kernel
li t0, 0x8800_0003
sw zero, 0(t0)          # "Launch persistent" trigger

# Kernel runs in background
# Submit work via different mechanism (e.g., queue)
```

## Compatibility

### RISC-V WGSL Interpreter

- Existing `RISCV_CPU_MMU.wgsl` unchanged
- Patched version adds MMIO handler for 0x8800_0000
- No changes to existing MMIO devices (UART, VirtIO, etc.)

### Glyph ISA

- Existing 27 opcodes unchanged
- SYSCALL opcode (0xFF) for completion notification
- LDP opcode for direct pixel reads (Patch-and-Copy)

## Testing

### Test 1: Basic Dispatch Loop

1. Guest writes request (glyph_id=TEST_COUNTER)
2. Guest triggers MMIO
3. Host detects, runs glyph (increments counter)
4. Host writes result
5. Guest reads result, verifies increment

### Test 2: Buffer Copy

1. Guest fills input buffer with pattern
2. Guest dispatches copy kernel
3. Guest verifies output buffer matches input

### Test 3: SHA-256 (Phase 2)

1. Guest dispatches SHA-256 on 10MB buffer
2. Verify: glyph result == Python hashlib.sha256()
3. Measure speedup vs interpreter

## Versioning

**ABI Version:** 1.0
**Last Updated:** 2026-08-30

### Version History

| Version | Date       | Changes                               |
|---------|------------|---------------------------------------|
| 1.0     | 2026-08-30 | Initial spec: request structure, MMIO trigger, polling |

## References

- `tools/RISCV_CPU_MMU.wgsl` — RISC-V WGSL interpreter
- `tools/glyph_isa_v2.py` — Glyph ISA implementation
- `glyph_dispatch/README.md` — Project overview