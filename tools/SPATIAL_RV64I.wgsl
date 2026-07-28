// 64-bit register file: each register is vec2<u32> (low, high)
struct RegisterFile {
    x: array<vec2<u32>, 32>,
};

struct CPUState {
    // 64-bit program counter split into low/high words
    pc_low: u32,
    pc_high: u32,
    halted: u32,
    steps_remaining: u32,
    // Privilege mode: 0 = User, 1 = Supervisor, 3 = Machine (matches RISC-V mstatus encoding)
    mode: u32,
    // Set by fetch() when instruction translation faults; tells main() to skip
    // decode_and_execute this cycle since pc has already been redirected to a trap handler.
    trap_pending: u32,
    // LR.W/SC.W reservation set (single-hart, so this is a simple address-match check).
    reservation_valid: u32,
    // 64-bit reservation address split into low/high words
    reservation_addr_low: u32,
    reservation_addr_high: u32,
    // Count of bytes ever written to the UART TX ring buffer (monotonic; host tracks its own
    // read cursor and takes it modulo the buffer capacity).
    uart_tx_len: u32,
    // CLINT timer device registers. Now 64-bit (low/high words) for RV64.
    mtime_low: u32,
    mtime_high: u32,
    mtimecmp_low: u32,
    mtimecmp_high: u32,
    // Guest physical address that maps to word 0 of our (Hilbert-mapped) `memory` buffer.
    // Now 64-bit to support >4GB address space.
    ram_base_low: u32,
    ram_base_high: u32,
    // UART RX: single byte buffer (non-blocking; if data_pending=0, reads return 0).
    uart_rx_data_pending: u32,
    uart_rx_byte: u32,
    // Length in bytes (2 or 4) of the most recently fetched instruction — set by fetch()
    // when it decodes the RVC quadrant bits, consumed by decode_and_execute() in the very
    // same cycle to pick the fallthrough PC increment. Never read across dispatches, so the
    // Python host never needs to read or write this field.
    instr_len: u32,
    // d2idx() fast-path cache for FDT scanning patterns (eliminates redundant hilbert_d2xy)
    last_d2idx_d: u32,
    last_d2idx_result: u32,
    _pad: array<u32, 2>,
};

@group(0) @binding(0) var<storage, read_write> memory: array<u32>;
@group(0) @binding(1) var<storage, read_write> registers: RegisterFile;
@group(0) @binding(2) var<storage, read_write> state: CPUState;
// Flat CSR file addressed directly by the 12-bit CSR index from the instruction encoding.
@group(0) @binding(3) var<storage, read_write> csrs: array<vec2<u32>, 4096>;
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
// QEMU "virt" machine and cnlohr/mini-rv64ima's riscv-minimal-nommu machine.
const CLINT_BASE: u32 = 0x11000000u;
const CLINT_REGION_SIZE: u32 = 0x10000u;
const CLINT_MTIMECMP_ADDR: u32 = 0x11004000u;
const CLINT_MTIME_ADDR: u32 = 0x1100BFF8u;

// Sifive-test-style syscon: any write halts the core, standing in for poweroff/reboot.
const SYSCON_ADDR: u32 = 0x11100000u;

const CSR_SSTATUS: u32 = 0x100u;
const CSR_SIE: u32 = 0x104u;
const CSR_STVEC: u32 = 0x105u;
const CSR_SEPC: u32 = 0x141u;
const CSR_SCAUSE: u32 = 0x142u;
const CSR_STVAL: u32 = 0x143u;
const CSR_SIP: u32 = 0x144u;
const CSR_MSTATUS: u32 = 0x300u;
const CSR_MEDELEG: u32 = 0x302u;
const CSR_MIDELEG: u32 = 0x303u;
const CSR_MIE: u32 = 0x304u;
const CSR_MTVEC: u32 = 0x305u;
const CSR_MEPC: u32 = 0x341u;
const CSR_MCAUSE: u32 = 0x342u;
const CSR_MTVAL: u32 = 0x343u;
const CSR_MIP: u32 = 0x344u;
const CSR_SATP: u32 = 0x180u;
const CSR_MISA: u32 = 0x301u;
// RV64 (MXL=2 in bits[63:62]) + extensions A,C,I,M,S,U (bits indexed by letter-'A'); no F/D since
// this core has no floating point. Hardcoded/read-only: OpenSBI and Linux both probe this to decide
// which privilege modes and instruction extensions are available before proceeding — without it,
// misa_extension('S') reads false and coldboot init (including the boot banner) never even runs.
const MISA_VALUE_LOW: u32 = 0x00141105u;
const MISA_VALUE_HIGH: u32 = 0x80000000u;

// sstatus is an architectural *view* of mstatus restricted to S-mode-visible bits
// (SIE=bit1, SPIE=bit5, SPP=bit8). Real hardware aliases the same physical register.
const SSTATUS_MASK: u32 = 0x122u;
// mstatus bits touched on an M-mode trap: MIE(3), MPIE(7), MPP(12:11)
const MSTATUS_TRAP_MASK: u32 = 0x1888u;

fn csr_read(addr: u32) -> vec2<u32> {
    if (addr == CSR_MISA) {
        return vec2<u32>(MISA_VALUE_LOW, MISA_VALUE_HIGH);
    } else if (addr == CSR_SSTATUS) {
        return vec2<u32>(csrs[CSR_MSTATUS].x & SSTATUS_MASK, csrs[CSR_MSTATUS].y);
    } else if (addr == CSR_SIE) {
        return vec2<u32>(csrs[CSR_MIE].x & csrs[CSR_MIDELEG].x, csrs[CSR_MIE].y & csrs[CSR_MIDELEG].y);
    } else if (addr == CSR_SIP) {
        return vec2<u32>(csrs[CSR_MIP].x & csrs[CSR_MIDELEG].x, csrs[CSR_MIP].y & csrs[CSR_MIDELEG].y);
    }
    return csrs[addr];
}

