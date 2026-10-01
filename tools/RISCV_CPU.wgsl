/*
 * RISCV_CPU.wgsl
 *
 * GPU-Native RISC-V Emulator (RV32I subset) - Phase 5
 *
 * Architecture:
 * - 1 Pixel = 1 32-bit RISC-V instruction (RGBA channels)
 * - Storage buffer = read-write memory (RAM)
 * - Compute shader = CPU (fetch/decode/execute)
 */

// ============================================================================
// DATA STRUCTURES
// ============================================================================

// 32-bit instruction packed into RGBA pixel
struct InstructionPixel {
    r: u32,  // Bits [7:0]
    g: u32,  // Bits [15:8]
    b: u32,  // Bits [23:16]
    a: u32,  // Bits [31:24]
}

// RISC-V CPU State
struct RiscvCPU {
    pc: vec2<u32>,              // Program counter (64-bit)
    regs: array<vec2<u32>, 32>, // x0-x31 (x0 is hardwired to 0)
    running: u32,               // 1 = executing, 0 = halted
    instr_count: u32,           // Instructions executed (debug)
    output_ptr: u32,            // Index to write next byte
}

// R-type instruction decoding
struct RType {
    funct7: u32,
    rs2: u32,
    rs1: u32,
    funct3: u32,
    rd: u32,
    opcode: u32,
}

// I-type instruction decoding
struct IType {
    imm: u32,
    rs1: u32,
    funct3: u32,
    rd: u32,
    opcode: u32,
}

// ============================================================================
// CONSTANTS
// ============================================================================

// Opcode values (RV32I base)
const OP_LUI: u32 = 55u;
const OP_AUIPC: u32 = 23u;
const OP_JAL: u32 = 111u;
const OP_JALR: u32 = 103u;
const OP_BRANCH: u32 = 99u;
const OP_LOAD: u32 = 3u;
const OP_STORE: u32 = 35u;
const OP_OP_IMM: u32 = 19u;
const OP_OP: u32 = 51u;
const OP_SYSTEM: u32 = 115u;

// Funct3 values
const F3_ADDI: u32 = 0u;
const F3_JALR: u32 = 0u;

// ============================================================================
// STORAGE BUFFERS
// ============================================================================

@group(0) @binding(0) var<storage, read_write> memory: array<InstructionPixel>;  // Read-write memory (RAM)
@group(0) @binding(1) var<storage, read_write> cpus: array<RiscvCPU>;    // CPU states
@group(0) @binding(2) var<storage, read_write> output: array<u32>;      // Output buffer (u32 words, 4 bytes each)
@group(0) @binding(3) var<uniform> max_instructions: u32;               // Execution limit

// ============================================================================
// HELPER FUNCTIONS
// ============================================================================

// Convert RGBA pixel to 32-bit instruction (little-endian)
fn pixel_to_instruction(px: InstructionPixel) -> u32 {
    return px.r | (px.g << 8u) | (px.b << 16u) | (px.a << 24u);
}

// Sign-extend 12-bit immediate to 32-bit
fn sign_extend_12(imm: u32) -> u32 {
    if ((imm & 2048u) != 0u) {
        return imm | 4294966272u;
    }
    return imm;
}

// Sign-extend 20-bit immediate to 32-bit
fn sign_extend_20(imm: u32) -> u32 {
    if ((imm & 524288u) != 0u) {
        return imm | 4278190080u;
    }
    return imm;
}

// Sign-extend 21-bit immediate (for JAL) to 32-bit
fn sign_extend_21(imm: u32) -> u32 {
    if ((imm & 1048576u) != 0u) {
        return imm | 4290772992u;
    }
    return imm;
}

// ============================================================================
// 64-BIT MATH HELPERS (RV64I Support)
// ============================================================================

// vec2<u32> represents a 64-bit int: x = low 32 bits, y = high 32 bits.

fn add64(a: vec2<u32>, b: vec2<u32>) -> vec2<u32> {
    let low = a.x + b.x;
    let carry = select(0u, 1u, low < a.x);
    let high = a.y + b.y + carry;
    return vec2<u32>(low, high);
}

fn sub64(a: vec2<u32>, b: vec2<u32>) -> vec2<u32> {
    let low = a.x - b.x;
    let borrow = select(0u, 1u, a.x < b.x);
    let high = a.y - b.y - borrow;
    return vec2<u32>(low, high);
}

// Sign extend a 32-bit value to 64-bit
fn sext32_to_64(val: u32) -> vec2<u32> {
    let is_neg = (val & 2147483648u) != 0u;
    return vec2<u32>(val, select(0u, 4294967295u, is_neg));
}

