#!/usr/bin/env python3
"""Debug M1: path length vs LDI immediate range (item-25)."""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np  # noqa: E402

from tools.glyph_isa_v2 import GlyphAssemblerV2, GlyphCPUv2, OpcodeMapV2  # noqa: E402

opcode_map = OpcodeMapV2()
asm = GlyphAssemblerV2(opcode_map)
prog = ['LDI r1 32', 'LDI r2 96', 'LDI r3 26', 'SYSCALL r0 0x03',
        'LDI r1 32', 'LDI r2 128', 'LDI r3 26', 'SYSCALL r4 0x04', 'HALT']
image = asm.assemble(prog, width_instrs=8)
if image.shape[0] < 5:
    ni = np.zeros((5, image.shape[1], 3), dtype=np.uint8)
    ni[: image.shape[0]] = image
    image = ni
cpu = GlyphCPUv2(opcode_map, cols_instrs=8)
tmp = tempfile.mkdtemp()
p = os.path.join(tmp, 'x.txt')
print('path:', p, 'len:', len(p))
for i, ch in enumerate(p + chr(0)):
    cpu.memory[32 + i] = ord(ch)
for i, b in enumerate(b'Hello from spatial memory!'):
    cpu.memory[96 + i] = b
cpu.run(image)
print('exists:', os.path.exists(p))
print('mem[32:40] as str:', bytes(cpu.memory[32:40]))
