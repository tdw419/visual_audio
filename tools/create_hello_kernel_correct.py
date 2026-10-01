#!/usr/bin/env python3
"""
Corrected RISC-V kernel generator with efficient memory layout
"""

import numpy as np

def encode_lui(rd, imm):
    """Encode LUI instruction: lui rd, imm"""
    imm_20 = imm & 0xFFFFF  # 20-bit immediate
    return (imm_20 << 12) | (rd << 7) | 0x37

def encode_addi(rd, rs1, imm):
    """Encode ADDI instruction: addi rd, rs1, imm"""
    imm_12 = imm & 0xFFF  # 12-bit immediate
    return (imm_12 << 20) | (rs1 << 15) | (0x0 << 12) | (rd << 7) | 0x13

def encode_ecall():
    """Encode ECALL instruction: ecall"""
    return 0x00000073

def create_hello_kernel():
    """
    Create hand-encoded RISC-V kernel that prints 'Hello from RISC-V in MKV!\n'

    Efficient memory layout:
    - Instructions: 0x00 - 0x1F (8 instructions * 4 bytes = 32 bytes)
    - Message: 0x20 (32 bytes) onwards
    - Use lui a1, 0 + addi a1, a1, 0x20 to get a1 = 0x00000020
    """
    msg = b"Hello from RISC-V in MKV!\n"

    print('Encoded instructions:')

    # lui a1, 0  (a1 = 0)
    lui_a1 = encode_lui(11, 0)
    print(f'  lui   a1, 0         -> a1 = 0x00000000')

    # addi a1, a1, 0x20  (a1 = 0x00000020 - message address)
    addi_a1_a1_0x20 = encode_addi(11, 11, 0x20)
    print(f'  addi  a1, a1, 0x20  -> a1 = 0x00000020 (message address)')

    # addi a0, x0, 1  (a0 = 1, fd=stdout)
    addi_a0_x0_1 = encode_addi(10, 0, 1)
    print(f'  addi  a0, x0, 1     -> a0 = 1 (fd=stdout)')

    # addi a2, x0, len  (a2 = message length)
    addi_a2_x0_len = encode_addi(12, 0, len(msg))
    print(f'  addi  a2, x0, {len(msg)}    -> a2 = {len(msg)} (count)')

    # addi a7, x0, 64  (a7 = 64, sys_write)
    addi_a7_x0_64 = encode_addi(17, 0, 64)
    print(f'  addi  a7, x0, 64    -> a7 = 64 (sys_write)')

    # ecall  (sys_write(1, 0x00000020, len))
    ecall_1 = encode_ecall()
    print(f'  ecall               -> sys_write(1, 0x00000020, {len(msg)})')

    # addi a0, x0, 0  (a0 = 0, exit status)
    addi_a0_x0_0 = encode_addi(10, 0, 0)
    print(f'  addi  a0, x0, 0     -> a0 = 0 (exit status)')

    # addi a7, x0, 93  (a7 = 93, sys_exit)
    addi_a7_x0_93 = encode_addi(17, 0, 93)
    print(f'  addi  a7, x0, 93    -> a7 = 93 (sys_exit)')

    # ecall  (sys_exit(0))
    ecall_2 = encode_ecall()
    print(f'  ecall               -> exit(0)')

    instructions = [
        lui_a1,
        addi_a1_a1_0x20,
        addi_a0_x0_1,
        addi_a2_x0_len,
        addi_a7_x0_64,
        ecall_1,
        addi_a0_x0_0,
        addi_a7_x0_93,
        ecall_2,
    ]

    # Message right after instructions (offset 32 = 0x20)
    msg_offset = 0x20

    print(f'\nMessage at offset 0x{msg_offset:02x}: {msg.decode("ascii")}')

    # Build binary
    max_addr = max(msg_offset + len(msg), len(instructions) * 4)
    kernel_binary = bytearray(max_addr)

    # Write instructions at PC=0
    for i, instr in enumerate(instructions):
        offset = i * 4
        kernel_binary[offset:offset+4] = instr.to_bytes(4, 'little')

    # Write message at msg_offset
    kernel_binary[msg_offset:msg_offset+len(msg)] = msg

    return bytes(kernel_binary), msg.decode('ascii')

if __name__ == '__main__':
    kernel_binary, expected_msg = create_hello_kernel()

    print(f'\nKernel size: {len(kernel_binary)} bytes')
    print(f'Expected output: {expected_msg}')

    # Verify encodings
    import struct
    for i in range(9):
        offset = i * 4
        word = struct.unpack('<I', kernel_binary[offset:offset+4])[0]
        print(f'  [{offset:3d}] 0x{word:08x}')