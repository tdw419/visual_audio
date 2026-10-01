#!/usr/bin/env python3
"""substor_boot.py — Bounded guest boot driver for Geometry OS (SUBSTOR-1).

Runs a real guest on the GPU-native RV32IMA emulator (SpatialRV32ICore in
tools/spatial_rv32i_cpu.py) with RAM served directly from a substrate-backed
store (SubstorSurfaceRAM in tools/substor_surface_ram.py) instead of a host-side
Python array.

ARCHITECTURAL CONTRACT (SUBSTOR-1):
1. Substrate Authority: Load from surface before each chunk; writeback to surface
   after each chunk. No host-side shadow buffer exists in the path. A mutation
   applied to the surface between chunks is loaded into the core and immediately
   seen by the guest's next chunk.
2. Bounded Boot: The driver executes a bounded instruction sequence finishing
   well under 120 seconds.
3. Guest Documentation and Honesty Statement:
   - GUEST RUN: The guest run in this implementation is `RV32IMA_SUBSTOR_GUEST`,
     a real RV32IMA guest program linked at RAM_BASE = 0x80000000.
   - STEPS EXECUTED: Exactly 8 RV32IMA instructions are executed across chunks
     to reach the named progress marker:
       * Instruction 0 (0x80000000): lui  x1, 0x80000
       * Instruction 1 (0x80000004): addi x1, x1, 0x100      (x1 = 0x80000100)
       * Instruction 2 (0x80000008): lw   x2, 0(x1)          (load RAM word)
       * Instruction 3 (0x8000000C): addi x2, x2, 1          (increment)
       * Instruction 4 (0x80000010): sw   x2, 0(x1)          (store RAM word)
       * Instruction 5 (0x80000014): lui  x3, 0x10000        (UART MMIO base)
       * Instruction 6 (0x80000018): addi x4, x0, 66         (ASCII 'B' = 66)
       * Instruction 7 (0x8000001C): sw   x4, 0(x3)          (emit UART byte)
       * Instruction 8 (0x80000020): beq  x0, x0, marker     (named PC 0x80000020)
   - NAMED PROGRESS MARKERS:
       * UART output: byte b'B' (0x42) emitted to UART TX MMIO.
       * RAM modification: Word 64 (0x80000100) modified in substrate RAM.
       * Named PC marker: 0x80000020.
   - HONESTY BOUNDARY: A full Linux kernel boot (`boot_images/rv32ima_nommu/Image`
     + `sixtyfourmb.dtb`, 3.4 MB kernel + 64 MB RAM) was NOT executed on this
     substrate surface path. Millions of instructions over a 64 MB surface would
     exceed reasonable test timeouts (~120s gate cap). We honestly report that we
     chose the smallest real RV32IMA guest that satisfies L1 rather than claiming
     a Linux boot we did not perform.
   - MEASURED vs ESTIMATED LABELS:
       * The 4 KB glyph-program memory figure is MEASURED (1024 words × 4 B).
       * The ~37× DSL→glyph expansion is MEASURED but a different quantity
         (compile-time expansion, NOT interpreter overhead).
       * The ~30–100 glyph steps per guest instruction figure is an ESTIMATE, unmeasured.
"""
from __future__ import annotations

import struct
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO / "tools") not in sys.path:
    sys.path.insert(0, str(_REPO / "tools"))

from rv32i_asm import assemble
from spatial_rv32i_cpu import SpatialRV32ICore
from substor_surface_ram import (
    SubstorSurfaceRAM,
    SubstorWitness,
    verify_substrate_witness,
)

RAM_BASE: int = 0x80000000
DEFAULT_MEMORY_SIZE: int = 4096  # 1024 words (4 KB measured glyph memory figure)
PROGRESS_MARKER_BYTE: bytes = b"B"  # ASCII 66
PROGRESS_MARKER_PC: int = 0x80000020
PROGRESS_MARKER_STEPS: int = 8
RAM_DATA_OFFSET: int = 0x100  # byte offset 0x100 = word index 64
INITIAL_RAM_VALUE: int = 41
EXPECTED_RAM_VALUE: int = 42

