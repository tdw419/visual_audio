#!/usr/bin/env python3
"""Disassemble the Alpine kernel around a given physical offset to see what runs there."""
import sys
import struct
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rv64i_decode import decode_instruction, expand_rvc, OP_INVALID

ALPINE_LNX = '/home/jericho/projects/zion/apps/linux/alpine/alpine-riscv64.lnx.bin'

def load_kernel():
    data = Path(ALPINE_LNX).read_bytes()
    kernel_offset, kernel_size, initrd_size = struct.unpack('<III', data[4:16])
    return data[kernel_offset:kernel_offset + kernel_size]

def disasm(code, start_off, count=32):
    i = start_off
    n = 0
    while i + 1 < len(code) and n < count:
        half0 = code[i] | (code[i+1] << 8)
        if (half0 & 0x3) == 0x3:
            if i + 3 >= len(code):
                break
            half1 = code[i+2] | (code[i+3] << 8)
            instr = (half1 << 16) | half0
            length = 4
        else:
            instr = expand_rvc(half0)
            length = 2
            if instr == 0:
                print(f'  0x{i:08x}: 0x{half0:04x}  (bad RVC)')
                i += 2
                continue
        decoded = decode_instruction(instr)
        if decoded is None:
            print(f'  0x{i:08x}: 0x{instr:08x}  (undecodable)')
        else:
            op, rd, rs1, rs2, imm, aux = decoded
            print(f'  0x{i:08x}: 0x{instr:08x}  op={op} rd={rd} rs1={rs1} rs2={rs2} imm={imm} aux={aux}')
        i += length
        n += 1

def main():
    code = load_kernel()
    off = int(sys.argv[1], 0) if len(sys.argv) > 1 else 0x10b4
    print(f'Kernel image {len(code)} bytes; disassembling at byte offset 0x{off:x} (virtual 0xffffffff80200000 + {off:#x}):')
    disasm(code, off, int(sys.argv[2]) if len(sys.argv) > 2 else 32)

if __name__ == '__main__':
    main()
