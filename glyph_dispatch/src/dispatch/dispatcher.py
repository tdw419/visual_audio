"""
Glyph Dispatcher — Host-side implementation.

Detects glyph dispatch triggers from RISC-V guest, loads glyph programs,
executes them on GPU, and writes results back to guest RAM.

Integration:
- Extends qemu_gpu_offload.py run_with_offload() loop
- Reads CPU state from GPU buffer to detect triggers
- Reads/writes guest RAM via GpuRam
- Executes glyph programs via GlyphCPUv2
"""

import sys
from pathlib import Path
from typing import Callable, Dict, Optional
import numpy as np

# Isolated imports: use glyph_dispatch's own copy of the Glyph ISA, never the
# repo-level tools/ copy (keeps this module self-contained and matches the
# SHA-256 kernel, which imports the same way).
#
# TEST-COL-1 (2026-09-13): these used to be absolute `from src.glyph...` imports,
# which required inserting `glyph_dispatch/` at sys.path[0]. That shadowed the
# repo's own top-level `src` package for the whole interpreter session (any later
# `import src.*` resolved to glyph_dispatch/src), which aborted collection of 17
# unrelated tests/ modules. Package-relative imports keep the isolation with no
# sys.path side effect.
from ..glyph.glyph_isa_v2 import OpcodeMapV2, GlyphAssemblerV2, GlyphCPUv2
from ..glyph.sha256_kernel import sha256_glyph
from .request_struct import (
    REQUEST_STRUCT_BASE,
    REQUEST_STRUCT_SIZE,
    OFFSET_FLAGS,
    OFFSET_GLYPH_ID,
    OFFSET_INPUT_BUF_PTR,
    OFFSET_INPUT_BUF_LEN,
    OFFSET_OUTPUT_BUF_PTR,
    OFFSET_OUTPUT_BUF_LEN,
    OFFSET_RESULT_STATUS,
    FLAG_BUSY,
    FLAG_ERROR,
    RESULT_SUCCESS,
    RESULT_ERROR,
    RESULT_OUTPUT_TOO_SMALL,
    RESULT_GLYPH_FAILED,
    GLYPH_ID_TEST_COUNTER,
    GLYPH_ID_SHA256,
)