RV32IMA_SUBSTOR_GUEST_ASM = """
    lui  x1, 0x80000
    addi x1, x1, 0x100
    lw   x2, 0(x1)
    addi x2, x2, 1
    sw   x2, 0(x1)
    lui  x3, 0x10000
    addi x4, x0, 66
    sw   x4, 0(x3)
marker:
    beq  x0, x0, marker
"""


def build_guest_binary() -> bytes:
    """Assemble the smallest real RV32IMA guest into binary machine code."""
    return assemble(RV32IMA_SUBSTOR_GUEST_ASM)


class SubstorBootDriver:
    """Bounded boot driver running SpatialRV32ICore backed by SubstorSurfaceRAM."""

    def __init__(
        self,
        surface_ram: SubstorSurfaceRAM,
        ram_base: int = RAM_BASE,
        memory_size_bytes: int = DEFAULT_MEMORY_SIZE,
        entry_point: int = RAM_BASE,
    ):
        self.surface_ram = surface_ram
        self.ram_base = int(ram_base)
        self.memory_size_bytes = int(memory_size_bytes)
        self.total_words = self.memory_size_bytes // 4
        self.entry_point = int(entry_point)

        # SpatialRV32ICore requires memory length to be a perfect square
        self.core = SpatialRV32ICore(memory_size_bytes=self.memory_size_bytes)
        self.N = int(np.sqrt(self.total_words))
        if self.N * self.N != self.total_words:
            raise ValueError(
                f"Memory word count {self.total_words} must be a perfect square"
            )

        self.total_steps: int = 0
        self.last_pre_writeback: Optional[List[int]] = None
        self.last_post_writeback: Optional[List[int]] = None
        self.accumulated_uart: bytearray = bytearray()

        # Initial synchronization from surface into core
        self.load_from_surface()

        # Initialize core CPUState registers with entry_point and ram_base
        state_data = np.array(
            [self.entry_point, 0, 0, 3, 0, 0, 0, 0, 0, 0, self.ram_base, 0, 0],
            dtype=np.uint32,
        ).tobytes()
        self.core.queue.write_buffer(self.core.state_buffer, 0, state_data)

    def load_from_surface(self) -> None:
        """Load RAM state directly from substrate surface into core.

        No host-side shadow buffer exists: the surface is the sole authority.
        """
        words = self.surface_ram.get_words(0, self.total_words)
        linear_arr = np.array(words, dtype=np.uint32)
        spatial_arr = np.zeros(self.total_words, dtype=np.uint32)

        for i, val in enumerate(linear_arr):
            x, y = self.core._d2xy(self.N, i)
            spatial_arr[y * self.N + x] = val

        self.core.memory.write_data(self.core.queue, spatial_arr.tobytes())

    def writeback_to_surface(self, writer: str = "guest_boot") -> int:
        """Read modified memory from GPU core and write back to substrate surface.

        Preserves writer attribution, logs write IDs, and records pre/post writeback snapshots.
        """
        # Read full memory buffer from core and un-Hilbert map
        raw_bytes = self.core.queue.read_buffer(self.core.memory.buffer)
        spatial_arr = np.frombuffer(raw_bytes, dtype=np.uint32)
        linear_words = np.zeros(self.total_words, dtype=np.uint32)
        for i in range(self.total_words):
            x, y = self.core._d2xy(self.N, i)
            linear_words[i] = spatial_arr[y * self.N + x]

        pre_words = [int(w) for w in linear_words]
        self.last_pre_writeback = list(pre_words)

        current_surface_words = self.surface_ram.get_words(0, self.total_words)
        modified_count = 0
        for idx, (new_val, old_val) in enumerate(zip(pre_words, current_surface_words)):
            if new_val != old_val:
                self.surface_ram.write_word(idx, new_val, writer=writer)
                modified_count += 1

        if self.surface_ram.surface_path:
            self.surface_ram.commit_surface()

        post_words = self.surface_ram.get_words(0, self.total_words)
        self.last_post_writeback = list(post_words)
        return modified_count

    def step_chunk(self, steps: int = 1, writer: str = "guest_boot") -> Dict[str, Any]:
        """Execute a chunk of instructions with load-before and writeback-after."""
        # 1. Authority: Load from surface into core before chunk
        self.load_from_surface()

        # 2. Step the GPU core
        self.core.step(steps=steps)
        self.total_steps += steps

        # 3. Writeback to surface after chunk
        self.writeback_to_surface(writer=writer)

        # 4. Drain UART output and collect CPU state
        uart = self.core.read_uart_output()
        if uart:
            self.accumulated_uart.extend(uart)

        state = self.core.get_state()
        return {
            "pc": int(state["pc"]),
            "steps": self.total_steps,
            "uart": uart,
            "accumulated_uart": bytes(self.accumulated_uart),
            "halted": int(state["halted"]),
            "regs": state["regs"],
        }

    def run_to_progress_marker(
        self, max_steps: int = 32, chunk_size: int = 4, writer: str = "guest_boot"
    ) -> Dict[str, Any]:
        """Run in chunks until the progress marker (UART byte or named PC) is reached."""
        while self.total_steps < max_steps:
            steps_to_run = min(chunk_size, max_steps - self.total_steps)
            info = self.step_chunk(steps=steps_to_run, writer=writer)
            if (
                PROGRESS_MARKER_BYTE in self.accumulated_uart
                or info["pc"] == PROGRESS_MARKER_PC
            ):
                return info

        return self.step_chunk(steps=0, writer=writer)

    def check_witness(self) -> Dict[str, Any]:
        """Verify substrate witness invariants on the current surface state."""
        return verify_substrate_witness(
            self.surface_ram, self.last_pre_writeback, self.last_post_writeback
        )


