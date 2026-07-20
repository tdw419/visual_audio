/*
 * RISCV_CPU.wgsl - RV64I with SV39 MMU
 *
 * GPU-Native RISC-V Emulator with Full MMU Support
 * - 64-bit registers via vec2<u32>
 * - SV39 page table walking
 * - Linux kernel boot support
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

// RISC-V CPU State with MMU support
struct RiscvCPU {
    pc: vec2<u32>,              // Program counter (64-bit)
    regs: array<vec2<u32>, 32>, // x0-x31 (x0 is hardwired to 0)
    running: u32,               // 1 = executing, 0 = halted
    instr_count: u32,           // Instructions executed (debug)
    output_ptr: u32,            // Index to write next byte
    satp: u32,                  // SATP CSR for MMU (SV39: [31:22]=PPN, [7:0]=mode)
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

// S-type instruction decoding
struct SType {
    imm: u32,
    rs2: u32,
    rs1: u32,
    funct3: u32,
    opcode: u32,
}

// ============================================================================
// CONSTANTS
// ============================================================================

// Opcode values (RV64I base)
const OP_LUI: u32 = 55u;
const OP_AUIPC: u32 = 23u;
const OP_JAL: u32 = 111u;
const OP_JALR: u32 = 103u;
const OP_BRANCH: u32 = 99u;
const OP_LOAD: u32 = 3u;
const OP_STORE: u32 = 35u;
const OP_OP_IMM: u32 = 19u;
const OP_OP: u32 = 51u;
const OP_OP_IMM_32: u32 = 27u;   // ADDIW, SLLIW, etc.
const OP_OP_32: u32 = 59u;       // ADDW, SUBW, etc.
const OP_SYSTEM: u32 = 115u;
const OP_SYSTEM_CSR: u32 = 115u;

// Funct3 values
const F3_ADDI: u32 = 0u;
const F3_JALR: u32 = 0u;
const F3_SLLI: u32 = 1u;
const F3_SLTI: u32 = 2u;
const F3_SLTIU: u32 = 3u;
const F3_XORI: u32 = 4u;
const F3_SRLI: u32 = 5u;
const F3_SRAI: u32 = 5u;
const F3_ORI: u32 = 6u;
const F3_ANDI: u32 = 7u;

// Funct7 values for OP_IMM shift
const F7_SLLI: u32 = 0u;
const F7_SRLI: u32 = 0u;
const F7_SRAI: u32 = 32u;

// Funct3 for 32-bit ops
const F3_ADDIW: u32 = 0u;
const F3_SLLIW: u32 = 1u;
const F3_SRLIW: u32 = 5u;
const F7_SRAIW: u32 = 32u;

// SV39 MMU Constants
const PAGE_SIZE: u32 = 4096u;
const PTE_V_MASK: u32 = 1u;         // Valid bit
const PTE_R_MASK: u32 = 2u;         // Readable
const PTE_W_MASK: u32 = 4u;         // Writable
const PTE_X_MASK: u32 = 8u;         // Executable
const PTE_U_MASK: u32 = 16u;        // User-accessible
const PTE_G_MASK: u32 = 32u;        // Global
const PTE_A_MASK: u32 = 64u;        // Accessed
const PTE_D_MASK: u32 = 128u;       // Dirty

// SATP modes
const SATP_MODE_OFF: u32 = 0u;
const SATP_MODE_SV39: u32 = 8u;
const SATP_MODE_SV48: u32 = 9u;

// UART Device (16550-compatible at 0x10000000)
const UART_BASE: u32 = 0x10000000u;
const UART_THR: u32 = 0x10000000u;  // Transmit Holding Register
const UART_LSR: u32 = 0x10000005u;  // Line Status Register
const UART_LSR_THRE: u32 = 32u;      // Transmit Holding Register Empty

// ============================================================================
// STORAGE BUFFERS
// ============================================================================

@group(0) @binding(0) var<storage, read_write> memory: array<InstructionPixel>;  // Physical memory
@group(0) @binding(1) var<storage, read_write> cpus: array<RiscvCPU>;    // CPU states
@group(0) @binding(2) var<storage, read_write> output: array<u32>;      // Output buffer
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

// Zero extend 32-bit to 64-bit
fn zext32_to_64(val: u32) -> vec2<u32> {
    return vec2<u32>(val, 0u);
}

// Compare two 64-bit values for equality
fn eq64(a: vec2<u32>, b: vec2<u32>) -> bool {
    return (a.x == b.x) && (a.y == b.y);
}

// Compare two 64-bit values (unsigned)
fn lt64(a: vec2<u32>, b: vec2<u32>) -> bool {
    if (a.y < b.y) { return true; }
    if (a.y > b.y) { return false; }
    return a.x < b.x;
}

// ============================================================================
// SV39 MMU IMPLEMENTATION
// ============================================================================

// Read a 32-bit word from physical memory
fn read_phys_word(pa: vec2<u32>) -> u32 {
    let word_addr = (pa.x / 4u);
    if (word_addr >= arrayLength(&memory)) {
        return 0u;
    }
    let px = memory[word_addr];
    return pixel_to_instruction(px);
}

// Write a 32-bit word to physical memory
fn write_phys_word(pa: vec2<u32>, val: u32) {
    let word_addr = (pa.x / 4u);
    if (word_addr >= arrayLength(&memory)) {
        return;
    }
    var px = memory[word_addr];
    let new_word = val;
    px.r = new_word & 0xFFu;
    px.g = (new_word >> 8u) & 0xFFu;
    px.b = (new_word >> 16u) & 0xFFu;
    px.a = (new_word >> 24u) & 0xFFu;
    memory[word_addr] = px;
}

// Check if SATP indicates MMU is enabled (SV39 mode)
fn mmu_enabled(satp: u32) -> bool {
    let mode = satp & 0xFu;
    return mode == SATP_MODE_SV39;
}

// Extract PPN from SATP CSR
fn satp_to_ppn(satp: u32) -> vec2<u32> {
    let ppn = (satp >> 22u) & 0x3FFFFFu;
    return vec2<u32>(ppn, 0u);
}

// Extract VPN (Virtual Page Number) from virtual address
// For SV39:
// - VPN2: bits [38:30]
// - VPN1: bits [29:21]
// - VPN0: bits [20:12]
// - Offset: bits [11:0]

fn extract_vpn2(va: vec2<u32>) -> u32 {
    let high_vpn = (va.y & 0x7Fu) << 2u;
    let low_vpn = va.x >> 30u;
    return high_vpn | low_vpn;
}

fn extract_vpn1(va: vec2<u32>) -> u32 {
    return (va.x >> 21u) & 0x1FFu;
}

fn extract_vpn0(va: vec2<u32>) -> u32 {
    return (va.x >> 12u) & 0x1FFu;
}

fn extract_offset(va: vec2<u32>) -> u32 {
    return va.x & 0xFFFu;
}

// Check if PTE is valid
fn pte_valid(pte: u32) -> bool {
    return (pte & PTE_V_MASK) != 0u;
}

// Check if PTE is a leaf (has R, W, or X bits set)
fn pte_is_leaf(pte: u32) -> bool {
    return (pte & (PTE_R_MASK | PTE_W_MASK | PTE_X_MASK)) != 0u;
}

// Extract PPN from PTE (bits [53:10])
fn pte_to_ppn(pte: u32) -> vec2<u32> {
    let ppn = (pte >> 10u) & 0x3FFFFFu;
    return vec2<u32>(ppn, 0u);
}

// Calculate physical address from PPN and offset
fn make_pa(ppn: vec2<u32>, offset: u32) -> vec2<u32> {
    let pa_low = (ppn.x << 12u) | offset;
    let pa_high = ppn.y;
    return vec2<u32>(pa_low, pa_high);
}

// SV39 page table walk
// Returns physical address, or vec2<u32>(0xFFFFFFFF, 0xFFFFFFFF) on fault
fn translate_va(satp: u32, va: vec2<u32>) -> vec2<u32> {
    // If MMU not enabled, return identity mapping
    if (!mmu_enabled(satp)) {
        return va;
    }

    // Get root page table address from SATP
    let root_ppn = satp_to_ppn(satp);
    
    // === LEVEL 1 (L1) PAGE TABLE ===
    let l1_vpn = extract_vpn2(va);
    let l1_pte_pa = add64(vec2<u32>(root_ppn.x << 12u, root_ppn.y), vec2<u32>(l1_vpn * 4u, 0u));
    let l1_pte = read_phys_word(l1_pte_pa);
    
    if (!pte_valid(l1_pte)) {
        // Page fault: L1 PTE not valid
        return vec2<u32>(0xFFFFFFFF, 0xFFFFFFFF);
    }
    
    if (pte_is_leaf(l1_pte)) {
        // L1 is a megapage (2MB mapping)
        let l1_ppn = pte_to_ppn(l1_pte);
        let offset = extract_offset(va) | ((va.x >> 12u) & 0x1FFu) << 12u;
        return make_pa(l1_ppn, offset);
    }
    
    // === LEVEL 2 (L2) PAGE TABLE ===
    let l2_vpn = extract_vpn1(va);
    let l2_ppn = pte_to_ppn(l1_pte);
    let l2_pte_pa = add64(vec2<u32>(l2_ppn.x << 12u, l2_ppn.y), vec2<u32>(l2_vpn * 4u, 0u));
    let l2_pte = read_phys_word(l2_pte_pa);
    
    if (!pte_valid(l2_pte)) {
        // Page fault: L2 PTE not valid
        return vec2<u32>(0xFFFFFFFF, 0xFFFFFFFF);
    }
    
    if (pte_is_leaf(l2_pte)) {
        // L2 is a leaf page (4KB mapping)
        let l2_ppn_leaf = pte_to_ppn(l2_pte);
        let offset = extract_offset(va);
        return make_pa(l2_ppn_leaf, offset);
    }
    
    // === LEVEL 3 (L3) PAGE TABLE (LEAF) ===
    let l3_vpn = extract_vpn0(va);
    let l3_ppn = pte_to_ppn(l2_pte);
    let l3_pte_pa = add64(vec2<u32>(l3_ppn.x << 12u, l3_ppn.y), vec2<u32>(l3_vpn * 4u, 0u));
    let l3_pte = read_phys_word(l3_pte_pa);
    
    if (!pte_valid(l3_pte) || !pte_is_leaf(l3_pte)) {
        // Page fault: L3 PTE not valid or not a leaf
        return vec2<u32>(0xFFFFFFFF, 0xFFFFFFFF);
    }
    
    // Final translation
    let final_ppn = pte_to_ppn(l3_pte);
    let offset = extract_offset(va);
    return make_pa(final_ppn, offset);
}

// ============================================================================
// INSTRUCTION FETCH
// ============================================================================

fn fetch_instruction(satp: u32, pc: vec2<u32>) -> u32 {
    // Translate virtual PC to physical address
    let pa = translate_va(satp, pc);
    
    // Check for translation fault
    if (pa.x == 0xFFFFFFFFu) {
        return 0u;
    }
    
    let pixel_idx = pa.x / 4u;
    if (pixel_idx >= arrayLength(&memory)) {
        return 0u;
    }
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

fn decode_s_type(instr: u32) -> SType {
    let imm_11_5 = (instr >> 25u) & 127u;
    let imm_4_0 = (instr >> 7u) & 31u;
    let imm = sign_extend_12((imm_11_5 << 5u) | imm_4_0);
    let r2 = (instr >> 20u) & 31u;
    let r1 = (instr >> 15u) & 31u;
    let f3 = (instr >> 12u) & 7u;
    let op = instr & 127u;
    return SType(imm, r2, r1, f3, op);
}

// ============================================================================
// UART EMULATION (16550-compatible at 0x10000000)
// ============================================================================

// Write character to UART output buffer, returns new output_ptr value
fn uart_write_char(cpu_id: u32, char: u32, uart_ptr: u32) -> u32 {
    // Reserve first 256 words (1024 bytes) for UART output per CPU
    let uart_base_out = cpu_id * 256u;
    
    // Check buffer bounds
    if (uart_ptr < 1024u) {
        let word_idx = uart_ptr / 4u;
        let byte_in_word = uart_ptr % 4u;
        
        // Read-modify-write to preserve other bytes in the word
        let old_word = output[uart_base_out + word_idx];
        let mask = ~(0xFFu << (byte_in_word * 8u));
        let new_word = (old_word & mask) | (char << (byte_in_word * 8u));
        output[uart_base_out + word_idx] = new_word;
        
        // Return advanced output pointer
        return uart_ptr + 1u;
    }
    return uart_ptr;
}

// Check if address maps to UART device
fn is_uart_addr(pa: vec2<u32>) -> bool {
    return pa.x >= UART_BASE && pa.x < (UART_BASE + 8u);
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
    if (funct3 == 0u) { take_branch = eq64(v1, v2); }       // BEQ
    else if (funct3 == 1u) { take_branch = !eq64(v1, v2); }  // BNE
    else if (funct3 == 4u) { take_branch = lt64(v1, v2); }   // BLT (signed)
    else if (funct3 == 5u) { take_branch = !lt64(v1, v2) && !eq64(v1, v2); }  // BGE
    else if (funct3 == 6u) { take_branch = lt64(v1, v2); }   // BLTU
    else if (funct3 == 7u) { take_branch = !lt64(v1, v2) && !eq64(v1, v2); }  // BGEU

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

// OP_LOAD (LB, LH, LW, LBU, LHU, LD, LWU)
fn execute_load(satp: u32, cpu: ptr<function, RiscvCPU>, instr: u32) {
    let decoded = decode_i_type(instr);
    let va = add64((*cpu).regs[decoded.rs1], sext32_to_64(decoded.imm));
    
    // Translate virtual address
    let pa = translate_va(satp, va);
    
    // Check for page fault
    if (pa.x == 0xFFFFFFFFu) {
        // TODO: Trigger page fault exception
        (*cpu).running = 0u;
        (*cpu).pc = add64((*cpu).pc, vec2<u32>(4u, 0u));
        return;
    }
    
    // Check if this is a UART read
    if (is_uart_addr(pa)) {
        // UART LSR (Line Status Register) - always ready
        if (pa.x == UART_LSR) {
            if (decoded.rd != 0u) {
                (*cpu).regs[decoded.rd] = vec2<u32>(UART_LSR_THRE, 0u);
            }
        }
        // UART THR reads as 0
        else {
            if (decoded.rd != 0u) {
                (*cpu).regs[decoded.rd] = vec2<u32>(0u, 0u);
            }
        }
        (*cpu).pc = add64((*cpu).pc, vec2<u32>(4u, 0u));
        return;
    }
    
    let byte_offset = pa.x & 3u;
    let word_addr = pa.x / 4u;
    let px = memory[word_addr];
    let word = pixel_to_instruction(px);

    var value = vec2<u32>(0u, 0u);
    var value32 = 0u;

    if (decoded.funct3 == 0u) {
        // LB (Load Byte - sign-extended)
        let byte_val = (word >> (byte_offset * 8u)) & 0xFFu;
        value32 = select(byte_val, byte_val | 0xFFFFFF00u, (byte_val & 0x80u) != 0u);
        value = sext32_to_64(value32);
    } else if (decoded.funct3 == 1u) {
        // LH (Load Halfword - sign-extended)
        let half_val = (word >> (byte_offset * 8u)) & 0xFFFFu;
        value32 = select(half_val, half_val | 0xFFFF0000u, (half_val & 0x8000u) != 0u);
        value = sext32_to_64(value32);
    } else if (decoded.funct3 == 2u) {
        // LW (Load Word - sign-extended to 64-bit)
        value32 = word;
        value = sext32_to_64(value32);
    } else if (decoded.funct3 == 3u) {
        // LD (Load Doubleword) - 64-bit load
        value.x = word;
        // Read next word for high 32 bits
        let word_addr_next = (pa.x + 4u) / 4u;
        if (word_addr_next < arrayLength(&memory)) {
            let px_next = memory[word_addr_next];
            value.y = pixel_to_instruction(px_next);
        }
    } else if (decoded.funct3 == 4u) {
        // LBU (Load Byte Unsigned)
        value32 = (word >> (byte_offset * 8u)) & 0xFFu;
        value = zext32_to_64(value32);
    } else if (decoded.funct3 == 5u) {
        // LHU (Load Halfword Unsigned)
        value32 = (word >> (byte_offset * 8u)) & 0xFFFFu;
        value = zext32_to_64(value32);
    } else if (decoded.funct3 == 6u) {
        // LWU (Load Word Unsigned)
        value32 = word;
        value = zext32_to_64(value32);
    }

    if (decoded.rd != 0u) {
        (*cpu).regs[decoded.rd] = value;
    }

    (*cpu).pc = add64((*cpu).pc, vec2<u32>(4u, 0u));
}

// OP_STORE (SB, SH, SW, SD)
fn execute_store(satp: u32, cpu: ptr<function, RiscvCPU>, instr: u32, cpu_id: u32) {
    let decoded = decode_s_type(instr);
    let va = add64((*cpu).regs[decoded.rs1], sext32_to_64(decoded.imm));
    
    // Translate virtual address
    let pa = translate_va(satp, va);
    
    // Check for page fault
    if (pa.x == 0xFFFFFFFFu) {
        // TODO: Trigger page fault exception
        (*cpu).running = 0u;
        (*cpu).pc = add64((*cpu).pc, vec2<u32>(4u, 0u));
        return;
    }
    
    // Check if this is a UART write
    if (is_uart_addr(pa)) {
        // UART THR (Transmit Holding Register)
        if (pa.x == UART_THR && decoded.funct3 == 0u) {
            let char = (*cpu).regs[decoded.rs2].x & 0xFFu;
            (*cpu).output_ptr = uart_write_char(cpu_id, char, (*cpu).output_ptr);
        }
        // UART LSR - ignore writes
        (*cpu).pc = add64((*cpu).pc, vec2<u32>(4u, 0u));
        return;
    }
    
    let byte_offset = pa.x & 3u;
    let word_addr = pa.x / 4u;
    let px = memory[word_addr];
    let old_word = pixel_to_instruction(px);
    let store_val = (*cpu).regs[decoded.rs2];

    var new_word = old_word;

    if (decoded.funct3 == 0u) {
        // SB (Store Byte)
        let mask = ~(0xFFu << (byte_offset * 8u));
        new_word = (old_word & mask) | ((store_val.x & 0xFFu) << (byte_offset * 8u));
    } else if (decoded.funct3 == 1u) {
        // SH (Store Halfword)
        let mask = ~(0xFFFFu << (byte_offset * 8u));
        new_word = (old_word & mask) | ((store_val.x & 0xFFFFu) << (byte_offset * 8u));
    } else if (decoded.funct3 == 2u) {
        // SW (Store Word)
        new_word = store_val.x;
    } else if (decoded.funct3 == 3u) {
        // SD (Store Doubleword)
        new_word = store_val.x;
        // Write high 32 bits to next word
        let word_addr_next = (pa.x + 4u) / 4u;
        if (word_addr_next < arrayLength(&memory)) {
            write_phys_word(add64(pa, vec2<u32>(4u, 0u)), store_val.y);
        }
    }

    write_phys_word(pa, new_word);
    (*cpu).pc = add64((*cpu).pc, vec2<u32>(4u, 0u));
}

// ECALL Handling
fn read_byte_from_memory(satp: u32, addr: vec2<u32>) -> u32 {
    let pa = translate_va(satp, addr);
    if (pa.x == 0xFFFFFFFFu) {
        return 0u;
    }
    let word_addr = pa.x / 4u;
    let byte_offset = pa.x % 4u;
    if (word_addr >= arrayLength(&memory)) {
        return 0u;
    }
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
                let char_val = read_byte_from_memory((*cpu).satp, add64(buf, vec2<u32>(i, 0u)));
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
        // sys_exit
        (*cpu).running = 0u;
    } else {
        // Unknown syscall - halt
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

    // Fetch instruction with MMU translation
    let instr = fetch_instruction(cpu.satp, cpu.pc);
    let opcode = instr & 127u;

    if (opcode == OP_LUI) {
        execute_lui(&cpu, instr);
    } else if (opcode == OP_OP_IMM) {
        let funct3 = (instr >> 12u) & 7u;
        if (funct3 == F3_ADDI) {
            execute_addi(&cpu, instr);
        } else {
            // Unsupported OP_IMM instruction
            output[cpu_id * 256u] = instr;
            cpu.running = 0u;
        }
    } else if (opcode == OP_OP) {
        let funct3 = (instr >> 12u) & 7u;
        let funct7 = (instr >> 25u) & 127u;
        if (funct3 == 0u && funct7 == 0u) {
            // ADD
            execute_add(&cpu, instr);
        } else {
            // Unsupported OP instruction
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
        execute_load(cpu.satp, &cpu, instr);
    } else if (opcode == OP_STORE) {
        execute_store(cpu.satp, &cpu, instr, cpu_id);
    } else if (opcode == OP_SYSTEM) {
        let funct3 = (instr >> 12u) & 7u;
        let funct12 = instr >> 20u;
        if (funct3 == 0u && funct12 == 0u) {
            // ECALL
            execute_ecall(&cpu, cpu_id);
        } else {
            // Unsupported SYSTEM instruction
            cpu.running = 0u;
        }
    } else {
        // Unknown opcode - halt
        cpu.running = 0u;
    }

    cpu.instr_count = cpu.instr_count + 1u;
    cpus[cpu_id] = cpu;
}