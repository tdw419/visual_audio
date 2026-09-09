#!/usr/bin/env python3
"""
Pixel Pattern Learning Tool

Uses the working RV32 emulator to capture pixel execution patterns,
then applies those patterns to guide RV64 emulator development.

Workflow:
1. Run RV32 code on GPU emulator
2. Capture pixel patterns from execution
3. Label patterns with semantic meaning
4. Build pattern library for RV64 development
"""

import json
from pathlib import Path
from collections import defaultdict
import sys

sys.path.append(str(Path(__file__).parent))
from spatial_rv32i_cpu import SpatialRV32ICore


class PixelPatternCapture:
    """Captures and stores pixel patterns from RV32 execution."""
    
    def __init__(self, pattern_db_path: Path | None = None):
        self.pattern_db_path = pattern_db_path or Path(__file__).parent / "pixel_patterns.json"
        self.patterns = self._load_patterns()
        self.session_patterns = defaultdict(list)
        
    def _load_patterns(self):
        if self.pattern_db_path.exists():
            with open(self.pattern_db_path) as f:
                return json.load(f)
        return {}
    
    def _save_patterns(self):
        with open(self.pattern_db_path, 'w') as f:
            json.dump(self.patterns, f, indent=2)
    
    def capture_instruction_pattern(self, core, instruction_bytes: str, 
                                     label: str, description: str = ""):
        """
        Execute a single instruction and capture the pixel pattern it creates.
        
        Args:
            core: SpatialRV32ICore instance
            instruction_bytes: 4-byte hex string (e.g., "00308533" for ADD)
            label: Semantic label (e.g., "ADD r0, r0, r1")
            description: Optional description
        """
        # Get initial state
        initial_regs = core.get_state()['regs']
        
        # Execute one instruction
        core.step(steps=1)
        
        # Get final state
        final_state = core.get_state()
        final_regs = final_state['regs']
        
        # Capture pattern
        pattern = {
            'instruction_hex': instruction_bytes,
            'label': label,
            'description': description,
            'registers_before': initial_regs,
            'registers_after': final_regs,
            'pc_before': final_state['pc'] - 4,
            'pc_after': final_state['pc'],
            'flag_changes': self._compute_flag_changes(initial_regs, final_regs)
        }
        
        # Store pattern
        if instruction_bytes not in self.patterns:
            self.patterns[instruction_bytes] = []
        self.patterns[instruction_bytes].append(pattern)
        self.session_patterns[label].append(pattern)
        
        print(f"✓ Captured pattern: {label}")
        self._save_patterns()
        
        return pattern
    
    def _compute_flag_changes(self, before, after):
        """Compute which registers changed."""
        changes = {}
        for i, (b, a) in enumerate(zip(before, after)):
            if b != a:
                changes[f'x{i}'] = {'from': b, 'to': a}
        return changes
    
    def get_pattern_for_instruction(self, instruction_hex: str):
        """Retrieve captured pattern for an instruction."""
        return self.patterns.get(instruction_hex, [])
    
    def compare_rv32_to_rv64_pattern(self, rv32_pattern, rv64_state):
        """
        Compare RV32 execution pattern to RV64 execution.
        
        Helps verify that RV64 behavior matches RV32 semantics for compatible operations.
        """
        changes = []
        for reg_name, change in rv32_pattern['flag_changes'].items():
            # For 32-bit operations in 64-bit mode, check low 32 bits
            reg_idx = int(reg_name[1:])
            if reg_idx < len(rv64_state['regs']):
                rv32_after = change['to']
                rv64_after = rv64_state['regs'][reg_idx] & 0xFFFFFFFF
                if rv32_after != rv64_after:
                    changes.append({
                        'register': reg_name,
                        'rv32_expected': rv32_after,
                        'rv64_actual': rv64_after,
                        'match': False
                    })
        
        return changes
    
    def generate_rv64_test_from_pattern(self, instruction_hex: str, test_name: str):
        """
        Generate a test case for RV64 based on captured RV32 pattern.
        
        This automates test generation for the 64-bit emulator.
        """
        patterns = self.get_pattern_for_instruction(instruction_hex)
        if not patterns:
            return None
        
        # Use first pattern as template
        pattern = patterns[0]
        
        test_case = {
            'name': test_name,
            'instruction_hex': instruction_hex,
            'rv32_pattern': pattern,
            'rv64_expected': self._infer_rv64_expectations(pattern)
        }
        
        return test_case
    
    def _infer_rv64_expectations(self, rv32_pattern):
        """
        Infer expected RV64 behavior from RV32 pattern.
        
        For 32-bit operations (ADD, SUB, etc.), RV64 should match low 32 bits
        and zero-extend to 64 bits.
        """
        expected = {}
        for reg_name, change in rv32_pattern['flag_changes'].items():
            reg_idx = int(reg_name[1:])
            expected[reg_idx] = {
                'low_32': change['to'],
                'full_64': change['to']  # Zero-extended
            }
        return expected


