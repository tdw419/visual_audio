struct RegisterFile {
    x: array<u32, 32>,
};

struct CPUState {
    pc: u32,
    halted: u32,
    steps_remaining: u32,
    // Privilege mode: 0 = User, 1 = Supervisor, 3 = Machine (matches RISC-V mstatus encoding)
    mode: u32,
    // Set by fetch() when instruction translation faults; tells main() to skip
    // decode_and_execute this cycle since pc has already been redirected to a trap handler.
    trap_pending: u32,
    // LR.W/SC.W reservation set (single-hart, so this is a simple address-match check).
    reservation_valid: u32,
    reservation_addr: u32,
    // Count of bytes ever written to the UART TX ring buffer (monotonic; host tracks its own
    // read cursor and takes it modulo the buffer capacity).
    uart_tx_len: u32,
    // CLINT timer device registers. 32-bit only (real hardware is 64-bit) — sufficient for a
    // skeleton timer source; a kernel using the high word will need this widened later.
    mtime: u32,
    mtimecmp: u32,
    // Guest physical address that maps to word 0 of our (Hilbert-mapped) `memory` buffer.
    // Real hardware/kernels commonly expect RAM to start at 0x80000000; our early bare-metal
    // tests all assume 0. Defaults to 0 so existing programs are unaffected; a kernel boot
    // sets this to match its linked RAM base via load_program's ram_base argument.
    ram_base: u32,
    // UART RX: single byte buffer (non-blocking; if data_pending=0, reads return 0).
    uart_rx_data_pending: u32,
    uart_rx_byte: u32,
};

@group(0) @binding(0) var<storage, read_write> memory: array<u32>;
@group(0) @binding(1) var<storage, read_write> registers: RegisterFile;
@group(0) @binding(2) var<storage, read_write> state: CPUState;
// Flat CSR file addressed directly by the 12-bit CSR index from the instruction encoding.
@group(0) @binding(3) var<storage, read_write> csrs: array<u32, 4096>;
// Memory-mapped UART TX ring buffer (one byte per u32 slot, for simple host-side draining).
@group(0) @binding(4) var<storage, read_write> uart_tx: array<u32, 4096>;

// Minimal 16550-style UART. THR (write) and RBR (read) share the base address; LSR is a
// fixed status byte reporting "always ready to transmit, nothing to receive" so a real
// ns16550 driver polling LSR before writing/reading never blocks.
const UART_BASE: u32 = 0x10000000u;
const UART_REGION_SIZE: u32 = 0x8u; // 8 byte-wide 16550 registers
const UART_LSR_ADDR: u32 = 0x10000005u;
const UART_LSR_READY: u32 = 0x60u; // THRE | TEMT, no DR

// CLINT MMIO region matching the `sifive,clint0` layout (hart 0 only) used by both the
// QEMU "virt" machine and cnlohr/mini-rv32ima's riscv-minimal-nommu machine.
const CLINT_BASE: u32 = 0x11000000u;
const CLINT_REGION_SIZE: u32 = 0x10000u;
const CLINT_MTIMECMP_ADDR: u32 = 0x11004000u;
const CLINT_MTIME_ADDR: u32 = 0x1100BFF8u;

// Sifive-test-style syscon: any write halts the core, standing in for poweroff/reboot.
const SYSCON_ADDR: u32 = 0x11100000u;

const CSR_SSTATUS: u32 = 0x100u;
const CSR_STVEC: u32 = 0x105u;
const CSR_SEPC: u32 = 0x141u;
const CSR_SCAUSE: u32 = 0x142u;
const CSR_STVAL: u32 = 0x143u;
const CSR_MSTATUS: u32 = 0x300u;
const CSR_MEDELEG: u32 = 0x302u;
const CSR_MIE: u32 = 0x304u;
const CSR_MTVEC: u32 = 0x305u;
const CSR_MEPC: u32 = 0x341u;
const CSR_MCAUSE: u32 = 0x342u;
const CSR_MTVAL: u32 = 0x343u;
const CSR_MIP: u32 = 0x344u;
const CSR_SATP: u32 = 0x180u;