class GlyphDispatcher:
    """Dispatch glyph kernels on behalf of RISC-V guest."""

    def __init__(self, ram, state_buffer=None, glyph_db_path: Optional[str] = None):
        """
        Initialize dispatcher.

        Args:
            ram: GpuRam instance for accessing guest memory
            state_buffer: GPU state buffer for reading glyph_busy flag (optional)
            glyph_db_path: Path to glyph program registry database (optional)
        """
        self.ram = ram

        # CPU state buffer (if provided)
        self.state_buffer = state_buffer
        self.glyph_busy_offset = None  # Will be determined from WGSL struct

        # Load glyph programs
        self.glyph_registry: Dict[int, GlyphProgram] = {}
        self._load_builtin_glyphs()

    def _load_builtin_glyphs(self):
        """Load built-in glyph programs."""
        op_map = OpcodeMapV2()
        assembler = GlyphAssemblerV2(op_map)

        # Glyph 0: minimal test kernel -- writes a known value via PRT.
        simple_test_image = assembler.assemble(
            ["LDI r1 42", "PRT r1", "HALT"], width_instrs=8)
        self.glyph_registry[GLYPH_ID_TEST_COUNTER] = GlyphProgram(
            id=GLYPH_ID_TEST_COUNTER,
            name="test_counter",
            image=simple_test_image,
            cpu=GlyphCPUv2(op_map, cols_instrs=8),
        )

        # Glyph 10: SHA-256. Runs the real Glyph ISA kernel on the input bytes
        # and returns the 32-byte digest. Single canonical entry point shared
        # with tools/sha256_lockstep_test.py.
        self.glyph_registry[GLYPH_ID_SHA256] = GlyphProgram(
            id=GLYPH_ID_SHA256,
            name="sha256",
            input_size=0,      # variable
            output_size=32,
            runner=sha256_glyph,
        )

        print(f"Loaded {len(self.glyph_registry)} built-in glyph kernels: "
              + ", ".join(g.name for g in self.glyph_registry.values()))

    def check_dispatch(self) -> bool:
        """
        Check if guest triggered a glyph dispatch.

        Returns:
            True if a dispatch was processed, False otherwise.
        """
        # The dispatch trigger is the BUSY bit in the request structure (set by
        # the guest, either directly or via the MMIO trigger write). A GPU CPU
        # state buffer, when present, is only an optimisation hint -- not
        # required for the host-side round trip.

        # Read request structure from shared RAM
        try:
            flags = self.ram.read_u32(REQUEST_STRUCT_BASE)
        except IndexError:
            # Request structure not accessible (out of bounds)
            return False

        # Check BUSY flag
        if (flags & FLAG_BUSY) == 0:
            return False  # No pending dispatch

        # Read request fields
        try:
            glyph_id = self.ram.read_u32(REQUEST_STRUCT_BASE + OFFSET_GLYPH_ID)
            input_buf_ptr = self.ram.read_u64(REQUEST_STRUCT_BASE + OFFSET_INPUT_BUF_PTR)
            input_buf_len = self.ram.read_u64(REQUEST_STRUCT_BASE + OFFSET_INPUT_BUF_LEN)
            output_buf_ptr = self.ram.read_u64(REQUEST_STRUCT_BASE + OFFSET_OUTPUT_BUF_PTR)
            output_buf_len = self.ram.read_u64(REQUEST_STRUCT_BASE + OFFSET_OUTPUT_BUF_LEN)
        except IndexError:
            # Request structure corrupted or incomplete
            self._mark_error(RESULT_ERROR)
            return True  # Processed (as error)

        # Validate glyph_id
        if glyph_id not in self.glyph_registry:
            print(f"[GLYPH] Unknown glyph_id: {glyph_id}")
            self._mark_error(RESULT_ERROR)
            return True

        # Load glyph program
        glyph = self.glyph_registry[glyph_id]

        # Read input data (if any)
        input_data = b""
        if input_buf_len > 0:
            try:
                input_data = self.ram.read_bytes(input_buf_ptr, input_buf_len)
            except IndexError:
                print(f"[GLYPH] Input buffer out of bounds: 0x{input_buf_ptr:x}")
                self._mark_error(RESULT_ERROR)
                return True

        # Execute glyph kernel
        try:
            output_data = self._run_glyph_program(glyph, input_data)
        except Exception as e:
            print(f"[GLYPH] Execution failed for glyph {glyph_id}: {e}")
            self._mark_error(RESULT_GLYPH_FAILED)
            return True

        # Write output data (if any)
        if output_buf_len > 0:
            if len(output_data) > output_buf_len:
                print(f"[GLYPH] Output buffer too small: {len(output_data)} > {output_buf_len}")
                self._mark_error(RESULT_OUTPUT_TOO_SMALL)
                return True

            try:
                self.ram.write_bytes(output_buf_ptr, output_data[:output_buf_len])
            except IndexError:
                print(f"[GLYPH] Output buffer out of bounds: 0x{output_buf_ptr:x}")
                self._mark_error(RESULT_ERROR)
                return True

        # Mark completion (success)
        self._mark_success()

        print(f"[GLYPH] Dispatch complete: glyph_id={glyph_id}, "
              f"input={input_buf_len} bytes, output={output_buf_len} bytes")

        return True

    def _run_glyph_program(self, glyph: 'GlyphProgram', input_data: bytes) -> bytes:
        """
        Execute a glyph program.

        Args:
            glyph: Glyph program to execute
            input_data: Input data bytes

        Returns:
            Output data bytes
        """
        if glyph.runner is not None:
            return glyph.runner(input_data)

        # Fallback: Phase-1 test-kernel path -- run cpu over image, collect PRT.
        glyph.cpu.run(glyph.image, max_instructions=1000)
        return bytes(glyph.cpu.output)

    def _mark_success(self):
        """Mark dispatch as successful."""
        # Clear BUSY flag
        flags = self.ram.read_u32(REQUEST_STRUCT_BASE)
        flags &= ~FLAG_BUSY
        self.ram.write_u32(REQUEST_STRUCT_BASE, flags)

        # Set result_status = success
        self.ram.write_u32(REQUEST_STRUCT_BASE + OFFSET_RESULT_STATUS, RESULT_SUCCESS)

    def _mark_error(self, result_status: int):
        """Mark dispatch as failed."""
        # Set ERROR flag
        flags = self.ram.read_u32(REQUEST_STRUCT_BASE)
        flags |= FLAG_ERROR
        flags &= ~FLAG_BUSY  # Also clear BUSY
        self.ram.write_u32(REQUEST_STRUCT_BASE, flags)

        # Set result_status (stored as u32; negative codes wrap, guest reads
        # them back as a signed word / checks bnez).
        self.ram.write_u32(REQUEST_STRUCT_BASE + OFFSET_RESULT_STATUS,
                           result_status & 0xFFFFFFFF)

    def clear_glyph_busy(self):
        """Clear glyph_busy flag in CPU state (when state buffer available)."""
        if self.state_buffer is None:
            return

        if self.glyph_busy_offset is None:
            print("[GLYPH] Warning: glyph_busy_offset not set, cannot clear flag")
            return

        # Read state, clear flag, write back
        state_bytes = self.state_buffer  # Assume this is a buffer we can modify
        state_arr = np.frombuffer(state_bytes, dtype=np.uint32)
        state_arr[self.glyph_busy_offset] = 0
        # Note: actual writeback depends on GPU buffer API


