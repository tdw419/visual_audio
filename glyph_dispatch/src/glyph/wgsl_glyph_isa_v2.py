"""
WGSL GPU-native port of glyph_isa_v2.py's Spatial ISA v1.0.

Unlike tools/wgsl_spatial_glyph_engine.py and tools/wgsl_spatial_glyph_working.py
(an older, incompatible ad-hoc instruction encoding), this shader faithfully
implements glyph_isa_v2's actual fixed-width format:

    Every instruction is a 1x4 horizontal pixel block:
        Pixel 0 (Opcode):    RGB identifying the opcode (see OpcodeMapV2)
        Pixel 1 (Registers): R=rs1, G=rs2, B=rd  (0xFF = UNUSED_REGISTER)
        Pixel 2 (Imm-Low):   lower 24 bits of immediate/coordinate
        Pixel 3 (Imm-High):  upper 24 bits (only low 8 bits used here -
                              WGSL registers are u32, unlike Python's
                              unbounded ints, so the immediate is carried
                              as a single u32 rather than the full 48-bit
                              range _pack_immediate supports. No opcode in
                              the current ISA needs more than 32 bits.)

    LD/ST/PUSH/POP/CALL/RET read and write the SAME image buffer that
    holds the program - this is self-modifying-code-capable memory, not
    a separate scratch region, exactly matching GlyphCPUv2._mem_read/write.

Opcode colors are pulled from OpcodeMapV2 at generation time (see
generate_wgsl_opcode_table() below) rather than hand-copied, so this file
never silently drifts from whatever tools/glyph_isa_v2.py currently
resolves - regenerate the constant block if wordbase.db content changes
the original 10 opcodes' colors.
"""

import numpy as np

from tools.glyph_isa_v2 import OpcodeMapV2, INSTR_WIDTH, UNUSED_REGISTER

_OPCODE_ORDER = [
    'HALT', 'LDI', 'ADD', 'SUB', 'MUL', 'CMP', 'JMP', 'JZ', 'PRT', 'LD', 'ST',
    'AND', 'OR', 'XOR', 'SHL', 'SHR', 'PUSH', 'POP', 'CALL', 'RET', 'SYSCALL',
    'JMPR', 'CALLR', 'KJMP', 'SYSRET', 'ROTR', 'JNZ', 'JNE',
    'CMP3', 'JLT', 'JGT'   # SE025
]


def generate_wgsl_opcode_table(opcode_map: OpcodeMapV2):
    """Emit the WGSL const block + get_opcode_from_color() check lines for
    every opcode currently in OpcodeMapV2, so the shader always matches
    the live map rather than a hand-copied snapshot."""
    consts = []
    checks = []
    for i, op in enumerate(_OPCODE_ORDER):
        consts.append("const OPCODE_%s: u32 = %du;" % (op, i))
        r, g, b = opcode_map.opcode_to_rgb(op)
        checks.append(
            "    if (r == %du && g == %du && b == %du) { return OPCODE_%s; }" % (r, g, b, op)
        )
    return "\n".join(consts), "\n".join(checks)


