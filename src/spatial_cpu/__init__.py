"""
Spatial CPU — GPU-native RISC-V emulator.

This module provides spatial (GPU-native) execution of RISC-V binaries,
bypassing CPU-side emulation for 4-6x performance improvement.

Key Invariant: All instruction execution happens on GPU.
CPU side only orchestrates dispatch and completion polling.
"""

from .riscv_spatial_core import (
    RiscvSpatialCore,
    RegisterFile,
    MemoryRegion,
    DecodeResult,
    INSTRUCTION_WIDTH,
    WORD_SIZE,
    REGISTER_COUNT,
    PC_START,
)

__all__ = [
    'RiscvSpatialCore',
    'RegisterFile',
    'MemoryRegion',
    'DecodeResult',
    'INSTRUCTION_WIDTH',
    'WORD_SIZE',
    'REGISTER_COUNT',
    'PC_START',
]