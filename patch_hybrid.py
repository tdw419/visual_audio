import sys

with open("tools/boot_xv6_gpu.py", "r") as f:
    content = f.read()

content = content.replace("from riscv_gpu_cpu import make_cpu_state", 
"from riscv_gpu_cpu import make_cpu_state\nfrom hybrid_kernel_loader import HybridKernelLoader")

content = content.replace("elf = ELF64Loader(elf_path)", "loader = HybridKernelLoader(elf_path)")
content = content.replace("elf.get_loadable_segments()", "loader.get_loadable_segments()")
content = content.replace("elf.entry_point", "loader.entry_point")

# Change the load loop to handle PE32+ segments:
old_loop = """    for seg in loader.get_loadable_segments():
        addr = seg['p_vaddr']
        size = seg['p_memsz']
        filesz = seg['p_filesz']
        offset = addr - PHYS_START"""

new_loop = """    fmt = loader.get_format()
    for seg in loader.get_loadable_segments():
        if fmt == "ELF64":
            addr = seg['p_vaddr']
            size = seg['p_memsz']
            filesz = seg['p_filesz']
            offset = addr - PHYS_START
        else:
            addr = seg['VirtualAddress'] + PHYS_START + 0x00201000
            size = seg['VirtualSize']
            filesz = seg['SizeOfRawData']
            offset = addr - PHYS_START"""

content = content.replace(old_loop, new_loop)

# Fix the memory population:
old_pop = """        # Copy segment data to pixel memory (2D RGBA layout)
        data = loader.get_segment_data(seg)
        # Reshape byte data to pixel layout
        start_pixel = offset // 4
        start_byte = offset % 4

        if start_byte == 0:
            # Aligned - can copy efficiently
            word_count = (len(data) + 3) // 4
            byte_data = np.frombuffer(data, dtype=np.uint8)
            # Reshape to (N, 4) and copy
            padded_len = word_count * 4
            if len(byte_data) < padded_len:
                padded = np.zeros(padded_len, dtype=np.uint8)
                padded[:len(byte_data)] = byte_data
                byte_data = padded
            pixel_data = byte_data.view(np.uint32).reshape(-1, 1)
            # memory view expects uint32 values
            # Wait, memory is now uint8!
            memory[start_pixel:start_pixel + word_count] = byte_data.reshape(-1, 4)
        else:"""

old_pop2 = """            # Aligned - can copy efficiently
            word_count = (len(data) + 3) // 4
            byte_data = np.frombuffer(data, dtype=np.uint32)
            # Reshape to (N, 1) and copy to first channel (R)
            # We must pad to multiple of 4 bytes first
            if len(data) % 4 != 0:
                padded = bytearray(data)
                padded.extend(b'\\0' * (4 - (len(data) % 4)))
                byte_data = np.frombuffer(padded, dtype=np.uint32)
                
            pixel_data = byte_data.reshape(-1, 1)
            # Actually memory expects uint32 in a specific way, we need to broadcast to shape (N, 4)
            # But memory is uint32 (N, 4), so memory[i, 0] = word
            # Wait! memory is uint32 (N, 4) in the original code! Let's just fix it all."""

# I will just regex the whole loop!
import re

content = re.sub(r"    for seg in loader\.get_loadable_segments\(\):.*?bss_start = offset \+ filesz",
"""    fmt = loader.get_format()
    for seg in loader.get_loadable_segments():
        if fmt == "ELF64":
            addr = seg['p_vaddr']
            size = seg['p_memsz']
            filesz = seg['p_filesz']
            offset = addr - PHYS_START
        else:
            addr = seg['VirtualAddress'] + PHYS_START + 0x00201000
            size = seg['VirtualSize']
            filesz = seg['SizeOfRawData']
            offset = addr - PHYS_START

        data = loader.get_segment_data(seg)
        start_pixel = offset // 4
        word_count = (len(data) + 3) // 4
        byte_data = np.frombuffer(data, dtype=np.uint8)
        padded_len = word_count * 4
        if len(byte_data) < padded_len:
            padded = np.zeros(padded_len, dtype=np.uint8)
            padded[:len(byte_data)] = byte_data
            byte_data = padded
        pixel_data = byte_data.reshape(-1, 4)
        memory[start_pixel:start_pixel + word_count] = pixel_data
        print(f"  Loaded {filesz} bytes at 0x{addr:016x}")
        if size > filesz:
            bss_start = offset + filesz""", content, flags=re.DOTALL)

with open("tools/boot_xv6_gpu.py", "w") as f:
    f.write(content)
