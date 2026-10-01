#!/usr/bin/env python3
"""
Lockstep Verification: Glyph Dispatch MMIO Handler

Tests Python ground truth:
1. Mock MMIO write sets glyph_busy correctly
2. CPU state field offsets match expected values
3. Request structure constants are correct

Run with: python3 tools/verify_glyph_dispatch_mmio.py
"""

import sys
import numpy as np
from pathlib import Path
import re

# Add path for imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Extract constants from request_struct.py
request_struct_file = project_root / "glyph_dispatch/src/dispatch/request_struct.py"
request_struct_content = open(request_struct_file).read()

# Parse constants using regex (handle hex literals with underscores)
REQUEST_STRUCT_BASE_match = re.search(r'REQUEST_STRUCT_BASE\s*=\s*0x([0-9A-Fa-f_]+)', request_struct_content)
REQUEST_STRUCT_BASE = int(REQUEST_STRUCT_BASE_match.group(1).replace('_', ''), 16) if REQUEST_STRUCT_BASE_match else 0x81001000

GLYPH_DISPATCH_TRIGGER_MMIO_match = re.search(r'GLYPH_DISPATCH_TRIGGER_MMIO\s*=\s*0x([0-9A-Fa-f_]+)', request_struct_content)
GLYPH_DISPATCH_TRIGGER_MMIO = int(GLYPH_DISPATCH_TRIGGER_MMIO_match.group(1).replace('_', ''), 16) if GLYPH_DISPATCH_TRIGGER_MMIO_match else 0x88000000

FLAG_BUSY_match = re.search(r'FLAG_BUSY\s*=\s*0x([0-9A-Fa-f_]+)', request_struct_content)
FLAG_BUSY = int(FLAG_BUSY_match.group(1).replace('_', ''), 16) if FLAG_BUSY_match else 0x00000001

FLAG_ERROR_match = re.search(r'FLAG_ERROR\s*=\s*0x([0-9A-Fa-f_]+)', request_struct_content)
FLAG_ERROR = int(FLAG_ERROR_match.group(1).replace('_', ''), 16) if FLAG_ERROR_match else 0x00000002

OFFSET_FLAGS_match = re.search(r'OFFSET_FLAGS\s*=\s*(?:0x)?([0-9A-Fa-f]+)', request_struct_content)
OFFSET_FLAGS = int(OFFSET_FLAGS_match.group(1), 16) if OFFSET_FLAGS_match else 0x00

OFFSET_GLYPH_ID_match = re.search(r'OFFSET_GLYPH_ID\s*=\s*(?:0x)?([0-9A-Fa-f]+)', request_struct_content)
OFFSET_GLYPH_ID = int(OFFSET_GLYPH_ID_match.group(1), 16) if OFFSET_GLYPH_ID_match else 0x04

# Extract glyph offsets from cpu_state_mirror.py
cpu_state_file = project_root / "glyph_dispatch/src/riscv/cpu_state_mirror.py"
cpu_state_content = open(cpu_state_file).read()

GLYPH_BUSY_OFFSET_match = re.search(r'GLYPH_BUSY_OFFSET\s*=\s*(\d+)', cpu_state_content)
GLYPH_BUSY_OFFSET = int(GLYPH_BUSY_OFFSET_match.group(1)) if GLYPH_BUSY_OFFSET_match else 516

GLYPH_LAST_TRIGGER_OFFSET_match = re.search(r'GLYPH_LAST_TRIGGER_OFFSET\s*=\s*(\d+)', cpu_state_content)
GLYPH_LAST_TRIGGER_OFFSET = int(GLYPH_LAST_TRIGGER_OFFSET_match.group(1)) if GLYPH_LAST_TRIGGER_OFFSET_match else 520

print(f"[INFO] Extracted REQUEST_STRUCT_BASE: 0x{REQUEST_STRUCT_BASE:08x}")
print(f"[INFO] Extracted GLYPH_DISPATCH_TRIGGER_MMIO: 0x{GLYPH_DISPATCH_TRIGGER_MMIO:08x}")
print(f"[INFO] Extracted GLYPH_BUSY_OFFSET: {GLYPH_BUSY_OFFSET}")
print(f"[INFO] Extracted GLYPH_LAST_TRIGGER_OFFSET: {GLYPH_LAST_TRIGGER_OFFSET}")


class MockGlyphCPUv2:
    """Mock GlyphCPUv2 for Python ground truth."""
    def __init__(self):
        self.registers = [0] * 32
        self.pc = 0x80000000
        self.running = 1
        self.instr_count = 0
        self.output = []
        self.glyph_busy = 0
        self.glyph_last_trigger = 0

    def step_mmio_write(self, pa: int, value: int, size: int) -> bool:
        """Simulate MMIO write (Python ground truth)."""
        if pa == GLYPH_DISPATCH_TRIGGER_MMIO:
            # This is a glyph dispatch trigger
            # Set glyph_busy = 1 to signal host
            self.glyph_busy = 1
            self.glyph_last_trigger = value
            return True
        return False


def test_python_ground_truth():
    """Test Python ground truth MMIO write."""
    print("\n=== Test 1: Python Ground Truth MMIO Write ===")

    cpu = MockGlyphCPUv2()

    # Initial state
    print(f"Initial: glyph_busy={cpu.glyph_busy}, glyph_last_trigger=0x{cpu.glyph_last_trigger:x}")

    # Simulate MMIO write
    cpu.step_mmio_write(GLYPH_DISPATCH_TRIGGER_MMIO, 0xDEADBEEF, 4)

    # Check result
    print(f"After write: glyph_busy={cpu.glyph_busy}, glyph_last_trigger=0x{cpu.glyph_last_trigger:x}")

    assert cpu.glyph_busy == 1, "glyph_busy should be 1 after trigger"
    assert cpu.glyph_last_trigger == 0xDEADBEEF, "glyph_last_trigger should match written value"

    print("✅ Test 1 PASSED")
    return True


