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
    ('virtio_status', np.uint32),
    ('vq_desc_low', np.uint32),
    ('vq_desc_high', np.uint32),
    ('vq_avail_low', np.uint32),
    ('vq_avail_high', np.uint32),
    ('vq_used_low', np.uint32),
    ('vq_used_high', np.uint32),
    ('vq_idx', np.uint32),
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
])

assert CPU_DTYPE.itemsize == 480, f"CPU struct layout drifted: {CPU_DTYPE.itemsize}"

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


def make_cpu_state(entry_point: int, satp=(0, 0), priv_mode: int = 3):
    """One-hart CPU state array, booting in M-mode with MMU off by default."""
    cpu = np.zeros(1, dtype=CPU_DTYPE)
    cpu[0]['pc'] = [entry_point & 0xFFFFFFFF, (entry_point >> 32) & 0xFFFFFFFF]
    cpu[0]['running'] = 1
    cpu[0]['priv_mode'] = priv_mode
    cpu[0]['satp'] = list(satp)
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
    return cpu