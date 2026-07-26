struct RegisterFile {
    x: array<u32, 32>,
};

struct CPUState {
    pc: u32,
    halted: u32,
};

@group(0) @binding(0) var<storage, read_write> memory: array<u32>;
@group(0) @binding(1) var<storage, read_write> registers: RegisterFile;
@group(0) @binding(2) var<storage, read_write> state: CPUState;

fn fetch() -> u32 {
    // TODO: Hilbert curve mapping pixel read
    return memory[state.pc / 4u];
}

fn sign_extend_12(imm: u32) -> u32 {
    if ((imm & 0x800u) != 0u) {
        return imm | 0xFFFFF000u;
    }
    return imm;
}

fn sign_extend_13(imm: u32) -> u32 {
    if ((imm & 0x1000u) != 0u) {
        return imm | 0xFFFFE000u;
    }
    return imm;
}

fn sign_extend_21(imm: u32) -> u32 {
    if ((imm & 0x100000u) != 0u) {
        return imm | 0xFFE00000u;
    }
    return imm;
}

fn decode_and_execute(instr: u32) {
    let opcode = instr & 0x7Fu;
    let rd = (instr >> 7u) & 0x1Fu;
    let funct3 = (instr >> 12u) & 0x7u;
    let rs1 = (instr >> 15u) & 0x1Fu;
    let rs2 = (instr >> 20u) & 0x1Fu;
    let funct7 = (instr >> 25u) & 0x7Fu;
    
    // x0 is always zero
    registers.x[0] = 0u;
    
    var rs1_val = registers.x[rs1];
    var rs2_val = registers.x[rs2];
    
    var next_pc = state.pc + 4u;
    var valid = true;
    
    if (opcode == 0x13u) {
        // I-type ALU (addi, andi, ori, xori)
        let imm = sign_extend_12(instr >> 20u);
        var result = 0u;
        if (funct3 == 0u) {
            result = rs1_val + imm; // addi
        } else if (funct3 == 4u) {
            result = rs1_val ^ imm; // xori
        } else if (funct3 == 6u) {
            result = rs1_val | imm; // ori
        } else if (funct3 == 7u) {
            result = rs1_val & imm; // andi
        } else {
            valid = false;
        }
        if (valid && rd != 0u) { registers.x[rd] = result; }
        
    } else if (opcode == 0x33u) {
        // R-type ALU (add, and, or, xor)
        var result = 0u;
        if (funct3 == 0u && funct7 == 0u) {
            result = rs1_val + rs2_val; // add
        } else if (funct3 == 4u && funct7 == 0u) {
            result = rs1_val ^ rs2_val; // xor
        } else if (funct3 == 6u && funct7 == 0u) {
            result = rs1_val | rs2_val; // or
        } else if (funct3 == 7u && funct7 == 0u) {
            result = rs1_val & rs2_val; // and
        } else {
            valid = false;
        }
        if (valid && rd != 0u) { registers.x[rd] = result; }
        
    } else if (opcode == 0x03u) {
        // Load (lw)
        let imm = sign_extend_12(instr >> 20u);
        let addr = rs1_val + imm;
        if (funct3 == 2u) {
            let val = memory[addr / 4u];
            if (rd != 0u) { registers.x[rd] = val; }
        } else {
            valid = false;
        }
        
    } else if (opcode == 0x23u) {
        // Store (sw)
        let imm5 = (instr >> 7u) & 0x1Fu;
        let imm7 = (instr >> 25u) & 0x7Fu;
        let imm = sign_extend_12((imm7 << 5u) | imm5);
        let addr = rs1_val + imm;
        if (funct3 == 2u) {
            memory[addr / 4u] = rs2_val;
        } else {
            valid = false;
        }
        
    } else if (opcode == 0x6Fu) {
        // jal
        let imm20 = ((instr >> 31u) << 20u) |
                    (((instr >> 12u) & 0xFFu) << 12u) |
                    (((instr >> 20u) & 0x1u) << 11u) |
                    (((instr >> 21u) & 0x3FFu) << 1u);
        let imm = sign_extend_21(imm20);
        if (rd != 0u) { registers.x[rd] = next_pc; }
        next_pc = state.pc + imm;
        
    } else if (opcode == 0x63u) {
        // Branch (beq)
        let imm12 = ((instr >> 31u) << 12u) |
                    (((instr >> 7u) & 0x1u) << 11u) |
                    (((instr >> 25u) & 0x3Fu) << 5u) |
                    (((instr >> 8u) & 0xFu) << 1u);
        let imm = sign_extend_13(imm12);
        if (funct3 == 0u) {
            if (rs1_val == rs2_val) {
                next_pc = state.pc + imm;
            }
        } else {
            valid = false;
        }
        
    } else {
        valid = false;
    }
    
    if (!valid) {
        state.halted = 1u;
    } else {
        state.pc = next_pc;
    }
}

@compute @workgroup_size(1)
fn main(@builtin(global_invocation_id) global_id: vec3<u32>) {
    if (state.halted != 0u) {
        return;
    }
    
    let instr = fetch();
    decode_and_execute(instr);
}
