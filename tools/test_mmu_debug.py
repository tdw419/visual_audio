import wgpu
import numpy as np

def main():
    device = wgpu.utils.get_default_device()

    with open('RISCV_CPU_MMU.wgsl', 'r') as f:
        shader_code = f.read()

    # Modify the WGSL to output debug info into output buffer
    shader_code = shader_code.replace(
        'return vec2<u32>(0xFFFFFFFF, 0xFFFFFFFF);',
        '{ output[0] = 0xDEADC0DE; return vec2<u32>(0xFFFFFFFF, 0xFFFFFFFF); }'
    )
    shader_code = shader_code.replace(
        'let l1_pte = read_phys_word(l1_pte_pa);',
        'let l1_pte = read_phys_word(l1_pte_pa); output[1] = l1_pte_pa.x; output[2] = l1_pte;'
    )
    shader_code = shader_code.replace(
        'let l2_pte = read_phys_word(l2_pte_pa);',
        'let l2_pte = read_phys_word(l2_pte_pa); output[3] = l2_pte_pa.x; output[4] = l2_pte;'
    )
    shader_code = shader_code.replace(
        'let l3_pte = read_phys_word(l3_pte_pa);',
        'let l3_pte = read_phys_word(l3_pte_pa); output[5] = l3_pte_pa.x; output[6] = l3_pte;'
    )

    mem_size = 16 * 1024 * 1024 // 4
    memory = np.zeros(mem_size, dtype=np.uint32)

    ROOT_PT_PPN = 1
    L2_PT_PPN = 2
    L3_PT_PPN = 3
    TARGET_PPN = 4

    ROOT_PT_ADDR = ROOT_PT_PPN * 4096
    L2_PT_ADDR = L2_PT_PPN * 4096
    L3_PT_ADDR = L3_PT_PPN * 4096
    TARGET_ADDR = TARGET_PPN * 4096

    PTE_V = 1
    PTE_R = 2
    PTE_W = 4
    PTE_X = 8

    memory[ROOT_PT_ADDR//4 + 1] = (L2_PT_PPN << 10) | PTE_V
    memory[L2_PT_ADDR//4 + 0] = (L3_PT_PPN << 10) | PTE_V
    memory[L3_PT_ADDR//4 + 0] = (TARGET_PPN << 10) | PTE_V | PTE_R | PTE_W | PTE_X
    memory[TARGET_ADDR//4 + 0] = 0x00100537

    from riscv_gpu_cpu import make_cpu_state, make_satp
    cpu_state = make_cpu_state(0x40000000, satp=make_satp(ROOT_PT_PPN))

    output_buf = np.zeros(1024, dtype=np.uint32)
    max_inst = np.array([10], dtype=np.uint32)

    buf_mem = device.create_buffer_with_data(data=memory.tobytes(), usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_SRC)
    buf_cpu = device.create_buffer_with_data(data=cpu_state, usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_SRC | wgpu.BufferUsage.COPY_DST)
    buf_out = device.create_buffer_with_data(data=output_buf, usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_SRC)
    buf_uni = device.create_buffer_with_data(data=max_inst, usage=wgpu.BufferUsage.UNIFORM)

    cshader = device.create_shader_module(code=shader_code)
    pipeline = device.create_compute_pipeline(
        layout="auto",
        compute={"module": cshader, "entry_point": "main"}
    )
    bind_group = device.create_bind_group(
        layout=pipeline.get_bind_group_layout(0),
        entries=[
            {"binding": 0, "resource": {"buffer": buf_mem, "offset": 0, "size": buf_mem.size}},
            {"binding": 1, "resource": {"buffer": buf_cpu, "offset": 0, "size": buf_cpu.size}},
            {"binding": 2, "resource": {"buffer": buf_out, "offset": 0, "size": buf_out.size}},
            {"binding": 3, "resource": {"buffer": buf_uni, "offset": 0, "size": buf_uni.size}},
        ]
    )

    encoder = device.create_command_encoder()
    compute_pass = encoder.begin_compute_pass()
    compute_pass.set_pipeline(pipeline)
    compute_pass.set_bind_group(0, bind_group, [], 0, 999999)
    compute_pass.dispatch_workgroups(1)
    compute_pass.end()
    device.queue.submit([encoder.finish()])

    out_readback = np.frombuffer(device.queue.read_buffer(buf_out), dtype=np.uint32)
    print(f"Error Code: 0x{out_readback[0]:08x}")
    print(f"L1 PA: {out_readback[1]}, PTE: {out_readback[2]}")
    print(f"L2 PA: {out_readback[3]}, PTE: {out_readback[4]}")
    print(f"L3 PA: {out_readback[5]}, PTE: {out_readback[6]}")

if __name__ == '__main__':
    main()
