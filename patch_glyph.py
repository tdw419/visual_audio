import sys

with open("tools/glyph_isa_v2.py", "r") as f:
    content = f.read()

# Add LD and ST to OPCODES
content = content.replace("'PRT': 'print',", "'PRT': 'print',\n        'LD': 'load',\n        'ST': 'store',")

# Add memory to GlyphCPUv2
content = content.replace("self.registers = [0] * 32", "self.registers = [0] * 32\n        self.memory = [0] * 1024")

# Add handling in assembler
content = content.replace("elif opcode in ('ADD', 'SUB', 'CMP'):", "elif opcode in ('ADD', 'SUB', 'CMP', 'LD', 'ST'):")

# Add LD/ST to step()
step_impl = """        elif opcode == 'CMP':
            self.registers[0] = 1 if self.registers[rd] == self.registers[rs2] else 0
        elif opcode == 'LD':
            addr = self.registers[rs2]
            if 0 <= addr < len(self.memory):
                self.registers[rd] = self.memory[addr]
        elif opcode == 'ST':
            addr = self.registers[rs1]
            if 0 <= addr < len(self.memory):
                self.memory[addr] = self.registers[rs2]"""
content = content.replace("elif opcode == 'CMP':\n            self.registers[0] = 1 if self.registers[rd] == self.registers[rs2] else 0", step_impl)

with open("tools/glyph_isa_v2.py", "w") as f:
    f.write(content)
