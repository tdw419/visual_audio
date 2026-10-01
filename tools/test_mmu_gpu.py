import wgpu
import numpy as np
import sys

def main():
    print("============================================================")
    print("RISC-V GPU MMU Test Harness (SV39)")
    print("============================================================")

    device = wgpu.utils.get_default_device()

    with open('RISCV_CPU_MMU.wgsl', 'r') as f:
        shader_code = f.read()

    # Create memory buffer (16MB)
    mem_size = 16 * 1024 * 1024 // 4 # words
    memory = np.zeros((mem_size, 4), dtype=np.uint32)

    # Physical Page Addresses
    ROOT_PT_PPN = 1
    L2_PT_PPN = 2
    L3_PT_PPN = 3
    TARGET_PPN = 4

    ROOT_PT_ADDR = ROOT_PT_PPN * 4096
    L2_PT_ADDR = L2_PT_PPN * 4096
    L3_PT_ADDR = L3_PT_PPN * 4096
    TARGET_ADDR = TARGET_PPN * 4096

    # We want to map Virtual Address 0x4000_0000 -> Physical Address 0x0000_4000
    # 0x4000_0000 -> VPN2=1, VPN1=0, VPN0=0
    # Root PT (PPN 1) -> entry 1 points to L2 PT (PPN 2)
    # L2 PT (PPN 2) -> entry 0 points to L3 PT (PPN 3)
    # L3 PT (PPN 3) -> entry 0 points to TARGET (PPN 4)
    # Real SV39 PTEs are 8 bytes (64-bit) each - PPN in bits [53:10], flags
    # in [7:0]. A prior version of this test used a 4-byte "simplified" PTE
    # stride that only matched an equally wrong shader implementation, not
    # real hardware or real kernel-built page tables (see xv6 boot work).

    PTE_V = 1
    PTE_R = 2
    PTE_W = 4
    PTE_X = 8

    def write_pte(byte_addr, ppn, flags):
        val = (ppn << 10) | flags
        word_idx = byte_addr // 4
        memory[word_idx] = [val & 0xFF, (val >> 8) & 0xFF, (val >> 16) & 0xFF, (val >> 24) & 0xFF]
        memory[word_idx + 1] = [0, 0, 0, 0]  # high 32 bits of the PTE

    # entry i within a page lives at byte offset i*8 (8-byte PTE stride)
    write_pte(ROOT_PT_ADDR + 1 * 8, L2_PT_PPN, PTE_V)                    # L1 entry (VPN2=1)
    write_pte(L2_PT_ADDR + 0 * 8, L3_PT_PPN, PTE_V)                      # L2 entry (VPN1=0)
    write_pte(L3_PT_ADDR + 0 * 8, TARGET_PPN, PTE_V | PTE_R | PTE_W | PTE_X)  # L3 leaf (VPN0=0)

    # Target Program (LUI a0, 0x00100; ADDI a0, a0, 0x100; ECALL for exit)
    # NOTE: previous encoding 0x01100513 was ADDI a0, x0, 17 (rs1=zero!),
    # which clobbered LUI's result - the test could never pass.
    program = [
        0x00100537,
        0x10050513,
        0x00000073
    ]
    for i, inst in enumerate(program):
        memory[TARGET_ADDR//4 + i] = [inst & 0xFF, (inst >> 8) & 0xFF, (inst >> 16) & 0xFF, (inst >> 24) & 0xFF]

    # Convert memory array to RGBA pixels (each u32 is 1 pixel)
    mem_bytes = memory.tobytes()

    # Start at virtual address 0x40000000 with SV39 enabled
    from riscv_gpu_cpu import CPU_DTYPE as cpu_layout, make_cpu_state, make_satp
    cpu_state = make_cpu_state(0x40000000, satp=make_satp(ROOT_PT_PPN))

    output_buf = np.zeros(1024, dtype=np.uint32)
    max_inst = np.array([100], dtype=np.uint32)

    input_words = np.zeros(256, dtype=np.uint32)

    buf_mem = device.create_buffer_with_data(data=mem_bytes, usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_SRC)
    buf_cpu = device.create_buffer_with_data(data=cpu_state, usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_SRC | wgpu.BufferUsage.COPY_DST)
    buf_out = device.create_buffer_with_data(data=output_buf, usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_SRC)
    buf_uni = device.create_buffer_with_data(data=max_inst, usage=wgpu.BufferUsage.UNIFORM)
    buf_input = device.create_buffer_with_data(data=input_words, usage=wgpu.BufferUsage.STORAGE)

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
            {"binding": 4, "resource": {"buffer": buf_input, "offset": 0, "size": buf_input.size}},
        ]
    )

    print("Running GPU Compute...")
    for step in range(5):
        encoder = device.create_command_encoder()
        compute_pass = encoder.begin_compute_pass()
        compute_pass.set_pipeline(pipeline)
        compute_pass.set_bind_group(0, bind_group, [], 0, 999999)
        compute_pass.dispatch_workgroups(1)
        compute_pass.end()
        queue = device.queue
        queue.submit([encoder.finish()])

        cpu_readback = np.frombuffer(device.queue.read_buffer(buf_cpu), dtype=cpu_layout)
        
        print(f"  Step {step}: PC=0x{cpu_readback[0]['pc'][0]:08x}, running={cpu_readback[0]['running']}, instr_count={cpu_readback[0]['instr_count']}")
        if cpu_readback[0]['running'] == 0:
            print("CPU Halted.")
            break

    print(f"Final a0: 0x{cpu_readback[0]['regs'][10][0]:08x}")
    if cpu_readback[0]['regs'][10][0] == 0x00100100:
        print("[PASS] MMU Translation Successful!")
    else:
        print("[FAIL] MMU Translation Failed.")

if __name__ == '__main__':
    main()