// sstatus is an architectural *view* of mstatus restricted to S-mode-visible bits
// (SIE=bit1, SPIE=bit5, SPP=bit8). Real hardware aliases the same physical register.
const SSTATUS_MASK: u32 = 0x122u;
// mstatus bits touched on an M-mode trap: MIE(3), MPIE(7), MPP(12:11)
const MSTATUS_TRAP_MASK: u32 = 0x1888u;

fn csr_read(addr: u32) -> u32 {
    if (addr == CSR_SSTATUS) {
        return csrs[CSR_MSTATUS] & SSTATUS_MASK;
    }
    return csrs[addr];
}

fn csr_write(addr: u32, val: u32) {
    if (addr == CSR_SSTATUS) {
        csrs[CSR_MSTATUS] = (csrs[CSR_MSTATUS] & ~SSTATUS_MASK) | (val & SSTATUS_MASK);
    } else {
        csrs[addr] = val;
    }
}

// Devices living below the RAM base, checked prior to normal memory access. Returns
// (value, handled): handled=0 means the address isn't a device and RAM access should proceed.
fn mmio_read(addr: u32) -> vec2<u32> {
    if (addr == UART_BASE) {
        // RBR: receive byte (if data_pending); consume on read
        if (state.uart_rx_data_pending != 0u) {
            state.uart_rx_data_pending = 0u;
            return vec2<u32>(state.uart_rx_byte, 1u);
        } else {
            return vec2<u32>(0u, 1u);
        }
    }
    if (addr == UART_LSR_ADDR) {
        // LSR: THRE|TEMT always true; DR set when RX data pending
        let dr = select(0u, 0x01u, state.uart_rx_data_pending != 0u);
        return vec2<u32>(UART_LSR_READY | dr, 1u);
    }
    if (addr >= UART_BASE && addr < UART_BASE + UART_REGION_SIZE) {
        return vec2<u32>(0u, 1u); // Any other 16550 register we don't model: read as 0
    }
    if (addr == CLINT_MTIME_ADDR) {
        return vec2<u32>(state.mtime, 1u);
    }
    if (addr == CLINT_MTIMECMP_ADDR) {
        return vec2<u32>(state.mtimecmp, 1u);
    }
    if (addr >= CLINT_BASE && addr < CLINT_BASE + CLINT_REGION_SIZE) {
        return vec2<u32>(0u, 1u); // msip and any other CLINT register we don't model: read as 0
    }
    return vec2<u32>(0u, 0u);
}

// Returns true if addr was a recognized device (and the write was serviced).
fn mmio_write(addr: u32, val: u32) -> bool {
    if (addr == UART_BASE) {
        uart_tx[state.uart_tx_len % 4096u] = val & 0xFFu;
        state.uart_tx_len = state.uart_tx_len + 1u;
        return true;
    }
    if (addr >= UART_BASE && addr < UART_BASE + UART_REGION_SIZE) {
        return true; // IER/FCR/LCR/MCR/etc — accept silently, we don't model them
    }
    if (addr == CLINT_MTIMECMP_ADDR) {
        state.mtimecmp = val;
        csrs[CSR_MIP] = csrs[CSR_MIP] & ~0x80u; // writing mtimecmp clears any pending MTIP
        return true;
    }
    if (addr >= CLINT_BASE && addr < CLINT_BASE + CLINT_REGION_SIZE) {
        return true; // msip and any other CLINT register we don't model — accept silently
    }
    if (addr == SYSCON_ADDR) {
        state.halted = 1u; // stand-in for poweroff/reboot: cleanly stop the core
        return true;
    }
    return false;
}

// Sub-word accessors into `memory`, operating on an address already resolved to a RAM-relative
// (i.e. RAM-base-subtracted) byte offset. Each returns (value, ok); ok=0 means out of bounds.
fn phys_read_u8(addr: u32) -> vec2<u32> {
    let d = addr / 4u;
    if (d >= arrayLength(&memory)) {
        return vec2<u32>(0u, 0u);
    }
    let shift = (addr & 3u) * 8u;
    return vec2<u32>((memory[d2idx(d)] >> shift) & 0xFFu, 1u);
}

