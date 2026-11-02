import numpy as np
from tools.glyph_isa_v2 import OpcodeMapV2, GlyphAssemblerV2, GlyphCPUv2

op_map = OpcodeMapV2()
assembler = GlyphAssemblerV2(op_map)
cpu = GlyphCPUv2(op_map, cols_instrs=8)
program = [
    "LDI r1 5",       # 0: r1=5
    "LDI r2 3",       # 1: r2=3
    "AND r1 r2",      # 2: r1=1
    "LDI r2 2",       # 3: r2=2
    "SHL r1 r2",      # 4: r1=4
    "PUSH r1",        # 5: Stack=[4]
    "CALL 4,1",       # 6: Push return PC (x=28, y=0). Jump to x=4, y=1 (idx 9)
    "POP r4",         # 7: Pop modified value from stack into r4
    "HALT",           # 8: Main program halts here
    # Subroutine at (4,1) - idx 9
    "POP r6",         # 9: Pop return address into r6
    "POP r5",         # 10: Pop 4 into r5
    "LDI r7 1",       # 11: r7=1
    "SHL r5 r7",      # 12: r5 = 4 << 1 = 8
    "PUSH r5",        # 13: Push 8 onto stack
    "PUSH r6",        # 14: Push return address back
    "RET",            # 15: Jump back to (x=28, y=0) which is idx 7
]
image = assembler.assemble(program, width_instrs=8)
cpu.registers[31] = 0
cpu.running = True

n = 0
while cpu.running and n < 20:
    pc = cpu.pc
    cpu.step(image)
    print(f"[{n}] PC={pc} -> r1={cpu.registers[1]} r4={cpu.registers[4]} r5={cpu.registers[5]} r6={cpu.registers[6]} sp={cpu.registers[31]}")
    n += 1

op_map.close()
