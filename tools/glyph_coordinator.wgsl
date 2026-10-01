// glyph_coordinator.wgsl
// GPU-native execution of the Glyph ISA v2 subset needed to run
// spatial_coordinator.glyph (LDI/ADD/SUB/CMP/JMP/JZ/LD/ST/CALL/RET/HALT).
//
// Unlike GlyphCPUv2 (tools/glyph_isa_v2.py), which decodes opcodes from
// RGB pixel colors resolved via wordbase.db, this shader consumes a
// pre-decoded numeric program buffer: the host assembles the .glyph
// source with GlyphAssemblerV2, then re-decodes each instruction's RGB
// back to (opcode_id, rs1, rs2, rd, imm) using a fixed opcode_id table
// (see tools/glyph_wgpu_bridge.py) before upload. Doing the RGB->opcode
// lookup on the GPU would require re-deriving the wordbase-driven color
// table inside WGSL for no benefit — the color encoding only matters for
// the pixel-image storage format, not for execution semantics.
//
// Single execution head (invocation 0) walks the whole program
// sequentially, mirroring the Python interpreter's one-PC-at-a-time
// model. This is not yet a parallel/multi-head design — it exists to
// prove the *same scheduler logic* (round-robin WCB dispatch via
// CALL/RET tick routines) runs correctly under a GPU compute pipeline,
// not to parallelize execution.
//
// Opcode ids (must match OPCODE_ID in tools/glyph_wgpu_bridge.py):
const OP_HALT: u32 = 0u;
const OP_LDI:  u32 = 1u;
const OP_ADD:  u32 = 2u;
const OP_SUB:  u32 = 3u;
const OP_CMP:  u32 = 4u;
const OP_JMP:  u32 = 5u;
const OP_JZ:   u32 = 6u;
const OP_LD:   u32 = 7u;
const OP_ST:   u32 = 8u;
const OP_CALL: u32 = 9u;
const OP_RET:  u32 = 10u;
const OP_JMPR: u32 = 11u;   // JMPR rX  -> pc = registers[rX] (dynamic jump, no return address)
const OP_CALLR: u32 = 12u;  // CALLR rX -> push resume pc, then pc = registers[rX] (dynamic call)

const NUM_REGS: u32 = 32u;
const STACK_BASE: i32 = 250;

// Program: flat array of fixed-shape instructions, one struct per
// instruction (host builds this from the assembled .glyph program —
// see tools/glyph_wgpu_bridge.py). rd/imm are separate fields (unlike
// an earlier draft that packed them into one word — that required
// opcode-dependent bit-unpacking conventions and was a needless source
// of bugs; a plain field per operand is clearer and costs one more i32
// per instruction, which is irrelevant at program sizes in the tens of
// instructions).
struct Instr {
    opcode: i32,
    rs1: i32,
    rs2: i32,
    rd: i32,
    imm: i32,
};

@group(0) @binding(0) var<storage, read> program: array<Instr>;
@group(0) @binding(1) var<storage, read_write> registers: array<i32, 32>;
@group(0) @binding(2) var<storage, read_write> data_memory: array<i32>;   // GlyphCPUv2.memory equivalent (WCB state)
@group(0) @binding(3) var<storage, read_write> call_stack: array<i32>;    // CALL/RET return-address stack
@group(0) @binding(4) var<storage, read_write> debug_out: array<i32>;     // step counter, final pc, halt reason

fn read_reg(idx: i32) -> i32 {
    if (idx < 0 || u32(idx) >= NUM_REGS) {
        return 0;
    }
    return registers[idx];
}

fn write_reg(idx: i32, val: i32) {
    if (idx >= 0 && u32(idx) < NUM_REGS) {
        registers[idx] = val;
    }
}

@compute @workgroup_size(1)
fn main(@builtin(global_invocation_id) global_id: vec3<u32>) {
    if (global_id.x != 0u) {
        return; // single execution head, matching the Python interpreter's model
    }

    var pc: i32 = 0;
    var sp: i32 = STACK_BASE;
    let program_len: i32 = i32(arrayLength(&program));
    let max_steps: i32 = 20000;
    var steps: i32 = 0;
    var halted: bool = false;

    loop {
        if (steps >= max_steps || pc < 0 || pc >= program_len) {
            break;
        }
        let instr = program[pc];
        let opcode = u32(instr.opcode);
        var next_pc = pc + 1;

        if (opcode == OP_HALT) {
            halted = true;
            break;
        } else if (opcode == OP_LDI) {
            write_reg(instr.rd, instr.imm);
        } else if (opcode == OP_ADD) {
            write_reg(instr.rd, read_reg(instr.rd) + read_reg(instr.rs2));
        } else if (opcode == OP_SUB) {
            write_reg(instr.rd, read_reg(instr.rd) - read_reg(instr.rs2));
        } else if (opcode == OP_CMP) {
            if (read_reg(instr.rd) == read_reg(instr.rs2)) {
                write_reg(0, 1);
            } else {
                write_reg(0, 0);
            }
        } else if (opcode == OP_JMP) {
            next_pc = instr.imm;
        } else if (opcode == OP_JZ) {
            if (read_reg(0) != 0) {
                next_pc = instr.imm;
            }
        } else if (opcode == OP_LD) {
            let addr = read_reg(instr.rs2);
            if (addr >= 0 && u32(addr) < arrayLength(&data_memory)) {
                write_reg(instr.rd, data_memory[addr]);
            }
        } else if (opcode == OP_ST) {
            let addr = read_reg(instr.rs1);
            if (addr >= 0 && u32(addr) < arrayLength(&data_memory)) {
                data_memory[addr] = read_reg(instr.rs2);
            }
        } else if (opcode == OP_CALL) {
            sp = sp - 1;
            if (sp >= 0 && u32(sp) < arrayLength(&call_stack)) {
                call_stack[sp] = next_pc;
            }
            next_pc = instr.imm;
        } else if (opcode == OP_RET) {
            if (sp >= 0 && u32(sp) < arrayLength(&call_stack)) {
                next_pc = call_stack[sp];
            }
            sp = sp + 1;
        } else if (opcode == OP_JMPR) {
            // Register holds the linear program index directly (unlike
            // GlyphCPUv2's (row<<16)|col packing for the same opcode —
            // this shader's pc is already linear, so no unpacking needed;
            // the host bridge is responsible for seeding registers with
            // the right representation for whichever executor is used).
            next_pc = read_reg(instr.rd);
        } else if (opcode == OP_CALLR) {
            sp = sp - 1;
            if (sp >= 0 && u32(sp) < arrayLength(&call_stack)) {
                call_stack[sp] = next_pc;
            }
            next_pc = read_reg(instr.rd);
        }

        pc = next_pc;
        steps = steps + 1;
    }

    debug_out[0] = steps;
    debug_out[1] = pc;
    if (halted) {
        debug_out[2] = 1;
    } else {
        debug_out[2] = 0;
    }
}
