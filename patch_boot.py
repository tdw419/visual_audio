import sys

with open("tools/boot_xv6_gpu.py", "r") as f:
    content = f.read()

# Fix memory array dtype
content = content.replace(
    "memory = np.zeros((pixel_count, 4), dtype=np.uint32)",
    "memory = np.zeros((pixel_count, 4), dtype=np.uint8)"
)

# Fix mem_view
content = content.replace(
    "mem_view = memory.view(np.uint32).reshape(-1)",
    "mem_view = memory.view(np.uint8).reshape(-1)"
)

# Fix patch_ptr
content = content.replace(
    "mem_view[(table_base - PHYS_START) + offset + i] = b",
    "mem_view[table_base + offset + i] = b"
)
content = content.replace(
    "def patch_ptr(table_base, offset, val):",
    "def patch_ptr(table_base, offset, val):"
) # Actually, I need to make sure table_base usage is correct

# Fix assemble
old_assemble = """        def assemble(instrs, base_addr):
            code = b''.join(struct.pack('<I', w) for w in instrs)
            offset = base_addr - PHYS_START
            for i, b in enumerate(code):
                mem_view[offset + i] = b
            return len(code)"""
            
new_assemble = """        def assemble(instrs, base_addr):
            code = b''.join(struct.pack('<I', w) for w in instrs)
            offset = base_addr - PHYS_START
            for i, b in enumerate(code):
                mem_view[offset + i] = b
            return len(code)"""

# No wait, assemble was already bytes in the original file, it was just WRITING bytes to a uint32 array.
# Since I changed mem_view to uint8, the original assemble works perfectly!

# Fix UEFI_HEAP_BASE
content = content.replace(
    "UEFI_HEAP_BASE = 0x88000000",
    "UEFI_HEAP_BASE = 0x87800000"
)

# Fix debug print
content = content.replace(
    "print(f\"    CPU state: PC=0x{cpu_state[0]['pc']:016x}, M-mode, MMU off\")",
    """print(f"    CPU state: PC=0x{loader.entry_point:016x}, M-mode, MMU off")
    ep_offset = loader.entry_point - PHYS_START
    print(f"    DEBUG: Memory at entry point: {[hex(x) for x in mem_view[ep_offset:ep_offset+16]]}")"""
)

with open("tools/boot_xv6_gpu.py", "w") as f:
    f.write(content)
    
