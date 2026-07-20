#!/usr/bin/env python3
"""
Debug instruction decode
"""

def decode_jal(word):
    imm_20 = (word >> 31) & 1
    imm_10_1 = (word >> 21) & 1023
    imm_11 = (word >> 20) & 1
    imm_19_12 = (word >> 12) & 255
    rd = (word >> 7) & 31
    opcode = word & 127
    
    imm = (imm_20 << 20) | (imm_19_12 << 12) | (imm_11 << 11) | (imm_10_1 << 1)
    # Sign extend
    if imm & (1 << 20):
        imm = imm | 0xFFF00000  # Sign extend to 32 bits
    
    print(f'Word: 0x{word:08x}')
    print(f'  Opcode: 0x{opcode:02x} (JAL={0x6f:x})')
    print(f'  rd: {rd} (ra={1})')
    print(f'  imm components:')
    print(f'    imm_20 = {imm_20}')
    print(f'    imm_10_1 = 0x{imm_10_1:03x}')
    print(f'    imm_11 = {imm_11}')
    print(f'    imm_19_12 = 0x{imm_19_12:02x}')
    print(f'  imm = 0x{imm & 0xFFFFF:05x} (signed {imm})')
    print(f'  JAL ra, {imm}  # PC = PC + {imm}')

word = 0x00a000ef
print('Decoding entry instruction:')
decode_jal(word)
print()

word2 = 0x10500073
print('Decoding second instruction:')
print(f'Word: 0x{word2:08x}')
opcode = word2 & 127
print(f'  Opcode: 0x{opcode:02x} (SYSTEM={0x73:x})')
funct3 = (word2 >> 12) & 7
funct12 = word2 >> 20
print(f'  funct3 = {funct3}')
print(f'  funct12 = 0x{funct12:03x}')
print(f'  This is ECALL or WFI')