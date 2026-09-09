#!/usr/bin/env python3
import sys, struct
from pathlib import Path
sys.path.insert(0, 'tools')
sys.path.insert(0, 'src')
from spatial_rv64i_cpu import SpatialRV64ICore
from create_dtb import build_device_tree

RAM_SIZE = 64 * 1024 * 1024
RAM_BASE = 0x80000000
KERNEL_OFFSET = 0x200000

core = SpatialRV64ICore(RAM_SIZE)
opensbi_data = Path('/usr/lib/riscv64-linux-gnu/opensbi/generic/fw_jump.bin').read_bytes()
alpine_data = Path('boot_images/alpine_riscv64.lnx.bin').read_bytes()

kernel_offset = struct.unpack('<I', alpine_data[4:8])[0]
kernel_size = struct.unpack('<I', alpine_data[8:12])[0]
initrd_size = struct.unpack('<I', alpine_data[12:16])[0]
kernel_pe = alpine_data[kernel_offset:kernel_offset + kernel_size]
initrd_data = alpine_data[kernel_offset + kernel_size:kernel_offset + kernel_size + initrd_size]

e_lfanew = struct.unpack('<I', kernel_pe[0x3C:0x40])[0]
if kernel_pe[e_lfanew:e_lfanew+4] == b'PE\x00\x00':
    opt = e_lfanew + 24
    if struct.unpack('<H', kernel_pe[opt:opt+2])[0] == 0x20b:
        kernel_mem_size = struct.unpack('<I', kernel_pe[opt+56:opt+60])[0]
    else:
        kernel_mem_size = struct.unpack('<I', kernel_pe[opt+56:opt+60])[0]
else:
    kernel_mem_size = kernel_size

kernel_load_addr = RAM_BASE + KERNEL_OFFSET
initrd_load_addr = max(kernel_load_addr + ((kernel_mem_size + 4095) & ~4095),
                       RAM_BASE + 0x2800000)
dtb = build_device_tree(
    ram_base=RAM_SIZE, ram_size=RAM_SIZE, uart_base=0x10000000,
    isa='rv64imafdc', timebase=10_000_000,
    bootargs='earlycon=uart8250,mmio,0x10000000 console=ttyS0 cma=0',
    kernel_addr=kernel_load_addr, initrd_addr=initrd_load_addr, initrd_size=initrd_size,
)

core.load_program(opensbi_data, entry_point=RAM_BASE, ram_base=RAM_BASE)
core.write_mem_bytes(KERNEL_OFFSET, kernel_pe)
initrd_offset = initrd_load_addr - RAM_BASE
core.write_mem_bytes(initrd_offset, initrd_data)
dtb_addr = (RAM_BASE + RAM_SIZE - len(dtb)) & ~0x7
dtb_offset = dtb_addr - RAM_BASE
core.write_mem_bytes(dtb_offset, dtb)

core.write_register(10, 0)
core.write_register(11, dtb_addr)

# Track trap entry/exit
print("Monitoring trap state...")
print("steps |      PC | mode | SEPC | SCAUSE | SIE | timer_fired | delivered")
print("-" * 90)

last_sepc = None
last_scause = None
stuck_count = 0

for i in range(1, 31):
    steps = i * 1_000_000
    core.step(1_000_000)
    s = core.get_state()
    csr_bytes = core.queue.read_buffer(core.csr_buffer)
    csr_arr = csr_bytes.tobytes()
    
    mstatus = int.from_bytes(csr_arr[0x100*8:0x100*8+8], 'little')
    sepc = int.from_bytes(csr_arr[0x141*8:0x141*8+8], 'little')
    scause = int.from_bytes(csr_arr[0x142*8:0x142*8+8], 'little')
    sie_val = (mstatus >> 1) & 1
    
    print(f"{steps:6d} | 0x{s['pc']:08x} | {s['mode']:3d} | 0x{sepc:08x} | 0x{scause:08x} | {sie_val} | {s['timer_interrupts_fired']:10d} | {s['interrupts_delivered']:9d}")
    
    # Check if stuck in same fault
    if sepc == last_sepc and scause == last_scause and scause != 0:
        stuck_count += 1
        if stuck_count > 5:
            print("\n*** STUCK IN TRAP LOOP ***")
            print(f"Repeated fault at SEPC=0x{sepc:016x}, SCAUSE=0x{scause:08x}")
            break
    else:
        stuck_count = 0
        last_sepc = sepc
        last_scause = scause

print(f"\nFinal state: timer_fired={s['timer_interrupts_fired']}, delivered={s['interrupts_delivered']}")