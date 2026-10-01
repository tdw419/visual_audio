// Basic-block-threaded RV32I execution: the SAME machine code bytes as
// multi_instance_rv32i.wgsl (tools/rv32i_assembler.py's sum-1-to-N
// program, independently verified against objdump) are decoded ONCE on
// the host into DecodedOp - no bitfields, no sign-extension math, branch
// targets pre-resolved to op-indices - and uploaded as a single shared,
// READ-ONLY buffer every lane executes against. This isolates exactly
// one variable versus the interpreted baseline: runtime decode vs.
// precomputed ops, with identical register/memory semantics otherwise.
// Removes the fetch/decode chain multi_instance_rv32i.wgsl's decode-tax
// baseline measured at 31-46x overhead per instruction versus native
// compute. Sharing the ops buffer read-only across lanes reintroduces
// none of the shared-*mutable*-state cost that made true multi-hart SMP
// the wrong design - nothing here ever writes to it.
struct DecodedOp {
    op: u32,    // 0=ADDI 1=LW 2=SW 3=BLT 4=JAL 5=ADD 6=HALT
    rd: u32,
    rs1: u32,
    rs2: u32,
    imm: u32,   // already sign-extended; branch/jump imm is an OP INDEX
};

@group(0) @binding(0)
var<storage, read> program: array<DecodedOp>;
@group(0) @binding(1)
var<storage, read_write> ram: array<u32>; // 2 words/instance: [0]=input N, [1]=output sum

const RAM_WORDS_PER_INSTANCE: u32 = 2u;

@compute @workgroup_size(64)
fn main(@builtin(global_invocation_id) id: vec3<u32>) {
    let idx = id.x;
    if (idx * RAM_WORDS_PER_INSTANCE >= arrayLength(&ram)) {
        return;
    }
    let base = idx * RAM_WORDS_PER_INSTANCE;

    var regs: array<u32, 32>;
    for (var r = 0u; r < 32u; r = r + 1u) {
        regs[r] = 0u;
    }
    var pc: u32 = 0u;

    let step_budget: u32 = 1000u;
    for (var step = 0u; step < step_budget; step = step + 1u) {
        let inst = program[pc];
        var next_pc = pc + 1u;

        switch (inst.op) {
            case 0u: { // ADDI rd = rs1 + imm
                regs[inst.rd] = bitcast<u32>(bitcast<i32>(regs[inst.rs1]) + bitcast<i32>(inst.imm));
            }
            case 1u: { // LW rd = ram[base + (rs1_val + imm)/4]
                let addr = bitcast<u32>(bitcast<i32>(regs[inst.rs1]) + bitcast<i32>(inst.imm));
                regs[inst.rd] = ram[base + (addr >> 2u)];
            }
            case 2u: { // SW ram[base + (rs1_val + imm)/4] = rs2 (encoded in rd field, see host decoder)
                let addr = bitcast<u32>(bitcast<i32>(regs[inst.rs1]) + bitcast<i32>(inst.imm));
                ram[base + (addr >> 2u)] = regs[inst.rd];
            }
            case 3u: { // BLT: if rd < rs1 (registers, not the branch's own rd/rs1 naming - see host decoder), jump to imm (op index)
                if (bitcast<i32>(regs[inst.rd]) < bitcast<i32>(regs[inst.rs1])) {
                    next_pc = inst.imm;
                }
            }
            case 4u: { // JAL: unconditional jump to imm (op index)
                next_pc = inst.imm;
            }
            case 5u: { // ADD rd = rs1 + rs2
                regs[inst.rd] = bitcast<u32>(bitcast<i32>(regs[inst.rs1]) + bitcast<i32>(regs[inst.rs2]));
            }
            default: { // HALT (ECALL)
                step = step_budget;
                continue;
            }
        }
        pc = next_pc;
        regs[0] = 0u;
    }
}