_SHADER_TEMPLATE = """
struct Pixel {
    r: u32,
    g: u32,
    b: u32,
    a: u32,
}

struct SpatialCPU {
    pc: vec2<u32>,             // 2D program counter (x always a multiple of 4)
    registers: array<u32, 32>, // r0-r31; r31 doubles as the stack pointer
    running: u32,
    output_ptr: u32,
    mode: u32,                 // GH-13 privilege: 0 = SUPER, 1 = USER (KJMP latch)
    // BK-2: E-K2 SYSCALL/SYSRET register-file snapshot. GlyphCPUv2 keeps
    // this as a CPU-object field (self._syscall_regs); WGSL's per-lane
    // struct has no equivalent scratch space, so it's added here instead
    // of borrowing box_mmio words (which would claim MMIO address space
    // with no corresponding CPU-side contract). has_saved_regs mirrors
    // Python's `is not None` check (only restore if a trap actually
    // saved something -- a bare SYSRET with no prior SYSCALL is a no-op
    // on the register file, matching the CPU).
    saved_registers: array<u32, 32>,
    has_saved_regs: u32,
    // DEFECT-18 (R1.4): GH-16 tick snapshot -- the pre-tick USER register
    // file and interrupted pixel PC; JMPR restores them on handler return
    // (mirrors GlyphCPUv2's _tick_regs/_tick_pc Python-side fields).
    tick_regs: array<u32, 32>,
    has_tick_regs: u32,
    tick_pc: vec2<u32>,
    // BK-76-twin (RULING_BK76_EXEMPTION_POSTURE.md, Option A): one-way
    // ever-user latch -- set when an instruction starts USER on a
    // tile-armed lane. Mirrors GlyphCPUv2._bk76_ever_user
    // (glyph_isa_v2.py:630/:837-844); gates the ST-arm SUPER
    // MMIO-window exemption refusal so boot-phase vector config
    // (pre-first-USER) stays lawful.
    bk76_ever_user: u32,
}

struct Uniforms {
    image_width: u32,
    image_height: u32,
    output_buffer_size: u32,
}

// image is BOTH the program ROM and read/write scratch memory (LD/ST/
// PUSH/POP/CALL/RET all operate on it) - matching GlyphCPUv2 exactly.
@group(0) @binding(0) var<storage, read_write> image: array<Pixel>;
@group(0) @binding(1) var<storage, read_write> cpus: array<SpatialCPU>;
@group(0) @binding(2) var<storage, read_write> output: array<u32>;
@group(0) @binding(3) var<uniform> uniforms: Uniforms;
@group(0) @binding(4) var<storage, read_write> box_mmio: array<u32, 160>;
// backlog(d)/DEFECT-D (2026-09-16): the WGSL twin's RAM analogue. Per the
// scoping receipt (systems/SCOPING_MEMORY_VIEW_UNIFICATION.md #7), the
// twin previously had NO RAM array at all - only box_mmio (which mirrors
// just the reserved MMIO block, GlyphCPUv2.memory[8192+i]). This is a
// SEPARATE, general-purpose buffer for the (d)-migrated syscalls' data/
// dest args (glyph_isa_v2.py's self.memory for everything else). See
// ram_read/ram_write below for the delegate-to-box_mmio-when-in-range
// rule that keeps the two buffers from silently diverging on overlap.
@group(0) @binding(5) var<storage, read_write> ram: array<u32, 16384>;

__OPCODE_CONSTS__
const UNUSED_REGISTER: u32 = 255u;
const INSTR_WIDTH: u32 = 4u;

fn get_opcode_from_color(r: u32, g: u32, b: u32) -> u32 {
__OPCODE_CHECKS__
    return 1000u; // Unknown opcode
}

fn load_pixel(x: u32, y: u32) -> vec3<u32> {
    let index = y * uniforms.image_width + x;
    let p = image[index];
    return vec3<u32>(p.r, p.g, p.b);
}

fn store_pixel(x: u32, y: u32, val: vec3<u32>) {
    let index = y * uniforms.image_width + x;
    image[index].r = val.x;
    image[index].g = val.y;
    image[index].b = val.z;
}

// Linear-wrap scalar address -> pixel coordinate (scanline order),
// matching GlyphCPUv2._addr_to_xy.
fn addr_to_xy(addr: u32) -> vec2<u32> {
    let total = uniforms.image_width * uniforms.image_height;
    let wrapped = addr % total;
    return vec2<u32>(wrapped % uniforms.image_width, wrapped / uniforms.image_width);
}

fn mem_read(addr: u32) -> u32 {
    let xy = addr_to_xy(addr);
    let p = load_pixel(xy.x, xy.y);
    return (p.x << 16u) | (p.y << 8u) | p.z;
}

fn mem_write(addr: u32, value: u32) {
    let xy = addr_to_xy(addr);
    let v = value & 0xFFFFFFu;
    store_pixel(xy.x, xy.y, vec3<u32>((v >> 16u) & 0xFFu, (v >> 8u) & 0xFFu, v & 0xFFu));
}

// --- GH-17/GH-25 spatial page walker (WGSL twin) -----------------------------
// Constants mirror tools/glyph_isa_v2.py (word units; word = addr >> 2).
const BOX_MMIO_WORD_LO: u32 = 8192u;          // BOX_MMIO_BASE >> 2
// SE022a/2.2a: widened 64 -> 160 words to cover the INPUT_* ring (offsets
// 92-159 below: LEN/CURSOR at 92/93, DATA at 96 running one byte per word
// for INPUT_DATA_CAP=64 words -> last slot 159) that glyph_isa_v2.py's
// SYSCALL_READ (0x02) drains. The Python side has no hard span cap on
// this block (plain self.memory words); this constant only gates the
// WGSL page-walker's SUPER-mode bypass check, so widening it is additive
// and doesn't change any existing box_mmio consumer's behavior. (128 was
// tried first and silently truncated the top of the ring - caught before
// shipping by re-deriving the offsets from BOX_MMIO_BASE arithmetic.)
const BOX_MMIO_SPAN: u32 = 160u;              // the reserved MMIO block, 160 words
const PAGE_TABLE_WORD: u32 = 8211u;           // PAGE_TABLE_ADDR >> 2
const PAGE_TABLE_TAG: u32 = 0x505447u;         // ASCII "PTG" (DEFECT-23-ROOT Option 1 container tag)
const PAGE_WORDS: u32 = 256u;                 // words per page
const PTE_V: u32 = 1u;
const PTE_W: u32 = 2u;
const PTE_U: u32 = 4u;
const PTE_PIX: u32 = 8u;
const PTE_HILB: u32 = 16u;
const HILB_SIDE: u32 = 64u;                   // 64x64 Hilbert frame grid
const MODE_LATCH_WORD: u32 = 8192u;           // BOX_MMIO_BASE + 0x00, >> 2
const MODE_USER: u32 = 1u;
// BK-2: E-K2 SYSCALL/SYSRET trap words (word units, mirror glyph_isa_v2.py's
// KSYS_PC_ADDR/SYSCALL_PC_ADDR/SYS_N_ADDR/SYS_A0_ADDR/SYS_A1_ADDR, all
// BOX_MMIO_BASE-relative and inside BOX_MMIO_SPAN).
const KSYS_PC_WORD: u32 = 8194u;              // BOX_MMIO_BASE + 0x08, >> 2
const SYSCALL_PC_WORD: u32 = 8201u;           // BOX_MMIO_BASE + 0x24, >> 2
const SYS_N_WORD: u32 = 8204u;                // BOX_MMIO_BASE + 0x30, >> 2
const SYS_A0_WORD: u32 = 8205u;               // BOX_MMIO_BASE + 0x34, >> 2
const SYS_A1_WORD: u32 = 8206u;               // BOX_MMIO_BASE + 0x38, >> 2
// SE022a/2.2a: input ring words, mirror glyph_isa_v2.py's
// INPUT_LEN_ADDR/INPUT_CURSOR_ADDR/INPUT_DATA_ADDR (BOX_MMIO_BASE + 0x170/
// 0x174/0x180 = words 8284/8285/8288, >> 2). One byte per word, same as the
// Python ring; DATA capacity 64 bytes = INPUT_DATA_CAP (slots 96..159 in
// box_mmio, i.e. words 8288..8351).
const INPUT_LEN_WORD: u32 = 8284u;            // BOX_MMIO_BASE + 0x170, >> 2
const INPUT_CURSOR_WORD: u32 = 8285u;         // BOX_MMIO_BASE + 0x174, >> 2
const INPUT_DATA_WORD: u32 = 8288u;           // BOX_MMIO_BASE + 0x180, >> 2
const INPUT_DATA_CAP: u32 = 64u;              // = glyph_isa_v2.INPUT_DATA_CAP
const RAM_WORDS: u32 = 16384u;                // ram buffer size (binding 5)
// GH-16 preemptive-scheduling timer words (R1.4 convergence: mirror
// glyph_isa_v2.py's KTICK_PC_ADDR/TIMER_COUNT_ADDR/TIMER_RELOAD_ADDR/
// TICK_PC_ADDR, BOX_MMIO_BASE + 0x3C/0x40/0x44/0x48, >> 2).
const KTICK_PC_WORD: u32 = 8207u;
const TIMER_COUNT_WORD: u32 = 8208u;
const TIMER_RELOAD_WORD: u32 = 8209u;
const TICK_PC_WORD: u32 = 8210u;
// E-K1 box-range words (R1.4: the USER-store confinement the oracle
// checks at glyph_isa_v2.py:1050 via _addr_in_box). Words 8195..8203 =
// BOX0_LO/HI, BOX1_LO/HI, BOX2_LO/HI (BOX_MMIO_BASE + 0x0C/0x10/0x14/
// 0x18/0x28/0x2C, >> 2). The 2D tile predicate (TILE_H/W/ROW/COL) is
// not mirrored: no fleet/kernel image arms a tile, and an unset tile is
// inert on the oracle anyway.
const BOX0_LO_WORD: u32 = 8195u;
const BOX0_HI_WORD: u32 = 8196u;
const BOX1_LO_WORD: u32 = 8197u;
const BOX1_HI_WORD: u32 = 8198u;
const BOX2_LO_WORD: u32 = 8202u;
const BOX2_HI_WORD: u32 = 8203u;
// BK-51: GO-2 2D tile predicate words (BOX_MMIO_BASE + 0x160/0x164/0x168/
// 0x16C, >> 2 = 8280/8281/8282/8283): kernel-armed tile origin (row, col)
// and extent (h, w) in grid coordinates. TILE_H == 0 -> tile unset / inert.
// Previously "not mirrored" (no fleet/kernel image arms a tile); BK-51's
// measured D3 divergence (tile-armed USER in-tile store DENIED on the twin
// while the oracle lands it) makes the predicate load-bearing for the
// spawn(tile=...) containment posture.
const TILE_ROW_WORD: u32 = 8280u;
const TILE_COL_WORD: u32 = 8281u;
const TILE_H_WORD: u32 = 8282u;
const TILE_W_WORD: u32 = 8283u;
// Memory grid width in WORDS (glyph_isa_v2.py W_MEM = 32; 128 bytes / row).
// The tile predicate derives (row, col) from the BYTE address exactly as
// the oracle does: word = byte_addr >> 2, row = word / W_MEM, col % W_MEM.
const W_MEM: u32 = 32u;
// E-K1 fault-record words (BOX_MMIO_BASE + 0x1C/0x20, >> 2): the engine
// writes the faulting byte address / offending store's packed pixel PC
// before vectoring KFAULT_PC (glyph_isa_v2.py FAULT_ADDR_ADDR/FAULT_PC_ADDR).
const FAULT_ADDR_WORD: u32 = 8199u;
const FAULT_PC_WORD: u32 = 8200u;
const KFAULT_PC_WORD: u32 = 8193u; // BOX_MMIO_BASE + 0x04, >> 2 (E-K1 vector)

// BK-50-twin: the BK-41 locked CONFIG set, kernel-write-only at the twin's
// walk_st door (oracle precedent: _BK41_LOCKED_WORDS, glyph_isa_v2.py:854,
// landed 65c1c46b; measured scope amendment EXCLUDES MODE_LATCH 8192 and the
// TILE words 8280..8283 -- the xv6-nano S6/S11 schedulers lawfully re-arm
// them post-USER every context switch, so locking them would be a lawful
// write caught in the net). SYS_A0/A1 (8205/8206) + the INPUT ring stay
// guest-writable per BK-76 §0's boundary.
var<private> BK50_LOCKED_WORDS: array<u32, 11> = array<u32, 11>(
    8193u, 8194u,               // KFAULT_PC, KSYS_PC
    8195u, 8196u, 8197u, 8198u, // BOX0_LO/HI, BOX1_LO/HI
    8202u, 8203u,               // BOX2_LO/HI
    8207u, 8208u, 8209u         // KTICK_PC, TIMER_COUNT, TIMER_RELOAD
);

// backlog(d)/DEFECT-D: ram_read/ram_write are the twin's mirror of
// GlyphCPUv2.self.memory[addr] for the (d)-migrated syscalls. self.memory
// is ONE flat array on the Python side, of which the box_mmio-mirrored
// [8192, 8192+160) range is just a sub-range; ram_read/ram_write preserve
// that by delegating to box_mmio when addr falls in that range (so an
// address that happens to land in the reserved block behaves identically
// through either path) and to the new `ram` buffer otherwise. Out-of-range
// addr reads 0 / drops the write, matching glyph_isa_v2.py's own
// no-crash-on-out-of-range-addr convention (SYSCALL_READ's growth guard,
// this rung's 0x01 fix).
fn ram_read(addr: u32) -> u32 {
    if (addr >= BOX_MMIO_WORD_LO && addr < BOX_MMIO_WORD_LO + BOX_MMIO_SPAN) {
        return box_mmio[addr - BOX_MMIO_WORD_LO];
    }
    if (addr < RAM_WORDS) { return ram[addr]; }
    return 0u;
}

fn ram_write(addr: u32, value: u32) {
    if (addr >= BOX_MMIO_WORD_LO && addr < BOX_MMIO_WORD_LO + BOX_MMIO_SPAN) {
        box_mmio[addr - BOX_MMIO_WORD_LO] = value;
        return;
    }
    if (addr < RAM_WORDS) { ram[addr] = value; }
}

// box_mmio[i] mirrors GlyphCPUv2.memory[8192 + i] for the reserved block.
// Bound as a STORAGE buffer (binding 4) so the armed page-table base and the
// mode latch persist across dispatches (declared above, with the bindings).

// Hilbert d2xy: frame slot d -> (col, row) on the HILB_SIDE grid. LUT-free
// bitwise twin of tools.geos_hilbert.hilbert_d2xy_true (Hacker's Delight) —
// leg 4 of the gate proves the emitted table agrees with the host curve.
fn hilb_d2xy(d: u32) -> vec2<u32> {
    var rx: u32;
    var ry: u32;
    var x: u32 = 0u;
    var y: u32 = 0u;
    var t: u32 = d;
    var s: u32 = 1u;
    loop {
        if (s >= HILB_SIDE) { break; }
        rx = 1u & (t / 2u);
        ry = 1u & (t ^ rx);
        // rot(s, x, y, rx, ry): rotate the quadrant
        if (ry == 0u) {
            if (rx == 1u) {
                x = s - 1u - x;
                y = s - 1u - y;
            }
            let tmp: u32 = x;
            x = y;
            y = tmp;
        }
        x = x + s * rx;
        y = y + s * ry;
        t = t / 4u;
        s = s * 2u;
    }
    return vec2<u32>(x, y);
}

// GH-25 translation: PTE with PTE_HILB -> frame pixel word. The PTE's pfn
// field is the PACKED 2D frame origin (row << 8 | col); the frame word is
// xy2d(col, row) * PAGE_WORDS + offset. Bitwise mirror of
// GlyphCPUv2._hilb_frame_pix_word (intra-frame offset stays LINEAR).
fn hilb_xy2d(x_in: u32, y_in: u32) -> u32 {
    var d: u32 = 0u;
    var x: u32 = x_in;
    var y: u32 = y_in;
    var s: u32 = HILB_SIDE >> 1u;
    loop {
        if (s == 0u) { break; }
        let rx: u32 = select(0u, 1u, (x & s) != 0u);
        let ry: u32 = select(0u, 1u, (y & s) != 0u);
        d = d + s * s * ((3u * rx) ^ ry);
        if (ry == 0u) {
            if (rx == 1u) {
                x = HILB_SIDE - 1u - x;
                y = HILB_SIDE - 1u - y;
            }
            let tmp: u32 = x;
            x = y;
            y = tmp;
        }
        s = s >> 1u;
    }
    return d;
}

fn hilb_frame_word(pfn_field: u32, offset: u32) -> u32 {
    let col: u32 = pfn_field & 0xFFu;
    let row: u32 = (pfn_field >> 8u) & 0xFFu;
    return hilb_xy2d(col, row) * PAGE_WORDS + offset;
}

// The walker: armed when box_mmio PAGE_TABLE_WORD slot != 0 and the address
// is NOT a SUPER-mode box-MMIO access (the box block bypasses paging, exactly
// like GlyphCPUv2). PTE fetch is image pixels (the WGSL engine has no RAM;
// box_mmio never covers the PT window). The CPU twin is RAM-FIRST with this
// image read as fallback when the RAM PTE is 0 — for the GH-25 harness (PTE
// stamped in the image, RAM zero) both engines take the image PTE; for
// GH-17..23 kernels (RAM PTEs) the CPU never reaches the fallback, matching
// the landed behavior (RCA systems/GH25_WIP_PTE_FETCH_RCA.md).
// A fault jumps to KFAULT_PC (box_mmio slot 15) or halts, mirroring the CPU.
//
// R1.4 CONVERGENCE FIX (2026-09-21, probe_r13_wgsl_fleet halt@153):
// the unpaged word-memory fallback below used to route EVERY address to
// image pixels (mem_read/mem_write), while GlyphCPUv2's unpaged ST/LD
// operate on RAM words (self.memory[addr], glyph_isa_v2.py:938/:1070)
// with an image-wrap READ fallback only when addr is out of RAM
// (glyph_isa_v2.py:944, ENG-3/BK-6). On the R1.2 fleet image (no page
// table armed -- agent_resident.py gates PT setup to mode="paged") the
// kernel's receipt store 0x020026 to word 952 landed on scanline pixel
// (24,29) -- the ST instruction's own opcode pixel -- so the shader
// decoded its own program as data, hit the unknown-opcode halt, and the
// fleet died at step 153 with all result words 0 while the CPU oracle
// ran to 434. walk_ld/walk_st now mirror the oracle: RAM first
// (ram_read/ram_write, which keep the box_mmio sub-range alias), then
// the CPU's documented image-wrap fallback on LD. The OOB ST delta is
// honest: the CPU faults there (lever #2), but fault vectoring is
// CPU-only in this shader (see the unmapped-store note below), so the
// OOB store stays dropped -- the pre-existing convention for the one
// path this engine cannot vector.
// The paged PTE fetch gets the same treatment: the CPU is RAM-first
// with an image-PTE fallback when the RAM PTE is 0 (RCA
// systems/GH25_WIP_PTE_FETCH_RCA.md); the twin now reads the RAM PTE
// and only falls back to the image PTE when it is zero, instead of
// always reading image pixels.
fn walk_ld(addr: u32, is_super: bool) -> u32 {
    let pt_base = box_mmio[PAGE_TABLE_WORD - BOX_MMIO_WORD_LO];
    if (pt_base == 0u || (is_super && addr >= BOX_MMIO_WORD_LO && addr < BOX_MMIO_WORD_LO + BOX_MMIO_SPAN)) {
        // BK-2 fix: this branch was asymmetric with walk_st's equivalent
        // (which DOES special-case the MMIO range here -- see below) --
        // it fell straight to mem_read(addr) unconditionally, so a plain
        // `LD` of an MMIO word (e.g. the kernel's own SYS_N read after
        // an E-K2 trap) silently read stale/baked PIXEL data instead of
        // the box_mmio buffer the trap actually wrote to. box_mmio is
        // the WGSL engine's ONLY persistent store for the reserved block
        // (it has no RAM the way GlyphCPUv2 does); every read of an
        // in-range word must come from there, matching walk_st's writes.
        if (addr >= BOX_MMIO_WORD_LO && addr < BOX_MMIO_WORD_LO + BOX_MMIO_SPAN) {
            if (!is_super) { return 0u; }
            return box_mmio[addr - BOX_MMIO_WORD_LO];
        }
        // R1.4: oracle semantics -- RAM word, then the CPU's ENG-3
        // image-wrap fallback for out-of-RAM addresses.
        if (addr < RAM_WORDS) { return ram[addr]; }
        return mem_read(addr);
    }
    // R1.4: tag check is RAM-first with image fallback -- bitwise twin of
    // check_pt_tag (glyph_isa_v2.py:88-95); reading image-only broke parity
    // once kernel stores land in RAM (walk_st below).
    var tag: u32 = 0u;
    if ((pt_base - 1u) < RAM_WORDS) { tag = ram[pt_base - 1u]; }
    if (tag == 0u) { tag = mem_read(pt_base - 1u); }
    if (tag != PAGE_TABLE_TAG) {
        return 4294967295u; // caller-visible fault marker; never taken in gates
    }
    let vpn = (addr >> 8u) & 0xFFu;
    let offset = addr & 0xFFu;
    let pte_idx = pt_base + vpn;
    // R1.4: RAM-first PTE fetch, image fallback when the RAM PTE is 0
    // (bitwise mirror of GlyphCPUv2's GH-25 dual fetch).
    var pte: u32 = 0u;
    if (pte_idx < RAM_WORDS) { pte = ram[pte_idx]; }
    if (pte == 0u) { pte = mem_read(pte_idx); }
    if ((pte & PTE_V) == 0u) {
        return 4294967295u; // caller-visible fault marker; never taken in gates
    }
    // BK-64: bitwise mirror of the oracle's LD flag check
    // (glyph_isa_v2.py:873) -- U required in USER, SUPER exempt. A
    // U-clear paged load from USER is refused with the same
    // caller-visible fault marker as the V-clear case above.
    if (!is_super && (pte & PTE_U) == 0u) {
        return 4294967295u;
    }
    let pfn = pte >> 8u;
    // BK-66-twin: post-translation paddr consult on ALL THREE frame arms
    // (bitwise mirror of the oracle's :952-990 LD consult sites — HILB/
    // PIX/plain each consult AFTER pfn decode, never the vaddr; ruling
    // 9714a363 clause 1). On refusal: record FAULT_ADDR = paddr<<2 +
    // FAULT_PC (the caller supplies PC), raise the pending flag, and
    // return the sentinel — the caller runs the E-K1 tail instead of
    // writing rd. A single decoded-word consult covers all three arms
    // because the frame word IS the translated address in every arm.
    var decoded_word: u32;
    if ((pte & PTE_HILB) != 0u) {
        decoded_word = hilb_frame_word(pfn, offset);
    } else if ((pte & PTE_PIX) != 0u) {
        decoded_word = pfn * PAGE_WORDS + offset;
    } else {
        decoded_word = pfn * PAGE_WORDS + offset;
    }
    if (paged_paddr_out_of_tile(decoded_word, is_super)) {
        box_mmio[FAULT_ADDR_WORD - BOX_MMIO_WORD_LO] = decoded_word << 2u;
        bk66_paddr_fault_pending = 1u;
        return 4294967295u;
    }
    if ((pte & PTE_HILB) != 0u) {
        return mem_read(decoded_word);
    }
    if ((pte & PTE_PIX) != 0u) {
        return mem_read(decoded_word);
    }
    // R1.4: plain (RAM-backed) frames live in RAM -- twin of
    // glyph_isa_v2.py:920-922 (LD) with the ENG-3 wrap for OOR.
    if (decoded_word < RAM_WORDS) { return ram[decoded_word]; }
    return mem_read(decoded_word);
}

// BK-48: the read-side twin fence (RULING_BK38_READ_POSTURE Option 2,
// clause 3) -- bitwise mirror of GlyphCPUv2's LD tile-confinement branch
// (glyph_isa_v2.py:995-1004). A tile-armed USER LD whose target falls
// outside the armed GO-2 tile must TRAP E-K1, not return the word. The
// twin's equivalent of _tile_confinement is TILE_H != 0: unset tile
// (TILE_H == 0) is inert -- byte-identical legacy reads for the
// cooperative single-address-space model (xv6-nano), where USER LD stays
// unfenced BY DESIGN (ruling clause 1). Grid math identical to
// addr_in_box's BK-51 tile branch: word = addr >> 2, row = word / W_MEM,
// col = word % W_MEM. Returns true when the load was rejected (the
// caller must then run the E-K1 sequence, mirroring the oracle).
fn ld_tile_fault(addr: u32, is_super: bool) -> bool {
    if (is_super) { return false; }
    // Branch-structure parity with the oracle (:883-885 vs :995): the
    // :995 tile-confinement elif only runs for UNPAGED loads -- a paged
    // USER LD takes the :885 branch, whose fence is BK-66's POST-
    // TRANSLATION _physical_in_tile consult on the decoded paddr (a
    // vaddr-side check there would be defeated by the attacker-owned
    // page table, BK-66 T1/T2). The twin's paged-path read fence is the
    // open BK-66-twin line item; until it lands this consult must NOT
    // fire on paged loads (it would over-confine: refuse a lawful
    // out-of-tile-vaddr/in-tile-paddr load the oracle admits -- the
    // BK-51 D3 shape on the read side).
    let pt_base = box_mmio[PAGE_TABLE_WORD - BOX_MMIO_WORD_LO];
    if (pt_base != 0u) { return false; }
    let tile_h = box_mmio[TILE_H_WORD - BOX_MMIO_WORD_LO];
    if (tile_h == 0u) { return false; }
    let tile_w = box_mmio[TILE_W_WORD - BOX_MMIO_WORD_LO];
    let trow = box_mmio[TILE_ROW_WORD - BOX_MMIO_WORD_LO];
    let tcol = box_mmio[TILE_COL_WORD - BOX_MMIO_WORD_LO];
    let word = addr;
    let row = word / W_MEM;
    let col = word % W_MEM;
    if (trow <= row && row < trow + tile_h && tcol <= col && col < tcol + tile_w) {
        return false;
    }
    return true;
}

// BK-66-twin: the paged arms' POST-TRANSLATION paddr consult — bitwise
// mirror of GlyphCPUv2._physical_in_tile (glyph_isa_v2.py:751-768, DESIGN
// RULING 9714a363 clause 1/5: "twin side takes the same paddr posture").
// The GO-2 tile predicate applied to the TRANSLATED physical word address,
// NEVER the vaddr (attacker owns the page table: a vaddr-side check is
// defeated by construction — the oracle's T1/T2 measured exactly that).
// The twin's equivalent of _tile_confinement is TILE_H != 0 (the BK-48/
// BK-51 inert-at-zero convention: unset tile == unfenced legacy paging).
// Grid math identical to addr_in_box's tile branch: row = word / W_MEM,
// col = word % W_MEM. Returns TRUE when the paddr is out-of-tile and the
// access must be refused (USER only — SUPER exempt, mode gate at :959/:1114).
fn paged_paddr_out_of_tile(paddr_word: u32, is_super: bool) -> bool {
    if (is_super) { return false; }
    let tile_h = box_mmio[TILE_H_WORD - BOX_MMIO_WORD_LO];
    if (tile_h == 0u) { return false; }
    let tile_w = box_mmio[TILE_W_WORD - BOX_MMIO_WORD_LO];
    let trow = box_mmio[TILE_ROW_WORD - BOX_MMIO_WORD_LO];
    let tcol = box_mmio[TILE_COL_WORD - BOX_MMIO_WORD_LO];
    let row = paddr_word / W_MEM;
    let col = paddr_word % W_MEM;
    return !(trow <= row && row < trow + tile_h && tcol <= col && col < tcol + tile_w);
}

// BK-66-twin wiring: the walker owns the decoded paddr; the caller owns the
// E-K1 sequence (mode + KFAULT_PC vector need `cpu`). The walker records the
// fault words itself (FAULT_ADDR = the PADDR the fence judged, bitwise
// twin of the oracle's _paged_paddr_fence_fault :777-791 — the fault carries the
// PHYSICAL byte address, never the vaddr), then sets this flag so the caller
// runs the E-K1 tail with the paddr-based FAULT_ADDR it just wrote instead
// of its vaddr-based default. Single-lane dispatch (workgroup_size(1), one
// step per dispatch) makes the module-private handshake race-free.
var<private> bk66_paddr_fault_pending: u32 = 0u;

// Returns true when the store was rejected as an E-K1 out-of-box USER
// store (the caller must then vector KFAULT_PC, mirroring the oracle).
fn walk_st(addr: u32, value: u32, is_super: bool) -> bool {
    let pt_base = box_mmio[PAGE_TABLE_WORD - BOX_MMIO_WORD_LO];
    if (pt_base != 0u && !(is_super && addr >= BOX_MMIO_WORD_LO && addr < BOX_MMIO_WORD_LO + BOX_MMIO_SPAN)) {
        // R1.4: same RAM-first tag check as walk_ld above (check_pt_tag twin).
        var tag: u32 = 0u;
        if ((pt_base - 1u) < RAM_WORDS) { tag = ram[pt_base - 1u]; }
        if (tag == 0u) { tag = mem_read(pt_base - 1u); }
        if (tag != PAGE_TABLE_TAG) {
            return false; // unmapped store / tag mismatch: dropped
        }
        let vpn = (addr >> 8u) & 0xFFu;
        let offset = addr & 0xFFu;
        // R1.4: RAM-first PTE fetch, image fallback when the RAM PTE is
        // 0 -- the ST twin of the walk_ld fetch above.
        var pte: u32 = 0u;
        if ((pt_base + vpn) < RAM_WORDS) { pte = ram[pt_base + vpn]; }
        if (pte == 0u) { pte = mem_read(pt_base + vpn); }
        if ((pte & PTE_V) == 0u || !(is_super || (pte & PTE_U) != 0u) || (pte & PTE_W) == 0u) {
            // BK-64: bitwise mirror of the oracle's ST flag check
            // (glyph_isa_v2.py:1001) -- V required; U required in USER
            // (SUPER exempt); W required with NO mode exemption. A
            // flag-cleared paged store is refused AND runs the same
            // E-K1 path as an out-of-box USER store (fault recorded,
            // mode -> SUPER, KFAULT_PC vector).
            return true;
        }
        let pfn = pte >> 8u;
        // BK-66-twin: post-translation paddr consult (bitwise mirror of the
        // oracle's :1114-1146 ST consult sites — HILB/PIX/plain, AFTER pfn
        // decode, never the vaddr; ruling 9714a363 clause 1). On refusal:
        // record FAULT_ADDR = paddr<<2 (the PHYSICAL byte address the fence
        // judged — oracle :777), raise the pending flag, return true — the
        // caller runs the E-K1 tail but must NOT overwrite FAULT_ADDR with
        // the vaddr (the pending-flag check at the ST dispatch site).
        var decoded_word: u32;
        if ((pte & PTE_HILB) != 0u) {
            decoded_word = hilb_frame_word(pfn, offset);
        } else if ((pte & PTE_PIX) != 0u) {
            decoded_word = pfn * PAGE_WORDS + offset;
        } else {
            decoded_word = pfn * PAGE_WORDS + offset;
        }
        if (paged_paddr_out_of_tile(decoded_word, is_super)) {
            box_mmio[FAULT_ADDR_WORD - BOX_MMIO_WORD_LO] = decoded_word << 2u;
            bk66_paddr_fault_pending = 1u;
            return true;
        }
        if ((pte & PTE_HILB) != 0u) {
            mem_write(decoded_word, value);
            return false;
        }
        if ((pte & PTE_PIX) != 0u) {
            mem_write(decoded_word, value);
            return false;
        }
        // R1.4: plain (RAM-backed) frames write RAM -- twin of
        // glyph_isa_v2.py:1048-1049 (ST into self.memory).
        if (decoded_word < RAM_WORDS) { ram[decoded_word] = value; }
        else { mem_write(decoded_word, value); }
        return false;
    }
    if (addr >= BOX_MMIO_WORD_LO && addr < BOX_MMIO_WORD_LO + BOX_MMIO_SPAN) {
        box_mmio[addr - BOX_MMIO_WORD_LO] = value;
    } else if (addr < RAM_WORDS) {
        // E-K1 (R1.4): an out-of-box USER store does not land AND faults.
        // Bitwise twin of glyph_isa_v2.py:1050-1065: the oracle records
        // FAULT_ADDR/FAULT_PC, drops to SUPER, and vectors to the kernel
        // fault handler at KFAULT_PC (the reaper); returning true makes
        // the caller run exactly that sequence.
        if (is_super || addr_in_box(addr << 2u)) {
            ram[addr] = value;
            return false;
        }
        return true;
    }
    return false;
}

// BK-49: the stack-path fence. PUSH/POP/CALL/RET/CALLR touch memory
// through the IMAGE plane (mem_write/mem_read) — the sequenced fence
// commit's fourth consult surface (measured, probe_wgsl_stack_fence_af3e.md:
// out-of-box PUSH landed + POP read, USER-clean, zero consults). This
// consult runs PER-OP at the dispatch arm on the exact stack word the
// operation touches — the landing posture decided at the landing gate
// (row option 1), NOT a consult inside mem_write/mem_read: a shared-site
// consult would double-fence the paged frame arms (BK-66-twin's
// post-translation paddr consult already owns the paged path) and would
// change every non-stack caller's semantics. The judged term is the SAME
// addr_in_box (boxes + GO-2 tile) walk_st consults; SUPER is exempt, so
// kernel KJMP/entry stacks are untouched, and a USER task's lawful stack
// lives inside its kernel-programmed box (BOX2, the stack-page class) or
// its armed tile. The caller owns the E-K1 tail (FAULT_PC, mode->SUPER,
// KFAULT_PC vector, kf==0 stop loudly — the BK-52 guard shape) so each
// arm decides its own pre-op ordering (PUSH/CALL: consult BEFORE the
// pre-decrement so a refused op mutates nothing; POP/RET: BEFORE the read
// and the post-increment).
fn stack_fence_fault(sp_word: u32, is_super: bool) -> bool {
    if (is_super) { return false; }
    return !addr_in_box(sp_word << 2u);
}

// BK-50-twin: the BK-41 CONFIG-block lock at the twin's walk_st door.
// The landed BK-76-twin refusal covers the three VECTOR words only; the
// measured BK-50 door (probe_wgsl_mmio_door_af3e, results md5
// f9349631f7610092ef583759d81cf319 re-measured this session) is the rest
// of the config block: a seeded-USER ST to BOX0_HI (8196) lands clean and
// a pure-USER disarm chain rewrites its own confinement through this
// legitimate branch, where the oracle traps the same program (E-K1).
// Bitwise oracle parity with glyph_isa_v2.py's _BK41_LOCKED_WORDS lock
// (:1333-1338 scalar ST arm, :1862-1868 PARALLEL_ST arm): the BK-76
// ever_user latch + FENCE-ARMED scope (tile OR box; BK-77), same word set
// (MODE_LATCH 8192 and TILE 8280..8283 EXCLUDED by the measured scope
// amendment). Refusal semantics = the landed BK-76-twin Option A shape:
// store dropped, FAULT_ADDR = word<<2, FAULT_PC packed, mode -> SUPER,
// stop, NO vector (tick-19 KFAULT restart-loop immunity). Returns true
// when the store must be refused (caller runs the tail above).
fn bk50_config_write_refused(cpu: ptr<function, SpatialCPU>, addr: u32) -> bool {
    if (cpu.bk76_ever_user != 1u) { return false; }
    // BK-77: scope is ANY armed fence -- the box-only posture (TILE_H==0,
    // box HI confirmed) is a real containment posture (the oracle's E-K1
    // USER arm, glyph_isa_v2.py:1481, needs no _tile_confinement), and
    // the TILE_H-only gate left the door open there (measured: the BK-55
    // twin chain escaped end-to-end; RESEARCH_bk55_boxonly_door_af3e.md).
    if (box_mmio[TILE_H_WORD - BOX_MMIO_WORD_LO] == 0u
            && !box_confirmed()) { return false; }
    if (addr < BOX_MMIO_WORD_LO
            || addr >= BOX_MMIO_WORD_LO + BOX_MMIO_SPAN) { return false; }
    for (var i = 0u; i < 11u; i = i + 1u) {
        if (BK50_LOCKED_WORDS[i] == addr) { return true; }
    }
    return false;
}

// BK-56: the CONFIG-block READ posture (DIRECTIVE_BK56_MMIO_READ_POSTURE.md,
// seat-lane provisional 2026-10-01, Option A decided). User-mode reads of the
// BK-41 locked CONFIG words refuse at the LD arm: the load delivers NO value
// (rd unwritten), FAULT_ADDR = word<<2, FAULT_PC packed, mode -> SUPER, stop,
// NO vector (BK-75 KFC-L6 — a read-refusal vector would itself leak the fault
// PC). Scope = the SAME 11-word set as BK-50/77's write lock (MODE_LATCH 8192
// and TILE 8280..8283 stay OUT by the measured scope amendment). SUPER reads
// stay green (kernel/tick/syscall dispatch are the lawful readers — the
// posture is mode-scoped, not a blanket block). Non-config window words
// (SYS_A0/A1 8205/8206, INPUT ring, MODE_LATCH, TILE) keep the landed
// silent-0 walk_ld USER semantics — not refused, BK-76 §0 boundary intact.
// Today's pre-fix shape (measured, probe_bk56_read_refuse_af3e results md5
// b9848e6f4202004521598c092b513c6f): the whole window returns 0 SILENTLY to
// USER (69a53298 posture) — a config read is indistinguishable from an
// unset word. This consult makes the config set LOUD.
fn bk56_config_read_refused(addr: u32, is_super: bool) -> bool {
    if (is_super) { return false; }
    if (addr < BOX_MMIO_WORD_LO
            || addr >= BOX_MMIO_WORD_LO + BOX_MMIO_SPAN) { return false; }
    for (var i = 0u; i < 11u; i = i + 1u) {
        if (BK50_LOCKED_WORDS[i] == addr) { return true; }
    }
    return false;
}

// BK-77: TRUE when any box range is CONFIRMED (HI != 0). Twin of the
// oracle's unset-range-never-matches rule (addr_in_box, :744-747): an
// armed box is a containment posture in its own right. (Plain body --
// WGSL has no variadic module-scope binding; box_mmio is module state.)
fn box_confirmed() -> bool {
    return box_mmio[BOX0_HI_WORD - BOX_MMIO_WORD_LO] != 0u
        || box_mmio[BOX1_HI_WORD - BOX_MMIO_WORD_LO] != 0u
        || box_mmio[BOX2_HI_WORD - BOX_MMIO_WORD_LO] != 0u;
}

// E-K1: is byte_addr inside a kernel-programmed box range, or inside the
// GO-2 2D tile when one is armed? Bitwise twin of GlyphCPUv2._addr_in_box
// (glyph_isa_v2.py:720-748) INCLUDING the tile branch (:734-747). An unset
// range (HI == 0) never matches; an unset tile (TILE_H == 0) is inert.
fn addr_in_box(byte_addr: u32) -> bool {
    let lo0 = box_mmio[BOX0_LO_WORD - BOX_MMIO_WORD_LO];
    let hi0 = box_mmio[BOX0_HI_WORD - BOX_MMIO_WORD_LO];
    let lo1 = box_mmio[BOX1_LO_WORD - BOX_MMIO_WORD_LO];
    let hi1 = box_mmio[BOX1_HI_WORD - BOX_MMIO_WORD_LO];
    let lo2 = box_mmio[BOX2_LO_WORD - BOX_MMIO_WORD_LO];
    let hi2 = box_mmio[BOX2_HI_WORD - BOX_MMIO_WORD_LO];
    if ((hi0 != 0u && lo0 <= byte_addr && byte_addr < hi0)
            || (hi1 != 0u && lo1 <= byte_addr && byte_addr < hi1)
            || (hi2 != 0u && lo2 <= byte_addr && byte_addr < hi2)) {
        return true;
    }
    // BK-51: the GO-2 2D tile predicate -- the twin previously omitted
    // this term entirely, so a tile-armed USER task was DENIED EVERY store
    // (in-tile included) where the oracle admits in-tile stores (measured
    // divergence: probe D3 in-tile ST faulted 640 on the twin, landed
    // clean on the oracle). Grid coordinates from the BYTE address,
    // identical math to the oracle: word = addr >> 2, row = word / W_MEM,
    // col = word % W_MEM.
    let tile_h = box_mmio[TILE_H_WORD - BOX_MMIO_WORD_LO];
    if (tile_h != 0u) {
        let tile_w = box_mmio[TILE_W_WORD - BOX_MMIO_WORD_LO];
        let trow = box_mmio[TILE_ROW_WORD - BOX_MMIO_WORD_LO];
        let tcol = box_mmio[TILE_COL_WORD - BOX_MMIO_WORD_LO];
        let word = byte_addr >> 2u;
        let row = word / W_MEM;
        let col = word % W_MEM;
        if (trow <= row && row < trow + tile_h && tcol <= col && col < tcol + tile_w) {
            return true;
        }
    }
    return false;
}

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
    // was_user: privilege at instruction START -- the oracle's tick
    // condition (glyph_isa_v2.py:1323) requires was_user AND still-USER
    // after dispatch, so a KJMP-into-USER (task entry) never counts as a
    // tickable USER instruction. Capturing it here keeps that exact rule.
    let was_user = (cpu.mode == MODE_USER);

    // BK-76-twin: the ever-user latch. Every measured :968-window attack
    // shape requires the engine to execute USER instructions after fence
    // arming (SYSCALL into SUPER, or a tick preemption). Boot/config-phase
    // vector writes all happen pre-first-USER, so latching here keeps them
    // lawful while post-USER vector stores become refuse-able. One-way;
    // the twin's _tile_confinement equivalent was TILE_H != 0 (BK-48/
    // BK-51) -- BK-77 widens it to ANY fence armed (tile OR box): the
    // box-only posture is a real containment posture and the TILE_H-only
    // latch never set there, leaving the BK-50 lock inert (measured,
    // RESEARCH_bk55_boxonly_door_af3e.md). Reset only by a fresh lane.
    if (was_user && (box_mmio[TILE_H_WORD - BOX_MMIO_WORD_LO] != 0u || box_confirmed())) {
        cpu.bk76_ever_user = 1u;
    }

    // BK-66-twin: clear the walker->caller paddr-fault handshake before
    // dispatch (single-lane single-step: no other writer exists).
    bk66_paddr_fault_pending = 0u;

    let x = cpu.pc.x;
    let y = cpu.pc.y;

    if (y >= uniforms.image_height || x >= uniforms.image_width) {
        cpu.running = 0u;
        cpus[cpu_id] = cpu;
        return;
    }

    let opcode_px = load_pixel(x, y);
    let reg_px = load_pixel(x + 1u, y);
    let low_px = load_pixel(x + 2u, y);
    let high_px = load_pixel(x + 3u, y);

    let opcode = get_opcode_from_color(opcode_px.x, opcode_px.y, opcode_px.z);

    let rs1 = reg_px.x;
    let rs2 = reg_px.y;
    let rd = reg_px.z;

    // Immediate: low 24 bits from low_px, next 8 bits from high_px's top
    // byte - a u32-sized subset of Python's full 48-bit pack (see module
    // docstring). Sufficient for every opcode in this ISA.
    let low24 = (low_px.x << 16u) | (low_px.y << 8u) | low_px.z;
    let imm = (high_px.z << 24u) | low24;

    var next_pc = vec2<u32>(x + INSTR_WIDTH, y);
    if (next_pc.x >= uniforms.image_width) {
        next_pc.x = 0u;
        next_pc.y = next_pc.y + 1u;
    }

    if (opcode == OPCODE_LDI) {
        cpu.registers[rd] = imm;
    } else if (opcode == OPCODE_ADD) {
        cpu.registers[rd] = cpu.registers[rd] + cpu.registers[rs2];
    } else if (opcode == OPCODE_SUB) {
        cpu.registers[rd] = cpu.registers[rd] - cpu.registers[rs2];
    } else if (opcode == OPCODE_MUL) {
        // SE023: 32-bit wrapped multiply, matching GlyphCPUv2 (u32 wrap).
        cpu.registers[rd] = cpu.registers[rd] * cpu.registers[rs2];
    } else if (opcode == OPCODE_AND) {
        cpu.registers[rd] = cpu.registers[rd] & cpu.registers[rs2];
    } else if (opcode == OPCODE_OR) {
        cpu.registers[rd] = cpu.registers[rd] | cpu.registers[rs2];
    } else if (opcode == OPCODE_XOR) {
        cpu.registers[rd] = cpu.registers[rd] ^ cpu.registers[rs2];
    } else if (opcode == OPCODE_SHL) {
        cpu.registers[rd] = cpu.registers[rd] << cpu.registers[rs2];
    } else if (opcode == OPCODE_SHR) {
        cpu.registers[rd] = cpu.registers[rd] >> cpu.registers[rs2];
    } else if (opcode == OPCODE_ROTR) {
        let n = cpu.registers[rs2] & 31u;
        let v = cpu.registers[rd];
        if (n == 0u) {
            cpu.registers[rd] = v;
        } else {
            cpu.registers[rd] = (v >> n) | (v << (32u - n));
        }
    } else if (opcode == OPCODE_CMP) {
        if (cpu.registers[rd] == cpu.registers[rs2]) {
            cpu.registers[0] = 1u;
        } else {
            cpu.registers[0] = 0u;
        }
    } else if (opcode == OPCODE_CMP3) {
        // SE025: tri-state compare, signed - bitwise twin of GlyphCPUv2's
        // CMP3 branch (glyph_isa_v2.py). r0 = 0 (lt) / 1 (eq) / 2 (gt);
        // i32 conversion is two's-complement, matching Python's signed view
        // of the 32-bit-wrapped registers exactly.
        let sa3 = i32(cpu.registers[rd] & 0xFFFFFFFFu);
        let sb3 = i32(cpu.registers[rs2] & 0xFFFFFFFFu);
        if (sa3 < sb3) {
            cpu.registers[0] = 0u;
        } else if (sa3 == sb3) {
            cpu.registers[0] = 1u;
        } else {
            cpu.registers[0] = 2u;
        }
    } else if (opcode == OPCODE_LD) {
        let addr = cpu.registers[rs2];
        // BK-56: the CONFIG-block READ posture (DIRECTIVE_BK56_MMIO_READ_
        // POSTURE.md, Option A decided). USER LD of a BK-41 locked config
        // word refuses BEFORE walk_ld: rd NOT written, FAULT_ADDR = word<<2,
        // FAULT_PC packed, mode -> SUPER, stop, NO vector (BK-75 KFC-L6 --
        // a read-refusal vector would itself leak the fault PC; research
        // finding 6: the read channel has no fault path to ride, this IS
        // the new consult). SUPER falls through untouched (L3 mode-scope).
        if (bk56_config_read_refused(addr, cpu.mode == 0u)) {
            box_mmio[FAULT_ADDR_WORD - BOX_MMIO_WORD_LO] = addr << 2u;
            box_mmio[FAULT_PC_WORD - BOX_MMIO_WORD_LO] =
                ((y & 0xFFFFu) << 16u) | ((x / INSTR_WIDTH) & 0xFFFFu);
            cpu.mode = 0u; // MODE_SUPER
            // NO vector by design (BK-75 KFC-L6): KFAULT_PC is never
            // consulted here -- stop immediately and loudly.
            cpu.running = 0u;
            cpus[cpu_id] = cpu;
            return;
        }
        // BK-48: read-side tile fence consult BEFORE the load (bitwise
        // twin of glyph_isa_v2.py:995 -- USER + tile armed + out-of-tile
        // target). On refusal the register is NOT written and the exact
        // E-K1 sequence the ST arm runs executes: record FAULT_ADDR (the
        // byte address the fence judged) + the offending load's packed
        // pixel PC, drop to SUPER, vector KFAULT_PC (kf==0 -> stop
        // loudly, never replay-and-land -- the BK-52 guard shape).
        if (ld_tile_fault(addr, cpu.mode == 0u)) {
            box_mmio[FAULT_ADDR_WORD - BOX_MMIO_WORD_LO] = addr << 2u;
            box_mmio[FAULT_PC_WORD - BOX_MMIO_WORD_LO] =
                ((y & 0xFFFFu) << 16u) | ((x / INSTR_WIDTH) & 0xFFFFu);
            cpu.mode = 0u; // MODE_SUPER
            let kf = box_mmio[KFAULT_PC_WORD - BOX_MMIO_WORD_LO];
            if (kf != 0u) {
                let tx = kf & 0xFFFFu;
                let ty = (kf >> 16u) & 0xFFFFu;
                next_pc = vec2<u32>(tx * INSTR_WIDTH, ty);
            } else {
                // Standalone / kernel mode: stop immediately and loudly,
                // matching the oracle's no-handler branch.
                cpu.running = 0u;
                cpus[cpu_id] = cpu;
                return;
            }
        } else {
            let ld_result = walk_ld(addr, cpu.mode == 0u);
            // BK-66-twin: a pending paddr fault means the walk REFUSED the
            // access post-translation — the sentinel is not data. Run the
            // E-K1 tail WITHOUT overwriting FAULT_ADDR (the walker already
            // wrote the PADDR byte the fence judged); rd stays unwritten.
            if (bk66_paddr_fault_pending == 0u) {
                cpu.registers[rd] = ld_result;
            } else {
                box_mmio[FAULT_PC_WORD - BOX_MMIO_WORD_LO] =
                    ((y & 0xFFFFu) << 16u) | ((x / INSTR_WIDTH) & 0xFFFFu);
                cpu.mode = 0u; // MODE_SUPER
                let kf = box_mmio[KFAULT_PC_WORD - BOX_MMIO_WORD_LO];
                if (kf != 0u) {
                    let tx = kf & 0xFFFFu;
                    let ty = (kf >> 16u) & 0xFFFFu;
                    next_pc = vec2<u32>(tx * INSTR_WIDTH, ty);
                } else {
                    cpu.running = 0u;
                    cpus[cpu_id] = cpu;
                    return;
                }
            }
        }
    } else if (opcode == OPCODE_ST) {
        // ST rs1 rs2 -> store rs2 into the pixel at address rs1 (rs1 is the
        // ADDRESS register here, matching GlyphCPUv2 and assembler).
        let addr = cpu.registers[rs1];
        // BK-76-twin clause-4 (RULING_BK76_EXEMPTION_POSTURE.md, Option A):
        // walk_st's SUPER MMIO-window exemption never consults the fence, so
        // a post-USER SUPER store to a DISPATCH VECTOR word lands
        // unconditionally (measured RED at landing: sentinel 65537 landed at
        // KSYS_PC/KTICK_PC). Scope: tile-armed lanes, after the lane has
        // executed USER instructions post-arm, window addresses, the THREE
        // vector words only (xv6-nano ISO_SYS_A0 8205, MODE_LATCH 8192,
        // ISO_INPUT_CURSOR 8237 stay lawful -- ruling invariant 2). Refuse:
        // store dropped, FAULT_ADDR/FAULT_PC recorded, mode -> SUPER
        // (post-mortem), lane stops with NO vector (tick-19 KFAULT restart
        // loop: 162 fires under fault-path refusal).
        if (cpu.bk76_ever_user == 1u && cpu.mode == 0u
                && box_mmio[TILE_H_WORD - BOX_MMIO_WORD_LO] != 0u
                && addr >= BOX_MMIO_WORD_LO
                && addr < BOX_MMIO_WORD_LO + BOX_MMIO_SPAN
                && (addr == KFAULT_PC_WORD || addr == KSYS_PC_WORD
                    || addr == KTICK_PC_WORD)) {
            box_mmio[FAULT_ADDR_WORD - BOX_MMIO_WORD_LO] = addr << 2u;
            box_mmio[FAULT_PC_WORD - BOX_MMIO_WORD_LO] =
                ((y & 0xFFFFu) << 16u) | ((x / INSTR_WIDTH) & 0xFFFFu);
            cpu.mode = 0u;   // MODE_SUPER, post-mortem posture
            cpu.running = 0u; // NO vector: restart-loop immunity
            cpus[cpu_id] = cpu;
            return;
        }
        // BK-50-twin: extend the same refusal from the three VECTOR words
        // to the full BK-41 locked CONFIG set (BOX ranges, timer words).
        // Scope (ever_user + tile-armed + window + locked set) lives in the
        // function; NO mode term here -- the measured BK-50 door is a
        // USER-mode store landing through walk_st's mode-blind MMIO branch
        // (the first draft gated on cpu.mode == 0u/SUPER and stayed RED:
        // the canary landed at BOX0_HI with the clause present, caught by
        // this gate's own L1). Oracle parity is BOTH post-USER arms: USER
        // at the E-K1 consult (:1041) and SUPER at the :968 exemption arm
        // (the BK-41 lock lives there too). The BK-76 clause above remains
        // first so the three vector words behave byte-identically (this
        // clause is strictly additive for the remaining locked words).
        if (bk50_config_write_refused(&cpu, addr)) {
            box_mmio[FAULT_ADDR_WORD - BOX_MMIO_WORD_LO] = addr << 2u;
            box_mmio[FAULT_PC_WORD - BOX_MMIO_WORD_LO] =
                ((y & 0xFFFFu) << 16u) | ((x / INSTR_WIDTH) & 0xFFFFu);
            cpu.mode = 0u;    // MODE_SUPER, post-mortem posture
            cpu.running = 0u; // NO vector: restart-loop immunity
            cpus[cpu_id] = cpu;
            return;
        }
        let e_k1_fault = walk_st(addr, cpu.registers[rs2], cpu.mode == 0u);
        if (e_k1_fault) {
            // E-K1 twin of glyph_isa_v2.py:1050-1065: record the faulting
            // byte address + offending store's packed pixel PC, drop to
            // SUPER, vector to the kernel's fault handler at KFAULT_PC.
            // Stepping continues -- the kernel reaps the offending proc.
            // BK-66-twin: when the walker's post-translation consult fired,
            // FAULT_ADDR already carries the PADDR byte (oracle :777 parity)
            // — do NOT overwrite it with the vaddr.
            if (bk66_paddr_fault_pending == 0u) {
                box_mmio[FAULT_ADDR_WORD - BOX_MMIO_WORD_LO] = addr << 2u;
            }
            box_mmio[FAULT_PC_WORD - BOX_MMIO_WORD_LO] =
                ((y & 0xFFFFu) << 16u) | ((x / INSTR_WIDTH) & 0xFFFFu);
            cpu.mode = 0u; // MODE_SUPER
            let kf = box_mmio[KFAULT_PC_WORD - BOX_MMIO_WORD_LO];
            if (kf != 0u) {
                let tx = kf & 0xFFFFu;
                let ty = (kf >> 16u) & 0xFFFFu;
                next_pc = vec2<u32>(tx * INSTR_WIDTH, ty);
            } else {
                // Standalone / kernel mode: stop immediately and loudly,
                // matching the oracle's no-handler branch.
                cpu.running = 0u;
                cpus[cpu_id] = cpu;
                return;
            }
        }
    } else if (opcode == OPCODE_JMPR) {
        // Jump to the packed pixel PC in rd (raw pixel units, no scaling).
        let packed = cpu.registers[rd];
        let tx = packed & 0xFFFFu;
        let ty = (packed >> 16u) & 0xFFFFu;
        next_pc = vec2<u32>(tx * INSTR_WIDTH, ty);
        // DEFECT-18 (R1.4): when returning from a tick handler to the
        // interrupted USER PC via JMPR, restore the pre-tick USER
        // register file, re-enter USER, and clear the snapshot --
        // bitwise twin of glyph_isa_v2.py's JMPR tick-restore branch.
        if (cpu.has_tick_regs == 1u && next_pc.x == cpu.tick_pc.x && next_pc.y == cpu.tick_pc.y) {
            cpu.registers = cpu.tick_regs;
            cpu.has_tick_regs = 0u;
            cpu.mode = MODE_USER;
        }
    } else if (opcode == OPCODE_KJMP) {
        // GH-13 privilege boundary: JMPR + mode latch one-shot (bitwise twin
        // of GlyphCPUv2's KJMP). The box-MMIO view is private per dispatch,
        // so the latch reads box_mmio[0]; the CPU zeroes its RAM copy after
        // the one-shot and the GPU copy starts at zero each run — same
        // visible behavior for both engines' kernels (arm -> KJMP).
        let packed = cpu.registers[rd];
        let tx = packed & 0xFFFFu;
        let ty = (packed >> 16u) & 0xFFFFu;
        next_pc = vec2<u32>(tx * INSTR_WIDTH, ty);
        if (box_mmio[0u] == MODE_USER) {
            cpu.mode = MODE_USER;
        } else {
            cpu.mode = 0u;
        }
        box_mmio[0u] = 0u;
    } else if (opcode == OPCODE_PUSH) {
        // BK-49: consult the fence on the LANDING word (r31-1) BEFORE the
        // pre-decrement — a refused PUSH mutates nothing (r31 stays, value
        // never lands) and runs the E-K1 sequence.
        if (stack_fence_fault(cpu.registers[31] - 1u, cpu.mode == 0u)) {
            box_mmio[FAULT_ADDR_WORD - BOX_MMIO_WORD_LO] =
                (cpu.registers[31] - 1u) << 2u;
            box_mmio[FAULT_PC_WORD - BOX_MMIO_WORD_LO] =
                ((y & 0xFFFFu) << 16u) | ((x / INSTR_WIDTH) & 0xFFFFu);
            cpu.mode = 0u; // MODE_SUPER
            let kf = box_mmio[KFAULT_PC_WORD - BOX_MMIO_WORD_LO];
            if (kf != 0u) {
                let tx = kf & 0xFFFFu;
                let ty = (kf >> 16u) & 0xFFFFu;
                next_pc = vec2<u32>(tx * INSTR_WIDTH, ty);
            } else {
                cpu.running = 0u;
                cpus[cpu_id] = cpu;
                return;
            }
        } else {
            cpu.registers[31] = cpu.registers[31] - 1u;
            mem_write(cpu.registers[31], cpu.registers[rd]);
        }
    } else if (opcode == OPCODE_POP) {
        // BK-49: consult on the word POP READS (r31) BEFORE the read and
        // the post-increment — a refused POP delivers nothing and leaves
        // the stack pointer alone.
        if (stack_fence_fault(cpu.registers[31], cpu.mode == 0u)) {
            box_mmio[FAULT_ADDR_WORD - BOX_MMIO_WORD_LO] =
                cpu.registers[31] << 2u;
            box_mmio[FAULT_PC_WORD - BOX_MMIO_WORD_LO] =
                ((y & 0xFFFFu) << 16u) | ((x / INSTR_WIDTH) & 0xFFFFu);
            cpu.mode = 0u; // MODE_SUPER
            let kf = box_mmio[KFAULT_PC_WORD - BOX_MMIO_WORD_LO];
            if (kf != 0u) {
                let tx = kf & 0xFFFFu;
                let ty = (kf >> 16u) & 0xFFFFu;
                next_pc = vec2<u32>(tx * INSTR_WIDTH, ty);
            } else {
                cpu.running = 0u;
                cpus[cpu_id] = cpu;
                return;
            }
        } else {
            cpu.registers[rd] = mem_read(cpu.registers[31]);
            cpu.registers[31] = cpu.registers[31] + 1u;
        }
    } else if (opcode == OPCODE_PRT) {
        let idx = cpu.output_ptr;
        if (idx < uniforms.output_buffer_size) {
            output[cpu_id * uniforms.output_buffer_size + idx] = cpu.registers[rd];
        }
        cpu.output_ptr = cpu.output_ptr + 1u;
    } else if (opcode == OPCODE_CALL) {
        // Push the (already pixel-unit) return address, then jump to the
        // instruction-index-encoded target (tx * INSTR_WIDTH), exactly
        // matching the asymmetry in GlyphCPUv2: the *saved* return PC is
        // stored in raw pixel units, but the jump *target* in imm is an
        // instruction index that must be scaled by INSTR_WIDTH.
        // BK-49: consult the fence on the LANDING word (r31-1) BEFORE the
        // pre-decrement and BEFORE the jump — a refused CALL mutates
        // nothing and the E-K1 vector owns next_pc.
        if (stack_fence_fault(cpu.registers[31] - 1u, cpu.mode == 0u)) {
            box_mmio[FAULT_ADDR_WORD - BOX_MMIO_WORD_LO] =
                (cpu.registers[31] - 1u) << 2u;
            box_mmio[FAULT_PC_WORD - BOX_MMIO_WORD_LO] =
                ((y & 0xFFFFu) << 16u) | ((x / INSTR_WIDTH) & 0xFFFFu);
            cpu.mode = 0u; // MODE_SUPER
            let kf = box_mmio[KFAULT_PC_WORD - BOX_MMIO_WORD_LO];
            if (kf != 0u) {
                let tx = kf & 0xFFFFu;
                let ty = (kf >> 16u) & 0xFFFFu;
                next_pc = vec2<u32>(tx * INSTR_WIDTH, ty);
            } else {
                cpu.running = 0u;
                cpus[cpu_id] = cpu;
                return;
            }
        } else {
            cpu.registers[31] = cpu.registers[31] - 1u;
            let packed_pc = (next_pc.y << 16u) | (next_pc.x & 0xFFFFu);
            mem_write(cpu.registers[31], packed_pc);

            let tx = imm & 0xFFFFu;
            let ty = (imm >> 16u) & 0xFFFFu;
            next_pc = vec2<u32>(tx * INSTR_WIDTH, ty);
        }
    } else if (opcode == OPCODE_RET) {
        // BK-49: consult on the word RET READS (r31) BEFORE the read and
        // the post-increment — a refused RET neither delivers the saved
        // PC nor moves the stack pointer, and the E-K1 vector owns next_pc.
        if (stack_fence_fault(cpu.registers[31], cpu.mode == 0u)) {
            box_mmio[FAULT_ADDR_WORD - BOX_MMIO_WORD_LO] =
                cpu.registers[31] << 2u;
            box_mmio[FAULT_PC_WORD - BOX_MMIO_WORD_LO] =
                ((y & 0xFFFFu) << 16u) | ((x / INSTR_WIDTH) & 0xFFFFu);
            cpu.mode = 0u; // MODE_SUPER
            let kf = box_mmio[KFAULT_PC_WORD - BOX_MMIO_WORD_LO];
            if (kf != 0u) {
                let tx = kf & 0xFFFFu;
                let ty = (kf >> 16u) & 0xFFFFu;
                next_pc = vec2<u32>(tx * INSTR_WIDTH, ty);
            } else {
                cpu.running = 0u;
                cpus[cpu_id] = cpu;
                return;
            }
        } else {
            let packed_pc = mem_read(cpu.registers[31]);
            cpu.registers[31] = cpu.registers[31] + 1u;
            let tx = packed_pc & 0xFFFFu;
            let ty = (packed_pc >> 16u) & 0xFFFFu;
            // Unlike CALL's jump target, the saved return address is already
            // in raw pixel units - no INSTR_WIDTH scaling here.
            next_pc = vec2<u32>(tx, ty);
        }
    } else if (opcode == OPCODE_CALLR) {
        // Computed call - bitwise twin of GlyphCPUv2's CALLR arm
        // (glyph_isa_v2.py:1279): push the (raw pixel-unit) return pc on
        // the r31 call stack, then jump to the packed target in rd with
        // the same tx*INSTR_WIDTH scaling JMPR/KJMP apply. WGSL parity
        // gap (2026-09-22): the const existed (opcode table line 37) but
        // this dispatch branch never did, so the transpiler's computed
        // calls (`jalr ra,N(ra)` -> CALLR r30, fix 2f619963) were silent
        // no-op fallthroughs on the shader path.
        // BK-49: same stack-path consult as CALL — the return-address push
        // is judged on its LANDING word (r31-1) before anything mutates.
        if (stack_fence_fault(cpu.registers[31] - 1u, cpu.mode == 0u)) {
            box_mmio[FAULT_ADDR_WORD - BOX_MMIO_WORD_LO] =
                (cpu.registers[31] - 1u) << 2u;
            box_mmio[FAULT_PC_WORD - BOX_MMIO_WORD_LO] =
                ((y & 0xFFFFu) << 16u) | ((x / INSTR_WIDTH) & 0xFFFFu);
            cpu.mode = 0u; // MODE_SUPER
            let kf = box_mmio[KFAULT_PC_WORD - BOX_MMIO_WORD_LO];
            if (kf != 0u) {
                let tx = kf & 0xFFFFu;
                let ty = (kf >> 16u) & 0xFFFFu;
                next_pc = vec2<u32>(tx * INSTR_WIDTH, ty);
            } else {
                cpu.running = 0u;
                cpus[cpu_id] = cpu;
                return;
            }
        } else {
            cpu.registers[31] = cpu.registers[31] - 1u;
            let packed_pc = (next_pc.y << 16u) | (next_pc.x & 0xFFFFu);
            mem_write(cpu.registers[31], packed_pc);

            let packed = cpu.registers[rd];
            let tx = packed & 0xFFFFu;
            let ty = (packed >> 16u) & 0xFFFFu;
            next_pc = vec2<u32>(tx * INSTR_WIDTH, ty);
        }
    } else if (opcode == OPCODE_JMP) {
        let tx = imm & 0xFFFFu;
        let ty = (imm >> 16u) & 0xFFFFu;
        next_pc = vec2<u32>(tx * INSTR_WIDTH, ty);
    } else if (opcode == OPCODE_JZ) {
        // Despite the name, this jumps when the CMP flag (r0) is nonzero
        // (i.e. "jump if equal") - matches GlyphCPUv2's own comment.
        if (cpu.registers[0] != 0u) {
            let tx = imm & 0xFFFFu;
            let ty = (imm >> 16u) & 0xFFFFu;
            next_pc = vec2<u32>(tx * INSTR_WIDTH, ty);
        }
    } else if (opcode == OPCODE_JNZ || opcode == OPCODE_JNE) {
        // SE024: exact boolean complement of JZ - jump when the CMP flag
        // (r0) is CLEAR. JNE is an alias of JNZ (see glyph_isa_v2.py).
        if (cpu.registers[0] == 0u) {
            let tx = imm & 0xFFFFu;
            let ty = (imm >> 16u) & 0xFFFFu;
            next_pc = vec2<u32>(tx * INSTR_WIDTH, ty);
        }
    } else if (opcode == OPCODE_JLT) {
        // SE025: jump when the CMP3 flag r0 == 0 (signed less-than).
        if (cpu.registers[0] == 0u) {
            let tx = imm & 0xFFFFu;
            let ty = (imm >> 16u) & 0xFFFFu;
            next_pc = vec2<u32>(tx * INSTR_WIDTH, ty);
        }
    } else if (opcode == OPCODE_JGT) {
        // SE025: jump when the CMP3 flag r0 == 2 (signed greater-than).
        // Equal (r0 == 1) falls through.
        if (cpu.registers[0] == 2u) {
            let tx = imm & 0xFFFFu;
            let ty = (imm >> 16u) & 0xFFFFu;
            next_pc = vec2<u32>(tx * INSTR_WIDTH, ty);
        }
    } else if (opcode == OPCODE_SYSCALL) {
        // BK-2: E-K2 trap, bitwise twin of GlyphCPUv2's SYSCALL handling
        // (glyph_isa_v2.py, `if ksys:` branch). When a kernel dispatcher
        // is armed (KSYS_PC word nonzero) this ignores the legacy
        // immediate-encoded syscall table entirely and instead: saves
        // the register file, marshals a7/a0/a1 (r17/r10/r11) into the
        // reserved words, saves the resume PC (SYSCALL_PC, packed the
        // same way KJMP's target packing works: y<<16 | (x/INSTR_WIDTH)),
        // drops to SUPER, and jumps KSYS_PC -- the SUPER-mode in-image
        // dispatcher (the same pixels the CPU oracle runs) takes it from
        // there and returns via SYSRET below. `imm`'s own encoding (the
        // instruction's own operand, `SYSCALL <rd> <imm>`) is NOT
        // consulted on this path, exactly like the CPU: the trap path
        // reads SYS_N from r17, never the immediate.
        let ksys = box_mmio[KSYS_PC_WORD - BOX_MMIO_WORD_LO];
        if (ksys != 0u) {
            cpu.saved_registers = cpu.registers;
            cpu.has_saved_regs = 1u;
            box_mmio[SYS_N_WORD - BOX_MMIO_WORD_LO] = cpu.registers[17];
            box_mmio[SYS_A0_WORD - BOX_MMIO_WORD_LO] = cpu.registers[10];
            box_mmio[SYS_A1_WORD - BOX_MMIO_WORD_LO] = cpu.registers[11];
            box_mmio[SYSCALL_PC_WORD - BOX_MMIO_WORD_LO] =
                (next_pc.y << 16u) | ((next_pc.x / INSTR_WIDTH) & 0xFFFFu);
            cpu.mode = 0u; // MODE_SUPER
            let tx = ksys & 0xFFFFu;
            let ty = (ksys >> 16u) & 0xFFFFu;
            next_pc = vec2<u32>(tx * INSTR_WIDTH, ty);
            cpu.pc = next_pc;
            cpus[cpu_id] = cpu;
            return;
        }
        // No kernel dispatcher armed: legacy immediate-encoded syscall
        // table (unchanged -- needed for images baked before E-K2, e.g.
        // the GH-4 parity fixtures that predate GH-18's kernel ABI).
        let syscall_num = imm;
        if (syscall_num == 1u) { // WRITE
            // backlog(d)/DEFECT-D (2026-09-16): migrated from image space
            // (mem_read) to RAM (ram_read), matching glyph_isa_v2.py's
            // 0x01 fix - same commit, both engines, per the going-forward
            // both-engines-per-handler rule.
            let addr = cpu.registers[1];
            let length = cpu.registers[2];
            var i: u32 = 0u;
            loop {
                if (i >= length) { break; }
                let val = ram_read(addr + i);
                let idx = cpu.output_ptr;
                if (idx < uniforms.output_buffer_size) {
                    output[cpu_id * uniforms.output_buffer_size + idx] = val;
                }
                cpu.output_ptr = cpu.output_ptr + 1u;
                i = i + 1u;
            }
            cpu.registers[rd] = 0u;
        } else if (syscall_num == 2u) { // READ
            // SE022a/2.2a: drain the harness-seeded input ring (mirrors
            // glyph_isa_v2.py's SYSCALL_READ, commit 7f47606) instead of
            // the old always-zero stub. total/cursor/data live in
            // box_mmio at INPUT_LEN_WORD/INPUT_CURSOR_WORD/INPUT_DATA_WORD
            // (one byte per word, same as the Python ring).
            // 2.2a residual (2026-09-16): dest migrated from image space
            // (mem_write) to RAM (ram_write), matching glyph_isa_v2.py's
            // 0x02 (writes self.memory) - same commit both engines, per
            // the going-forward both-engines-per-handler rule. ram_write
            // preserves the box_mmio sub-range alias and drops
            // out-of-range writes, mirroring the Python growth guard
            // (truncate, never extend RAM).
            let addr = cpu.registers[1];
            let length = cpu.registers[2];
            let total = box_mmio[INPUT_LEN_WORD - BOX_MMIO_WORD_LO];
            let cursor = box_mmio[INPUT_CURSOR_WORD - BOX_MMIO_WORD_LO];
            let capped_total = min(total, INPUT_DATA_CAP);
            var avail: u32 = 0u;
            if (capped_total > cursor) { avail = capped_total - cursor; }
            var n: u32 = length;
            if (avail < n) { n = avail; }
            var i: u32 = 0u;
            loop {
                if (i >= n) { break; }
                let b = box_mmio[(INPUT_DATA_WORD - BOX_MMIO_WORD_LO) + cursor + i];
                ram_write(addr + i, b);
                i = i + 1u;
            }
            box_mmio[INPUT_CURSOR_WORD - BOX_MMIO_WORD_LO] = cursor + n;
            cpu.registers[rd] = n;
        } else if (syscall_num == 3u || syscall_num == 4u || syscall_num == 6u) { // FILE_WRITE, FILE_READ, DEBUG
            cpu.registers[rd] = 0u;
        } else if (syscall_num == 16u) { // BOOT_LINUX (0x10)
            // backlog(d)/DEFECT-D residual (2026-09-22): bitwise twin of
            // glyph_isa_v2.py's RAM-migrated 0x10 arm. The VAC2 header is
            // DATA: bytes packed one per word, LOW byte first, read via
            // ram_read (out-of-range -> 0). Recognition only - no boot.
            // A RAM-seeded container is accepted (0); an image-only
            // seeding is refused (-1): ram_read does NOT fall back to
            // image pixels, matching the CPU engine's post-migration
            // behavior.
            let caddr = cpu.registers[1];
            let b0 = ram_read(caddr) & 0xFFu;
            let b1 = ram_read(caddr + 1u) & 0xFFu;
            let b2 = ram_read(caddr + 2u) & 0xFFu;
            let b3 = ram_read(caddr + 3u) & 0xFFu;
            // b"VAC2" = 0x56 0x41 0x43 0x32
            let ok = b0 == 0x56u && b1 == 0x41u && b2 == 0x43u && b3 == 0x32u;
            cpu.registers[rd] = select(4294967295u, 0u, ok);
        } else if (syscall_num == 5u) { // EXIT
            cpu.registers[rd] = cpu.registers[1]; // Return status
            cpu.running = 0u;
            cpus[cpu_id] = cpu;
            return;
        } else if (syscall_num >= 16u && syscall_num <= 255u && syscall_num != 18u && syscall_num != 19u) { // GeOS MMIO (18u=RUN2 excluded: TICKET_ITEM8; 19u=FILE_LIST excluded: BK-15 — both fall to unknown → -1)
            cpu.registers[rd] = 0u;
        } else { // Unknown
            cpu.registers[rd] = 4294967295u; // -1 as u32
        }
    } else if (opcode == OPCODE_SYSRET) {
        // BK-2: E-K2 return, bitwise twin of GlyphCPUv2's SYSRET. Restore
        // the pre-trap register file (if a SYSCALL actually saved one --
        // a bare SYSRET with none is a register-file no-op, matching the
        // CPU), then deliver the dispatcher's result (SYS_A0) into a0 =
        // r10, re-enter USER, and resume at the saved post-SYSCALL PC
        // (same tx*INSTR_WIDTH unpacking KJMP/JMPR use).
        if (cpu.has_saved_regs == 1u) {
            cpu.registers = cpu.saved_registers;
            cpu.has_saved_regs = 0u;
        }
        cpu.registers[10] = box_mmio[SYS_A0_WORD - BOX_MMIO_WORD_LO];
        cpu.mode = MODE_USER;
        let sp = box_mmio[SYSCALL_PC_WORD - BOX_MMIO_WORD_LO];
        let tx = sp & 0xFFFFu;
        let ty = (sp >> 16u) & 0xFFFFu;
        next_pc = vec2<u32>(tx * INSTR_WIDTH, ty);
    } else if (opcode == OPCODE_HALT) {
        cpu.running = 0u;
        cpus[cpu_id] = cpu;
        return;
    } else if (opcode == 1000u) {
        // ENG-1: unknown opcode — mirror GlyphCPUv2.step()'s halt-on-unknown
        // (`opcode is None -> running = False`). Pre-fix this fell through
        // to the pc writeback and silently continued as a no-op, diverging
        // from the Python oracle on any byte-corrupted opcode pixel.
        cpu.running = 0u;
        cpus[cpu_id] = cpu;
        return;
    }

    // GH-16 (R1.4): preemptive scheduling timer tick -- bitwise twin of
    // glyph_isa_v2.py:1322-1345. Fires after every COMPLETED USER-mode
    // instruction while still in USER and still running (the oracle also
    // requires `not faulted`; this shader's dropped-store E-K1 cannot
    // fault by construction, so the condition is mode+running here).
    // Counts down box_mmio[TIMER_COUNT]; on expiry reloads and vectors
    // to the kernel's KTICK handler in SUPER mode, saving the register
    // file + interrupted PC for the DEFECT-18 JMPR restore above.
    if (was_user && cpu.mode == MODE_USER && cpu.running == 1u) {
        let ktick = box_mmio[KTICK_PC_WORD - BOX_MMIO_WORD_LO];
        if (ktick != 0u) {
            var tcount = box_mmio[TIMER_COUNT_WORD - BOX_MMIO_WORD_LO];
            if (tcount > 0u) {
                tcount = tcount - 1u;
                box_mmio[TIMER_COUNT_WORD - BOX_MMIO_WORD_LO] = tcount;
                if (tcount == 0u) {
                    let reload_val = box_mmio[TIMER_RELOAD_WORD - BOX_MMIO_WORD_LO];
                    box_mmio[TIMER_COUNT_WORD - BOX_MMIO_WORD_LO] = reload_val;
                    box_mmio[TICK_PC_WORD - BOX_MMIO_WORD_LO] =
                        ((next_pc.y & 0xFFFFu) << 16u) | ((next_pc.x / INSTR_WIDTH) & 0xFFFFu);
                    cpu.tick_regs = cpu.registers;
                    cpu.has_tick_regs = 1u;
                    cpu.tick_pc = next_pc;
                    cpu.mode = 0u; // MODE_SUPER
                    let tx = ktick & 0xFFFFu;
                    let ty = (ktick >> 16u) & 0xFFFFu;
                    next_pc = vec2<u32>(tx * INSTR_WIDTH, ty);
                }
            }
        }
    }

    cpu.pc = next_pc;
    cpus[cpu_id] = cpu;
}
"""


