import numpy as np
from tools.glyph_isa_v2 import OpcodeMapV2, GlyphAssemblerV2, GlyphCPUv2

def test_memory():
    opcode_map = OpcodeMapV2()
    assembler = GlyphAssemblerV2(opcode_map)
    cpu = GlyphCPUv2(opcode_map, cols_instrs=8)
    
    # Store 42 at memory address 10 (r1=10, r2=42)
    # Load from memory address 10 into r3
    program = [
        "LDI r1 10",
        "LDI r2 42",
        "ST r1 r2",   # store r2 into addr in r1
        "LD r3 r1",   # load from addr in r1 into r3
        "HALT"
    ]
    
    image = assembler.assemble(program, width_instrs=8)
    cpu.run(image)
    
    # r3 should be 42
    assert cpu.registers[3] == 42
    assert cpu.memory[10] == 42
    print("Memory tests passed!")
    opcode_map.close()

if __name__ == '__main__':
    test_memory()
