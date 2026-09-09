#!/usr/bin/env python3
"""
Glyph Dispatch Test Suite

Tests the dispatcher in isolation from the full RISC-V emulator.
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "tools"))  # For glyph_isa_v2 import

# Add src to path
src_path = project_root / "src"
sys.path.insert(0, str(src_path))

from dispatch.dispatcher import GlyphDispatcher, GlyphProgram
from glyph.glyph_isa_v2 import OpcodeMapV2, GlyphAssemblerV2, GlyphCPUv2
from dispatch.request_struct import (
    REQUEST_STRUCT_BASE,
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
    GLYPH_ID_TEST_COUNTER,
)


class MockGpuRam:
    """Mock GpuRam for testing without GPU."""

    def __init__(self, size_mb=1, ram_base=0x80000000):
        self.ram_base = ram_base
        self.size = size_mb * 1024 * 1024
        self.memory = bytearray(self.size)

    def _check_bounds(self, gpa: int, length: int = 1):
        if gpa < self.ram_base:
            raise IndexError(f"Access below RAM base: 0x{gpa:x} < 0x{self.ram_base:x}")
        end = gpa + length
        limit = self.ram_base + self.size
        if end > limit:
            raise IndexError(f"Access beyond RAM: [0x{gpa:x}, 0x{end:x}) limit=0x{limit:x}")

    def read_u32(self, gpa: int) -> int:
        self._check_bounds(gpa, 4)
        offset = gpa - self.ram_base
        return int.from_bytes(self.memory[offset:offset+4], 'little')

    def write_u32(self, gpa: int, val: int):
        self._check_bounds(gpa, 4)
        offset = gpa - self.ram_base
        self.memory[offset:offset+4] = val.to_bytes(4, 'little')

    def read_u64(self, gpa: int) -> int:
        self._check_bounds(gpa, 8)
        offset = gpa - self.ram_base
        return int.from_bytes(self.memory[offset:offset+8], 'little')

    def write_u64(self, gpa: int, val: int):
        self._check_bounds(gpa, 8)
        offset = gpa - self.ram_base
        self.memory[offset:offset+8] = val.to_bytes(8, 'little')

    def read_bytes(self, gpa: int, length: int) -> bytes:
        self._check_bounds(gpa, length)
        offset = gpa - self.ram_base
        return bytes(self.memory[offset:offset+length])

    def write_bytes(self, gpa: int, data: bytes):
        self._check_bounds(gpa, len(data))
        offset = gpa - self.ram_base
        self.memory[offset:offset+len(data)] = data


def test_basic_dispatch():
    """Test basic dispatch cycle: guest submit → host execute → guest poll."""
    print("\n=== Test 1: Basic Dispatch Cycle ===")

    # Create mock RAM with base at 0x80000000 and sufficient size
    # Request structure at 0x81001000 requires RAM from 0x80000000-0x81004000+
    ram = MockGpuRam(size_mb=32, ram_base=0x80000000)

    # Create dispatcher with dummy state buffer
    # Phase 1 tests don't need state_buffer but dispatcher requires it
    dummy_state_buffer = bytearray(4096)
    dispatcher = GlyphDispatcher(ram, state_buffer=dummy_state_buffer)

    # Guest: submit request
    print("Guest submitting request...")
    ram.write_u32(REQUEST_STRUCT_BASE + OFFSET_GLYPH_ID, GLYPH_ID_TEST_COUNTER)
    ram.write_u64(REQUEST_STRUCT_BASE + OFFSET_INPUT_BUF_PTR, 0x8100_2000)
    ram.write_u64(REQUEST_STRUCT_BASE + OFFSET_INPUT_BUF_LEN, 0)
    ram.write_u64(REQUEST_STRUCT_BASE + OFFSET_OUTPUT_BUF_PTR, 0x8100_3000)
    ram.write_u64(REQUEST_STRUCT_BASE + OFFSET_OUTPUT_BUF_LEN, 0)

    # Set BUSY flag
    ram.write_u32(REQUEST_STRUCT_BASE, FLAG_BUSY)
    print(f"  Flags after submit: 0x{ram.read_u32(REQUEST_STRUCT_BASE):08x}")

    # Host: check dispatch
    print("Host checking dispatch...")
    result = dispatcher.check_dispatch()
    print(f"  Dispatch processed: {result}")

    # Verify completion
    result_flags = ram.read_u32(REQUEST_STRUCT_BASE)
    result_status = ram.read_u32(REQUEST_STRUCT_BASE + OFFSET_RESULT_STATUS)
    if result_status >= 0x80000000:
        result_status -= 0x100000000

    print(f"  Flags after dispatch: 0x{result_flags:08x}")
    print(f"  Result status: {result_status}")
    print(f"  BUSY cleared: {(result_flags & FLAG_BUSY) == 0}")
    print(f"  No error: {(result_flags & FLAG_ERROR) == 0}")
    print(f"  Status success: {result_status == RESULT_SUCCESS}")

    assert result == True, "Dispatch should be processed"
    assert (result_flags & FLAG_BUSY) == 0, "BUSY flag should be cleared"
    assert (result_flags & FLAG_ERROR) == 0, "ERROR flag should not be set"
    assert result_status == RESULT_SUCCESS, "Result status should be success"

    print("✅ Test 1 passed!")


def test_invalid_glyph_id():
    """Test error handling for invalid glyph_id."""
    print("\n=== Test 2: Invalid Glyph ID ===")

    ram = MockGpuRam(size_mb=32, ram_base=0x80000000)
    dummy_state_buffer = bytearray(4096)
    dispatcher = GlyphDispatcher(ram, state_buffer=dummy_state_buffer)

    # Submit request with invalid glyph_id
    ram.write_u32(REQUEST_STRUCT_BASE + OFFSET_GLYPH_ID, 0xDEADBEEF)  # Invalid
    ram.write_u64(REQUEST_STRUCT_BASE + OFFSET_INPUT_BUF_PTR, 0x8100_2000)
    ram.write_u64(REQUEST_STRUCT_BASE + OFFSET_INPUT_BUF_LEN, 0)
    ram.write_u64(REQUEST_STRUCT_BASE + OFFSET_OUTPUT_BUF_PTR, 0x8100_3000)
    ram.write_u64(REQUEST_STRUCT_BASE + OFFSET_OUTPUT_BUF_LEN, 0)
    ram.write_u32(REQUEST_STRUCT_BASE, FLAG_BUSY)

    # Process dispatch
    result = dispatcher.check_dispatch()

    # Verify error handling
    result_flags = ram.read_u32(REQUEST_STRUCT_BASE)
    result_status = ram.read_u32(REQUEST_STRUCT_BASE + OFFSET_RESULT_STATUS)
    if result_status >= 0x80000000:
        result_status -= 0x100000000

    print(f"  Dispatch processed: {result}")
    print(f"  Flags: 0x{result_flags:08x} (ERROR={result_flags & FLAG_ERROR != 0})")
    print(f"  Result status: {result_status}")

    assert result == True, "Dispatch should be processed (as error)"
    assert (result_flags & FLAG_ERROR) != 0, "ERROR flag should be set"
    assert result_status == RESULT_ERROR, "Result status should be error"

    print("✅ Test 2 passed!")


def test_buffer_out_of_bounds():
    """Test error handling for out-of-bounds buffer access."""
    print("\n=== Test 3: Buffer Out of Bounds ===")

    ram = MockGpuRam(size_mb=32, ram_base=0x80000000)
    dummy_state_buffer = bytearray(4096)
    dispatcher = GlyphDispatcher(ram, state_buffer=dummy_state_buffer)

    # Submit request with input buffer beyond RAM
    # RAM range: 0x80000000-0x82000000 (32MB)
    # Use address beyond 32MB
    ram.write_u32(REQUEST_STRUCT_BASE + OFFSET_GLYPH_ID, GLYPH_ID_TEST_COUNTER)
    ram.write_u64(REQUEST_STRUCT_BASE + OFFSET_INPUT_BUF_PTR, 0x83000000)  # Beyond 32MB
    ram.write_u64(REQUEST_STRUCT_BASE + OFFSET_INPUT_BUF_LEN, 1024)
    ram.write_u64(REQUEST_STRUCT_BASE + OFFSET_OUTPUT_BUF_PTR, 0x8100_3000)
    ram.write_u64(REQUEST_STRUCT_BASE + OFFSET_OUTPUT_BUF_LEN, 0)
    ram.write_u32(REQUEST_STRUCT_BASE, FLAG_BUSY)

    # Process dispatch
    result = dispatcher.check_dispatch()

    # Verify error handling
    result_flags = ram.read_u32(REQUEST_STRUCT_BASE)
    result_status = ram.read_u32(REQUEST_STRUCT_BASE + OFFSET_RESULT_STATUS)
    if result_status >= 0x80000000:
        result_status -= 0x100000000

    print(f"  Dispatch processed: {result}")
    print(f"  Flags: 0x{result_flags:08x} (ERROR={result_flags & FLAG_ERROR != 0})")
    print(f"  Result status: {result_status}")

    assert result == True, "Dispatch should be processed (as error)"
    assert (result_flags & FLAG_ERROR) != 0, "ERROR flag should be set"
    assert result_status == RESULT_ERROR, "Result status should be error"

    print("✅ Test 3 passed!")


def test_no_busy_flag():
    """Test that dispatch is ignored if BUSY flag not set."""
    print("\n=== Test 4: No BUSY Flag ===")

    ram = MockGpuRam(size_mb=32, ram_base=0x80000000)
    dummy_state_buffer = bytearray(4096)
    dispatcher = GlyphDispatcher(ram, state_buffer=dummy_state_buffer)

    # Submit request WITHOUT setting BUSY flag
    ram.write_u32(REQUEST_STRUCT_BASE + OFFSET_GLYPH_ID, GLYPH_ID_TEST_COUNTER)
    ram.write_u64(REQUEST_STRUCT_BASE + OFFSET_INPUT_BUF_PTR, 0x8100_2000)
    ram.write_u64(REQUEST_STRUCT_BASE + OFFSET_INPUT_BUF_LEN, 0)
    ram.write_u64(REQUEST_STRUCT_BASE + OFFSET_OUTPUT_BUF_PTR, 0x8100_3000)
    ram.write_u64(REQUEST_STRUCT_BASE + OFFSET_OUTPUT_BUF_LEN, 0)
    # Don't set BUSY flag

    # Process dispatch
    result = dispatcher.check_dispatch()

    print(f"  Dispatch processed: {result}")

    assert result == False, "Dispatch should NOT be processed"

    print("✅ Test 4 passed!")


def test_glyph_output():
    """Test that glyph program output is captured correctly."""
    print("\n=== Test 5: Glyph Output Capture ===")

    ram = MockGpuRam(size_mb=32, ram_base=0x80000000)

    # Create a custom glyph that outputs a known value
    op_map = OpcodeMapV2()
    assembler = GlyphAssemblerV2(op_map)

    # Simple program: LDI r1 123; PRT r1; HALT
    program = ["LDI r1 123", "PRT r1", "HALT"]
    image = assembler.assemble(program, width_instrs=8)
    cpu = GlyphCPUv2(op_map, cols_instrs=8)

    # Register custom glyph
    custom_glyph = GlyphProgram(
        id=GLYPH_ID_TEST_COUNTER,
        name="custom_test",
        image=image,
        cpu=cpu,
        input_size=0,
        output_size=0,
    )

    dispatcher = GlyphDispatcher(ram)
    dispatcher.glyph_registry[GLYPH_ID_TEST_COUNTER] = custom_glyph

    # Submit request
    ram.write_u32(REQUEST_STRUCT_BASE + OFFSET_GLYPH_ID, GLYPH_ID_TEST_COUNTER)
    ram.write_u64(REQUEST_STRUCT_BASE + OFFSET_INPUT_BUF_PTR, 0x8100_2000)
    ram.write_u64(REQUEST_STRUCT_BASE + OFFSET_INPUT_BUF_LEN, 0)
    ram.write_u64(REQUEST_STRUCT_BASE + OFFSET_OUTPUT_BUF_PTR, 0x8100_3000)
    ram.write_u64(REQUEST_STRUCT_BASE + OFFSET_OUTPUT_BUF_LEN, 0)
    ram.write_u32(REQUEST_STRUCT_BASE, FLAG_BUSY)

    # Process dispatch
    result = dispatcher.check_dispatch()

    # Verify glyph executed
    output = custom_glyph.cpu.output
    print(f"  Glyph output: {output}")
    print(f"  Expected: [123]")

    assert result == True, "Dispatch should be processed"
    assert output == [123], f"Glyph output should be [123], got {output}"

    print("✅ Test 5 passed!")


def main():
    """Run all tests."""
    print("=" * 60)
    print("Glyph Dispatch Test Suite")
    print("=" * 60)

    test_basic_dispatch()
    test_invalid_glyph_id()
    test_buffer_out_of_bounds()
    test_no_busy_flag()
    test_glyph_output()

    print("\n" + "=" * 60)
    print("ALL TESTS PASSED ✅")
    print("=" * 60)


if __name__ == "__main__":
    main()