def build_shader(opcode_map: OpcodeMapV2) -> str:
    consts, checks = generate_wgsl_opcode_table(opcode_map)
    src = _SHADER_TEMPLATE.replace("__OPCODE_CONSTS__", consts)
    src = src.replace("__OPCODE_CHECKS__", checks)
    return src


def make_cpu_state_array(n_cpus: int = 1):
    """One SpatialCPU per lane: pc(2) + registers(32) + running(1) +
    output_ptr(1) + mode(1) + saved_registers(32) + has_saved_regs(1)
    + tick_regs(32) + has_tick_regs(1) + tick_pc(2) + pad(1)
    + bk76_ever_user(1) + pad(1)
    = 108 u32 (432 bytes) -- BK-2's E-K2 SYSCALL/SYSRET register-file
    snapshot (see the WGSL struct's own comment for why this lives here
    rather than in box_mmio) + DEFECT-18's tick snapshot + BK-76-twin's
    ever-user latch.

    WGSL rounds the struct size up to its alignment (vec2<u32> => align 8);
    107 u32 (428) rounds to 432, hence the trailing pad word."""
    dtype = np.dtype([
        ('pc', np.uint32, 2),
        ('registers', np.uint32, 32),
        ('running', np.uint32),
        ('output_ptr', np.uint32),
        ('mode', np.uint32),
        ('saved_registers', np.uint32, 32),
        ('has_saved_regs', np.uint32),
        ('tick_regs', np.uint32, 32),
        ('has_tick_regs', np.uint32),
        ('tick_pc', np.uint32, 2),
        ('_tick_pad', np.uint32),  # WGSL aligns vec2 to 8: struct rounds 105 u32 -> 106
        ('bk76_ever_user', np.uint32),  # BK-76-twin: one-way ever-user latch
        ('_bk76_pad', np.uint32),  # WGSL struct rounds 107 u32 -> 108 (align 8)
    ])
    cpus = np.zeros(n_cpus, dtype=dtype)
    cpus['running'] = 1
    return cpus, dtype
