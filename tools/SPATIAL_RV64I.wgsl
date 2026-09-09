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
    bb_cur_slot: u32,
    bb_active: u32,
    // Basic-block measurement counters (written by main(); read back by the host for
    // the dynamic block-length distribution). Additive instrumentation — the host
    // state serializer and get_state() were extended to match.
    bb_total_insts: u32,
    bb_ctl_insts: u32,
    bb_fallback_insts: u32,
    bb_threaded_insts: u32,
    bb_threading_enabled: u32,
    // TLB instrumentation counters: read back by host to verify TLB is active
    tlb_hits: u32,
    tlb_misses: u32,
    // Timer interrupt diagnostics (for debugging RCU stall)
    timer_interrupts_fired: u32,
    interrupts_delivered: u32,
    // SBI ecall tracking (for debugging timer setup)
    sbi_ecall_console: u32,    // SBI 0x01 (console putchar)
    sbi_ecall_time: u32,       // SBI 0x54494D45 (TIME extension)
    sbi_ecall_unknown: u32,    // Other SBI extensions
    // VirtIO block device queue state (mirrored from RISCV_CPU_MMU.wgsl's RiscvCPU)
    virtio_status: u32,
    vq_desc_low: u32,
    vq_desc_high: u32,
    vq_avail_low: u32,
    vq_avail_high: u32,
    vq_used_low: u32,
    vq_used_high: u32,
    vq_idx: u32,
    vq_ready: u32,
    vq_queue_num: u32,
    vq_queue_align: u32,
};

@group(0) @binding(0) var<storage, read_write> memory: array<u32>;
@group(0) @binding(1) var<storage, read_write> registers: RegisterFile;
@group(0) @binding(2) var<storage, read_write> state: CPUState;
// Flat CSR file addressed directly by the 12-bit CSR index from the instruction encoding.
@group(0) @binding(3) var<storage, read_write> csrs: array<vec2<u32>, 4096>;
// Memory-mapped UART TX ring buffer (one byte per u32 slot, for simple host-side draining).
@group(0) @binding(4) var<storage, read_write> uart_tx: array<u32, 4096>;
// Precomputed Hilbert mapping: hilbert_lut[d] = spatial buffer index of linear word d.
// Computed ONCE on the host at core init (see tools/spatial_rv64i_cpu.py) and cached to
// disk, replacing the per-access 12-iteration hilbert_d2xy() loop. Read-only; shares
// safely across dispatches and never written by the shader.
@group(0) @binding(5) var<storage, read> hilbert_lut: array<u32>;
// Pre-decoded instruction table (basic-block threading): decoded_ops[phys/2] is the
// DecodedOp for the instruction at physical byte address phys. Decoded ONCE on the
// host (tools/rv64i_decode.py, verified against riscv64 objdump) so execute_decoded()
// runs a flat switch on pre-extracted fields instead of re-decoding bitfields and
// sign-extending immediates on every instruction, every step. Indexed by halfword so
// RVC 16-bit and standard 32-bit instructions both resolve by phys/2. The op field is
// 0xFFFFFFFF for slots the host chose not to pre-decode (data, unsupported encodings,
// padding) — those fall back to the runtime decode_and_execute() path.
struct DecodedOp {
    op: u32,    // OP_* enum; 0xFFFFFFFF = not pre-decoded (runtime fallback)
    rd: u32,
    rs1: u32,
    rs2: u32,
    imm: u32,   // pre-sign-extended to 32 bits (or shamt / LUI 20-bit<<12)
    aux: u32,   // funct3 for loads/stores/branches, csr_addr for CSR ops, amo_op/dword for A-ext
    raw: u32,   // expanded 32-bit instruction word, for validation against self-modifying code
    len: u32,   // 2 or 4 (byte length; mirrors fetch()'s instr_len)
    epoch: u32, // decode epoch tag; mismatch triggers runtime fallback (GPU-side store invalidation)
};
@group(0) @binding(6) var<storage, read> decoded_ops: array<DecodedOp>;
// Global epoch counter: incremented on every sfence.vma / satp CSR write to invalidate
// decoded_ops entries cached before GPU-side memory stores (e.g., execve's kernel copy).
var<private> decoded_ops_epoch: u32 = 0u;

// Timer-jitter PRNG state for mtime dithering (see the mtime advance loop below).
// Fixed nonzero seed keeps runs reproducible; this is timing noise for the guest's
// entropy source, not a security-relevant RNG.
// (A CSR-persisted variant was tried to make timer-IRQ timing batch-independent;
// it regressed the boot at a post-workingset wait, so reverted to var<private>.
// The fresh-boot percpu deadlock is fixed by DECODED_FASTPATH_DISABLED instead.)
var<private> mtime_jitter_lcg: u32 = 0x2545F491u;
// Accumulator clamped to [-8, 8]: once cumulative drift from the 1:1 rate hits
// either bound, the pick that would push it further is refused (delta forced back
// to 1 for that step). This caps total drift at 8 ticks forever, regardless of run
// length, so the LONG-RUN average stays effectively 1 tick/instruction even though
// individual per-instruction deltas vary between 0/1/2.
var<private> mtime_jitter_acc: i32 = 0;

// Direct-mapped Sv39 TLB: caches the final leaf translation (VPN -> PPN + perm) so the
// per-page-table-walk boot-time init loop (e.g. Alpine's early page population) doesn't
// re-walk the same 3-level tree on every access. See translate_address(). Indexed by the
// low bits of the full 27-bit VPN; entries never straddle an ASID (no ASID tagging — any
// satp write or sfence.vma invalidates the whole table, since address spaces are rare
// events compared to page-table walks).
const TLB_SIZE: u32 = 256u;
struct TlbEntry {
    tag: u32,   // bit31 = valid; bits[26:0] = VPN this entry caches
    ppn: u32,   // physical page number (translated PA >> 12); PA assumed 32-bit (see translate_address)
    perm: u32,  // bit0=r, bit1=w, bit2=x (from the leaf PTE)
    _pad: u32,
};
@group(0) @binding(7) var<storage, read_write> tlb: array<TlbEntry, 256>;

fn tlb_invalidate_all() {
    for (var i: u32 = 0u; i < TLB_SIZE; i = i + 1u) {
        tlb[i].tag = 0u;
    }
    // Bump epoch to invalidate all decoded_ops entries that may have been
    // cached before GPU-side stores (e.g., execve's kernel copy of /bin/sh).
    // This is O(1) vs. O(N) clearing the entire table.
    decoded_ops_epoch = decoded_ops_epoch + 1u;
}

fn tlb_lookup(vpn: u32, need_write: bool, need_exec: bool) -> vec2<u32> {
    // Returns (pa, hit): hit=0 means miss (or hit but permission-denied -> caller falls
    // back to the real walk, which will raise the correctly-coded page fault).
    let idx = vpn & (TLB_SIZE - 1u);
    let e = tlb[idx];
    if ((e.tag & 0x80000000u) == 0u || (e.tag & 0x07FFFFFFu) != vpn) {
        state.tlb_misses = state.tlb_misses + 1u;
        return vec2<u32>(0u, 0u);
    }
    let r = e.perm & 1u;
    let w = (e.perm >> 1u) & 1u;
    let x = (e.perm >> 2u) & 1u;
    var ok = r == 1u;
    if (need_exec) { ok = x == 1u; }
    else if (need_write) { ok = w == 1u; }
    if (!ok) {
        state.tlb_misses = state.tlb_misses + 1u;
        return vec2<u32>(0u, 0u);
    }
    state.tlb_hits = state.tlb_hits + 1u;
    return vec2<u32>((e.ppn << 12u), 1u);
}

fn tlb_insert(vpn: u32, ppn: u32, pte: u32) {
    let idx = vpn & (TLB_SIZE - 1u);
    let r = (pte >> 1u) & 1u;
    let w = (pte >> 2u) & 1u;
    let x = (pte >> 3u) & 1u;
    tlb[idx].tag = 0x80000000u | vpn;
    tlb[idx].ppn = ppn;
    tlb[idx].perm = r | (w << 1u) | (x << 2u);
}

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

// Glyph dispatch MMIO trigger (glyph_dispatch/docs/ABI.md). A write here asks
// the host to service the glyph dispatch request struct in RAM. This address is
// inside the RAM span, so it needs an explicit mmio_write branch or the write is
// lost to RAM. The written value is ignored.
const GLYPH_DISPATCH_TRIGGER: u32 = 0x88000000u;

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
// Sstc extension: lets S-mode arm its own timer directly (no SBI ecall trap-and-emulate
// round trip through M-mode). Writes already land in `csrs[CSR_STIMECMP]` via csr_write's
// generic fallthrough; what was missing is ever comparing it against mtime and raising STIP
// (bit 5) — see maybe_take_interrupt(). OpenSBI reports 'sstc' as a supported Boot HART ISA
// extension, so a kernel that prefers Sstc over the legacy SBI TIME extension would silently
// never receive a timer interrupt without this.
const CSR_STIMECMP: u32 = 0x14Du;
// Read-only hardware timer CSR, read via the `rdtime` pseudo-instruction. Linux's
// calibrate_delay()/sched_clock() read this around a busy loop to derive BogoMIPS and the
// clocksource rate; without wiring it to state.mtime it always reads 0, elapsed-time is always
// 0, and calibration never converges (observed as PC stuck in an infinite loop, "0.00 BogoMIPS").
const CSR_TIME: u32 = 0xC01u;
const CSR_MISA: u32 = 0x301u;
// RV64 (MXL=2 in bits[63:62]) + extensions A,C,I,M,S,U (bits indexed by letter-'A'); no F/D since
// this core has no floating point. Hardcoded/read-only: OpenSBI and Linux both probe this to decide
// which privilege modes and instruction extensions are available before proceeding — without it,
// misa_extension('S') reads false and coldboot init (including the boot banner) never even runs.
const MISA_VALUE_LOW: u32 = 0x00141105u;
const MISA_VALUE_HIGH: u32 = 0x80000000u;

// sstatus is an architectural *view* of mstatus restricted to S-mode-visible bits
// (SIE=bit1, SPIE=bit5, SPP=bit8). Real hardware aliases the same physical register.
const SSTATUS_MASK: u32 = 0xDE322u;
// mstatus bits touched on an M-mode trap: MIE(3), MPIE(7), MPP(12:11)
const MSTATUS_TRAP_MASK: u32 = 0x1888u;

