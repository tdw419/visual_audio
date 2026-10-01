#!/usr/bin/env python3
import wgpu
import wgpu.utils
import numpy as np
from pathlib import Path

pixels = np.load('test_kernel_no_mmu_v3.npy')
entry = 0x2000

device = wgpu.utils.get_default_device()
shader = (Path(__file__).parent / 'RISCV_CPU_MMU.wgsl').read_text()

pixel_data = pixels.reshape(-1, 4).astype(np.uint32)
memory = device.create_buffer(size=pixel_data.nbytes,
    usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_DST)
device.queue.write_buffer(memory, 0, pixel_data.tobytes())

from riscv_gpu_cpu import make_cpu_state
cpu = make_cpu_state(entry)  # M-mode, MMU off

cpu_buf = device.create_buffer(size=cpu.nbytes,
    usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_DST | wgpu.BufferUsage.COPY_SRC)
device.queue.write_buffer(cpu_buf, 0, cpu.tobytes())

out_buf = device.create_buffer(size=65536,
    usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_SRC)

max_inst = np.array([1000], dtype=np.uint32)
uni_buf = device.create_buffer(size=max_inst.nbytes,
    usage=wgpu.BufferUsage.UNIFORM | wgpu.BufferUsage.COPY_DST)
device.queue.write_buffer(uni_buf, 0, max_inst.tobytes())

bind = device.create_bind_group_layout(entries=[
    {'binding':0, 'visibility': wgpu.ShaderStage.COMPUTE, 'buffer':{'type':'storage'}},
    {'binding':1, 'visibility': wgpu.ShaderStage.COMPUTE, 'buffer':{'type':'storage'}},
    {'binding':2, 'visibility': wgpu.ShaderStage.COMPUTE, 'buffer':{'type':'storage'}},
    {'binding':3, 'visibility': wgpu.ShaderStage.COMPUTE, 'buffer':{'type':'uniform'}},
])
bg = device.create_bind_group(layout=bind, entries=[
    {'binding':0, 'resource':{'buffer':memory, 'offset':0, 'size':pixel_data.nbytes}},
    {'binding':1, 'resource':{'buffer':cpu_buf, 'offset':0, 'size':cpu.nbytes}},
    {'binding':2, 'resource':{'buffer':out_buf, 'offset':0, 'size':65536}},
    {'binding':3, 'resource':{'buffer':uni_buf, 'offset':0, 'size':max_inst.nbytes}},
])

shader_mod = device.create_shader_module(code=shader)
layout = device.create_pipeline_layout(bind_group_layouts=[bind])
pipeline = device.create_compute_pipeline(layout=layout,
    compute={'module':shader_mod, 'entry_point':'main'})

# Execute
enc = device.create_command_encoder()
pass_enc = enc.begin_compute_pass()
pass_enc.set_pipeline(pipeline)
pass_enc.set_bind_group(0, bg)
pass_enc.dispatch_workgroups(1)
pass_enc.end()
device.queue.submit([enc.finish()])

# Read back
cpu_read = np.frombuffer(device.queue.read_buffer(cpu_buf), dtype=cpu.dtype)[0]
out = np.frombuffer(device.queue.read_buffer(out_buf), dtype=np.uint8)

print(f'Instructions executed: {cpu_read["instr_count"]}')
print(f'Output pointer: {cpu_read["output_ptr"]}')
print(f'Raw bytes: {out[:16].tolist()}')
print(f'ASCII: {"".join(chr(b) if 32 <= b < 127 else "." for b in out[:cpu_read["output_ptr"]])}')