// ============================================================================
// INSTRUCTION FETCH
// ============================================================================

fn fetch_instruction(pc: vec2<u32>) -> u32 {
    let pixel_idx = pc.x / 4u;
    let px = memory[pixel_idx];
    return pixel_to_instruction(px);
}

// ============================================================================
// INSTRUCTION DECODING
// ============================================================================

fn decode_r_type(instr: u32) -> RType {
    let f7 = (instr >> 25u) & 127u;
    let r2 = (instr >> 20u) & 31u;
    let r1 = (instr >> 15u) & 31u;
    let f3 = (instr >> 12u) & 7u;
    let rd = (instr >> 7u) & 31u;
    let op = instr & 127u;
    return RType(f7, r2, r1, f3, rd, op);
}

fn decode_i_type(instr: u32) -> IType {
    let imm_raw = (instr >> 20u) & 4095u;
    let imm = sign_extend_12(imm_raw);
    let r1 = (instr >> 15u) & 31u;
    let f3 = (instr >> 12u) & 7u;
    let rd = (instr >> 7u) & 31u;
    let op = instr & 127u;
    return IType(imm, r1, f3, rd, op);
}

// ============================================================================
// INSTRUCTION EXECUTION
// ============================================================================

// LUI (Load Upper Immediate)
fn execute_lui(cpu: ptr<function, RiscvCPU>, instr: u32) {
    let imm = (instr >> 12u) & 1048575u;
    let rd = (instr >> 7u) & 31u;
    if (rd != 0u) {
        (*cpu).regs[rd] = sext32_to_64(imm << 12u);
    }
    (*cpu).pc = add64((*cpu).pc, vec2<u32>(4u, 0u));
}

// ADDI (Add Immediate)
fn execute_addi(cpu: ptr<function, RiscvCPU>, instr: u32) {
    let decoded = decode_i_type(instr);
    if (decoded.rd != 0u) {
        (*cpu).regs[decoded.rd] = add64((*cpu).regs[decoded.rs1], sext32_to_64(decoded.imm));
    }
    (*cpu).pc = add64((*cpu).pc, vec2<u32>(4u, 0u));
}

// JAL (Jump and Link)
fn execute_jal(cpu: ptr<function, RiscvCPU>, instr: u32) {
    let imm_20 = (instr >> 31u) & 1u;
    let imm_10_1 = (instr >> 21u) & 1023u;
    let imm_11 = (instr >> 20u) & 1u;
    let imm_19_12 = (instr >> 12u) & 255u;
    let imm = (imm_20 << 20u) | (imm_19_12 << 12u) | (imm_11 << 11u) | (imm_10_1 << 1u);
    let signed_imm = sign_extend_21(imm);
    let rd = (instr >> 7u) & 31u;
    if (rd != 0u) { (*cpu).regs[rd] = add64((*cpu).pc, vec2<u32>(4u, 0u)); }
    (*cpu).pc = add64((*cpu).pc, sext32_to_64(signed_imm));
}

// JALR (Jump and Link Register)
fn execute_jalr(cpu: ptr<function, RiscvCPU>, instr: u32) {
    let decoded = decode_i_type(instr);
    if (decoded.rd != 0u) { (*cpu).regs[decoded.rd] = add64((*cpu).pc, vec2<u32>(4u, 0u)); }
    let target_addr = add64((*cpu).regs[decoded.rs1], sext32_to_64(decoded.imm));
    (*cpu).pc = vec2<u32>(target_addr.x & 4294967294u, target_addr.y);
}

// BRANCH
fn execute_branch(cpu: ptr<function, RiscvCPU>, instr: u32) {
    let imm_12 = (instr >> 31u) & 1u;
    let imm_10_5 = (instr >> 25u) & 63u;
    let imm_4_1 = (instr >> 8u) & 15u;
    let imm_11 = (instr >> 7u) & 1u;
    let imm = (imm_12 << 12u) | (imm_11 << 11u) | (imm_10_5 << 5u) | (imm_4_1 << 1u);
    let signed_imm = sign_extend_12(imm);

    let rs1 = (instr >> 15u) & 31u;
    let rs2 = (instr >> 20u) & 31u;
    let funct3 = (instr >> 12u) & 7u;

    let v1 = (*cpu).regs[rs1];
    let v2 = (*cpu).regs[rs2];

    var take_branch = false;
    if (funct3 == 0u) { take_branch = (v1.x == v2.x && v1.y == v2.y); }       // BEQ
    else if (funct3 == 1u) { take_branch = (v1.x != v2.x || v1.y != v2.y); }  // BNE
    else if (funct3 == 4u) { take_branch = (v1.x < v2.x); }   // BLT (unsigned simplified)
    else if (funct3 == 5u) { take_branch = (v1.x >= v2.x); }  // BGE (unsigned simplified)
    else if (funct3 == 6u) { take_branch = (v1.x < v2.x); }   // BLTU
    else if (funct3 == 7u) { take_branch = (v1.x >= v2.x); }  // BGEU

    if (take_branch) {
        (*cpu).pc = add64((*cpu).pc, sext32_to_64(signed_imm));
    } else {
        (*cpu).pc = add64((*cpu).pc, vec2<u32>(4u, 0u));
    }
}

