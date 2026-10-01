# UART RX Implementation for SpatialRV32ICore

## Overview
Implemented UART RX (input) path for the GPU-native RV32IMA emulator, enabling full-duplex communication between host and guest OS.

## Changes Made

### WGSL Shader (SPATIAL_RV32I.wgsl)
1. **Extended CPUState struct** - Added two fields:
   - `uart_rx_data_pending`: flag indicating RX data available (0/1)
   - `uart_rx_byte`: the received byte value

2. **Updated mmio_read() function**:
   - UART_BASE (0x10000000) now returns `uart_rx_byte` when data is pending, and clears `uart_rx_data_pending` on read
   - UART_LSR_ADDR (0x10000005) now sets DR (Data Ready) bit when `uart_rx_data_pending` is 1

3. **Updated CPUState size**:
   - State buffer: 44 bytes → 52 bytes (+8 bytes for two u32 fields)

### Python Wrapper (spatial_rv32i_cpu.py)
1. **State buffer allocation**: 52 bytes instead of 44
2. **get_state()**: Returns two new fields (uart_rx_data_pending, uart_rx_byte)
3. **write_uart_input(data: bytes)**: New method to feed bytes into UART RX
   - Loops over bytes, writing uart_rx_data_pending=1 and uart_rx_byte=byte to GPU state
4. **load_program()**: Initializes new RX fields to 0 on reset

## Verification

### Unit Tests
- **test_uart_rx.py**: Guest reads UART via LB, waits for LSR DR bit, consumes byte
- **test_lsr_dr.py**: Verifies LSR DR bit is set/cleared correctly

### Integration Test
- **demo_uart_rx_linux.py**: Boots Linux 6.1.14 RV32IMA-NOMMU, waits for login prompt, feeds character 'r', kernel echoes back
- Confirms full-duplex UART: TX (kernel → host) and RX (host → kernel) both functional

## Design Notes

### Non-Blocking Single-Byte Buffer
- UART RX uses a simple non-blocking design: single byte buffer
- When host writes byte via `write_uart_input()`, sets `uart_rx_data_pending=1`
- Guest reads UART_BASE to consume byte (clears pending flag)
- Guest polls LSR DR bit to check if data available (standard 16550 behavior)

### Consume-on-Read
- Reading UART_BASE automatically clears `uart_rx_data_pending`
- This matches real 16550 behavior where RBR read clears DR flag
- Ensures guest can't re-read same byte accidentally

### LSR DR Bit Behavior
- LSR = 0x61 (THRE|TEMT|DR) when data pending
- LSR = 0x60 (THRE|TEMT) when no data pending
- Matches 16550 driver expectations; kernel polls LSR before reading

## Usage Example

```python
from spatial_rv32i_cpu import SpatialRV32ICore

core = SpatialRV32ICore(memory_size_bytes=1024)
core.load_program(binary, entry_point=0x80000000, ram_base=0x80000000)

# Feed input to guest
core.write_uart_input(b"Hello\n")

# Run guest
core.step(steps=100000)

# Read guest output
print(core.read_uart_output().decode())
```

## Limitations
- Single-byte buffer: host must pace input or risk overwriting before guest consumes
- No interrupts: guest must poll LSR (standard for earlycon / boot console)
- Non-blocking: if guest reads when no data, returns 0

## Files Modified
- `tools/SPATIAL_RV32I.wgsl` - WGSL shader with RX support
- `tools/spatial_rv32i_cpu.py` - Python wrapper with write_uart_input()

## Files Added
- `tools/test_uart_rx.py` - Unit test for RX path
- `tools/test_lsr_dr.py` - LSR DR bit verification
- `tools/demo_uart_rx_linux.py` - Integration test with Linux

## Backward Compatibility
- All existing tests pass unchanged
- State buffer size change is transparent to existing code
- Default init (pending=0, byte=0) preserves old behavior (no input)