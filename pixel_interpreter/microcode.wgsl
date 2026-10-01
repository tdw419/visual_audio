@group(0) @binding(0) var memory_in:  texture_2d<u32>;
@group(0) @binding(1) var memory_out: texture_storage_2d<rgba32uint, write>;

// Opcodes (identical to cpu_emulator.py)
const OP_NOP:   u32 = 0u;
const OP_SET:   u32 = 1u;  // Acc = Imm
const OP_ADD:   u32 = 2u;  // Acc = Acc + SrcB
const OP_SUB:   u32 = 3u;  // Acc = Acc - SrcB
const OP_LOAD:  u32 = 4u;  // Acc = Memory[coord] where coord=(src_a, src_b)
const OP_STORE: u32 = 5u;  // Memory[coord] = Acc where coord=(src_a, src_b)
const OP_JMP:   u32 = 6u;  // PC = coord where coord=(src_a, src_b)
const OP_JZ:    u32 = 7u;  // If ZF == 1 then PC = coord where coord=(src_a, src_b)
const OP_HALT:  u32 = 255u;
const OP_CALL:  u32 = 15u; // Stack[SP] = PC; SP++; PC = Imm
const OP_RET:   u32 = 16u; // SP--; PC = Stack[SP]
const OP_SEI:   u32 = 17u; // Set interrupt enable flag = 1
const OP_CLI:   u32 = 18u; // Set interrupt enable flag = 0
const OP_CTX_SAVE: u32 = 19u; // Save PC, Acc, SP, ZF to PCB at (src_a, src_b)
const OP_CTX_LOAD: u32 = 20u; // Load PC, Acc, SP, ZF from PCB at (src_a, src_b)
const OP_POP:    u32 = 23u; // Discard top of stack: SP--
const OP_MUL:   u32 = 14u; // Acc = Acc * SrcB

// Memory locations for interrupt handling
const IRQ_CELL: vec2<i32> = vec2<i32>(4, 0);
const IRQ_PAYLOAD_X: vec2<i32> = vec2<i32>(5, 0);
const IRQ_PAYLOAD_Y: vec2<i32> = vec2<i32>(6, 0);
const IVT_ROW: i32 = 254;

