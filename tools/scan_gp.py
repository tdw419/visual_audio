import struct
from pe32_loader import PE32Loader
loader = PE32Loader('boot_images/alpine_Image')
print(f"Entry point: {hex(loader.entry_point)}")
text_sec = next(s for s in loader.sections if s['name'] == '.text')
data = loader.get_section_data(text_sec)
# Look for auipc gp, 0x1557
# auipc gp (x3), imm
# gp = 3. 0x1557 << 12
# opcode = 0x17, rd = 3
# 0x01557197
for i in range(0, len(data) - 4, 2):
    instr = struct.unpack_from('<I', data, i)[0]
    if instr == 0x01557197:
        print(f"Found auipc gp at offset {hex(i)}")
