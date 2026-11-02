#!/usr/bin/env python3
"""
RISC-V WGSL DSL - Declarative instruction definition framework for GPU emulator.

This DSL lets you define RISC-V instructions declaratively and generates optimized WGSL code.
It aims to make the 400+ opcode implementation more maintainable while preserving GPU performance.
"""

from typing import Callable, Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from enum import Enum


class OpcodeFormat(Enum):
    """RISC-V instruction encoding formats"""
    R_TYPE = "R-type"     # rd, funct3, rs1, rs2, funct7, opcode
    I_TYPE = "I-type"     # rd, funct3, rs1, imm[11:0], opcode  
    S_TYPE = "S-type"     # imm[11:5], rs2, rs1, funct3, imm[4:0], opcode
    B_TYPE = "B-type"     # imm[12|10:5], rs2, rs1, funct3, imm[4:1|11], opcode
    U_TYPE = "U-type"     # imm[31:12], rd, opcode
    J_TYPE = "J-type"     # imm[20|10:1|11|19:12], rd, opcode


@dataclass
class CSRRegister:
    """Control and Status Register definition"""
    name: str
    number: int
    description: str = ""
    width: int = 64  # 32 or 64 bits
    privileges: List[str] = field(default_factory=lambda: ["M"])  # M, S, U


