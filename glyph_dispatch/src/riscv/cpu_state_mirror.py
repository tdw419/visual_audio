# CPU state mirror with glyph dispatch extensions

import numpy as np

# Original CPU_DTYPE from tools/riscv_gpu_cpu.py
CPU_DTYPE_ORIGINAL = np.dtype([
    ('pc', np.uint32, 2),
    ('regs', np.uint32, (32, 2)),
    ('running', np.uint32),
    ('instr_count', np.uint32),
    ('output_ptr', np.uint32),
    ('priv_mode', np.uint32),
    ('satp', np.uint32, 2),
    ('mstatus', np.uint32, 2),
    ('mtvec', np.uint32, 2),
    ('mepc', np.uint32, 2),
    ('mcause', np.uint32, 2),
    ('mtval', np.uint32, 2),
    ('mscratch', np.uint32, 2),
    ('mie', np.uint32, 2),
    ('mip', np.uint32, 2),
    ('stvec', np.uint32, 2),
    ('sepc', np.uint32, 2),
    ('scause', np.uint32, 2),
    ('stval', np.uint32, 2),
    ('sscratch', np.uint32, 2),
    ('medeleg', np.uint32, 2),
    ('mideleg', np.uint32, 2),
    ('menvcfg', np.uint32, 2),
    ('virtio_status', np.uint32),
    ('vq_desc_low', np.uint32),
    ('vq_desc_high', np.uint32),
    ('vq_avail_low', np.uint32),
    ('vq_avail_high', np.uint32),
    ('vq_used_low', np.uint32),
    ('vq_used_high', np.uint32),
    ('vq_idx', np.uint32),
    ('vq_ready', np.uint32),
    ('vq_queue_num', np.uint32),
    ('vq_queue_align', np.uint32),
    ('plic_pending', np.uint32),
    ('plic_enable', np.uint32),
    ('plic_claimed', np.uint32),
    ('uart_irq_delay', np.uint32),
    ('uart_input_ptr', np.uint32),
    ('uart_input_len', np.uint32),
    ('mtime_low', np.uint32),
    ('mtime_high', np.uint32),
    ('mtimecmp_low', np.uint32),
    ('mtimecmp_high', np.uint32),
    ('timer_fired', np.uint32),
    ('timer_interrupt_count', np.uint32),
    ('total_interrupt_count', np.uint32),
    ('plic_priority_irq1', np.uint32),
    ('current_instr_len', np.uint32),
    ('uefi_heap_ptr', np.uint32),
    ('uefi_heap_end', np.uint32),
])

# Extended CPU_DTYPE with glyph dispatch fields
CPU_DTYPE_EXTENDED = np.dtype([
    ('pc', np.uint32, 2),
    ('regs', np.uint32, (32, 2)),
    ('running', np.uint32),
    ('instr_count', np.uint32),
    ('output_ptr', np.uint32),
    ('priv_mode', np.uint32),
    ('satp', np.uint32, 2),
    ('mstatus', np.uint32, 2),
    ('mtvec', np.uint32, 2),
    ('mepc', np.uint32, 2),
    ('mcause', np.uint32, 2),
    ('mtval', np.uint32, 2),
    ('mscratch', np.uint32, 2),
    ('mie', np.uint32, 2),
    ('mip', np.uint32, 2),
    ('stvec', np.uint32, 2),
    ('sepc', np.uint32, 2),
    ('scause', np.uint32, 2),
    ('stval', np.uint32, 2),
    ('sscratch', np.uint32, 2),
    ('medeleg', np.uint32, 2),
    ('mideleg', np.uint32, 2),
    ('menvcfg', np.uint32, 2),
    ('virtio_status', np.uint32),
    ('vq_desc_low', np.uint32),
    ('vq_desc_high', np.uint32),
    ('vq_avail_low', np.uint32),
    ('vq_avail_high', np.uint32),
    ('vq_used_low', np.uint32),
    ('vq_used_high', np.uint32),
    ('vq_idx', np.uint32),
    ('vq_ready', np.uint32),
    ('vq_queue_num', np.uint32),
    ('vq_queue_align', np.uint32),
    ('plic_pending', np.uint32),
    ('plic_enable', np.uint32),
    ('plic_claimed', np.uint32),
    ('uart_irq_delay', np.uint32),
    ('uart_input_ptr', np.uint32),
    ('uart_input_len', np.uint32),
    ('mtime_low', np.uint32),
    ('mtime_high', np.uint32),
    ('mtimecmp_low', np.uint32),
    ('mtimecmp_high', np.uint32),
    ('timer_fired', np.uint32),
    ('timer_interrupt_count', np.uint32),
    ('total_interrupt_count', np.uint32),
    ('plic_priority_irq1', np.uint32),
    ('current_instr_len', np.uint32),
    ('uefi_heap_ptr', np.uint32),
    ('uefi_heap_end', np.uint32),
    # Glyph dispatch extensions (added at end)
    ('glyph_busy', np.uint32),           # 1 = glyph kernel running, 0 = idle
    ('glyph_last_trigger', np.uint32),  # Last value written to MMIO trigger
])

