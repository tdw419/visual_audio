import sys
import re

with open("tools/boot_xv6_gpu.py", "r") as f:
    content = f.read()

# We need to insert the UEFI tables and trampolines right after the kernel is loaded, before GPU pipeline is created.
# Let's find: `print(f"    Memory buffer: {pixel_count} words ({MEMORY_SIZE_MB // 2}MB)")`
# Actually, the original code had:
injection = """
    print("\\n  Injecting Minimal EFI System Table...")
    efi_base = PHYS_START + 0x02001000
    efi_offset = 0x02001000
    mem_view = memory.view(np.uint8).reshape(-1)

    sys_table = struct.pack('<8sIIIIQQQQQQQQ',
        b'IBI SYST', 0x00020000, 120, 0, 0, # Header: Sig, Rev, Size, CRC32, Reserved
        0, # FirmwareVendor
        0, # FirmwareRevision
        0, # ConsoleInHandle
        0, # ConIn
        0, # ConsoleOutHandle
        efi_base + 0x500, # ConOut (needs to point to a valid SimpleTextOutputProtocol)
        0, # ConsoleErrorHandle
        0  # StdErr
    )
    sys_table += struct.pack('<QQQQ',
        efi_base + 0x200, # RuntimeServices
        efi_base + 0x100, # BootServices
        0, # NumberOfTableEntries
        0  # ConfigurationTable
    )

    bs_table = struct.pack('<8sIII', b'BOOTSERV', 0x00020000, 400, 0).ljust(400, b'\\0')
    rs_table = struct.pack('<8sIII', b'RUN SERV', 0x00020000, 104, 0).ljust(104, b'\\0')

    # Write tables to memory
    sys_offset = efi_base - PHYS_START
    for i, b in enumerate(sys_table):
        mem_view[sys_offset + i] = b
    for i, b in enumerate(bs_table):
        mem_view[sys_offset + 0x100 + i] = b
    for i, b in enumerate(rs_table):
        mem_view[sys_offset + 0x200 + i] = b

    def patch_ptr(table_offset, offset, val):
        ptr_bytes = struct.pack('<Q', val)
        for i, b in enumerate(ptr_bytes):
            mem_view[table_offset + offset + i] = b

    SBI_EXT_UEFI = 0x55454649
    UEFI_ALLOCATE_POOL = 1

    def r(name):
        return {'zero': 0, 'ra': 1, 'a0': 10, 'a1': 11, 'a2': 12,
                 'a3': 13, 'a6': 16, 'a7': 17, 't0': 5}[name]

    def i_type(opcode, rd, funct3, rs1, imm):
        return ((imm & 0xFFF) << 20) | (r(rs1) << 15) | (funct3 << 12) | (r(rd) << 7) | opcode

    def r_type(opcode, rd, funct3, rs1, rs2, funct7=0):
        return (funct7 << 25) | (r(rs2) << 20) | (r(rs1) << 15) | (funct3 << 12) | (r(rd) << 7) | opcode

    def s_type(opcode, funct3, rs1, rs2, imm):
        return (((imm >> 5) & 0x7F) << 25) | (r(rs2) << 20) | (r(rs1) << 15) | (funct3 << 12) | ((imm & 0x1F) << 7) | opcode

    def b_type(opcode, funct3, rs1, rs2, imm):
        imm12 = (imm >> 12) & 1
        imm11 = (imm >> 11) & 1
        imm10_5 = (imm >> 5) & 0x3F
        imm4_1 = (imm >> 1) & 0xF
        return (imm12 << 31) | (imm10_5 << 25) | (r(rs2) << 20) | (r(rs1) << 15) | (funct3 << 12) | (imm4_1 << 8) | (imm11 << 7) | opcode

    def addi(rd, rs1, imm):
        return i_type(0x13, rd, 0, rs1, imm)

    def lui(rd, imm20):
        return ((imm20 & 0xFFFFF) << 12) | (r(rd) << 7) | 0x37

    def li_eid(reg, value):
        upper = (value >> 12) & 0xFFFFF
        lower = value & 0xFFF
        return [lui(reg, upper), addi(reg, reg, lower)]

    RET = i_type(0x67, 'zero', 0, 'ra', 0)
    ECALL = 0x00000073

    def assemble(instrs, base_addr):
        code = b''.join(struct.pack('<I', w) for w in instrs)
        offset = base_addr - PHYS_START
        for i, b in enumerate(code):
            mem_view[offset + i] = b
        return len(code)

    trampoline_base = PHYS_START + efi_offset + 0x400

    copy_mem_addr = trampoline_base
    copy_mem_instrs = (
        [addi('a3', 'zero', 0),
         b_type(0x63, 0, 'a2', 'a3', 28)]
        + [i_type(0x03, 't0', 4, 'a1', 0),
           s_type(0x23, 0, 'a0', 't0', 0),
           addi('a0', 'a0', 1),
           addi('a1', 'a1', 1),
           addi('a2', 'a2', -1),
           b_type(0x63, 1, 'a2', 'a3', -20)]
        + [RET]
    )
    copy_mem_size = assemble(copy_mem_instrs, copy_mem_addr)

    allocate_pool_addr = copy_mem_addr + copy_mem_size
    allocate_pool_instrs = (
        [addi('a3', 'a2', 0),
         addi('a0', 'a1', 0)]
        + li_eid('a7', SBI_EXT_UEFI)
        + [addi('a6', 'zero', UEFI_ALLOCATE_POOL),
           ECALL,
           s_type(0x23, 3, 'a3', 'a1', 0),
           RET]
    )
    size_used = assemble(allocate_pool_instrs, allocate_pool_addr)

    handle_protocol_addr = allocate_pool_addr + size_used + 0x40
    lip_base = PHYS_START + efi_offset + 0x600
    lip_struct = struct.pack('<QQQQQQQQQQQ',
        PHYS_START + 0x02001000,
        PHYS_START + 0x80201000,
        0x000c0000,
        0x0000b6d8,
        0, 0, 0, 0, 0, 0, 0
    )
    lip_offset = lip_base - PHYS_START
    for i, b in enumerate(lip_struct):
        mem_view[lip_offset + i] = b

    handle_protocol_instrs = [
        addi('a0', 'zero', 0),
        lui('t0', (lip_base >> 12) & 0xFFFFF),
        addi('t0', 't0', lip_base & 0xFFF),
        s_type(0x23, 3, 'a2', 't0', 0),
        RET,
    ]
    assemble(handle_protocol_instrs, handle_protocol_addr)

    allocate_pages_addr = handle_protocol_addr + 0x40
    allocate_pages_instrs = (
        li_eid('a7', SBI_EXT_UEFI)
        + [addi('a6', 'zero', 2),
           ECALL,
           RET]
    )
    assemble(allocate_pages_instrs, allocate_pages_addr)

    get_memory_map_addr = allocate_pages_addr + 0x40
    get_memory_map_instrs = (
        li_eid('a7', SBI_EXT_UEFI)
        + [addi('a6', 'zero', 3),
           ECALL,
           RET]
    )
    assemble(get_memory_map_instrs, get_memory_map_addr)

    exit_bs_addr = get_memory_map_addr + 0x40
    exit_boot_services_instrs = [
        addi('a0', 'zero', 0),
        RET,
    ]
    assemble(exit_boot_services_instrs, exit_bs_addr)

    output_string_addr = exit_bs_addr + 0x40
    output_string_instrs = (
        li_eid('a7', SBI_EXT_UEFI)
        + [addi('a6', 'zero', 4),
           ECALL,
           RET]
    )
    assemble(output_string_instrs, output_string_addr)

    bs_base = sys_offset + 0x100
    patch_ptr(bs_base, 0x28, allocate_pages_addr)
    patch_ptr(bs_base, 0x38, get_memory_map_addr)
    patch_ptr(bs_base, 0x40, allocate_pool_addr)
    patch_ptr(bs_base, 0x98, handle_protocol_addr)
    patch_ptr(bs_base, 0xE8, exit_bs_addr)
    patch_ptr(bs_base, 0x148, copy_mem_addr)

    con_out_base = sys_offset + 0x500
    patch_ptr(con_out_base, 0x0, exit_bs_addr)
    patch_ptr(con_out_base, 0x8, output_string_addr)
"""