// ADD (Register)
fn execute_add(cpu: ptr<function, RiscvCPU>, instr: u32) {
    let rd = (instr >> 7u) & 31u;
    let rs1 = (instr >> 15u) & 31u;
    let rs2 = (instr >> 20u) & 31u;

    if (rd != 0u) {
        (*cpu).regs[rd] = add64((*cpu).regs[rs1], (*cpu).regs[rs2]);
    }

    (*cpu).pc = add64((*cpu).pc, vec2<u32>(4u, 0u));
}

// OP_LOAD (LB, LH, LW, LBU, LHU, LD)
fn execute_load(cpu: ptr<function, RiscvCPU>, instr: u32) {
    let decoded = decode_i_type(instr);
    let addr = add64((*cpu).regs[decoded.rs1], sext32_to_64(decoded.imm));
    let byte_offset = addr.x & 3u;
    let word_addr = addr.x / 4u;
    let px = memory[word_addr];
    let word = pixel_to_instruction(px);

    var value = vec2<u32>(0u, 0u);
    var value32 = 0u;

    if (decoded.funct3 == 0u) {
        let byte_val = (word >> (byte_offset * 8u)) & 0xFFu;
        value32 = select(byte_val, byte_val | 0xFFFFFF00u, (byte_val & 0x80u) != 0u);
        value = sext32_to_64(value32);
    } else if (decoded.funct3 == 1u) {
        let half_val = (word >> (byte_offset * 8u)) & 0xFFFFu;
        value32 = select(half_val, half_val | 0xFFFF0000u, (half_val & 0x8000u) != 0u);
        value = sext32_to_64(value32);
    } else if (decoded.funct3 == 2u) {
        value32 = word;
        value = sext32_to_64(value32);
    } else if (decoded.funct3 == 3u) {
        // LD (Load Doubleword)
        value = vec2<u32>(word, 0u); // Stubbed
    } else if (decoded.funct3 == 4u) {
        value32 = (word >> (byte_offset * 8u)) & 0xFFu;
        value = vec2<u32>(value32, 0u);
    } else if (decoded.funct3 == 5u) {
        value32 = (word >> (byte_offset * 8u)) & 0xFFFFu;
        value = vec2<u32>(value32, 0u);
    } else if (decoded.funct3 == 6u) {
        value32 = word;
        value = vec2<u32>(value32, 0u);
    }

    if (decoded.rd != 0u) {
        (*cpu).regs[decoded.rd] = value;
    }

    (*cpu).pc = add64((*cpu).pc, vec2<u32>(4u, 0u));
}

// OP_STORE (SB, SH, SW, SD)
fn execute_store(cpu: ptr<function, RiscvCPU>, instr: u32) {
    let rs1 = (instr >> 15u) & 31u;
    let rs2 = (instr >> 20u) & 31u;
    let funct3 = (instr >> 12u) & 7u;
    let imm_s = ((instr >> 7u) & 31u) | ((instr >> 25u) << 5u);
    let imm = sign_extend_12(imm_s);

    let addr = add64((*cpu).regs[rs1], sext32_to_64(imm));
    let byte_offset = addr.x & 3u;
    let word_addr = addr.x / 4u;
    let px = memory[word_addr];
    let old_word = pixel_to_instruction(px);
    let store_val = (*cpu).regs[rs2].x;

    var new_word = old_word;

    if (funct3 == 0u) {
        let mask = ~(0xFFu << (byte_offset * 8u));
        new_word = (old_word & mask) | ((store_val & 0xFFu) << (byte_offset * 8u));
    } else if (funct3 == 1u) {
        let mask = ~(0xFFFFu << (byte_offset * 8u));
        new_word = (old_word & mask) | ((store_val & 0xFFFFu) << (byte_offset * 8u));
    } else if (funct3 == 2u) {
        new_word = store_val;
    } else if (funct3 == 3u) {
        new_word = store_val;
    }

    memory[word_addr].r = new_word & 0xFFu;
    memory[word_addr].g = (new_word >> 8u) & 0xFFu;
    memory[word_addr].b = (new_word >> 16u) & 0xFFu;
    memory[word_addr].a = (new_word >> 24u) & 0xFFu;

    (*cpu).pc = add64((*cpu).pc, vec2<u32>(4u, 0u));
}