def capture_basic_arithmetic_patterns():
    """
    Capture patterns for basic arithmetic operations.
    
    This builds a foundation library of pixel patterns that can guide
    RV64 emulator development.
    """
    print("=" * 60)
    print("CAPTURING RV32 ARITHMETIC PATTERNS")
    print("=" * 60)
    
    capturer = PixelPatternCapture()
    core = SpatialRV32ICore(memory_size_bytes=1024 * 1024)
    
    # Pattern 1: ADD (add x5, x5, x6)
    # Opcode: 0x00b28533
    print("\n--- Pattern 1: ADD ---")
    core.reset()
    core.load_program(bytes.fromhex("00b28533fe00006f"), entry_point=0x1000)  # ADD r5, r5, r6; halt
    core.write_register(5, 10)
    core.write_register(6, 20)
    capturer.capture_instruction_pattern(
        core, "00b28533", 
        "ADD r5, r5, r6", 
        "Add r6 to r5 (10 + 20 = 30)"
    )
    
    # Pattern 2: SUB (sub x5, x5, x6)
    # Opcode: 0x40b28533
    print("\n--- Pattern 2: SUB ---")
    core.reset()
    core.load_program(bytes.fromhex("40b28533fe00006f"), entry_point=0x1000)
    core.write_register(5, 30)
    core.write_register(6, 10)
    capturer.capture_instruction_pattern(
        core, "40b28533",
        "SUB r5, r5, r6",
        "Subtract r6 from r5 (30 - 10 = 20)"
    )
    
    # Pattern 3: LUI (lui x5, 0x12345)
    # Opcode: 0x123452b7
    print("\n--- Pattern 3: LUI ---")
    core.reset()
    core.load_program(bytes.fromhex("123452b7fe00006f"), entry_point=0x1000)
    capturer.capture_instruction_pattern(
        core, "123452b7",
        "LUI r5, 0x12345",
        "Load upper immediate into r5 (0x12345000)"
    )
    
    # Pattern 4: ADDI (addi x5, x5, 5)
    # Opcode: 0x00528513
    print("\n--- Pattern 4: ADDI ---")
    core.reset()
    core.load_program(bytes.fromhex("00528513fe00006f"), entry_point=0x1000)
    core.write_register(5, 10)
    capturer.capture_instruction_pattern(
        core, "00528513",
        "ADDI r5, r5, 5",
        "Add immediate to r5 (10 + 5 = 15)"
    )
    
    print("\n" + "=" * 60)
    print(f"CAPTURE COMPLETE: {len(capturer.patterns)} patterns stored")
    print(f"Pattern database: {capturer.pattern_db_path}")
    print("=" * 60)
    
    return capturer


def generate_rv64_tests_from_patterns():
    """
    Generate test cases for RV64 emulator based on captured RV32 patterns.
    
    This automates test creation for the 64-bit emulator.
    """
    print("\n" + "=" * 60)
    print("GENERATING RV64 TESTS FROM PATTERNS")
    print("=" * 60)
    
    capturer = PixelPatternCapture()
    tests = []
    
    # Generate tests for basic arithmetic
    for instr_hex in ["00b28533", "40b28533", "123452b7", "00528513"]:
        patterns = capturer.get_pattern_for_instruction(instr_hex)
        if patterns:
            test = capturer.generate_rv64_test_from_pattern(
                instr_hex, 
                f"RV64_{patterns[0]['label'].replace(' ', '_')}"
            )
            if test:
                tests.append(test)
                print(f"✓ Generated test: {test['name']}")
    
    # Save tests
    test_path = Path(__file__).parent / "rv64_tests_from_patterns.json"
    with open(test_path, 'w') as f:
        json.dump(tests, f, indent=2)
    
    print(f"\nTests saved to: {test_path}")
    print(f"Total tests: {len(tests)}")
    
    return tests


def visualize_pattern(pattern: dict):
    """
    Visualize a captured execution pattern.
    
    This helps humans understand the "shape" of instruction execution
    in pixel space.
    """
    print(f"\n{'='*60}")
    print(f"PATTERN: {pattern['label']}")
    print(f"{'='*60}")
    print(f"Instruction: 0x{pattern['instruction_hex']}")
    print(f"Description: {pattern['description']}")
    print(f"\nPC: 0x{pattern['pc_before']:08x} → 0x{pattern['pc_after']:08x}")
    
    if pattern['flag_changes']:
        print(f"\nRegister Changes:")
        for reg, change in pattern['flag_changes'].items():
            print(f"  {reg}: 0x{change['from']:08x} → 0x{change['to']:08x}")
    else:
        print(f"\nNo register changes (likely PC-only operation)")
    
    # Visual representation as "pixel bars"
    print(f"\nVisual Pattern:")
    print(f"  Before: [{''.join(['█' if r != 0 else '░' for r in pattern['registers_before'][:8]])}]")
    print(f"  After:  [{''.join(['█' if r != 0 else '░' for r in pattern['registers_after'][:8]])}]")
    print(f"{'='*60}")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Learn pixel patterns from RV32 execution")
    parser.add_argument('--capture', action='store_true', help='Capture new patterns')
    parser.add_argument('--visualize', type=str, help='Visualize pattern by instruction hex')
    parser.add_argument('--generate-tests', action='store_true', help='Generate RV64 tests from patterns')
    
    args = parser.parse_args()
    
    if args.capture:
        capturer = capture_basic_arithmetic_patterns()
        print("\nCaptured patterns:")
        for instr_hex, patterns in capturer.session_patterns.items():
            for pattern in patterns:
                visualize_pattern(pattern)
    
    elif args.visualize:
        capturer = PixelPatternCapture()
        patterns = capturer.get_pattern_for_instruction(args.visualize)
        if patterns:
            for pattern in patterns:
                visualize_pattern(pattern)
        else:
            print(f"No pattern found for instruction 0x{args.visualize}")
    
    elif args.generate_tests:
        tests = generate_rv64_tests_from_patterns()
    
    else:
        parser.print_help()