@dataclass
class InstructionDefinition:
    """Complete RISC-V instruction definition"""
    name: str
    opcode: int
    format: OpcodeFormat
    funct3: Optional[int] = None
    funct7: Optional[int] = None
    funct12: Optional[int] = None  # For CSR instructions
    description: str = ""
    implementation: Optional[str] = None  # WGSL implementation code
    decode_logic: Optional[str] = None   # Custom decode logic
    exception_handling: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class WGSLGenerator:
    """Generate WGSL code from instruction definitions"""

    def __init__(self):
        self.instructions: List[InstructionDefinition] = []
        self.csrs: Dict[int, CSRRegister] = {}
        self.helpers: List[str] = []
        
    def add_instruction(self, instruction: InstructionDefinition):
        """Register an instruction definition"""
        self.instructions.append(instruction)
        
    def add_csr(self, csr: CSRRegister):
        """Register a CSR definition"""
        self.csrs[csr.number] = csr
        
    def add_helper(self, wgsl_code: str):
        """Add a WGSL helper function"""
        self.helpers.append(wgsl_code)
        
    def generate_csr_constants(self) -> str:
        """Generate CSR number constants"""
        lines = ["// CSR number constants"]
        for csr in sorted(self.csrs.values(), key=lambda x: x.number):
            lines.append(f"const CSR_{csr.name} = {csr.number:#06x}u;")
        return "\n".join(lines)
        
    def generate_instruction_decoder(self) -> str:
        """Generate the main instruction decode and dispatch logic"""
        cases = []
        
        for instr in self.instructions:
            match_conditions = []
            
            # Base opcode match - check actual opcode bits
            opcode_match = f"(opcode == {instr.opcode:#06x}u)"
            match_conditions.append(opcode_match)
            
            # Format-specific matching
            if instr.format == OpcodeFormat.R_TYPE:
                if instr.funct3 is not None:
                    match_conditions.append(f"(funct3 == {instr.funct3:#x}u)")
                if instr.funct7 is not None:
                    match_conditions.append(f"(funct7 == {instr.funct7:#x}u)")
                    
            elif instr.format in [OpcodeFormat.I_TYPE, OpcodeFormat.S_TYPE, OpcodeFormat.B_TYPE]:
                if instr.funct3 is not None:
                    match_conditions.append(f"(funct3 == {instr.funct3:#x}u)")
                    
            elif instr.format == OpcodeFormat.I_TYPE and instr.funct12 is not None:
                # CSR instruction
                match_conditions.append(f"(funct3 == {instr.funct3:#x}u)")
                match_conditions.append(f"(funct12 == {instr.funct12:#x}u)")
                
            condition = " && ".join(match_conditions)
            cases.append(f"    if ({condition}) {{")
            
            if instr.decode_logic:
                cases.append(f"        // Custom decode: {instr.description}")
                cases.append(f"        {instr.decode_logic}")
            else:
                cases.append(f"        // {instr.description}")
                cases.append(f"        execute_{instr.name.lower()}(rd, rs1, rs2, imm);")
                
            cases.append(f"        return;")
            cases.append(f"    }}")
            
        return "\n".join(cases)
        
    def generate_instruction_implementations(self) -> str:
        """Generate WGSL implementations for all instructions"""
        implementations = []
        
        for instr in self.instructions:
            if instr.implementation:
                impl_code = instr.implementation.format(
                    name=instr.name.lower(),
                    desc=instr.description
                )
                implementations.append(impl_code)
                
        return "\n\n".join(implementations)
        
    def generate_full_shader(self) -> str:
        """Generate complete WGSL shader from all definitions"""
        shader_parts = []
        
        # Header
        shader_parts.append("// Generated by RISC-V WGSL DSL")
        shader_parts.append("// DO NOT EDIT MANUALLY - Use the DSL instead")
        shader_parts.append("")
        
        # CSR constants
        shader_parts.append("// ============================================================================")
        shader_parts.append("// CSR Constants")
        shader_parts.append("// ============================================================================")
        shader_parts.append("")
        shader_parts.append(self.generate_csr_constants())
        shader_parts.append("")
        
        # Helper functions
        shader_parts.append("// ============================================================================")
        shader_parts.append("// Helper Functions")
        shader_parts.append("// ============================================================================")
        shader_parts.append("")
        shader_parts.append("\n".join(self.helpers))
        shader_parts.append("")
        
        # Instruction implementations
        shader_parts.append("// ============================================================================")
        shader_parts.append("// Instruction Implementations")
        shader_parts.append("// ============================================================================")
        shader_parts.append("")
        shader_parts.append(self.generate_instruction_implementations())
        shader_parts.append("")
        
        # Main decoder
        shader_parts.append("// ============================================================================")
        shader_parts.append("// Main Instruction Decoder")
        shader_parts.append("// ============================================================================")
        shader_parts.append("")
        decoder_body = f"""fn decode_and_execute(instr: u32) {{
    let opcode = instr & 0x7Fu;
    let rd = (instr >> 7u) & 0x1Fu;
    let funct3 = (instr >> 12u) & 0x7Fu;
    let rs1 = (instr >> 15u) & 0x1Fu;
    let rs2 = (instr >> 20u) & 0x1Fu;
    let funct7 = (instr >> 25u) & 0x7Fu;
    let funct12 = (instr >> 20u) & 0xFFFu;
    let imm = extract_immediate(instr, opcode);

{self.generate_instruction_decoder()}

    // Illegal instruction - halt
    state.halted = 1u;
}}"""
        
        shader_parts.append(decoder_body)
        
        return "\n".join(shader_parts)