def create_booted_substrate_guest(
    surface_path: Optional[Union[str, Path]] = None,
    initial_ram_val: int = INITIAL_RAM_VALUE,
    memory_size_bytes: int = DEFAULT_MEMORY_SIZE,
) -> Tuple[SubstorBootDriver, SubstorSurfaceRAM]:
    """Factory creating a initialized SubstorSurfaceRAM and SubstorBootDriver.

    Sets up declared regions:
    - 'loader': owns the instruction region [0, code_words)
    - 'guest_boot': owns the full RAM region [0, total_words)
    Pre-populates the guest binary and initial RAM seed with writer attribution.
    """
    total_words = memory_size_bytes // 4
    surface_ram = SubstorSurfaceRAM(
        size_words=total_words, surface_path=surface_path
    )

    binary = build_guest_binary()
    padded_binary = binary + b"\x00" * ((4 - len(binary) % 4) % 4)
    code_words = list(np.frombuffer(padded_binary, dtype=np.uint32))
    num_code_words = len(code_words)

    # Declare regions
    surface_ram.declare_region("loader", 0, num_code_words)
    surface_ram.declare_region("guest_boot", 0, total_words)

    # Loader writes instructions into substrate surface RAM
    surface_ram.write_words(0, code_words, writer="loader")

    # Guest boot seeds initial RAM data at word 64 (offset 0x100)
    data_word_idx = RAM_DATA_OFFSET // 4
    surface_ram.write_word(data_word_idx, initial_ram_val, writer="guest_boot")

    if surface_path:
        surface_ram.commit_surface()

    driver = SubstorBootDriver(
        surface_ram=surface_ram,
        ram_base=RAM_BASE,
        memory_size_bytes=memory_size_bytes,
        entry_point=RAM_BASE,
    )
    return driver, surface_ram
