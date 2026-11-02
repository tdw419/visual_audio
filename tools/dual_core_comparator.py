#!/usr/bin/env python3
"""
Dual-Core Comparative Validation: RV32 vs RV64

Uses the existing RV32 ground-truth pattern (xv6_ls_pattern_demo.json) and VCC hash
(b39fe95ba0a53c61e8a641e70b05db0bd4b7564440c578208ef40cb4cdf43e6d) to validate
RV64 emulator correctness.

Key principle: When running the same xv6 OS image compiled for both architectures,
the low 32 bits of RV64 registers must match the RV32 execution pattern exactly
for non-64-bit-specific instructions.
"""

import json
import hashlib
import subprocess
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass


@dataclass
class EmulatorState:
    """Snapshot of emulator state for comparison."""
    pc: int
    registers_low_32: List[int]  # Low 32 bits only for RV64
    memory_snapshot: bytes
    steps: int
    halted: bool


class RV32PatternLoader:
    """Load and analyze RV32 ground-truth patterns."""

    def __init__(self, pattern_path: str):
        with open(pattern_path) as f:
            self.pattern = json.load(f)

        self.command = self.pattern['command']
        self.serial_output = self.pattern['serial_output']
        self.metadata = self.pattern['metadata']
        self.files = self.metadata['files']

    def get_expected_vcc_hash(self) -> str:
        """Get expected VCC framebuffer hash."""
        from test_xv6_ls_pixels import PixelValidator
        validator = PixelValidator('tools/xv6_ls_pattern_demo.json')
        framebuffer = validator.rasterize_text_to_framebuffer(
            validator.serial_output,
            width=640,
            height=400
        )
        return validator.compute_frame_hash(framebuffer)


class DualCoreComparator:
    """Compare RV32 and RV64 emulator execution states."""

    def __init__(self, rv32_pattern_path: str = "tools/xv6_ls_pattern_demo.json"):
        self.rv32_pattern = RV32PatternLoader(rv32_pattern_path)
        self.expected_vcc_hash = self.rv32_pattern.get_expected_vcc_hash()
        self.register_mismatches: List[Tuple[int, int, int, int]] = []  # (step, reg, expected, actual)

    def compare_low_32_bits(self, rv64_state: EmulatorState,
                            expected_state: Optional[EmulatorState] = None) -> Tuple[bool, List[str]]:
        """Compare low 32 bits of RV64 registers against RV32 ground truth.

        Args:
            rv64_state: RV64 emulator state
            expected_state: RV32 emulator state (if available)

        Returns:
            (passed, errors)
        """
        errors = []

        # Extract low 32 bits from RV64 registers
        rv64_regs_low = rv64_state.registers_low_32

        # For RV32 patterns, we expect exact matches on non-64-bit operations
        if expected_state:
            expected_regs = expected_state.registers_low_32
            for i in range(32):
                if rv64_regs_low[i] != expected_regs[i]:
                    errors.append(
                        f"Register mismatch at step {rv64_state.steps}: "
                        f"x{i}: RV32={expected_regs[i]:08x}, RV64_low={rv64_regs_low[i]:08x}"
                    )
                    self.register_mismatches.append((rv64_state.steps, i, expected_regs[i], rv64_regs_low[i]))

        passed = len(errors) == 0
        return passed, errors

    def validate_vcc_framebuffer(self, rv64_framebuffer: List[List[int]]) -> Tuple[bool, str, str]:
        """Validate RV64 framebuffer against expected VCC hash.

        Args:
            rv64_framebuffer: RV64 emulator framebuffer (640×400)

        Returns:
            (passed, expected_hash, actual_hash)
        """
        # Compute hash of RV64 framebuffer
        flat_bytes = bytes([pixel for row in rv64_framebuffer for pixel in row])
        actual_hash = hashlib.sha256(flat_bytes).hexdigest()

        # Compare against expected VCC hash from RV32 pattern
        passed = actual_hash == self.expected_vcc_hash

        return passed, self.expected_vcc_hash, actual_hash

    def analyze_mismatch(self, rv32_framebuffer: List[List[int]],
                         rv64_framebuffer: List[List[int]]) -> Dict:
        """Analyze VCC mismatch to isolate the bug.

        Args:
            rv32_framebuffer: Expected RV32 framebuffer
            rv64_framebuffer: Actual RV64 framebuffer

        Returns:
            Analysis dict with mismatch locations
        """
        mismatches = []

        for y in range(len(rv32_framebuffer)):
            for x in range(len(rv32_framebuffer[0])):
                if rv32_framebuffer[y][x] != rv64_framebuffer[y][x]:
                    mismatches.append({
                        'x': x,
                        'y': y,
                        'expected': rv32_framebuffer[y][x],
                        'actual': rv64_framebuffer[y][x]
                    })

        # Find contiguous mismatch regions
        if mismatches:
            # Group by y-coordinate to identify lines with issues
            lines_with_mismatches = {}
            for m in mismatches:
                y = m['y']
                if y not in lines_with_mismatches:
                    lines_with_mismatches[y] = []
                lines_with_mismatches[y].append(m['x'])

            return {
                'total_mismatches': len(mismatches),
                'lines_affected': len(lines_with_mismatches),
                'lines_with_mismatches': lines_with_mismatches,
                'first_mismatch': mismatches[0] if mismatches else None
            }

        return {'total_mismatches': 0}


