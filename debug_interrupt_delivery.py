#!/usr/bin/env python3
"""
Debug interrupt delivery: capture interrupt state at regular checkpoints.
"""
import sys
sys.path.insert(0, 'tools')
from spatial_rv64i_cpu import SpatialRV64ICore
import struct

print("=" * 70)
print("INTERRUPT DELIVERY DEBUGGING")
print("=" * 70)

core = SpatialRV64ICore(memory_size_bytes=64 * 1024 * 1024)

# Load boot image
with open('boot_images/alpine_riscv64.lnx.bin', 'rb') as f:
    alpine_data = f.read()

kernel_offset = struct.unpack('<I', alpine_data[4:8])[0]
kernel_size = struct.unpack('<I', alpine_data[8:12])[0]
kernel_pe = alpine_data[kernel_offset:kernel_offset + kernel_size]
core.load_program(kernel_pe, entry_point=0x80200000, ram_base=0x80000000)

# Set boot registers
core.write_register(10, 0)  # a0 = hart ID 0

print("\nCapturing interrupt state every 2M steps...")
print("steps |      PC | mode | MIE | SIE | mideleg | pending | delivered | mtimecmp | mtime")
print("-" * 95)

for steps in [2_000_000, 5_000_000, 10_000_000, 15_000_000, 20_000_000]:
    core.step(steps - (0 if steps == 2_000_000 else (steps - 2_000_000)))
    
    s = core.get_state()
    
    # Read CSR values directly from buffer
    csr_bytes = core.queue.read_buffer(core.csr_buffer)
    csr_arr = csr_bytes.tobytes()
    
    # Extract CSRs (each is 8 bytes: low + high)
    mstatus = int.from_bytes(csr_arr[0x100*8:0x100*8+8], 'little')
    mie = int.from_bytes(csr_arr[0x104*8:0x104*8+8], 'little')
    mideleg = int.from_bytes(csr_arr[0x303*8:0x303*8+8], 'little')
    mip = int.from_bytes(csr_arr[0x344*8:0x344*8+8], 'little')
    stimecmp = int.from_bytes(csr_arr[0x14D*8:0x14D*8+8], 'little')
    
    mstatus_mie = (mstatus >> 3) & 1
    mstatus_sie = (mstatus >> 1) & 1
    mideleg_stip = (mideleg >> 5) & 1
    mideleg_mtip = (mideleg >> 7) & 1
    mie_stie = (mie >> 5) & 1
    mie_mtie = (mie >> 7) & 1
    
    pending_stip = (mip >> 5) & 1
    pending_mtip = (mip >> 7) & 1
    
    print(f"{steps:6d} | 0x{s['pc']:08x} | {s['mode']} | {mstatus_mie} | {mstatus_sie} | 0x{mideleg:08x} | {s['timer_interrupts_fired']:8d} | {s['interrupts_delivered']:9d} | 0x{s['mtimecmp_low']:08x} | 0x{s['mtime_low']:08x}")
    print(f"        |          |      |     |     | MDELEG.STIP={mideleg_stip}, MTIP={mideleg_mtip} | MIE.STIE={mie_stie}, MTIE={mie_mtie}")
    print(f"        |          |      |     |     | pending STIP={pending_stip}, MTIP={pending_mtip} | STIMECMP=0x{stimecmp:08x}")
    print("-" * 95)

print("\nUART output:")
print("-" * 70)
uart = core.read_uart_output()[-500:]
print(uart.decode('latin-1', errors='replace'))
print("-" * 70)