fn phys_read_u16(addr: u32) -> vec2<u32> {
    let d = addr / 4u;
    if (d >= arrayLength(&memory)) {
        return vec2<u32>(0u, 0u);
    }
    let shift = (addr & 2u) * 8u;
    return vec2<u32>((memory[d2idx(d)] >> shift) & 0xFFFFu, 1u);
}

fn phys_read_u32(addr: u32) -> vec2<u32> {
    let d = addr / 4u;
    if (d >= arrayLength(&memory)) {
        return vec2<u32>(0u, 0u);
    }
    return vec2<u32>(memory[d2idx(d)], 1u);
}

fn phys_write_u8(addr: u32, val: u32) -> bool {
    let d = addr / 4u;
    if (d >= arrayLength(&memory)) {
        return false;
    }
    let idx = d2idx(d);
    let shift = (addr & 3u) * 8u;
    let mask = ~(0xFFu << shift);
    memory[idx] = (memory[idx] & mask) | ((val & 0xFFu) << shift);
    return true;
}

fn phys_write_u16(addr: u32, val: u32) -> bool {
    let d = addr / 4u;
    if (d >= arrayLength(&memory)) {
        return false;
    }
    let idx = d2idx(d);
    let shift = (addr & 2u) * 8u;
    let mask = ~(0xFFFFu << shift);
    memory[idx] = (memory[idx] & mask) | ((val & 0xFFFFu) << shift);
    return true;
}

fn phys_write_u32(addr: u32, val: u32) -> bool {
    let d = addr / 4u;
    if (d >= arrayLength(&memory)) {
        return false;
    }
    memory[d2idx(d)] = val;
    return true;
}

// Raises a synchronous exception (ecall/ebreak) from the given faulting pc and
// returns the new pc. Delegates to S-mode if medeleg has the cause bit set and
// we're not already in M-mode; otherwise traps to M-mode. If the destination
// trap vector is unconfigured (0), halts instead of jumping to address 0 —
// this keeps bare-metal programs that never set up a handler behaving as before.
fn raise_trap(cause: u32, tval: u32, pc: u32) -> u32 {
    let delegate = (state.mode != 3u) && (((csrs[CSR_MEDELEG] >> cause) & 1u) == 1u);
    if (delegate) {
        csrs[CSR_SEPC] = pc;
        csrs[CSR_SCAUSE] = cause;
        csrs[CSR_STVAL] = tval;
        var mstatus = csrs[CSR_MSTATUS];
        let sie = (mstatus >> 1u) & 1u;
        let spp = select(0u, 1u, state.mode == 1u);
        mstatus = (mstatus & ~SSTATUS_MASK) | (sie << 5u) | (spp << 8u);
        csrs[CSR_MSTATUS] = mstatus;
        state.mode = 1u;
        if (csrs[CSR_STVEC] == 0u) {
            state.halted = 1u;
            return pc;
        }
        return csrs[CSR_STVEC] & 0xFFFFFFFCu;
    } else {
        csrs[CSR_MEPC] = pc;
        csrs[CSR_MCAUSE] = cause;
        csrs[CSR_MTVAL] = tval;
        var mstatus = csrs[CSR_MSTATUS];
        let mie = (mstatus >> 3u) & 1u;
        mstatus = (mstatus & ~MSTATUS_TRAP_MASK) | (mie << 7u) | (state.mode << 11u);
        csrs[CSR_MSTATUS] = mstatus;
        state.mode = 3u;
        if (csrs[CSR_MTVEC] == 0u) {
            state.halted = 1u;
            return pc;
        }
        return csrs[CSR_MTVEC] & 0xFFFFFFFCu;
    }
}

fn do_mret() -> u32 {
    var mstatus = csrs[CSR_MSTATUS];
    let mpie = (mstatus >> 7u) & 1u;
    let mpp = (mstatus >> 11u) & 3u;
    mstatus = (mstatus & ~MSTATUS_TRAP_MASK) | (mpie << 3u) | (1u << 7u);
    csrs[CSR_MSTATUS] = mstatus;
    state.mode = mpp;
    return csrs[CSR_MEPC];
}