class GlyphProgram:
    """Represents a loaded glyph program.

    Two execution styles:
      * ``runner`` set  -> call ``runner(input_bytes) -> output_bytes``. Used by
        kernels that need input data marshalled in and a byte string back
        (e.g. SHA-256, which runs the Glyph ISA program on a fresh GlyphCPUv2).
      * ``runner`` None -> run ``cpu`` over ``image`` and return
        ``bytes(cpu.output)`` (the original Phase-1 test-kernel path).
    """

    def __init__(self, id: int, name: str,
                 image: Optional[np.ndarray] = None,
                 cpu: Optional[GlyphCPUv2] = None,
                 input_size: int = 0, output_size: int = 0,
                 runner: Optional[Callable[[bytes], bytes]] = None):
        self.id = id
        self.name = name
        self.image = image  # Pixel image (height, width, 3)
        self.cpu = cpu      # GlyphCPUv2 instance
        self.input_size = input_size
        self.output_size = output_size
        self.runner = runner


# Test harness (for standalone testing)
if __name__ == "__main__":
    print("=== Glyph Dispatcher Standalone Test ===")

    # Mock GpuRam for testing
    class MockGpuRam:
        def __init__(self):
            self.memory = bytearray(1024 * 1024)  # 1MB test memory

        def _check_bounds(self, gpa: int, length: int = 1):
            end = gpa + length
            if end > len(self.memory):
                raise IndexError(f"Access beyond RAM: [{gpa:x}, {end:x})")

        def read_u32(self, gpa: int) -> int:
            self._check_bounds(gpa, 4)
            return int.from_bytes(self.memory[gpa:gpa+4], 'little')

        def write_u32(self, gpa: int, val: int):
            self._check_bounds(gpa, 4)
            self.memory[gpa:gpa+4] = val.to_bytes(4, 'little')

        def read_u64(self, gpa: int) -> int:
            self._check_bounds(gpa, 8)
            return int.from_bytes(self.memory[gpa:gpa+8], 'little')

        def write_u64(self, gpa: int, val: int):
            self._check_bounds(gpa, 8)
            self.memory[gpa:gpa+8] = val.to_bytes(8, 'little')

        def read_bytes(self, gpa: int, length: int) -> bytes:
            self._check_bounds(gpa, length)
            return bytes(self.memory[gpa:gpa+length])

        def write_bytes(self, gpa: int, data: bytes):
            self._check_bounds(gpa, len(data))
            self.memory[gpa:gpa+len(data)] = data

    # Create mock RAM
    mock_ram = MockGpuRam()

    # Create dispatcher
    dispatcher = GlyphDispatcher(mock_ram)

    # Test 1: Submit dispatch request
    print("\nTest 1: Submit dispatch request")
    dispatcher.ram.write_u32(REQUEST_STRUCT_BASE + OFFSET_GLYPH_ID, GLYPH_ID_TEST_COUNTER)
    dispatcher.ram.write_u64(REQUEST_STRUCT_BASE + OFFSET_INPUT_BUF_PTR, 0x8100_2000)
    dispatcher.ram.write_u64(REQUEST_STRUCT_BASE + OFFSET_INPUT_BUF_LEN, 0)
    dispatcher.ram.write_u64(REQUEST_STRUCT_BASE + OFFSET_OUTPUT_BUF_PTR, 0x8100_3000)
    dispatcher.ram.write_u64(REQUEST_STRUCT_BASE + OFFSET_OUTPUT_BUF_LEN, 0)

    # Set BUSY flag
    flags = FLAG_BUSY
    dispatcher.ram.write_u32(REQUEST_STRUCT_BASE, flags)

    # Check dispatch
    result = dispatcher.check_dispatch()
    print(f"Dispatch processed: {result}")

    # Verify result
    result_flags = dispatcher.ram.read_u32(REQUEST_STRUCT_BASE)
    result_status = dispatcher.ram.read_u32(REQUEST_STRUCT_BASE + OFFSET_RESULT_STATUS)

    print(f"Flags: 0x{result_flags:08x} (BUSY={result_flags & FLAG_BUSY != 0}, ERROR={result_flags & FLAG_ERROR != 0})")
    print(f"Result status: {result_status}")

    assert (result_flags & FLAG_BUSY) == 0, "BUSY flag should be cleared"
    assert result_status == RESULT_SUCCESS, "Result status should be success"

    print("\n✅ All tests passed!")