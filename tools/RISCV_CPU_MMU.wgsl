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

// RISC-V CPU State with MMU support and machine-mode CSR file.
// Field order must match Python CPU_DTYPE exactly (std430, not sorted).
struct RiscvCPU {
    pc: vec2<u32>,              // Program counter (64-bit)
    regs: array<vec2<u32>, 32>, // x0-x31 (x0 is hardwired to 0)
    running: u32,               // 1 = executing, 0 = halted
    instr_count: u32,           // Instructions executed (debug)
    output_ptr: u32,            // Index to write next byte
    priv_mode: u32,             // Current privilege: 3 = M, 1 = S, 0 = U
    satp: vec2<u32>,            // SATP CSR, real RV64 layout: [63:60]=mode, [43:0]=PPN
    mstatus: vec2<u32>,         // Machine status (MIE/MPIE/MPP live in .x)
    mtvec: vec2<u32>,           // Trap vector base
    mepc: vec2<u32>,            // Trap return address
    mcause: vec2<u32>,          // Trap cause
    mtval: vec2<u32>,           // Trap value (faulting instr/address)
    mscratch: vec2<u32>,        // Scratch for trap handlers
    mie: vec2<u32>,             // Interrupt enable
    mip: vec2<u32>,             // Interrupt pending
    stvec: vec2<u32>,           // S-mode trap vector base
    sepc: vec2<u32>,            // S-mode trap return address
    scause: vec2<u32>,          // S-mode trap cause
    stval: vec2<u32>,           // S-mode trap value
    sscratch: vec2<u32>,        // S-mode scratch
    medeleg: vec2<u32>,         // Exception delegation to S-mode
    mideleg: vec2<u32>,         // Interrupt delegation to S-mode
    virtio_status: u32,         // VirtIO device status
    plic_pending: u32,          // PLIC pending interrupt bits (IRQ 0-31)
    plic_enable: u32,           // PLIC enable bits for hart 0
    plic_claimed: u32,          // Currently claimed IRQ (0 = none)
    _pad: u32,                  // Padding (std430 adds padding for alignment)
    _pad2: u32,                 // More padding to reach 432 bytes
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
const OP_AMO: u32 = 47u;         // A extension: LR/SC + AMOs
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

// Funct7 values for OP_IMM shift (RV64: shamt[5] is in funct7[5])
// Use mask to check low 5 bits only for 6-bit shamt support
const F7_SLLI: u32 = 0u;         // Low 5 bits; shamt[5] handled separately
const F7_SRLI: u32 = 0u;         // Low 5 bits; shamt[5] handled separately
const F7_SRAI: u32 = 32u;        // shamt[5] set for arithmetic

// Funct3 for 32-bit ops
const F3_ADDIW: u32 = 0u;
const F3_SLLIW: u32 = 1u;
const F3_SRLIW: u32 = 5u;
const F3_SRAIW: u32 = 5u;

// Funct7 values for OP_IMM_32 shifts
const F7_SLLIW: u32 = 0u;
const F7_SRLIW: u32 = 0u;
const F7_SRAIW: u32 = 32u;

// Funct7 values for OP_32
const F7_ADDW: u32 = 0u;
const F7_SUBW: u32 = 32u;
const F7_SLLW: u32 = 0u;
const F7_SRLW: u32 = 0u;
const F7_SRAW: u32 = 32u;

// M Extension (funct7 = 1 under OP / OP_32)
const F7_MULDIV: u32 = 1u;

// Privilege levels
const PRIV_U: u32 = 0u;
const PRIV_S: u32 = 1u;
const PRIV_M: u32 = 3u;

// CSR addresses
const CSR_SSTATUS: u32 = 0x100u;
const CSR_SIE: u32 = 0x104u;
const CSR_STVEC: u32 = 0x105u;
const CSR_SSCRATCH: u32 = 0x140u;
const CSR_SEPC: u32 = 0x141u;
const CSR_SCAUSE: u32 = 0x142u;
const CSR_STVAL: u32 = 0x143u;
const CSR_SIP: u32 = 0x144u;
const CSR_SATP: u32 = 0x180u;
const CSR_MEDELEG: u32 = 0x302u;
const CSR_MIDELEG: u32 = 0x303u;
const CSR_MSTATUS: u32 = 0x300u;
const CSR_MISA: u32 = 0x301u;
const CSR_MIE: u32 = 0x304u;
const CSR_MTVEC: u32 = 0x305u;
const CSR_MSCRATCH: u32 = 0x340u;
const CSR_MEPC: u32 = 0x341u;
const CSR_MCAUSE: u32 = 0x342u;
const CSR_MTVAL: u32 = 0x343u;
const CSR_MIP: u32 = 0x344u;
const CSR_MCYCLE: u32 = 0xB00u;
const CSR_MINSTRET: u32 = 0xB02u;
const CSR_CYCLE: u32 = 0xC00u;
const CSR_TIME: u32 = 0xC01u;
const CSR_INSTRET: u32 = 0xC02u;
const CSR_MVENDORID: u32 = 0xF11u;
const CSR_MARCHID: u32 = 0xF12u;
const CSR_MIMPID: u32 = 0xF13u;
const CSR_MHARTID: u32 = 0xF14u;

// Zicsr CSR access functions
fn read_csr(cpu: ptr<function, RiscvCPU>, csr_addr: u32) -> vec2<u32> {
    if (csr_addr == CSR_MHARTID) {
        // Return hart ID = 0 for single-core system
        return vec2<u32>(0u, 0u);
    } else if (csr_addr == CSR_MSTATUS) {
        return (*cpu).mstatus;
    } else if (csr_addr == CSR_MEPC) {
        return (*cpu).mepc;
    } else if (csr_addr == CSR_MCAUSE) {
        return (*cpu).mcause;
    } else if (csr_addr == CSR_MTVAL) {
        return (*cpu).mtval;
    } else if (csr_addr == CSR_MTVEC) {
        return (*cpu).mtvec;
    } else if (csr_addr == CSR_MIE) {
        return (*cpu).mie;
    } else if (csr_addr == CSR_MIP) {
        return (*cpu).mip;
    } else if (csr_addr == CSR_MSCRATCH) {
        return (*cpu).mscratch;
    } else if (csr_addr == CSR_MEDELEG) {
        return (*cpu).medeleg;
    } else if (csr_addr == CSR_MIDELEG) {
        return (*cpu).mideleg;
    } else if (csr_addr == CSR_CYCLE || csr_addr == CSR_MCYCLE) {
        // Return instruction count as cycle count
        return vec2<u32>((*cpu).instr_count, 0u);
    } else if (csr_addr == CSR_INSTRET || csr_addr == CSR_MINSTRET) {
        // Return instruction count
        return vec2<u32>((*cpu).instr_count, 0u);
    } else if (csr_addr == CSR_MISA) {
        // Return MISA: MXL=64 (bits 63:62=11), extensions in lower bits
        // We support IMAFD (integer, multiply/div, float/double, atomic)
        // I=1, M=12, A=1, F=4, D=8, Zicsr=2
        return vec2<u32>(0x80000008u, 0x00000000u);  // MXL=2 (RV64)
    } else if (csr_addr == CSR_TIME) {
        // Return fake time (instruction count * 10)
        return vec2<u32>((*cpu).instr_count * 10u, 0u);
    } else if (csr_addr == CSR_MVENDORID) {
        // Vendor ID: 0 (no vendor)
        return vec2<u32>(0u, 0u);
    } else if (csr_addr == CSR_MARCHID) {
        // Architecture ID: non-zero for RISC-V
        return vec2<u32>(1u, 0u);
    } else if (csr_addr == CSR_MIMPID) {
        // Implementation ID: 0
        return vec2<u32>(0u, 0u);
    } else if (csr_addr == CSR_SSTATUS) {
        // SSTATUS = restricted view of MSTATUS
        let sstatus_x = (*cpu).mstatus.x & SSTATUS_MASK_LO;
        let sstatus_y = (*cpu).mstatus.y & SSTATUS_MASK_HI;
        return vec2<u32>(sstatus_x, sstatus_y);
    } else if (csr_addr == CSR_STVEC) {
        return (*cpu).stvec;
    } else if (csr_addr == CSR_SEPC) {
        return (*cpu).sepc;
    } else if (csr_addr == CSR_SCAUSE) {
        return (*cpu).scause;
    } else if (csr_addr == CSR_STVAL) {
        return (*cpu).stval;
    } else if (csr_addr == CSR_SATP) {
        return (*cpu).satp;
    } else if (csr_addr == CSR_SSCRATCH) {
        return (*cpu).sscratch;
    } else if (csr_addr == CSR_SIE) {
        // SIE = MIE with delegation mask
        let sie_x = (*cpu).mie.x & (*cpu).mideleg.x;
        let sie_y = (*cpu).mie.y & (*cpu).mideleg.y;
        return vec2<u32>(sie_x, sie_y);
    } else if (csr_addr == CSR_SIP) {
        // SIP = MIP with delegation mask
        let sip_x = (*cpu).mip.x & (*cpu).mideleg.x;
        let sip_y = (*cpu).mip.y & (*cpu).mideleg.y;
        return vec2<u32>(sip_x, sip_y);
    }
    // Unknown CSR - return zero
    return vec2<u32>(0u, 0u);
}

fn write_csr(cpu: ptr<function, RiscvCPU>, csr_addr: u32, val: vec2<u32>) {
    if (csr_addr == CSR_MSTATUS) {
        (*cpu).mstatus = val;
    } else if (csr_addr == CSR_MEPC) {
        (*cpu).mepc = val;
    } else if (csr_addr == CSR_MCAUSE) {
        (*cpu).mcause = val;
    } else if (csr_addr == CSR_MTVAL) {
        (*cpu).mtval = val;
    } else if (csr_addr == CSR_MTVEC) {
        (*cpu).mtvec = val;
    } else if (csr_addr == CSR_MIE) {
        (*cpu).mie = val;
    } else if (csr_addr == CSR_MSCRATCH) {
        (*cpu).mscratch = val;
    } else if (csr_addr == CSR_MEDELEG) {
        (*cpu).medeleg = val;
    } else if (csr_addr == CSR_MIDELEG) {
        (*cpu).mideleg = val;
    } else if (csr_addr == CSR_STVEC) {
        (*cpu).stvec = val;
    } else if (csr_addr == CSR_SEPC) {
        (*cpu).sepc = val;
    } else if (csr_addr == CSR_SCAUSE) {
        (*cpu).scause = val;
    } else if (csr_addr == CSR_STVAL) {
        (*cpu).stval = val;
    } else if (csr_addr == CSR_SATP) {
        (*cpu).satp = val;
    } else if (csr_addr == CSR_SSCRATCH) {
        (*cpu).sscratch = val;
    } else if (csr_addr == CSR_SIE) {
        // Write to SIE affects MIE
        (*cpu).mie.x = ((*cpu).mie.x & ~(*cpu).mideleg.x) | (val.x & (*cpu).mideleg.x);
    } else if (csr_addr == CSR_SSTATUS) {
        // Write to SSTATUS affects MSTATUS
        (*cpu).mstatus.x = ((*cpu).mstatus.x & ~SSTATUS_MASK_LO) | (val.x & SSTATUS_MASK_LO);
        (*cpu).mstatus.y = ((*cpu).mstatus.y & ~SSTATUS_MASK_HI) | (val.y & SSTATUS_MASK_HI);
    }
    // Ignore writes to read-only CSRs (CYCLE, TIME, INSTRET, MISA, etc.)
}

// CSRRW (Read-Write CSR)
fn execute_csrrw(cpu: ptr<function, RiscvCPU>, instr: u32) {
    let rd = (instr >> 7u) & 31u;
    let rs1 = (instr >> 15u) & 31u;
    let csr_addr = instr >> 20u;

    let old_val = read_csr(cpu, csr_addr);
    write_csr(cpu, csr_addr, (*cpu).regs[rs1]);

    if (rd != 0u) {
        (*cpu).regs[rd] = old_val;
    }
    (*cpu).pc = add64((*cpu).pc, vec2<u32>(4u, 0u));
}

// CSRRS (Read-Set CSR)
fn execute_csrrs(cpu: ptr<function, RiscvCPU>, instr: u32) {
    let rd = (instr >> 7u) & 31u;
    let rs1 = (instr >> 15u) & 31u;
    let csr_addr = instr >> 20u;

    let old_val = read_csr(cpu, csr_addr);
    let new_val = old_val | (*cpu).regs[rs1];
    write_csr(cpu, csr_addr, new_val);

    if (rd != 0u) {
        (*cpu).regs[rd] = old_val;
    }
    (*cpu).pc = add64((*cpu).pc, vec2<u32>(4u, 0u));
}

// CSRRC (Read-Clear CSR)
fn execute_csrrc(cpu: ptr<function, RiscvCPU>, instr: u32) {
    let rd = (instr >> 7u) & 31u;
    let rs1 = (instr >> 15u) & 31u;
    let csr_addr = instr >> 20u;

    let old_val = read_csr(cpu, csr_addr);
    let new_val = old_val & ~(*cpu).regs[rs1];
    write_csr(cpu, csr_addr, new_val);

    if (rd != 0u) {
        (*cpu).regs[rd] = old_val;
    }
    (*cpu).pc = add64((*cpu).pc, vec2<u32>(4u, 0u));
}

// mstatus bit positions (low word)
const MSTATUS_SIE_BIT: u32 = 1u;
const MSTATUS_MIE_BIT: u32 = 3u;
const MSTATUS_SPIE_BIT: u32 = 5u;
const MSTATUS_MPIE_BIT: u32 = 7u;
const MSTATUS_SPP_BIT: u32 = 8u;
const MSTATUS_MPP_SHIFT: u32 = 11u;  // bits [12:11]

// sstatus = restricted view of mstatus: SIE, SPIE, UBE, SPP, VS, FS, XS, SUM, MXR
const SSTATUS_MASK_LO: u32 = 0x000DE762u;
const SSTATUS_MASK_HI: u32 = 0x00000003u;  // UXL bits [33:32]

// mcause exception codes
const CAUSE_ILLEGAL_INSTR: u32 = 2u;
const CAUSE_BREAKPOINT: u32 = 3u;
const CAUSE_ECALL_U: u32 = 8u;
const CAUSE_ECALL_S: u32 = 9u;
const CAUSE_ECALL_M: u32 = 11u;
const CAUSE_INSTR_PAGE_FAULT: u32 = 12u;   // Instruction page fault
const CAUSE_LOAD_PAGE_FAULT: u32 = 13u;    // Load page fault
const CAUSE_STORE_PAGE_FAULT: u32 = 15u;   // Store page fault

// Interrupt cause codes (MSB bit 31 set = interrupt)
const CAUSE_USER_SOFT: u32 = 0x80000000u;   // 0
const CAUSE_SUPERVISOR_SOFT: u32 = 0x80000001u; // 1
const CAUSE_MACHINE_SOFT: u32 = 0x80000003u;    // 3
const CAUSE_USER_TIMER: u32 = 0x80000004u;      // 4
const CAUSE_SUPERVISOR_TIMER: u32 = 0x80000005u; // 5
const CAUSE_MACHINE_TIMER: u32 = 0x80000007u;    // 7
const CAUSE_USER_EXTERNAL: u32 = 0x80000008u;    // 8
const CAUSE_SUPERVISOR_EXTERNAL: u32 = 0x80000009u; // 9
const CAUSE_MACHINE_EXTERNAL: u32 = 0x8000000Bu;   // 11

// MIP interrupt bits
const MIP_USIP: u32 = 1u;
const MIP_SSIP: u32 = 2u;
const MIP_MSIP: u32 = 4u;
const MIP_UTIP: u32 = 8u;
const MIP_STIP: u32 = 16u;
const MIP_MTIP: u32 = 32u;
const MIP_UEIP: u32 = 64u;
const MIP_SEIP: u32 = 128u;   // S-mode external interrupt
const MIP_MEIP: u32 = 256u;   // M-mode external interrupt (from PLIC)

// SBI extension IDs (a7) - the WGSL emulator IS the M-mode firmware.
// S-mode ECALLs are handled inline instead of vectoring to mtvec.
const SBI_EXT_LEGACY_SET_TIMER: u32 = 0x00u;
const SBI_EXT_LEGACY_PUTCHAR: u32 = 0x01u;
const SBI_EXT_LEGACY_GETCHAR: u32 = 0x02u;
const SBI_EXT_BASE: u32 = 0x10u;
const SBI_EXT_TIME: u32 = 0x54494D45u;   // "TIME"
const SBI_EXT_IPI: u32 = 0x735049u;      // "sPI"
const SBI_EXT_RFENCE: u32 = 0x52464E43u; // "RFNC"
const SBI_EXT_HSM: u32 = 0x48534Du;      // "HSM"
const SBI_EXT_SRST: u32 = 0x53525354u;   // "SRST"
const SBI_EXT_DBCN: u32 = 0x4442434Eu;   // "DBCN" (debug console)
const SBI_SUCCESS: u32 = 0u;
const SBI_ERR_NOT_SUPPORTED: u32 = 0xFFFFFFFEu;  // -2 (low word; high = all ones)

// SYSTEM funct12 encodings (funct3 == 0)
const F12_ECALL: u32 = 0x000u;
const F12_EBREAK: u32 = 0x001u;
const F12_SRET: u32 = 0x102u;
const F12_WFI: u32 = 0x105u;
const F12_MRET: u32 = 0x302u;
const F7_SFENCE_VMA: u32 = 0x09u;

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

// PLIC (Platform-Level Interrupt Controller)
const PLIC_BASE: u32 = 0x0c000000u;
const PLIC_PENDING_BASE: u32 = 0x0c001000u;  // Pending bits (1 bit per IRQ)
const PLIC_ENABLE_BASE: u32 = 0x0c002000u;   // Enable bits per hart/context
const PLIC_CONTEXT_BASE: u32 = 0x0c200000u;  // Hart 0 context
const PLIC_THRESHOLD: u32 = 0x0c200000u;     // Priority threshold
const PLIC_CLAIM: u32 = 0x0c200004u;          // Claim/Complete register

// VirtIO Block Device
const VIRTIO_BASE: u32 = 0x10001000u;
const VIRTIO_QUEUE_NOTIFY: u32 = 0x50u;  // QueueNotify (kick) offset

// VirtIO IRQ numbers (RISC-V standard)
const VIRTIO_IRQ: u32 = 1u;  // VirtIO block device = IRQ 1

// Physical memory base offset
// For M-mode systems like xv6, DRAM starts at 0x80000000
// When MMU is off, we subtract this base to get pixel index
const PHYS_BASE: u32 = 0x80000000u;

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
        return imm | 4294963200u;  // 0xFFFFF000
    }
    return imm;
}

