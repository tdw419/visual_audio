#!/usr/bin/env python3
"""
Python RISC-V Emulator - Reference Implementation for TASK_SE009

This Python emulator implements the same RV32I subset as the WGSL Spatial CPU
(RISCV_CPU.wgsl) to verify perfect synchronization between CPU and GPU.

Architecture:
- 32-bit RISC-V instructions (little-endian)
- 32 general-purpose registers (x0-x31, x0 hardwired to 0)
- Memory: byte-addressable, little-endian words
- Syscalls: sys_write (64), sys_exit (93)
"""

import struct
from typing import List, Callable, Optional, Union


class PythonRISCVEmulator:
    """
    Python reference emulator matching WGSL RISCV_CPU.wgsl behavior
    """

    # Opcode values (matching WGSL constants)
    OP_LUI = 0x37      # 55
    OP_AUIPC = 0x17    # 23
    OP_JAL = 0x6F      # 111
    OP_JALR = 0x67     # 103
    OP_BRANCH = 0x63   # 99
    OP_LOAD = 0x03     # 3
    OP_STORE = 0x23    # 35
    OP_OP_IMM = 0x13   # 19
    OP_OP = 0x33       # 51
    OP_SYSTEM = 0x73   # 115

    def __init__(self, memory: Union[bytes, bytearray]):
        """
        Initialize emulator with memory image

        Args:
            memory: Byte array containing code and data
        """
        # Memory as mutable bytearray
        self.memory = bytearray(memory)

        # Registers (x0 hardwired to 0)
        self.regs = [0] * 32

        # Program counter
        self.pc = 0

        # Running state
        self.running = True

        # Instruction count
        self.instr_count = 0

        # Output buffer (simulating GPU output buffer)
        self.output: List[int] = []
        self.output_ptr = 0

    def fetch_instruction(self) -> int:
        """
        Fetch 32-bit instruction at current PC

        Returns:
            32-bit instruction word (little-endian)
        """
        # Bounds check
        if self.pc >= len(self.memory):
            return 0
        word_bytes = self.memory[self.pc:self.pc+4]
        if len(word_bytes) < 4:
            return 0
        return struct.unpack('<I', word_bytes)[0]

    @staticmethod
    def sign_extend_12(imm: int) -> int:
        """Sign-extend 12-bit immediate to 32-bit"""
        if imm & 0x800:
            return imm | 0xFFFFF000
        return imm

    @staticmethod
    def sign_extend_20(imm: int) -> int:
        """Sign-extend 20-bit immediate to 32-bit"""
        if imm & 0x80000:
            return imm | 0xFFF00000
        return imm

    @staticmethod
    def sign_extend_21(imm: int) -> int:
        """Sign-extend 21-bit immediate (for JAL) to 32-bit"""
        if imm & 0x100000:
            return imm | 0xFFE00000
        return imm

    def decode_r_type(self, instr: int) -> tuple:
        """Decode R-type instruction fields"""
        funct7 = (instr >> 25) & 0x7F
        rs2 = (instr >> 20) & 0x1F
        rs1 = (instr >> 15) & 0x1F
        funct3 = (instr >> 12) & 0x7
        rd = (instr >> 7) & 0x1F
        opcode = instr & 0x7F
        return (funct7, rs2, rs1, funct3, rd, opcode)

    def decode_i_type(self, instr: int) -> tuple:
        """Decode I-type instruction fields"""
        imm_raw = (instr >> 20) & 0xFFF
        imm = self.sign_extend_12(imm_raw)
        rs1 = (instr >> 15) & 0x1F
        funct3 = (instr >> 12) & 0x7
        rd = (instr >> 7) & 0x1F
        opcode = instr & 0x7F
        return (imm, rs1, funct3, rd, opcode)

    def decode_s_type(self, instr: int) -> tuple:
        """Decode S-type instruction fields"""
        imm_11_5 = (instr >> 25) & 0x7F
        imm_4_0 = (instr >> 7) & 0x1F
        imm = self.sign_extend_12((imm_11_5 << 5) | imm_4_0)
        rs2 = (instr >> 20) & 0x1F
        rs1 = (instr >> 15) & 0x1F
        funct3 = (instr >> 12) & 0x7
        opcode = instr & 0x7F
        return (imm, rs2, rs1, funct3, opcode)

    def decode_b_type(self, instr: int) -> tuple:
        """Decode B-type instruction fields"""
        imm_12 = (instr >> 31) & 0x1
        imm_10_5 = (instr >> 25) & 0x3F
        imm_4_1 = (instr >> 8) & 0xF
        imm_11 = (instr >> 7) & 0x1
        imm = self.sign_extend_12(
            (imm_12 << 12) | (imm_11 << 11) | (imm_10_5 << 5) | (imm_4_1 << 1)
        )
        rs2 = (instr >> 20) & 0x1F
        rs1 = (instr >> 15) & 0x1F
        funct3 = (instr >> 12) & 0x7
        opcode = instr & 0x7F
        return (imm, rs2, rs1, funct3, opcode)

    def decode_j_type(self, instr: int) -> tuple:
        """Decode J-type instruction fields"""
        imm_20 = (instr >> 31) & 0x1
        imm_10_1 = (instr >> 21) & 0x3FF
        imm_11 = (instr >> 20) & 0x1
        imm_19_12 = (instr >> 12) & 0xFF
        imm = self.sign_extend_21(
            (imm_20 << 20) | (imm_19_12 << 12) | (imm_11 << 11) | (imm_10_1 << 1)
        )
        rd = (instr >> 7) & 0x1F
        opcode = instr & 0x7F
        return (imm, rd, opcode)

    def execute_lui(self, instr: int):
        """LUI: Load Upper Immediate - rd = imm[31:12] << 12"""
        imm = (instr >> 12) & 0xFFFFF
        rd = (instr >> 7) & 0x1F
        if rd != 0:
            self.regs[rd] = imm << 12
        self.pc += 4

    def execute_addi(self, instr: int):
        """ADDI: Add Immediate - rd = rs1 + imm"""
        decoded = self.decode_i_type(instr)
        if decoded[3] != 0:  # rd != 0
            self.regs[decoded[3]] = self.regs[decoded[1]] + decoded[0]
        self.pc += 4

    def execute_jal(self, instr: int):
        """JAL: Jump and Link - PC += imm, rd = PC+4"""
        decoded = self.decode_j_type(instr)
        if decoded[1] != 0:  # rd != 0
            self.regs[decoded[1]] = self.pc + 4
        self.pc += decoded[0]

    def execute_jalr(self, instr: int):
        """JALR: Jump and Link Register - PC = (rs1 + imm) & ~1"""
        decoded = self.decode_i_type(instr)
        if decoded[3] != 0:  # rd != 0
            self.regs[decoded[3]] = self.pc + 4
        self.pc = (self.regs[decoded[1]] + decoded[0]) & 0xFFFFFFFE

    def execute_branch(self, instr: int):
        """Execute branch instructions (BEQ, BNE, BLT, BGE, BLTU, BGEU)"""
        decoded = self.decode_b_type(instr)
        imm = decoded[0]
        rs1_val = self.regs[decoded[2]]
        rs2_val = self.regs[decoded[1]]
        funct3 = decoded[3]

        take_branch = False

        if funct3 == 0x0:  # BEQ
            take_branch = (rs1_val == rs2_val)
        elif funct3 == 0x1:  # BNE
            take_branch = (rs1_val != rs2_val)
        elif funct3 == 0x4:  # BLT (signed)
            take_branch = (rs1_val < rs2_val)
        elif funct3 == 0x5:  # BGE (signed)
            take_branch = (rs1_val >= rs2_val)
        elif funct3 == 0x6:  # BLTU
            take_branch = (rs1_val < rs2_val)
        elif funct3 == 0x7:  # BGEU
            take_branch = (rs1_val >= rs2_val)

        if take_branch:
            self.pc += imm
        else:
            self.pc += 4

    def execute_add(self, instr: int):
        """ADD: Register addition - rd = rs1 + rs2"""
        rd = (instr >> 7) & 0x1F
        rs1 = (instr >> 15) & 0x1F
        rs2 = (instr >> 20) & 0x1F
        if rd != 0:
            self.regs[rd] = self.regs[rs1] + self.regs[rs2]
        self.pc += 4

    def execute_load(self, instr: int):
        """Execute load instructions (LB, LH, LW, LBU, LHU)"""
        decoded = self.decode_i_type(instr)
        addr = self.regs[decoded[1]] + decoded[0]
        byte_offset = addr & 0x3
        word_addr = addr & ~0x3

        # Read word from memory (little-endian)
        word_bytes = self.memory[word_addr:word_addr+4]
        word = struct.unpack('<I', word_bytes.ljust(4, b'\x00'))[0]

        value = 0

        if decoded[2] == 0x0:  # LB - Load Byte (sign-extended)
            byte_val = (word >> (byte_offset * 8)) & 0xFF
            if byte_val & 0x80:
                value = byte_val | 0xFFFFFF00
            else:
                value = byte_val
        elif decoded[2] == 0x1:  # LH - Load Halfword (sign-extended)
            half_val = (word >> (byte_offset * 8)) & 0xFFFF
            if half_val & 0x8000:
                value = half_val | 0xFFFF0000
            else:
                value = half_val
        elif decoded[2] == 0x2:  # LW - Load Word
            value = word
        elif decoded[2] == 0x4:  # LBU - Load Byte Unsigned
            value = (word >> (byte_offset * 8)) & 0xFF
        elif decoded[2] == 0x5:  # LHU - Load Halfword Unsigned
            value = (word >> (byte_offset * 8)) & 0xFFFF

        if decoded[3] != 0:  # rd != 0
            self.regs[decoded[3]] = value

        self.pc += 4

    def execute_store(self, instr: int):
        """Execute store instructions (SB, SH, SW)"""
        decoded = self.decode_s_type(instr)
        addr = self.regs[decoded[2]] + decoded[0]
        byte_offset = addr & 0x3
        word_addr = addr & ~0x3
        store_val = self.regs[decoded[1]]

        # Read current word
        word_bytes = self.memory[word_addr:word_addr+4]
        old_word = struct.unpack('<I', word_bytes.ljust(4, b'\x00'))[0]

        new_word = old_word

        if decoded[3] == 0x0:  # SB - Store Byte
            mask = ~(0xFF << (byte_offset * 8))
            new_word = (old_word & mask) | ((store_val & 0xFF) << (byte_offset * 8))
        elif decoded[3] == 0x1:  # SH - Store Halfword
            mask = ~(0xFFFF << (byte_offset * 8))
            new_word = (old_word & mask) | ((store_val & 0xFFFF) << (byte_offset * 8))
        elif decoded[3] == 0x2:  # SW - Store Word
            new_word = store_val

        # Write back to memory
        self.memory[word_addr:word_addr+4] = struct.pack('<I', new_word)

        self.pc += 4

    def execute_ecall(self):
        """Execute ECALL - environment call (syscall)"""
        syscall_num = self.regs[17]  # a7

        if syscall_num == 64:  # sys_write
            fd = self.regs[10]     # a0
            buf = self.regs[11]    # a1
            count = self.regs[12]  # a2

            if fd == 1:  # stdout
                for i in range(count):
                    byte_val = self.memory[buf + i]
                    self.output.append(byte_val)
                self.output_ptr += count

        elif syscall_num == 93:  # sys_exit
            self.running = False
        else:
            # Unknown syscall - halt
            self.running = False

        self.pc += 4

    def step(self):
        """Execute one instruction (matching WGSL behavior)"""
        # Return early if already halted (WGSL: check running at start of main)
        if not self.running:
            return

        # Don't execute past end of memory
        if self.pc >= len(self.memory):
            self.running = False
            return

        instr = self.fetch_instruction()
        opcode = instr & 0x7F

        if opcode == self.OP_LUI:
            self.execute_lui(instr)
        elif opcode == self.OP_OP_IMM:
            # Check funct3 for ADDI
            funct3 = (instr >> 12) & 0x7
            if funct3 == 0x0:
                self.execute_addi(instr)
            else:
                raise NotImplementedError(f"Unsupported OP_IMM funct3={funct3}")
        elif opcode == self.OP_OP:
            # Check funct3 and funct7 for ADD
            funct3 = (instr >> 12) & 0x7
            funct7 = (instr >> 25) & 0x7F
            if funct3 == 0x0 and funct7 == 0x0:
                self.execute_add(instr)
            else:
                raise NotImplementedError(f"Unsupported OP funct3={funct3}, funct7={funct7}")
        elif opcode == self.OP_JAL:
            self.execute_jal(instr)
        elif opcode == self.OP_JALR:
            self.execute_jalr(instr)
        elif opcode == self.OP_BRANCH:
            self.execute_branch(instr)
        elif opcode == self.OP_LOAD:
            self.execute_load(instr)
        elif opcode == self.OP_STORE:
            self.execute_store(instr)
        elif opcode == self.OP_SYSTEM:
            funct3 = (instr >> 12) & 0x7
            funct12 = instr >> 20
            if funct3 == 0x0 and funct12 == 0x0:
                self.execute_ecall()
            else:
                raise NotImplementedError(f"Unsupported SYSTEM funct3={funct3}, funct12={funct12}")
        else:
            raise NotImplementedError(f"Unknown opcode: {opcode:#x}")

        # Always increment instr_count, even if running was set to False during execution
        # This matches the GPU WGSL behavior which increments at the end of main()
        self.instr_count += 1

    def run(self, max_instructions: int = 1000) -> bytes:
        """
        Run the program until halt or max_instructions reached

        Args:
            max_instructions: Maximum number of instructions to execute

        Returns:
            Output bytes from sys_write calls
        """
        while self.running and self.instr_count < max_instructions:
            self.step()

        return bytes(self.output)

    def get_state(self) -> dict:
        """Get current emulator state"""
        return {
            'pc': self.pc,
            'regs': self.regs.copy(),
            'running': self.running,
            'instr_count': self.instr_count,
            'output_ptr': self.output_ptr,
        }


