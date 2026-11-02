#!/usr/bin/env python3
"""Quick xv6 boot test that dumps full UART output and CPU state."""
import sys, struct, numpy as np
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / 'tools'))
from riscv_gpu_cpu import make_cpu_state, CPU_DTYPE
from boot_xv6_gpu import ELF64Loader, create_gpu_hardware

elf_path = '/tmp/xv6-riscv/kernel/kernel'

# Load ELF
elf = ELF64Loader(elf_path)

# Setup memory
MEMORY_SIZE_MB = 128
MEMORY_SIZE = MEMORY_SIZE_MB * 1024 * 1024
PHYS_START = 0x80000000
pixel_count = MEMORY_SIZE // 4
memory = np.zeros((pixel_count, 4), dtype=np.uint32)

# Load kernel segments
for seg in elf.get_loadable_segments():
    offset = seg['p_vaddr'] - PHYS_START
    if offset < 0 or offset + seg['p_memsz'] > MEMORY_SIZE:
        continue
    data = elf.get_segment_data(seg)
    start_pixel = offset // 4
    start_byte = offset % 4
    if start_byte == 0:
        word_count = (len(data) + 3) // 4
        byte_data = np.frombuffer(data, dtype=np.uint8)
        padded_len = word_count * 4
        if len(byte_data) < padded_len:
            padded = np.zeros(padded_len, dtype=np.uint8)
            padded[:len(byte_data)] = byte_data
            byte_data = padded
        pixel_data = byte_data.reshape(-1, 4)
        memory[start_pixel:start_pixel + word_count] = pixel_data
    else:
        for i, byte in enumerate(data):
            pixel_idx = (offset + i) // 4
            byte_idx = (offset + i) % 4
            memory[pixel_idx, byte_idx] = byte

# Load fs.img
fs_img_path = Path('/tmp/xv6-riscv/fs.img')
if fs_img_path.exists():
    fs_data = fs_img_path.read_bytes()
    fs_offset = 0x81000000 - PHYS_START
    start_pixel = fs_offset // 4
    start_byte = fs_offset % 4
    if start_byte == 0:
        word_count = (len(fs_data) + 3) // 4
        byte_data = np.frombuffer(fs_data, dtype=np.uint8)
        padded_len = word_count * 4
        if len(byte_data) < padded_len:
            padded = np.zeros(padded_len, dtype=np.uint8)
            padded[:len(byte_data)] = byte_data
            byte_data = padded
        pixel_data = byte_data.reshape(-1, 4)
        memory[start_pixel:start_pixel + word_count] = pixel_data
    print(f"Loaded fs.img: {len(fs_data)} bytes at 0x81000000")

# Setup CPU state
cpu_state = make_cpu_state(elf.entry_point, priv_mode=3)
max_instructions = 2000000
harness = create_gpu_hardware(memory, cpu_state, max_instructions)
device = harness['device']
queue = harness['queue']

# Boot loop
cpu_layout = cpu_state.dtype
last_pc = 0
stall_count = 0

for iteration in range(100):
    encoder = device.create_command_encoder()
    pass_enc = encoder.begin_compute_pass()
    pass_enc.set_pipeline(harness['pipeline'])
    pass_enc.set_bind_group(0, harness['bind_group'])
    pass_enc.dispatch_workgroups(1)
    pass_enc.end()
    queue.submit([encoder.finish()])

    # Read CPU state
    cpu_bytes = queue.read_buffer(harness['cpu_buffer'])
    cpu_readback = np.frombuffer(cpu_bytes, dtype=cpu_layout)
    pc = (cpu_readback['pc'][0][1] << 32) | cpu_readback['pc'][0][0]
    running = int(cpu_readback['running'][0])
    instr_count = int(cpu_readback['instr_count'][0])
    timer_irq = int(cpu_readback['timer_interrupt_count'][0])
    total_irq = int(cpu_readback['total_interrupt_count'][0])
    mstatus_val = int((cpu_readback[0]['mstatus'][1] << 32) | cpu_readback[0]['mstatus'][0])
    mie_val = int((cpu_readback[0]['mie'][1] << 32) | cpu_readback[0]['mie'][0])
    mip_val = int((cpu_readback[0]['mip'][1] << 32) | cpu_readback[0]['mip'][0])
    mideleg_val = int((cpu_readback[0]['mideleg'][1] << 32) | cpu_readback[0]['mideleg'][0])
    medeleg_val = int((cpu_readback[0]['medeleg'][1] << 32) | cpu_readback[0]['medeleg'][0])
    satp_val = int((cpu_readback[0]['satp'][1] << 32) | cpu_readback[0]['satp'][0])
    priv_mode = int(cpu_readback[0]['priv_mode'])
    plic_pending = int(cpu_readback[0]['plic_pending'])
    plic_enable = int(cpu_readback[0]['plic_enable'])
    mtime_low = int(cpu_readback[0]['mtime_low'])
    mtime_high = int(cpu_readback[0]['mtime_high'])
    mtimecmp_low = int(cpu_readback[0]['mtimecmp_low'])
    mtimecmp_high = int(cpu_readback[0]['mtimecmp_high'])
    timer_fired = int(cpu_readback[0]['timer_fired'])

    priv_names = {0: 'U', 1: 'S', 3: 'M'}
    mtime = (mtime_high << 32) | mtime_low
    mtimecmp = (mtimecmp_high << 32) | mtimecmp_low

    print(f"I{iteration:3d} PC=0x{pc:016x} {priv_names.get(priv_mode,'?')} "
          f"instr={instr_count:>8d} timer={timer_irq} irqs={total_irq} "
          f"satp=0x{satp_val:016x} mtime={mtime:>12d} cmp={mtimecmp:>12d} "
          f"fired={timer_fired} mstatus=0x{mstatus_val:08x} mie=0x{mie_val:08x} "
          f"mip=0x{mip_val:08x} mideleg=0x{mideleg_val:08x} "
          f"plic={plic_pending:02x}/{plic_enable:02x}")

    if pc == last_pc:
        stall_count += 1
        if stall_count >= 8:
            break
    else:
        stall_count = 0
    last_pc = pc

# Read full UART buffer
output_bytes = queue.read_buffer(harness['output_buffer'])
full_out = ''
for i in range(0, 65536, 4):
    word = struct.unpack_from('<I', output_bytes[i:i+4])[0]
    for b in word.to_bytes(4, 'little'):
        if b == 0:
            break
        if 32 <= b < 127 or b in (ord('\n'), ord('\r'), ord('\t'), ord('\x1b')):
            full_out += chr(b)
        elif b == 8:  # backspace
            full_out = full_out[:-1] if full_out else full_out
        else:
            full_out += f'[{b:02x}]'

print(f"\n=== FULL UART OUTPUT ({len(full_out)} chars) ===")
print(full_out if full_out else "(none)")