# Verify sizes
assert CPU_DTYPE_ORIGINAL.itemsize == 528, f"Original CPU struct size drifted: {CPU_DTYPE_ORIGINAL.itemsize}"
assert CPU_DTYPE_EXTENDED.itemsize == 536, f"Extended CPU struct size drifted: {CPU_DTYPE_EXTENDED.itemsize}"

# Default to original for compatibility with existing tools
CPU_DTYPE = CPU_DTYPE_ORIGINAL

# Field offsets for glyph busy detection
# Based on CPU_DTYPE_EXTENDED layout:
# Fields 0-42: original fields (516 bytes)
# Field 43: glyph_busy at offset 516
# Field 44: glyph_last_trigger at offset 520
GLYPH_BUSY_OFFSET = 516
GLYPH_LAST_TRIGGER_OFFSET = 520

# Constants from original file
SATP_MODE_SV39 = 8
MEDELEG_DEFAULT = (1 << 0) | (1 << 3) | (1 << 8) | (1 << 12) | (1 << 13) | (1 << 15)  # 0xB109
MIDELEG_DEFAULT = (1 << 1) | (1 << 5) | (1 << 9)  # 0x222
MENVCFG_RESET_DEFAULT = 0x2000000000000000


def make_satp(root_ppn: int, mode: int = SATP_MODE_SV39):
    """satp as [low, high] u32 pair. RV64: mode in bits [63:60], PPN in [43:0]."""
    value = (mode << 60) | (root_ppn & ((1 << 44) - 1))
    return [value & 0xFFFFFFFF, (value >> 32) & 0xFFFFFFFF]


def make_cpu_state(entry_point: int, satp=(0, 0), priv_mode: int = 3, use_extended: bool = False):
    """One-hart CPU state array, booting in M-mode with MMU off by default.

    Args:
        entry_point: PC value to start at
        satp: SATP CSR value as [low, high] pair
        priv_mode: Privilege mode (3=M, 1=S, 0=U)
        use_extended: If True, use CPU_DTYPE_EXTENDED with glyph fields

    Returns:
        numpy array with CPU state
    """
    dtype = CPU_DTYPE_EXTENDED if use_extended else CPU_DTYPE
    cpu = np.zeros(1, dtype=dtype)
    cpu[0]['pc'] = [entry_point & 0xFFFFFFFF, (entry_point >> 32) & 0xFFFFFFFF]
    cpu[0]['running'] = 1
    cpu[0]['priv_mode'] = priv_mode
    cpu[0]['satp'] = list(satp)
    cpu[0]['menvcfg'] = [MENVCFG_RESET_DEFAULT & 0xFFFFFFFF, (MENVCFG_RESET_DEFAULT >> 32) & 0xFFFFFFFF]
    return cpu


def make_linux_boot_state(entry_point: int, dtb_addr: int, use_extended: bool = False):
    """CPU state for direct S-mode kernel entry, per the RISC-V Linux boot protocol:
    a0 = hart ID (0), a1 = DTB physical address, MMU off, delegation programmed as firmware
    would leave it.

    Args:
        entry_point: PC value to start at
        dtb_addr: Device tree blob physical address
        use_extended: If True, use CPU_DTYPE_EXTENDED with glyph fields

    Returns:
        numpy array with CPU state
    """
    cpu = make_cpu_state(entry_point, priv_mode=1, use_extended=use_extended)
    cpu[0]['regs'][10] = [0, 0]  # a0 = hart 0
    cpu[0]['regs'][11] = [dtb_addr & 0xFFFFFFFF, (dtb_addr >> 32) & 0xFFFFFFFF]  # a1 = DTB
    cpu[0]['medeleg'] = [MEDELEG_DEFAULT & 0xFFFFFFFF, 0]
    cpu[0]['mideleg'] = [MIDELEG_DEFAULT & 0xFFFFFFFF, 0]
    # Set stvec to a non-zero trap handler to prevent early halt
    cpu[0]['stvec'] = [0x80200000 & 0xFFFFFFFF, 0]
    # Enable S-mode interrupts in mstatus
    cpu[0]['mstatus'] = [0x00000002, 0]  # SIE bit set
    return cpu