def test_hello_world():
    """Test Python emulator with Hello World kernel"""
    from create_hello_kernel_correct import create_hello_kernel

    print("=" * 60)
    print("Python RISC-V Emulator - Hello World Test")
    print("=" * 60)

    # Create kernel
    kernel_binary, expected_msg = create_hello_kernel()
    print(f"\nKernel size: {len(kernel_binary)} bytes")
    print(f"Expected output: {expected_msg!r}")

    # Run on Python emulator
    emulator = PythonRISCVEmulator(kernel_binary)
    output = emulator.run(max_instructions=100)

    print(f"\nExecution complete:")
    print(f"  Instructions executed: {emulator.instr_count}")
    print(f"  Final PC: 0x{emulator.pc:04x}")
    print(f"  Running: {emulator.running}")

    print(f"\nFinal register state:")
    print(f"  a0 (x10) = 0x{emulator.regs[10]:08x}")
    print(f"  a1 (x11) = 0x{emulator.regs[11]:08x}")
    print(f"  a2 (x12) = 0x{emulator.regs[12]:08x}")
    print(f"  a7 (x17) = 0x{emulator.regs[17]:08x}")
    print(f"  output_ptr = {emulator.output_ptr}")

    print(f"\nCaptured output: {output.decode('ascii', errors='replace')!r}")

    # Verify
    if output.decode('ascii') == expected_msg:
        print("\n*** PASS *** - Python RISC-V emulator working correctly!")
        return 0
    else:
        print(f"\n*** FAIL *** - Expected {expected_msg!r}")
        return 1


