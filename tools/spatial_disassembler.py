import struct

# Register ABI names for easier reading
REG_NAMES = [
    "zero", "ra", "sp", "gp", "tp", "t0", "t1", "t2",
    "s0/fp", "s1", "a0", "a1", "a2", "a3", "a4", "a5",
    "a6", "a7", "s2", "s3", "s4", "s5", "s6", "s7",
    "s8", "s9", "s10", "s11", "t3", "t4", "t5", "t6"
]

def sign_extend(val, bits):
    sign_bit = 1 << (bits - 1)
    return (val & (sign_bit - 1)) - (val & sign_bit)

def disassemble_instruction(instr: int, pc: int) -> str:
    opcode = instr & 0x7F
    rd = (instr >> 7) & 0x1F
    funct3 = (instr >> 12) & 0x7
    rs1 = (instr >> 15) & 0x1F
    rs2 = (instr >> 20) & 0x1F
    funct7 = (instr >> 25) & 0x7F
    
    r_name = lambda reg: f"x{reg}" # or use REG_NAMES[reg]

    if opcode == 0x37:
        # lui
        imm = (instr & 0xFFFFF000)
        return f"lui {r_name(rd)}, 0x{imm >> 12:x}"
    
    elif opcode == 0x17:
        # auipc
        imm = (instr & 0xFFFFF000)
        return f"auipc {r_name(rd)}, 0x{imm >> 12:x}"
        
    elif opcode == 0x6F:
        # jal
        imm20 = (instr >> 31) & 0x1
        imm19_12 = (instr >> 12) & 0xFF
        imm11 = (instr >> 20) & 0x1
        imm10_1 = (instr >> 21) & 0x3FF
        imm = sign_extend((imm20 << 20) | (imm19_12 << 12) | (imm11 << 11) | (imm10_1 << 1), 21)
        target = pc + imm
        return f"jal {r_name(rd)}, {imm}  # -> 0x{target:08x}"
        
    elif opcode == 0x67:
        # jalr
        imm = sign_extend(instr >> 20, 12)
        return f"jalr {r_name(rd)}, {imm}({r_name(rs1)})"
        
    elif opcode == 0x63:
        # Branch
        imm12 = (instr >> 31) & 0x1
        imm11 = (instr >> 7) & 0x1
        imm10_5 = (instr >> 25) & 0x3F
        imm4_1 = (instr >> 8) & 0xF
        imm = sign_extend((imm12 << 12) | (imm11 << 11) | (imm10_5 << 5) | (imm4_1 << 1), 13)
        target = pc + imm
        ops = ["beq", "bne", "??", "??", "blt", "bge", "bltu", "bgeu"]
        return f"{ops[funct3]} {r_name(rs1)}, {r_name(rs2)}, {imm}  # -> 0x{target:08x}"
        
    elif opcode == 0x03:
        # Load
        imm = sign_extend(instr >> 20, 12)
        ops = ["lb", "lh", "lw", "ld", "lbu", "lhu", "lwu"]
        if funct3 < len(ops):
            return f"{ops[funct3]} {r_name(rd)}, {imm}({r_name(rs1)})"
        return f"unknown_load_{funct3} {r_name(rd)}, {imm}({r_name(rs1)})"
        
    elif opcode == 0x23:
        # Store
        imm11_5 = (instr >> 25) & 0x7F
        imm4_0 = (instr >> 7) & 0x1F
        imm = sign_extend((imm11_5 << 5) | imm4_0, 12)
        ops = ["sb", "sh", "sw", "sd"]
        if funct3 < len(ops):
            return f"{ops[funct3]} {r_name(rs2)}, {imm}({r_name(rs1)})"
        return f"unknown_store_{funct3} {r_name(rs2)}, {imm}({r_name(rs1)})"
        
    elif opcode == 0x13:
        # I-type ALU
        imm = sign_extend(instr >> 20, 12)
        shamt = (instr >> 20) & 0x1F
        if funct3 == 0: return f"addi {r_name(rd)}, {r_name(rs1)}, {imm}"
        elif funct3 == 2: return f"slti {r_name(rd)}, {r_name(rs1)}, {imm}"
        elif funct3 == 3: return f"sltiu {r_name(rd)}, {r_name(rs1)}, {imm}"
        elif funct3 == 4: return f"xori {r_name(rd)}, {r_name(rs1)}, {imm}"
        elif funct3 == 6: return f"ori {r_name(rd)}, {r_name(rs1)}, {imm}"
        elif funct3 == 7: return f"andi {r_name(rd)}, {r_name(rs1)}, {imm}"
        elif funct3 == 1 and funct7 == 0: return f"slli {r_name(rd)}, {r_name(rs1)}, {shamt}"
        elif funct3 == 5 and funct7 == 0: return f"srli {r_name(rd)}, {r_name(rs1)}, {shamt}"
        elif funct3 == 5 and funct7 == 0x20: return f"srai {r_name(rd)}, {r_name(rs1)}, {shamt}"
        else: return f"unknown_itype_{funct3}_{funct7} {r_name(rd)}, {r_name(rs1)}, {imm}"
        
    elif opcode == 0x33:
        if funct7 == 1:
            # M-extension
            ops = ["mul", "mulh", "mulhsu", "mulhu", "div", "divu", "rem", "remu"]
            if funct3 < len(ops):
                return f"{ops[funct3]} {r_name(rd)}, {r_name(rs1)}, {r_name(rs2)}"
            return f"unknown_mext_{funct3} {r_name(rd)}, {r_name(rs1)}, {r_name(rs2)}"
        else:
            # R-type ALU
            if funct3 == 0 and funct7 == 0: return f"add {r_name(rd)}, {r_name(rs1)}, {r_name(rs2)}"
            elif funct3 == 0 and funct7 == 0x20: return f"sub {r_name(rd)}, {r_name(rs1)}, {r_name(rs2)}"
            elif funct3 == 1 and funct7 == 0: return f"sll {r_name(rd)}, {r_name(rs1)}, {r_name(rs2)}"
            elif funct3 == 2 and funct7 == 0: return f"slt {r_name(rd)}, {r_name(rs1)}, {r_name(rs2)}"
            elif funct3 == 3 and funct7 == 0: return f"sltu {r_name(rd)}, {r_name(rs1)}, {r_name(rs2)}"
            elif funct3 == 4 and funct7 == 0: return f"xor {r_name(rd)}, {r_name(rs1)}, {r_name(rs2)}"
            elif funct3 == 5 and funct7 == 0: return f"srl {r_name(rd)}, {r_name(rs1)}, {r_name(rs2)}"
            elif funct3 == 5 and funct7 == 0x20: return f"sra {r_name(rd)}, {r_name(rs1)}, {r_name(rs2)}"
            elif funct3 == 6 and funct7 == 0: return f"or {r_name(rd)}, {r_name(rs1)}, {r_name(rs2)}"
            elif funct3 == 7 and funct7 == 0: return f"and {r_name(rd)}, {r_name(rs1)}, {r_name(rs2)}"
            else: return f"unknown_rtype_{funct3}_{funct7} {r_name(rd)}, {r_name(rs1)}, {r_name(rs2)}"
            
    elif opcode == 0x73:
        if instr == 0x00000073: return "ecall"
        if instr == 0x00100073: return "ebreak"
        
        # Check for CSR instructions
        csr = instr >> 20
        if funct3 == 1: return f"csrrw {r_name(rd)}, 0x{csr:03x}, {r_name(rs1)}"
        elif funct3 == 2: return f"csrrs {r_name(rd)}, 0x{csr:03x}, {r_name(rs1)}"
        elif funct3 == 3: return f"csrrc {r_name(rd)}, 0x{csr:03x}, {r_name(rs1)}"
        elif funct3 == 5: return f"csrrwi {r_name(rd)}, 0x{csr:03x}, {rs1}"
        elif funct3 == 6: return f"csrrsi {r_name(rd)}, 0x{csr:03x}, {rs1}"
        elif funct3 == 7: return f"csrrci {r_name(rd)}, 0x{csr:03x}, {rs1}"
        
        return f"unknown_system_{instr:08x}"
        
    return f"unknown_opcode_{opcode:02x} ({instr:08x})"

def disassemble_block(binary_data: bytes, start_pc: int = 0):
    lines = []
    # Ensure padded to 4 bytes
    padded = binary_data + b'\x00' * ((4 - len(binary_data) % 4) % 4)
    words = struct.unpack(f"<{len(padded)//4}I", padded)
    
    for i, word in enumerate(words):
        pc = start_pc + i * 4
        asm = disassemble_instruction(word, pc)
        lines.append(f"{pc:08x}:  {word:08x}    {asm}")
        
    return "\n".join(lines)

if __name__ == "__main__":
    import argparse
    import sys
    
    parser = argparse.ArgumentParser(description="RV32I+M Disassembler")
    parser.add_argument("file", help="Raw binary file to disassemble")
    parser.add_argument("--base", type=lambda x: int(x, 0), default=0, help="Base PC address")
    args = parser.parse_args()
    
    try:
        with open(args.file, "rb") as f:
            data = f.read()
        print(disassemble_block(data, args.base))
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)
