#!/usr/bin/env python3
"""
Create simple test kernel without WFI
"""

import struct

# Simple RISC-V kernel:
# - lui a0, 42       ; a0 = 42
# - lui a1, 23       ; a1 = 23  
# - add a2, a0, a1   ; a2 = 65
# - lui a7, 93       ; a7 = 93 (sys_exit)
# - ecall            ; exit

def encode_lui(rd, imm):
    imm_20 = imm & 0xFFFFF
    return (imm_20 << 12) | (rd << 7) | 0x37

def encode_add(rd, rs1, rs2):
    return ((rs2 << 20) | (rs1 << 15) | (0 << 12) | (rd << 7) | 0x33)

def encode_ecall():
    return 0x00000073

instructions = [
    encode_lui(10, 42),     # lui a0, 42
    encode_lui(11, 23),     # lui a1, 23
    encode_add(12, 10, 11), # add a2, a0, a1
    encode_lui(17, 93),     # lui a7, 93
    encode_ecall(),         # ecall (sys_exit)
]

kernel_data = bytearray()
for instr in instructions:
    kernel_data.extend(instr.to_bytes(4, 'little'))

with open('simple_test.elf', 'wb') as f:
    # Minimal ELF64 header
    f.write(b'\x7fELF\x02\x01\x01\x00')  # magic + class=64 + little=1
    f.write(b'\x00' * 8)  # version/abi
    f.write(struct.pack('<H', 2))  # type=EXEC
    f.write(struct.pack('<H', 243))  # machine=RISCV
    f.write(struct.pack('<I', 1))  # version
    f.write(struct.pack('<Q', 0x80001000))  # entry=0x80001000 (high address)
    f.write(struct.pack('<Q', 64))  # phoff
    f.write(struct.pack('<Q', 0))  # shoff
    f.write(struct.pack('<I', 0))  # flags
    f.write(struct.pack('<H', 64))  # ehdrsize
    f.write(struct.pack('<H', 56))  # phentsize
    f.write(struct.pack('<H', 1))  # phnum
    f.write(struct.pack('<H', 0))  # shentsize
    f.write(struct.pack('<H', 0))  # shnum
    f.write(struct.pack('<H', 0))  # shstrndx
    
    # Program header (LOAD)
    code_offset = 128  # Start code after ELF + PH
    f.write(struct.pack('<I', 1))  # PT_LOAD
    f.write(struct.pack('<I', 5))  # flags=R+X
    f.write(struct.pack('<Q', code_offset))  # offset
    f.write(struct.pack('<Q', 0x80001000))  # vaddr (high address)
    f.write(struct.pack('<Q', 0x80001000))  # paddr
    f.write(struct.pack('<Q', len(kernel_data)))  # filesz
    f.write(struct.pack('<Q', len(kernel_data)))  # memsz
    f.write(struct.pack('<Q', 0x1000))  # align
    
    # Padding to end of PH
    f.write(b'\x00' * (code_offset - 64 - 56))
    
    # Write kernel data
    f.write(kernel_data)

print(f"Created simple_test.elf")
print(f"  Size: {len(kernel_data)} bytes ({len(kernel_data)//4} instructions)")
print(f"  Entry: 0x1000")
print("\nInstructions:")
for i, instr in enumerate(instructions):
    print(f"  0x{0x1000 + i*4:04x}: 0x{instr:08x}")