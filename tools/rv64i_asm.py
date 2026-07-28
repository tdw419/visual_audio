"""
Minimal RV64I assembler for the spatial GPU emulator (SPATIAL_RV64I.wgsl).

Supports the base integer ISA implemented by the shader:
  addi slti sltiu xori ori andi slli srli srai
  add sub sll slt sltu xor srl sra or and
  lw sw
  beq bne blt bge bltu bgeu
  jal jalr
  lui auipc
  ecall ebreak
Pseudo-ops: nop, mv, li (12-bit or full 32-bit), j, jr, ret, call (as jal)

Usage:
    python3 rv64i_asm.py input.s -o output.bin
"""

import argparse
import re
import struct
import sys

ABI_NAMES = {
    'zero': 0, 'ra': 1, 'sp': 2, 'gp': 3, 'tp': 4,
    't0': 5, 't1': 6, 't2': 7,
    's0': 8, 'fp': 8, 's1': 9,
    'a0': 10, 'a1': 11, 'a2': 12, 'a3': 13, 'a4': 14, 'a5': 15, 'a6': 16, 'a7': 17,
    's2': 18, 's3': 19, 's4': 20, 's5': 21, 's6': 22, 's7': 23, 's8': 24, 's9': 25, 's10': 26, 's11': 27,
    't3': 28, 't4': 29, 't5': 30, 't6': 31,
}


def reg(tok):
    tok = tok.strip().rstrip(',')
    if tok in ABI_NAMES:
        return ABI_NAMES[tok]
    m = re.fullmatch(r'x(\d+)', tok)
    if m:
        n = int(m.group(1))
        if 0 <= n <= 31:
            return n
    raise ValueError(f"Unknown register: {tok}")


def parse_imm(tok, labels, pc):
    tok = tok.strip().rstrip(',')
    if tok in labels:
        return labels[tok] - pc
    try:
        return int(tok, 0)
    except ValueError:
        raise ValueError(f"Unknown immediate/label: {tok}")


def u32(v):
    return v & 0xFFFFFFFF


R_TYPE = {
    # mnemonic: (funct7, funct3)
    'add':  (0x00, 0x0), 'sub':  (0x20, 0x0),
    'sll':  (0x00, 0x1),
    'slt':  (0x00, 0x2), 'sltu': (0x00, 0x3),
    'xor':  (0x00, 0x4),
    'srl':  (0x00, 0x5), 'sra':  (0x20, 0x5),
    'or':   (0x00, 0x6),
    'and':  (0x00, 0x7),
    # M extension
    'mul':    (0x01, 0x0), 'mulh': (0x01, 0x1), 'mulhsu': (0x01, 0x2), 'mulhu': (0x01, 0x3),
    'div':    (0x01, 0x4), 'divu': (0x01, 0x5), 'rem':    (0x01, 0x6), 'remu':  (0x01, 0x7),
}

I_ALU = {
    # mnemonic: funct3 (shifts also need funct7)
    'addi': 0x0, 'slti': 0x2, 'sltiu': 0x3, 'xori': 0x4,
    'ori': 0x6, 'andi': 0x7,
}

I_SHIFT = {
    'slli': (0x00, 0x1), 'srli': (0x00, 0x5), 'srai': (0x20, 0x5),
}

BRANCH = {
    'beq': 0x0, 'bne': 0x1, 'blt': 0x4, 'bge': 0x5, 'bltu': 0x6, 'bgeu': 0x7,
}


def split_mem_operand(tok):
    # imm(reg) syntax, e.g. "4(x1)" or "0(sp)"
    m = re.fullmatch(r'(-?\w+)\((\w+)\)', tok.strip().rstrip(','))
    if not m:
        raise ValueError(f"Expected imm(reg) operand, got: {tok}")
    return m.group(1), m.group(2)


def encode_r(funct7, rs2, rs1, funct3, rd, opcode):
    return u32((funct7 << 25) | (rs2 << 20) | (rs1 << 15) | (funct3 << 12) | (rd << 7) | opcode)


def encode_i(imm12, rs1, funct3, rd, opcode):
    return u32(((imm12 & 0xFFF) << 20) | (rs1 << 15) | (funct3 << 12) | (rd << 7) | opcode)