fn csr_read(addr: u32) -> vec2<u32> {
    if (addr == CSR_MISA) {
        return vec2<u32>(MISA_VALUE_LOW, MISA_VALUE_HIGH);
    } else if (addr == CSR_TIME) {
        return vec2<u32>(state.mtime_low, state.mtime_high);
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
    } else if (addr == CSR_SATP) {
        let mode = val.y >> 28u;
        if (mode == 0u || mode == 8u) {
            if (csrs[addr].x != val.x || csrs[addr].y != val.y) {
                tlb_invalidate_all();
            }
            csrs[addr] = val;
        }
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
    
    // VirtIO-MMIO block device at 0x10007000
    if (addr >= 0x10007000u && addr < 0x10007200u) {
        let virtio_offset = addr - 0x10007000u;
        
        // Magic value register (0x00)
        if (virtio_offset == 0x00u) {
            return vec2<u32>(0x74726976u, 1u); // 'virt'
        }
        
        // Version register (0x04) 
        if (virtio_offset == 0x04u) {
            return vec2<u32>(0x00000001u, 1u); // Legacy version 1.0
        }
        
        // Device ID register (0x08)
        if (virtio_offset == 0x08u) {
            return vec2<u32>(0x00000002u, 1u); // Block device
        }
        
        // Vendor ID register (0x0C)
        if (virtio_offset == 0x0C) {
            return vec2<u32>(0x00001AF4u, 1u); // Red Hat
        }
        
        // Device features register (0x10)
        if (virtio_offset == 0x10u) {
            return vec2<u32>(0x00000003u, 1u); // VIRTIO_BLK_F_RO (1) + VIRTIO_F_VERSION_1 (2)
        }
        
        // Queue num max register (0x34)
        if (virtio_offset == 0x34u) {
            return vec2<u32>(256u, 1u); // Support 256 descriptor queue
        }
        
        // InterruptStatus (0x60): bit0 = used ring updated. Tied to the
        // pending virtio external interrupt (SEIP latched in mip by the
        // QueueNotify handler / host offload).
        if (virtio_offset == 0x60u) {
            return vec2<u32>(select(0u, 1u, (csrs[CSR_MIP].x & 0x200u) != 0u), 1u);
        }

        // Config space - capacity (0x100)
        if (virtio_offset >= 0x100u && virtio_offset < 0x108u) {
            // 256MB disk = 524288 sectors
            let sectors = 524288u;
            return vec2<u32>(sectors, 1u);
        }
        
        // Default: read as 0 but handled (not RAM)
        return vec2<u32>(0u, 1u);
    }
    
    // PLIC claim register: 0x0c200000 + context*0x1000 + 0x004. Return the
    // pending virtio source (1) while its interrupt is latched (SEIP in mip),
    // else 0. Same value for the M (ctx 0) and S (ctx 1) contexts.
    if (addr >= 0x0c200000u && addr < 0x0c400000u && (addr & 0xFFFu) == 0x004u) {
        return vec2<u32>(select(0u, 1u, (csrs[CSR_MIP].x & 0x200u) != 0u), 1u);
    }
    // PLIC (Platform-Level Interrupt Controller) at 0x0c000000u
    if (addr >= 0x0c000000u && addr < 0x10000000u) {
        return vec2<u32>(0u, 1u);
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
    
    // VirtIO-MMIO block device at 0x10007000
    if (addr >= 0x10007000u && addr < 0x10007200u) {
        let virtio_offset = addr - 0x10007000u;
        if (virtio_offset == 0x38u) {
            state.vq_queue_num = val;
        }
        if (virtio_offset == 0x3cu) {
            state.vq_queue_align = val;
        }
        if (virtio_offset == 0x40u) {
            state.vq_desc_low = val * 4096u; // Store descriptor base physical address from PFN
            let num = select(256u, state.vq_queue_num, state.vq_queue_num != 0u);
            let align = select(4096u, state.vq_queue_align, state.vq_queue_align != 0u);
            let avail = state.vq_desc_low + num * 16u;
            state.vq_avail_low = avail;
            let used = (avail + 6u + num * 2u + align - 1u) & ~(align - 1u);
            state.vq_used_low = used;
        }
        if (virtio_offset == 0x70u) {
            state.virtio_status = val;
        }
        // InterruptACK (0x64): driver clears the vring interrupt after handling.
        if (virtio_offset == 0x64u) {
            csrs[CSR_MIP].x = csrs[CSR_MIP].x & ~0x200u;
            return true;
        }
        // Queue notify register (0x50) - process virtqueue descriptors
        if (virtio_offset == 0x50u) {
            if (state.vq_ready == 2u) {
                state.vq_idx = val;
                state.halted = 2u; // VIRTIO_NOTIFY yield code for offload
            } else {
                if (process_virtqueue_spatial()) {
                    csrs[CSR_MIP].x = csrs[CSR_MIP].x | 0x200u; // assert virtio completion (SEIP)
                } else {
                    state.halted = 2u; // Standalone fallback failure yield
                }
            }
            return true;
        }
        // Other VirtIO writes: accept silently
        return true;
    }
    // PLIC complete register: 0x0c200000 + context*0x1000 + 0x004. Writing the
    // claimed source number deasserts it.
    if (addr >= 0x0c200000u && addr < 0x0c400000u && (addr & 0xFFFu) == 0x004u) {
        csrs[CSR_MIP].x = csrs[CSR_MIP].x & ~0x200u;
        return true;
    }
    // PLIC (Platform-Level Interrupt Controller) at 0x0c000000u
    if (addr >= 0x0c000000u && addr < 0x10000000u) {
        return true;
    }
    if (addr == SYSCON_ADDR) {
        state.halted = 1u; // stand-in for poweroff/reboot: cleanly stop the core
        return true;
    }
    if (addr == GLYPH_DISPATCH_TRIGGER) {
        // Ask the host to service the glyph dispatch request struct. Reuse the
        // VirtIO QueueNotify offload yield code (2) -- the Route B loop already
        // hands the host a servicing turn on halted == 2, where
        // run_with_offload_glyph() also calls GlyphDispatchHost.on_yield().
        state.halted = 2u;
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

// ============================================================================
// xv6-nano spatial isolation (GPU_OS_ROADMAP GO-1)
// ============================================================================
// Ports GlyphCPUv2's E-K1/E-K2 per-task privilege box + trap
// (systems/XV6_NANO_ISOLATION_ROADMAP.md) to this GPU RV64 engine. All
// state lives in guest RAM -- a reserved MMIO-style word block whose byte
// layout matches BOX_MMIO_BASE in tools/glyph_isa_v2.py -- so no CPUState
// field is added and every non-xv6 image (Alpine, unit fixtures) is
// untouched. Privilege mapping: GlyphCPUv2 MODE_SUPER == RV M-mode (3)
// here, MODE_USER == RV U-mode (0). Unlike GlyphCPUv2 (packed pixel PCs),
// KFAULT_PC / KSYS_PC / SYSCALL_PC here are real RV byte addresses -- the
// engine executes a flat binary, there are no pixel coordinates.
const ISO_MODE_LATCH_A: u32 = 0x8000u;
const ISO_KFAULT_PC_A:  u32 = 0x8004u;
const ISO_KSYS_PC_A:    u32 = 0x8008u;
const ISO_BOX0_LO_A:    u32 = 0x800Cu;
const ISO_BOX0_HI_A:    u32 = 0x8010u;
const ISO_BOX1_LO_A:    u32 = 0x8014u;
const ISO_BOX1_HI_A:    u32 = 0x8018u;
const ISO_FAULT_ADDR_A: u32 = 0x801Cu;
const ISO_FAULT_PC_A:   u32 = 0x8020u;
const ISO_SYSCALL_PC_A: u32 = 0x8024u;
const ISO_BOX2_LO_A:    u32 = 0x8028u;
const ISO_BOX2_HI_A:    u32 = 0x802Cu;
const ISO_SYS_N_A:      u32 = 0x8030u;
const ISO_SYS_A0_A:     u32 = 0x8034u;
const ISO_SYS_A1_A:     u32 = 0x8038u;
// GPU-only words above GlyphCPUv2's block (it stops at 0x8038):
const ISO_SWITCH_LO_A:  u32 = 0x8040u;  // [lo,hi) RV byte range of switch_to (harness-seeded)
const ISO_SWITCH_HI_A:  u32 = 0x8044u;  // -- switch_to's terminal `ret` == GlyphCPUv2's KJMP
const ISO_SYS_ACTIVE_A: u32 = 0x8048u;  // 1 while a SYSCALL (ebreak) trap is outstanding
const ISO_SNAP_BASE_A:  u32 = 0x8050u;  // 32 x (lo,hi) GPR snapshot across a SYSCALL->SYSRET (..0x8150)
// GO-2: the box as a 2D tile. A task's memory IS a rectangle on the pixel
// grid. Memory-grid width W_MEM (in 32-bit words) is a fixed shared constant
// (mirrors W_MEM in tools/glyph_isa_v2.py and the #define in xv6_nano.c). A
// byte address a -> word w = a>>2 -> (row,col) = (w / W_MEM, w % W_MEM). The
// tile words sit above the GPR snapshot (0x8150) so they never collide.
const W_MEM: u32 = 32u;                  // 128 bytes / grid row
const ISO_TILE_ROW_A:   u32 = 0x8160u;   // kernel-armed tile origin row / col ...
const ISO_TILE_COL_A:   u32 = 0x8164u;
const ISO_TILE_H_A:     u32 = 0x8168u;   // ... and extent. TILE_H == 0 -> tile unset / inert.
const ISO_TILE_W_A:     u32 = 0x816Cu;

fn iso_eligible() -> bool {
    // Only the small xv6-nano harness core opts in; Alpine / any large image
    // is never touched. Mirrors GlyphCPUv2._iso_enabled's "data memory small
    // enough to be the box harness" gate.
    return arrayLength(&memory) < 0x10000u;
}

fn iso_active() -> bool {
    return iso_eligible()
        && (phys_read_u32(ISO_KFAULT_PC_A).x != 0u || phys_read_u32(ISO_KSYS_PC_A).x != 0u);
}

fn iso_addr_in_box(a: u32) -> bool {
    let lo0 = phys_read_u32(ISO_BOX0_LO_A).x; let hi0 = phys_read_u32(ISO_BOX0_HI_A).x;
    let lo1 = phys_read_u32(ISO_BOX1_LO_A).x; let hi1 = phys_read_u32(ISO_BOX1_HI_A).x;
    let lo2 = phys_read_u32(ISO_BOX2_LO_A).x; let hi2 = phys_read_u32(ISO_BOX2_HI_A).x;
    if (hi0 != 0u && a >= lo0 && a < hi0) { return true; }
    if (hi1 != 0u && a >= lo1 && a < hi1) { return true; }
    if (hi2 != 0u && a >= lo2 && a < hi2) { return true; }
    // GO-2: the 2D tile predicate. If a tile is armed (TILE_H != 0), the
    // permitted region is the rectangle [TILE_ROW, TILE_ROW+TILE_H) x
    // [TILE_COL, TILE_COL+TILE_W) in (row,col) grid coordinates derived from
    // the byte address. An unset tile (TILE_H == 0) is inert, so the GO-1
    // scenarios are unaffected.
    let th = phys_read_u32(ISO_TILE_H_A).x;
    if (th != 0u) {
        let tw = phys_read_u32(ISO_TILE_W_A).x;
        let tr = phys_read_u32(ISO_TILE_ROW_A).x;
        let tc = phys_read_u32(ISO_TILE_COL_A).x;
        let w = a >> 2u;
        let row = w / W_MEM;
        let col = w % W_MEM;
        if (row >= tr && row < tr + th && col >= tc && col < tc + tw) { return true; }
    }
    return false;
}

// E-K1: a user-mode store outside BOX0 u BOX1 u BOX2 must trap. Records the
// fault, drops to SUPER, vectors to KFAULT_PC. Returns true (and sets
// *next_pc) when the store was trapped and must NOT land.
fn iso_check_store(addr: u32, pc: vec2<u32>, next_pc: ptr<function, vec2<u32>>) -> bool {
    if (iso_active() && state.mode == 0u && !iso_addr_in_box(addr)) {
        phys_write_u32(ISO_FAULT_ADDR_A, addr);
        phys_write_u32(ISO_FAULT_PC_A, pc.x);
        state.mode = 3u;
        *next_pc = vec2<u32>(phys_read_u32(ISO_KFAULT_PC_A).x, 0u);
        return true;
    }
    return false;
}

// switch_to's terminal `ret` == GlyphCPUv2's KJMP glyph op: unconditionally
// drop to SUPER (a clean cooperative yield returning to the scheduler),
// then re-enter USER if the scheduler armed MODE_LATCH for the task being
// switched in. Identified by PC range (harness-seeded) so every other
// computed `ret` keeps normal semantics.
fn iso_on_ret(rd: u32, ret_pc: vec2<u32>) {
    if (!iso_active() || rd != 0u) { return; }
    let slo = phys_read_u32(ISO_SWITCH_LO_A).x;
    let shi = phys_read_u32(ISO_SWITCH_HI_A).x;
    if (shi == 0u || ret_pc.x < slo || ret_pc.x >= shi) { return; }
    state.mode = 3u;
    if (phys_read_u32(ISO_MODE_LATCH_A).x == 1u) {
        state.mode = 0u;
        phys_write_u32(ISO_MODE_LATCH_A, 0u);
    }
}

fn iso_snapshot_regs() {
    for (var r: u32 = 0u; r < 32u; r = r + 1u) {
        phys_write_u32(ISO_SNAP_BASE_A + r * 8u, registers.x[r].x);
        phys_write_u32(ISO_SNAP_BASE_A + r * 8u + 4u, registers.x[r].y);
    }
}

fn iso_restore_regs() {
    for (var r: u32 = 1u; r < 32u; r = r + 1u) {
        registers.x[r] = vec2<u32>(phys_read_u32(ISO_SNAP_BASE_A + r * 8u).x,
                                   phys_read_u32(ISO_SNAP_BASE_A + r * 8u + 4u).x);
    }
}

// E-K2: `ebreak` in an isolated image with KSYS_PC set traps to the
// SUPER-mode C dispatcher. Snapshot the register file (the dispatcher is a
// plain C function -- it clobbers caller-saved regs the task expects to
// survive the inlined ebreak; a real trap saves the file, so do we),
// marshal a7/a0/a1 into the reserved words, save the resume PC, jump
// KSYS_PC. Returns true (and sets *next_pc) when handled here.
fn iso_syscall_trap(pc_after: vec2<u32>, next_pc: ptr<function, vec2<u32>>) -> bool {
    if (!iso_active()) { return false; }
    let ksys = phys_read_u32(ISO_KSYS_PC_A).x;
    if (ksys == 0u) { return false; }
    iso_snapshot_regs();
    phys_write_u32(ISO_SYS_N_A, registers.x[17].x);
    phys_write_u32(ISO_SYS_A0_A, registers.x[10].x);
    phys_write_u32(ISO_SYS_A1_A, registers.x[11].x);
    phys_write_u32(ISO_SYSCALL_PC_A, pc_after.x);
    phys_write_u32(ISO_SYS_ACTIVE_A, 1u);
    state.mode = 3u;
    *next_pc = vec2<u32>(ksys, 0u);
    return true;
}

// E-K2: `mret` out of that dispatcher (glyph SYSRET). Restore the pre-trap
// register file, deliver the dispatcher's result (SYS_A0) into a0, re-enter
// USER, resume after the ebreak. Returns true (and sets *next_pc) when this
// mret closed a SYSCALL trap.
fn iso_sysret(next_pc: ptr<function, vec2<u32>>) -> bool {
    if (!iso_active() || phys_read_u32(ISO_SYS_ACTIVE_A).x != 1u) { return false; }
    iso_restore_regs();
    registers.x[10] = vec2<u32>(phys_read_u32(ISO_SYS_A0_A).x, 0u);
    phys_write_u32(ISO_SYS_ACTIVE_A, 0u);
    state.mode = 0u;
    *next_pc = vec2<u32>(phys_read_u32(ISO_SYSCALL_PC_A).x, 0u);
    return true;
}

// ============================================================================
// VirtIO Descriptor Ring Walker (Spatial - Hilbert-mapped memory access)
// Ported from RISCV_CPU_MMU.wgsl's process_virtqueue, but adapted for the 
// spatial addressing used in SPATIAL_RV64I.wgsl (phys_read_u16/phys_read_u32
// and phys_write_u32 instead of read_phys_word/write_phys_word).
// ============================================================================

fn process_virtqueue_spatial() -> bool {
    // phys_read_*/phys_write_* take a memory-buffer BYTE OFFSET (they do
    // `addr/4 >= arrayLength(&memory)`), not a guest physical address — unlike
    // the normal load/store path which subtracts ram_base first. Every queue
    // address here (from state and from descriptors) is a guest PA, so convert
    // once by subtracting rb and keep all derived `+ offset` arithmetic relative.
    let rb = state.ram_base_low;
    // Read virtio queue physical addresses from state
    let desc_pa_low = state.vq_desc_low - rb;
    let desc_pa_high = state.vq_desc_high;
    let avail_pa_low = state.vq_avail_low - rb;
    let avail_pa_high = state.vq_avail_high;
    let used_pa_low = state.vq_used_low - rb;
    let used_pa_high = state.vq_used_high;
    
    // Read avail_idx (16-bit value at avail_pa + 2)
    let avail_idx_pa = avail_pa_low + 2u;
    let avail_result = phys_read_u16(avail_idx_pa);
    if (avail_result.y == 0u) { return false; } // read failed
    let avail_idx = avail_result.x;
    
    // No new descriptors to process
    if (state.vq_idx == avail_idx) { return false; }
    
    // Read descriptor index from avail ring
    // avail ring layout: flags[2] | idx[2] | ring[queue_num*2] | used_event[2]
    // We need the ring entry at offset 4 + (vq_idx % queue_num) * 2
    let queue_num = state.vq_queue_num;
    let ring_offset = 4u + (state.vq_idx % queue_num) * 2u;
    let desc_idx_pa = avail_pa_low + ring_offset;
    let desc_idx_result = phys_read_u16(desc_idx_pa);
    if (desc_idx_result.y == 0u) { return false; }
    let desc_idx = desc_idx_result.x;
    
    // Read descriptor 0 (header)
    // virtq_desc layout: addr[8] | len[4] | flags[2] | next[2]
    let desc0_pa = desc_pa_low + desc_idx * 16u;
    let desc0_addr_low = phys_read_u32(desc0_pa);
    if (desc0_addr_low.y == 0u) { return false; }
    let desc0_addr_low_val = desc0_addr_low.x;
    
    let desc0_addr_high = phys_read_u32(desc0_pa + 4u);
    if (desc0_addr_high.y == 0u) { return false; }
    let desc0_addr_high_val = desc0_addr_high.x;
    
    let desc0_next_result = phys_read_u32(desc0_pa + 12u);
    if (desc0_next_result.y == 0u) { return false; }
    let desc0_next = (desc0_next_result.x >> 16u) & 0xFFFFu;
    
    // Read sector number from header (at offset 8 in the descriptor's buffer)
    let header_pa = desc0_addr_low_val - rb;
    let sector_result = phys_read_u32(header_pa + 8u);
    if (sector_result.y == 0u) { return false; }
    let sector = sector_result.x;
    
    // Read descriptor 1 (data buffer)
    let desc1_pa = desc_pa_low + desc0_next * 16u;
    let desc1_addr_low = phys_read_u32(desc1_pa);
    if (desc1_addr_low.y == 0u) { return false; }
    let desc1_addr_low_val = desc1_addr_low.x;
    
    let desc1_addr_high = phys_read_u32(desc1_pa + 4u);
    if (desc1_addr_high.y == 0u) { return false; }
    
    let desc1_len_result = phys_read_u32(desc1_pa + 8u);
    if (desc1_len_result.y == 0u) { return false; }
    let desc1_len = desc1_len_result.x;
    
    let desc1_flags_result = phys_read_u32(desc1_pa + 12u);
    if (desc1_flags_result.y == 0u) { return false; }
    let desc1_flags = desc1_flags_result.x & 0xFFFFu;
    let is_write = (desc1_flags & 2u) == 0u; // VRING_DESC_F_WRITE is 2
    
    // Block device base address. NOT 0x81000000 (xv6's convention) -- on this
    // shader's actual Alpine boot memory layout that address overlaps the
    // kernel's real in-memory footprint (measured: kernel loads at 0x80200000,
    // PE SizeOfImage extends to ~0x815e3000). 0x81600000 is verified clear of
    // the kernel (1MB+ margin) and leaves room before initrd at 0x82000000.
    // Must stay in sync with DISK_PA in standalone_alpine_boot.py and the
    // disk@ reserved-memory node in tools/create_dtb.py.
    let disk_pa = (0x81600000u - rb) + sector * 512u;
    
    // Copy data between buffer and disk
    let words_to_copy = desc1_len / 4u;
    for (var i = 0u; i < words_to_copy; i = i + 1u) {
        let offset = i * 4u;
        if (is_write) {
            // Write: buffer -> disk
            let val = phys_read_u32((desc1_addr_low_val - rb) + offset);
            if (val.y == 0u) { return false; }
            if (!phys_write_u32(disk_pa + offset, val.x)) { return false; }
        } else {
            // Read: disk -> buffer
            let val = phys_read_u32(disk_pa + offset);
            if (val.y == 0u) { return false; }
            if (!phys_write_u32((desc1_addr_low_val - rb) + offset, val.x)) { return false; }
        }
    }
    
    // Handle descriptor 2 (status write) if VRING_DESC_F_NEXT is set
    if ((desc1_flags & 1u) != 0u) {
        let desc1_next = (desc1_flags_result.x >> 16u) & 0xFFFFu;
        let desc2_pa = desc_pa_low + desc1_next * 16u;
        let desc2_addr_low = phys_read_u32(desc2_pa);
        if (desc2_addr_low.y == 0u) { return false; }
        let status_pa = desc2_addr_low.x - rb;
        
        // Write 0 to status byte (byte write)
        if (!phys_write_u8(status_pa, 0u)) { return false; }
    }
    
    // Write to used ring
    let used_idx_pa = used_pa_low + 2u;
    let used_idx_result = phys_read_u16(used_idx_pa);
    if (used_idx_result.y == 0u) { return false; }
    let used_idx = used_idx_result.x;
    
    let used_ring_offset = 4u + (used_idx % queue_num) * 8u;
    let used_elem_pa = used_pa_low + used_ring_offset;
    if (!phys_write_u32(used_elem_pa, desc_idx)) { return false; }
    if (!phys_write_u32(used_elem_pa + 4u, desc1_len)) { return false; }
    
    // Increment used_idx
    let new_used_idx = (used_idx + 1u) & 0xFFFFu;
    if (!phys_write_u16(used_idx_pa, new_used_idx)) { return false; }
    
    // Advance our vq_idx
    state.vq_idx = (state.vq_idx + 1u) & 0xFFFFu;
    
    return true;
}

// Raises a synchronous exception (ecall/ebreak) from the given faulting pc and
// returns the new pc. Delegates to S-mode if medeleg has the cause bit set and
// we're not already in M-mode; otherwise traps to M-mode. If the destination
// trap vector is unconfigured (0), halts instead of jumping to address 0 —
// this keeps bare-metal programs that never set up a handler behaving as before.
fn raise_trap(cause: u32, tval: vec2<u32>, pc: vec2<u32>) -> vec2<u32> {
    // Track interrupt delivery (for RCU stall debugging)
    // Check if this is an interrupt (cause with high bit set)
    let is_interrupt = (cause >> 31u) != 0u;
    if (is_interrupt) {
        state.interrupts_delivered = state.interrupts_delivered + 1u;
    }

    // Any trap or interrupt taken between an LR and its SC must break the
    // reservation — real hardware does this, and Linux's cmpxchg loop relies on
    // sc.w failing after an interrupt. Without it, a timer IRQ landing between
    // lr.w and sc.w leaves a stale reservation, sc.w spuriously succeeds, and
    // uncontended spinlocks get corrupted into the qspinlock slowpath.
    state.reservation_valid = 0u;
    
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
        // A trap to S-mode changes ONLY SPIE<-SIE, SIE<-0, SPP<-prev priv.
        // SUM (bit 18), MXR (bit 19), FS, etc. are untouched by the hardware.
        // Clearing the whole SSTATUS_MASK here wiped SUM mid-uaccess, so a demand
        // page fault (or timer IRQ) during copy_to_user/__clear_user on a fresh
        // PIE mapping made do_page_fault see SUM=0 -> no_context -> -EFAULT on the
        // first execve. Touch only bits SIE(1)/SPIE(5)/SPP(8).
        mstatus = (mstatus & ~0x122u) | (sie << 5u) | (spp << 8u);
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
    // SRET changes ONLY SIE<-SPIE, SPIE<-1, SPP<-0 (U). SUM/MXR/FS are preserved;
    // wiping SSTATUS_MASK here cleared SUM on every return from a trap handler.
    mstatus = (mstatus & ~0x122u) | (spie << 1u) | (1u << 5u);
    csrs[CSR_MSTATUS].x = mstatus;
    state.mode = spp;
    return csrs[CSR_SEPC];
}

// Checks the CLINT timer against mtimecmp, sets MTIP in mip if it has fired, and — if
// that interrupt is actually enabled (mie.MTIE and, in M-mode, mstatus.MIE) — takes it right
// now: redirects pc to mtvec and sets trap_pending so main() skips decode this cycle.
fn maybe_take_interrupt() {
    // Timer interrupts are LEVEL-sensitive: mip.TIP reflects the comparison
    // (mtime >= compare) LIVE and deasserts the moment the handler writes a
    // larger compare value. A previous revision OR-latched the bits and never
    // cleared them ("clearing is implicit"), which turned the first armed timer
    // interrupt into an infinite interrupt storm — the Alpine boot hung the
    // instant the kernel started the tick in kernel_init_freeable (right after
    // "Mountpoint-cache hash table entries"; QEMU with the same kernel sails
    // through). Clear-and-set from the live comparison each call instead.
    let mtip_fired = state.mtimecmp_low != 0u && state.mtime_low >= state.mtimecmp_low;
    // STIP is the OR of two sources: (a) the Sstc level-sensitive comparison (stimecmp),
    // and (b) an STIP injected by OpenSBI's M-mode timer forwarding (csr_set(MIP, STIP))
    // for the legacy SBI TIME path — that injected bit is software-latched and must
    // survive until the guest re-arms the timer (the SBI TIME handler clears it) or
    // explicitly clears sip.STIP. A pure recompute from stimecmp alone would wipe the
    // forwarded tick and re-introduce the stall.
    let stip_injected = (csrs[CSR_MIP].x & 0x20u) != 0u;
    let stip_fired = stip_injected
        || (csrs[CSR_STIMECMP].x != 0u && state.mtime_low >= csrs[CSR_STIMECMP].x);
    
    // Track timer interrupt fires (for RCU stall debugging)
    if (mtip_fired || stip_fired) {
        state.timer_interrupts_fired = state.timer_interrupts_fired + 1u;
    }
    
    // ~0xA0 clears bits 7 (MTIP) and 5 (STIP); other mip bits (SSIP/MSIP/SEIP)
    // are preserved.
    csrs[CSR_MIP].x = (csrs[CSR_MIP].x & ~0xA0u)
        | select(0u, 0x80u, mtip_fired)
        | select(0u, 0x20u, stip_fired);

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
    state.interrupts_delivered = state.interrupts_delivered + 1u;
    // Break any pending LR reservation — see the note in raise_trap(). This path
    // inlines its own trap entry instead of calling raise_trap, so it needs the
    // same clear.
    state.reservation_valid = 0u;

    let pc = vec2<u32>(state.pc_low, state.pc_high);
    let cause_lo = taken_cause;
    let cause_hi = 0x80000000u;
    
    if (target_mode == 1u) {
        csrs[CSR_SEPC] = pc;
        csrs[CSR_SCAUSE] = vec2<u32>(cause_lo, cause_hi);
        csrs[CSR_STVAL] = vec2<u32>(0u, 0u);
        let mstatus_sie = (mstatus >> 1u) & 1u;
        let spp = select(0u, 1u, state.mode == 1u);
        // Only SIE(1)/SPIE(5)/SPP(8) change on an S-mode trap; preserve SUM/MXR/FS
        // (see the matching note in raise_trap()).
        csrs[CSR_MSTATUS].x = (mstatus & ~0x122u) | (mstatus_sie << 5u) | (spp << 8u);
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
// The full Hilbert mapping is precomputed on the host into the read-only hilbert_lut
// buffer (hilbert_lut[d] = spatial index of linear word d), so this is an O(1) lookup
// instead of the former 12-iteration hilbert_d2xy() loop per access.
fn d2idx(d: u32) -> u32 {
    // Fast path: if accessing same word as last time (different byte offset), reuse cached result
    if (d == state.last_d2idx_d) {
        return state.last_d2idx_result;
    }

    // O(1) lookup into the host-precomputed Hilbert mapping.
    let idx = hilbert_lut[d];

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
    // 1. Privilege / U-bit / SUM checks
    let u = (pte >> 4u) & 1u;
    let mode = state.mode;
    if (mode == 0u) {
        if (u == 0u) { return false; }
    } else if (mode == 1u) {
        if (need_exec) {
            if (u == 1u) { return false; }
        } else {
            let sum = (csrs[CSR_MSTATUS].x >> 18u) & 1u;
            if (u == 1u && sum == 0u) { return false; }
        }
    }

    // 2. Access permission checks
    let r = (pte >> 1u) & 1u;
    let w = (pte >> 2u) & 1u;
    let x = (pte >> 3u) & 1u;
    if (need_exec) {
        return x == 1u;
    }
    if (need_write) {
        return w == 1u;
    }
    let mxr = (csrs[CSR_MSTATUS].x >> 19u) & 1u;
    return r == 1u || (mxr == 1u && x == 1u);
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
    let vpn_full = (vpn2 << 18u) | (vpn1 << 9u) | vpn0;

    let cached = tlb_lookup(vpn_full, need_write, need_exec);
    if (cached.y == 1u) {
        return vec2<u32>(cached.x | off, 0u);
    }

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
        let pa2 = (ppn2 << 30u) | (vpn1 << 21u) | (vpn0 << 12u) | off;
        tlb_insert(vpn_full, pa2 >> 12u, pte.x);
        return vec2<u32>(pa2, 0u);
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
        let pa1 = (ppn1_2 << 21u) | (vpn0 << 12u) | off;
        tlb_insert(vpn_full, pa1 >> 12u, pte.x);
        return vec2<u32>(pa1, 0u);
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
    tlb_insert(vpn_full, ppn_all, pte.x);
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
        } else if (funct3 == 1u) {
            return 0x00003007u; // Dummy standard fld
        } else if (funct3 == 5u) {
            return 0x00003027u; // Dummy standard fsd
        }
        return 0u;

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
        } else if (funct3 == 1u) {
            return 0x00003007u; // Dummy standard fld
        } else if (funct3 == 5u) {
            return 0x00003027u; // Dummy standard fsd
        }
        return 0u;
    }
    return 0u;
}

struct FetchResult {
    instr: u32,
    phys: u32,
    half0: u32,
};

fn fetch() -> FetchResult {
    let translated = translate_address(vec2<u32>(state.pc_low, state.pc_high), false, true);
    if (translated.y != 0u) {
        let new_pc = raise_trap(12u, vec2<u32>(state.pc_low, state.pc_high), vec2<u32>(state.pc_low, state.pc_high)); // instruction page fault
        state.pc_low = new_pc.x;
        state.pc_high = new_pc.y;
        state.trap_pending = 1u;
        return FetchResult(0u, 0u, 0u);
    }

    if (translated.x < state.ram_base_low) {
        let new_pc2 = raise_trap(1u, vec2<u32>(state.pc_low, state.pc_high), vec2<u32>(state.pc_low, state.pc_high));
        state.pc_low = new_pc2.x;
        state.pc_high = new_pc2.y;
        state.trap_pending = 1u;
        return FetchResult(0u, 0u, 0u);
    }
    let phys = translated.x - state.ram_base_low;
    let half0 = phys_read_u16(phys);
    if (half0.y == 0u) {
        state.halted = 1u;
        return FetchResult(0u, 0u, 0u);
    }

    if ((half0.x & 0x3u) == 0x3u) {
        // Standard 32-bit instruction; the upper half lives at pc+2.
        var hi_phys = phys + 2u;
        if ((phys & 0xFFFu) == 0xFFEu) {
            // The instruction straddles a 4KB page boundary: the low halfword is
            // the last one in this page, the high halfword is in the NEXT virtual
            // page, which is not physically contiguous with this one. Translate
            // pc+2 on its own instead of assuming phys+2. (Without this, the high
            // 16 bits came from whatever RAM followed this frame -> garbage
            // immediate -> bogus jump target; hit by ld-musl PLT thunks that land
            // a jalr at offset 0xFFE.)
            let pc2 = u64_add(vec2<u32>(state.pc_low, state.pc_high), vec2<u32>(2u, 0u));
            let t2 = translate_address(pc2, false, true);
            if (t2.y != 0u) {
                let np = raise_trap(12u, pc2, vec2<u32>(state.pc_low, state.pc_high));
                state.pc_low = np.x;
                state.pc_high = np.y;
                state.trap_pending = 1u;
                return FetchResult(0u, 0u, 0u);
            }
            if (t2.x < state.ram_base_low) {
                let np = raise_trap(1u, pc2, vec2<u32>(state.pc_low, state.pc_high));
                state.pc_low = np.x;
                state.pc_high = np.y;
                state.trap_pending = 1u;
                return FetchResult(0u, 0u, 0u);
            }
            hi_phys = t2.x - state.ram_base_low;
        }
        let half1 = phys_read_u16(hi_phys);
        if (half1.y == 0u) {
            state.halted = 1u;
            return FetchResult(0u, 0u, 0u);
        }
        state.instr_len = 4u;
        return FetchResult((half1.x << 16u) | half0.x, phys, half0.x);
    } else {
        state.instr_len = 2u;
        return FetchResult(expand_rvc(half0.x), phys, half0.x);
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
            let mm_phys = mmio_read(translated.x);
            if (translated.y != 0u) {
                next_pc = raise_trap(13u, addr, vec2<u32>(state.pc_low, state.pc_high)); // load page fault
            } else if (mm_phys.y != 0u) {
                // MMIO device reached via a translated (non-identity) virtual mapping — the
                // check above only catches identity/raw-physical MMIO accesses. Any MMU-
                // enabled guest OS maps devices into virtual address space once paging is on,
                // so this path is not an edge case.
                if (rd != 0u) { registers.x[rd] = vec2<u32>(mm_phys.x, 0u); }
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
        if (iso_check_store(addr.x, vec2<u32>(state.pc_low, state.pc_high), &next_pc)) {
            // xv6-nano E-K1: out-of-box user store -- trapped, does not land
        } else if (mmio_write(addr.x, rs2_val.x)) {
            // handled by a device
        } else if (funct3 > 3u) {
            valid = false;
        } else {
            let translated = translate_address(addr, true, false);
            if (translated.y != 0u) {
                next_pc = raise_trap(15u, addr, vec2<u32>(state.pc_low, state.pc_high)); // store/AMO page fault
            } else if (mmio_write(translated.x, rs2_val.x)) {
                // MMIO device reached via a translated (non-identity) virtual mapping — see
                // the matching comment in the load path above.
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
            iso_on_ret(rd, vec2<u32>(state.pc_low, state.pc_high));  // xv6-nano E-K1 KJMP boundary
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
                    registers.x[10] = vec2<u32>(0u, 0u);
                    registers.x[11] = vec2<u32>(0u, 0u);
                    state.sbi_ecall_console = state.sbi_ecall_console + 1u;
                } else if (state.mode == 1u && sbi_ext == 0x54494D45u) {
                    // TIME extension "set timer": 64-bit deadline in a0.
                    //
                    // OpenSBI v1.7 on this platform runs its timer with the Sstc extension:
                    // its aclint driver arms the S-mode compare (stimecmp CSR, 0x14D)
                    // directly and never touches the legacy mtimecmp MMIO (which our
                    // emulator also maps to state.mtimecmp). If the native handler armed
                    // the legacy path instead (mtimecmp + mie.MTIE), the M-mode timer
                    // would fire but OpenSBI's Sstc-mode handler would never stop it:
                    // mtimecmp stays at the stale deadline, mtip_fired stays true, and the
                    // hart storms the M-mode trap handler forever (observed: 93% M-mode,
                    // boot stuck right after sched_clock init). Writing stimecmp matches
                    // what OpenSBI's mtimer_event_start does and lets the existing STIP
                    // comparison (maybe_take_interrupt) deliver the tick to S-mode
                    // directly. Also clear any stale forwarded STIP: the previous tick has
                    // been consumed by the guest re-arming.
                    csrs[CSR_STIMECMP] = vec2<u32>(registers.x[10].x, registers.x[10].y);
                    csrs[CSR_MIP].x = csrs[CSR_MIP].x & ~0x20u; // clear latched STIP
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
                // xv6-nano E-K2: ebreak -> SUPER-mode syscall dispatcher when KSYS_PC is set
                if (!iso_syscall_trap(next_pc, &next_pc)) {
                    next_pc = raise_trap(3u, vec2<u32>(0u, 0u), vec2<u32>(state.pc_low, state.pc_high)); // ebreak
                }
            } else if (funct12 == 0x302u) {
                // xv6-nano E-K2: mret closing a SYSCALL trap -> SYSRET (restore regs, mode=USER)
                if (!iso_sysret(&next_pc)) {
                    next_pc = do_mret();
                }
            } else if (funct12 == 0x102u) {
                next_pc = do_sret();
            } else if (funct12 == 0x105u) {
                // wfi — no interrupt controller yet, treat as nop
            } else if ((funct12 >> 5u) == 0x09u) {
                // sfence.vma
                tlb_invalidate_all();
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

    } else if (opcode == 0x07u || opcode == 0x27u || opcode == 0x53u ||
               opcode == 0x43u || opcode == 0x47u || opcode == 0x4Bu || opcode == 0x4Fu) {
        // Floating point no-ops (F/D dummy support for __fstate_save/restore)
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

// ============================================================================
// Pre-decoded-op execution (basic-block threading).
//
// Mirrors decode_and_execute()'s semantics exactly, but reads op/rd/rs1/rs2/imm/aux
// from a DecodedOp that the host decoded ONCE (tools/rv64i_decode.py, verified
// against riscv64 objdump). No bitfield extraction, no sign-extension, no RVC
// expansion in the hot loop, and no illegal-instruction fallback needed (the host
// only pre-decodes statically-valid encodings). The `imm` field is already
// sign-extended to 32 bits (or holds a shift amount / LUI 20-bit<<12), and the
// execute side extends to 64 bits where the ISA requires it.
//
// DecodedOp.op values must match OP_* in tools/rv64i_decode.py exactly.
// ============================================================================
fn execute_decoded(op: DecodedOp) {
    // x0 is always zero
    registers.x[0] = vec2<u32>(0u, 0u);

    let rs1_val = registers.x[op.rs1];
    let rs2_val = registers.x[op.rs2];

    let pc = vec2<u32>(state.pc_low, state.pc_high);
    var next_pc = u64_add(pc, vec2<u32>(state.instr_len, 0u));

    let imm64 = sext_32_to_64(bitcast<i32>(op.imm));

    switch (op.op) {
        // --- OP-IMM (0x13) ---
        case 0u: { // ADDI
            if (op.rd != 0u) { registers.x[op.rd] = u64_add(rs1_val, imm64); }
        }
        case 1u: { // SLTI
            if (op.rd != 0u) { registers.x[op.rd] = vec2<u32>(select(0u, 1u, u64_lt(rs1_val, imm64)), 0u); }
        }
        case 2u: { // SLTIU
            if (op.rd != 0u) { registers.x[op.rd] = vec2<u32>(select(0u, 1u, u64_ltu(rs1_val, imm64)), 0u); }
        }
        case 3u: { // XORI
            if (op.rd != 0u) { registers.x[op.rd] = vec2<u32>(rs1_val.x ^ op.imm, rs1_val.y ^ imm64.y); }
        }
        case 4u: { // ORI
            if (op.rd != 0u) { registers.x[op.rd] = vec2<u32>(rs1_val.x | op.imm, rs1_val.y | imm64.y); }
        }
        case 5u: { // ANDI
            if (op.rd != 0u) { registers.x[op.rd] = vec2<u32>(rs1_val.x & op.imm, rs1_val.y & imm64.y); }
        }
        case 6u: { // SLLI
            if (op.rd != 0u) { registers.x[op.rd] = u64_shl(rs1_val, op.imm); }
        }
        case 7u: { // SRLI
            if (op.rd != 0u) { registers.x[op.rd] = u64_shr(rs1_val, op.imm); }
        }
        case 8u: { // SRAI
            if (op.rd != 0u) { registers.x[op.rd] = u64_sar(rs1_val, op.imm); }
        }

        // --- Branch (0x63): target = pc + sign-extended imm ---
        case 9u: { // BEQ
            if (u64_eq(rs1_val, rs2_val)) { next_pc = u64_add(pc, imm64); }
        }
        case 10u: { // BNE
            if (!u64_eq(rs1_val, rs2_val)) { next_pc = u64_add(pc, imm64); }
        }
        case 11u: { // BLT
            if (u64_lt(rs1_val, rs2_val)) { next_pc = u64_add(pc, imm64); }
        }
        case 12u: { // BGE
            if (!u64_lt(rs1_val, rs2_val)) { next_pc = u64_add(pc, imm64); }
        }
        case 13u: { // BLTU
            if (u64_ltu(rs1_val, rs2_val)) { next_pc = u64_add(pc, imm64); }
        }
        case 14u: { // BGEU
            if (!u64_ltu(rs1_val, rs2_val)) { next_pc = u64_add(pc, imm64); }
        }

        // --- Load (0x03): aux = funct3 ---
        case 15u: { // LB
            let addr = u64_add(rs1_val, imm64);
            let mm = mmio_read(addr.x);
            if (mm.y != 0u) {
                if (op.rd != 0u) { registers.x[op.rd] = vec2<u32>(mm.x, 0u); }
            } else {
                let translated = translate_address(addr, false, false);
                let mm_phys = mmio_read(translated.x);
                if (translated.y != 0u) {
                    next_pc = raise_trap(13u, addr, pc);
                } else if (mm_phys.y != 0u) {
                    if (op.rd != 0u) { registers.x[op.rd] = vec2<u32>(mm_phys.x, 0u); }
                } else if (translated.x < state.ram_base_low) {
                    next_pc = raise_trap(5u, addr, pc);
                } else {
                    let phys = translated.x - state.ram_base_low;
                    let r = phys_read_u8(phys);
                    if (r.y != 0u) {
                        if (op.rd != 0u) { registers.x[op.rd] = sext_32_to_64(bitcast<i32>(select(r.x, r.x | 0xFFFFFF00u, (r.x & 0x80u) != 0u))); }
                    } else {
                        next_pc = raise_trap(5u, addr, pc);
                    }
                }
            }
        }
        case 16u: { // LH
            let addr = u64_add(rs1_val, imm64);
            let mm = mmio_read(addr.x);
            if (mm.y != 0u) {
                if (op.rd != 0u) { registers.x[op.rd] = vec2<u32>(mm.x, 0u); }
            } else {
                let translated = translate_address(addr, false, false);
                let mm_phys = mmio_read(translated.x);
                if (translated.y != 0u) {
                    next_pc = raise_trap(13u, addr, pc);
                } else if (mm_phys.y != 0u) {
                    if (op.rd != 0u) { registers.x[op.rd] = vec2<u32>(mm_phys.x, 0u); }
                } else if (translated.x < state.ram_base_low) {
                    next_pc = raise_trap(5u, addr, pc);
                } else {
                    let phys = translated.x - state.ram_base_low;
                    let r = phys_read_u16(phys);
                    if (r.y != 0u) {
                        if (op.rd != 0u) { registers.x[op.rd] = sext_32_to_64(bitcast<i32>(select(r.x, r.x | 0xFFFF0000u, (r.x & 0x8000u) != 0u))); }
                    } else {
                        next_pc = raise_trap(5u, addr, pc);
                    }
                }
            }
        }
        case 17u: { // LW
            let addr = u64_add(rs1_val, imm64);
            let mm = mmio_read(addr.x);
            if (mm.y != 0u) {
                if (op.rd != 0u) { registers.x[op.rd] = vec2<u32>(mm.x, 0u); }
            } else {
                let translated = translate_address(addr, false, false);
                let mm_phys = mmio_read(translated.x);
                if (translated.y != 0u) {
                    next_pc = raise_trap(13u, addr, pc);
                } else if (mm_phys.y != 0u) {
                    if (op.rd != 0u) { registers.x[op.rd] = vec2<u32>(mm_phys.x, 0u); }
                } else if (translated.x < state.ram_base_low) {
                    next_pc = raise_trap(5u, addr, pc);
                } else {
                    let phys = translated.x - state.ram_base_low;
                    let r = phys_read_u32(phys);
                    if (r.y != 0u) {
                        if (op.rd != 0u) { registers.x[op.rd] = sext_32_to_64(bitcast<i32>(r.x)); }
                    } else {
                        next_pc = raise_trap(5u, addr, pc);
                    }
                }
            }
        }
        case 18u: { // LBU
            let addr = u64_add(rs1_val, imm64);
            let mm = mmio_read(addr.x);
            if (mm.y != 0u) {
                if (op.rd != 0u) { registers.x[op.rd] = vec2<u32>(mm.x, 0u); }
            } else {
                let translated = translate_address(addr, false, false);
                let mm_phys = mmio_read(translated.x);
                if (translated.y != 0u) {
                    next_pc = raise_trap(13u, addr, pc);
                } else if (mm_phys.y != 0u) {
                    if (op.rd != 0u) { registers.x[op.rd] = vec2<u32>(mm_phys.x, 0u); }
                } else if (translated.x < state.ram_base_low) {
                    next_pc = raise_trap(5u, addr, pc);
                } else {
                    let phys = translated.x - state.ram_base_low;
                    let r = phys_read_u8(phys);
                    if (r.y != 0u) {
                        if (op.rd != 0u) { registers.x[op.rd] = vec2<u32>(r.x, 0u); }
                    } else {
                        next_pc = raise_trap(5u, addr, pc);
                    }
                }
            }
        }
        case 19u: { // LHU
            let addr = u64_add(rs1_val, imm64);
            let mm = mmio_read(addr.x);
            if (mm.y != 0u) {
                if (op.rd != 0u) { registers.x[op.rd] = vec2<u32>(mm.x, 0u); }
            } else {
                let translated = translate_address(addr, false, false);
                let mm_phys = mmio_read(translated.x);
                if (translated.y != 0u) {
                    next_pc = raise_trap(13u, addr, pc);
                } else if (mm_phys.y != 0u) {
                    if (op.rd != 0u) { registers.x[op.rd] = vec2<u32>(mm_phys.x, 0u); }
                } else if (translated.x < state.ram_base_low) {
                    next_pc = raise_trap(5u, addr, pc);
                } else {
                    let phys = translated.x - state.ram_base_low;
                    let r = phys_read_u16(phys);
                    if (r.y != 0u) {
                        if (op.rd != 0u) { registers.x[op.rd] = vec2<u32>(r.x, 0u); }
                    } else {
                        next_pc = raise_trap(5u, addr, pc);
                    }
                }
            }
        }
        case 20u: { // LD
            let addr = u64_add(rs1_val, imm64);
            let mm = mmio_read(addr.x);
            if (mm.y != 0u) {
                if (op.rd != 0u) { registers.x[op.rd] = vec2<u32>(mm.x, 0u); }
            } else {
                let translated = translate_address(addr, false, false);
                let mm_phys = mmio_read(translated.x);
                if (translated.y != 0u) {
                    next_pc = raise_trap(13u, addr, pc);
                } else if (mm_phys.y != 0u) {
                    if (op.rd != 0u) { registers.x[op.rd] = vec2<u32>(mm_phys.x, 0u); }
                } else if (translated.x < state.ram_base_low) {
                    next_pc = raise_trap(5u, addr, pc);
                } else {
                    let phys = translated.x - state.ram_base_low;
                    let rlo = phys_read_u32(phys);
                    let rhi = phys_read_u32(phys + 4u);
                    if (rlo.y != 0u && rhi.y != 0u) {
                        if (op.rd != 0u) { registers.x[op.rd] = vec2<u32>(rlo.x, rhi.x); }
                    } else {
                        next_pc = raise_trap(5u, addr, pc);
                    }
                }
            }
        }
        case 21u: { // LWU
            let addr = u64_add(rs1_val, imm64);
            let mm = mmio_read(addr.x);
            if (mm.y != 0u) {
                if (op.rd != 0u) { registers.x[op.rd] = vec2<u32>(mm.x, 0u); }
            } else {
                let translated = translate_address(addr, false, false);
                let mm_phys = mmio_read(translated.x);
                if (translated.y != 0u) {
                    next_pc = raise_trap(13u, addr, pc);
                } else if (mm_phys.y != 0u) {
                    if (op.rd != 0u) { registers.x[op.rd] = vec2<u32>(mm_phys.x, 0u); }
                } else if (translated.x < state.ram_base_low) {
                    next_pc = raise_trap(5u, addr, pc);
                } else {
                    let phys = translated.x - state.ram_base_low;
                    let r = phys_read_u32(phys);
                    if (r.y != 0u) {
                        if (op.rd != 0u) { registers.x[op.rd] = vec2<u32>(r.x, 0u); }
                    } else {
                        next_pc = raise_trap(5u, addr, pc);
                    }
                }
            }
        }

        // --- Store (0x23): aux = funct3 ---
        case 22u: { // SB
            let addr = u64_add(rs1_val, imm64);
            if (iso_check_store(addr.x, pc, &next_pc)) {
            } else if (mmio_write(addr.x, rs2_val.x)) {
            } else {
                let translated = translate_address(addr, true, false);
                if (translated.y != 0u) {
                    next_pc = raise_trap(15u, addr, pc);
                } else if (mmio_write(translated.x, rs2_val.x)) {
                } else if (translated.x < state.ram_base_low) {
                    next_pc = raise_trap(7u, addr, pc);
                } else {
                    let phys = translated.x - state.ram_base_low;
                    if (!phys_write_u8(phys, rs2_val.x)) {
                        next_pc = raise_trap(7u, addr, pc);
                    }
                }
            }
        }
        case 23u: { // SH
            let addr = u64_add(rs1_val, imm64);
            if (iso_check_store(addr.x, pc, &next_pc)) {
            } else if (mmio_write(addr.x, rs2_val.x)) {
            } else {
                let translated = translate_address(addr, true, false);
                if (translated.y != 0u) {
                    next_pc = raise_trap(15u, addr, pc);
                } else if (mmio_write(translated.x, rs2_val.x)) {
                } else if (translated.x < state.ram_base_low) {
                    next_pc = raise_trap(7u, addr, pc);
                } else {
                    let phys = translated.x - state.ram_base_low;
                    if (!phys_write_u16(phys, rs2_val.x)) {
                        next_pc = raise_trap(7u, addr, pc);
                    }
                }
            }
        }
        case 24u: { // SW
            let addr = u64_add(rs1_val, imm64);
            if (iso_check_store(addr.x, pc, &next_pc)) {
            } else if (mmio_write(addr.x, rs2_val.x)) {
            } else {
                let translated = translate_address(addr, true, false);
                if (translated.y != 0u) {
                    next_pc = raise_trap(15u, addr, pc);
                } else if (mmio_write(translated.x, rs2_val.x)) {
                } else if (translated.x < state.ram_base_low) {
                    next_pc = raise_trap(7u, addr, pc);
                } else {
                    let phys = translated.x - state.ram_base_low;
                    if (!phys_write_u32(phys, rs2_val.x)) {
                        next_pc = raise_trap(7u, addr, pc);
                    }
                }
            }
        }
        case 25u: { // SD
            let addr = u64_add(rs1_val, imm64);
            if (iso_check_store(addr.x, pc, &next_pc)) {
            } else if (mmio_write(addr.x, rs2_val.x)) {
            } else {
                let translated = translate_address(addr, true, false);
                if (translated.y != 0u) {
                    next_pc = raise_trap(15u, addr, pc);
                } else if (mmio_write(translated.x, rs2_val.x)) {
                } else if (translated.x < state.ram_base_low) {
                    next_pc = raise_trap(7u, addr, pc);
                } else {
                    let phys = translated.x - state.ram_base_low;
                    if (!phys_write_u32(phys, rs2_val.x) || !phys_write_u32(phys + 4u, rs2_val.y)) {
                        next_pc = raise_trap(7u, addr, pc);
                    }
                }
            }
        }

        // --- M extension 64-bit (0x33, funct7=0x01) ---
        case 26u: { // MUL
            if (op.rd != 0u) { registers.x[op.rd] = u64_mul_low(rs1_val, rs2_val); }
        }
        case 27u: { // MULH
            if (op.rd != 0u) { registers.x[op.rd] = mul_high64(rs1_val, rs2_val, true, true); }
        }
        case 28u: { // MULHSU
            if (op.rd != 0u) { registers.x[op.rd] = mul_high64(rs1_val, rs2_val, true, false); }
        }
        case 29u: { // MULHU
            if (op.rd != 0u) { registers.x[op.rd] = mul_high64(rs1_val, rs2_val, false, false); }
        }
        case 30u: { // DIV
            if (op.rd != 0u) { registers.x[op.rd] = div_signed64(rs1_val, rs2_val); }
        }
        case 31u: { // DIVU
            if (op.rd != 0u) { registers.x[op.rd] = div_unsigned64(rs1_val, rs2_val); }
        }
        case 32u: { // REM
            if (op.rd != 0u) { registers.x[op.rd] = rem_signed64(rs1_val, rs2_val); }
        }
        case 33u: { // REMU
            if (op.rd != 0u) { registers.x[op.rd] = rem_unsigned64(rs1_val, rs2_val); }
        }

        // --- R-type 64-bit (0x33) ---
        case 34u: { // ADD
            if (op.rd != 0u) { registers.x[op.rd] = u64_add(rs1_val, rs2_val); }
        }
        case 35u: { // SUB
            if (op.rd != 0u) { registers.x[op.rd] = u64_sub(rs1_val, rs2_val); }
        }
        case 36u: { // SLL
            if (op.rd != 0u) { registers.x[op.rd] = u64_shl(rs1_val, rs2_val.x & 0x3Fu); }
        }
        case 37u: { // SLT
            if (op.rd != 0u) { registers.x[op.rd] = vec2<u32>(select(0u, 1u, u64_lt(rs1_val, rs2_val)), 0u); }
        }
        case 38u: { // SLTU
            if (op.rd != 0u) { registers.x[op.rd] = vec2<u32>(select(0u, 1u, u64_ltu(rs1_val, rs2_val)), 0u); }
        }
        case 39u: { // XOR
            if (op.rd != 0u) { registers.x[op.rd] = vec2<u32>(rs1_val.x ^ rs2_val.x, rs1_val.y ^ rs2_val.y); }
        }
        case 40u: { // SRL
            if (op.rd != 0u) { registers.x[op.rd] = u64_shr(rs1_val, rs2_val.x & 0x3Fu); }
        }
        case 41u: { // SRA
            if (op.rd != 0u) { registers.x[op.rd] = u64_sar(rs1_val, rs2_val.x & 0x3Fu); }
        }
        case 42u: { // OR
            if (op.rd != 0u) { registers.x[op.rd] = vec2<u32>(rs1_val.x | rs2_val.x, rs1_val.y | rs2_val.y); }
        }
        case 43u: { // AND
            if (op.rd != 0u) { registers.x[op.rd] = vec2<u32>(rs1_val.x & rs2_val.x, rs1_val.y & rs2_val.y); }
        }

        // --- M extension W (0x3B, funct7=0x01) ---
        case 44u: { // MULW
            if (op.rd != 0u) { registers.x[op.rd] = sext_32_to_64(bitcast<i32>(rs1_val.x * rs2_val.x)); }
        }
        case 45u: { // DIVW
            if (op.rd != 0u) { registers.x[op.rd] = sext_32_to_64(bitcast<i32>(div_signed(rs1_val.x, rs2_val.x))); }
        }
        case 46u: { // DIVUW
            if (op.rd != 0u) { registers.x[op.rd] = sext_32_to_64(bitcast<i32>(div_unsigned(rs1_val.x, rs2_val.x))); }
        }
        case 47u: { // REMW
            if (op.rd != 0u) { registers.x[op.rd] = sext_32_to_64(bitcast<i32>(rem_signed(rs1_val.x, rs2_val.x))); }
        }
        case 48u: { // REMUW
            if (op.rd != 0u) { registers.x[op.rd] = sext_32_to_64(bitcast<i32>(rem_unsigned(rs1_val.x, rs2_val.x))); }
        }

        // --- R-type W (0x3B) ---
        case 49u: { // ADDW
            if (op.rd != 0u) { registers.x[op.rd] = sext_32_to_64(bitcast<i32>(rs1_val.x + rs2_val.x)); }
        }
        case 50u: { // SUBW
            if (op.rd != 0u) { registers.x[op.rd] = sext_32_to_64(bitcast<i32>(rs1_val.x - rs2_val.x)); }
        }
        case 51u: { // SLLW
            if (op.rd != 0u) { registers.x[op.rd] = sext_32_to_64(bitcast<i32>(rs1_val.x << (rs2_val.x & 0x1Fu))); }
        }
        case 52u: { // SRLW
            if (op.rd != 0u) { registers.x[op.rd] = sext_32_to_64(bitcast<i32>(rs1_val.x >> (rs2_val.x & 0x1Fu))); }
        }
        case 53u: { // SRAW
            if (op.rd != 0u) { registers.x[op.rd] = sext_32_to_64(bitcast<i32>(rs1_val.x) >> (rs2_val.x & 0x1Fu)); }
        }

        // --- I-type W (0x1B) ---
        case 54u: { // ADDIW
            if (op.rd != 0u) { registers.x[op.rd] = sext_32_to_64(bitcast<i32>(rs1_val.x + op.imm)); }
        }
        case 55u: { // SLLIW
            if (op.rd != 0u) { registers.x[op.rd] = sext_32_to_64(bitcast<i32>(rs1_val.x << (op.imm & 0x1Fu))); }
        }
        case 56u: { // SRLIW
            if (op.rd != 0u) { registers.x[op.rd] = sext_32_to_64(bitcast<i32>(rs1_val.x >> (op.imm & 0x1Fu))); }
        }
        case 57u: { // SRAIW
            if (op.rd != 0u) { registers.x[op.rd] = sext_32_to_64(bitcast<i32>(rs1_val.x) >> (op.imm & 0x1Fu)); }
        }

        // --- A extension (0x2F): aux bit 0 = is_dword ---
        case 58u: { // LR.W / LR.D
            let is_dword = (op.aux & 1u) == 1u;
            let translated = translate_address(rs1_val, false, false);
            if (translated.y != 0u) {
                next_pc = raise_trap(13u, rs1_val, pc);
            } else if (translated.x < state.ram_base_low) {
                next_pc = raise_trap(5u, rs1_val, pc);
            } else {
                let phys = translated.x - state.ram_base_low;
                let d = phys / 4u;
                if (d >= arrayLength(&memory) || (is_dword && (d + 1u) >= arrayLength(&memory))) {
                    next_pc = raise_trap(5u, rs1_val, pc);
                } else {
                    let idx = d2idx(d);
                    let lo = memory[idx];
                    let hi = select(0u, memory[d2idx(d + 1u)], is_dword);
                    let val = select(sext_32_to_64(bitcast<i32>(lo)), vec2<u32>(lo, hi), is_dword);
                    if (op.rd != 0u) { registers.x[op.rd] = val; }
                    state.reservation_valid = 1u;
                    state.reservation_addr_low = translated.x;
                    state.reservation_addr_high = 0u;
                }
            }
        }
        case 59u: { // SC.W / SC.D
            let is_dword = (op.aux & 1u) == 1u;
            let translated = translate_address(rs1_val, true, false);
            if (translated.y != 0u) {
                next_pc = raise_trap(15u, rs1_val, pc);
            } else if (translated.x < state.ram_base_low) {
                next_pc = raise_trap(7u, rs1_val, pc);
            } else {
                let phys = translated.x - state.ram_base_low;
                let d = phys / 4u;
                if (d >= arrayLength(&memory) || (is_dword && (d + 1u) >= arrayLength(&memory))) {
                    next_pc = raise_trap(7u, rs1_val, pc);
                } else {
                    let idx = d2idx(d);
                    if (state.reservation_valid == 1u && state.reservation_addr_low == translated.x) {
                        memory[idx] = rs2_val.x;
                        if (is_dword) { memory[d2idx(d + 1u)] = rs2_val.y; }
                        if (op.rd != 0u) { registers.x[op.rd] = vec2<u32>(0u, 0u); } // success
                    } else if (op.rd != 0u) {
                        registers.x[op.rd] = vec2<u32>(1u, 0u); // failure
                    }
                    state.reservation_valid = 0u;
                }
            }
        }
        case 60u: { // AMOSWAP
            amo_common(op, rs1_val, rs2_val, pc, 0x01u, &next_pc);
        }
        case 61u: { // AMOADD
            amo_common(op, rs1_val, rs2_val, pc, 0x00u, &next_pc);
        }
        case 62u: { // AMOXOR
            amo_common(op, rs1_val, rs2_val, pc, 0x04u, &next_pc);
        }
        case 63u: { // AMOAND
            amo_common(op, rs1_val, rs2_val, pc, 0x0Cu, &next_pc);
        }
        case 64u: { // AMOOR
            amo_common(op, rs1_val, rs2_val, pc, 0x08u, &next_pc);
        }
        case 65u: { // AMOMIN
            amo_common(op, rs1_val, rs2_val, pc, 0x10u, &next_pc);
        }
        case 66u: { // AMOMAX
            amo_common(op, rs1_val, rs2_val, pc, 0x14u, &next_pc);
        }
        case 67u: { // AMOMINU
            amo_common(op, rs1_val, rs2_val, pc, 0x18u, &next_pc);
        }
        case 68u: { // AMOMAXU
            amo_common(op, rs1_val, rs2_val, pc, 0x1Cu, &next_pc);
        }

        // --- LUI / AUIPC / JAL / JALR / FENCE ---
        case 69u: { // LUI
            if (op.rd != 0u) { registers.x[op.rd] = sext_32_to_64(bitcast<i32>(op.imm)); }
        }
        case 70u: { // AUIPC
            if (op.rd != 0u) { registers.x[op.rd] = u64_add(pc, sext_32_to_64(bitcast<i32>(op.imm))); }
        }
        case 71u: { // JAL
            if (op.rd != 0u) { registers.x[op.rd] = next_pc; }
            next_pc = u64_add(pc, imm64);
        }
        case 72u: { // JALR
            var jump_addr = u64_add(rs1_val, imm64);
            jump_addr.x = jump_addr.x & 0xFFFFFFFEu;
            if (op.rd != 0u) { registers.x[op.rd] = next_pc; }
            next_pc = jump_addr;
            iso_on_ret(op.rd, pc);  // xv6-nano E-K1 KJMP boundary (switch_to's terminal ret)
        }
        case 73u: { // FENCE / FENCE.I — no-op
        }

        // --- SYSTEM (0x73) ---
        case 74u: { // ECALL (with native SBI dispatch, mirrors decode_and_execute)
            let sbi_ext = registers.x[17].x; // a7
            
            if (state.mode == 1u && sbi_ext == 0x01u) {
                uart_tx[state.uart_tx_len % 4096u] = registers.x[10].x & 0xFFu;
                state.uart_tx_len = state.uart_tx_len + 1u;
                registers.x[10] = vec2<u32>(0u, 0u);
                registers.x[11] = vec2<u32>(0u, 0u);
                state.sbi_ecall_console = state.sbi_ecall_console + 1u;
            } else if (state.mode == 1u && sbi_ext == 0x54494D45u) {
                // TIME extension "set timer": OpenSBI v1.7's Sstc-mode aclint driver arms
                // the S-mode compare (stimecmp) directly — mirror that. (The legacy
                // mtimecmp+MTIE path leaves the M-timer pending forever because OpenSBI's
                // Sstc-mode handler never clears the mtimecmp MMIO — observed M-mode storm.)
                csrs[CSR_STIMECMP] = vec2<u32>(registers.x[10].x, registers.x[10].y);
                csrs[CSR_MIP].x = csrs[CSR_MIP].x & ~0x20u;
                registers.x[10] = vec2<u32>(0u, 0u);
                registers.x[11] = vec2<u32>(0u, 0u);
                state.sbi_ecall_time = state.sbi_ecall_time + 1u;
            } else {
                state.sbi_ecall_unknown = state.sbi_ecall_unknown + 1u;
                var cause = 11u;
                if (state.mode == 0u) {
                    cause = 8u;
                } else if (state.mode == 1u) {
                    cause = 9u;
                }
                next_pc = raise_trap(cause, vec2<u32>(0u, 0u), pc);
            }
        }
        case 75u: { // EBREAK
            // xv6-nano E-K2: ebreak -> SUPER-mode syscall dispatcher when KSYS_PC is set
            if (!iso_syscall_trap(next_pc, &next_pc)) {
                next_pc = raise_trap(3u, vec2<u32>(0u, 0u), pc);
            }
        }
        case 76u: { // MRET
            // xv6-nano E-K2: mret closing a SYSCALL trap -> SYSRET
            if (!iso_sysret(&next_pc)) {
                next_pc = do_mret();
            }
        }
        case 77u: { // SRET
            next_pc = do_sret();
        }
        case 78u: { // WFI — no-op
        }
        case 79u: { // SFENCE.VMA — flush the TLB (the kernel publishes PTE updates with this)
            tlb_invalidate_all();
        }
        case 80u: { // CSRRW
            let csr_addr = op.aux;
            let old_val = csr_read(csr_addr);
            csr_write(csr_addr, rs1_val);
            if (op.rd != 0u) { registers.x[op.rd] = old_val; }
        }
        case 81u: { // CSRRS
            let csr_addr = op.aux;
            let old_val = csr_read(csr_addr);
            if (op.rs1 != 0u) {
                csr_write(csr_addr, vec2<u32>(old_val.x | rs1_val.x, old_val.y | rs1_val.y));
            }
            if (op.rd != 0u) { registers.x[op.rd] = old_val; }
        }
        case 82u: { // CSRRC
            let csr_addr = op.aux;
            let old_val = csr_read(csr_addr);
            if (op.rs1 != 0u) {
                csr_write(csr_addr, vec2<u32>(old_val.x & ~rs1_val.x, old_val.y & ~rs1_val.y));
            }
            if (op.rd != 0u) { registers.x[op.rd] = old_val; }
        }
        case 83u: { // CSRRWI — rs1 field carries the 5-bit uimm
            let csr_addr = op.aux;
            let old_val = csr_read(csr_addr);
            csr_write(csr_addr, vec2<u32>(op.rs1, 0u));
            if (op.rd != 0u) { registers.x[op.rd] = old_val; }
        }
        case 84u: { // CSRRSI
            let csr_addr = op.aux;
            let old_val = csr_read(csr_addr);
            if (op.rs1 != 0u) {
                csr_write(csr_addr, vec2<u32>(old_val.x | op.rs1, old_val.y));
            }
            if (op.rd != 0u) { registers.x[op.rd] = old_val; }
        }
        case 85u: { // CSRRCI
            let csr_addr = op.aux;
            let old_val = csr_read(csr_addr);
            if (op.rs1 != 0u) {
                csr_write(csr_addr, vec2<u32>(old_val.x & ~op.rs1, old_val.y));
            }
            if (op.rd != 0u) { registers.x[op.rd] = old_val; }
        }
        default: {
            // Should never happen: the host only pre-decodes valid ops. If it does,
            // take the illegal-instruction path so behavior matches decode_and_execute.
            let trap_pc = raise_trap(2u, vec2<u32>(0u, 0u), pc);
            state.pc_low = trap_pc.x;
            state.pc_high = trap_pc.y;
            state.trap_pending = 1u;
            return;
        }
    }

    state.pc_low = next_pc.x;
    state.pc_high = next_pc.y;
}

// Shared AMO execute path: mirrors decode_and_execute's A-extension AMO block.
// amo_op is baked in by the op enum; this helper carries the memory + write logic.
fn amo_common(op: DecodedOp, rs1_val: vec2<u32>, rs2_val: vec2<u32>, pc: vec2<u32>, amo_op: u32, next_pc: ptr<function, vec2<u32>>) {
    let is_dword = (op.aux & 1u) == 1u;
    let translated = translate_address(rs1_val, true, false);
    if (translated.y != 0u) {
        *next_pc = raise_trap(15u, rs1_val, pc);
        return;
    }
    if (translated.x < state.ram_base_low) {
        *next_pc = raise_trap(7u, rs1_val, pc);
        return;
    }
    let phys = translated.x - state.ram_base_low;
    let d = phys / 4u;
    if (d >= arrayLength(&memory) || (is_dword && (d + 1u) >= arrayLength(&memory))) {
        *next_pc = raise_trap(7u, rs1_val, pc);
        return;
    }
    let idx = d2idx(d);
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
    }
    memory[idx] = new_val.x;
    if (is_dword) { memory[d2idx(d + 1u)] = new_val.y; }
    if (op.rd != 0u) { registers.x[op.rd] = old; }
    state.reservation_valid = 0u; // any regular AMO invalidates a pending reservation
}

@compute @workgroup_size(1, 1, 1)
fn main(@builtin(global_invocation_id) global_id: vec3<u32>) {
    var steps = state.steps_remaining;
    
    // We add a safety cap of 65535 instructions per dispatch to avoid GPU timeouts
    if (steps > 16777216u) {
        steps = 16777216u;
    }
    
    // Basic-block threading state: cur_slot is the decoded_ops slot (phys/2) of the
    // instruction most recently executed on the fast path. When threading is active
    // (=1), each loop iteration advances cur_slot by instr_len/2 (fallthrough) and
    // executes the pre-decoded op directly — no fetch(), no I-TLB translate, no
    // maybe_take_interrupt(), no raw validation. A block ends (threading -> 0) at any
    // control-flow op, trap, halt, non-pre-decoded slot, or 4KB-page crossing (where
    // the next physical address is not guaranteed contiguous without a translate).
    // This is the real-emulator version of the toy proof in tools/basic_block_rv64i.wgsl:
    // it removes the per-instruction fetch/translate/lookup overhead for the ~88% of
    // instructions that fall through within a basic block (measured: avg block 8.5
    // instructions on the Alpine boot; 0% runtime-decode fallback).
    // Cross-dispatch basic-block cache: cur_slot and threading persist across
    // dispatches in state.bb_cur_slot and state.bb_active.
    var cur_slot = state.bb_cur_slot;
    var threading = state.bb_active;

    // bb counters accumulate in locals and flush ONCE at dispatch end: the host
    // only reads them after step() returns, so per-step storage writes to the
    // same state-buffer cache line only serialize the loop (measured cost of the
    // full per-step counter write set is significant at ~1.8M steps/s).
    var bb_total = state.bb_total_insts;
    var bb_ctl = state.bb_ctl_insts;
    var bb_threaded = state.bb_threaded_insts;
    var bb_fallback = state.bb_fallback_insts;

    var i = 0u;
    while (i < steps) {
        if (state.halted != 0u) {
            break;
        }

        // This is a functional (not cycle-accurate) simulator: real hardware retires far
        // more instructions per mtimer tick than we want to spend emulating, so a
        // microsecond-scale boot-time delay/calibration loop (udelay etc.) keyed off mtime
        // would otherwise cost tens to hundreds of millions of emulated instructions before
        // OpenSBI reaches its first UART write. Advance mtime by a small scale factor per
        // instruction instead of 1:1 so such waits resolve in a realistic instruction budget.
        //
        // The scale factor must stay SMALL, though: the guest kernel arms a 1ms tick
        // (HZ=1000 -> 10000 mtime ticks at the 10MHz timebase), and the interrupt path
        // (M-mode OpenSBI handler + S-mode tick processing) is ~600 emulated instructions
        // per delivery. A large factor (previously 1024) made the tick fire every ~10
        // instructions, saturating the CPU at ~98% interrupt duty — kernel_init never got
        // scheduled and the boot hung right after "Mountpoint-cache hash table entries".
        // With scale 1 the tick fires every 10000 instructions (~6% duty), matching the
        // real-hardware ratio, and 1ms delays cost only 10000 instructions.
        //
        // A perfectly CONSTANT 1-tick-per-instruction clock makes the guest's
        // jitterentropy RNG spin forever (its SP 800-90B health tests reject
        // perfectly uniform timing deltas). An earlier PC-derived variation attempt
        // caused a HARD boot stall at vgaarb because it drifted the long-run mtime
        // rate away from 1:1, breaking a kernel timing assumption elsewhere.
        //
        // This version dithers instead of drifting: a small LCG picks a per-step
        // delta of 0, 1, or 2 (mean 1.0), with cumulative drift hard-capped at
        // +/-8 ticks so mtime's rate stays effectively 1:1 over any run length —
        // only the LOCAL, instruction-to-instruction variance changes, which is
        // exactly what jitterentropy's health tests check, and exactly what the
        // vgaarb-sensitive code (driven by the long-run rate, not per-tick deltas)
        // should not notice.
        // Jitter disabled 2026-09-02: the LCG state is var<private>, so it RESETS
        // to the same seed on every dispatch — mtime after N steps depended on the
        // host's dispatch chunking, not just N. That made lockstep runs diverge on
        // interrupt timing purely due to chunk size (reproduced deterministically:
        // same-step divergence at 50k chunks, zero divergence replaying the same
        // window as one call), and can stall timer-dependent guest polls. Constant
        // 1:1 mtime is chunk-independent and matches the long-run rate exactly.
        // mtime advances AT RETIREMENT (see advance_mtime() below), NOT at loop
        // top: the threaded path's fallback `continue`s (stale op, trap-pending)
       // leave without incrementing i, so a top-of-loop advance double-charged
        // mtime for one instruction — fast core ran ~1.85x time rate, skewing
        // rdtime-driven guest RNG and timer-armed polls vs the slow path.

        if (threading != 0u) {
            // ---- Threaded fallthrough execution: no fetch, no translate, no interrupt ----
            cur_slot = cur_slot + (state.instr_len >> 1u);
            let tdop = decoded_ops[cur_slot];
            // Epoch check: stale entries fall back to full fetch path.
            let t_epoch_valid = (tdop.epoch == decoded_ops_epoch);
            // RAW validation: the threaded path executes decoded ops WITHOUT the
            // fetch-path's implicit freshness (fetch reads live memory every
            // instruction). Self-modifying code (kernel alternatives patching)
            // rewrites instructions AFTER the host decoded them — GPU stores never
            // update the host shadow, so a slot can hold a stale op whose .raw no
            // longer matches memory. Caught live: slot held op=JAL +128 (raw
            // 0x0800006f) while memory held NOP (0x00000013) at pc
            // 0xffffffff800769ec — fast core jumped, slow core fell through.
            // Compare the stored raw against live memory; mismatch -> fall back.
            // (Same 4KB-page guarantee as the page-straddle check: t_page_safe
            // below prevents a len==4 instruction from crossing pages, and blocks
            // end at page boundaries, so phys+2 is always in-RAM when len==4.)
            var t_raw_ok = true;
            let t_phys = cur_slot * 2u;
            let t_h0 = phys_read_u16(t_phys);
            if (t_h0.y == 0u || t_h0.x != (tdop.raw & 0xFFFFu)) {
                t_raw_ok = false;
            } else if (tdop.len == 4u) {
                let t_h1 = phys_read_u16(t_phys + 2u);
                if (t_h1.y == 0u || t_h1.x != ((tdop.raw >> 16) & 0xFFFFu)) {
                    t_raw_ok = false;
                }
            }
            if (tdop.op == 0xFFFFFFFFu || tdop.len == 0u || !t_epoch_valid || !t_raw_ok) {
                // Not pre-decoded, stale, or memory no longer matches — fall back
                // to the full fetch path for this address.
                threading = 0u;
                continue;
            }
            // Interrupt ordering parity with the fetch path: the slow path calls
            // maybe_take_interrupt() BEFORE executing each instruction. The threaded
            // path historically checked only after execution, delivering pending
            // interrupts one instruction late — enough to change which instruction
            // a timer trap lands on (and, with a spinlock held, to walk into
            // single-hart self-deadlock the slow path avoids).
            maybe_take_interrupt();
            if (state.halted != 0u) { break; }
            if (state.trap_pending != 0u) {
                threading = 0u;
                continue;
            }
            // Capture pc BEFORE executing: the fallthrough check below needs the
            // just-executed instruction's own pc and length to verify the op really
            // advanced pc by len (load/store page faults and other traps redirect pc
            // via raise_trap WITHOUT setting trap_pending, so this pc compare is the
            // authoritative "did control flow stay linear" test).
            let t_pc = vec2<u32>(state.pc_low, state.pc_high);
            let t_len = tdop.len;
            // execute_decoded() advances pc by state.instr_len; fetch() normally sets it,
            // but we bypassed fetch, so set it to this op's length first.
            state.instr_len = t_len;
            { let _mp = state.mtime_low; state.mtime_low = state.mtime_low + 1u; if (state.mtime_low < _mp) { state.mtime_high = state.mtime_high + 1u; } }
            execute_decoded(tdop);
            
            // Post-execute: do NOT deliver interrupts here. maybe_take_interrupt()
            // is a delivery point — calling it after execute_decoded gave the
            // threaded path a second delivery opportunity per instruction that
            // the fetch path does not have (fast core took timer ticks one
            // execute-step early; pinned at step 10,631,150, pc
            // 0xffffffff800769ec, RCU stall check). But we must still REFRESH the
            // level-sensitive timer bits in mip so a tick that arrived mid-block
            // is observed and breaks threading — otherwise the block runs to its
            // end with a pending, undelivered tick (RCU-stall hazard). This
            // recompute mirrors the mip update in maybe_take_interrupt() without
            // delivering; delivery happens at the next iteration's pre-execute
            // call (line ~3041), exactly like the fetch path.
            let t_mtip = state.mtimecmp_low != 0u && state.mtime_low >= state.mtimecmp_low;
            let t_stip_injected = (csrs[CSR_MIP].x & 0x20u) != 0u;
            let t_stip = t_stip_injected
                || (csrs[CSR_STIMECMP].x != 0u && state.mtime_low >= csrs[CSR_STIMECMP].x);
            csrs[CSR_MIP].x = (csrs[CSR_MIP].x & ~0xA0u)
                | select(0u, 0x80u, t_mtip)
                | select(0u, 0x20u, t_stip);
            // Use SIP/SIE for S-mode, MIP/MIE for M-mode
            let sip = vec2<u32>(csrs[CSR_MIP].x & csrs[CSR_MIDELEG].x, csrs[CSR_MIP].y & csrs[CSR_MIDELEG].y);
            let sie = vec2<u32>(csrs[CSR_MIE].x & csrs[CSR_MIDELEG].x, csrs[CSR_MIE].y & csrs[CSR_MIDELEG].y);
            let pending_interrupts = (state.mode == 3u && ((csrs[CSR_MIP].x & csrs[CSR_MIE].x) != 0u))
                || (state.mode == 1u && ((sip.x & sie.x) != 0u));
            if (pending_interrupts) {
                // Interrupt pending - break out of threading to handle it
                threading = 0u;
            }
            
            bb_total = bb_total + 1u;
            bb_threaded = bb_threaded + 1u;
            // Same CTL set as the fast path (branches 9-14, JAL 71, JALR 72,
            // ECALL/EBREAK/MRET/SRET/WFI 74-78, SFENCE.VMA 79).
            let t_is_ctl = (tdop.op >= 9u && tdop.op <= 14u) || tdop.op == 71u || tdop.op == 72u
                || (tdop.op >= 74u && tdop.op <= 79u);
            if (t_is_ctl) {
                bb_ctl = bb_ctl + 1u;
            }
            // CSR writes (ops 80-85) also end the block: writing satp can change the
            // virtual->physical mapping underneath us, and any CSR write can change
            // privilege/interrupt state that the next instruction depends on. The full
            // fetch path re-translates and re-checks interrupts after the block.
            // STORES also end the block (ops 22-25 = SB/SH/SW/SD): GPU-side stores
            // never update the host's _linear_shadow, so the host can't see kernel
            // self-modifying code (alternatives patching) and may leave stale
            // decoded_ops whose .raw no longer matches memory. The threaded loop
            // performs no raw validation, so it would execute pre-patch ops.
            // Ending the block after every store forces a full fetch (with
            // raw_matches validation) before any potentially patched instruction.
            let t_stores = (tdop.op >= 22u) && (tdop.op <= 25u);
            let t_stops = t_is_ctl || t_stores || tdop.op >= 80u;
            // Fallthrough test: new pc must equal old pc + len (64-bit). Any trap or
            // taken-branch redirect leaves pc elsewhere — stop threading.
            let t_fb_low = t_pc.x + t_len;
            let t_fb_carry = select(0u, 1u, t_fb_low < t_pc.x);
            let t_redirected = (state.pc_low != t_fb_low) || (state.pc_high != (t_pc.y + t_fb_carry));
            // Page test: the NEXT instruction must start and end in the same 4KB virtual page.
            // If the next instruction starts at >= 0xFFEu, a 4-byte instruction straddles
            // across two physical pages that may not be contiguous. Fall back to fetch.
            let t_next_off = (t_pc.x & 0xFFFu) + t_len;
            let t_page_safe = t_next_off < 0xFFEu;
            if (t_stops || t_redirected || !t_page_safe
                || state.trap_pending != 0u || state.halted != 0u) {
                threading = 0u;
            }
            i = i + 1u;
            continue;
        }

        maybe_take_interrupt();
        if (state.halted != 0u) {
            break;
        }
        if (state.trap_pending != 0u) {
            state.trap_pending = 0u;
            i = i + 1u;
            continue;
        }

        let fr = fetch();
        if (state.halted != 0u) {
            break;
        }
        if (state.trap_pending != 0u) {
            state.trap_pending = 0u;
            i = i + 1u;
            continue;
        }

        let instr = fr.instr;
        // Pre-decoded-op fast path: look up the op table (indexed by phys/2),
        // validate the bytes still match (self-modifying code), and execute
        // the pre-decoded op. Anything not pre-decoded falls back to runtime decode.
        let slot = fr.phys >> 1u;
        let dop = decoded_ops[slot];
        // select(false_value, true_value, cond): cond=true (4-byte) compares the full
        // expanded word; cond=false (2-byte RVC) compares the raw halfword.
        let raw_matches = select(
            dop.raw == fr.half0,                 // 2-byte RVC: raw is the halfword
            dop.raw == instr,                    // 4-byte: raw is the full expanded word
            dop.len == 4u
        );
        // Epoch check: if the entry was decoded before a sfence.vma/satp write,
        // it may be stale (GPU-side stores like execve's kernel copy don't update
        // decoded_ops). Mismatch triggers runtime fallback.
        let epoch_valid = (dop.epoch == decoded_ops_epoch);
        let DECODED_FASTPATH_DISABLED: bool = false;
        let is_straddle = ((fr.phys & 0xFFFu) == 0xFFEu) && (state.instr_len == 4u);
        if (!DECODED_FASTPATH_DISABLED && !is_straddle && dop.op != 0xFFFFFFFFu && dop.len == state.instr_len && raw_matches && epoch_valid) {
            // Capture pc, pc offset, and length BEFORE executing: the threading entry
            // check needs the just-executed instruction's own pc and length to decide
            // whether control flow stayed linear AND the next address is safely
            // predictable (same 4KB page). The pc compare is the authoritative test:
            // load/store page faults redirect pc via raise_trap WITHOUT setting
            // trap_pending, so is_ctl alone would miss them.
            let entry_pc = vec2<u32>(state.pc_low, state.pc_high);
            let entry_pc_off = state.pc_low & 0xFFFu;
            let entry_len = state.instr_len;
            { let _mp = state.mtime_low; state.mtime_low = state.mtime_low + 1u; if (state.mtime_low < _mp) { state.mtime_high = state.mtime_high + 1u; } }
            execute_decoded(dop);
            cur_slot = slot;
            bb_total = bb_total + 1u;
            // Basic-block measurement: a control-flow op ends the block. Mirrors the
            // CTL_OPS set in tools/bb_length_static.py (branches 9-14, JAL 71, JALR 72,
            // ECALL/EBREAK/MRET/SRET/WFI 74-78, SFENCE.VMA 79).
            let is_ctl = (dop.op >= 9u && dop.op <= 14u) || dop.op == 71u || dop.op == 72u
                || (dop.op >= 74u && dop.op <= 79u);
            if (is_ctl) {
                bb_ctl = bb_ctl + 1u;
            }
            // Fallthrough test (same as the threaded loop): new pc must equal old pc +
            // len (64-bit). Any trap or taken-branch redirect leaves pc elsewhere.
            let fb_low = entry_pc.x + entry_len;
            let fb_carry = select(0u, 1u, fb_low < entry_pc.x);
            let redirected = (state.pc_low != fb_low) || (state.pc_high != (entry_pc.y + fb_carry));
            // Enter threading iff: control flow stayed linear, no trap/halt, the op is
            // not a store or CSR write (stores can self-modify code; CSR writes change
            // state), and the NEXT instruction starts safely before the page boundary
            // (< 0xFFEu, so a 4-byte instruction will not straddle pages).
            let is_store = (dop.op >= 22u && dop.op <= 25u);
            if (state.bb_threading_enabled != 0u && !is_ctl && !is_store && dop.op < 80u && !redirected
                && state.trap_pending == 0u && state.halted == 0u
                && (entry_pc_off + entry_len) < 0xFFEu) {
                threading = 1u;
            }
        } else {
            { let _mp = state.mtime_low; state.mtime_low = state.mtime_low + 1u; if (state.mtime_low < _mp) { state.mtime_high = state.mtime_high + 1u; } }
            decode_and_execute(instr);
            cur_slot = 0u;
            threading = 0u;
            bb_total = bb_total + 1u;
            bb_fallback = bb_fallback + 1u;
        }
        i = i + 1u;
    }
    
    // Flush bb counters once per dispatch (host reads them via get_state() after
    // step() returns; per-step writes are pure overhead).
    state.bb_total_insts = bb_total;
    state.bb_ctl_insts = bb_ctl;
    state.bb_threaded_insts = bb_threaded;
    state.bb_fallback_insts = bb_fallback;
    state.bb_cur_slot = cur_slot;
    state.bb_active = threading;

    state.steps_remaining = state.steps_remaining - i;
}
