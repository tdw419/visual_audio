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

// Hilbert Curve: Convert distance to (x, y) coordinate
fn hilbert_d2xy(n: u32, d: u32) -> vec2<u32> {
    var rx: u32;
    var ry: u32;
    var t = d;
    var x: u32 = 0u;
    var y: u32 = 0u;
    var s: u32 = 1u;

    while (s < n) {
        rx = (t / 2u) & 1u;
        ry = (t ^ rx) & 1u;

        if (ry == 0u) {
            if (rx == 1u) {
                x = s - 1u - x;
                y = s - 1u - y;
            }
            let temp = x;
            x = y;
            y = temp;
        }

        x = x + s * rx;
        y = y + s * ry;
        t = t / 4u;
        s = s * 2u;
    }

    return vec2<u32>(x, y);
}

// Convert 1D distance (d) to physical 2D index
fn d2idx(d: u32) -> u32 {
    let mem_len = arrayLength(&memory);
    let N = u32(sqrt(f32(mem_len))); 
    let xy = hilbert_d2xy(N, d);
    return xy.y * N + xy.x;
}

fn fetch() -> u32 {
    let d = state.pc / 4u;
    if (d >= arrayLength(&memory)) {
        state.halted = 1u;
        return 0u;
    }
    let idx = d2idx(d);
    return memory[idx];
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
        // I-type ALU (addi, slti, sltiu, xori, ori, andi, slli, srli, srai)
        let imm = sign_extend_12(instr >> 20u);
        let shamt = (instr >> 20u) & 0x1Fu;
        var result = 0u;
        if (funct3 == 0u) {
            result = rs1_val + imm; // addi
        } else if (funct3 == 2u) {
            result = select(0u, 1u, i32(rs1_val) < i32(imm)); // slti
        } else if (funct3 == 3u) {
            result = select(0u, 1u, rs1_val < imm); // sltiu
        } else if (funct3 == 4u) {
            result = rs1_val ^ imm; // xori
        } else if (funct3 == 6u) {
            result = rs1_val | imm; // ori
        } else if (funct3 == 7u) {
            result = rs1_val & imm; // andi
        } else if (funct3 == 1u && funct7 == 0u) {
            result = rs1_val << shamt; // slli
        } else if (funct3 == 5u && funct7 == 0u) {
            result = rs1_val >> shamt; // srli
        } else if (funct3 == 5u && funct7 == 0x20u) {
            result = bitcast<u32>(bitcast<i32>(rs1_val) >> shamt); // srai
        } else {
            valid = false;
        }
        if (valid && rd != 0u) { registers.x[rd] = result; }

    } else if (opcode == 0x33u) {
        // R-type ALU (add, sub, sll, slt, sltu, xor, srl, sra, or, and)
        let shamt = rs2_val & 0x1Fu;
        var result = 0u;
        if (funct3 == 0u && funct7 == 0u) {
            result = rs1_val + rs2_val; // add
        } else if (funct3 == 0u && funct7 == 0x20u) {
            result = rs1_val - rs2_val; // sub
        } else if (funct3 == 1u && funct7 == 0u) {
            result = rs1_val << shamt; // sll
        } else if (funct3 == 2u && funct7 == 0u) {
            result = select(0u, 1u, i32(rs1_val) < i32(rs2_val)); // slt
        } else if (funct3 == 3u && funct7 == 0u) {
            result = select(0u, 1u, rs1_val < rs2_val); // sltu
        } else if (funct3 == 4u && funct7 == 0u) {
            result = rs1_val ^ rs2_val; // xor
        } else if (funct3 == 5u && funct7 == 0u) {
            result = rs1_val >> shamt; // srl
        } else if (funct3 == 5u && funct7 == 0x20u) {
            result = bitcast<u32>(bitcast<i32>(rs1_val) >> shamt); // sra
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
        let d = addr / 4u;
        if (funct3 == 2u) {
            if (d < arrayLength(&memory)) {
                let idx = d2idx(d);
                let val = memory[idx];
                if (rd != 0u) { registers.x[rd] = val; }
            } else {
                valid = false;
            }
        } else {
            valid = false;
        }
        
    } else if (opcode == 0x23u) {
        // Store (sw)
        let imm5 = (instr >> 7u) & 0x1Fu;
        let imm7 = (instr >> 25u) & 0x7Fu;
        let imm = sign_extend_12((imm7 << 5u) | imm5);
        let addr = rs1_val + imm;
        let d = addr / 4u;
        if (funct3 == 2u) {
            if (d < arrayLength(&memory)) {
                let idx = d2idx(d);
                memory[idx] = rs2_val;
            } else {
                valid = false;
            }
        } else {
            valid = false;
        }
        
    } else if (opcode == 0x37u) {
        // lui
        let imm = instr & 0xFFFFF000u;
        if (rd != 0u) { registers.x[rd] = imm; }

    } else if (opcode == 0x17u) {
        // auipc
        let imm = instr & 0xFFFFF000u;
        if (rd != 0u) { registers.x[rd] = state.pc + imm; }

    } else if (opcode == 0x67u) {
        // jalr
        let imm = sign_extend_12(instr >> 20u);
        if (funct3 == 0u) {
            let jump_addr = (rs1_val + imm) & 0xFFFFFFFEu;
            if (rd != 0u) { registers.x[rd] = next_pc; }
            next_pc = jump_addr;
        } else {
            valid = false;
        }

    } else if (opcode == 0x73u) {
        // ecall / ebreak — trap to halt (no OS/trap handler yet)
        valid = false;

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
            if (rs1_val == rs2_val) { next_pc = state.pc + imm; } // beq
        } else if (funct3 == 1u) {
            if (rs1_val != rs2_val) { next_pc = state.pc + imm; } // bne
        } else if (funct3 == 4u) {
            if (i32(rs1_val) < i32(rs2_val)) { next_pc = state.pc + imm; } // blt
        } else if (funct3 == 5u) {
            if (i32(rs1_val) >= i32(rs2_val)) { next_pc = state.pc + imm; } // bge
        } else if (funct3 == 6u) {
            if (rs1_val < rs2_val) { next_pc = state.pc + imm; } // bltu
        } else if (funct3 == 7u) {
            if (rs1_val >= rs2_val) { next_pc = state.pc + imm; } // bgeu
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