fn do_sret() -> u32 {
    var mstatus = csrs[CSR_MSTATUS];
    let spie = (mstatus >> 5u) & 1u;
    let spp = (mstatus >> 8u) & 1u;
    mstatus = (mstatus & ~SSTATUS_MASK) | (spie << 1u) | (1u << 5u);
    csrs[CSR_MSTATUS] = mstatus;
    state.mode = spp;
    return csrs[CSR_SEPC];
}

// Checks the CLINT timer against mtimecmp, latches MTIP in mip if it has fired, and — if
// that interrupt is actually enabled (mie.MTIE and, in M-mode, mstatus.MIE) — takes it right
// now: redirects pc to mtvec and sets trap_pending so main() skips decode this cycle.
// Skeleton simplification: machine timer interrupts always go straight to M-mode; there's no
// mideleg-based delegation to S-mode yet (real hardware supports that via sip/sie aliasing).
fn maybe_take_interrupt() {
    if (state.mtimecmp != 0u && state.mtime >= state.mtimecmp) {
        csrs[CSR_MIP] = csrs[CSR_MIP] | 0x80u; // MTIP
    }

    let mtip_enabled = ((csrs[CSR_MIP] & csrs[CSR_MIE]) & 0x80u) != 0u;
    if (!mtip_enabled) {
        return;
    }

    let mstatus = csrs[CSR_MSTATUS];
    // M-mode interrupts are only maskable by mstatus.MIE while already in M-mode; a lower
    // privilege mode can never block an M-mode interrupt.
    let globally_enabled = (state.mode != 3u) || (((mstatus >> 3u) & 1u) == 1u);
    if (!globally_enabled) {
        return;
    }

    csrs[CSR_MEPC] = state.pc;
    csrs[CSR_MCAUSE] = 0x80000007u; // interrupt bit set, code 7 = machine timer interrupt
    csrs[CSR_MTVAL] = 0u;
    let mie_bit = (mstatus >> 3u) & 1u;
    csrs[CSR_MSTATUS] = (mstatus & ~MSTATUS_TRAP_MASK) | (mie_bit << 7u) | (state.mode << 11u);
    state.mode = 3u;

    if (csrs[CSR_MTVEC] == 0u) {
        state.halted = 1u;
    } else {
        state.pc = csrs[CSR_MTVEC] & 0xFFFFFFFCu;
    }
    state.trap_pending = 1u;
}

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

fn read_word_phys(byte_addr: u32) -> u32 {
    let d = byte_addr / 4u;
    if (d >= arrayLength(&memory)) {
        return 0u;
    }
    return memory[d2idx(d)];
}

fn check_perm(pte: u32, need_write: bool, need_exec: bool) -> bool {
    let r = (pte >> 1u) & 1u;
    let w = (pte >> 2u) & 1u;
    let x = (pte >> 3u) & 1u;
    if (need_exec) {
        return x == 1u;
    }
    if (need_write) {
        return w == 1u;
    }
    return r == 1u;
    // NOTE: no U-bit/SUM/MXR checks yet (privilege-vs-page-U-bit enforcement is Phase C work).
}

