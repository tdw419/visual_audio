#!/usr/bin/env python3
"""Boot xv6, inject ls, dump every iteration."""
import sys, struct, numpy as np
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / 'tools'))
from riscv_gpu_cpu import make_cpu_state, CPU_DTYPE
from boot_xv6_gpu import ELF64Loader, create_gpu_hardware, inject_command

elf_path = '/tmp/xv6-riscv/kernel/kernel'
elf = ELF64Loader(elf_path)

MEMORY_SIZE_MB = 128
MEMORY_SIZE = MEMORY_SIZE_MB * 1024 * 1024
PHYS_START = 0x80000000
pixel_count = MEMORY_SIZE // 4
memory = np.zeros((pixel_count, 4), dtype=np.uint32)

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

cpu_state = make_cpu_state(elf.entry_point, priv_mode=3)
max_instructions = 2000000
harness = create_gpu_hardware(memory, cpu_state, max_instructions)
device = harness['device']
queue = harness['queue']

cpu_layout = cpu_state.dtype
injected = False
last_out_len = 0

for iteration in range(120):
    encoder = device.create_command_encoder()
    pass_enc = encoder.begin_compute_pass()
    pass_enc.set_pipeline(harness['pipeline'])
    pass_enc.set_bind_group(0, harness['bind_group'])
    pass_enc.dispatch_workgroups(1)
    pass_enc.end()
    queue.submit([encoder.finish()])

    # Read output buffer
    output_bytes = queue.read_buffer(harness['output_buffer'])
    out_str = ''
    for i in range(0, 65536, 4):
        word = struct.unpack_from('<I', output_bytes[i:i+4])[0]
        for b in word.to_bytes(4, 'little'):
            if b == 0:
                break
            if 32 <= b < 127 or b in (ord('\n'), ord('\r'), ord('\t')):
                out_str += chr(b)

    # Read CPU state
    cpu_bytes = queue.read_buffer(harness['cpu_buffer'])
    cpu_readback = np.frombuffer(cpu_bytes, dtype=cpu_layout)
    pc = (cpu_readback['pc'][0][1] << 32) | cpu_readback['pc'][0][0]
    timer_irq = int(cpu_readback['timer_interrupt_count'][0])
    total_irq = int(cpu_readback['total_interrupt_count'][0])
    instr_count = int(cpu_readback['instr_count'][0])

    # Print on any output change
    if len(out_str) != last_out_len:
        last_out_len = len(out_str)
        # Show last 200 chars of output
        tail = out_str[-200:] if len(out_str) > 200 else out_str
        tail = tail.replace('\n', '\\n')
        print(f"I{iteration:2d} PC=0x{pc:016x} timer={timer_irq} irqs={total_irq} out[{len(out_str)}]='{tail}'")

    # Inject on prompt
    if '$ ' in out_str and not injected:
        print(f"\n>>> Prompt! Injecting 'ls'")
        inject_command(queue, harness, cpu_layout, 'ls')
        injected = True
        print(">>> Injected\n")
        
    # Stop a few iterations after injection
    if injected and iteration > 40:
        break

# Final dump
output_bytes = queue.read_buffer(harness['output_buffer'])
full_out = ''
for i in range(0, 65536, 4):
    word = struct.unpack_from('<I', output_bytes[i:i+4])[0]
    for b in word.to_bytes(4, 'little'):
        if b == 0:
            break
        if 32 <= b < 127 or b in (ord('\n'), ord('\r'), ord('\t')):
            full_out += chr(b)

print(f"\n\n{'='*60}")
print(f"FINAL OUTPUT ({len(full_out)} chars)")
print(full_out)