@compute @workgroup_size(1, 1, 1)
fn main(@builtin(global_invocation_id) global_id: vec3<u32>) {
    // State row at y = 0: (0,0)=PC, (1,0)=Acc, (2,0)=Flags, (3,0)=SP
    var pc_state  = textureLoad(memory_in, vec2<i32>(0, 0), 0); // R:pc_x, G:pc_y, B:halt, A:reserved
    var reg_acc   = textureLoad(memory_in, vec2<i32>(1, 0), 0); // R:accumulator
    var reg_flag  = textureLoad(memory_in, vec2<i32>(2, 0), 0); // R:zero_flag
    var reg_sp    = textureLoad(memory_in, vec2<i32>(3, 0), 0); // R:stack pointer

    if (pc_state.b == 1u) { return; } // halt

    // Instruction fetch at PC
    let inst = textureLoad(memory_in, vec2<i32>(i32(pc_state.r), i32(pc_state.g)), 0);
    let opcode = inst.r;
    let src_a  = inst.g;
    let src_b  = inst.b;
    let dst    = inst.a;

    var next_pc = vec2<u32>(pc_state.r + 1u, pc_state.g);
    var write_addr = vec2<i32>(-1, -1);
    var write_val  = vec4<u32>(0u);

    switch (opcode) {
        case OP_SET: {
            reg_acc.r = dst;
        }
        case OP_ADD: {
            reg_acc.r = reg_acc.r + src_b;
            reg_flag.r = select(0u, 1u, reg_acc.r == 0u);
        }
        case OP_SUB: {
            reg_acc.r = reg_acc.r - src_b;
            reg_flag.r = select(0u, 1u, reg_acc.r == 0u);
        }
        case OP_MUL: {
            reg_acc.r = reg_acc.r * src_b;
            reg_flag.r = select(0u, 1u, reg_acc.r == 0u);
        }
        case OP_LOAD: {
            // coord = (src_a, src_b)
            let cell = textureLoad(memory_in, vec2<i32>(i32(src_a), i32(src_b)), 0);
            reg_acc.r = cell.r;
        }
        case OP_STORE: {
            // coord = (src_a, src_b)
            write_addr = vec2<i32>(i32(src_a), i32(src_b));
            write_val = vec4<u32>(reg_acc.r, 0u, 0u, 255u);
        }
        case OP_JMP: {
            // coord = (src_a, src_b)
            next_pc = vec2<u32>(src_a, src_b);
        }
        case OP_JZ: {
            if (reg_flag.r == 1u) {
                // coord = (src_a, src_b)
                next_pc = vec2<u32>(src_a, src_b);
            }
        }
        case OP_CALL: {
            // Push next_pc to stack at row 255
            let stack_x = reg_sp.r % 256u;
            textureStore(memory_out, vec2<i32>(i32(stack_x), 255), vec4<u32>(next_pc.x, next_pc.y, 0u, 255u));
            reg_sp.r = (reg_sp.r + 1u) % 256u;
            // Jump to target
            next_pc = vec2<u32>(src_a, src_b);
        }
        case OP_RET: {
            // Pop PC from stack
            reg_sp.r = (reg_sp.r - 1u + 256u) % 256u;
            let stack_x = reg_sp.r % 256u;
            let ret_addr = textureLoad(memory_in, vec2<i32>(i32(stack_x), 255), 0);
            next_pc = vec2<u32>(ret_addr.r, ret_addr.g);
        }
        case OP_CTX_SAVE: {
            // Peek at PC from stack (don't pop - RET will handle it)
            let peek_sp = (reg_sp.r - 1u + 256u) % 256u;
            let ret_val = textureLoad(memory_in, vec2<i32>(i32(peek_sp), 255), 0);
            let pcb_x = i32(src_a);
            let pcb_y = i32(src_b);
            
            // Save PC (from stack peek)
            textureStore(memory_out, vec2<i32>(pcb_x, pcb_y), vec4<u32>(ret_val.r, ret_val.g, 0u, 255u));
            // Save Accumulator
            textureStore(memory_out, vec2<i32>(pcb_x, pcb_y + 1), vec4<u32>(reg_acc.r, 0u, 0u, 255u));
            // Save SP (current value)
            textureStore(memory_out, vec2<i32>(pcb_x, pcb_y + 2), vec4<u32>(reg_sp.r, 0u, 0u, 255u));
            // Save Zero Flag
            textureStore(memory_out, vec2<i32>(pcb_x, pcb_y + 3), vec4<u32>(reg_flag.r, 0u, 0u, 255u));
        }
        case OP_CTX_LOAD: {
            let pcb_x = i32(src_a);
            let pcb_y = i32(src_b);
            
            // Load PCB values
            let pc_val = textureLoad(memory_in, vec2<i32>(pcb_x, pcb_y), 0);
            let new_acc = textureLoad(memory_in, vec2<i32>(pcb_x, pcb_y + 1), 0);
            let new_sp = textureLoad(memory_in, vec2<i32>(pcb_x, pcb_y + 2), 0);
            let new_zf = textureLoad(memory_in, vec2<i32>(pcb_x, pcb_y + 3), 0);
            
            // Restore registers
            reg_acc.r = new_acc.r;
            reg_sp.r = new_sp.r;
            reg_flag.r = new_zf.r;
            
            // Push the saved PC onto stack for RET to use later
            let stack_x = reg_sp.r % 256u;
            textureStore(memory_out, vec2<i32>(i32(stack_x), 255), vec4<u32>(pc_val.r, pc_val.g, 0u, 255u));
            reg_sp.r = (reg_sp.r + 1u) % 256u;
        }
        case OP_SEI: {
            // Set interrupt enable - handled by external CPU (no action in WGSL)
        }
        case OP_CLI: {
            // Clear interrupt enable - handled by external CPU (no action in WGSL)
        }
        case OP_POP: {
            // Discard top of stack: SP--
            reg_sp.r = (reg_sp.r - 1u + 256u) % 256u;
        }
        case OP_HALT: {
            pc_state.b = 1u;
        }
        default: {}
    }

    pc_state.r = next_pc.x;
    pc_state.g = next_pc.y;
    textureStore(memory_out, vec2<i32>(0, 0), pc_state);
    textureStore(memory_out, vec2<i32>(1, 0), reg_acc);
    textureStore(memory_out, vec2<i32>(2, 0), reg_flag);
    textureStore(memory_out, vec2<i32>(3, 0), reg_sp);
    if (write_addr.x >= 0) { textureStore(memory_out, write_addr, write_val); }
}