// Multi-instance RV32I emulator: N fully independent RISC-V machines run
// as N GPU lanes, each with its own private register file and RAM slice -
// zero shared mutable state, zero atomics, zero cross-lane coordination.
// This is deliberately "architecture (B)" from tonight's design
// discussion: many independent guests, not one coordinated SMP guest
// (which would need atomics/CAS/IPI routing - the exact shared-state
// serialization pattern that loses on SIMT hardware). Each lane still
// runs its own sequential fetch-decode-execute loop (still ~1M instr/s
// per lane, same as the single-core emulator - this wins only through
// lane COUNT, not per-lane speed, same as the Collatz benchmark).
//
// Deliberately minimal instruction subset - only what the test program
// (tools/rv32i_assembler.py) actually uses: ADDI, LW, SW, BLT, JAL, ADD,
// ECALL. Not a general RV32I core; extend the opcode switch below before
// running anything else.

struct CPUState {
    pc: u32,
    status: u32,     // 0 = running, 1 = halted (ECALL), 2 = illegal instruction
    regs: array<u32, 32>,
};

@group(0) @binding(0)
var<storage, read_write> vcpus: array<CPUState>;
@group(0) @binding(1)
var<storage, read_write> ram: array<u32>;

// Fixed per-instance memory slice, in words. Each lane's guest_addr 0 maps
// to ram[instance_id * RAM_WORDS_PER_INSTANCE].
const RAM_WORDS_PER_INSTANCE: u32 = 64u;

fn mem_read(instance_id: u32, guest_addr: u32) -> u32 {
    return ram[instance_id * RAM_WORDS_PER_INSTANCE + (guest_addr >> 2u)];
}

fn mem_write(instance_id: u32, guest_addr: u32, val: u32) {
    ram[instance_id * RAM_WORDS_PER_INSTANCE + (guest_addr >> 2u)] = val;
}

fn sign_extend(val: u32, bits: u32) -> u32 {
    let shift = 32u - bits;
    return bitcast<u32>(bitcast<i32>(val << shift) >> shift);
}

@compute @workgroup_size(64)
fn main(@builtin(global_invocation_id) id: vec3<u32>) {
    let instance_id = id.x;
    if (instance_id >= arrayLength(&vcpus)) {
        return;
    }

    var cpu = vcpus[instance_id];
    if (cpu.status != 0u) {
        return;
    }

    let step_budget: u32 = 1000u;
    for (var step = 0u; step < step_budget; step = step + 1u) {
        let instr = mem_read(instance_id, cpu.pc);
        var next_pc = cpu.pc + 4u;

        let opcode = instr & 0x7Fu;
        let rd = (instr >> 7u) & 0x1Fu;
        let funct3 = (instr >> 12u) & 0x7u;
        let rs1 = (instr >> 15u) & 0x1Fu;
        let rs2 = (instr >> 20u) & 0x1Fu;

        let imm_i = sign_extend(instr >> 20u, 12u);
        let imm_s = sign_extend(((instr >> 25u) << 5u) | ((instr >> 7u) & 0x1Fu), 12u);
        let b12 = (instr >> 31u) & 1u;
        let b11 = (instr >> 7u) & 1u;
        let b10_5 = (instr >> 25u) & 0x3Fu;
        let b4_1 = (instr >> 8u) & 0xFu;
        let imm_b = sign_extend((b12 << 12u) | (b11 << 11u) | (b10_5 << 5u) | (b4_1 << 1u), 13u);
        let j20 = (instr >> 31u) & 1u;
        let j19_12 = (instr >> 12u) & 0xFFu;
        let j11 = (instr >> 20u) & 1u;
        let j10_1 = (instr >> 21u) & 0x3FFu;
        let imm_j = sign_extend((j20 << 20u) | (j19_12 << 12u) | (j11 << 11u) | (j10_1 << 1u), 21u);

        let src1 = cpu.regs[rs1];
        let src2 = cpu.regs[rs2];
        var wb_val = 0u;
        var write_rd = false;

        if (opcode == 0x13u && funct3 == 0x0u) {           // ADDI
            wb_val = bitcast<u32>(bitcast<i32>(src1) + bitcast<i32>(imm_i));
            write_rd = true;
        } else if (opcode == 0x03u && funct3 == 0x2u) {     // LW
            let addr = bitcast<u32>(bitcast<i32>(src1) + bitcast<i32>(imm_i));
            wb_val = mem_read(instance_id, addr);
            write_rd = true;
        } else if (opcode == 0x23u && funct3 == 0x2u) {     // SW
            let addr = bitcast<u32>(bitcast<i32>(src1) + bitcast<i32>(imm_s));
            mem_write(instance_id, addr, src2);
        } else if (opcode == 0x63u && funct3 == 0x4u) {     // BLT
            if (bitcast<i32>(src1) < bitcast<i32>(src2)) {
                next_pc = bitcast<u32>(bitcast<i32>(cpu.pc) + bitcast<i32>(imm_b));
            }
        } else if (opcode == 0x63u && funct3 == 0x5u) {     // BGE
            if (bitcast<i32>(src1) >= bitcast<i32>(src2)) {
                next_pc = bitcast<u32>(bitcast<i32>(cpu.pc) + bitcast<i32>(imm_b));
            }
        } else if (opcode == 0x6Fu) {                        // JAL
            wb_val = cpu.pc + 4u;
            write_rd = true;
            next_pc = bitcast<u32>(bitcast<i32>(cpu.pc) + bitcast<i32>(imm_j));
        } else if (opcode == 0x33u && funct3 == 0x0u) {     // ADD
            wb_val = bitcast<u32>(bitcast<i32>(src1) + bitcast<i32>(src2));
            write_rd = true;
        } else if (opcode == 0x73u) {                        // ECALL
            cpu.status = 1u;
            step = step_budget;
            continue;
        } else {
            cpu.status = 2u; // illegal instruction
            step = step_budget;
            continue;
        }

        if (write_rd && rd != 0u) {
            cpu.regs[rd] = wb_val;
        }
        cpu.pc = next_pc;
        cpu.regs[0] = 0u;
    }

    vcpus[instance_id] = cpu;
}