// Sv32 two-level page table walk. Returns (phys_addr, fault) where fault != 0 means
// the translation failed (invalid/misconfigured PTE or a permission violation).
// Bypassed entirely when satp.MODE (bit 31) is 0, i.e. translation is off (M-mode default).
fn translate_address(va: u32, need_write: bool, need_exec: bool) -> vec2<u32> {
    if (((csrs[CSR_SATP] >> 31u) & 1u) == 0u) {
        return vec2<u32>(va, 0u);
    }

    let vpn1 = (va >> 22u) & 0x3FFu;
    let vpn0 = (va >> 12u) & 0x3FFu;
    let off = va & 0xFFFu;

    let root_ppn = csrs[CSR_SATP] & 0x3FFFFFu;
    let pte1 = read_word_phys((root_ppn * 4096u) + vpn1 * 4u);
    let v1 = pte1 & 1u;
    let r1 = (pte1 >> 1u) & 1u;
    let w1 = (pte1 >> 2u) & 1u;
    let x1 = (pte1 >> 3u) & 1u;
    if (v1 == 0u || (r1 == 0u && w1 == 1u)) {
        return vec2<u32>(0u, 1u); // invalid leading-order PTE
    }
    if (r1 == 1u || x1 == 1u) {
        // Leaf at level 1: a 4MiB superpage.
        if (!check_perm(pte1, need_write, need_exec)) {
            return vec2<u32>(0u, 1u);
        }
        let leaf_ppn1 = (pte1 >> 10u) & 0x3FFFFFu;
        return vec2<u32>((leaf_ppn1 << 22u) | (va & 0x3FFFFFu), 0u);
    }

    // Non-leaf: descend to the level-0 (4KiB) table.
    let ppn0_table = (pte1 >> 10u) & 0x3FFFFFu;
    let pte0 = read_word_phys((ppn0_table * 4096u) + vpn0 * 4u);
    let v0 = pte0 & 1u;
    let r0 = (pte0 >> 1u) & 1u;
    let w0 = (pte0 >> 2u) & 1u;
    if (v0 == 0u || (r0 == 0u && w0 == 1u)) {
        return vec2<u32>(0u, 1u);
    }
    if (!check_perm(pte0, need_write, need_exec)) {
        return vec2<u32>(0u, 1u);
    }
    let leaf_ppn0 = (pte0 >> 10u) & 0x3FFFFFu;
    return vec2<u32>((leaf_ppn0 << 12u) | off, 0u);
}

