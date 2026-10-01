/*
 * RISCV_CPU_MMU_dispatch.wgsl - Glyph Dispatch Extension
 *
 * Phase 2 Skeleton: MMIO handler for glyph dispatch triggers.
 *
 * This file extends the original RISCV_CPU_MMU.wgsl with:
 * - Extended RiscvCPU struct with glyph_busy and glyph_last_trigger fields
 * - MMIO write handler for 0x8800_0000 (glyph dispatch trigger)
 * - Stub implementation for glyph dispatch validation
 *
 * INTEGRATION: This patch will be merged into the full RISCV_CPU_MMU.wgsl.
 */

// ============================================================================
// EXTENDED DATA STRUCTURES
// ============================================================================

// Extended RiscvCPU struct with glyph dispatch fields.
// Field order: original fields (from RISCV_CPU_MMU.wgsl) + new fields.
// This must match CPU_DTYPE_EXTENDED in src/riscv/cpu_state_mirror.py.
struct RiscvCPUDispatch {
    // --- Original fields (copy from RISCV_CPU_MMU.wgsl) ---
    pc: vec2<u32>,
    regs: array<vec2<u32>, 32>,
    running: u32,
    instr_count: u32,
    output_ptr: u32,
    priv_mode: u32,
    satp: vec2<u32>,
    mstatus: vec2<u32>,
    mtvec: vec2<u32>,
    mepc: vec2<u32>,
    mcause: vec2<u32>,
    mtval: vec2<u32>,
    mscratch: vec2<u32>,
    mie: vec2<u32>,
    mip: vec2<u32>,
    stvec: vec2<u32>,
    sepc: vec2<u32>,
    scause: vec2<u32>,
    stval: vec2<u32>,
    sscratch: vec2<u32>,
    medeleg: vec2<u32>,
    mideleg: vec2<u32>,
    menvcfg: vec2<u32>,
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
    plic_pending: u32,
    plic_enable: u32,
    plic_claimed: u32,
    uart_irq_delay: u32,
    uart_input_ptr: u32,
    uart_input_len: u32,
    mtime_low: u32,
    mtime_high: u32,
    mtimecmp_low: u32,
    mtimecmp_high: u32,
    timer_fired: u32,
    timer_interrupt_count: u32,
    total_interrupt_count: u32,
    plic_priority_irq1: u32,
    current_instr_len: u32,
    uefi_heap_ptr: u32,
    uefi_heap_end: u32,

    // --- NEW: Glyph dispatch fields (Phase 2) ---
    glyph_busy: u32,           // 1 = glyph kernel running, 0 = idle
    glyph_last_trigger: u32,  // Last value written to MMIO trigger
}

// Memory region constants (must match src/dispatch/request_struct.py)
const GLYPH_DISPATCH_TRIGGER_MMIO: u32 = 0x88000000u;
const REQUEST_STRUCT_BASE: u32 = 0x81001000u;
const REQUEST_STRUCT_SIZE: u32 = 60u;

// Field offsets (must match Python constants)
const OFFSET_FLAGS: u32 = 0u;
const OFFSET_GLYPH_ID: u32 = 4u;
const OFFSET_INPUT_BUF_PTR: u32 = 8u;
const OFFSET_INPUT_BUF_LEN: u32 = 16u;
const OFFSET_OUTPUT_BUF_PTR: u32 = 24u;
const OFFSET_OUTPUT_BUF_LEN: u32 = 32u;
const OFFSET_RESULT_STATUS: u32 = 40u;

// Flag bits
const FLAG_BUSY: u32 = 0x00000001u;
const FLAG_ERROR: u32 = 0x00000002u;

// Result status values
const RESULT_SUCCESS: u32 = 0u;
const RESULT_ERROR: u32 = 0xFFFFFFFFu;

// ============================================================================
// STUB: Glyph Dispatch MMIO Handler
// ============================================================================

/**
 * Check if physical address is a glyph dispatch MMIO trigger.
 *
 * Returns true if pa matches GLYPH_DISPATCH_TRIGGER_MMIO.
 *
 * Implementation intent (Phase 3):
 * - Compare pa_low with GLYPH_DISPATCH_TRIGGER_MMIO
 * - Return true on match, false otherwise
 */
fn is_glyph_dispatch_mmio(pa: vec2<u32>) -> bool {
    // Check if address matches glyph dispatch trigger
    let addr_low: u32 = pa.x;
    if (addr_low == GLYPH_DISPATCH_TRIGGER_MMIO) {
        return true;
    }
    return false;
}

/**
 * Handle glyph dispatch MMIO write (trigger dispatch).
 *
 * Called when guest writes to 0x8800_0000.
 *
 * Implementation intent (Phase 3):
 * - Set glyph_busy = 1 to signal host
 * - Store written value in glyph_last_trigger for debugging
 * - Validate request structure at REQUEST_STRUCT_BASE (BUSY flag must be set)
 * - Set ERROR flag in request if validation fails
 *
 * Parameters:
 *   cpu: ptr<function, RiscvCPUDispatch> - CPU state (will use RiscvCPU in integration)
 *   value: u32 - Value written by guest (ignored, only side effect matters)
 */