// Sign-extend 20-bit immediate to 32-bit
fn sign_extend_20(imm: u32) -> u32 {
    if ((imm & 524288u) != 0u) {
        return imm | 4293918720u;  // 0xFFF00000
    }
    return imm;
}

// Sign-extend 21-bit immediate (for JAL) to 32-bit
fn sign_extend_21(imm: u32) -> u32 {
    if ((imm & 1048576u) != 0u) {
        return imm | 4292870144u;  // 0xFFE00000
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

// Compare two 64-bit values (signed): flip the sign bit and compare unsigned
fn lt64s(a: vec2<u32>, b: vec2<u32>) -> bool {
    return lt64(vec2<u32>(a.x, a.y ^ 0x80000000u), vec2<u32>(b.x, b.y ^ 0x80000000u));
}

fn is_neg64(a: vec2<u32>) -> bool {
    return (a.y & 0x80000000u) != 0u;
}

fn neg64(a: vec2<u32>) -> vec2<u32> {
    return sub64(vec2<u32>(0u, 0u), a);
}

// 64-bit shifts. WGSL masks shift amounts mod 32, so shamt == 0 and
// shamt >= 32 need explicit branches (e.g. `x >> (32u - 0u)` is `x >> 0u`).
fn shl64(v: vec2<u32>, shamt: u32) -> vec2<u32> {
    if (shamt == 0u) { return v; }
    if (shamt < 32u) {
        return vec2<u32>(v.x << shamt, (v.y << shamt) | (v.x >> (32u - shamt)));
    }
    return vec2<u32>(0u, v.x << (shamt - 32u));
}

fn shr64u(v: vec2<u32>, shamt: u32) -> vec2<u32> {
    if (shamt == 0u) { return v; }
    if (shamt < 32u) {
        return vec2<u32>((v.x >> shamt) | (v.y << (32u - shamt)), v.y >> shamt);
    }
    return vec2<u32>(v.y >> (shamt - 32u), 0u);
}

fn shr64s(v: vec2<u32>, shamt: u32) -> vec2<u32> {
    if (shamt == 0u) { return v; }
    let hi_signed = bitcast<i32>(v.y);
    if (shamt < 32u) {
        let low = (v.x >> shamt) | (v.y << (32u - shamt));
        let high = bitcast<u32>(hi_signed >> shamt);
        return vec2<u32>(low, high);
    }
    let fill = select(0u, 0xFFFFFFFFu, hi_signed < 0);
    if (shamt == 32u) { return vec2<u32>(v.y, fill); }
    return vec2<u32>(bitcast<u32>(hi_signed >> (shamt - 32u)), fill);
}

// ============================================================================
// M EXTENSION MATH (multiply/divide on vec2<u32> limbs)
// ============================================================================

// 32x32 -> 64 unsigned widening multiply via 16-bit limbs
// (WGSL has no widening multiply builtin)
fn mul32_wide(a: u32, b: u32) -> vec2<u32> {
    let a_lo = a & 0xFFFFu;
    let a_hi = a >> 16u;
    let b_lo = b & 0xFFFFu;
    let b_hi = b >> 16u;

    let ll = a_lo * b_lo;
    let lh = a_lo * b_hi;
    let hl = a_hi * b_lo;
    let hh = a_hi * b_hi;

    // mid sums three 16x16 products' overlapping halves; max value fits in u32
    let mid = (ll >> 16u) + (lh & 0xFFFFu) + (hl & 0xFFFFu);
    let low = (ll & 0xFFFFu) | (mid << 16u);
    let high = hh + (lh >> 16u) + (hl >> 16u) + (mid >> 16u);
    return vec2<u32>(low, high);
}

// Low 64 bits of a 64x64 product (MUL)
fn mul64_low(a: vec2<u32>, b: vec2<u32>) -> vec2<u32> {
    let p = mul32_wide(a.x, b.x);
    let high = p.y + a.x * b.y + a.y * b.x;  // wrapping adds are correct here
    return vec2<u32>(p.x, high);
}

// High 64 bits of an unsigned 64x64 -> 128 product (MULHU)
fn mulhu64(a: vec2<u32>, b: vec2<u32>) -> vec2<u32> {
    let p00 = mul32_wide(a.x, b.x);
    let p01 = mul32_wide(a.x, b.y);
    let p10 = mul32_wide(a.y, b.x);
    let p11 = mul32_wide(a.y, b.y);

    // Column 1 (bits 32-63): p00.y + p01.x + p10.x, track carries into column 2
    let s1a = p00.y + p01.x;
    let c1a = select(0u, 1u, s1a < p00.y);
    let s1 = s1a + p10.x;
    let c1b = select(0u, 1u, s1 < s1a);
    let carry1 = c1a + c1b;

    // Column 2 (bits 64-95): p01.y + p10.y + p11.x + carry1
    let s2a = p01.y + p10.y;
    let c2a = select(0u, 1u, s2a < p01.y);
    let s2b = s2a + p11.x;
    let c2b = select(0u, 1u, s2b < s2a);
    let s2 = s2b + carry1;
    let c2c = select(0u, 1u, s2 < s2b);

    // Column 3 (bits 96-127)
    let r3 = p11.y + c2a + c2b + c2c;
    return vec2<u32>(s2, r3);
}

// High 64 bits of signed x signed (MULH), via the identity:
// mulh(a,b) = mulhu(a,b) - (a < 0 ? b : 0) - (b < 0 ? a : 0)
fn mulh64(a: vec2<u32>, b: vec2<u32>) -> vec2<u32> {
    var h = mulhu64(a, b);
    if (is_neg64(a)) { h = sub64(h, b); }
    if (is_neg64(b)) { h = sub64(h, a); }
    return h;
}

// High 64 bits of signed x unsigned (MULHSU)
fn mulhsu64(a: vec2<u32>, b: vec2<u32>) -> vec2<u32> {
    var h = mulhu64(a, b);
    if (is_neg64(a)) { h = sub64(h, b); }
    return h;
}

struct DivRem {
    q: vec2<u32>,
    r: vec2<u32>,
}

// Unsigned 64/64 restoring division. Div-by-zero follows the RISC-V spec:
// quotient = all ones, remainder = dividend (no trap).
fn divremu64(a: vec2<u32>, b: vec2<u32>) -> DivRem {
    if (b.x == 0u && b.y == 0u) {
        return DivRem(vec2<u32>(0xFFFFFFFFu, 0xFFFFFFFFu), a);
    }
    var q = vec2<u32>(0u, 0u);
    var r = vec2<u32>(0u, 0u);
    for (var i: i32 = 63; i >= 0; i = i - 1) {
        r = shl64(r, 1u);
        if (i >= 32) {
            r.x = r.x | ((a.y >> u32(i - 32)) & 1u);
        } else {
            r.x = r.x | ((a.x >> u32(i)) & 1u);
        }
        if (!lt64(r, b)) {
            r = sub64(r, b);
            if (i >= 32) {
                q.y = q.y | (1u << u32(i - 32));
            } else {
                q.x = q.x | (1u << u32(i));
            }
        }
    }
    return DivRem(q, r);
}

// Signed 64/64 division. Spec cases: div-by-zero -> q=-1, r=dividend;
// INT64_MIN / -1 overflow -> q=dividend, r=0.
fn divrems64(a: vec2<u32>, b: vec2<u32>) -> DivRem {
    if (b.x == 0u && b.y == 0u) {
        return DivRem(vec2<u32>(0xFFFFFFFFu, 0xFFFFFFFFu), a);
    }
    if (a.x == 0u && a.y == 0x80000000u && b.x == 0xFFFFFFFFu && b.y == 0xFFFFFFFFu) {
        return DivRem(a, vec2<u32>(0u, 0u));
    }
    let a_neg = is_neg64(a);
    let b_neg = is_neg64(b);
    let ua = select(a, neg64(a), a_neg);
    let ub = select(b, neg64(b), b_neg);
    let dr = divremu64(ua, ub);
    let q = select(dr.q, neg64(dr.q), a_neg != b_neg);
    let r = select(dr.r, neg64(dr.r), a_neg);
    return DivRem(q, r);
}

// ============================================================================
// SV39 MMU IMPLEMENTATION
// ============================================================================

// Read a 32-bit word from physical memory
fn read_phys_word(pa: vec2<u32>) -> u32 {
    // Handle physical memory at 0x80000000+ (xv6 M-mode boot)
    let pa_base = select(0u, PHYS_BASE, pa.x >= PHYS_BASE);
    let pa_offset = pa.x - pa_base;
    let word_addr = (pa_offset / 4u);
    if (word_addr >= arrayLength(&memory)) {
        return 0u;
    }
    let px = memory[word_addr];
    return pixel_to_instruction(px);
}

// Write a 32-bit word to physical memory
fn write_phys_word(pa: vec2<u32>, val: u32) {
    // Handle physical memory at 0x80000000+ (xv6 M-mode boot)
    let pa_base = select(0u, PHYS_BASE, pa.x >= PHYS_BASE);
    let pa_offset = pa.x - pa_base;
    let word_addr = (pa_offset / 4u);
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
// RV64 satp layout: mode = bits [63:60], ASID = [59:44], PPN = [43:0]
fn mmu_enabled(satp: vec2<u32>) -> bool {
    // Mode [63:60] maps to satp.y [31:28]
    let mode = (satp.y >> 28u) & 0xFu;
    return mode == SATP_MODE_SV39;
}

// Extract PPN from SATP CSR (bits [43:0])
fn satp_to_ppn(satp: vec2<u32>) -> vec2<u32> {
    // PPN[31:0] = satp.x, PPN[43:32] = satp.y[11:0]
    return vec2<u32>(satp.x, satp.y & 0xFFFu);
}

// Extract VPN (Virtual Page Number) from virtual address
// For SV39:
// - VPN2: bits [38:30]
// - VPN1: bits [29:21]
// - VPN0: bits [20:12]
// - Offset: bits [11:0]

fn extract_vpn2(va: vec2<u32>) -> u32 {
    // VPN2 is bits [38:30] of VA
    // VA[38:32] = va.y[6:0], VA[31:30] = va.x[1:0]
    let high_vpn = (va.y & 0x7Fu) << 2u;  // bits [38:32] -> position [9:2]
    let low_vpn = va.x >> 30u;            // bits [31:30] -> position [1:0]
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
fn pte_to_ppn(pte: vec2<u32>) -> vec2<u32> {
    let ppn_low = (pte.x >> 10u) | (pte.y << 22u);
    let ppn_high = (pte.y >> 10u) & 0xFFFu;
    return vec2<u32>(ppn_low, ppn_high);
}

// Calculate physical address from PPN and offset
fn make_pa(ppn: vec2<u32>, offset: u32) -> vec2<u32> {
    let pa_low = (ppn.x << 12u) | offset;
    let pa_high = (ppn.y << 12u) | (ppn.x >> 20u);
    return vec2<u32>(pa_low, pa_high);
}

fn translate_va(cpu: ptr<function, RiscvCPU>, va: vec2<u32>) -> vec2<u32> {
    if (!mmu_enabled((*cpu).satp)) {
        return va;
    }

    let root_ppn = satp_to_ppn((*cpu).satp);
    
    // SV39 PTEs are 64 bits (8 bytes) each
    
    // === LEVEL 1 (L1) PAGE TABLE ===
    let l1_vpn = extract_vpn2(va);
    let l1_pte_pa = add64(vec2<u32>(root_ppn.x << 12u, root_ppn.y), vec2<u32>(l1_vpn * 8u, 0u));
    let l1_pte_low = read_phys_word(l1_pte_pa);
    let l1_pte_high = read_phys_word(add64(l1_pte_pa, vec2<u32>(4u, 0u)));
    let l1_pte = vec2<u32>(l1_pte_low, l1_pte_high);
    
    if (!pte_valid(l1_pte.x)) {
        return vec2<u32>(0xFFFFFFFFu, 0xFFFFFFFFu);
    }
    
    if (pte_is_leaf(l1_pte.x)) {
        // L1 is a gigapage (1GB mapping)
        let l1_ppn = pte_to_ppn(l1_pte);
        // Offset = VA[29:0]
        let offset = va.x & 0x3FFFFFFFu;
        return make_pa(l1_ppn, offset);
    }
    
    // === LEVEL 2 (L2) PAGE TABLE ===
    let l2_vpn = extract_vpn1(va);
    let l2_ppn = pte_to_ppn(l1_pte);
    let l2_pte_pa = add64(vec2<u32>(l2_ppn.x << 12u, l2_ppn.y), vec2<u32>(l2_vpn * 8u, 0u));
    let l2_pte_low = read_phys_word(l2_pte_pa);
    let l2_pte_high = read_phys_word(add64(l2_pte_pa, vec2<u32>(4u, 0u)));
    let l2_pte = vec2<u32>(l2_pte_low, l2_pte_high);
    
    if (!pte_valid(l2_pte.x)) {
        return vec2<u32>(0xFFFFFFFFu, 0xFFFFFFFFu);
    }
    
    if (pte_is_leaf(l2_pte.x)) {
        // L2 is a megapage (2MB mapping)
        let l2_ppn_leaf = pte_to_ppn(l2_pte);
        // Offset = VA[20:0]
        let offset = va.x & 0x1FFFFFu;
        return make_pa(l2_ppn_leaf, offset);
    }
    
    // === LEVEL 3 (L3) PAGE TABLE (LEAF) ===
    let l3_vpn = extract_vpn0(va);
    let l3_ppn = pte_to_ppn(l2_pte);
    let l3_pte_pa = add64(vec2<u32>(l3_ppn.x << 12u, l3_ppn.y), vec2<u32>(l3_vpn * 8u, 0u));
    let l3_pte_low = read_phys_word(l3_pte_pa);
    let l3_pte_high = read_phys_word(add64(l3_pte_pa, vec2<u32>(4u, 0u)));
    let l3_pte = vec2<u32>(l3_pte_low, l3_pte_high);
    
    if (!pte_valid(l3_pte.x) || !pte_is_leaf(l3_pte.x)) {
        return vec2<u32>(0xFFFFFFFFu, 0xFFFFFFFFu);
    }
    
    // L3 is a leaf page (4KB mapping)
    let l3_ppn_leaf = pte_to_ppn(l3_pte);
    let offset = extract_offset(va);
    return make_pa(l3_ppn_leaf, offset);
}

// ============================================================================
// INSTRUCTION FETCH
// ============================================================================

// A fetched instruction word (e.g. 0xFFFFFFFF, a syntactically valid, if
// currently unrecognized, opcode) is a legitimate value that must not be
// confused with "fetch failed" - hence a struct instead of an overloaded
// sentinel return, which previously misfired take_trap(PAGE_FAULT) on any
// real instruction word that happened to equal 0xFFFFFFFF.
struct FetchResult {
    instr: u32,
    faulted: bool,
}

fn fetch_instruction(cpu: ptr<function, RiscvCPU>, pc: vec2<u32>) -> FetchResult {
    // Translate virtual PC to physical address
    let pa = translate_va(cpu, pc);

    // Check for translation fault
    if (pa.x == 0xFFFFFFFFu) {
        return FetchResult(0u, true);
    }

    // Handle physical memory at 0x80000000+ (xv6 M-mode boot)
    let pa_base = select(0u, PHYS_BASE, pa.x >= PHYS_BASE);
    let pa_offset = pa.x - pa_base;
    let pixel_idx = pa_offset / 4u;

    if (pixel_idx >= arrayLength(&memory)) {
        return FetchResult(0u, true);
    }
    let px = memory[pixel_idx];
    return FetchResult(pixel_to_instruction(px), false);
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
// PLIC (Platform-Level Interrupt Controller)
// ============================================================================

// Check if address maps to PLIC
fn is_plic_addr(pa: vec2<u32>) -> bool {
    return pa.x >= PLIC_BASE && pa.x < (PLIC_BASE + 0x210000u);
}

// Raise a PLIC interrupt (sets pending bit)
fn plic_raise_irq(cpu: ptr<function, RiscvCPU>, irq: u32) {
    if (irq < 32u) {
        (*cpu).plic_pending = (*cpu).plic_pending | (1u << irq);
    }
}

// Check for pending external interrupt (for MIP.MEIP)
fn check_external_interrupt(cpu: ptr<function, RiscvCPU>) -> bool {
    // External interrupt pending if PLIC has bits set that are enabled
    let pending_enabled = (*cpu).plic_pending & (*cpu).plic_enable;
    return pending_enabled != 0u;
}

// ============================================================================
// VIRTIO BLOCK DEVICE EMULATION
// ============================================================================

// Check if address maps to VirtIO
fn is_virtio_addr(pa: vec2<u32>) -> bool {
    return pa.x >= VIRTIO_BASE && pa.x < (VIRTIO_BASE + 0x1000u);
}

// VirtIO descriptor ring layout (16 bytes per descriptor)
// struct virtq_desc {
//   u64 addr;    // Physical address (LE)
//   u32 len;     // Length (LE)
//   u16 flags;   // Flags (LE)
//   u16 next;    // Next descriptor (LE)
// }
// Total: 16 bytes

// VirtIO used ring entry (8 bytes per used entry)
// struct virtq_used_elem {
//   u32 id;      // Index of descriptor (LE)
//   u32 len;     // Total written length (LE)
// }

// VirtIO request header (16 bytes)
// struct virtio_blk_req {
//   u32 type;    // 0=read, 1=write
//   u32 reserved;
//   u64 sector;  // LBA sector number
// }

// Process VirtIO block read request (synchronously)
fn virtio_process_block_read(cpu: ptr<function, RiscvCPU>, queue_addr: vec2<u32>, queue_idx: u32) {
    // Read queue descriptor address (vring.desc) from queue memory
    // This is a simplification: xv6 stores queue info in memory, we need to walk it

    // For now: stub - just signal completion via PLIC
    // Real implementation would:
    // 1. Read vring.desc array (queue_addr)
    // 2. Walk descriptors, read data from disk image to guest buffer
    // 3. Write to vring.used array with length
    // 4. Update vring.used.idx

    // Minimal stub: raise IRQ to indicate completion
    plic_raise_irq(cpu, VIRTIO_IRQ);
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

// AUIPC (Add Upper Immediate to PC)
fn execute_auipc(cpu: ptr<function, RiscvCPU>, instr: u32) {
    let rd = (instr >> 7u) & 31u;
    let imm = ((instr >> 12u) & 0xFFFFFu) << 12u;  // imm[31:12] << 12
    let imm64 = sext32_to_64(imm);
    let pc_plus_imm = add64((*cpu).pc, imm64);
    if (rd != 0u) {
        (*cpu).regs[rd] = pc_plus_imm;
    }
    (*cpu).pc = add64((*cpu).pc, vec2<u32>(4u, 0u));
}

// ANDI (AND Immediate)
fn execute_andi(cpu: ptr<function, RiscvCPU>, instr: u32) {
    let decoded = decode_i_type(instr);
    if (decoded.rd != 0u) {
        let imm64 = sext32_to_64(decoded.imm);
        (*cpu).regs[decoded.rd].x = (*cpu).regs[decoded.rs1].x & imm64.x;
        (*cpu).regs[decoded.rd].y = (*cpu).regs[decoded.rs1].y & imm64.y;
    }
    (*cpu).pc = add64((*cpu).pc, vec2<u32>(4u, 0u));
}

// ORI (OR Immediate)
fn execute_ori(cpu: ptr<function, RiscvCPU>, instr: u32) {
    let decoded = decode_i_type(instr);
    if (decoded.rd != 0u) {
        let imm64 = sext32_to_64(decoded.imm);
        (*cpu).regs[decoded.rd].x = (*cpu).regs[decoded.rs1].x | imm64.x;
        (*cpu).regs[decoded.rd].y = (*cpu).regs[decoded.rs1].y | imm64.y;
    }
    (*cpu).pc = add64((*cpu).pc, vec2<u32>(4u, 0u));
}

// XORI (XOR Immediate)
fn execute_xori(cpu: ptr<function, RiscvCPU>, instr: u32) {
    let decoded = decode_i_type(instr);
    if (decoded.rd != 0u) {
        let imm64 = sext32_to_64(decoded.imm);
        (*cpu).regs[decoded.rd].x = (*cpu).regs[decoded.rs1].x ^ imm64.x;
        (*cpu).regs[decoded.rd].y = (*cpu).regs[decoded.rs1].y ^ imm64.y;
    }
    (*cpu).pc = add64((*cpu).pc, vec2<u32>(4u, 0u));
}

// SLTI (Set Less Than Immediate - signed)
fn execute_slti(cpu: ptr<function, RiscvCPU>, instr: u32) {
    let decoded = decode_i_type(instr);
    if (decoded.rd != 0u) {
        let rs1_val = (*cpu).regs[decoded.rs1];
        let imm_val = sext32_to_64(decoded.imm);

        // Signed comparison: check if rs1 < imm
        let rs1_neg = (rs1_val.y & 0x80000000u) != 0u;
        let imm_neg = (imm_val.y & 0x80000000u) != 0u;

        var is_less = false;
        if (rs1_neg && !imm_neg) {
            is_less = true;  // Negative < positive
        } else if (!rs1_neg && imm_neg) {
            is_less = false; // Positive < negative
        } else {
            // Same sign - compare high then low
            if (rs1_val.y < imm_val.y) {
                is_less = true;
            } else if (rs1_val.y == imm_val.y) {
                is_less = rs1_val.x < imm_val.x;
            }
        }

        (*cpu).regs[decoded.rd] = vec2<u32>(select(0u, 1u, is_less), 0u);
    }
    (*cpu).pc = add64((*cpu).pc, vec2<u32>(4u, 0u));
}

// SLTIU (Set Less Than Immediate - unsigned)
fn execute_sltiu(cpu: ptr<function, RiscvCPU>, instr: u32) {
    let decoded = decode_i_type(instr);
    if (decoded.rd != 0u) {
        let rs1_val = (*cpu).regs[decoded.rs1];
        let imm_val = sext32_to_64(decoded.imm);
        let is_less = lt64(rs1_val, imm_val);
        (*cpu).regs[decoded.rd] = vec2<u32>(select(0u, 1u, is_less), 0u);
    }
    (*cpu).pc = add64((*cpu).pc, vec2<u32>(4u, 0u));
}

// SLLI (Shift Left Logical Immediate)
fn execute_slli(cpu: ptr<function, RiscvCPU>, instr: u32) {
    let shamt = (instr >> 20u) & 63u;  // shamt[5:0] for RV64
    let rd = (instr >> 7u) & 31u;
    let rs1 = (instr >> 15u) & 31u;

    if (rd != 0u) {
        (*cpu).regs[rd] = shl64((*cpu).regs[rs1], shamt);
    }
    (*cpu).pc = add64((*cpu).pc, vec2<u32>(4u, 0u));
}

// SRLI (Shift Right Logical Immediate)
fn execute_srli(cpu: ptr<function, RiscvCPU>, instr: u32) {
    let shamt = (instr >> 20u) & 63u;  // shamt[5:0] for RV64
    let rd = (instr >> 7u) & 31u;
    let rs1 = (instr >> 15u) & 31u;

    if (rd != 0u) {
        (*cpu).regs[rd] = shr64u((*cpu).regs[rs1], shamt);
    }
    (*cpu).pc = add64((*cpu).pc, vec2<u32>(4u, 0u));
}

// SRAI (Shift Right Arithmetic Immediate)
fn execute_srai(cpu: ptr<function, RiscvCPU>, instr: u32) {
    let shamt = (instr >> 20u) & 63u;  // shamt[5:0] for RV64
    let rd = (instr >> 7u) & 31u;
    let rs1 = (instr >> 15u) & 31u;

    if (rd != 0u) {
        (*cpu).regs[rd] = shr64s((*cpu).regs[rs1], shamt);
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
    if (funct3 == 0u) { take_branch = eq64(v1, v2); }        // BEQ
    else if (funct3 == 1u) { take_branch = !eq64(v1, v2); }  // BNE
    else if (funct3 == 4u) { take_branch = lt64s(v1, v2); }  // BLT (signed)
    else if (funct3 == 5u) { take_branch = !lt64s(v1, v2); } // BGE (signed, >=)
    else if (funct3 == 6u) { take_branch = lt64(v1, v2); }   // BLTU
    else if (funct3 == 7u) { take_branch = !lt64(v1, v2); }  // BGEU (>=)

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

// SUB (Subtract Register)
fn execute_sub(cpu: ptr<function, RiscvCPU>, instr: u32) {
    let rd = (instr >> 7u) & 31u;
    let rs1 = (instr >> 15u) & 31u;
    let rs2 = (instr >> 20u) & 31u;

    if (rd != 0u) {
        (*cpu).regs[rd] = sub64((*cpu).regs[rs1], (*cpu).regs[rs2]);
    }

    (*cpu).pc = add64((*cpu).pc, vec2<u32>(4u, 0u));
}

// AND (AND Register)
fn execute_and(cpu: ptr<function, RiscvCPU>, instr: u32) {
    let rd = (instr >> 7u) & 31u;
    let rs1 = (instr >> 15u) & 31u;
    let rs2 = (instr >> 20u) & 31u;

    if (rd != 0u) {
        (*cpu).regs[rd].x = (*cpu).regs[rs1].x & (*cpu).regs[rs2].x;
        (*cpu).regs[rd].y = (*cpu).regs[rs1].y & (*cpu).regs[rs2].y;
    }

    (*cpu).pc = add64((*cpu).pc, vec2<u32>(4u, 0u));
}

// OR (OR Register)
fn execute_or(cpu: ptr<function, RiscvCPU>, instr: u32) {
    let rd = (instr >> 7u) & 31u;
    let rs1 = (instr >> 15u) & 31u;
    let rs2 = (instr >> 20u) & 31u;

    if (rd != 0u) {
        (*cpu).regs[rd].x = (*cpu).regs[rs1].x | (*cpu).regs[rs2].x;
        (*cpu).regs[rd].y = (*cpu).regs[rs1].y | (*cpu).regs[rs2].y;
    }

    (*cpu).pc = add64((*cpu).pc, vec2<u32>(4u, 0u));
}

// XOR (XOR Register)
fn execute_xor(cpu: ptr<function, RiscvCPU>, instr: u32) {
    let rd = (instr >> 7u) & 31u;
    let rs1 = (instr >> 15u) & 31u;
    let rs2 = (instr >> 20u) & 31u;

    if (rd != 0u) {
        (*cpu).regs[rd].x = (*cpu).regs[rs1].x ^ (*cpu).regs[rs2].x;
        (*cpu).regs[rd].y = (*cpu).regs[rs1].y ^ (*cpu).regs[rs2].y;
    }

    (*cpu).pc = add64((*cpu).pc, vec2<u32>(4u, 0u));
}

// SLL (Shift Left Logical)
fn execute_sll(cpu: ptr<function, RiscvCPU>, instr: u32) {
    let rd = (instr >> 7u) & 31u;
    let rs1 = (instr >> 15u) & 31u;
    let rs2 = (instr >> 20u) & 31u;
    let shamt = (*cpu).regs[rs2].x & 63u;  // shamt[5:0] for RV64

    if (rd != 0u) {
        (*cpu).regs[rd] = shl64((*cpu).regs[rs1], shamt);
    }
    (*cpu).pc = add64((*cpu).pc, vec2<u32>(4u, 0u));
}

// SRL (Shift Right Logical)
fn execute_srl(cpu: ptr<function, RiscvCPU>, instr: u32) {
    let rd = (instr >> 7u) & 31u;
    let rs1 = (instr >> 15u) & 31u;
    let rs2 = (instr >> 20u) & 31u;
    let shamt = (*cpu).regs[rs2].x & 63u;  // shamt[5:0] for RV64

    if (rd != 0u) {
        (*cpu).regs[rd] = shr64u((*cpu).regs[rs1], shamt);
    }
    (*cpu).pc = add64((*cpu).pc, vec2<u32>(4u, 0u));
}

// SRA (Shift Right Arithmetic)
fn execute_sra(cpu: ptr<function, RiscvCPU>, instr: u32) {
    let rd = (instr >> 7u) & 31u;
    let rs1 = (instr >> 15u) & 31u;
    let rs2 = (instr >> 20u) & 31u;
    let shamt = (*cpu).regs[rs2].x & 63u;  // shamt[5:0] for RV64

    if (rd != 0u) {
        (*cpu).regs[rd] = shr64s((*cpu).regs[rs1], shamt);
    }
    (*cpu).pc = add64((*cpu).pc, vec2<u32>(4u, 0u));
}

// SLT (Set Less Than - signed)
fn execute_slt(cpu: ptr<function, RiscvCPU>, instr: u32) {
    let rd = (instr >> 7u) & 31u;
    let rs1 = (instr >> 15u) & 31u;
    let rs2 = (instr >> 20u) & 31u;

    if (rd != 0u) {
        let v1 = (*cpu).regs[rs1];
        let v2 = (*cpu).regs[rs2];

        // Signed comparison: check if rs1 < rs2
        let v1_neg = (v1.y & 0x80000000u) != 0u;
        let v2_neg = (v2.y & 0x80000000u) != 0u;

        var is_less = false;
        if (v1_neg && !v2_neg) {
            is_less = true;  // Negative < positive
        } else if (!v1_neg && v2_neg) {
            is_less = false; // Positive < negative
        } else {
            // Same sign - compare high then low
            if (v1.y < v2.y) {
                is_less = true;
            } else if (v1.y == v2.y) {
                is_less = v1.x < v2.x;
            }
        }

        (*cpu).regs[rd] = vec2<u32>(select(0u, 1u, is_less), 0u);
    }
    (*cpu).pc = add64((*cpu).pc, vec2<u32>(4u, 0u));
}

// SLTU (Set Less Than - unsigned)
fn execute_sltu(cpu: ptr<function, RiscvCPU>, instr: u32) {
    let rd = (instr >> 7u) & 31u;
    let rs1 = (instr >> 15u) & 31u;
    let rs2 = (instr >> 20u) & 31u;

    if (rd != 0u) {
        let is_less = lt64((*cpu).regs[rs1], (*cpu).regs[rs2]);
        (*cpu).regs[rd] = vec2<u32>(select(0u, 1u, is_less), 0u);
    }
    (*cpu).pc = add64((*cpu).pc, vec2<u32>(4u, 0u));
}

// ============================================================================
// 32-BIT *W INSTRUCTIONS (OP_IMM_32 = 27, OP_32 = 59)
// These operate on low 32 bits only, then sign-extend to 64 bits
// ============================================================================

// ADDIW (Add Immediate Word)
fn execute_addiw(cpu: ptr<function, RiscvCPU>, instr: u32) {
    let decoded = decode_i_type(instr);
    if (decoded.rd != 0u) {
        let result_32 = (*cpu).regs[decoded.rs1].x + decoded.imm;
        (*cpu).regs[decoded.rd] = sext32_to_64(result_32);
    }
    (*cpu).pc = add64((*cpu).pc, vec2<u32>(4u, 0u));
}

// SLLIW (Shift Left Logical Immediate Word)
fn execute_slliw(cpu: ptr<function, RiscvCPU>, instr: u32) {
    let shamt = (instr >> 20u) & 31u;  // shamt[4:0] for W variants
    let rd = (instr >> 7u) & 31u;
    let rs1 = (instr >> 15u) & 31u;

    if (rd != 0u) {
        let result_32 = (*cpu).regs[rs1].x << shamt;
        (*cpu).regs[rd] = sext32_to_64(result_32);
    }
    (*cpu).pc = add64((*cpu).pc, vec2<u32>(4u, 0u));
}

// SRLIW (Shift Right Logical Immediate Word)
fn execute_srliw(cpu: ptr<function, RiscvCPU>, instr: u32) {
    let shamt = (instr >> 20u) & 31u;  // shamt[4:0] for W variants
    let rd = (instr >> 7u) & 31u;
    let rs1 = (instr >> 15u) & 31u;

    if (rd != 0u) {
        let result_32 = (*cpu).regs[rs1].x >> shamt;
        (*cpu).regs[rd] = sext32_to_64(result_32);
    }
    (*cpu).pc = add64((*cpu).pc, vec2<u32>(4u, 0u));
}

// SRAIW (Shift Right Arithmetic Immediate Word)
fn execute_sraiw(cpu: ptr<function, RiscvCPU>, instr: u32) {
    let shamt = (instr >> 20u) & 31u;  // shamt[4:0] for W variants
    let rd = (instr >> 7u) & 31u;
    let rs1 = (instr >> 15u) & 31u;

    if (rd != 0u) {
        // Use i32 for arithmetic right shift, then convert back
        let val_i32 = bitcast<i32>((*cpu).regs[rs1].x);
        let result_i32 = val_i32 >> shamt;
        (*cpu).regs[rd] = sext32_to_64(bitcast<u32>(result_i32));
    }
    (*cpu).pc = add64((*cpu).pc, vec2<u32>(4u, 0u));
}

// ADDW (Add Word)
fn execute_addw(cpu: ptr<function, RiscvCPU>, instr: u32) {
    let rd = (instr >> 7u) & 31u;
    let rs1 = (instr >> 15u) & 31u;
    let rs2 = (instr >> 20u) & 31u;

    if (rd != 0u) {
        let result_32 = (*cpu).regs[rs1].x + (*cpu).regs[rs2].x;
        (*cpu).regs[rd] = sext32_to_64(result_32);
    }
    (*cpu).pc = add64((*cpu).pc, vec2<u32>(4u, 0u));
}

// SUBW (Subtract Word)
fn execute_subw(cpu: ptr<function, RiscvCPU>, instr: u32) {
    let rd = (instr >> 7u) & 31u;
    let rs1 = (instr >> 15u) & 31u;
    let rs2 = (instr >> 20u) & 31u;

    if (rd != 0u) {
        let result_32 = (*cpu).regs[rs1].x - (*cpu).regs[rs2].x;
        (*cpu).regs[rd] = sext32_to_64(result_32);
    }
    (*cpu).pc = add64((*cpu).pc, vec2<u32>(4u, 0u));
}

// SLLW (Shift Left Logical Word)
fn execute_sllw(cpu: ptr<function, RiscvCPU>, instr: u32) {
    let rd = (instr >> 7u) & 31u;
    let rs1 = (instr >> 15u) & 31u;
    let rs2 = (instr >> 20u) & 31u;
    let shamt = (*cpu).regs[rs2].x & 31u;  // shamt[4:0] for W variants

    if (rd != 0u) {
        let result_32 = (*cpu).regs[rs1].x << shamt;
        (*cpu).regs[rd] = sext32_to_64(result_32);
    }
    (*cpu).pc = add64((*cpu).pc, vec2<u32>(4u, 0u));
}

// SRLW (Shift Right Logical Word)
fn execute_srlw(cpu: ptr<function, RiscvCPU>, instr: u32) {
    let rd = (instr >> 7u) & 31u;
    let rs1 = (instr >> 15u) & 31u;
    let rs2 = (instr >> 20u) & 31u;
    let shamt = (*cpu).regs[rs2].x & 31u;  // shamt[4:0] for W variants

    if (rd != 0u) {
        let result_32 = (*cpu).regs[rs1].x >> shamt;
        (*cpu).regs[rd] = sext32_to_64(result_32);
    }
    (*cpu).pc = add64((*cpu).pc, vec2<u32>(4u, 0u));
}

// SRAW (Shift Right Arithmetic Word)
fn execute_sraw(cpu: ptr<function, RiscvCPU>, instr: u32) {
    let rd = (instr >> 7u) & 31u;
    let rs1 = (instr >> 15u) & 31u;
    let rs2 = (instr >> 20u) & 31u;
    let shamt = (*cpu).regs[rs2].x & 31u;  // shamt[4:0] for W variants

    if (rd != 0u) {
        // Use i32 for arithmetic right shift, then convert back
        let val_i32 = bitcast<i32>((*cpu).regs[rs1].x);
        let result_i32 = val_i32 >> shamt;
        (*cpu).regs[rd] = sext32_to_64(bitcast<u32>(result_i32));
    }
    (*cpu).pc = add64((*cpu).pc, vec2<u32>(4u, 0u));
}

// ============================================================================
// M EXTENSION (funct7 = 1): MUL/MULH/MULHSU/MULHU/DIV/DIVU/REM/REMU + W forms
// ============================================================================

fn execute_muldiv(cpu: ptr<function, RiscvCPU>, instr: u32) {
    let rd = (instr >> 7u) & 31u;
    let rs1 = (instr >> 15u) & 31u;
    let rs2 = (instr >> 20u) & 31u;
    let funct3 = (instr >> 12u) & 7u;

    if (rd != 0u) {
        let a = (*cpu).regs[rs1];
        let b = (*cpu).regs[rs2];
        var result = vec2<u32>(0u, 0u);

        if (funct3 == 0u) {        // MUL
            result = mul64_low(a, b);
        } else if (funct3 == 1u) { // MULH
            result = mulh64(a, b);
        } else if (funct3 == 2u) { // MULHSU
            result = mulhsu64(a, b);
        } else if (funct3 == 3u) { // MULHU
            result = mulhu64(a, b);
        } else if (funct3 == 4u) { // DIV
            result = divrems64(a, b).q;
        } else if (funct3 == 5u) { // DIVU
            result = divremu64(a, b).q;
        } else if (funct3 == 6u) { // REM
            result = divrems64(a, b).r;
        } else {                   // REMU
            result = divremu64(a, b).r;
        }
        (*cpu).regs[rd] = result;
    }
    (*cpu).pc = add64((*cpu).pc, vec2<u32>(4u, 0u));
}

// 32-bit signed divide following RISC-V semantics (result before sign-extension)
fn div32s(a: u32, b: u32) -> u32 {
    if (b == 0u) { return 0xFFFFFFFFu; }                        // q = -1
    if (a == 0x80000000u && b == 0xFFFFFFFFu) { return a; }     // INT32_MIN / -1
    let a_neg = (a & 0x80000000u) != 0u;
    let b_neg = (b & 0x80000000u) != 0u;
    let ua = select(a, 0u - a, a_neg);
    let ub = select(b, 0u - b, b_neg);
    let uq = ua / ub;
    return select(uq, 0u - uq, a_neg != b_neg);
}

fn rem32s(a: u32, b: u32) -> u32 {
    if (b == 0u) { return a; }
    if (a == 0x80000000u && b == 0xFFFFFFFFu) { return 0u; }
    let a_neg = (a & 0x80000000u) != 0u;
    let b_neg = (b & 0x80000000u) != 0u;
    let ua = select(a, 0u - a, a_neg);
    let ub = select(b, 0u - b, b_neg);
    let ur = ua % ub;
    return select(ur, 0u - ur, a_neg);
}

// MULW/DIVW/DIVUW/REMW/REMUW: 32-bit operate, sign-extend result to 64
fn execute_muldiv_w(cpu: ptr<function, RiscvCPU>, instr: u32) {
    let rd = (instr >> 7u) & 31u;
    let rs1 = (instr >> 15u) & 31u;
    let rs2 = (instr >> 20u) & 31u;
    let funct3 = (instr >> 12u) & 7u;

    if (rd != 0u) {
        let a = (*cpu).regs[rs1].x;
        let b = (*cpu).regs[rs2].x;
        var result32 = 0u;

        if (funct3 == 0u) {        // MULW (low 32 bits; u32 wrap == i32 wrap)
            result32 = a * b;
        } else if (funct3 == 4u) { // DIVW
            result32 = div32s(a, b);
        } else if (funct3 == 5u) { // DIVUW
            result32 = select(a / max(b, 1u), 0xFFFFFFFFu, b == 0u);
        } else if (funct3 == 6u) { // REMW
            result32 = rem32s(a, b);
        } else {                   // REMUW
            result32 = select(a % max(b, 1u), a, b == 0u);
        }
        (*cpu).regs[rd] = sext32_to_64(result32);
    }
    (*cpu).pc = add64((*cpu).pc, vec2<u32>(4u, 0u));
}

// ============================================================================
// CSR FILE + TRAP MACHINERY
// ============================================================================

// Read a CSR. Unknown CSRs read as 0 (no trap) so kernel/firmware probing
// of PMP, delegation, and counter CSRs doesn't kill the boot.
// sstatus/sie/sip are architectural views of mstatus/mie/mip, not storage.
fn csr_read(cpu: ptr<function, RiscvCPU>, addr: u32) -> vec2<u32> {
    switch (addr) {
        case CSR_MHARTID: { return vec2<u32>(0u, 0u); }  // Always hart 0
        case CSR_MSTATUS: { return (*cpu).mstatus; }
        case CSR_MISA: {
            // MXL=2 (RV64) in bits [63:62]; extensions A, I, M, S, U
            let ext = (1u << 0u) | (1u << 8u) | (1u << 12u) | (1u << 18u) | (1u << 20u);
            return vec2<u32>(ext, 0x80000000u);
        }
        case CSR_MIE: { return (*cpu).mie; }
        case CSR_MTVEC: { return (*cpu).mtvec; }
        case CSR_MSCRATCH: { return (*cpu).mscratch; }
        case CSR_MEPC: { return (*cpu).mepc; }
        case CSR_MCAUSE: { return (*cpu).mcause; }
        case CSR_MTVAL: { return (*cpu).mtval; }
        case CSR_MIP: { return (*cpu).mip; }
        case CSR_MEDELEG: { return (*cpu).medeleg; }
        case CSR_MIDELEG: { return (*cpu).mideleg; }
        case CSR_SSTATUS: {
            // Restricted view of mstatus; UXL reads as 2 (RV64)
            return vec2<u32>((*cpu).mstatus.x & SSTATUS_MASK_LO,
                             ((*cpu).mstatus.y & SSTATUS_MASK_HI) | 0x2u);
        }
        case CSR_SIE: {
            return vec2<u32>((*cpu).mie.x & (*cpu).mideleg.x,
                             (*cpu).mie.y & (*cpu).mideleg.y);
        }
        case CSR_SIP: {
            return vec2<u32>((*cpu).mip.x & (*cpu).mideleg.x,
                             (*cpu).mip.y & (*cpu).mideleg.y);
        }
        case CSR_STVEC: { return (*cpu).stvec; }
        case CSR_SSCRATCH: { return (*cpu).sscratch; }
        case CSR_SEPC: { return (*cpu).sepc; }
        case CSR_SCAUSE: { return (*cpu).scause; }
        case CSR_STVAL: { return (*cpu).stval; }
        case CSR_SATP: { return (*cpu).satp; }
        case CSR_MCYCLE, CSR_MINSTRET, CSR_CYCLE, CSR_TIME, CSR_INSTRET: {
            return vec2<u32>((*cpu).instr_count, 0u);
        }
        case CSR_MVENDORID, CSR_MARCHID, CSR_MIMPID: { return vec2<u32>(0u, 0u); }
        default: { return vec2<u32>(0u, 0u); }
    }
}

// Write a CSR. Read-only and unknown CSRs are silently ignored.
fn csr_write(cpu: ptr<function, RiscvCPU>, addr: u32, val: vec2<u32>) {
    switch (addr) {
        case CSR_MSTATUS: { (*cpu).mstatus = val; }
        case CSR_MIE: { (*cpu).mie = val; }
        case CSR_MTVEC: { (*cpu).mtvec = val; }
        case CSR_MSCRATCH: { (*cpu).mscratch = val; }
        case CSR_MEPC: { (*cpu).mepc = vec2<u32>(val.x & 0xFFFFFFFEu, val.y); }
        case CSR_MCAUSE: { (*cpu).mcause = val; }
        case CSR_MTVAL: { (*cpu).mtval = val; }
        case CSR_MIP: { (*cpu).mip = val; }
        case CSR_MEDELEG: { (*cpu).medeleg = val; }
        case CSR_MIDELEG: { (*cpu).mideleg = val; }
        case CSR_SSTATUS: {
            // Only the S-view bits of mstatus are writable through sstatus.
            // CRITICAL: Preserve MIE bit (bit 3) - S-mode writes to sstatus must not
            // affect M-mode interrupt enable, otherwise push_off/pop_off will fail.
            // SSTATUS_MASK_LO = 0x000DE762 excludes bit 3 (MIE), so we need to
            // preserve it explicitly when in M-mode.
            let preserve_mie = (*cpu).mstatus.x & (1u << 3u);
            (*cpu).mstatus.x = ((*cpu).mstatus.x & ~SSTATUS_MASK_LO) | (val.x & SSTATUS_MASK_LO) | preserve_mie;
            (*cpu).mstatus.y = ((*cpu).mstatus.y & ~SSTATUS_MASK_HI) | (val.y & SSTATUS_MASK_HI);
        }
        case CSR_SIE: {
            // S-mode may only touch interrupt bits delegated via mideleg
            (*cpu).mie.x = ((*cpu).mie.x & ~(*cpu).mideleg.x) | (val.x & (*cpu).mideleg.x);
            (*cpu).mie.y = ((*cpu).mie.y & ~(*cpu).mideleg.y) | (val.y & (*cpu).mideleg.y);
        }
        case CSR_SIP: {
            (*cpu).mip.x = ((*cpu).mip.x & ~(*cpu).mideleg.x) | (val.x & (*cpu).mideleg.x);
            (*cpu).mip.y = ((*cpu).mip.y & ~(*cpu).mideleg.y) | (val.y & (*cpu).mideleg.y);
        }
        case CSR_STVEC: { (*cpu).stvec = val; }
        case CSR_SSCRATCH: { (*cpu).sscratch = val; }
        case CSR_SEPC: { (*cpu).sepc = vec2<u32>(val.x & 0xFFFFFFFEu, val.y); }
        case CSR_SCAUSE: { (*cpu).scause = val; }
        case CSR_STVAL: { (*cpu).stval = val; }
        case CSR_SATP: { (*cpu).satp = val; }
        default: { }
    }
}

// Enter a trap handler. Exceptions raised in S/U mode whose cause bit is set
// in medeleg vector to S-mode (stvec); everything else goes to M-mode (mtvec).
fn take_trap(cpu: ptr<function, RiscvCPU>, cause: vec2<u32>, tval: vec2<u32>) {
    let code = cause.x & 31u;
    let delegated = (*cpu).priv_mode != PRIV_M &&
                    (((*cpu).medeleg.x >> code) & 1u) != 0u;

    if (delegated) {
        (*cpu).sepc = (*cpu).pc;
        (*cpu).scause = cause;
        (*cpu).stval = tval;

        // mstatus: SPIE <- SIE, SIE <- 0, SPP <- (was S-mode ? 1 : 0)
        var ms = (*cpu).mstatus.x;
        let sie = (ms >> MSTATUS_SIE_BIT) & 1u;
        let spp = select(0u, 1u, (*cpu).priv_mode == PRIV_S);
        ms = ms & ~((1u << MSTATUS_SPIE_BIT) | (1u << MSTATUS_SIE_BIT) | (1u << MSTATUS_SPP_BIT));
        ms = ms | (sie << MSTATUS_SPIE_BIT) | (spp << MSTATUS_SPP_BIT);
        (*cpu).mstatus.x = ms;

        (*cpu).priv_mode = PRIV_S;
        let target_pc = vec2<u32>((*cpu).stvec.x & 0xFFFFFFFCu, (*cpu).stvec.y);
        if (target_pc.x == 0u && target_pc.y == 0u) {
            (*cpu).running = 0u; // Halt on unhandled S-mode trap
            return;
        }
        (*cpu).pc = target_pc;
    } else {
        (*cpu).mepc = (*cpu).pc;
        (*cpu).mcause = cause;
        (*cpu).mtval = tval;

        // mstatus: MPIE <- MIE, MIE <- 0, MPP <- current privilege
        var ms = (*cpu).mstatus.x;
        let mie = (ms >> MSTATUS_MIE_BIT) & 1u;
        ms = ms & ~((1u << MSTATUS_MPIE_BIT) | (1u << MSTATUS_MIE_BIT) | (3u << MSTATUS_MPP_SHIFT));
        ms = ms | (mie << MSTATUS_MPIE_BIT) | ((*cpu).priv_mode << MSTATUS_MPP_SHIFT);
        (*cpu).mstatus.x = ms;

        (*cpu).priv_mode = PRIV_M;
        let target_pc = vec2<u32>((*cpu).mtvec.x & 0xFFFFFFFCu, (*cpu).mtvec.y);
        if (target_pc.x == 0u && target_pc.y == 0u) {
            (*cpu).running = 0u; // Halt on unhandled M-mode trap
            return;
        }
        (*cpu).pc = target_pc;
    }
}

// Illegal instruction: trap if a reachable handler is installed, otherwise
// halt with the instruction word as a debug marker (old behavior)
fn handle_illegal(cpu: ptr<function, RiscvCPU>, instr: u32, cpu_id: u32) {
    let delegated = (*cpu).priv_mode != PRIV_M &&
                    (((*cpu).medeleg.x >> CAUSE_ILLEGAL_INSTR) & 1u) != 0u;
    let handler_x = select((*cpu).mtvec.x, (*cpu).stvec.x, delegated);
    let handler_y = select((*cpu).mtvec.y, (*cpu).stvec.y, delegated);
    if (handler_x != 0u || handler_y != 0u) {
        take_trap(cpu, vec2<u32>(CAUSE_ILLEGAL_INSTR, 0u), vec2<u32>(instr, 0u));
    } else {
        output[cpu_id * 256u] = instr;
        (*cpu).running = 0u;
    }
}

// CSRRW/CSRRS/CSRRC and their immediate forms (funct3 bit 2 = immediate).
// Enforces the privilege encoded in the CSR address: bits [9:8] are the
// minimum privilege, bits [11:10] == 3 marks the CSR read-only.
fn execute_csr(cpu: ptr<function, RiscvCPU>, instr: u32, cpu_id: u32) {
    let funct3 = (instr >> 12u) & 7u;
    let rd = (instr >> 7u) & 31u;
    let rs1_field = (instr >> 15u) & 31u;  // rs1 register OR 5-bit zimm
    let csr_addr = instr >> 20u;

    // Privilege check: S-mode touching an M-mode CSR is an illegal instruction
    let min_priv = (csr_addr >> 8u) & 3u;
    if ((*cpu).priv_mode < min_priv) {
        handle_illegal(cpu, instr, cpu_id);
        return;
    }

    let op = funct3 & 3u;
    let writes = (op == 1u) || (rs1_field != 0u);
    if (writes && ((csr_addr >> 10u) & 3u) == 3u) {
        // Write to a read-only CSR (0xCxx/0xFxx ranges)
        handle_illegal(cpu, instr, cpu_id);
        return;
    }

    let old = csr_read(cpu, csr_addr);

    var src: vec2<u32>;
    if ((funct3 & 4u) != 0u) {
        src = vec2<u32>(rs1_field, 0u);  // Zero-extended 5-bit immediate
    } else {
        src = (*cpu).regs[rs1_field];
    }

    if (op == 1u) {                        // CSRRW: unconditional write
        csr_write(cpu, csr_addr, src);
    } else if (op == 2u && rs1_field != 0u) {  // CSRRS: set bits
        csr_write(cpu, csr_addr, vec2<u32>(old.x | src.x, old.y | src.y));
    } else if (op == 3u && rs1_field != 0u) {  // CSRRC: clear bits
        csr_write(cpu, csr_addr, vec2<u32>(old.x & ~src.x, old.y & ~src.y));
    }

    if (rd != 0u) {
        (*cpu).regs[rd] = old;
    }
    (*cpu).pc = add64((*cpu).pc, vec2<u32>(4u, 0u));
}

// MRET: return from M-mode trap handler
fn execute_mret(cpu: ptr<function, RiscvCPU>) {
    var ms = (*cpu).mstatus.x;
    let mpie = (ms >> MSTATUS_MPIE_BIT) & 1u;
    let mpp = (ms >> MSTATUS_MPP_SHIFT) & 3u;

    ms = (ms & ~(1u << MSTATUS_MIE_BIT)) | (mpie << MSTATUS_MIE_BIT);  // MIE <- MPIE
    ms = ms | (1u << MSTATUS_MPIE_BIT);                                // MPIE <- 1
    ms = ms & ~(3u << MSTATUS_MPP_SHIFT);                              // MPP <- U
    (*cpu).mstatus.x = ms;

    (*cpu).priv_mode = mpp;
    (*cpu).pc = (*cpu).mepc;
}

// SRET: return from S-mode trap handler
fn execute_sret(cpu: ptr<function, RiscvCPU>) {
    var ms = (*cpu).mstatus.x;
    let spie = (ms >> MSTATUS_SPIE_BIT) & 1u;
    let spp = (ms >> MSTATUS_SPP_BIT) & 1u;

    ms = (ms & ~(1u << MSTATUS_SIE_BIT)) | (spie << MSTATUS_SIE_BIT);  // SIE <- SPIE
    ms = ms | (1u << MSTATUS_SPIE_BIT);                                // SPIE <- 1
    ms = ms & ~(1u << MSTATUS_SPP_BIT);                                // SPP <- U
    (*cpu).mstatus.x = ms;

    (*cpu).priv_mode = spp;  // 1 = S, 0 = U
    (*cpu).pc = (*cpu).sepc;
}

// OP_LOAD (LB, LH, LW, LBU, LHU, LD, LWU)
fn execute_load(satp: vec2<u32>, cpu: ptr<function, RiscvCPU>, instr: u32) {
    let decoded = decode_i_type(instr);
    let va = add64((*cpu).regs[decoded.rs1], sext32_to_64(decoded.imm));
    
    // Translate virtual address
    let pa = translate_va(cpu, va);
    
    // Check for page fault
    if (pa.x == 0xFFFFFFFFu) {
        take_trap(cpu, vec2<u32>(CAUSE_LOAD_PAGE_FAULT, 0u), va);
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

    // PLIC register reads
    if (is_plic_addr(pa)) {
        let offset = pa.x - PLIC_BASE;
        var val = 0u;

        // Pending bits (IRQ 0-31)
        if (offset >= 0x1000u && offset < 0x1004u) {
            val = (*cpu).plic_pending;
        }
        // Enable bits for hart 0, mode S
        else if (offset >= 0x2080u && offset < 0x2084u) {
            val = (*cpu).plic_enable;
        }
        // Claim/Complete register (hart 0, mode S)
        else if (offset == 0x200004u) {
            // Claim: return lowest-priority pending+enabled IRQ
            let pending_enabled = (*cpu).plic_pending & (*cpu).plic_enable;
            if (pending_enabled != 0u) {
                // Find lowest set bit
                var irq = 0u;
                for (var i = 0u; i < 32u; i = i + 1u) {
                    if ((pending_enabled & (1u << i)) != 0u) {
                        irq = i;
                        break;
                    }
                }
                val = irq;
                (*cpu).plic_claimed = irq;
            } else {
                val = 0u;
            }
        }

        if (decoded.rd != 0u) {
            (*cpu).regs[decoded.rd] = vec2<u32>(val, 0u);
        }
        (*cpu).pc = add64((*cpu).pc, vec2<u32>(4u, 0u));
        return;
    }

    // VirtIO MMIO stub
    if (pa.x >= 0x10001000u && pa.x < 0x10002000u) {
        let offset = pa.x - 0x10001000u;
        var val = 0u;
        if (offset == 0x0u) { val = 0x74726976u; } // Magic
        else if (offset == 0x4u) { val = 2u; }      // Version
        else if (offset == 0x8u) { val = 2u; }      // Device ID (Block)
        else if (offset == 0xcu) { val = 0x554d4551u; } // Vendor (QEMU)
        else if (offset == 0x10u) { val = 0u; }     // DeviceFeatures
        else if (offset == 0x34u) { val = 8u; }     // QueueNumMax
        else if (offset == 0x44u) { val = 0u; }     // QueueReady
        else if (offset == 0x60u) { val = 0u; }     // InterruptStatus
        else if (offset == 0x70u) { val = (*cpu).virtio_status; } // Status
        
        if (decoded.rd != 0u) {
            (*cpu).regs[decoded.rd] = vec2<u32>(val, 0u);
        }
        (*cpu).pc = add64((*cpu).pc, vec2<u32>(4u, 0u));
        return;
    }
    
    let byte_offset = pa.x & 3u;
    let word = read_phys_word(pa);

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
        value.y = read_phys_word(add64(pa, vec2<u32>(4u, 0u)));
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
fn execute_store(satp: vec2<u32>, cpu: ptr<function, RiscvCPU>, instr: u32, cpu_id: u32) {
    let decoded = decode_s_type(instr);
    let va = add64((*cpu).regs[decoded.rs1], sext32_to_64(decoded.imm));
    
    // Translate virtual address
    let pa = translate_va(cpu, va);
    
    // Check for page fault
    if (pa.x == 0xFFFFFFFFu) {
        take_trap(cpu, vec2<u32>(CAUSE_STORE_PAGE_FAULT, 0u), va);
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

    // PLIC register writes
    if (is_plic_addr(pa)) {
        let offset = pa.x - PLIC_BASE;

        // Pending bits: ignore writes (read-only)
        // Enable bits for hart 0, mode S
        if (offset >= 0x2080u && offset < 0x2084u) {
            (*cpu).plic_enable = (*cpu).regs[decoded.rs2].x;
        }
        // Claim/Complete register (write completes interrupt)
        else if (offset == 0x200004u) {
            let completed_irq = (*cpu).regs[decoded.rs2].x;
            if (completed_irq == (*cpu).plic_claimed) {
                // Clear the pending bit
                (*cpu).plic_pending = (*cpu).plic_pending & ~(1u << completed_irq);
                (*cpu).plic_claimed = 0u;
            }
        }

        (*cpu).pc = add64((*cpu).pc, vec2<u32>(4u, 0u));
        return;
    }

    // VirtIO MMIO stub
    if (pa.x >= 0x10001000u && pa.x < 0x10002000u) {
        let offset = pa.x - 0x10001000u;
        if (offset == 0x70u) {
            (*cpu).virtio_status = (*cpu).regs[decoded.rs2].x;
        } else if (offset == VIRTIO_QUEUE_NOTIFY) {
            // QueueNotify (kick): synchronously process request
            // For now: stub that just raises the interrupt
            plic_raise_irq(cpu, VIRTIO_IRQ);
        }
        (*cpu).pc = add64((*cpu).pc, vec2<u32>(4u, 0u));
        return;
    }
    
    let byte_offset = pa.x & 3u;
    let old_word = read_phys_word(pa);
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
        write_phys_word(add64(pa, vec2<u32>(4u, 0u)), store_val.y);
    }

    write_phys_word(pa, new_word);
    (*cpu).pc = add64((*cpu).pc, vec2<u32>(4u, 0u));
}

// ============================================================================
// A EXTENSION: ATOMIC MEMORY OPERATIONS
// ============================================================================

// Load Reserved (LR.W/LR.D) - on single hart, trivially succeeds.
// funct3: 2 = .W (32-bit, sign-extended into rd), 3 = .D (64-bit)
fn execute_lr(cpu: ptr<function, RiscvCPU>, instr: u32, funct3: u32) {
    let rd = (instr >> 7u) & 31u;
    let rs1 = (instr >> 15u) & 31u;
    let va = (*cpu).regs[rs1];

    let pa = translate_va(cpu, va);
    if (pa.x == 0xFFFFFFFFu) {
        take_trap(cpu, vec2<u32>(CAUSE_LOAD_PAGE_FAULT, 0u), va);
        return;
    }
    if (is_uart_addr(pa)) {
        take_trap(cpu, vec2<u32>(CAUSE_LOAD_PAGE_FAULT, 0u), va);
        return;
    }

    if (funct3 == 3u) {
        let low_val = read_phys_word(pa);
        let high_val = read_phys_word(add64(pa, vec2<u32>(4u, 0u)));
        if (rd != 0u) {
            (*cpu).regs[rd] = vec2<u32>(low_val, high_val);
        }
    } else {
        let val32 = read_phys_word(pa);
        if (rd != 0u) {
            (*cpu).regs[rd] = sext32_to_64(val32);
        }
    }

    // Reservation set (single hart: always valid on the matching SC)
    (*cpu).pc = add64((*cpu).pc, vec2<u32>(4u, 0u));
}

// Store Conditional (SC.W/SC.D) - on single hart, trivially succeeds.
fn execute_sc(cpu: ptr<function, RiscvCPU>, instr: u32, funct3: u32) {
    let rd = (instr >> 7u) & 31u;
    let rs1 = (instr >> 15u) & 31u;
    let rs2 = (instr >> 20u) & 31u;
    let va = (*cpu).regs[rs1];
    let store_val = (*cpu).regs[rs2];

    let pa = translate_va(cpu, va);
    if (pa.x == 0xFFFFFFFFu) {
        take_trap(cpu, vec2<u32>(CAUSE_STORE_PAGE_FAULT, 0u), va);
        return;
    }
    if (is_uart_addr(pa)) {
        take_trap(cpu, vec2<u32>(CAUSE_STORE_PAGE_FAULT, 0u), va);
        return;
    }

    if (funct3 == 3u) {
        write_phys_word(pa, store_val.x);
        write_phys_word(add64(pa, vec2<u32>(4u, 0u)), store_val.y);
    } else {
        write_phys_word(pa, store_val.x);
    }

    // SC returns 0 on success, non-zero on failure (single hart: always succeeds)
    if (rd != 0u) {
        (*cpu).regs[rd] = vec2<u32>(0u, 0u);
    }

    (*cpu).pc = add64((*cpu).pc, vec2<u32>(4u, 0u));
}

// AMO.W/AMO.D: atomic read-modify-write.
// funct5 (real RISC-V encoding, instr[31:27]):
//   0=ADD 1=SWAP 2=LR 4=XOR 8=OR 12=AND 16=MIN 20=MAX 24=MINU 28=MAXU
// funct3: 2 = .W (32-bit, sign-extended into rd), 3 = .D (64-bit)
fn execute_amo(cpu: ptr<function, RiscvCPU>, instr: u32, funct3: u32, funct5: u32) {
    let rd = (instr >> 7u) & 31u;
    let rs1 = (instr >> 15u) & 31u;
    let rs2 = (instr >> 20u) & 31u;

    let va = (*cpu).regs[rs1];
    let pa = translate_va(cpu, va);
    if (pa.x == 0xFFFFFFFFu) {
        take_trap(cpu, vec2<u32>(CAUSE_LOAD_PAGE_FAULT, 0u), va);
        return;
    }
    if (is_uart_addr(pa)) {
        take_trap(cpu, vec2<u32>(CAUSE_LOAD_PAGE_FAULT, 0u), va);
        return;
    }

    let src = (*cpu).regs[rs2];
    let is_word = funct3 != 3u;

    if (is_word) {
        let mem_val32 = read_phys_word(pa);
        let src32 = src.x;
        var new_val32 = mem_val32;

        if (funct5 == 0u) { new_val32 = mem_val32 + src32; }
        else if (funct5 == 1u) { new_val32 = src32; }
        else if (funct5 == 4u) { new_val32 = mem_val32 ^ src32; }
        else if (funct5 == 8u) { new_val32 = mem_val32 | src32; }
        else if (funct5 == 12u) { new_val32 = mem_val32 & src32; }
        else if (funct5 == 16u) {
            if (bitcast<i32>(src32) < bitcast<i32>(mem_val32)) { new_val32 = src32; }
        } else if (funct5 == 20u) {
            if (bitcast<i32>(src32) > bitcast<i32>(mem_val32)) { new_val32 = src32; }
        } else if (funct5 == 24u) {
            if (src32 < mem_val32) { new_val32 = src32; }
        } else if (funct5 == 28u) {
            if (src32 > mem_val32) { new_val32 = src32; }
        } else {
            (*cpu).pc = add64((*cpu).pc, vec2<u32>(4u, 0u));
            return;
        }

        write_phys_word(pa, new_val32);
        if (rd != 0u) {
            (*cpu).regs[rd] = sext32_to_64(mem_val32);
        }
    } else {
        let low_val = read_phys_word(pa);
        let high_val = read_phys_word(add64(pa, vec2<u32>(4u, 0u)));
        let mem_val = vec2<u32>(low_val, high_val);
        var new_val = mem_val;

        if (funct5 == 0u) { new_val = add64(mem_val, src); }
        else if (funct5 == 1u) { new_val = src; }
        else if (funct5 == 4u) { new_val = vec2<u32>(mem_val.x ^ src.x, mem_val.y ^ src.y); }
        else if (funct5 == 8u) { new_val = vec2<u32>(mem_val.x | src.x, mem_val.y | src.y); }
        else if (funct5 == 12u) { new_val = vec2<u32>(mem_val.x & src.x, mem_val.y & src.y); }
        else if (funct5 == 16u) {
            if (lt64s(src, mem_val)) { new_val = src; }
        } else if (funct5 == 20u) {
            if (lt64s(mem_val, src)) { new_val = src; }
        } else if (funct5 == 24u) {
            if (lt64(src, mem_val)) { new_val = src; }
        } else if (funct5 == 28u) {
            if (lt64(mem_val, src)) { new_val = src; }
        } else {
            (*cpu).pc = add64((*cpu).pc, vec2<u32>(4u, 0u));
            return;
        }

        write_phys_word(pa, new_val.x);
        write_phys_word(add64(pa, vec2<u32>(4u, 0u)), new_val.y);
        if (rd != 0u) {
            (*cpu).regs[rd] = mem_val;
        }
    }

    (*cpu).pc = add64((*cpu).pc, vec2<u32>(4u, 0u));
}

// ECALL Handling
fn read_byte_from_memory(cpu: ptr<function, RiscvCPU>, addr: vec2<u32>) -> u32 {
    let pa = translate_va(cpu, addr);
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

// Read one byte from PHYSICAL memory (SBI calls pass physical addresses)
fn read_phys_byte(pa: vec2<u32>) -> u32 {
    let word = read_phys_word(pa);
    return (word >> ((pa.x & 3u) * 8u)) & 0xFFu;
}

// ============================================================================
// SBI FIRMWARE (executed inline - the GPU emulator IS the M-mode firmware)
//
// An ECALL from S-mode is an "environment call to the SEE". Instead of
// vectoring to an M-mode software handler, we implement the SBI contract
// directly in WGSL: read a7 (EID) / a6 (FID), act, put the SBI return in
// a0 (error) / a1 (value), and resume at pc + 4.
// ============================================================================

fn execute_sbi(cpu: ptr<function, RiscvCPU>, cpu_id: u32) {
    let eid = (*cpu).regs[17].x;  // a7
    let fid = (*cpu).regs[16].x;  // a6
    let arg0 = (*cpu).regs[10];   // a0
    let arg1 = (*cpu).regs[11];   // a1

    var err = vec2<u32>(SBI_SUCCESS, 0u);
    var val = vec2<u32>(0u, 0u);

    if (eid == SBI_EXT_LEGACY_PUTCHAR) {
        // Legacy console putchar: character in a0. Legacy calls return
        // only a0 (0 on success); a1 is preserved.
        (*cpu).output_ptr = uart_write_char(cpu_id, arg0.x & 0xFFu, (*cpu).output_ptr);
        (*cpu).regs[10] = vec2<u32>(0u, 0u);
        (*cpu).pc = add64((*cpu).pc, vec2<u32>(4u, 0u));
        return;
    } else if (eid == SBI_EXT_LEGACY_GETCHAR) {
        // No input device: legacy getchar returns -1
        (*cpu).regs[10] = vec2<u32>(0xFFFFFFFFu, 0xFFFFFFFFu);
        (*cpu).pc = add64((*cpu).pc, vec2<u32>(4u, 0u));
        return;
    } else if (eid == SBI_EXT_LEGACY_SET_TIMER) {
        // No timer interrupts yet: accept and ignore
        (*cpu).regs[10] = vec2<u32>(0u, 0u);
        (*cpu).pc = add64((*cpu).pc, vec2<u32>(4u, 0u));
        return;
    } else if (eid == SBI_EXT_BASE) {
        if (fid == 0u) {        // sbi_get_spec_version: v2.0 (major in [30:24])
            val = vec2<u32>(2u << 24u, 0u);
        } else if (fid == 1u) { // sbi_get_impl_id (custom)
            val = vec2<u32>(0x47505547u, 0u);  // "GPUG"
        } else if (fid == 2u) { // sbi_get_impl_version
            val = vec2<u32>(1u, 0u);
        } else if (fid == 3u) { // sbi_probe_extension(a0 = EID)
            let probed = arg0.x;
            let supported = probed == SBI_EXT_BASE || probed == SBI_EXT_TIME ||
                            probed == SBI_EXT_SRST || probed == SBI_EXT_DBCN ||
                            probed == SBI_EXT_LEGACY_PUTCHAR || probed == SBI_EXT_LEGACY_GETCHAR;
            val = vec2<u32>(select(0u, 1u, supported), 0u);
        } else if (fid == 4u || fid == 5u || fid == 6u) {
            // mvendorid / marchid / mimpid
            val = vec2<u32>(0u, 0u);
        } else {
            err = vec2<u32>(SBI_ERR_NOT_SUPPORTED, 0xFFFFFFFFu);
        }
    } else if (eid == SBI_EXT_TIME) {
        if (fid == 0u) {        // sbi_set_timer: no timer interrupts yet
            // success, no-op
        } else {
            err = vec2<u32>(SBI_ERR_NOT_SUPPORTED, 0xFFFFFFFFu);
        }
    } else if (eid == SBI_EXT_DBCN) {
        if (fid == 0u) {
            // sbi_debug_console_write(num_bytes=a0, base_addr=a1/a2 physical)
            let count = min(arg0.x, 4096u);
            for (var i = 0u; i < count; i = i + 1u) {
                let ch = read_phys_byte(add64(arg1, vec2<u32>(i, 0u)));
                (*cpu).output_ptr = uart_write_char(cpu_id, ch, (*cpu).output_ptr);
            }
            val = vec2<u32>(count, 0u);  // bytes written
        } else if (fid == 2u) {
            // sbi_debug_console_write_byte(a0)
            (*cpu).output_ptr = uart_write_char(cpu_id, arg0.x & 0xFFu, (*cpu).output_ptr);
        } else if (fid == 1u) {
            // sbi_debug_console_read: no input - 0 bytes
            val = vec2<u32>(0u, 0u);
        } else {
            err = vec2<u32>(SBI_ERR_NOT_SUPPORTED, 0xFFFFFFFFu);
        }
    } else if (eid == SBI_EXT_SRST) {
        // sbi_system_reset: clean shutdown of the pixel machine
        (*cpu).running = 0u;
    } else {
        // HSM, IPI, RFENCE, everything else: not supported (single hart,
        // no TLB shootdown needed, no secondary harts to start)
        err = vec2<u32>(SBI_ERR_NOT_SUPPORTED, 0xFFFFFFFFu);
    }

    (*cpu).regs[10] = err;
    (*cpu).regs[11] = val;
    (*cpu).pc = add64((*cpu).pc, vec2<u32>(4u, 0u));
}

fn execute_ecall(cpu: ptr<function, RiscvCPU>, cpu_id: u32) {
    // S-mode ECALL = SBI call, handled by the inline firmware above
    if ((*cpu).priv_mode == PRIV_S) {
        execute_sbi(cpu, cpu_id);
        return;
    }

    // U-mode ECALL = system call to the S-mode kernel: real trap (cause 8).
    // pc is NOT advanced - sepc/mepc must point at the ECALL itself.
    if ((*cpu).priv_mode == PRIV_U) {
        take_trap(cpu, vec2<u32>(CAUSE_ECALL_U, 0u), vec2<u32>(0u, 0u));
        return;
    }

    // M-mode ECALL: legacy test-kernel syscall shim (sys_write/sys_exit)
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
                let char_val = read_byte_from_memory(cpu, add64(buf, vec2<u32>(i, 0u)));
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

    for (var step_iter = 0u; step_iter < max_instructions; step_iter = step_iter + 1u) {
        if (cpu.running == 0u) {
            break;
        }
        
        if (cpu.instr_count >= max_instructions) {
            // Budget for this dispatch exhausted - pause, don't halt.
            // running stays 1 so the host can resume by dispatching again
            // with a larger max_instructions; forcing a halt here (plus a
            // marker write to output[cpu_id*256], which collides with the
            // UART's own first word) made single-stepping and console
            // content checks from the host impossible to distinguish from
            // a real halt/trap. Genuine runaway detection belongs on the
            // host side (it already tracks PC/instr_count across calls).
            break;
        }

        // === INTERRUPT DELIVERY ===
        // Check for external interrupts from PLIC
        let has_ext_irq = check_external_interrupt(&cpu);

        // Update MIP external interrupt bits
        var new_mip = cpu.mip;
        if (has_ext_irq) {
            // Set both MEIP (M-mode) and SEIP (S-mode) external interrupt bits
            // xv6 runs S-mode, so SEIP is what matters
            new_mip.x = new_mip.x | MIP_MEIP | MIP_SEIP;
        } else {
            new_mip.x = new_mip.x & ~(MIP_MEIP | MIP_SEIP);
        }
        cpu.mip = new_mip;

        // Check if we should take an interrupt
        // S-mode: check if SEIP is set and SIE is enabled (mstatus.sie bit 1)
        // M-mode: check if MEIP is set and MIE is enabled (mstatus.mie bit 3)
        let should_trap_s = (cpu.mip.x & MIP_SEIP) != 0u && (cpu.mstatus.x & 2u) != 0u && cpu.priv_mode == PRIV_S;
        let should_trap_m = (cpu.mip.x & MIP_MEIP) != 0u && (cpu.mstatus.x & 8u) != 0u && cpu.priv_mode == PRIV_M;

        if (should_trap_s) {
            take_trap(&cpu, vec2<u32>(CAUSE_SUPERVISOR_EXTERNAL, 0u), cpu.pc);
            continue;
        } else if (should_trap_m) {
            take_trap(&cpu, vec2<u32>(CAUSE_MACHINE_EXTERNAL, 0u), cpu.pc);
            continue;
        }

        // Fetch instruction with MMU translation
    let fetch = fetch_instruction(&cpu, cpu.pc);

    // Check for instruction page fault
    if (fetch.faulted) {
        take_trap(&cpu, vec2<u32>(CAUSE_INSTR_PAGE_FAULT, 0u), cpu.pc);
        continue;  // Trap changes pc, re-fetch next iteration
    }
    let instr = fetch.instr;

    let opcode = instr & 127u;

    if (opcode == OP_LUI) {
        execute_lui(&cpu, instr);
    } else if (opcode == OP_AUIPC) {
        execute_auipc(&cpu, instr);
    } else if (opcode == OP_OP_IMM) {
        let funct3 = (instr >> 12u) & 7u;
        let funct7 = (instr >> 25u) & 127u;
        if (funct3 == F3_ADDI) {
            execute_addi(&cpu, instr);
        } else if (funct3 == F3_ANDI) {
            execute_andi(&cpu, instr);
        } else if (funct3 == F3_ORI) {
            execute_ori(&cpu, instr);
        } else if (funct3 == F3_XORI) {
            execute_xori(&cpu, instr);
        } else if (funct3 == F3_SLTI) {
            execute_slti(&cpu, instr);
        } else if (funct3 == F3_SLTIU) {
            execute_sltiu(&cpu, instr);
        } else if (funct3 == F3_SLLI && (funct7 & 0x7Eu) == F7_SLLI) {
            execute_slli(&cpu, instr);
        } else if (funct3 == F3_SRLI && (funct7 & 0x7Eu) == F7_SRLI) {
            execute_srli(&cpu, instr);
        } else if (funct3 == F3_SRAI && (funct7 & 0x7Eu) == (F7_SRAI & 0x7Eu)) {
            execute_srai(&cpu, instr);
        } else {
            // Unsupported OP_IMM instruction
            handle_illegal(&cpu, instr, cpu_id);
        }
    } else if (opcode == OP_OP) {
        let funct3 = (instr >> 12u) & 7u;
        let funct7 = (instr >> 25u) & 127u;
        if (funct7 == F7_MULDIV) {
            // M extension: MUL, MULH, MULHSU, MULHU, DIV, DIVU, REM, REMU
            execute_muldiv(&cpu, instr);
        } else if (funct3 == 0u && funct7 == 0u) {
            // ADD
            execute_add(&cpu, instr);
        } else if (funct3 == 0u && funct7 == 32u) {
            // SUB
            execute_sub(&cpu, instr);
        } else if (funct3 == 7u && funct7 == 0u) {
            // AND
            execute_and(&cpu, instr);
        } else if (funct3 == 6u && funct7 == 0u) {
            // OR
            execute_or(&cpu, instr);
        } else if (funct3 == 4u && funct7 == 0u) {
            // XOR
            execute_xor(&cpu, instr);
        } else if (funct3 == 1u && funct7 == 0u) {
            // SLL
            execute_sll(&cpu, instr);
        } else if (funct3 == 5u && funct7 == 0u) {
            // SRL
            execute_srl(&cpu, instr);
        } else if (funct3 == 5u && funct7 == 32u) {
            // SRA
            execute_sra(&cpu, instr);
        } else if (funct3 == 2u && funct7 == 0u) {
            // SLT
            execute_slt(&cpu, instr);
        } else if (funct3 == 3u && funct7 == 0u) {
            // SLTU
            execute_sltu(&cpu, instr);
        } else {
            // Unsupported OP instruction
            handle_illegal(&cpu, instr, cpu_id);
        }
    } else if (opcode == OP_OP_IMM_32) {
        let funct3 = (instr >> 12u) & 7u;
        let funct7 = (instr >> 25u) & 127u;
        if (funct3 == F3_ADDIW) {
            execute_addiw(&cpu, instr);
        } else if (funct3 == F3_SLLIW && (funct7 & 0x7Eu) == F7_SLLIW) {
            execute_slliw(&cpu, instr);
        } else if (funct3 == F3_SRLIW && (funct7 & 0x7Eu) == F7_SRLIW) {
            execute_srliw(&cpu, instr);
        } else if (funct3 == F3_SRAIW && (funct7 & 0x7Eu) == (F7_SRAIW & 0x7Eu)) {
            execute_sraiw(&cpu, instr);
        } else {
            // Unsupported OP_IMM_32 instruction
            handle_illegal(&cpu, instr, cpu_id);
        }
    } else if (opcode == OP_OP_32) {
        let funct3 = (instr >> 12u) & 7u;
        let funct7 = (instr >> 25u) & 127u;
        if (funct7 == F7_MULDIV) {
            // M extension W forms: MULW, DIVW, DIVUW, REMW, REMUW
            execute_muldiv_w(&cpu, instr);
        } else if (funct3 == 0u && funct7 == F7_ADDW) {
            // ADDW
            execute_addw(&cpu, instr);
        } else if (funct3 == 0u && funct7 == F7_SUBW) {
            // SUBW
            execute_subw(&cpu, instr);
        } else if (funct3 == 1u && funct7 == F7_SLLW) {
            // SLLW
            execute_sllw(&cpu, instr);
        } else if (funct3 == 5u && funct7 == F7_SRLW) {
            // SRLW
            execute_srlw(&cpu, instr);
        } else if (funct3 == 5u && funct7 == F7_SRAW) {
            // SRAW
            execute_sraw(&cpu, instr);
        } else {
            // Unsupported OP_32 instruction
            handle_illegal(&cpu, instr, cpu_id);
        }
    } else if (opcode == OP_JAL) {
        execute_jal(&cpu, instr);
    } else if (opcode == OP_JALR) {
        execute_jalr(&cpu, instr);
    } else if (opcode == OP_BRANCH) {
        execute_branch(&cpu, instr);
    } else if (opcode == OP_AMO) {
        // A extension: LR/SC + AMOs. funct3 selects width (2=.W, 3=.D);
        // funct5 (top 5 bits of funct7) selects the operation.
        let funct3 = (instr >> 12u) & 7u;
        let funct5 = (instr >> 27u) & 31u;
        if (funct5 == 2u) {
            execute_lr(&cpu, instr, funct3);
        } else if (funct5 == 3u) {
            execute_sc(&cpu, instr, funct3);
        } else {
            execute_amo(&cpu, instr, funct3, funct5);
        }
    } else if (opcode == OP_LOAD) {
        execute_load(cpu.satp, &cpu, instr);
    } else if (opcode == OP_STORE) {
        execute_store(cpu.satp, &cpu, instr, cpu_id);
    } else if (opcode == OP_SYSTEM) {
        let funct3 = (instr >> 12u) & 7u;
        if (funct3 == 0u) {
            let funct12 = instr >> 20u;
            let funct7 = (instr >> 25u) & 127u;
            if (funct12 == F12_ECALL) {
                execute_ecall(&cpu, cpu_id);
            } else if (funct12 == F12_EBREAK) {
                // EBREAK: trap if handler installed, else halt
                handle_illegal(&cpu, instr, cpu_id);
            } else if (funct12 == F12_MRET) {
                if (cpu.priv_mode == PRIV_M) {
                    execute_mret(&cpu);
                } else {
                    // MRET below M-mode is an illegal instruction
                    handle_illegal(&cpu, instr, cpu_id);
                }
            } else if (funct12 == F12_SRET) {
                if (cpu.priv_mode >= PRIV_S) {
                    execute_sret(&cpu);
                } else {
                    handle_illegal(&cpu, instr, cpu_id);
                }
            } else if (funct12 == F12_WFI) {
                // WFI: no interrupt sources yet - treat as NOP
                cpu.pc = add64(cpu.pc, vec2<u32>(4u, 0u));
            } else if (funct7 == F7_SFENCE_VMA) {
                // SFENCE.VMA: no TLB to flush - NOP
                cpu.pc = add64(cpu.pc, vec2<u32>(4u, 0u));
            } else {
                handle_illegal(&cpu, instr, cpu_id);
            }
        } else if (funct3 != 4u) {
            // CSRRW/CSRRS/CSRRC/CSRRWI/CSRRSI/CSRRCI
            execute_csr(&cpu, instr, cpu_id);
        } else {
            handle_illegal(&cpu, instr, cpu_id);
        }
    } else if (opcode == 15u) {
        // MISC-MEM: FENCE / FENCE.I - single-hart in-order execution, NOP
        cpu.pc = add64(cpu.pc, vec2<u32>(4u, 0u));
    } else {
        // Unknown opcode
        handle_illegal(&cpu, instr, cpu_id);
    }

        cpu.regs[0] = vec2<u32>(0u, 0u); // Ensure x0 is always 0
        cpu.instr_count = cpu.instr_count + 1u;
    } // end of step loop

    cpus[cpu_id] = cpu;
}