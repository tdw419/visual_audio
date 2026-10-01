"""
Shared host-side mirror of `struct RiscvCPU` in RISCV_CPU_MMU.wgsl.

Every harness must build its CPU state buffer from CPU_DTYPE so there is
exactly one place to update when the WGSL struct changes.
"""

import numpy as np

CPU_DTYPE = np.dtype([
    ('pc', np.uint32, 2),
    ('regs', np.uint32, (32, 2)),
    ('running', np.uint32),
    ('instr_count', np.uint32),
    ('output_ptr', np.uint32),
    ('priv_mode', np.uint32),   # 3 = M-mode (boot default), 1 = S, 0 = U
    ('satp', np.uint32, 2),     # Real RV64 layout: mode [63:60], PPN [43:0]
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
    ('menvcfg', np.uint32, 2),  # CSR 0x30A, machine environment config
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
    ('uart_input_ptr', np.uint32),  # guest-owned, persists across dispatches
    ('uart_input_len', np.uint32),  # host-owned; shader only reads it
    ('mtime_low', np.uint32),       # CLINT mtime (low 32 bits)
    ('mtime_high', np.uint32),      # CLINT mtime (high 32 bits)
    ('mtimecmp_low', np.uint32),    # CLINT mtimecmp (low 32 bits)
    ('mtimecmp_high', np.uint32),   # CLINT mtimecmp (high 32 bits)
    ('timer_fired', np.uint32),     # Edge trigger: timer already fired for this mtimecmp
    ('timer_interrupt_count', np.uint32),  # Number of timer interrupts taken
    ('total_interrupt_count', np.uint32),  # Total interrupts taken
    ('plic_priority_irq1', np.uint32),     # Priority for IRQ 1
    ('current_instr_len', np.uint32),      # 2 (RVC) or 4 - set by fetch
    ('uefi_heap_ptr', np.uint32),          # Next free byte in the UEFI AllocatePool heap
    ('uefi_heap_end', np.uint32),          # First byte past the UEFI heap region
])

assert CPU_DTYPE.itemsize == 528, f"CPU struct layout drifted: {CPU_DTYPE.itemsize}"

SATP_MODE_SV39 = 8

# Delegation defaults for an S-mode kernel boot (what OpenSBI programs):
# exceptions: misaligned fetch, breakpoint, ecall-from-U, page faults (12/13/15)
MEDELEG_DEFAULT = (1 << 0) | (1 << 3) | (1 << 8) | (1 << 12) | (1 << 13) | (1 << 15)  # 0xB109
# interrupts: supervisor software/timer/external (SSIP/STIP/SEIP)
MIDELEG_DEFAULT = (1 << 1) | (1 << 5) | (1 << 9)  # 0x222


def make_satp(root_ppn: int, mode: int = SATP_MODE_SV39):
    """satp as [low, high] u32 pair. RV64: mode in bits [63:60], PPN in [43:0]."""
    value = (mode << 60) | (root_ppn & ((1 << 44) - 1))
    return [value & 0xFFFFFFFF, (value >> 32) & 0xFFFFFFFF]


# QEMU's virt machine reads menvcfg as 0x2000000000000000 at hart reset,
# before any explicit CSR write (confirmed via `-d in_asm` trace at `IN: start`).
# qemu_cpu_trace.py's register dump doesn't capture menvcfg, so this can't be
# picked up via apply_init_state - it must match QEMU's hart reset default here.
MENVCFG_RESET_DEFAULT = 0x2000000000000000


def make_cpu_state(entry_point: int, satp=(0, 0), priv_mode: int = 3):
    """One-hart CPU state array, booting in M-mode with MMU off by default."""
    cpu = np.zeros(1, dtype=CPU_DTYPE)
    cpu[0]['pc'] = [entry_point & 0xFFFFFFFF, (entry_point >> 32) & 0xFFFFFFFF]
    cpu[0]['running'] = 1
    cpu[0]['priv_mode'] = priv_mode
    cpu[0]['satp'] = list(satp)
    cpu[0]['menvcfg'] = [MENVCFG_RESET_DEFAULT & 0xFFFFFFFF, (MENVCFG_RESET_DEFAULT >> 32) & 0xFFFFFFFF]
    return cpu


def apply_init_state(cpu: np.ndarray, init_state_path: str) -> np.ndarray:
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
                      '_pad0'}
    csr_fields = {name for name in CPU_DTYPE.names if name not in non_csr_fields}
    
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


def make_linux_boot_state(entry_point: int, dtb_addr: int):
    """CPU state for direct S-mode kernel entry, per the RISC-V Linux boot
    protocol: a0 = hart ID (0), a1 = DTB physical address, MMU off,
    delegation programmed as firmware would leave it."""
    cpu = make_cpu_state(entry_point, priv_mode=1)
    cpu[0]['regs'][10] = [0, 0]  # a0 = hart 0
    cpu[0]['regs'][11] = [dtb_addr & 0xFFFFFFFF, (dtb_addr >> 32) & 0xFFFFFFFF]  # a1 = DTB
    cpu[0]['medeleg'] = [MEDELEG_DEFAULT & 0xFFFFFFFF, 0]
    cpu[0]['mideleg'] = [MIDELEG_DEFAULT & 0xFFFFFFFF, 0]
    # Set stvec to a non-zero trap handler to prevent early halt
    # Use 0x80200000 as a simple trap handler region
    cpu[0]['stvec'] = [0x80200000 & 0xFFFFFFFF, 0]
    # Enable S-mode interrupts in mstatus
    cpu[0]['mstatus'] = [0x00000002, 0]  # SIE bit set
    return cpu