content = content.replace("    print(\"\\n[4] Initializing GPU...\")", injection + "\n    print(\"\\n[4] Initializing GPU...\")")

content = content.replace(
    "memory = np.zeros((pixel_count, 4), dtype=np.uint32)",
    "memory = np.zeros((pixel_count, 4), dtype=np.uint8)"
)

# And fix cpu_state initialization
cpu_state_patch = """
    # [4b] Initialize UEFI heap (for PE32+ kernels)
    UEFI_HEAP_BASE = 0x87800000
    UEFI_HEAP_SIZE = 8 * 1024 * 1024  # 8MB
    cpu_state[0]['uefi_heap_ptr'] = UEFI_HEAP_BASE
    cpu_state[0]['uefi_heap_end'] = UEFI_HEAP_BASE + UEFI_HEAP_SIZE
    print(f"    UEFI heap: 0x{UEFI_HEAP_BASE:08x} - 0x{UEFI_HEAP_BASE + UEFI_HEAP_SIZE:08x}")
    
    cpu_state[0]['regs'][2][0] = UEFI_HEAP_BASE + UEFI_HEAP_SIZE
    cpu_state[0]['regs'][10][0] = PHYS_START + 0x02001000
"""

content = content.replace(
    "cpu_state = make_cpu_state(loader.entry_point, priv_mode=3)  # M-mode boot",
    "cpu_state = make_cpu_state(loader.entry_point, priv_mode=3)  # M-mode boot" + cpu_state_patch
)

with open("tools/boot_xv6_gpu.py", "w") as f:
    f.write(content)
