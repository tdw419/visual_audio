#!/usr/bin/env python3
"""Minimal RV32I assembler for a small, fixed instruction subset - just
enough to assemble the test program used to verify the multi-instance GPU
RISC-V emulator (multi_instance_rv32i.wgsl). Not a general assembler;
supports exactly: ADDI, LW, SW, BLT, BGE, JAL, ADD, ECALL.
"""
import struct


def r_type(funct7, rs2, rs1, funct3, rd, opcode):
    return (funct7 << 25) | (rs2 << 20) | (rs1 << 15) | (funct3 << 12) | (rd << 7) | opcode


def i_type(imm, rs1, funct3, rd, opcode):
    imm &= 0xFFF
    return (imm << 20) | (rs1 << 15) | (funct3 << 12) | (rd << 7) | opcode


def s_type(imm, rs2, rs1, funct3, opcode):
    imm &= 0xFFF
    imm_11_5 = (imm >> 5) & 0x7F
    imm_4_0 = imm & 0x1F
    return (imm_11_5 << 25) | (rs2 << 20) | (rs1 << 15) | (funct3 << 12) | (imm_4_0 << 7) | opcode


def b_type(imm, rs2, rs1, funct3, opcode):
    # imm is a byte offset, must be even; encodes bits [12|10:5|4:1|11]
    imm &= 0x1FFE
    b12 = (imm >> 12) & 1
    b11 = (imm >> 11) & 1
    b10_5 = (imm >> 5) & 0x3F
    b4_1 = (imm >> 1) & 0xF
    return (b12 << 31) | (b10_5 << 25) | (rs2 << 20) | (rs1 << 15) | (funct3 << 12) | (b4_1 << 8) | (b11 << 7) | opcode


def j_type(imm, rd, opcode):
    imm &= 0x1FFFFE
    b20 = (imm >> 20) & 1
    b19_12 = (imm >> 12) & 0xFF
    b11 = (imm >> 11) & 1
    b10_1 = (imm >> 1) & 0x3FF
    return (b20 << 31) | (b10_1 << 21) | (b11 << 20) | (b19_12 << 12) | (rd << 7) | opcode


def ADDI(rd, rs1, imm): return i_type(imm, rs1, 0x0, rd, 0x13)
def LW(rd, rs1, imm): return i_type(imm, rs1, 0x2, rd, 0x03)
def SW(rs2, rs1, imm): return s_type(imm, rs2, rs1, 0x2, 0x23)
def BLT(rs1, rs2, imm): return b_type(imm, rs2, rs1, 0x4, 0x63)
def BGE(rs1, rs2, imm): return b_type(imm, rs2, rs1, 0x5, 0x63)
def JAL(rd, imm): return j_type(imm, rd, 0x6F)
def ADD(rd, rs1, rs2): return r_type(0x00, rs2, rs1, 0x0, rd, 0x33)
def ECALL(): return i_type(0, 0, 0x0, 0, 0x73)


def assemble_sum_program() -> bytes:
    """Same program, with correctly computed branch/jump offsets.
    Layout (byte addresses):
      0:  ADDI x1, x0, 0        ; sum = 0
      4:  LW   x2, 0(x0)        ; N = mem[0]
      8:  ADDI x3, x0, 1        ; i = 1
      12: loop: BLT x2, x3, +16 -> target 28 (done)   [12 + 16 = 28]
      16: ADD  x1, x1, x3       ; sum += i
      20: ADDI x3, x3, 1        ; i += 1
      24: JAL  x0, -12          ; -> back to 12 (loop)
      28: done: SW  x1, 4(x0)   ; mem[4] = sum
      32: ECALL                 ; halt
    """
    prog = [
        ADDI(1, 0, 0),
        LW(2, 0, 0),
        ADDI(3, 0, 1),
        BLT(2, 3, 16),   # 12 -> 28
        ADD(1, 1, 3),
        ADDI(3, 3, 1),
        JAL(0, -12),     # 24 -> 12
        SW(1, 0, 4),
        ECALL(),
    ]
    return b"".join(struct.pack("<I", w) for w in prog)


if __name__ == "__main__":
    code = assemble_sum_program()
    print(f"{len(code)} bytes, {len(code)//4} instructions")
    words = struct.unpack(f"<{len(code)//4}I", code)
    for i, w in enumerate(words):
        print(f"  [{i*4:3d}] 0x{w:08x}")
    print("Rust array literal:")
    print("[" + ", ".join(f"0x{w:08x}" for w in words) + "]")