def test_load_store():
    """Test Python emulator with LOAD/STORE instructions"""
    import numpy as np

    print("\n" + "=" * 60)
    print("Python RISC-V Emulator - LOAD/STORE Test")
    print("=" * 60)

    # Encoding helpers
    def encode_lui(rd, imm):
        imm_20 = imm & 0xFFFFF
        return (imm_20 << 12) | (rd << 7) | 0x37

    def encode_addi(rd, rs1, imm):
        imm_12 = imm & 0xFFF
        return (imm_12 << 20) | (rs1 << 15) | (0x0 << 12) | (rd << 7) | 0x13

    def encode_lw(rd, rs1, imm):
        imm_12 = imm & 0xFFF
        return (imm_12 << 20) | (rs1 << 15) | (0x2 << 12) | (rd << 7) | 0x03

    def encode_sw(rs2, rs1, imm):
        imm_11_5 = (imm >> 5) & 0x7F
        imm_4_0 = imm & 0x1F
        return (imm_11_5 << 25) | (rs2 << 20) | (rs1 << 15) | (0x2 << 12) | (imm_4_0 << 7) | 0x23

    def encode_ecall():
        return 0x00000073

    # Create test program
    instructions = [
        encode_lui(11, 0),              # lui a1, 0
        encode_addi(11, 11, 0x40),      # addi a1, a1, 0x40
        encode_lui(10, 0x12345),       # lui a0, 0x12345
        encode_sw(10, 11, 0),           # sw a0, 0(a1)
        encode_lw(12, 11, 0),           # lw a2, 0(a1)
        encode_ecall(),                 # ecall
    ]

    # Build memory image
    memory = bytearray(1024)
    for i, instr in enumerate(instructions):
        offset = i * 4
        memory[offset:offset+4] = instr.to_bytes(4, 'little')

    print("\nProgram:")
    print("  [0] lui a1, 0              -> a1 = 0x00000000")
    print("  [1] addi a1, a1, 0x40     -> a1 = 0x00000040 (data address)")
    print("  [2] lui a0, 0x12345       -> a0 = 0x12345000")
    print("  [3] sw a0, 0(a1)          -> store 0x12345000 at address 0x40")
    print("  [4] lw a2, 0(a1)          -> a2 = [0x40] (should be 0x12345000)")
    print("  [5] ecall                  -> halt")

    # Run on Python emulator
    emulator = PythonRISCVEmulator(memory)
    emulator.run(max_instructions=100)

    print(f"\nFinal state:")
    print(f"  a0 (x10) = 0x{emulator.regs[10]:08x} (expected 0x12345000)")
    print(f"  a1 (x11) = 0x{emulator.regs[11]:08x} (expected 0x00000040)")
    print(f"  a2 (x12) = 0x{emulator.regs[12]:08x} (expected 0x12345000)")

    # Read memory to verify store
    word_bytes = emulator.memory[0x40:0x44]
    stored_word = struct.unpack('<I', word_bytes)[0]
    print(f"  Memory[0x40] = 0x{stored_word:08x} (expected 0x12345000)")

    # Verify
    checks = [
        emulator.regs[10] == 0x12345000,  # a0
        emulator.regs[11] == 0x00000040,  # a1
        emulator.regs[12] == 0x12345000,  # a2
        stored_word == 0x12345000,         # memory[0x40]
    ]

    print(f"\nVerification:")
    if all(checks):
        print("  *** PASS *** - LOAD/STORE working!")
        return 0
    else:
        print("  *** FAIL ***")
        return 1


if __name__ == '__main__':
    import sys
    result1 = test_hello_world()
    result2 = test_load_store()
    sys.exit(max(result1, result2))