// ECALL Handling
fn read_byte_from_memory(addr: vec2<u32>) -> u32 {
    let word_addr = addr.x / 4u;
    let byte_offset = addr.x % 4u;
    let px = memory[word_addr];
    let word = pixel_to_instruction(px);
    return (word >> (byte_offset * 8u)) & 255u;
}

fn execute_ecall(cpu: ptr<function, RiscvCPU>, cpu_id: u32) {
    let syscall_num = (*cpu).regs[17].x; // a7

    if (syscall_num == 64u) {
        // sys_write
        let fd = (*cpu).regs[10].x;
        let buf = (*cpu).regs[11];
        let count = (*cpu).regs[12].x;

        if (fd == 1u) {
            let base_out = cpu_id * 256u;
            let byte_idx = (*cpu).output_ptr;
            for (var i = 0u; i < count; i = i + 1u) {
                let char_val = read_byte_from_memory(add64(buf, vec2<u32>(i, 0u)));
                let word_idx = (byte_idx + i) / 4u;
                let byte_in_word = (byte_idx + i) % 4u;
                let mask = ~(0xFFu << (byte_in_word * 8u));
                let old_word = output[base_out + word_idx];
                let new_word = (old_word & mask) | (char_val << (byte_in_word * 8u));
                output[base_out + word_idx] = new_word;
            }
            (*cpu).output_ptr = (*cpu).output_ptr + count;
        }
    } else if (syscall_num == 93u) {
        (*cpu).running = 0u;
    } else {
        (*cpu).running = 0u;
    }

    (*cpu).pc = add64((*cpu).pc, vec2<u32>(4u, 0u));
}

// ============================================================================
// MAIN COMPUTE KERNEL
// ============================================================================

@compute @workgroup_size(1)
fn main(@builtin(global_invocation_id) global_id: vec3<u32>) {
    let cpu_id = global_id.x;

    if (cpu_id >= arrayLength(&cpus)) {
        return;
    }

    var cpu = cpus[cpu_id];

    if (cpu.running == 0u) {
        return;
    }

    if (cpu.instr_count >= max_instructions) {
        cpu.running = 0u;
        output[cpu_id * 256u] = 3735928559u;  // Timeout marker
        cpus[cpu_id] = cpu;
        return;
    }

    let instr = fetch_instruction(cpu.pc);
    let opcode = instr & 127u;

    if (opcode == OP_LUI) {
        execute_lui(&cpu, instr);
    } else if (opcode == OP_OP_IMM) {
        let funct3 = (instr >> 12u) & 7u;
        if (funct3 == F3_ADDI) {
            execute_addi(&cpu, instr);
        } else {
            output[cpu_id * 256u] = instr;
            cpu.running = 0u;
        }
    } else if (opcode == OP_OP) {
        let funct3 = (instr >> 12u) & 7u;
        let funct7 = (instr >> 25u) & 127u;
        if (funct3 == 0u && funct7 == 0u) {
            execute_add(&cpu, instr);
        } else {
            output[cpu_id * 256u] = instr;
            cpu.running = 0u;
        }
    } else if (opcode == OP_JAL) {
        execute_jal(&cpu, instr);
    } else if (opcode == OP_JALR) {
        execute_jalr(&cpu, instr);
    } else if (opcode == OP_BRANCH) {
        execute_branch(&cpu, instr);
    } else if (opcode == OP_LOAD) {
        execute_load(&cpu, instr);
    } else if (opcode == OP_STORE) {
        execute_store(&cpu, instr);
    } else if (opcode == OP_SYSTEM) {
        let funct3 = (instr >> 12u) & 7u;
        let funct12 = instr >> 20u;
        if (funct3 == 0u && funct12 == 0u) {
            execute_ecall(&cpu, cpu_id);
        } else {
            cpu.running = 0u;
        }
    } else {
        cpu.running = 0u;
    }

    cpu.instr_count = cpu.instr_count + 1u;
    cpus[cpu_id] = cpu;
}
