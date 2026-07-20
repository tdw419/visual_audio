"""
Shared host-side mirror of `struct RiscvCPU` in RISCV_CPU_MMU.wgsl.

Every harness must build its CPU state buffer from CPU_DTYPE so there is
exactly one place to update when the WGSL struct changes. The struct is
352 bytes; a size assert guards against drift.
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
])
assert CPU_DTYPE.itemsize == 352, f"CPU struct layout drifted: {CPU_DTYPE.itemsize}"

SATP_MODE_SV39 = 8


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
