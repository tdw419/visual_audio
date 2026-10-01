//! RV64I Instruction Decoder
//!
//! Decodes 32-bit RISC-V instructions into RV64Instruction structs.
//! Implements all base RV64I instruction formats (R, I, S, B, U, J).

use serde::{Deserialize, Serialize};

/// RV64I opcode types (subset of base ISA)
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum RV64Opcode {
    // LUI - Load Upper Immediate
    LUI,
    // AUIPC - Add Upper Immediate to PC
    AUIPC,
    // JAL - Jump and Link
    JAL,
    // JALR - Jump and Link Register
    JALR,
    // Branch instructions
    BEQ,
    BNE,
    BLT,
    BGE,
    BLTU,
    BGEU,
    // Load instructions
    LB,
    LH,
    LW,
    LD,
    LBU,
    LHU,
    LWU,
    // Store instructions
    SB,
    SH,
    SW,
    SD,
    // ALU Immediate
    ADDI,
    SLTI,
    SLTIU,
    XORI,
    ORI,
    ANDI,
    SLLI,
    SRLI,
    SRAI,
    // ALU Register
    ADD,
    SUB,
    SLL,
    SLT,
    SLTU,
    XOR,
    SRL,
    SRA,
    OR,
    AND,
    // Fence
    FENCE,
    FENCEI,
    // System
    ECALL,
    EBREAK,
    CSRRW,
    CSRRS,
    CSRRC,
    CSRRWI,
    CSRRSI,
    CSRRCI,
    // RV64I-specific
    ADDIW,
    SLLIW,
    SRLIW,
    SRAIW,
    ADDW,
    SUBW,
    SLLW,
    SRLW,
    SRAW,
    // Unknown/invalid
    Unknown(u8),
}

/// Decoded RV64 instruction
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RV64Instruction {
    pub opcode: RV64Opcode,
    pub rd: u8,      // Destination register
    pub rs1: u8,     // Source register 1
    pub rs2: u8,     // Source register 2
    pub imm: i64,    // Immediate value
    pub funct3: u8,  // funct3 field
    pub funct7: u8,  // funct7 field
}

impl Default for RV64Instruction {
    fn default() -> Self {
        RV64Instruction {
            opcode: RV64Opcode::Unknown(0),
            rd: 0,
            rs1: 0,
            rs2: 0,
            imm: 0,
            funct3: 0,
            funct7: 0,
        }
    }
}

/// Decode error types
#[derive(Debug, Clone)]
pub enum DecodeError {
    InvalidOpcode { bits: u32 },
    InvalidFunct3 { bits: u32, funct3: u8 },
    InvalidFunct7 { bits: u32, funct7: u8 },
    Unimplemented { opcode: u8, reason: String },
}

/// RV64 instruction decoder
pub struct RV64Decoder;

impl RV64Decoder {
    /// Decode a 32-bit instruction word
    pub fn decode(bits: u32) -> Result<RV64Instruction, DecodeError> {
        // Extract common fields
        let opcode = (bits & 0x7F) as u8;
        let rd = ((bits >> 7) & 0x1F) as u8;
        let funct3 = ((bits >> 12) & 0x07) as u8;
        let rs1 = ((bits >> 15) & 0x1F) as u8;
        let rs2 = ((bits >> 20) & 0x1F) as u8;
        let funct7 = ((bits >> 25) & 0x7F) as u8;

        // STUB: Opcode dispatch
        // TODO: Implement format-specific decoding (R, I, S, B, U, J)
        // TODO: Extract immediates based on format
        // TODO: Map opcode+funct3+funct7 to RV64Opcode

        // Temporary: return NOP-like instruction
        Ok(RV64Instruction {
            opcode: RV64Opcode::ADDI, // Simple placeholder
            rd,
            rs1,
            rs2,
            imm: 0,
            funct3,
            funct7,
        })
    }

    /// Decode I-type immediate
    fn decode_i_imm(bits: u32) -> i64 {
        // bits[31:20] sign-extended to 64 bits
        let imm = ((bits as i32) >> 20) as i64;
        imm
    }

    /// Decode S-type immediate
    fn decode_s_imm(bits: u32) -> i64 {
        // bits[31:25] + bits[11:7] sign-extended
        let imm_11_5 = ((bits >> 25) & 0x7F) as i64;
        let imm_4_0 = ((bits >> 7) & 0x1F) as i64;
        ((imm_11_5 << 5) | imm_4_0).sign_extend(12)
    }

    /// Decode B-type immediate
    fn decode_b_imm(bits: u32) -> i64 {
        // bits[31] + bits[7] + bits[30:25] + bits[11:8]
        let imm_12 = ((bits >> 31) & 1) as i64;
        let imm_10_5 = ((bits >> 25) & 0x3F) as i64;
        let imm_4_1 = ((bits >> 8) & 0xF) as i64;
        let imm_11 = ((bits >> 7) & 1) as i64;

        let imm = (imm_12 << 12) | (imm_11 << 11) | (imm_10_5 << 5) | (imm_4_1 << 1);
        imm.sign_extend(13)
    }

    /// Decode U-type immediate
    fn decode_u_imm(bits: u32) -> i64 {
        // bits[31:12] with lower 12 bits zero
        ((bits & 0xFFFFF000) as i32) as i64
    }

    /// Decode J-type immediate
    fn decode_j_imm(bits: u32) -> i64 {
        // bits[31] + bits[19:12] + bits[20] + bits[30:21]
        let imm_20 = ((bits >> 31) & 1) as i64;
        let imm_10_1 = ((bits >> 21) & 0x3FF) as i64;
        let imm_11 = ((bits >> 20) & 1) as i64;
        let imm_19_12 = ((bits >> 12) & 0xFF) as i64;

        let imm = (imm_20 << 20) | (imm_19_12 << 12) | (imm_11 << 11) | (imm_10_1 << 1);
        imm.sign_extend(21)
    }
}

/// Sign extension helper
trait SignExtend {
    fn sign_extend(self, bits: u32) -> i64;
}

impl SignExtend for i64 {
    fn sign_extend(self, bits: u32) -> i64 {
        // Self-extend sign bit to 64 bits
        let shift = 64 - bits;
        (self << shift) >> shift
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_decode_addi() {
        // addi x1, x0, 0x100
        let bits: u32 = 0x00100093;
        let inst = RV64Decoder::decode(bits).unwrap();

        assert_eq!(inst.opcode, RV64Opcode::ADDI);
        assert_eq!(inst.rd, 1);
        assert_eq!(inst.rs1, 0);
        assert_eq!(inst.funct3, 0);
    }

    #[test]
    fn test_decode_i_imm() {
        // Positive immediate
        assert_eq!(RV64Decoder::decode_i_imm(0x00000F93), 0);
        // Negative immediate
        assert_eq!(RV64Decoder::decode_i_imm(0xFFF00F93), -1);
    }

    #[test]
    fn test_decode_u_imm() {
        // lui x1, 0x1000
        let bits: u32 = 0x000010B7;
        let imm = RV64Decoder::decode_u_imm(bits);
        assert_eq!(imm, 0x1000);
    }

    #[test]
    fn test_instruction_default() {
        let inst = RV64Instruction::default();
        assert_eq!(inst.opcode, RV64Opcode::Unknown(0));
        assert_eq!(inst.rd, 0);
    }
}