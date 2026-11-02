// Basic-block-threaded RV64I execution — the RV64I analog of
// systems/geos_pixel_v5/shaders/basic_block_rv32i.wgsl (see commit f4e49ee): a tiny
// program (sum 1..N) is decoded ONCE on the host into DecodedOp (no bitfields, no
// sign-extension math, branch targets pre-resolved to op-indices) and uploaded as a
// single shared, READ-ONLY buffer every lane executes against. Unlike the RV32I
// version, registers and the accumulator are genuinely 64-bit — WGSL has no native
// i64/u64, so all arithmetic goes through the vec2<u32> (low, high) helpers mirrored
// from tools/SPATIAL_RV64I.wgsl (u64_add/u64_lt/etc.), which is exactly the extra
// per-instruction cost this benchmark is meant to isolate: does removing the runtime
// decode tax still cross 1.0x vs CPU once every op also carries 64-bit-emulation cost?
struct DecodedOp {
    op: u32,    // 0=ADDI 1=LD 2=SD 3=BLT 4=JAL 5=ADD 6=HALT
    rd: u32,
    rs1: u32,
    rs2: u32,
    imm_lo: u32, // pre-sign-extended 64-bit immediate (low); branch/jump imm is an OP INDEX (imm_lo only)
    imm_hi: u32,
};

@group(0) @binding(0)
var<storage, read> program: array<DecodedOp>;
@group(0) @binding(1)
var<storage, read_write> ram: array<vec2<u32>>; // 2 dwords/instance: [0]=input N, [1]=output sum

const RAM_DWORDS_PER_INSTANCE: u32 = 2u;

fn u64_add(a: vec2<u32>, b: vec2<u32>) -> vec2<u32> {
    let low = a.x + b.x;
    let carry = select(0u, 1u, low < a.x);
    let high = a.y + b.y + carry;
    return vec2<u32>(low, high);
}

fn u64_lt(a: vec2<u32>, b: vec2<u32>) -> bool {
    let a_y = bitcast<i32>(a.y);
    let b_y = bitcast<i32>(b.y);
    if (a_y != b_y) {
        return a_y < b_y;
    }
    return a.x < b.x;
}

@compute @workgroup_size(64)
fn main(@builtin(global_invocation_id) id: vec3<u32>) {
    let idx = id.x;
    if (idx * RAM_DWORDS_PER_INSTANCE >= arrayLength(&ram)) {
        return;
    }
    let base = idx * RAM_DWORDS_PER_INSTANCE;

    var regs: array<vec2<u32>, 32>;
    for (var r = 0u; r < 32u; r = r + 1u) {
        regs[r] = vec2<u32>(0u, 0u);
    }
    var pc: u32 = 0u;

    let step_budget: u32 = 1000u;
    for (var step = 0u; step < step_budget; step = step + 1u) {
        let inst = program[pc];
        var next_pc = pc + 1u;
        let imm = vec2<u32>(inst.imm_lo, inst.imm_hi);

        switch (inst.op) {
            case 0u: { // ADDI rd = rs1 + imm
                regs[inst.rd] = u64_add(regs[inst.rs1], imm);
            }
            case 1u: { // LD rd = ram[base + (rs1_val + imm)/8]
                let addr = u64_add(regs[inst.rs1], imm);
                regs[inst.rd] = ram[base + (addr.x >> 3u)];
            }
            case 2u: { // SD ram[base + (rs1_val + imm)/8] = rs2 (encoded in rd field, see host decoder)
                let addr = u64_add(regs[inst.rs1], imm);
                ram[base + (addr.x >> 3u)] = regs[inst.rd];
            }
            case 3u: { // BLT: if rd < rs1 (registers, not the branch's own rd/rs1 naming), jump to imm (op index)
                if (u64_lt(regs[inst.rd], regs[inst.rs1])) {
                    next_pc = imm.x;
                }
            }
            case 4u: { // JAL: unconditional jump to imm (op index)
                next_pc = imm.x;
            }
            case 5u: { // ADD rd = rs1 + rs2
                regs[inst.rd] = u64_add(regs[inst.rs1], regs[inst.rs2]);
            }
            default: { // HALT (ECALL)
                step = step_budget;
                continue;
            }
        }
        pc = next_pc;
        regs[0] = vec2<u32>(0u, 0u);
    }
}