def encode_s(imm12, rs2, rs1, funct3, opcode):
    imm5 = imm12 & 0x1F
    imm7 = (imm12 >> 5) & 0x7F
    return u32((imm7 << 25) | (rs2 << 20) | (rs1 << 15) | (funct3 << 12) | (imm5 << 7) | opcode)


def encode_b(imm13, rs2, rs1, funct3, opcode):
    imm12 = (imm13 >> 12) & 0x1
    imm10_5 = (imm13 >> 5) & 0x3F
    imm4_1 = (imm13 >> 1) & 0xF
    imm11 = (imm13 >> 11) & 0x1
    return u32((imm12 << 31) | (imm10_5 << 25) | (rs2 << 20) | (rs1 << 15) |
               (funct3 << 12) | (imm4_1 << 8) | (imm11 << 7) | opcode)


def encode_u(imm20, rd, opcode):
    return u32((imm20 << 12) | (rd << 7) | opcode)


def encode_j(imm21, rd, opcode):
    imm20 = (imm21 >> 20) & 0x1
    imm10_1 = (imm21 >> 1) & 0x3FF
    imm11 = (imm21 >> 11) & 0x1
    imm19_12 = (imm21 >> 12) & 0xFF
    return u32((imm20 << 31) | (imm10_1 << 21) | (imm11 << 20) | (imm19_12 << 12) | (rd << 7) | opcode)


def strip_comment(line):
    for marker in ('#', '//'):
        idx = line.find(marker)
        if idx != -1:
            line = line[:idx]
    return line.strip()


def first_pass(lines):
    """Compute label -> byte address, expanding pseudo-ops that emit >1 instruction."""
    labels = {}
    addr = 0
    expanded = []
    for raw in lines:
        line = strip_comment(raw)
        if not line:
            continue
        if line.endswith(':'):
            labels[line[:-1].strip()] = addr
            continue
        if ':' in line:
            label, rest = line.split(':', 1)
            labels[label.strip()] = addr
            line = rest.strip()
            if not line:
                continue
        parts = re.split(r'[\s,]+', line)
        mnemonic = parts[0].lower()
        n = instr_count(mnemonic, parts[1:])
        expanded.append((addr, line))
        addr += 4 * n
    return labels, expanded


def instr_count(mnemonic, operands):
    if mnemonic == 'li':
        imm_tok = operands[1] if len(operands) > 1 else '0'
        try:
            val = int(imm_tok, 0)
        except ValueError:
            val = 0
        if -2048 <= val <= 2047:
            return 1
        return 2  # lui + addi
    return 1