fn csr_write(addr: u32, val: vec2<u32>) {
    if (addr == CSR_SSTATUS) {
        csrs[CSR_MSTATUS].x = (csrs[CSR_MSTATUS].x & ~SSTATUS_MASK) | (val.x & SSTATUS_MASK);
        csrs[CSR_MSTATUS].y = val.y;
    } else if (addr == CSR_SIE) {
        csrs[CSR_MIE].x = (csrs[CSR_MIE].x & ~csrs[CSR_MIDELEG].x) | (val.x & csrs[CSR_MIDELEG].x);
        csrs[CSR_MIE].y = (csrs[CSR_MIE].y & ~csrs[CSR_MIDELEG].y) | (val.y & csrs[CSR_MIDELEG].y);
    } else if (addr == CSR_SIP) {
        csrs[CSR_MIP].x = (csrs[CSR_MIP].x & ~csrs[CSR_MIDELEG].x) | (val.x & csrs[CSR_MIDELEG].x);
        csrs[CSR_MIP].y = (csrs[CSR_MIP].y & ~csrs[CSR_MIDELEG].y) | (val.y & csrs[CSR_MIDELEG].y);
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
        return vec2<u32>(state.mtime_low, 1u);
    }
    if (addr == CLINT_MTIMECMP_ADDR) {
        return vec2<u32>(state.mtimecmp_low, 1u);
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
        state.mtimecmp_low = val;
        state.mtimecmp_high = 0u; // STUB: handle 64-bit writes properly
        csrs[CSR_MIP].x = csrs[CSR_MIP].x & ~0x80u; // writing mtimecmp clears any pending MTIP
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

// ============================================================================
// 64-Bit Arithmetic Helpers (STUB IMPLEMENTATIONS)
// All operations use vec2<u32> where x=low word, y=high word
// ============================================================================

// 64-bit addition with carry propagation
fn u64_add(a: vec2<u32>, b: vec2<u32>) -> vec2<u32> {
    let low = a.x + b.x;
    let carry = select(0u, 1u, low < a.x);
    let high = a.y + b.y + carry;
    return vec2<u32>(low, high);
}

// 64-bit subtraction with borrow
fn u64_sub(a: vec2<u32>, b: vec2<u32>) -> vec2<u32> {
    let low = a.x - b.x;
    let borrow = select(0u, 1u, a.x < b.x);
    let high = a.y - b.y - borrow;
    return vec2<u32>(low, high);
}

// 64-bit left shift (shift < 64)
fn u64_shl(a: vec2<u32>, shift: u32) -> vec2<u32> {
    let s = shift & 63u;
    if (s == 0u) { return a; }
    if (s >= 32u) {
        return vec2<u32>(0u, a.x << (s - 32u));
    }
    return vec2<u32>(a.x << s, (a.y << s) | (a.x >> (32u - s)));
}

// 64-bit logical right shift
fn u64_shr(a: vec2<u32>, shift: u32) -> vec2<u32> {
    let s = shift & 63u;
    if (s == 0u) { return a; }
    if (s >= 32u) {
        return vec2<u32>(a.y >> (s - 32u), 0u);
    }
    return vec2<u32>((a.x >> s) | (a.y << (32u - s)), a.y >> s);
}

// 64-bit arithmetic right shift (sign-extended)
fn u64_sar(a: vec2<u32>, shift: u32) -> vec2<u32> {
    let s = shift & 63u;
    let sign_ext = select(0u, 0xFFFFFFFFu, (a.y & 0x80000000u) != 0u);
    if (s == 0u) { return a; }
    if (s >= 32u) {
        let shift_amt = s - 32u;
        let high_shifted = bitcast<u32>(bitcast<i32>(a.y) >> shift_amt);
        return vec2<u32>(high_shifted, sign_ext);
    }
    let low = (a.x >> s) | (a.y << (32u - s));
    let high = bitcast<u32>(bitcast<i32>(a.y) >> s);
    return vec2<u32>(low, high);
}

// Sign-extend 32-bit value to 64-bit
fn sext_32_to_64(value: i32) -> vec2<u32> {
    let low = bitcast<u32>(value);
    let high = select(0u, 0xFFFFFFFFu, value < 0);
    return vec2<u32>(low, high);
}

// Zero-extend 32-bit value to 64-bit
fn zext_32_to_64(value: u32) -> vec2<u32> {
    return vec2<u32>(value, 0u);
}

// Extract low 32 bits of 64-bit value
fn u64_low(a: vec2<u32>) -> u32 {
    return a.x;
}

// Extract high 32 bits of 64-bit value
fn u64_high(a: vec2<u32>) -> u32 {
    return a.y;
}

// Combine low and high words into 64-bit value
fn u64_from_parts(low: u32, high: u32) -> vec2<u32> {
    return vec2<u32>(low, high);
}

// Check if 64-bit value is zero
fn u64_is_zero(a: vec2<u32>) -> bool {
    return (a.x == 0u) && (a.y == 0u);
}

// 64-bit equality comparison
fn u64_eq(a: vec2<u32>, b: vec2<u32>) -> bool {
    return (a.x == b.x) && (a.y == b.y);
}

// 64-bit less-than comparison (signed)
fn u64_lt(a: vec2<u32>, b: vec2<u32>) -> bool {
    let a_y = bitcast<i32>(a.y);
    let b_y = bitcast<i32>(b.y);
    if (a_y != b_y) {
        return a_y < b_y;
    }
    return a.x < b.x;
}

// 64-bit less-than comparison (unsigned)
fn u64_ltu(a: vec2<u32>, b: vec2<u32>) -> bool {
    if (a.y != b.y) {
        return a.y < b.y;
    }
    return a.x < b.x;
}

// ============================================================================
// Sub-word accessors into `memory`, operating on an address already resolved to a RAM-relative
// (i.e. RAM-base-subtracted) byte offset. Each returns (value, ok); ok=0 means out of bounds.
// ============================================================================
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
fn raise_trap(cause: u32, tval: vec2<u32>, pc: vec2<u32>) -> vec2<u32> {
    let delegate = (state.mode != 3u) && (((csrs[CSR_MEDELEG].x >> cause) & 1u) == 1u);
    let cause_hi = select(0u, 0x80000000u, (cause >> 31u) != 0u);
    let cause_lo = cause & 0x7FFFFFFFu;
    if (delegate) {
        csrs[CSR_SEPC] = pc;
        csrs[CSR_SCAUSE] = vec2<u32>(cause_lo, cause_hi);
        csrs[CSR_STVAL] = tval;
        var mstatus = csrs[CSR_MSTATUS].x;
        let sie = (mstatus >> 1u) & 1u;
        let spp = select(0u, 1u, state.mode == 1u);
        mstatus = (mstatus & ~SSTATUS_MASK) | (sie << 5u) | (spp << 8u);
        csrs[CSR_MSTATUS].x = mstatus;
        state.mode = 1u;
        if (u64_is_zero(csrs[CSR_STVEC])) {
            state.halted = 1u;
            return pc;
        }
        let vec = vec2<u32>(csrs[CSR_STVEC].x & 0xFFFFFFFCu, csrs[CSR_STVEC].y);
        state.pc_low = vec.x;
        state.pc_high = vec.y;
        return vec;
    } else {
        csrs[CSR_MEPC] = pc;
        csrs[CSR_MCAUSE] = vec2<u32>(cause_lo, cause_hi);
        csrs[CSR_MTVAL] = tval;
        var mstatus = csrs[CSR_MSTATUS].x;
        let mie = (mstatus >> 3u) & 1u;
        mstatus = (mstatus & ~MSTATUS_TRAP_MASK) | (mie << 7u) | (state.mode << 11u);
        csrs[CSR_MSTATUS].x = mstatus;
        state.mode = 3u;
        if (u64_is_zero(csrs[CSR_MTVEC])) {
            state.halted = 1u;
            return pc;
        }
        let vec = vec2<u32>(csrs[CSR_MTVEC].x & 0xFFFFFFFCu, csrs[CSR_MTVEC].y);
        state.pc_low = vec.x;
        state.pc_high = vec.y;
        return vec;
    }
}

fn do_mret() -> vec2<u32> {
    var mstatus = csrs[CSR_MSTATUS].x;
    let mpie = (mstatus >> 7u) & 1u;
    let mpp = (mstatus >> 11u) & 3u;
    mstatus = (mstatus & ~MSTATUS_TRAP_MASK) | (mpie << 3u) | (1u << 7u);
    csrs[CSR_MSTATUS].x = mstatus;
    state.mode = mpp;
    return csrs[CSR_MEPC];
}

fn do_sret() -> vec2<u32> {
    var mstatus = csrs[CSR_MSTATUS].x;
    let spie = (mstatus >> 5u) & 1u;
    let spp = (mstatus >> 8u) & 1u;
    mstatus = (mstatus & ~SSTATUS_MASK) | (spie << 1u) | (1u << 5u);
    csrs[CSR_MSTATUS].x = mstatus;
    state.mode = spp;
    return csrs[CSR_SEPC];
}

// Checks the CLINT timer against mtimecmp, latches MTIP in mip if it has fired, and — if
// that interrupt is actually enabled (mie.MTIE and, in M-mode, mstatus.MIE) — takes it right
// now: redirects pc to mtvec and sets trap_pending so main() skips decode this cycle.
fn maybe_take_interrupt() {
    if (state.mtimecmp_low != 0u && state.mtime_low >= state.mtimecmp_low) {
        csrs[CSR_MIP].x = csrs[CSR_MIP].x | 0x80u; // MTIP
    }

    let pending_enabled = csrs[CSR_MIP].x & csrs[CSR_MIE].x;
    if (pending_enabled == 0u) {
        return;
    }

    let mstatus = csrs[CSR_MSTATUS].x;
    let mie = (mstatus >> 3u) & 1u;
    let sie = (mstatus >> 1u) & 1u;
    let mideleg = csrs[CSR_MIDELEG].x;

    var taken_cause = 0xFFFFFFFFu;
    var target_mode = 0u;

    var causes = array<u32, 6>(11u, 3u, 7u, 9u, 1u, 5u);
    for (var i = 0u; i < 6u; i = i + 1u) {
        let cause = causes[i];
        if (((pending_enabled >> cause) & 1u) != 0u) {
            let delegated = ((mideleg >> cause) & 1u) != 0u;
            let t_mode = select(3u, 1u, delegated);
            
            var globally_enabled = false;
            if (state.mode < t_mode) {
                globally_enabled = true;
            } else if (state.mode == t_mode) {
                if (t_mode == 3u) {
                    globally_enabled = mie == 1u;
                } else {
                    globally_enabled = sie == 1u;
                }
            }
            
            if (globally_enabled) {
                taken_cause = cause;
                target_mode = t_mode;
                break;
            }
        }
    }

    if (taken_cause == 0xFFFFFFFFu) {
        return;
    }

    let pc = vec2<u32>(state.pc_low, state.pc_high);
    let cause_lo = taken_cause;
    let cause_hi = 0x80000000u;
    
    if (target_mode == 1u) {
        csrs[CSR_SEPC] = pc;
        csrs[CSR_SCAUSE] = vec2<u32>(cause_lo, cause_hi);
        csrs[CSR_STVAL] = vec2<u32>(0u, 0u);
        let mstatus_sie = (mstatus >> 1u) & 1u;
        let spp = select(0u, 1u, state.mode == 1u);
        csrs[CSR_MSTATUS].x = (mstatus & ~SSTATUS_MASK) | (mstatus_sie << 5u) | (spp << 8u);
        state.mode = 1u;
        if (u64_is_zero(csrs[CSR_STVEC])) {
            state.halted = 1u;
        } else {
            let vec = vec2<u32>(csrs[CSR_STVEC].x & 0xFFFFFFFCu, csrs[CSR_STVEC].y);
            state.pc_low = vec.x;
            state.pc_high = vec.y;
        }
    } else {
        csrs[CSR_MEPC] = pc;
        csrs[CSR_MCAUSE] = vec2<u32>(cause_lo, cause_hi);
        csrs[CSR_MTVAL] = vec2<u32>(0u, 0u);
        let mstatus_mie = (mstatus >> 3u) & 1u;
        csrs[CSR_MSTATUS].x = (mstatus & ~MSTATUS_TRAP_MASK) | (mstatus_mie << 7u) | (state.mode << 11u);
        state.mode = 3u;
        if (u64_is_zero(csrs[CSR_MTVEC])) {
            state.halted = 1u;
        } else {
            let vec = vec2<u32>(csrs[CSR_MTVEC].x & 0xFFFFFFFCu, csrs[CSR_MTVEC].y);
            state.pc_low = vec.x;
            state.pc_high = vec.y;
        }
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

// Side length of the Hilbert-mapped memory buffer (sqrt of its word count). This is fixed
// for the lifetime of a core instance (buffer size never changes after creation), but
// d2idx() is called on every single memory access — recomputing sqrt(f32(mem_len)) that
// often measurably slows down any code with a high ratio of memory ops per instruction
// (e.g. libfdt's byte-at-a-time property scanning). tools/spatial_rv64i_cpu.py substitutes
// this placeholder with the real value at shader-load time (see HILBERT_N_PLACEHOLDER).
const HILBERT_N: u32 = 8192u; // HILBERT_N_PLACEHOLDER — replaced at load time, do not rely on this literal

// Convert 1D distance (d) to physical 2D index with fast-path caching.
// This eliminates redundant hilbert_d2xy() computation for FDT scanning patterns
// where many sequential or same-word memory accesses occur.
fn d2idx(d: u32) -> u32 {
    // Fast path: if accessing same word as last time (different byte offset), reuse cached result
    if (d == state.last_d2idx_d) {
        return state.last_d2idx_result;
    }

    // Fallback: full recomputation
    let xy = hilbert_d2xy(HILBERT_N, d);
    let idx = xy.y * HILBERT_N + xy.x;

    // Update cache
    state.last_d2idx_d = d;
    state.last_d2idx_result = idx;

    return idx;
}

fn read_word_phys(byte_addr: u32) -> u32 {
    if (byte_addr < state.ram_base_low) {
        return 0u;
    }
    let phys = byte_addr - state.ram_base_low;
    let d = phys / 4u;
    if (d >= arrayLength(&memory)) {
        return 0u;
    }
    return memory[d2idx(d)];
}

fn read_dword_phys(byte_addr: u32) -> vec2<u32> {
    return vec2<u32>(read_word_phys(byte_addr), read_word_phys(byte_addr + 4u));
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

// Sv39 three-level page table walk.
fn translate_address(va: vec2<u32>, need_write: bool, need_exec: bool) -> vec2<u32> {
    let satp_mode = csrs[CSR_SATP].y >> 28u;
    let is_m_mode = (state.mode == 3u);
    // TODO: proper MPRV handling. For now, M-mode bypasses translation.
    if (satp_mode != 8u || is_m_mode) {
        return vec2<u32>(va.x, 0u);
    }

    // Check VA sign extension from bit 38
    let bit38 = (va.y >> 6u) & 1u;
    let expected_hi = select(0u, 0x03FFFFFFu, bit38 == 1u);
    if ((va.y >> 6u) != expected_hi) {
        return vec2<u32>(0u, 1u); // page fault
    }

    let vpn0 = (va.x >> 12u) & 0x1FFu;
    let vpn1 = (va.x >> 21u) & 0x1FFu;
    let vpn2_lo = (va.x >> 30u) & 0x3u;
    let vpn2_hi = (va.y & 0x7Fu) << 2u;
    let vpn2 = vpn2_lo | vpn2_hi;
    let off = va.x & 0xFFFu;

    // We assume 32-bit physical addresses for our GPU memory limits
    let root_ppn = csrs[CSR_SATP].x; 
    
    // Level 2
    var pte_addr = (root_ppn * 4096u) + vpn2 * 8u;
    var pte = read_dword_phys(pte_addr);
    var v = pte.x & 1u;
    var r = (pte.x >> 1u) & 1u;
    var w = (pte.x >> 2u) & 1u;
    var x = (pte.x >> 3u) & 1u;
    if (v == 0u || (r == 0u && w == 1u)) { return vec2<u32>(0u, 1u); }
    if (r == 1u || x == 1u) {
        if (!check_perm(pte.x, need_write, need_exec)) { return vec2<u32>(0u, 1u); }
        let ppn0 = (pte.x >> 10u) & 0x1FFu;
        let ppn1 = (pte.x >> 19u) & 0x1FFu;
        if (ppn0 != 0u || ppn1 != 0u) { return vec2<u32>(0u, 1u); }
        let ppn2 = (pte.x >> 28u) | ((pte.y & 0xFFFFu) << 4u);
        return vec2<u32>((ppn2 << 30u) | (vpn1 << 21u) | (vpn0 << 12u) | off, 0u);
    }

    // Level 1
    let pt1_ppn = (pte.x >> 10u) | ((pte.y & 0xFFFFu) << 22u);
    pte_addr = (pt1_ppn * 4096u) + vpn1 * 8u;
    pte = read_dword_phys(pte_addr);
    v = pte.x & 1u;
    r = (pte.x >> 1u) & 1u;
    w = (pte.x >> 2u) & 1u;
    x = (pte.x >> 3u) & 1u;
    if (v == 0u || (r == 0u && w == 1u)) { return vec2<u32>(0u, 1u); }
    if (r == 1u || x == 1u) {
        if (!check_perm(pte.x, need_write, need_exec)) { return vec2<u32>(0u, 1u); }
        let ppn0 = (pte.x >> 10u) & 0x1FFu;
        if (ppn0 != 0u) { return vec2<u32>(0u, 1u); }
        let ppn1_2 = (pte.x >> 19u) | ((pte.y & 0xFFFFu) << 13u);
        return vec2<u32>((ppn1_2 << 21u) | (vpn0 << 12u) | off, 0u);
    }

    // Level 0
    let pt0_ppn = (pte.x >> 10u) | ((pte.y & 0xFFFFu) << 22u);
    pte_addr = (pt0_ppn * 4096u) + vpn0 * 8u;
    pte = read_dword_phys(pte_addr);
    v = pte.x & 1u;
    r = (pte.x >> 1u) & 1u;
    w = (pte.x >> 2u) & 1u;
    x = (pte.x >> 3u) & 1u;
    if (v == 0u || (r == 0u && w == 1u)) { return vec2<u32>(0u, 1u); }
    if (r == 0u && w == 0u && x == 0u) { return vec2<u32>(0u, 1u); } // no further levels
    if (!check_perm(pte.x, need_write, need_exec)) { return vec2<u32>(0u, 1u); }
    let ppn_all = (pte.x >> 10u) | ((pte.y & 0xFFFFu) << 22u);
    return vec2<u32>((ppn_all << 12u) | off, 0u);
}

// ============================================================================
// RVC (compressed instruction) decode. Each function below expands a 16-bit compressed
// instruction into the equivalent standard 32-bit RV64GC encoding, which then flows through
// the existing decode_and_execute() unchanged. An unrecognized/reserved encoding expands to
// 0u, which decode_and_execute() already treats as an illegal instruction (halts).
// ============================================================================

fn rvc_sext6(imm: u32) -> u32 {
    if ((imm & 0x20u) != 0u) { return imm | 0xFFFFFFC0u; }
    return imm;
}

fn rvc_sext10(imm: u32) -> u32 {
    if ((imm & 0x200u) != 0u) { return imm | 0xFFFFFC00u; }
    return imm;
}

fn rvc_sext18(imm: u32) -> u32 {
    if ((imm & 0x20000u) != 0u) { return imm | 0xFFFC0000u; }
    return imm;
}

// C.J/C.JAL 11-bit signed, always-even offset: imm[11|4|9:8|10|6|7|3:1|5] <- c[12|11|10:9|8|7|6|5:3|2]
fn rvc_cj_offset(c: u32) -> u32 {
    let b11 = (c >> 12u) & 0x1u;
    let b4 = (c >> 11u) & 0x1u;
    let b98 = (c >> 9u) & 0x3u;
    let b10 = (c >> 8u) & 0x1u;
    let b6 = (c >> 7u) & 0x1u;
    let b7 = (c >> 6u) & 0x1u;
    let b31 = (c >> 3u) & 0x7u;
    let b5 = (c >> 2u) & 0x1u;
    var imm = (b11 << 11u) | (b10 << 10u) | (b98 << 8u) | (b7 << 7u) | (b6 << 6u) | (b5 << 5u) | (b4 << 4u) | (b31 << 1u);
    if (b11 == 1u) { imm = imm | 0xFFFFF000u; }
    return imm;
}

// C.BEQZ/C.BNEZ 8-bit signed, always-even offset: imm[8|4:3|7:6|2:1|5] <- c[12|11:10|6:5|4:3|2]
fn rvc_cb_offset(c: u32) -> u32 {
    let b8 = (c >> 12u) & 0x1u;
    let b43 = (c >> 10u) & 0x3u;
    let b76 = (c >> 5u) & 0x3u;
    let b21 = (c >> 3u) & 0x3u;
    let b5 = (c >> 2u) & 0x1u;
    var imm = (b8 << 8u) | (b76 << 6u) | (b5 << 5u) | (b43 << 3u) | (b21 << 1u);
    if (b8 == 1u) { imm = imm | 0xFFFFFE00u; }
    return imm;
}

fn rvc_encode_jal(rd: u32, imm: u32) -> u32 {
    let imm20 = (imm >> 20u) & 0x1u;
    let imm101 = (imm >> 1u) & 0x3FFu;
    let imm11 = (imm >> 11u) & 0x1u;
    let imm1912 = (imm >> 12u) & 0xFFu;
    return (imm20 << 31u) | (imm101 << 21u) | (imm11 << 20u) | (imm1912 << 12u) | (rd << 7u) | 0x6Fu;
}

fn rvc_encode_branch(funct3: u32, rs1: u32, rs2: u32, imm: u32) -> u32 {
    let imm12 = (imm >> 12u) & 0x1u;
    let imm11 = (imm >> 11u) & 0x1u;
    let imm105 = (imm >> 5u) & 0x3Fu;
    let imm41 = (imm >> 1u) & 0xFu;
    return (imm12 << 31u) | (imm105 << 25u) | (rs2 << 20u) | (rs1 << 15u) | (funct3 << 12u) | (imm41 << 8u) | (imm11 << 7u) | 0x63u;
}

fn expand_rvc(c: u32) -> u32 {
    let op = c & 0x3u;
    let funct3 = (c >> 13u) & 0x7u;

    // 3-bit "popular" register fields, biased to x8-x15.
    let rd_prime = 8u + ((c >> 2u) & 0x7u);
    let rs1_prime = 8u + ((c >> 7u) & 0x7u);
    let rs2_prime = 8u + ((c >> 2u) & 0x7u);
    // Full 5-bit register fields (CR/CI/CSS formats).
    let rd_rs1_full = (c >> 7u) & 0x1Fu;
    let rs2_full = (c >> 2u) & 0x1Fu;

    if (op == 0u) {
        if (funct3 == 0u) {
            // C.ADDI4SPN: addi rd', x2, nzuimm
            let uimm = (((c >> 11u) & 0x3u) << 4u) | (((c >> 7u) & 0xFu) << 6u) |
                       (((c >> 6u) & 0x1u) << 2u) | (((c >> 5u) & 0x1u) << 3u);
            if (uimm == 0u) { return 0u; } // all-zero encoding is reserved/illegal
            return (uimm << 20u) | (2u << 15u) | (0u << 12u) | (rd_prime << 7u) | 0x13u;
        } else if (funct3 == 2u) {
            // C.LW: lw rd', offset(rs1')
            let off = (((c >> 6u) & 0x1u) << 2u) | (((c >> 10u) & 0x7u) << 3u) | (((c >> 5u) & 0x1u) << 6u);
            return (off << 20u) | (rs1_prime << 15u) | (2u << 12u) | (rd_prime << 7u) | 0x03u;
        } else if (funct3 == 3u) {
            // C.LD: ld rd', offset(rs1')
            let off = (((c >> 10u) & 0x7u) << 3u) | (((c >> 5u) & 0x3u) << 6u);
            return (off << 20u) | (rs1_prime << 15u) | (3u << 12u) | (rd_prime << 7u) | 0x03u;
        } else if (funct3 == 6u) {
            // C.SW: sw rs2', offset(rs1')
            let off = (((c >> 6u) & 0x1u) << 2u) | (((c >> 10u) & 0x7u) << 3u) | (((c >> 5u) & 0x1u) << 6u);
            let imm5 = off & 0x1Fu;
            let imm7 = (off >> 5u) & 0x7Fu;
            return (imm7 << 25u) | (rs2_prime << 20u) | (rs1_prime << 15u) | (2u << 12u) | (imm5 << 7u) | 0x23u;
        } else if (funct3 == 7u) {
            // C.SD: sd rs2', offset(rs1')
            let off = (((c >> 10u) & 0x7u) << 3u) | (((c >> 5u) & 0x3u) << 6u);
            let imm5 = off & 0x1Fu;
            let imm7 = (off >> 5u) & 0x7Fu;
            return (imm7 << 25u) | (rs2_prime << 20u) | (rs1_prime << 15u) | (3u << 12u) | (imm5 << 7u) | 0x23u;
        }
        return 0u; // C.FLD/C.FSD (funct3 1/5): no D-extension support

    } else if (op == 1u) {
        if (funct3 == 0u) {
            // C.NOP (rd=0) / C.ADDI: addi rd, rd, nzimm
            let imm = rvc_sext6((((c >> 12u) & 0x1u) << 5u) | ((c >> 2u) & 0x1Fu));
            return (imm << 20u) | (rd_rs1_full << 15u) | (0u << 12u) | (rd_rs1_full << 7u) | 0x13u;
        } else if (funct3 == 1u) {
            // C.ADDIW (RV64/RV128 only): addiw rd, rd, imm
            let imm = rvc_sext6((((c >> 12u) & 0x1u) << 5u) | ((c >> 2u) & 0x1Fu));
            return (imm << 20u) | (rd_rs1_full << 15u) | (0u << 12u) | (rd_rs1_full << 7u) | 0x1Bu;
        } else if (funct3 == 2u) {
            // C.LI: addi rd, x0, imm
            let imm = rvc_sext6((((c >> 12u) & 0x1u) << 5u) | ((c >> 2u) & 0x1Fu));
            return (imm << 20u) | (0u << 15u) | (0u << 12u) | (rd_rs1_full << 7u) | 0x13u;
        } else if (funct3 == 3u) {
            if (rd_rs1_full == 2u) {
                // C.ADDI16SP: addi x2, x2, nzimm
                let imm = rvc_sext10((((c >> 12u) & 0x1u) << 9u) | (((c >> 3u) & 0x3u) << 7u) |
                                      (((c >> 5u) & 0x1u) << 6u) | (((c >> 2u) & 0x1u) << 5u) |
                                      (((c >> 6u) & 0x1u) << 4u));
                return (imm << 20u) | (2u << 15u) | (0u << 12u) | (2u << 7u) | 0x13u;
            } else {
                // C.LUI: lui rd, nzimm[17:12]
                let imm = rvc_sext18((((c >> 12u) & 0x1u) << 17u) | (((c >> 2u) & 0x1Fu) << 12u));
                return (imm & 0xFFFFF000u) | (rd_rs1_full << 7u) | 0x37u;
            }
        } else if (funct3 == 4u) {
            let funct2_hi = (c >> 10u) & 0x3u;
            if (funct2_hi == 0u || funct2_hi == 1u) {
                // C.SRLI / C.SRAI (CB format: single register field, rd' == rs1'; bits[6:2] is shamt)
                let shamt = (((c >> 12u) & 0x1u) << 5u) | ((c >> 2u) & 0x1Fu);
                let funct6 = select(0u, 0x10u, funct2_hi == 1u);
                return (funct6 << 26u) | (shamt << 20u) | (rs1_prime << 15u) | (5u << 12u) | (rs1_prime << 7u) | 0x13u;
            } else if (funct2_hi == 2u) {
                // C.ANDI (CB format: single register field, rd' == rs1'; bits[6:2] is imm)
                let imm = rvc_sext6((((c >> 12u) & 0x1u) << 5u) | ((c >> 2u) & 0x1Fu));
                return (imm << 20u) | (rs1_prime << 15u) | (7u << 12u) | (rs1_prime << 7u) | 0x13u;
            } else {
                // CA format: single register field at bits[9:7] (rd' == rs1'); rs2' at bits[4:2]
                let is_word = ((c >> 12u) & 0x1u) != 0u;
                let funct2_lo = (c >> 5u) & 0x3u;
                if (is_word) {
                    if (funct2_lo == 0u) {
                        return (0x20u << 25u) | (rs2_prime << 20u) | (rs1_prime << 15u) | (0u << 12u) | (rs1_prime << 7u) | 0x3Bu; // C.SUBW
                    } else if (funct2_lo == 1u) {
                        return (0u << 25u) | (rs2_prime << 20u) | (rs1_prime << 15u) | (0u << 12u) | (rs1_prime << 7u) | 0x3Bu; // C.ADDW
                    }
                    return 0u;
                } else {
                    if (funct2_lo == 0u) {
                        return (0x20u << 25u) | (rs2_prime << 20u) | (rs1_prime << 15u) | (0u << 12u) | (rs1_prime << 7u) | 0x33u; // C.SUB
                    } else if (funct2_lo == 1u) {
                        return (rs2_prime << 20u) | (rs1_prime << 15u) | (4u << 12u) | (rs1_prime << 7u) | 0x33u; // C.XOR
                    } else if (funct2_lo == 2u) {
                        return (rs2_prime << 20u) | (rs1_prime << 15u) | (6u << 12u) | (rs1_prime << 7u) | 0x33u; // C.OR
                    } else {
                        return (rs2_prime << 20u) | (rs1_prime << 15u) | (7u << 12u) | (rs1_prime << 7u) | 0x33u; // C.AND
                    }
                }
            }
        } else if (funct3 == 5u) {
            return rvc_encode_jal(0u, rvc_cj_offset(c)); // C.J
        } else if (funct3 == 6u) {
            return rvc_encode_branch(0u, rs1_prime, 0u, rvc_cb_offset(c)); // C.BEQZ
        } else if (funct3 == 7u) {
            return rvc_encode_branch(1u, rs1_prime, 0u, rvc_cb_offset(c)); // C.BNEZ
        }
        return 0u;

    } else if (op == 2u) {
        if (funct3 == 0u) {
            // C.SLLI
            let shamt = (((c >> 12u) & 0x1u) << 5u) | ((c >> 2u) & 0x1Fu);
            return (shamt << 20u) | (rd_rs1_full << 15u) | (1u << 12u) | (rd_rs1_full << 7u) | 0x13u;
        } else if (funct3 == 2u) {
            // C.LWSP: lw rd, offset(x2)
            let off = (((c >> 4u) & 0x7u) << 2u) | (((c >> 12u) & 0x1u) << 5u) | (((c >> 2u) & 0x3u) << 6u);
            return (off << 20u) | (2u << 15u) | (2u << 12u) | (rd_rs1_full << 7u) | 0x03u;
        } else if (funct3 == 3u) {
            // C.LDSP: ld rd, offset(x2)
            let off = (((c >> 5u) & 0x3u) << 3u) | (((c >> 12u) & 0x1u) << 5u) | (((c >> 2u) & 0x7u) << 6u);
            return (off << 20u) | (2u << 15u) | (3u << 12u) | (rd_rs1_full << 7u) | 0x03u;
        } else if (funct3 == 4u) {
            let bit12 = (c >> 12u) & 0x1u;
            if (bit12 == 0u) {
                if (rs2_full == 0u) {
                    return (0u << 20u) | (rd_rs1_full << 15u) | (0u << 12u) | (0u << 7u) | 0x67u; // C.JR
                } else {
                    return (rs2_full << 20u) | (0u << 15u) | (0u << 12u) | (rd_rs1_full << 7u) | 0x33u; // C.MV
                }
            } else {
                if (rd_rs1_full == 0u && rs2_full == 0u) {
                    return (1u << 20u) | 0x73u; // C.EBREAK
                } else if (rs2_full == 0u) {
                    return (0u << 20u) | (rd_rs1_full << 15u) | (0u << 12u) | (1u << 7u) | 0x67u; // C.JALR
                } else {
                    return (rs2_full << 20u) | (rd_rs1_full << 15u) | (0u << 12u) | (rd_rs1_full << 7u) | 0x33u; // C.ADD
                }
            }
        } else if (funct3 == 6u) {
            // C.SWSP: sw rs2, offset(x2)
            let off = (((c >> 9u) & 0xFu) << 2u) | (((c >> 7u) & 0x3u) << 6u);
            let imm5 = off & 0x1Fu;
            let imm7 = (off >> 5u) & 0x7Fu;
            return (imm7 << 25u) | (rs2_full << 20u) | (2u << 15u) | (2u << 12u) | (imm5 << 7u) | 0x23u;
        } else if (funct3 == 7u) {
            // C.SDSP: sd rs2, offset(x2)
            let off = (((c >> 10u) & 0x7u) << 3u) | (((c >> 7u) & 0x7u) << 6u);
            let imm5 = off & 0x1Fu;
            let imm7 = (off >> 5u) & 0x7Fu;
            return (imm7 << 25u) | (rs2_full << 20u) | (2u << 15u) | (3u << 12u) | (imm5 << 7u) | 0x23u;
        }
        return 0u;
    }
    return 0u;
}

fn fetch() -> u32 {
    let translated = translate_address(vec2<u32>(state.pc_low, state.pc_high), false, true);
    if (translated.y != 0u) {
        let new_pc = raise_trap(12u, vec2<u32>(state.pc_low, state.pc_high), vec2<u32>(state.pc_low, state.pc_high)); // instruction page fault
        state.pc_low = new_pc.x;
        state.pc_high = new_pc.y;
        state.trap_pending = 1u;
        return 0u;
    }

    if (translated.x < state.ram_base_low) {
        let new_pc2 = raise_trap(1u, vec2<u32>(state.pc_low, state.pc_high), vec2<u32>(state.pc_low, state.pc_high));
        state.pc_low = new_pc2.x;
        state.pc_high = new_pc2.y;
        state.trap_pending = 1u;
        return 0u;
    }
    let phys = translated.x - state.ram_base_low;
    let half0 = phys_read_u16(phys);
    if (half0.y == 0u) {
        state.halted = 1u;
        return 0u;
    }

    if ((half0.x & 0x3u) == 0x3u) {
        // Standard 32-bit instruction; the upper half may live in the next word.
        let half1 = phys_read_u16(phys + 2u);
        if (half1.y == 0u) {
            state.halted = 1u;
            return 0u;
        }
        state.instr_len = 4u;
        return (half1.x << 16u) | half0.x;
    } else {
        state.instr_len = 2u;
        return expand_rvc(half0.x);
    }
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

// --- RV64 M-extension: 64x64->128 unsigned multiply, 128-bit negate, restoring long division ---

// Schoolbook 64x64->128 multiply via four 32x32->64 partial products (umul64).
// Returns (r0,r1,r2,r3) limbs low-to-high, i.e. product = r3:r2:r1:r0.
fn umul64x64(a: vec2<u32>, b: vec2<u32>) -> vec4<u32> {
    let p00 = umul64(a.x, b.x);
    let p01 = umul64(a.x, b.y);
    let p10 = umul64(a.y, b.x);
    let p11 = umul64(a.y, b.y);

    let r0 = p00.x;

    let s1 = p00.y + p01.x;
    let c1 = select(0u, 1u, s1 < p00.y);
    let r1 = s1 + p10.x;
    let c2 = select(0u, 1u, r1 < s1);
    let mid_carry = c1 + c2;

    let t1 = p01.y + p10.y;
    let c3 = select(0u, 1u, t1 < p01.y);
    let t2 = t1 + mid_carry;
    let c4 = select(0u, 1u, t2 < t1);

    let r2 = t2 + p11.x;
    let c5 = select(0u, 1u, r2 < t2);
    let r3 = p11.y + c3 + c4 + c5;

    return vec4<u32>(r0, r1, r2, r3);
}

// Two's-complement negate of a 128-bit value given as (lo, hi) 64-bit halves.
fn negate128(lo: vec2<u32>, hi: vec2<u32>) -> vec4<u32> {
    let inv_lo = vec2<u32>(~lo.x, ~lo.y);
    let inv_hi = vec2<u32>(~hi.x, ~hi.y);
    let new_lo = u64_add(inv_lo, vec2<u32>(1u, 0u));
    let carry = select(0u, 1u, u64_ltu(new_lo, inv_lo));
    let new_hi = u64_add(inv_hi, vec2<u32>(carry, 0u));
    return vec4<u32>(new_lo.x, new_lo.y, new_hi.x, new_hi.y);
}

// Low 64 bits of a*b (two's-complement wraparound; identical for signed/unsigned).
fn u64_mul_low(a: vec2<u32>, b: vec2<u32>) -> vec2<u32> {
    let p = umul64x64(a, b);
    return vec2<u32>(p.x, p.y);
}

// High 64 bits of the full 128-bit product, honoring sign per operand.
fn mul_high64(a: vec2<u32>, b: vec2<u32>, signed_a: bool, signed_b: bool) -> vec2<u32> {
    let neg_a = signed_a && ((a.y >> 31u) != 0u);
    let neg_b = signed_b && ((b.y >> 31u) != 0u);
    let abs_a = select(a, negate64(a.x, a.y), neg_a);
    let abs_b = select(b, negate64(b.x, b.y), neg_b);
    let prod = umul64x64(abs_a, abs_b);
    var lo = vec2<u32>(prod.x, prod.y);
    var hi = vec2<u32>(prod.z, prod.w);
    if (neg_a != neg_b) {
        let neg = negate128(lo, hi);
        hi = vec2<u32>(neg.z, neg.w);
    }
    return hi;
}

fn u64_bit_at(a: vec2<u32>, i: u32) -> u32 {
    if (i < 32u) {
        return (a.x >> i) & 1u;
    }
    return (a.y >> (i - 32u)) & 1u;
}

// Unsigned 64-bit restoring long division. Caller handles b==0.
fn udiv64(a: vec2<u32>, b: vec2<u32>) -> vec2<u32> {
    var quotient = vec2<u32>(0u, 0u);
    var remainder = vec2<u32>(0u, 0u);
    var i: i32 = 63;
    loop {
        if (i < 0) { break; }
        remainder = u64_shl(remainder, 1u);
        remainder.x = remainder.x | u64_bit_at(a, u32(i));
        quotient = u64_shl(quotient, 1u);
        if (!u64_ltu(remainder, b)) {
            remainder = u64_sub(remainder, b);
            quotient.x = quotient.x | 1u;
        }
        i = i - 1;
    }
    return quotient;
}

fn urem64(a: vec2<u32>, b: vec2<u32>) -> vec2<u32> {
    var remainder = vec2<u32>(0u, 0u);
    var i: i32 = 63;
    loop {
        if (i < 0) { break; }
        remainder = u64_shl(remainder, 1u);
        remainder.x = remainder.x | u64_bit_at(a, u32(i));
        if (!u64_ltu(remainder, b)) {
            remainder = u64_sub(remainder, b);
        }
        i = i - 1;
    }
    return remainder;
}

const I64_MIN: vec2<u32> = vec2<u32>(0u, 0x80000000u);
const ALL_ONES_64: vec2<u32> = vec2<u32>(0xFFFFFFFFu, 0xFFFFFFFFu);

fn div_signed64(a: vec2<u32>, b: vec2<u32>) -> vec2<u32> {
    if (u64_is_zero(b)) {
        return ALL_ONES_64;
    }
    if (u64_eq(a, I64_MIN) && u64_eq(b, ALL_ONES_64)) {
        return a; // overflow: MIN_INT64 / -1 = MIN_INT64
    }
    let neg_a = (a.y >> 31u) != 0u;
    let neg_b = (b.y >> 31u) != 0u;
    let abs_a = select(a, negate64(a.x, a.y), neg_a);
    let abs_b = select(b, negate64(b.x, b.y), neg_b);
    var q = udiv64(abs_a, abs_b);
    if (neg_a != neg_b) {
        q = negate64(q.x, q.y);
    }
    return q;
}

fn rem_signed64(a: vec2<u32>, b: vec2<u32>) -> vec2<u32> {
    if (u64_is_zero(b)) {
        return a;
    }
    if (u64_eq(a, I64_MIN) && u64_eq(b, ALL_ONES_64)) {
        return vec2<u32>(0u, 0u);
    }
    let neg_a = (a.y >> 31u) != 0u;
    let neg_b = (b.y >> 31u) != 0u;
    let abs_a = select(a, negate64(a.x, a.y), neg_a);
    let abs_b = select(b, negate64(b.x, b.y), neg_b);
    var r = urem64(abs_a, abs_b);
    if (neg_a) {
        r = negate64(r.x, r.y);
    }
    return r;
}

fn div_unsigned64(a: vec2<u32>, b: vec2<u32>) -> vec2<u32> {
    if (u64_is_zero(b)) {
        return ALL_ONES_64;
    }
    return udiv64(a, b);
}

fn rem_unsigned64(a: vec2<u32>, b: vec2<u32>) -> vec2<u32> {
    if (u64_is_zero(b)) {
        return a;
    }
    return urem64(a, b);
}

fn decode_and_execute(instr: u32) {
    let opcode = instr & 0x7Fu;
    let rd = (instr >> 7u) & 0x1Fu;
    let funct3 = (instr >> 12u) & 0x7u;
    let rs1 = (instr >> 15u) & 0x1Fu;
    let rs2 = (instr >> 20u) & 0x1Fu;
    let funct7 = (instr >> 25u) & 0x7Fu;
    let funct6 = (instr >> 26u) & 0x3Fu;

    // x0 is always zero
    registers.x[0] = vec2<u32>(0u, 0u);

    let rs1_val = registers.x[rs1];
    let rs2_val = registers.x[rs2];

    let pc = vec2<u32>(state.pc_low, state.pc_high);
    var next_pc = u64_add(pc, vec2<u32>(state.instr_len, 0u));
    var valid = true;

    if (opcode == 0x13u) {
        // I-type ALU, 64-bit (addi, slti, sltiu, xori, ori, andi, slli, srli, srai)
        let imm = sign_extend_12(instr >> 20u);
        let imm64 = sext_32_to_64(bitcast<i32>(imm));
        let shamt = (instr >> 20u) & 0x3Fu; // 6-bit shamt for RV64
        var result = vec2<u32>(0u, 0u);
        if (funct3 == 0u) {
            result = u64_add(rs1_val, imm64); // addi
        } else if (funct3 == 2u) {
            result = vec2<u32>(select(0u, 1u, u64_lt(rs1_val, imm64)), 0u); // slti
        } else if (funct3 == 3u) {
            result = vec2<u32>(select(0u, 1u, u64_ltu(rs1_val, imm64)), 0u); // sltiu
        } else if (funct3 == 4u) {
            result = vec2<u32>(rs1_val.x ^ imm64.x, rs1_val.y ^ imm64.y); // xori
        } else if (funct3 == 6u) {
            result = vec2<u32>(rs1_val.x | imm64.x, rs1_val.y | imm64.y); // ori
        } else if (funct3 == 7u) {
            result = vec2<u32>(rs1_val.x & imm64.x, rs1_val.y & imm64.y); // andi
        } else if (funct3 == 1u && funct6 == 0u) {
            result = u64_shl(rs1_val, shamt); // slli
        } else if (funct3 == 5u && funct6 == 0u) {
            result = u64_shr(rs1_val, shamt); // srli
        } else if (funct3 == 5u && funct6 == 0x10u) {
            result = u64_sar(rs1_val, shamt); // srai
        } else {
            valid = false;
        }
        if (valid && rd != 0u) { registers.x[rd] = result; }

    } else if (opcode == 0x1Bu) {
        // I-type ALU, 32-bit result sign-extended to 64 (addiw, slliw, srliw, sraiw)
        let imm = sign_extend_12(instr >> 20u);
        let shamt5 = (instr >> 20u) & 0x1Fu;
        let top7 = instr >> 25u;
        var result32: i32 = 0;
        if (funct3 == 0u) {
            result32 = bitcast<i32>(rs1_val.x + imm); // addiw
        } else if (funct3 == 1u && top7 == 0u) {
            result32 = bitcast<i32>(rs1_val.x << shamt5); // slliw
        } else if (funct3 == 5u && top7 == 0u) {
            result32 = bitcast<i32>(rs1_val.x >> shamt5); // srliw
        } else if (funct3 == 5u && top7 == 0x20u) {
            result32 = bitcast<i32>(rs1_val.x) >> shamt5; // sraiw
        } else {
            valid = false;
        }
        if (valid && rd != 0u) { registers.x[rd] = sext_32_to_64(result32); }

    } else if (opcode == 0x33u && funct7 == 0x01u) {
        // M extension, 64-bit (mul, mulh, mulhsu, mulhu, div, divu, rem, remu)
        var result = vec2<u32>(0u, 0u);
        if (funct3 == 0u) {
            result = u64_mul_low(rs1_val, rs2_val); // mul
        } else if (funct3 == 1u) {
            result = mul_high64(rs1_val, rs2_val, true, true); // mulh
        } else if (funct3 == 2u) {
            result = mul_high64(rs1_val, rs2_val, true, false); // mulhsu
        } else if (funct3 == 3u) {
            result = mul_high64(rs1_val, rs2_val, false, false); // mulhu
        } else if (funct3 == 4u) {
            result = div_signed64(rs1_val, rs2_val); // div
        } else if (funct3 == 5u) {
            result = div_unsigned64(rs1_val, rs2_val); // divu
        } else if (funct3 == 6u) {
            result = rem_signed64(rs1_val, rs2_val); // rem
        } else if (funct3 == 7u) {
            result = rem_unsigned64(rs1_val, rs2_val); // remu
        } else {
            valid = false;
        }
        if (valid && rd != 0u) { registers.x[rd] = result; }

    } else if (opcode == 0x3Bu && funct7 == 0x01u) {
        // M extension, W-suffix: mulw/divw/divuw/remw/remuw (32-bit op, sign-extended result)
        var result32 = 0u;
        if (funct3 == 0u) {
            result32 = rs1_val.x * rs2_val.x; // mulw
        } else if (funct3 == 4u) {
            result32 = div_signed(rs1_val.x, rs2_val.x); // divw
        } else if (funct3 == 5u) {
            result32 = div_unsigned(rs1_val.x, rs2_val.x); // divuw
        } else if (funct3 == 6u) {
            result32 = rem_signed(rs1_val.x, rs2_val.x); // remw
        } else if (funct3 == 7u) {
            result32 = rem_unsigned(rs1_val.x, rs2_val.x); // remuw
        } else {
            valid = false;
        }
        if (valid && rd != 0u) { registers.x[rd] = sext_32_to_64(bitcast<i32>(result32)); }

    } else if (opcode == 0x33u) {
        // R-type ALU, 64-bit (add, sub, sll, slt, sltu, xor, srl, sra, or, and)
        let shamt = rs2_val.x & 0x3Fu;
        var result = vec2<u32>(0u, 0u);
        if (funct3 == 0u && funct7 == 0u) {
            result = u64_add(rs1_val, rs2_val); // add
        } else if (funct3 == 0u && funct7 == 0x20u) {
            result = u64_sub(rs1_val, rs2_val); // sub
        } else if (funct3 == 1u && funct7 == 0u) {
            result = u64_shl(rs1_val, shamt); // sll
        } else if (funct3 == 2u && funct7 == 0u) {
            result = vec2<u32>(select(0u, 1u, u64_lt(rs1_val, rs2_val)), 0u); // slt
        } else if (funct3 == 3u && funct7 == 0u) {
            result = vec2<u32>(select(0u, 1u, u64_ltu(rs1_val, rs2_val)), 0u); // sltu
        } else if (funct3 == 4u && funct7 == 0u) {
            result = vec2<u32>(rs1_val.x ^ rs2_val.x, rs1_val.y ^ rs2_val.y); // xor
        } else if (funct3 == 5u && funct7 == 0u) {
            result = u64_shr(rs1_val, shamt); // srl
        } else if (funct3 == 5u && funct7 == 0x20u) {
            result = u64_sar(rs1_val, shamt); // sra
        } else if (funct3 == 6u && funct7 == 0u) {
            result = vec2<u32>(rs1_val.x | rs2_val.x, rs1_val.y | rs2_val.y); // or
        } else if (funct3 == 7u && funct7 == 0u) {
            result = vec2<u32>(rs1_val.x & rs2_val.x, rs1_val.y & rs2_val.y); // and
        } else {
            valid = false;
        }
        if (valid && rd != 0u) { registers.x[rd] = result; }

    } else if (opcode == 0x3Bu) {
        // R-type ALU, W-suffix: addw, subw, sllw, srlw, sraw (32-bit op, sign-extended result)
        let shamt5 = rs2_val.x & 0x1Fu;
        var result32: i32 = 0;
        if (funct3 == 0u && funct7 == 0u) {
            result32 = bitcast<i32>(rs1_val.x + rs2_val.x); // addw
        } else if (funct3 == 0u && funct7 == 0x20u) {
            result32 = bitcast<i32>(rs1_val.x - rs2_val.x); // subw
        } else if (funct3 == 1u && funct7 == 0u) {
            result32 = bitcast<i32>(rs1_val.x << shamt5); // sllw
        } else if (funct3 == 5u && funct7 == 0u) {
            result32 = bitcast<i32>(rs1_val.x >> shamt5); // srlw
        } else if (funct3 == 5u && funct7 == 0x20u) {
            result32 = bitcast<i32>(rs1_val.x) >> shamt5; // sraw
        } else {
            valid = false;
        }
        if (valid && rd != 0u) { registers.x[rd] = sext_32_to_64(result32); }

    } else if (opcode == 0x03u) {
        // Load: lb/lh/lw/lbu/lhu/ld/lwu (funct3 = 0/1/2/4/5/3/6)
        let imm = sign_extend_12(instr >> 20u);
        let addr = u64_add(rs1_val, sext_32_to_64(bitcast<i32>(imm)));
        let mm = mmio_read(addr.x);
        if (mm.y != 0u) {
            if (rd != 0u) { registers.x[rd] = vec2<u32>(mm.x, 0u); }
        } else if (funct3 > 6u) {
            valid = false;
        } else {
            let translated = translate_address(addr, false, false);
            if (translated.y != 0u) {
                next_pc = raise_trap(13u, addr, vec2<u32>(state.pc_low, state.pc_high)); // load page fault
            } else if (translated.x < state.ram_base_low) {
                next_pc = raise_trap(5u, addr, vec2<u32>(state.pc_low, state.pc_high)); // load access fault
            } else {
                let phys = translated.x - state.ram_base_low;
                var result = vec2<u32>(0u, 0u);
                var ok = true;
                if (funct3 == 0u) {
                    let r = phys_read_u8(phys);
                    ok = r.y != 0u;
                    result = sext_32_to_64(bitcast<i32>(select(r.x, r.x | 0xFFFFFF00u, (r.x & 0x80u) != 0u)));
                } else if (funct3 == 4u) {
                    let r = phys_read_u8(phys);
                    ok = r.y != 0u;
                    result = vec2<u32>(r.x, 0u);
                } else if (funct3 == 1u) {
                    let r = phys_read_u16(phys);
                    ok = r.y != 0u;
                    result = sext_32_to_64(bitcast<i32>(select(r.x, r.x | 0xFFFF0000u, (r.x & 0x8000u) != 0u)));
                } else if (funct3 == 5u) {
                    let r = phys_read_u16(phys);
                    ok = r.y != 0u;
                    result = vec2<u32>(r.x, 0u);
                } else if (funct3 == 2u) {
                    let r = phys_read_u32(phys);
                    ok = r.y != 0u;
                    result = sext_32_to_64(bitcast<i32>(r.x));
                } else if (funct3 == 6u) {
                    let r = phys_read_u32(phys);
                    ok = r.y != 0u;
                    result = vec2<u32>(r.x, 0u);
                } else if (funct3 == 3u) {
                    // ld: doubleword, low word at phys, high word at phys+4
                    let rlo = phys_read_u32(phys);
                    let rhi = phys_read_u32(phys + 4u);
                    ok = rlo.y != 0u && rhi.y != 0u;
                    result = vec2<u32>(rlo.x, rhi.x);
                }
                if (ok) {
                    if (rd != 0u) { registers.x[rd] = result; }
                } else {
                    next_pc = raise_trap(5u, addr, vec2<u32>(state.pc_low, state.pc_high)); // load access fault
                }
            }
        }

    } else if (opcode == 0x23u) {
        // Store: sb/sh/sw/sd (funct3 = 0/1/2/3)
        let imm5 = (instr >> 7u) & 0x1Fu;
        let imm7 = (instr >> 25u) & 0x7Fu;
        let imm = sign_extend_12((imm7 << 5u) | imm5);
        let addr = u64_add(rs1_val, sext_32_to_64(bitcast<i32>(imm)));
        if (mmio_write(addr.x, rs2_val.x)) {
            // handled by a device
        } else if (funct3 > 3u) {
            valid = false;
        } else {
            let translated = translate_address(addr, true, false);
            if (translated.y != 0u) {
                next_pc = raise_trap(15u, addr, vec2<u32>(state.pc_low, state.pc_high)); // store/AMO page fault
            } else if (translated.x < state.ram_base_low) {
                next_pc = raise_trap(7u, addr, vec2<u32>(state.pc_low, state.pc_high)); // store access fault
            } else {
                let phys = translated.x - state.ram_base_low;
                var ok = false;
                if (funct3 == 0u) {
                    ok = phys_write_u8(phys, rs2_val.x);
                } else if (funct3 == 1u) {
                    ok = phys_write_u16(phys, rs2_val.x);
                } else if (funct3 == 2u) {
                    ok = phys_write_u32(phys, rs2_val.x);
                } else {
                    // sd: doubleword
                    ok = phys_write_u32(phys, rs2_val.x) && phys_write_u32(phys + 4u, rs2_val.y);
                }
                if (!ok) {
                    next_pc = raise_trap(7u, addr, vec2<u32>(state.pc_low, state.pc_high)); // store access fault
                }
            }
        }

    } else if (opcode == 0x2Fu) {
        // A extension: lr.w/sc.w/amo*.w (funct3=010) and lr.d/sc.d/amo*.d (funct3=011)
        let amo_op = funct7 >> 2u;

        if (funct3 != 2u && funct3 != 3u) {
            valid = false;
        } else {
            let is_dword = funct3 == 3u;
            let is_lr = amo_op == 0x02u;
            let translated = translate_address(rs1_val, !is_lr, false);
            if (translated.y != 0u) {
                next_pc = raise_trap(select(15u, 13u, is_lr), rs1_val, vec2<u32>(state.pc_low, state.pc_high));
            } else if (translated.x < state.ram_base_low) {
                next_pc = raise_trap(select(7u, 5u, is_lr), rs1_val, vec2<u32>(state.pc_low, state.pc_high));
            } else {
                let phys = translated.x - state.ram_base_low;
                let d = phys / 4u;
                if (d >= arrayLength(&memory) || (is_dword && (d + 1u) >= arrayLength(&memory))) {
                    next_pc = raise_trap(select(7u, 5u, is_lr), rs1_val, vec2<u32>(state.pc_low, state.pc_high));
                } else {
                    let idx = d2idx(d);
                    let debug_lo = memory[idx];
                    let debug_hi = select(0u, memory[d2idx(d + 1u)], is_dword);
                    // DEBUG: will check via CPU trace
                    if (is_lr) {
                        let lo = debug_lo;
                        let hi = select(0u, memory[d2idx(d + 1u)], is_dword);
                        let val = select(sext_32_to_64(bitcast<i32>(lo)), vec2<u32>(lo, hi), is_dword);
                        if (rd != 0u) { registers.x[rd] = val; }
                        state.reservation_valid = 1u;
                        state.reservation_addr_low = translated.x;
                        state.reservation_addr_high = 0u;
                    } else if (amo_op == 0x03u) {
                        // sc.w / sc.d
                        if (state.reservation_valid == 1u && state.reservation_addr_low == translated.x) {
                            memory[idx] = rs2_val.x;
                            if (is_dword) { memory[d2idx(d + 1u)] = rs2_val.y; }
                            if (rd != 0u) { registers.x[rd] = vec2<u32>(0u, 0u); } // success
                        } else if (rd != 0u) {
                            registers.x[rd] = vec2<u32>(1u, 0u); // failure
                        }
                        state.reservation_valid = 0u;
                    } else {
                        let old_lo = memory[idx];
                        let old_hi = select(0u, memory[d2idx(d + 1u)], is_dword);
                        let old = select(sext_32_to_64(bitcast<i32>(old_lo)), vec2<u32>(old_lo, old_hi), is_dword);
                        var new_val = old;
                        if (amo_op == 0x01u) {
                            new_val = rs2_val; // amoswap
                        } else if (amo_op == 0x00u) {
                            new_val = u64_add(old, rs2_val); // amoadd
                        } else if (amo_op == 0x04u) {
                            new_val = vec2<u32>(old.x ^ rs2_val.x, old.y ^ rs2_val.y); // amoxor
                        } else if (amo_op == 0x0Cu) {
                            new_val = vec2<u32>(old.x & rs2_val.x, old.y & rs2_val.y); // amoand
                        } else if (amo_op == 0x08u) {
                            new_val = vec2<u32>(old.x | rs2_val.x, old.y | rs2_val.y); // amoor
                        } else if (amo_op == 0x10u) {
                            new_val = select(rs2_val, old, u64_lt(old, rs2_val)); // amomin
                        } else if (amo_op == 0x14u) {
                            new_val = select(rs2_val, old, !u64_lt(old, rs2_val) && !u64_eq(old, rs2_val)); // amomax
                        } else if (amo_op == 0x18u) {
                            new_val = select(rs2_val, old, u64_ltu(old, rs2_val)); // amominu
                        } else if (amo_op == 0x1Cu) {
                            new_val = select(rs2_val, old, !u64_ltu(old, rs2_val) && !u64_eq(old, rs2_val)); // amomaxu
                        } else {
                            valid = false;
                        }
                        if (valid) {
                            memory[idx] = new_val.x;
                            if (is_dword) { memory[d2idx(d + 1u)] = new_val.y; }
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
        if (rd != 0u) { registers.x[rd] = sext_32_to_64(bitcast<i32>(imm)); }

    } else if (opcode == 0x17u) {
        // auipc
        let imm = instr & 0xFFFFF000u;
        if (rd != 0u) { registers.x[rd] = u64_add(pc, sext_32_to_64(bitcast<i32>(imm))); }

    } else if (opcode == 0x67u) {
        // jalr
        let imm = sign_extend_12(instr >> 20u);
        if (funct3 == 0u) {
            var jump_addr = u64_add(rs1_val, sext_32_to_64(bitcast<i32>(imm)));
            jump_addr.x = jump_addr.x & 0xFFFFFFFEu;
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
                // Native SBI dispatch, mirrors the RV32I core (see SPATIAL_RV32I.wgsl).
                let sbi_ext = registers.x[17].x; // a7
                if (state.mode == 1u && sbi_ext == 0x01u) {
                    // Legacy console putchar: character is in a0.
                    uart_tx[state.uart_tx_len % 4096u] = registers.x[10].x & 0xFFu;
                    state.uart_tx_len = state.uart_tx_len + 1u;
                    registers.x[10] = vec2<u32>(0u, 0u); // SBI_SUCCESS
                    registers.x[11] = vec2<u32>(0u, 0u);
                } else if (state.mode == 1u && sbi_ext == 0x54494D45u) {
                    // TIME extension "set timer": 64-bit deadline in a0.
                    state.mtimecmp_low = registers.x[10].x;
                    state.mtimecmp_high = registers.x[10].y;
                    csrs[CSR_MIP].x = csrs[CSR_MIP].x & ~0x80u; // clear any latched MTIP
                    registers.x[10] = vec2<u32>(0u, 0u);
                    registers.x[11] = vec2<u32>(0u, 0u);
                } else {
                    // Not a recognized SBI hypercall — take the real trap.
                    var cause = 11u; // M-mode environment call
                    if (state.mode == 0u) {
                        cause = 8u; // U-mode environment call
                    } else if (state.mode == 1u) {
                        cause = 9u; // S-mode environment call
                    }
                    next_pc = raise_trap(cause, vec2<u32>(0u, 0u), vec2<u32>(state.pc_low, state.pc_high));
                }
            } else if (funct12 == 1u) {
                next_pc = raise_trap(3u, vec2<u32>(0u, 0u), vec2<u32>(state.pc_low, state.pc_high)); // ebreak
            } else if (funct12 == 0x302u) {
                next_pc = do_mret();
            } else if (funct12 == 0x102u) {
                next_pc = do_sret();
            } else if (funct12 == 0x105u) {
                // wfi — no interrupt controller yet, treat as nop
            } else if ((funct12 >> 5u) == 0x09u) {
                // sfence.vma
                // No TLB in this emulator yet, treat as NOP.
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
                new_val = vec2<u32>(old_val.x | rs1_val.x, old_val.y | rs1_val.y); // csrrs
            } else if (funct3 == 3u) {
                new_val = vec2<u32>(old_val.x & ~rs1_val.x, old_val.y & ~rs1_val.y); // csrrc
            } else if (funct3 == 5u) {
                new_val = vec2<u32>(rs1, 0u); // csrrwi
            } else if (funct3 == 6u) {
                new_val = vec2<u32>(old_val.x | rs1, old_val.y); // csrrsi
            } else if (funct3 == 7u) {
                new_val = vec2<u32>(old_val.x & ~rs1, old_val.y); // csrrci
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
        next_pc = u64_add(pc, sext_32_to_64(bitcast<i32>(imm)));

    } else if (opcode == 0x63u) {
        // Branch (beq, bne, blt, bge, bltu, bgeu)
        let imm12 = ((instr >> 31u) << 12u) |
                    (((instr >> 7u) & 0x1u) << 11u) |
                    (((instr >> 25u) & 0x3Fu) << 5u) |
                    (((instr >> 8u) & 0xFu) << 1u);
        let imm = sign_extend_13(imm12);
        let branch_target = u64_add(pc, sext_32_to_64(bitcast<i32>(imm)));
        if (funct3 == 0u) {
            if (u64_eq(rs1_val, rs2_val)) { next_pc = branch_target; } // beq
        } else if (funct3 == 1u) {
            if (!u64_eq(rs1_val, rs2_val)) { next_pc = branch_target; } // bne
        } else if (funct3 == 4u) {
            if (u64_lt(rs1_val, rs2_val)) { next_pc = branch_target; } // blt
        } else if (funct3 == 5u) {
            if (!u64_lt(rs1_val, rs2_val)) { next_pc = branch_target; } // bge
        } else if (funct3 == 6u) {
            if (u64_ltu(rs1_val, rs2_val)) { next_pc = branch_target; } // bltu
        } else if (funct3 == 7u) {
            if (!u64_ltu(rs1_val, rs2_val)) { next_pc = branch_target; } // bgeu
        } else {
            valid = false;
        }

    } else {
        valid = false;
    }

    if (!valid) {
        let trap_pc = raise_trap(2u, vec2<u32>(instr, 0u), vec2<u32>(state.pc_low, state.pc_high)); // Illegal instruction
        state.pc_low = trap_pc.x;
        state.pc_high = trap_pc.y;
        state.trap_pending = 1u;
    } else {
        state.pc_low = next_pc.x;
        state.pc_high = next_pc.y;
    }
}

@compute @workgroup_size(1, 1, 1)
fn main(@builtin(global_invocation_id) global_id: vec3<u32>) {
    var steps = state.steps_remaining;
    
    // We add a safety cap of 65535 instructions per dispatch to avoid GPU timeouts
    if (steps > 16777216u) {
        steps = 16777216u;
    }
    
    var i = 0u;
    while (i < steps) {
        if (state.halted != 0u) {
            break;
        }

        // This is a functional (not cycle-accurate) simulator: real hardware retires far
        // more instructions per mtimer tick than we want to spend emulating, so a
        // microsecond-scale boot-time delay/calibration loop (udelay etc.) keyed off mtime
        // would otherwise cost tens to hundreds of millions of emulated instructions before
        // OpenSBI reaches its first UART write. Advance mtime by a large scale factor per
        // instruction instead of 1:1 so such waits resolve in a realistic instruction budget.
        state.mtime_low = state.mtime_low + 1024u;
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