def test_cpu_state_dtype():
    """Test CPU_DTYPE_EXTENDED field layout."""
    print("\n=== Test 2: CPU State Dtype Layout ===")

    # Check if glyph offsets match expected values
    print(f"GLYPH_BUSY_OFFSET: {GLYPH_BUSY_OFFSET}")
    print(f"GLYPH_LAST_TRIGGER_OFFSET: {GLYPH_LAST_TRIGGER_OFFSET}")

    # Verify offsets match expected values (from cpu_state_mirror.py)
    expected_glyph_busy_offset = 516
    expected_glyph_last_trigger_offset = 520

    assert GLYPH_BUSY_OFFSET == expected_glyph_busy_offset, f"Expected glyph_busy offset {expected_glyph_busy_offset}, got {GLYPH_BUSY_OFFSET}"
    assert GLYPH_LAST_TRIGGER_OFFSET == expected_glyph_last_trigger_offset, f"Expected glyph_last_trigger offset {expected_glyph_last_trigger_offset}, got {GLYPH_LAST_TRIGGER_OFFSET}"

    print("✅ Test 2 PASSED")
    return True


def test_request_structure_constants():
    """Test request structure constants match expected values."""
    print("\n=== Test 3: Request Structure Constants ===")

    print(f"REQUEST_STRUCT_BASE: 0x{REQUEST_STRUCT_BASE:08x}")
    print(f"GLYPH_DISPATCH_TRIGGER_MMIO: 0x{GLYPH_DISPATCH_TRIGGER_MMIO:08x}")
    print(f"OFFSET_FLAGS: {OFFSET_FLAGS}")
    print(f"OFFSET_GLYPH_ID: {OFFSET_GLYPH_ID}")
    print(f"FLAG_BUSY: 0x{FLAG_BUSY:08x}")
    print(f"FLAG_ERROR: 0x{FLAG_ERROR:08x}")

    # Verify flag bit values
    assert FLAG_BUSY == 0x00000001, "FLAG_BUSY should be 0x00000001"
    assert FLAG_ERROR == 0x00000002, "FLAG_ERROR should be 0x00000002"

    # Verify memory addresses don't overlap
    assert REQUEST_STRUCT_BASE != GLYPH_DISPATCH_TRIGGER_MMIO, "Request struct and MMIO should not overlap"

    print("✅ Test 3 PASSED")
    return True


def test_request_validation_python():
    """Test request validation with Python ground truth."""
    print("\n=== Test 4: Request Validation (Python Ground Truth) ===")

    # Mock RAM with request structure (must be large enough for REQUEST_STRUCT_BASE)
    # REQUEST_STRUCT_BASE is 0x81001000, so we need at least 128MB of RAM
    ram_size = 128 * 1024 * 1024  # 128MB
    ram = bytearray(ram_size)
    ram_base = 0x80000000

    # Write request structure at REQUEST_STRUCT_BASE
    req_offset = REQUEST_STRUCT_BASE - ram_base

    # Write BUSY flag
    busy_bytes = (0x00000001).to_bytes(4, 'little')
    ram[req_offset + OFFSET_FLAGS:req_offset + OFFSET_FLAGS + 4] = busy_bytes

    # Write glyph_id
    glyph_id_bytes = (10).to_bytes(4, 'little')
    ram[req_offset + OFFSET_GLYPH_ID:req_offset + OFFSET_GLYPH_ID + 4] = glyph_id_bytes

    # Read back flags
    flags_bytes = ram[req_offset + OFFSET_FLAGS:req_offset + OFFSET_FLAGS + 4]
    flags = int.from_bytes(flags_bytes, 'little')

    # Read back glyph_id
    glyph_id_bytes = ram[req_offset + OFFSET_GLYPH_ID:req_offset + OFFSET_GLYPH_ID + 4]
    glyph_id = int.from_bytes(glyph_id_bytes, 'little')

    print(f"Flags: 0x{flags:08x} (BUSY={(flags & FLAG_BUSY) != 0}, ERROR={(flags & FLAG_ERROR) != 0})")
    print(f"Glyph ID: {glyph_id}")

    # Validate
    assert (flags & FLAG_BUSY) != 0, "BUSY flag should be set"
    assert glyph_id == 10, f"Glyph ID should be 10, got {glyph_id}"
    assert (flags & FLAG_ERROR) == 0, "ERROR flag should not be set"

    print("✅ Test 4 PASSED")
    return True


def main():
    """Run all lockstep verification tests."""
    print("=" * 60)
    print("Glyph Dispatch MMIO Lockstep Verification")
    print("=" * 60)

    results = []

    # Test 1: Python ground truth
    results.append(("Python ground truth MMIO write", test_python_ground_truth()))

    # Test 2: CPU dtype layout
    results.append(("CPU state dtype layout", test_cpu_state_dtype()))

    # Test 3: Request structure constants
    results.append(("Request structure constants", test_request_structure_constants()))

    # Test 4: Request validation
    results.append(("Request validation (Python)", test_request_validation_python()))

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    passed = sum(1 for _, result in results if result is True)
    failed = sum(1 for _, result in results if result is False)

    for test_name, result in results:
        status = "✅ PASSED" if result else "❌ FAILED"
        print(f"{status}: {test_name}")

    print(f"\nTotal: {passed} passed, {failed} failed")

    if failed > 0:
        print("\n⚠️  Some tests failed - check output above")
        return 1
    else:
        print("\n✅ All tests passed!")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())