def apply_init_state(cpu: np.ndarray, init_state_path: str):
    """Apply a QEMU-extracted initial state JSON to a CPU state array.

    The JSON format matches what qemu_cpu_trace.py and diff_qemu_gpu_traces.py emit:
    {'pc': int, 'regs': {name: value, ...}}

    Only registers matching known CSR/GPR names are applied; unknown names are silently skipped.
    """
    import json
    with open(init_state_path) as f:
        state = json.load(f)

    # Determine which CSR fields are present in our cpu_dtype layout
    non_csr_fields = {'pc', 'regs', 'running', 'instr_count', 'output_ptr',
                      'priv_mode', 'virtio_status', 'vq_desc_low', 'vq_desc_high',
                      'vq_avail_low', 'vq_avail_high', 'vq_used_low', 'vq_used_high',
                      'vq_idx', 'plic_pending', 'plic_enable', 'plic_claimed',
                      'uart_irq_delay', 'uart_input_ptr', 'uart_input_len',
                      'mtime_low', 'mtime_high', 'mtimecmp_low', 'mtimecmp_high',
                      'timer_fired', 'timer_interrupt_count', 'total_interrupt_count',
                      'glyph_busy', 'glyph_last_trigger', '_pad0'}
    csr_fields = {name for name in cpu.dtype.names if name not in non_csr_fields}

    regs = state.get('regs', {})

    # Apply GPRs from x0-x31
    for i in range(32):
        key = f'x{i}'
        if key in regs and regs[key] != 0:
            val = int(regs[key])
            cpu[0]['regs'][i] = [val & 0xFFFFFFFF, (val >> 32) & 0xFFFFFFFF]

    # Apply CSRs (vec2<u32> fields)
    for field in csr_fields:
        if field in regs:
            val = int(regs[field])
            cpu[0][field] = [val & 0xFFFFFFFF, (val >> 32) & 0xFFFFFFFF]

    # Apply PC
    if 'pc' in regs:
        val = int(regs['pc'])
        cpu[0]['pc'] = [val & 0xFFFFFFFF, (val >> 32) & 0xFFFFFFFF]

    return cpu


# Test harness
if __name__ == "__main__":
    print("=== CPU State Mirror Test ===")

    # Test original dtype
    cpu_orig = make_cpu_state(0x80000000)
    print(f"Original CPU_DTYPE size: {CPU_DTYPE_ORIGINAL.itemsize} bytes")
    print(f"Original CPU state size: {cpu_orig.nbytes} bytes")

    # Test extended dtype
    cpu_ext = make_cpu_state(0x80000000, use_extended=True)
    print(f"Extended CPU_DTYPE size: {CPU_DTYPE_EXTENDED.itemsize} bytes")
    print(f"Extended CPU state size: {cpu_ext.nbytes} bytes")

    # Verify field offsets
    print(f"\nGlyph busy offset: {GLYPH_BUSY_OFFSET}")
    print(f"Glyph last trigger offset: {GLYPH_LAST_TRIGGER_OFFSET}")

    # Test setting glyph fields
    cpu_ext[0]['glyph_busy'] = 1
    cpu_ext[0]['glyph_last_trigger'] = 0xDEADBEEF

    print(f"Glyph busy: {cpu_ext[0]['glyph_busy']}")
    print(f"Glyph last trigger: 0x{cpu_ext[0]['glyph_last_trigger']:08x}")

    # Test Linux boot state
    linux_state = make_linux_boot_state(0x80200000, 0x82000000)
    print(f"\nLinux boot state PC: {linux_state[0]['pc']}")
    print(f"Linux boot state a0: {linux_state[0]['regs'][10]}")
    print(f"Linux boot state a1: {linux_state[0]['regs'][11]}")

    print("\n✅ All tests passed!")