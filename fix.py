with open("tools/glyph_isa_v2.py", "r") as f:
    lines = f.readlines()

new_lines = []
i = 0
while i < len(lines):
    line = lines[i]
    if line.strip().startswith("elif opcode == 'CMP':") and "self.registers[0]" in lines[i+1]:
        # replace these lines
        new_lines.append("        elif opcode == 'CMP':\n")
        new_lines.append("            self.registers[0] = 1 if self.registers[rd] == self.registers[rs2] else 0\n")
        new_lines.append("        elif opcode == 'LD':\n")
        new_lines.append("            addr = self.registers[rs1]\n")
        new_lines.append("            if 0 <= addr < len(self.memory):\n")
        new_lines.append("                self.registers[rd] = self.memory[addr]\n")
        new_lines.append("        elif opcode == 'ST':\n")
        new_lines.append("            addr = self.registers[rd]\n")
        new_lines.append("            if 0 <= addr < len(self.memory):\n")
        new_lines.append("                self.memory[addr] = self.registers[rs2]\n")
        i += 2
        continue
    new_lines.append(line)
    i += 1
    
with open("tools/glyph_isa_v2.py", "w") as f:
    f.write("".join(new_lines))