fn fetch() -> u32 {
    let translated = translate_address(state.pc, false, true);
    if (translated.y != 0u) {
        state.pc = raise_trap(12u, state.pc, state.pc); // instruction page fault
        state.trap_pending = 1u;
        return 0u;
    }

    if (translated.x < state.ram_base) {
        state.halted = 1u; // fetching from a device/unmapped hole below RAM base
        return 0u;
    }
    let fetched = phys_read_u32(translated.x - state.ram_base);
    if (fetched.y == 0u) {
        state.halted = 1u;
        return 0u;
    }
    return fetched.x;
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

// --- M extension helpers: 32x32->64 unsigned multiply, two's complement negate ---

fn negate32(a: u32) -> u32 {
    return (~a) + 1u;
}

// Returns (low, high) of a * b, both treated as unsigned 32-bit.
fn umul64(a: u32, b: u32) -> vec2<u32> {
    let a_lo = a & 0xFFFFu;
    let a_hi = a >> 16u;
    let b_lo = b & 0xFFFFu;
    let b_hi = b >> 16u;

    let t0 = a_lo * b_lo;
    let t1 = a_hi * b_lo + (t0 >> 16u);
    let t2 = a_lo * b_hi + (t1 & 0xFFFFu);
    let lo = (t2 << 16u) | (t0 & 0xFFFFu);
    let hi = a_hi * b_hi + (t1 >> 16u) + (t2 >> 16u);
    return vec2<u32>(lo, hi);
}

fn negate64(lo: u32, hi: u32) -> vec2<u32> {
    let inv_lo = ~lo;
    let inv_hi = ~hi;
    let new_lo = inv_lo + 1u;
    let carry = select(0u, 1u, new_lo < inv_lo);
    let new_hi = inv_hi + carry;
    return vec2<u32>(new_lo, new_hi);
}

// signed_a/signed_b select whether each operand's sign bit should be honored.
fn mul_high(a: u32, b: u32, signed_a: bool, signed_b: bool) -> u32 {
    let neg_a = signed_a && ((a >> 31u) != 0u);
    let neg_b = signed_b && ((b >> 31u) != 0u);
    let abs_a = select(a, negate32(a), neg_a);
    let abs_b = select(b, negate32(b), neg_b);
    var prod = umul64(abs_a, abs_b);
    if (neg_a != neg_b) {
        prod = negate64(prod.x, prod.y);
    }
    return prod.y;
}

fn div_signed(a: u32, b: u32) -> u32 {
    if (b == 0u) {
        return 0xFFFFFFFFu;
    }
    if (a == 0x80000000u && b == 0xFFFFFFFFu) {
        return a; // overflow: MIN_INT / -1 = MIN_INT
    }
    return bitcast<u32>(bitcast<i32>(a) / bitcast<i32>(b));
}

fn rem_signed(a: u32, b: u32) -> u32 {
    if (b == 0u) {
        return a;
    }
    if (a == 0x80000000u && b == 0xFFFFFFFFu) {
        return 0u;
    }
    // Derive remainder from the (verified-correct) truncating division
    // rather than relying on WGSL's % operator sign semantics for i32.
    let q = bitcast<i32>(a) / bitcast<i32>(b);
    return bitcast<u32>(bitcast<i32>(a) - q * bitcast<i32>(b));
}

fn div_unsigned(a: u32, b: u32) -> u32 {
    if (b == 0u) {
        return 0xFFFFFFFFu;
    }
    return a / b;
}

fn rem_unsigned(a: u32, b: u32) -> u32 {
    if (b == 0u) {
        return a;
    }
    let q = a / b;
    return a - q * b;
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

    } else if (opcode == 0x33u && funct7 == 0x01u) {
        // M extension (mul, mulh, mulhsu, mulhu, div, divu, rem, remu)
        var result = 0u;
        if (funct3 == 0u) {
            result = rs1_val * rs2_val; // mul (low 32 bits, wraps naturally)
        } else if (funct3 == 1u) {
            result = mul_high(rs1_val, rs2_val, true, true); // mulh
        } else if (funct3 == 2u) {
            result = mul_high(rs1_val, rs2_val, true, false); // mulhsu
        } else if (funct3 == 3u) {
            result = mul_high(rs1_val, rs2_val, false, false); // mulhu
        } else if (funct3 == 4u) {
            result = div_signed(rs1_val, rs2_val); // div
        } else if (funct3 == 5u) {
            result = div_unsigned(rs1_val, rs2_val); // divu
        } else if (funct3 == 6u) {
            result = rem_signed(rs1_val, rs2_val); // rem
        } else if (funct3 == 7u) {
            result = rem_unsigned(rs1_val, rs2_val); // remu
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
        // Load: lb/lh/lw/lbu/lhu (funct3 = 0/1/2/4/5)
        let imm = sign_extend_12(instr >> 20u);
        let addr = rs1_val + imm;
        let mm = mmio_read(addr);
        if (mm.y != 0u) {
            if (rd != 0u) { registers.x[rd] = mm.x; }
        } else if (funct3 > 5u || funct3 == 3u) {
            valid = false;
        } else {
            let translated = translate_address(addr, false, false);
            if (translated.y != 0u) {
                next_pc = raise_trap(13u, addr, state.pc); // load page fault
            } else if (translated.x < state.ram_base) {
                valid = false; // unmapped hole below RAM base
            } else {
                let phys = translated.x - state.ram_base;
                var result = vec2<u32>(0u, 0u);
                if (funct3 == 0u) {
                    result = phys_read_u8(phys);
                    if (result.y != 0u && (result.x & 0x80u) != 0u) { result.x = result.x | 0xFFFFFF00u; }
                } else if (funct3 == 4u) {
                    result = phys_read_u8(phys);
                } else if (funct3 == 1u) {
                    result = phys_read_u16(phys);
                    if (result.y != 0u && (result.x & 0x8000u) != 0u) { result.x = result.x | 0xFFFF0000u; }
                } else if (funct3 == 5u) {
                    result = phys_read_u16(phys);
                } else {
                    result = phys_read_u32(phys);
                }
                if (result.y != 0u) {
                    if (rd != 0u) { registers.x[rd] = result.x; }
                } else {
                    valid = false;
                }
            }
        }

    } else if (opcode == 0x23u) {
        // Store: sb/sh/sw (funct3 = 0/1/2)
        let imm5 = (instr >> 7u) & 0x1Fu;
        let imm7 = (instr >> 25u) & 0x7Fu;
        let imm = sign_extend_12((imm7 << 5u) | imm5);
        let addr = rs1_val + imm;
        if (mmio_write(addr, rs2_val)) {
            // handled by a device
        } else if (funct3 > 2u) {
            valid = false;
        } else {
            let translated = translate_address(addr, true, false);
            if (translated.y != 0u) {
                next_pc = raise_trap(15u, addr, state.pc); // store/AMO page fault
            } else if (translated.x < state.ram_base) {
                valid = false;
            } else {
                let phys = translated.x - state.ram_base;
                var ok = false;
                if (funct3 == 0u) {
                    ok = phys_write_u8(phys, rs2_val);
                } else if (funct3 == 1u) {
                    ok = phys_write_u16(phys, rs2_val);
                } else {
                    ok = phys_write_u32(phys, rs2_val);
                }
                if (!ok) {
                    valid = false;
                }
            }
        }

    } else if (opcode == 0x2Fu) {
        // A extension: lr.w / sc.w / amo*.w (funct3 must be 010 = word-sized)
        let amo_op = funct7 >> 2u;
        if (funct3 != 2u) {
            valid = false;
        } else {
            let is_lr = amo_op == 0x02u;
            let translated = translate_address(rs1_val, !is_lr, false);
            if (translated.y != 0u) {
                next_pc = raise_trap(select(15u, 13u, is_lr), rs1_val, state.pc);
            } else if (translated.x < state.ram_base) {
                valid = false;
            } else {
                let d = (translated.x - state.ram_base) / 4u;
                if (d >= arrayLength(&memory)) {
                    valid = false;
                } else {
                    let idx = d2idx(d);
                    if (is_lr) {
                        let val = memory[idx];
                        if (rd != 0u) { registers.x[rd] = val; }
                        state.reservation_valid = 1u;
                        state.reservation_addr = translated.x;
                    } else if (amo_op == 0x03u) {
                        // sc.w
                        if (state.reservation_valid == 1u && state.reservation_addr == translated.x) {
                            memory[idx] = rs2_val;
                            if (rd != 0u) { registers.x[rd] = 0u; } // success
                        } else if (rd != 0u) {
                            registers.x[rd] = 1u; // failure
                        }
                        state.reservation_valid = 0u;
                    } else {
                        let old = memory[idx];
                        var new_val = old;
                        if (amo_op == 0x01u) {
                            new_val = rs2_val; // amoswap.w
                        } else if (amo_op == 0x00u) {
                            new_val = old + rs2_val; // amoadd.w
                        } else if (amo_op == 0x04u) {
                            new_val = old ^ rs2_val; // amoxor.w
                        } else if (amo_op == 0x0Cu) {
                            new_val = old & rs2_val; // amoand.w
                        } else if (amo_op == 0x08u) {
                            new_val = old | rs2_val; // amoor.w
                        } else if (amo_op == 0x10u) {
                            new_val = select(rs2_val, old, i32(old) < i32(rs2_val)); // amomin.w
                        } else if (amo_op == 0x14u) {
                            new_val = select(rs2_val, old, i32(old) > i32(rs2_val)); // amomax.w
                        } else if (amo_op == 0x18u) {
                            new_val = select(rs2_val, old, old < rs2_val); // amominu.w
                        } else if (amo_op == 0x1Cu) {
                            new_val = select(rs2_val, old, old > rs2_val); // amomaxu.w
                        } else {
                            valid = false;
                        }
                        if (valid) {
                            memory[idx] = new_val;
                            if (rd != 0u) { registers.x[rd] = old; }
                            state.reservation_valid = 0u; // any regular AMO invalidates a pending reservation
                        }
                    }
                }
            }
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

    } else if (opcode == 0x0Fu) {
        // MISC-MEM: fence (funct3=0) / fence.i (funct3=1, Zifencei). Both are no-ops here —
        // we have no instruction cache or reordering memory system to flush/fence.
        if (funct3 != 0u && funct3 != 1u) {
            valid = false;
        }

    } else if (opcode == 0x73u) {
        // SYSTEM: ecall/ebreak/mret/sret/wfi, or a CSR instruction
        let funct12 = instr >> 20u;
        if (funct3 == 0u) {
            if (funct12 == 0u) {
                // Native SBI dispatch: an S-mode ecall requesting one of a small set of
                // legacy SBI extensions is serviced directly here instead of trapping to
                // M-mode firmware — equivalent in effect to ecall -> (OpenSBI) -> mret,
                // but without needing real firmware code resident at mtvec. This works
                // regardless of whether mtvec is configured, unlike routing SBI calls
                // through a Python-side halt handler (which only fires when raise_trap
                // finds no M-mode handler and halts).
                let sbi_ext = registers.x[17]; // a7
                if (state.mode == 1u && sbi_ext == 0x01u) {
                    // Legacy console putchar: character is in a0.
                    uart_tx[state.uart_tx_len % 4096u] = registers.x[10] & 0xFFu;
                    state.uart_tx_len = state.uart_tx_len + 1u;
                    registers.x[10] = 0u; // SBI_SUCCESS
                    registers.x[11] = 0u;
                } else if (state.mode == 1u && sbi_ext == 0x54494D45u) {
                    // TIME extension "set timer": 64-bit deadline in a0(lo)/a1(hi).
                    // We only track a 32-bit mtimecmp, so the high word is dropped.
                    state.mtimecmp = registers.x[10];
                    csrs[CSR_MIP] = csrs[CSR_MIP] & ~0x80u; // clear any latched MTIP
                    registers.x[10] = 0u;
                    registers.x[11] = 0u;
                } else {
                    // Not a recognized SBI hypercall — take the real trap.
                    var cause = 11u; // M-mode environment call
                    if (state.mode == 0u) {
                        cause = 8u; // U-mode environment call
                    } else if (state.mode == 1u) {
                        cause = 9u; // S-mode environment call
                    }
                    next_pc = raise_trap(cause, 0u, state.pc);
                }
            } else if (funct12 == 1u) {
                next_pc = raise_trap(3u, 0u, state.pc); // ebreak
            } else if (funct12 == 0x302u) {
                next_pc = do_mret();
            } else if (funct12 == 0x102u) {
                next_pc = do_sret();
            } else if (funct12 == 0x105u) {
                // wfi — no interrupt controller yet, treat as nop
            } else {
                valid = false;
            }
        } else {
            // CSR instructions: csrrw/csrrs/csrrc (register) and *i (5-bit immediate in rs1 field)
            let csr_addr = instr >> 20u;
            let old_val = csr_read(csr_addr);
            var new_val = old_val;
            if (funct3 == 1u) {
                new_val = rs1_val; // csrrw
            } else if (funct3 == 2u) {
                new_val = old_val | rs1_val; // csrrs
            } else if (funct3 == 3u) {
                new_val = old_val & ~rs1_val; // csrrc
            } else if (funct3 == 5u) {
                new_val = rs1; // csrrwi
            } else if (funct3 == 6u) {
                new_val = old_val | rs1; // csrrsi
            } else if (funct3 == 7u) {
                new_val = old_val & ~rs1; // csrrci
            } else {
                valid = false;
            }
            if (valid) {
                // csrrw/csrrwi always write; the set/clear variants skip the write when the
                // mask (rs1/uimm) is zero, per the RISC-V spec (avoids spurious side effects).
                let should_write = (funct3 == 1u || funct3 == 5u) || (rs1 != 0u);
                if (should_write) {
                    csr_write(csr_addr, new_val);
                }
                if (rd != 0u) { registers.x[rd] = old_val; }
            }
        }

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
    var steps = state.steps_remaining;
    
    // We add a safety cap of 65535 instructions per dispatch to avoid GPU timeouts
    if (steps > 65535u) {
        steps = 65535u;
    }
    
    var i = 0u;
    while (i < steps) {
        if (state.halted != 0u) {
            break;
        }

        state.mtime = state.mtime + 1u;
        maybe_take_interrupt();
        if (state.halted != 0u) {
            break;
        }
        if (state.trap_pending != 0u) {
            state.trap_pending = 0u;
            i = i + 1u;
            continue;
        }

        let instr = fetch();
        if (state.halted != 0u) {
            break;
        }
        if (state.trap_pending != 0u) {
            state.trap_pending = 0u;
            i = i + 1u;
            continue;
        }

        decode_and_execute(instr);
        i = i + 1u;
    }
    
    state.steps_remaining = state.steps_remaining - i;
}