def assemble_line(line, labels, addr):
    parts = re.split(r'[\s,]+', line)
    mnemonic = parts[0].lower()
    ops = [p for p in parts[1:] if p != '']

    if mnemonic in R_TYPE:
        funct7, funct3 = R_TYPE[mnemonic]
        rd, rs1, rs2 = reg(ops[0]), reg(ops[1]), reg(ops[2])
        return [encode_r(funct7, rs2, rs1, funct3, rd, 0x33)]

    if mnemonic in I_ALU:
        funct3 = I_ALU[mnemonic]
        rd, rs1 = reg(ops[0]), reg(ops[1])
        imm = parse_imm(ops[2], labels, addr)
        return [encode_i(imm, rs1, funct3, rd, 0x13)]

    if mnemonic in I_SHIFT:
        funct7, funct3 = I_SHIFT[mnemonic]
        rd, rs1 = reg(ops[0]), reg(ops[1])
        shamt = parse_imm(ops[2], labels, addr) & 0x1F
        return [encode_i((funct7 << 5) | shamt, rs1, funct3, rd, 0x13)]

    if mnemonic == 'lw':
        rd = reg(ops[0])
        imm_tok, rs1_tok = split_mem_operand(ops[1])
        imm = parse_imm(imm_tok, labels, addr)
        return [encode_i(imm, reg(rs1_tok), 0x2, rd, 0x03)]

    if mnemonic == 'sw':
        rs2 = reg(ops[0])
        imm_tok, rs1_tok = split_mem_operand(ops[1])
        imm = parse_imm(imm_tok, labels, addr)
        return [encode_s(imm, rs2, reg(rs1_tok), 0x2, 0x23)]

    if mnemonic in BRANCH:
        funct3 = BRANCH[mnemonic]
        rs1, rs2 = reg(ops[0]), reg(ops[1])
        imm = parse_imm(ops[2], labels, addr)
        return [encode_b(imm, rs2, rs1, funct3, 0x63)]

    if mnemonic == 'jal':
        if len(ops) == 2:
            rd = reg(ops[0])
            imm = parse_imm(ops[1], labels, addr)
        else:
            rd = 1
            imm = parse_imm(ops[0], labels, addr)
        return [encode_j(imm, rd, 0x6F)]

    if mnemonic == 'jalr':
        if len(ops) == 1:
            rd, rs1, imm = 1, reg(ops[0]), 0
        elif len(ops) == 2 and '(' in ops[1]:
            rd = reg(ops[0])
            imm_tok, rs1_tok = split_mem_operand(ops[1])
            rs1, imm = reg(rs1_tok), parse_imm(imm_tok, labels, addr)
        else:
            rd, rs1, imm = reg(ops[0]), reg(ops[1]), parse_imm(ops[2], labels, addr) if len(ops) > 2 else 0
        return [encode_i(imm, rs1, 0x0, rd, 0x67)]

    if mnemonic == 'lui':
        rd = reg(ops[0])
        imm = parse_imm(ops[1], labels, addr) & 0xFFFFF
        return [encode_u(imm, rd, 0x37)]

    if mnemonic == 'auipc':
        rd = reg(ops[0])
        imm = parse_imm(ops[1], labels, addr) & 0xFFFFF
        return [encode_u(imm, rd, 0x17)]

    if mnemonic == 'ecall':
        return [u32(0x00000073)]
    if mnemonic == 'ebreak':
        return [u32(0x00100073)]

    # Pseudo-instructions
    if mnemonic == 'nop':
        return [encode_i(0, 0, 0x0, 0, 0x13)]
    if mnemonic == 'mv':
        rd, rs1 = reg(ops[0]), reg(ops[1])
        return [encode_i(0, rs1, 0x0, rd, 0x13)]
    if mnemonic == 'not':
        rd, rs1 = reg(ops[0]), reg(ops[1])
        return [encode_i(-1 & 0xFFF, rs1, 0x4, rd, 0x13)]
    if mnemonic == 'j':
        imm = parse_imm(ops[0], labels, addr)
        return [encode_j(imm, 0, 0x6F)]
    if mnemonic == 'jr':
        return [encode_i(0, reg(ops[0]), 0x0, 0, 0x67)]
    if mnemonic == 'ret':
        return [encode_i(0, 1, 0x0, 0, 0x67)]
    if mnemonic == 'call':
        imm = parse_imm(ops[0], labels, addr)
        return [encode_j(imm, 1, 0x6F)]
    if mnemonic == 'li':
        rd = reg(ops[0])
        val = parse_imm(ops[1], labels, addr)
        if -2048 <= val <= 2047:
            return [encode_i(val, 0, 0x0, rd, 0x13)]
        upper = (val + 0x800) >> 12
        lower = val - (upper << 12)
        return [
            encode_u(upper & 0xFFFFF, rd, 0x37),
            encode_i(lower, rd, 0x0, rd, 0x13),
        ]

    raise ValueError(f"Unknown mnemonic: {mnemonic}")


def assemble(source: str) -> bytes:
    lines = source.splitlines()
    labels, expanded = first_pass(lines)
    out = bytearray()
    for addr, line in expanded:
        for word in assemble_line(line, labels, addr):
            out += struct.pack('<I', word)
    return bytes(out)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('input', help='Assembly source file (.s)')
    ap.add_argument('-o', '--output', required=True, help='Output binary file')
    args = ap.parse_args()

    with open(args.input) as f:
        source = f.read()

    binary = assemble(source)
    with open(args.output, 'wb') as f:
        f.write(binary)

    print(f"Assembled {len(binary)} bytes ({len(binary)//4} instructions) -> {args.output}")


if __name__ == '__main__':
    sys.exit(main())
