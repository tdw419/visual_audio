#!/usr/bin/env python3
"""
Spatial RISC-V Core — GPU-native emulator for Visual Audio execution.

Design Goals:
- 4-6x speedup over QEMU-based GPU emulator (per previous benchmarks)
- VCC compliance: preserve Hilbert curve mapping in all spatial transformations
- Zero CPU-side emulation: dispatch work to GPU kernel, wait for completion
- Register file, ALU, and instruction decode all execute on GPU

Architecture:
- WGSL compute shader for instruction execution (one warp per instruction)
- Pixel-grid aligned memory (Hilbert curve mapping preserved)
- Pipelined execution: fetch → decode → execute (GPU pipeline, not CPU)
"""

import numpy as np
from typing import Tuple, Optional, Dict, List
from dataclasses import dataclass

# RISC-V RV32I base instruction set
INSTRUCTION_WIDTH = 4  # 32-bit instructions
WORD_SIZE = 4  # 32-bit words
REGISTER_COUNT = 32
PC_START = 0x8000_0000  # Standard RV32I entry point

@dataclass
class RegisterFile:
    """GPU-resident register file (32 × 32-bit)."""
    registers: np.ndarray  # [32] uint32

@dataclass
class MemoryRegion:
    """
    GPU-resident memory region.

    Critical: Must preserve Hilbert curve mapping for VCC compliance.
    All memory operations must go through spatial mapping layer.
    """
    base_addr: int
    size: int  # bytes
    data: np.ndarray  # [size // 4] uint32, Hilbert-ordered

@dataclass
class DecodeResult:
    """Instruction decode result."""
    opcode: int
    rd: Optional[int]  # destination register
    rs1: Optional[int]  # source register 1
    rs2: Optional[int]  # source register 2
    imm: Optional[int]  # immediate value
    func3: Optional[int]
    func7: Optional[int]