# Example usage with common RISC-V instructions
def create_example_dsl() -> WGSLGenerator:
    """Create a DSL instance with example instruction definitions"""
    
    dsl = WGSLGenerator()
    
    # Define common CSRs
    dsl.add_csr(CSRRegister("MSTATUS", 0x300, "Machine status register"))
    dsl.add_csr(CSRRegister("MTVEC", 0x305, "Machine trap-vector base address"))
    dsl.add_csr(CSRRegister("MEPC", 0x341, "Machine exception program counter"))
    dsl.add_csr(CSRRegister("MCAUSE", 0x342, "Machine trap cause"))
    dsl.add_csr(CSRRegister("SSTATUS", 0x100, "Supervisor status register"))
    dsl.add_csr(CSRRegister("STVEC", 0x105, "Supervisor trap-vector base address"))
    dsl.add_csr(CSRRegister("SEPC", 0x141, "Supervisor exception program counter"))
    dsl.add_csr(CSRRegister("SCAUSE", 0x142, "Supervisor trap cause"))
    
    # ADD instruction (R-type)
    add_impl = """// {desc}
fn execute_{name}(rd: u32, rs1: u32, rs2: u32, imm: vec2<u32>) {{
    let result = u64_add(registers.x[rs1], registers.x[rs2]);
    registers.x[rd] = result;
}}"""
    
    dsl.add_instruction(InstructionDefinition(
        name="ADD",
        opcode=0x33,
        format=OpcodeFormat.R_TYPE,
        funct3=0x0,
        funct7=0x00,
        description="Add rs1 and rs2, store result in rd",
        implementation=add_impl
    ))
    
    # SUB instruction (R-type)
    sub_impl = """// {desc}
fn execute_{name}(rd: u32, rs1: u32, rs2: u32, imm: vec2<u32>) {{
    let result = u64_sub(registers.x[rs1], registers.x[rs2]);
    registers.x[rd] = result;
}}"""
    
    dsl.add_instruction(InstructionDefinition(
        name="SUB",
        opcode=0x33,
        format=OpcodeFormat.R_TYPE,
        funct3=0x0,
        funct7=0x20,
        description="Subtract rs2 from rs1, store result in rd",
        implementation=sub_impl
    ))
    
    # LW instruction (I-type) 
    lw_impl = """// {desc}
fn execute_{name}(rd: u32, rs1: u32, rs2: u32, imm: vec2<u32>) {{
    let addr = u64_add(registers.x[rs1], imm);
    let phys_addr = sv39_translate(addr.x, addr.y, false, false);
    if (phys_addr.y == 1u) {{
        return;
    }}
    let value = read_word(phys_addr.x);
    registers.x[rd] = vec2<u32>(value, sext(value));
}}"""
    
    dsl.add_instruction(InstructionDefinition(
        name="LW",
        opcode=0x03,
        format=OpcodeFormat.I_TYPE,
        funct3=0x2,
        description="Load 32-bit word from memory",
        implementation=lw_impl
    ))
    
    # SW instruction (S-type)
    sw_impl = """// {desc}
fn execute_{name}(rd: u32, rs1: u32, rs2: u32, imm: vec2<u32>) {{
    let addr = u64_add(registers.x[rs1], imm);
    let phys_addr = sv39_translate(addr.x, addr.y, true, false);
    if (phys_addr.y == 1u) {{
        return;
    }}
    write_word(phys_addr.x, registers.x[rs2].x);
}}"""
    
    dsl.add_instruction(InstructionDefinition(
        name="SW",
        opcode=0x23,
        format=OpcodeFormat.S_TYPE,
        funct3=0x2,
        description="Store 32-bit word to memory",
        implementation=sw_impl
    ))
    
    # CSRRW instruction (CSR read/write)
    csrrw_impl = """// {desc}
fn execute_{name}(rd: u32, rs1: u32, rs2: u32, imm: vec2<u32>) {{
    let csr_num = imm.x & 0xFFFu;
    let old_val = read_csr(csr_num);
    write_csr(csr_num, registers.x[rs1]);
    registers.x[rd] = old_val;
}}"""
    
    dsl.add_instruction(InstructionDefinition(
        name="CSRRW",
        opcode=0x73,
        format=OpcodeFormat.I_TYPE,
        funct3=0x1,
        funct12=None,  # CSR is in imm field
        description="Atomic read-write CSR",
        implementation=csrrw_impl
    ))
    
    return dsl


if __name__ == "__main__":
    # Generate example WGSL from DSL
    dsl = create_example_dsl()
    
    print("=== Generated WGSL Shader ===")
    print(dsl.generate_full_shader())
    
    # Show statistics
    print("\n=== DSL Statistics ===")
    print(f"Instructions defined: {len(dsl.instructions)}")
    print(f"CSRs defined: {len(dsl.csrs)}")
    print(f"Helper functions: {len(dsl.helpers)}")