#!/usr/bin/env python3
"""
Corrected RISC-V Hello World kernel generator

Generates hand-encoded RISC-V instructions that print "Hello from RISC-V in MKV!\n"
"""

def create_hello_kernel():
    """Create hand-encoded RISC-V kernel that prints 'Hello from RISC-V in MKV!\n'"""
    msg = b"Hello from RISC-V in MKV!\n"

    # RISC-V RV32I instruction encoding helper
    def encode_lui(rd, imm):
        """LUI: Load Upper Immediate - rd = imm[31:12] << 12"""
        opcode = 0x37
        return ((imm & 0xFFFFF) << 12) | (rd << 7) | opcode

    def encode_addi(rd, rs1, imm):
        """ADDI: Add Immediate - rd = rs1 + imm (sign-extended)"""
        opcode = 0x13
        funct3 = 0
        return ((imm & 0xFFF) << 20) | (rs1 << 15) | (funct3 << 12) | (rd << 7) | opcode

    def encode_ecall():
        """ECALL: Environment Call"""
        return 0x00000073

    # Register numbers (x0-x31)
    X0 = 0   # zero
    X10 = 10 # a0
    X11 = 11 # a1
    X12 = 12 # a2
    X17 = 17 # a7

    # Instructions:
    # 1. lui a1, 0x00100        ; a1 = 0x00100000 (message address)
    # 2. addi a1, a1, 0        ; a1 = 0x00100000
    # 3. addi a0, x0, 1        ; a0 = 1 (fd=stdout)
    # 4. addi a2, x0, 24       ; a2 = 24 (count)
    # 5. addi a7, x0, 64       ; a7 = 64 (sys_write)
    # 6. ecall                 ; syscall
    # 7. addi a0, x0, 0        ; a0 = 0 (exit status)
    # 8. addi a7, x0, 93       ; a7 = 93 (sys_exit)
    # 9. ecall                 ; exit

    instructions = [
        encode_lui(X11, 0x00100),     # lui a1, 0x00100
        encode_addi(X11, X11, 0),     # addi a1, a1, 0
        encode_addi(X10, X0, 1),      # addi a0, x0, 1
        encode_addi(X12, X0, 24),     # addi a2, x0, 24
        encode_addi(X17, X0, 64),     # addi a7, x0, 64
        encode_ecall(),                # ecall
        encode_addi(X10, X0, 0),      # addi a0, x0, 0
        encode_addi(X17, X0, 93),     # addi a7, x0, 93
        encode_ecall(),                # ecall
    ]

    # Convert to little-endian bytes
    code = b''.join([instr.to_bytes(4, 'little') for instr in instructions])

    # Message at address 0x100 (256 bytes)
    code_with_padding = code.ljust(256, b'\x00')

    # Add message
    full_binary = code_with_padding + msg

    # Print debug info
    print("Encoded instructions:")
    print("  lui   a1, 0x00100   -> a1 = 0x00100000")
    print("  addi  a1, a1, 0     -> a1 = 0x00100000")
    print("  addi  a0, x0, 1     -> a0 = 1 (fd=stdout)")
    print("  addi  a2, x0, 24    -> a2 = 24 (count)")
    print("  addi  a7, x0, 64    -> a7 = 64 (sys_write)")
    print("  ecall               -> sys_write(1, 0x00100000, 24)")
    print("  addi  a0, x0, 0     -> a0 = 0 (exit status)")
    print("  addi  a7, x0, 93    -> a7 = 93 (sys_exit)")
    print("  ecall               -> exit(0)")
    print(f"\nMessage at offset 0x100: {msg.decode('ascii')}")

    return full_binary, msg

if __name__ == '__main__':
    import sys
    output_path = sys.argv[1] if len(sys.argv) > 1 else 'hello_kernel.bin'
    kernel_binary, msg = create_hello_kernel()

    with open(output_path, 'wb') as f:
        f.write(kernel_binary)

    print(f"\nCreated: {output_path}")
    print(f"  Total size: {len(kernel_binary)} bytes")
    print(f"  Code size: 256 bytes (including padding)")
    print(f"  Message size: {len(msg)} bytes")
    print(f"  Message: {msg.decode('ascii')}")