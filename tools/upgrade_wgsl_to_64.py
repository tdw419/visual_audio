import re

with open('tools/RISCV_CPU.wgsl', 'r') as f:
    code = f.read()

# 1. RiscvCPU struct
code = re.sub(
    r'struct RiscvCPU {.*?}',
    '''struct RiscvCPU {
    pc: vec2<u32>,              // Program counter
    regs: array<vec2<u32>, 32>, // x0-x31 (x0 is hardwired to 0)
    running: u32,         // 1 = executing, 0 = halted
    instr_count: u32,     // Instructions executed (debug)
    output_ptr: u32,      // Index to write next byte
}''',
    code, flags=re.DOTALL
)

# 2. fetch_instruction
code = re.sub(
    r'fn fetch_instruction\(pc: u32\) -> u32 {.*?}',
    '''fn fetch_instruction(pc: vec2<u32>) -> u32 {
    let pixel_idx = pc.x / 4u;
    let px = memory[pixel_idx];
    return pixel_to_instruction(px);
}''',
    code, flags=re.DOTALL
)

# 3. execute_lui
code = re.sub(
    r'fn execute_lui.*?\}',
    '''fn execute_lui(cpu: ptr<function, RiscvCPU>, instr: u32) {
    let imm = (instr >> 12u) & 1048575u;
    let rd = (instr >> 7u) & 31u;
    if (rd != 0u) {
        (*cpu).regs[rd] = sext32_to_64(imm << 12u);
    }
    (*cpu).pc = add64((*cpu).pc, vec2<u32>(4u, 0u));
}''',
    code, count=1, flags=re.DOTALL
)

# 4. execute_addi
code = re.sub(
    r'fn execute_addi.*?\}',
    '''fn execute_addi(cpu: ptr<function, RiscvCPU>, instr: u32) {
    let decoded = decode_i_type(instr);
    if (decoded.rd != 0u) {
        (*cpu).regs[decoded.rd] = add64((*cpu).regs[decoded.rs1], sext32_to_64(decoded.imm));
    }
    (*cpu).pc = add64((*cpu).pc, vec2<u32>(4u, 0u));
}''',
    code, count=1, flags=re.DOTALL
)

# 5. execute_jal
code = re.sub(
    r'fn execute_jal\(cpu: ptr<function, RiscvCPU>, instr: u32\) {.*?\}',
    '''fn execute_jal(cpu: ptr<function, RiscvCPU>, instr: u32) {
    let imm_20 = (instr >> 31u) & 1u;
    let imm_10_1 = (instr >> 21u) & 1023u;
    let imm_11 = (instr >> 20u) & 1u;
    let imm_19_12 = (instr >> 12u) & 255u;
    let imm = (imm_20 << 20u) | (imm_19_12 << 12u) | (imm_11 << 11u) | (imm_10_1 << 1u);
    let signed_imm = sign_extend_21(imm);
    let rd = (instr >> 7u) & 31u;
    if (rd != 0u) { (*cpu).regs[rd] = add64((*cpu).pc, vec2<u32>(4u, 0u)); }
    (*cpu).pc = add64((*cpu).pc, sext32_to_64(signed_imm));
}''',
    code, count=1, flags=re.DOTALL
)

# 6. execute_jalr
code = re.sub(
    r'fn execute_jalr\(cpu: ptr<function, RiscvCPU>, instr: u32\) {.*?\}',
    '''fn execute_jalr(cpu: ptr<function, RiscvCPU>, instr: u32) {
    let decoded = decode_i_type(instr);
    if (decoded.rd != 0u) { (*cpu).regs[decoded.rd] = add64((*cpu).pc, vec2<u32>(4u, 0u)); }
    let target_addr = add64((*cpu).regs[decoded.rs1], sext32_to_64(decoded.imm));
    (*cpu).pc = vec2<u32>(target_addr.x & 4294967294u, target_addr.y);
}''',
    code, count=1, flags=re.DOTALL
)

# 7. execute_branch
code = re.sub(
    r'fn execute_branch\(cpu: ptr<function, RiscvCPU>, instr: u32\) {.*?\}',
    '''fn execute_branch(cpu: ptr<function, RiscvCPU>, instr: u32) {
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
    if (funct3 == 0u) { take_branch = (v1.x == v2.x && v1.y == v2.y); }
    else if (funct3 == 1u) { take_branch = (v1.x != v2.x || v1.y != v2.y); }
    else if (funct3 == 4u) { take_branch = (v1.x < v2.x); }
    else if (funct3 == 5u) { take_branch = (v1.x >= v2.x); }
    else if (funct3 == 6u) { take_branch = (v1.x < v2.x); }
    else if (funct3 == 7u) { take_branch = (v1.x >= v2.x); }
    if (take_branch) {
        (*cpu).pc = add64((*cpu).pc, sext32_to_64(signed_imm));
    } else {
        (*cpu).pc = add64((*cpu).pc, vec2<u32>(4u, 0u));
    }
}''',
    code, count=1, flags=re.DOTALL
)

# 8. execute_add
code = re.sub(
    r'fn execute_add\(cpu: ptr<function, RiscvCPU>, instr: u32\) {.*?\}',
    '''fn execute_add(cpu: ptr<function, RiscvCPU>, instr: u32) {
    let rd = (instr >> 7u) & 31u;
    let rs1 = (instr >> 15u) & 31u;
    let rs2 = (instr >> 20u) & 31u;
    if (rd != 0u) {
        (*cpu).regs[rd] = add64((*cpu).regs[rs1], (*cpu).regs[rs2]);
    }
    (*cpu).pc = add64((*cpu).pc, vec2<u32>(4u, 0u));
}''',
    code, count=1, flags=re.DOTALL
)

# 9. execute_load
code = re.sub(
    r'fn execute_load\(cpu: ptr<function, RiscvCPU>, instr: u32\) {.*?\}',
    '''fn execute_load(cpu: ptr<function, RiscvCPU>, instr: u32) {
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
        value = vec2<u32>(word, 0u);
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
}''',
    code, count=1, flags=re.DOTALL
)

# 10. execute_store
code = re.sub(
    r'fn execute_store\(cpu: ptr<function, RiscvCPU>, instr: u32\) {.*?\}',
    '''fn execute_store(cpu: ptr<function, RiscvCPU>, instr: u32) {
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
}''',
    code, count=1, flags=re.DOTALL
)

# 11. execute_ecall
code = re.sub(
    r'fn execute_ecall\(cpu: ptr<function, RiscvCPU>, cpu_id: u32\) {.*?\}',
    '''fn execute_ecall(cpu: ptr<function, RiscvCPU>, cpu_id: u32) {
    let syscall_num = (*cpu).regs[17].x;
    if (syscall_num == 64u) {
        let fd = (*cpu).regs[10].x;
        let buf = (*cpu).regs[11].x;
        let count = (*cpu).regs[12].x;
        if (fd == 1u) {
            let base_out = cpu_id * 256u;
            let byte_idx = (*cpu).output_ptr;
            for (var i = 0u; i < count; i = i + 1u) {
                let char_val = read_byte_from_memory(buf + i);
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
}''',
    code, count=1, flags=re.DOTALL
)

with open('tools/RISCV_CPU.wgsl', 'w') as f:
    f.write(code)