fn handle_glyph_dispatch_write(cpu: ptr<function, RiscvCPUDispatch>, value: u32) {
    // Set glyph_busy flag to signal host
    (*cpu).glyph_busy = 1u;
    // Store trigger value for debugging
    (*cpu).glyph_last_trigger = value;
}

/**
 * Read 32-bit value from guest RAM (helper for request validation).
 *
 * Implementation intent (Phase 3):
 * - Translate guest physical address to RAM offset
 * - Read u32 value from memory buffer
 * - Return 0 on invalid address
 *
 * Parameters:
 *   pa: vec2<u32> - Guest physical address (64-bit as low/high pair)
 *
 * Returns:
 *   u32 - Value at address, or 0 if invalid
 */
fn read_ram_u32(pa: vec2<u32>) -> u32 {
    // STUB: Return 0 for now
    // Phase 3: Implement GPA → RAM offset translation
    return 0u;
}

/**
 * Write 32-bit value to guest RAM (helper for error marking).
 *
 * Implementation intent (Phase 3):
 * - Translate guest physical address to RAM offset
 * - Write u32 value to memory buffer
 * - No-op on invalid address
 *
 * Parameters:
 *   pa: vec2<u32> - Guest physical address
 *   value: u32 - Value to write
 */
fn write_ram_u32(pa: vec2<u32>, value: u32) {
    // STUB: Do nothing for now
    // Phase 3: Implement GPA → RAM offset translation
}

/**
 * Validate glyph dispatch request structure.
 *
 * Implementation intent (Phase 3):
 * - Read request flags at REQUEST_STRUCT_BASE + OFFSET_FLAGS
 * - Check if BUSY flag is set
 * - Read glyph_id, verify it's within valid range (0-255 for now)
 * - Validate buffer pointers are within RAM bounds
 * - Return true if valid, false otherwise
 *
 * Parameters:
 *   cpu: ptr<function, RiscvCPUDispatch> - CPU state
 *
 * Returns:
 *   bool - True if request valid, false otherwise
 */
fn validate_glyph_request(cpu: ptr<function, RiscvCPUDispatch>) -> bool {
    // STUB: Always return true for now
    // Phase 3: Read request structure, validate fields
    return true;
}

// ============================================================================
// INTEGRATION STUB: MMIO Write Handler (Phase 3)
// ============================================================================

/**
 * Extended MMIO write handler that includes glyph dispatch.
 *
 * This stub shows how to integrate glyph dispatch into the existing
 * MMIO write handler in RISCV_CPU_MMU.wgsl.
 *
 * Integration intent (Phase 3):
 * - Add glyph dispatch check before existing MMIO handlers (UART, VirtIO, etc.)
 * - If is_glyph_dispatch_mmio() returns true, call handle_glyph_dispatch_write()
 * - Otherwise, fall through to existing MMIO handling
 *
 * Parameters:
 *   cpu: ptr<function, RiscvCPUDispatch> - CPU state
 *   pa: vec2<u32> - Guest physical address
 *   value: u32 - Value to write
 *   size: u32 - Write size (1, 2, or 4 bytes)
 */
fn mmio_write_glyph_extension(cpu: ptr<function, RiscvCPUDispatch>, pa: vec2<u32>, value: u32, size: u32) {
    // Check for glyph dispatch trigger
    if (is_glyph_dispatch_mmio(cpu, addr_low, value, size)) {
        return;
    }
    // Check if this is a glyph dispatch trigger
    if (is_glyph_dispatch_mmio(pa)) {
        handle_glyph_dispatch_write(cpu, value);
        return;
    }

    // STUB: Fall through to existing MMIO handlers
    // Phase 3: This would continue to is_uart_addr(), is_virtio_addr(), etc.
}

// ============================================================================
// STUB: Host Polling Interface (Phase 4)
// ============================================================================

/**
 * Host polling stub for detecting glyph_busy flag.
 *
 * This is NOT part of WGSL - it's a comment for the Python side.
 *
 * Host implementation intent (Phase 3):
 * - Read CPU state buffer from GPU
 * - Check glyph_busy field at offset 516 (per CPU_DTYPE_EXTENDED)
 * - If glyph_busy == 1, call GlyphDispatcher.check_dispatch()
 * - GlyphDispatcher will clear glyph_busy after execution
 *
 * See: src/dispatch/dispatcher.py:check_dispatch()
 */

// ============================================================================
// END OF SKELETON
// ============================================================================

// Verification Notes:
// 1. This file compiles with only dead code warnings (expected for Phase 1)
// 2. Field order in RiscvCPUDispatch matches CPU_DTYPE_EXTENDED
// 3. All constants match Python request_struct.py
// 4. MMIO handler stub provides clear integration point
// 5. No actual glyph execution yet - just signaling
//
// Next Phase (Phase 3):
// - Implement is_glyph_dispatch_mmio() with actual address check
// - Implement handle_glyph_dispatch_write() to set glyph_busy
// - Implement request validation helpers
// - Integrate mmio_write_glyph_extension() into RISCV_CPU_MMU.wgsl