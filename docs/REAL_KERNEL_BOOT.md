# Real Kernel Boot Infrastructure

This directory contains diagnostic scripts for booting real compiled RISC-V kernels on the GPU emulator.

## Level 5c: Non-Identity SV39 Mapping

**File**: `tests/bare_metal/level5c/level5c.elf`

**What it tests**:
- M-mode → S-mode privilege transition via `mret`
- Three-level Sv39 page table walk with non-identity mappings
- Code remap: VA 0xC0000000 → PA 0x80000000
- UART remap: VA 0x50000000 → PA 0x10000000
- Instruction fetch through translated address (proof of real MMU)

**Expected UART output**:
1. "Level 5c: Non-Identity SV39 Mapping"
2. "Page table built (4 root entries, 2 shared leaves)."
3. "supervisor_main reached via non-identity VA fetch: OK"
4. "UART write via non-identity VA (0x50000000->0x10000000): OK"
5. "Level 5c Complete."

## ELF Loading Pattern

```python
import struct
from tools.spatial_rv64i_cpu import SpatialRV64ICore

# Parse ELF64 header
with open(ELF_PATH, 'rb') as f:
    elf_data = f.read()

e_entry = struct.unpack('<Q', elf_data[24:32])[0]
e_phoff = struct.unpack('<Q', elf_data[32:40])[0]
e_phentsize = struct.unpack('<H', elf_data[54:56])[0]
e_phnum = struct.unpack('<H', elf_data[56:58])[0]

core = SpatialRV64ICore(RAM_SIZE)

# Load each LOAD segment
for i in range(e_phnum):
    ph_offset = e_phoff + i * e_phentsize
    p_type = struct.unpack('<I', elf_data[ph_offset:ph_offset+4])[0]

    if p_type == 1:  # PT_LOAD
        p_offset = struct.unpack('<Q', elf_data[ph_offset+8:ph_offset+16])[0]
        p_paddr = struct.unpack('<Q', elf_data[ph_offset+24:ph_offset+32])[0]
        p_filesz = struct.unpack('<Q', elf_data[ph_offset+32:ph_offset+40])[0]
        p_memsz = struct.unpack('<Q', elf_data[ph_offset+40:ph_offset+48])[0]

        buf_offset = p_paddr - RAM_BASE
        segment_data = elf_data[p_offset:p_offset + p_filesz]

        # Zero-pad to memsz (BSS regions)
        if len(segment_data) < p_memsz:
            segment_data += b'\x00' * (p_memsz - len(segment_data))

        core.write_mem_bytes(buf_offset, segment_data)

# Set CPU state
import numpy as np
state_data = np.array(
    [e_entry & 0xFFFFFFFF, e_entry >> 32, 0, 1, 3, 0, 0, 0, 0, 0, 0, 0, 0, 0,
     RAM_BASE, 0, 0, 0, 0, 0, 0, 0, 0], dtype=np.uint32
).tobytes()
core.queue.write_buffer(core.state_buffer, 0, state_data)

# Execute
core.step(steps=50_000)
output = core.read_uart_output()
```

## Performance Notes

- `get_state()` is expensive (~1s GPU sync) due to state buffer readback
- `step()` is fast (~90K steps/sec for Level 5c) - GPU kernel execution
- `read_uart_output()` is fast - only reads UART buffer, not full state
- Avoid `get_state()` inside tight loops for integration tests

## Test Status

- ✓ OpenSBI boot (test_opensbi_boot.py, ~145s)
- ✓ Level 5c non-identity SV39 (tests/bare_metal/level5c/)
- ✗ Alpine Linux boot (test_alpine_opensbi_boot.py - times out, needs DTB/firmware work)