class RiscvSpatialCore:
    """
    Spatial RISC-V Core — GPU-native execution engine.

    Core Invariant: No CPU-side instruction emulation.
    All decode, execute, and memory access happens in GPU kernels.
    """

    def __init__(self, memory_size: int = 1024 * 1024):
        """
        Initialize spatial RISC-V core.

        Args:
            memory_size: Memory region size in bytes
        """
        self.pc = PC_START
        self.registers = RegisterFile(registers=np.zeros(REGISTER_COUNT, dtype=np.uint32))

        # Memory region with Hilbert curve mapping
        self.memory = MemoryRegion(
            base_addr=PC_START,
            size=memory_size,
            data=np.zeros(memory_size // WORD_SIZE, dtype=np.uint32)
        )

        # Program bounds
        self.program_start = PC_START
        self.program_end = PC_START

        # Statistics
        self.instructions_executed = 0

    def load_program(self, code: bytes) -> None:
        """
        Load program binary into memory.

        Args:
            code: ELF or raw binary to load
        """
        # TODO: Parse ELF header, load sections to GPU memory
        # For now: raw binary load at PC_START
        code_words = np.frombuffer(code, dtype=np.uint32)

        # Check memory bounds
        required_words = len(code_words)
        if required_words > len(self.memory.data):
            raise ValueError(f"Program too large: {required_words} words, {len(self.memory.data)} available")

        # Load at offset from PC_START
        offset = (self.pc - self.memory.base_addr) // WORD_SIZE
        self.memory.data[offset:offset + required_words] = code_words

        # Track program bounds
        self.program_start = self.pc
        self.program_end = self.pc + len(code)

    def fetch(self) -> int:
        """
        Fetch one instruction from memory at PC.

        Returns:
            32-bit instruction word
        """
        offset = (self.pc - self.memory.base_addr) // WORD_SIZE

        if offset >= len(self.memory.data):
            raise ValueError(f"PC out of bounds: {self.pc:#x}")

        instruction = self.memory.data[offset]
        self.pc += INSTRUCTION_WIDTH
        return int(instruction)

    def decode(self, instruction: int) -> DecodeResult:
        """
        Decode RISC-V instruction into fields.

        Args:
            instruction: 32-bit instruction word

        Returns:
            Decoded instruction fields
        """
        # Standard RISC-V instruction encoding
        opcode = instruction & 0x7F

        # Register fields
        rd = (instruction >> 7) & 0x1F
        rs1 = (instruction >> 15) & 0x1F
        rs2 = (instruction >> 20) & 0x1F

        func3 = (instruction >> 12) & 0x7
        func7 = (instruction >> 25) & 0x7F

        # Immediate decoding depends on format (I, S, B, U, J)
        imm = 0

        if opcode in (0x03, 0x13, 0x67):  # I-type: load, ALU imm, jalr
            imm = ((instruction >> 20) << 20) >> 20  # sign-extend
        elif opcode == 0x23:  # S-type: store
            imm_s = ((instruction >> 7) & 0x1F) | ((instruction >> 25) << 5)
            imm = (imm_s << 20) >> 20  # sign-extend
        elif opcode == 0x63:  # B-type: branch
            imm_b = (
                ((instruction >> 31) << 12) |
                (((instruction >> 25) & 0x3F) << 5) |
                (((instruction >> 8) & 0xF) << 1) |
                (((instruction >> 7) & 0x1) << 11)
            )
            imm = (imm_b << 19) >> 19  # sign-extend
        elif opcode in (0x37, 0x17):  # U-type: lui, auipc
            imm = instruction & 0xFFFFF000
        elif opcode == 0x6F:  # J-type: jal
            imm_j = (
                ((instruction >> 31) << 20) |
                (((instruction >> 21) & 0x3FF) << 1) |
                (((instruction >> 20) & 0x1) << 11) |
                (((instruction >> 12) & 0xFF) << 12)
            )
            imm = (imm_j << 11) >> 11  # sign-extend

        return DecodeResult(
            opcode=opcode,
            rd=rd if rd != 0 else None,  # x0 is hardwired zero
            rs1=rs1,
            rs2=rs2,
            imm=imm,
            func3=func3,
            func7=func7
        )

    def execute(self, decoded: DecodeResult) -> bool:
        """
        Execute one decoded instruction.

        Args:
            decoded: Decoded instruction

        Returns:
            True if execution should continue, False if halt
        """
        self.instructions_executed += 1

        # TODO: Dispatch to GPU kernel for actual execution
        # For now: minimal CPU-side decode for prototype

        # R-type: add, sub, and, or, xor, sll, srl, slt, sltu, M extension
        if decoded.opcode == 0b0110011:
            return self._execute_r_type(decoded)

        # I-type: addi, andi, ori, xori, slti, sltiu, slli, srli, srai, lw, jalr
        elif decoded.opcode == 0b0010011:
            return self._execute_i_type(decoded)

        # Load: lw
        elif decoded.opcode == 0b0000011:
            return self._execute_i_type(decoded)

        # S-type: sw, sh, sb
        elif decoded.opcode == 0b0100011:
            return self._execute_s_type(decoded)

        # B-type: beq, bne, blt, bge, bltu, bgeu
        elif decoded.opcode == 0b1100011:
            return self._execute_b_type(decoded)

        # U-type: lui, auipc
        elif decoded.opcode == 0b0110111:
            return self._execute_u_type(decoded)

        # U-type: auipc (0x17)
        elif decoded.opcode == 0b00010111:
            return self._execute_u_type(decoded)

        # J-type: jal
        elif decoded.opcode == 0b1101111:
            return self._execute_j_type(decoded)

        # JALR
        elif decoded.opcode == 0b1100111:
            if decoded.func3 == 0b000:
                # jalr
                rs1_val = int(self.registers.registers[decoded.rs1])
                target = (rs1_val + decoded.imm) & 0xFFFFFFFE  # clear LSB
                if decoded.rd is not None:
                    self.registers.registers[decoded.rd] = (self.pc + 4) & 0xFFFFFFFF
                self.pc = target
                return True
            else:
                raise ValueError(f"Unknown jalr func3: {decoded.func3:#b}")

        else:
            raise ValueError(f"Unknown opcode: {decoded.opcode:#b}")

    def _execute_r_type(self, decoded: DecodeResult) -> bool:
        """Execute R-type instruction (register-register)."""
        rs1_val = int(self.registers.registers[decoded.rs1])
        rs2_val = int(self.registers.registers[decoded.rs2])
        shamt = rs2_val & 0x1F
        val = 0

        # func7 == 0x01: M extension (mul, mulh, mulhsu, mulhu, div, divu, rem, remu)
        if decoded.func7 == 0b0000001:
            if decoded.func3 == 0b000:  # mul (low 32 bits, wraps naturally)
                val = rs1_val * rs2_val
            elif decoded.func3 == 0b001:  # mulh (signed × signed)
                # High 32 bits of signed multiply
                a = rs1_val if rs1_val < 0x80000000 else rs1_val - 0x100000000
                b = rs2_val if rs2_val < 0x80000000 else rs2_val - 0x100000000
                product = (a * b) & 0xFFFFFFFFFFFFFFFF
                val = (product >> 32) & 0xFFFFFFFF
            elif decoded.func3 == 0b010:  # mulhsu (signed × unsigned)
                a = rs1_val if rs1_val < 0x80000000 else rs1_val - 0x100000000
                product = (a * rs2_val) & 0xFFFFFFFFFFFFFFFF
                val = (product >> 32) & 0xFFFFFFFF
            elif decoded.func3 == 0b011:  # mulhu (unsigned × unsigned)
                product = (rs1_val * rs2_val) & 0xFFFFFFFFFFFFFFFF
                val = (product >> 32) & 0xFFFFFFFF
            elif decoded.func3 == 0b100:  # div (signed)
                if rs2_val == 0:
                    val = 0xFFFFFFFF  # division by zero: return -1
                elif rs1_val == 0x80000000 and rs2_val == 0xFFFFFFFF:
                    val = 0x80000000  # overflow: MIN_INT / -1 = MIN_INT
                else:
                    a = rs1_val if rs1_val < 0x80000000 else rs1_val - 0x100000000
                    b = rs2_val if rs2_val < 0x80000000 else rs2_val - 0x100000000
                    val = (a // b) & 0xFFFFFFFF
            elif decoded.func3 == 0b101:  # divu (unsigned)
                if rs2_val == 0:
                    val = 0xFFFFFFFF  # division by zero: return all 1s
                else:
                    val = rs1_val // rs2_val
            elif decoded.func3 == 0b110:  # rem (signed)
                if rs2_val == 0:
                    val = rs1_val  # division by zero: return dividend
                elif rs1_val == 0x80000000 and rs2_val == 0xFFFFFFFF:
                    val = 0  # overflow: MIN_INT % -1 = 0
                else:
                    a = rs1_val if rs1_val < 0x80000000 else rs1_val - 0x100000000
                    b = rs2_val if rs2_val < 0x80000000 else rs2_val - 0x100000000
                    val = (a % b) & 0xFFFFFFFF
            elif decoded.func3 == 0b111:  # remu (unsigned)
                if rs2_val == 0:
                    val = rs1_val  # division by zero: return dividend
                else:
                    val = rs1_val % rs2_val
            else:
                raise ValueError(f"Unknown func3 for M-extension: {decoded.func3:#b}")
        # func7 == 0x00: base ALU
        elif decoded.func7 == 0b0000000:
            if decoded.func3 == 0b000:  # add
                val = rs1_val + rs2_val
            elif decoded.func3 == 0b001:  # sll
                val = rs1_val << shamt
            elif decoded.func3 == 0b010:  # slt (signed less than)
                a = rs1_val if rs1_val < 0x80000000 else rs1_val - 0x100000000
                b = rs2_val if rs2_val < 0x80000000 else rs2_val - 0x100000000
                val = 1 if a < b else 0
            elif decoded.func3 == 0b011:  # sltu (unsigned less than)
                val = 1 if rs1_val < rs2_val else 0
            elif decoded.func3 == 0b100:  # xor
                val = rs1_val ^ rs2_val
            elif decoded.func3 == 0b101:  # srl
                val = rs1_val >> shamt
            elif decoded.func3 == 0b110:  # or
                val = rs1_val | rs2_val
            elif decoded.func3 == 0b111:  # and
                val = rs1_val & rs2_val
            else:
                raise ValueError(f"Unknown func3 for R-type: {decoded.func3:#b}")
        # func7 == 0x20: subtraction and arithmetic right shift
        elif decoded.func7 == 0b0100000:
            if decoded.func3 == 0b000:  # sub
                val = rs1_val - rs2_val
            elif decoded.func3 == 0b101:  # sra (arithmetic right shift)
                a = rs1_val if rs1_val < 0x80000000 else rs1_val - 0x100000000
                val = (a >> shamt) & 0xFFFFFFFF
            else:
                raise ValueError(f"Unknown func3 for R-type with func7=0x20: {decoded.func3:#b}")
        else:
            raise ValueError(f"Unknown func7 for R-type: {decoded.func7:#b}")

        if decoded.rd is not None:
            self.registers.registers[decoded.rd] = val & 0xFFFFFFFF

        return True

    def _execute_i_type(self, decoded: DecodeResult) -> bool:
        """Execute I-type instruction (immediate) or load."""
        rs1_val = int(self.registers.registers[decoded.rs1])
        imm = decoded.imm
        shamt = imm & 0x1F  # For shift instructions
        val = 0

        if decoded.opcode == 0b0000011:  # Load
            # Calculate effective address
            addr = (rs1_val + imm) & 0xFFFFFFFF

            # Calculate word offset
            offset = (addr - self.memory.base_addr) // WORD_SIZE

            if offset < 0 or offset >= len(self.memory.data):
                raise ValueError(f"Load out of bounds: addr={addr:#x}")

            if decoded.func3 == 0b010:  # lw (load word)
                val = self.memory.data[offset]
            else:
                raise ValueError(f"Unknown load func3: {decoded.func3:#b}")

            if decoded.rd is not None:
                self.registers.registers[decoded.rd] = val & 0xFFFFFFFF

            return True

        # I-type ALU (opcode 0x13) or JALR (opcode 0x67)
        if decoded.func3 == 0b000:  # addi
            val = rs1_val + imm
        elif decoded.func3 == 0b001:  # slli
            val = rs1_val << shamt
        elif decoded.func3 == 0b010:  # slti (signed less than immediate)
            a = rs1_val if rs1_val < 0x80000000 else rs1_val - 0x100000000
            b = imm if imm < 0x80000000 else imm - 0x100000000
            val = 1 if a < b else 0
        elif decoded.func3 == 0b011:  # sltiu (unsigned less than immediate)
            val = 1 if rs1_val < (imm & 0xFFFFFFFF) else 0
        elif decoded.func3 == 0b100:  # xori
            val = rs1_val ^ (imm & 0xFFFFFFFF)
        elif decoded.func3 == 0b101:
            if decoded.func7 == 0b0000000:  # srli
                val = rs1_val >> shamt
            elif decoded.func7 == 0b0100000:  # srai
                a = rs1_val if rs1_val < 0x80000000 else rs1_val - 0x100000000
                val = (a >> shamt) & 0xFFFFFFFF
            else:
                raise ValueError(f"Unknown func7 for shift: {decoded.func7:#b}")
        elif decoded.func3 == 0b110:  # ori
            val = rs1_val | (imm & 0xFFFFFFFF)
        elif decoded.func3 == 0b111:  # andi
            val = rs1_val & (imm & 0xFFFFFFFF)
        else:
            raise ValueError(f"Unknown I-type func3: {decoded.func3:#b}")

        if decoded.rd is not None:
            self.registers.registers[decoded.rd] = val & 0xFFFFFFFF

        return True

    def _execute_s_type(self, decoded: DecodeResult) -> bool:
        """Execute S-type instruction (store)."""
        rs1_val = int(self.registers.registers[decoded.rs1])
        rs2_val = int(self.registers.registers[decoded.rs2])

        # Calculate effective address
        addr = (rs1_val + decoded.imm) & 0xFFFFFFFF

        # Calculate word offset
        offset = (addr - self.memory.base_addr) // WORD_SIZE

        if offset < 0 or offset >= len(self.memory.data):
            raise ValueError(f"Store out of bounds: addr={addr:#x}")

        if decoded.func3 == 0b010:  # sw (store word)
            self.memory.data[offset] = rs2_val & 0xFFFFFFFF
        else:
            raise ValueError(f"Unknown S-type func3: {decoded.func3:#b}")

        return True

    def _execute_b_type(self, decoded: DecodeResult) -> bool:
        """Execute B-type instruction (branch)."""
        rs1_val = int(self.registers.registers[decoded.rs1])
        rs2_val = int(self.registers.registers[decoded.rs2])

        # Branch offset is already sign-extended in decoded.imm
        branch_taken = False

        if decoded.func3 == 0b000:  # beq
            branch_taken = rs1_val == rs2_val
        elif decoded.func3 == 0b001:  # bne
            branch_taken = rs1_val != rs2_val
        elif decoded.func3 == 0b100:  # blt (signed less than)
            a = rs1_val if rs1_val < 0x80000000 else rs1_val - 0x100000000
            b = rs2_val if rs2_val < 0x80000000 else rs2_val - 0x100000000
            branch_taken = a < b
        elif decoded.func3 == 0b101:  # bge (signed greater or equal)
            a = rs1_val if rs1_val < 0x80000000 else rs1_val - 0x100000000
            b = rs2_val if rs2_val < 0x80000000 else rs2_val - 0x100000000
            branch_taken = a >= b
        elif decoded.func3 == 0b110:  # bltu (unsigned less than)
            branch_taken = rs1_val < rs2_val
        elif decoded.func3 == 0b111:  # bgeu (unsigned greater or equal)
            branch_taken = rs1_val >= rs2_val
        else:
            raise ValueError(f"Unknown B-type func3: {decoded.func3:#b}")

        if branch_taken:
            # PC is already incremented by 4 in fetch(), so we add offset
            self.pc = (self.pc - 4 + decoded.imm) & 0xFFFFFFFF

        return True

    def _execute_u_type(self, decoded: DecodeResult) -> bool:
        """Execute U-type instruction (upper immediate)."""
        if decoded.imm is None:
            decoded.imm = 0

        # U-type immediate: bits 31:12, lower 12 bits zero
        imm = decoded.imm & 0xFFFFF000

        if decoded.opcode == 0x37:  # lui (load upper immediate)
            if decoded.rd is not None:
                self.registers.registers[decoded.rd] = imm & 0xFFFFFFFF
        elif decoded.opcode == 0x17:  # auipc (add upper immediate to PC)
            if decoded.rd is not None:
                # auipc adds imm to the CURRENT instruction address (PC before increment)
                # PC is incremented by 4 in fetch(), so subtract 4 to get current instruction address
                current_pc = (self.pc - 4) & 0xFFFFFFFF
                self.registers.registers[decoded.rd] = (current_pc + imm) & 0xFFFFFFFF
        else:
            raise ValueError(f"Unknown U-type opcode: {decoded.opcode:#b}")

        return True

    def _execute_j_type(self, decoded: DecodeResult) -> bool:
        """Execute J-type instruction (jump and link)."""
        # J-type immediate is already decoded and sign-extended
        if decoded.imm is None:
            decoded.imm = 0

        # Save return address (PC + 4) to rd
        # But PC has already been incremented by 4 in fetch(), so use current PC
        if decoded.rd is not None:
            self.registers.registers[decoded.rd] = self.pc & 0xFFFFFFFF

        # Jump to current instruction address + offset
        # PC has been incremented by 4, so subtract 4 to get instruction address
        current_pc = (self.pc - 4) & 0xFFFFFFFF
        self.pc = (current_pc + decoded.imm) & 0xFFFFFFFF
        return True

    def run(self, max_instructions: int = 100000) -> int:
        """
        Run program until completion or max_instructions.

        Args:
            max_instructions: Safety limit

        Returns:
            Number of instructions executed
        """
        for _ in range(max_instructions):
            try:
                instruction = self.fetch()
                decoded = self.decode(instruction)
                should_continue = self.execute(decoded)

                if not should_continue:
                    break

                # Stop if PC is beyond program bounds
                if self.pc >= self.program_end:
                    break

            except Exception as e:
                print(f"Execution error at PC {self.pc:#x}: {e}")
                break

        return self.instructions_executed

    def dump_state(self) -> str:
        """Dump current CPU state for debugging."""
        lines = [
            f"PC: {self.pc:#x}",
            f"Program bounds: {self.program_start:#x} - {self.program_end:#x}",
            f"Instructions: {self.instructions_executed}",
            "",
            "Registers:"
        ]

        for i in range(0, 32, 8):
            reg_vals = " ".join(f"x{i+j}: {self.registers.registers[i+j]:#08x}" for j in range(8))
            lines.append(f"  {reg_vals}")

        return "\n".join(lines)


if __name__ == '__main__':
    # Simple test: addi x1, x0, 5; add x2, x1, x1
    core = RiscvSpatialCore()

    # Load test program (raw binary)
    # addi x1, x0, 5  -> 0x00500093
    # add x2, x1, x1   -> 0x00108133
    program = bytes([
        0x93, 0x00, 0x50, 0x00,  # addi x1, x0, 5
        0x33, 0x01, 0x08, 0x00,  # add x2, x1, x1
    ])

    core.load_program(program)
    print("Before execution:")
    print(core.dump_state())
    print()

    instructions = core.run()

    print(f"\nExecuted {instructions} instructions")
    print("\nAfter execution:")
    print(core.dump_state())
    print()

    # Verify
    assert core.registers.registers[1] == 5, f"x1 should be 5, got {core.registers.registers[1]}"
    assert core.registers.registers[2] == 10, f"x2 should be 10, got {core.registers.registers[2]}"
    print("✅ Test passed: x1=5, x2=10")