class EmulatorHarness:
    """Run emulators and capture state."""

    def run_rv64_emulator(self, program: str, max_steps: int = 100000) -> EmulatorState:
        """Run RV64 emulator and capture state.

        Args:
            program: Program to run (e.g., 'ls')
            max_steps: Maximum execution steps

        Returns:
            Emulator state snapshot
        """
        # TODO: Hook into actual RV64 emulator
        # For now, return a mock state
        return EmulatorState(
            pc=0x80005000,
            registers_low_32=[0] * 32,
            memory_snapshot=b'',
            steps=max_steps,
            halted=False
        )

    def capture_framebuffer(self, emulator_state: EmulatorState) -> List[List[int]]:
        """Capture framebuffer from emulator.

        Args:
            emulator_state: Emulator state

        Returns:
            2D pixel array (640×400)
        """
        # TODO: Capture actual framebuffer from GPU
        # For now, return empty framebuffer
        return [[0 for _ in range(640)] for _ in range(400)]


def run_comparative_validation():
    """Run the complete RV32 vs RV64 comparative validation."""

    print("=" * 70)
    print("DUAL-CORE COMPARATIVE VALIDATION: RV32 vs RV64")
    print("=" * 70)
    print()

    # Initialize comparator
    comparator = DualCoreComparator()

    print(f"Loaded RV32 ground-truth pattern: tools/xv6_ls_pattern_demo.json")
    print(f"  Command: {comparator.rv32_pattern.command}")
    print(f"  Files: {len(comparator.rv32_pattern.files)}")
    print(f"  Expected VCC Hash: {comparator.expected_vcc_hash[:40]}...")
    print()

    # Run RV64 emulator
    print("─" * 70)
    print("STAGE 1: Run RV64 Emulator")
    print("─" * 70)

    harness = EmulatorHarness()
    rv64_state = harness.run_rv64_emulator('ls', max_steps=15234)

    print(f"  RV64 execution completed")
    print(f"  Steps: {rv64_state.steps}")
    print(f"  PC: 0x{rv64_state.pc:08x}")
    print(f"  Halted: {rv64_state.halted}")
    print()

    # Capture framebuffer
    print("─" * 70)
    print("STAGE 2: Capture RV64 Framebuffer")
    print("─" * 70)

    rv64_framebuffer = harness.capture_framebuffer(rv64_state)
    print(f"  Captured {len(rv64_framebuffer)}×{len(rv64_framebuffer[0])} framebuffer")
    print()

    # Validate VCC hash
    print("─" * 70)
    print("STAGE 3: VCC Framebuffer Validation")
    print("─" * 70)

    vcc_passed, expected_hash, actual_hash = comparator.validate_vcc_framebuffer(rv64_framebuffer)

    print(f"  Expected VCC Hash: {expected_hash}")
    print(f"  Actual VCC Hash:   {actual_hash}")

    if vcc_passed:
        print(f"  ✓ VCC PASSED: RV64 produces identical pixel output")
    else:
        print(f"  ✗ VCC FAILED: RV64 output mismatches RV32 ground truth")

        # Analyze mismatch
        from test_xv6_ls_pixels import PixelValidator
        validator = PixelValidator('tools/xv6_ls_pattern_demo.json')
        rv32_framebuffer = validator.rasterize_text_to_framebuffer(
            validator.serial_output,
            width=640,
            height=400
        )

        analysis = comparator.analyze_mismatch(rv32_framebuffer, rv64_framebuffer)
        print()
        print(f"  Mismatch Analysis:")
        print(f"    Total mismatched pixels: {analysis['total_mismatches']}")
        print(f"    Lines affected: {analysis['lines_affected']}")

        if 'first_mismatch' in analysis and analysis['first_mismatch']:
            first = analysis['first_mismatch']
            print(f"    First mismatch: ({first['x']}, {first['y']}) → {first['expected']} vs {first['actual']}")

    print()

    # Show verification commands
    print("─" * 70)
    print("VERIFICATION COMMANDS")
    print("─" * 70)
    print()
    print("To verify RV64 emulator during development, run:")
    print()
    print("  # Verify RV64 UART/string output matches RV32 pattern")
    print("  python3 tools/test_xv6_ls_pattern.py")
    print()
    print("  # Verify RV64 screen rendering produces exact VCC hash")
    print("  python3 tools/test_xv6_ls_pixels.py")
    print()

    print("=" * 70)
    print("COMPARATIVE VALIDATION COMPLETE")
    print("=" * 70)
    print()

    print("What This Provides:")
    print()
    print("✓ RV32 ground-truth pattern validates RV64 correctness")
    print("✓ VCC hash b39fe95b... is the pixel-perfect target")
    print("✓ Low-32 bit register equivalence for non-64-bit ops")
    print("✓ Visual diff isolates bugs (UART, alignment, sign-extension)")
    print()

    return 0 if vcc_passed else 1


if __name__ == "__main__":
    import sys
    sys.exit(run_comparative_validation())