#!/usr/bin/env python3
"""Smoke tests for pixel-interpreter ISA. Covers all major opcodes."""

from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent))

import numpy as np
from PIL import Image

# Import from cpu_emulator
from cpu_emulator import (
    PixelCPU, OP_NOP, OP_SET, OP_ADD, OP_SUB, OP_LOAD, OP_STORE, OP_JMP, OP_JZ, OP_HALT
)

def test_set_add_sub_halt():
    """Test 1: SET 5; ADD 3; SUB 8; HALT -> Acc=0, ZF=1"""
    print("=== Test 1: SET/ADD/SUB/HALT ===")
    
    # Build program image
    prog = np.zeros((16, 16, 4), dtype=np.uint8)
    # Code at y=1
    prog[1, 0] = [OP_SET, 0, 0, 5]       # SET 5
    prog[1, 1] = [OP_ADD, 0, 3, 0]       # ADD 3
    prog[1, 2] = [OP_SUB, 0, 8, 0]       # SUB 8
    prog[1, 3] = [OP_HALT, 0, 0, 0]      # HALT
    
    img = Image.fromarray(prog)
    img.save("/tmp/test1_prog.png")
    
    cpu = PixelCPU(16, 16)
    cpu.load_program(Path("/tmp/test1_prog.png"))
    stats = cpu.run()
    
    assert stats['halted'], "Should halt"
    assert stats['accumulator'] == 0, f"Acc=0 expected, got {stats['accumulator']}"
    assert stats['zero_flag'] == 1, f"ZF=1 expected, got {stats['zero_flag']}"
    print("✓ PASS\n")

def test_store_load():
    """Test 2: SET 42; STORE to (10,10); LOAD from (10,10) -> Acc=42"""
    print("=== Test 2: STORE/LOAD ===")
    
    prog = np.zeros((16, 16, 4), dtype=np.uint8)
    # Data location: (5, 5) - use smaller coords for uint8 PNG encoding
    
    # Code at y=1
    prog[1, 0] = [OP_SET, 0, 0, 42]                        # SET 42
    # PACK COORD: G=dest_x=5, B=dest_y=5, A=opcode=STORE
    prog[1, 1] = [OP_STORE, 5, 5, 0]                        # STORE (5,5)
    prog[1, 2] = [OP_SET, 0, 0, 0]                          # SET 0 (clear)
    # PACK COORD: G=src_x=5, B=src_y=5, A=opcode=LOAD
    prog[1, 3] = [OP_LOAD, 5, 5, 0]                         # LOAD (5,5)
    prog[1, 4] = [OP_HALT, 0, 0, 0]                         # HALT
    
    img = Image.fromarray(prog)
    img.save("/tmp/test2_prog.png")
    
    cpu = PixelCPU(16, 16)
    cpu.load_program(Path("/tmp/test2_prog.png"))
    stats = cpu.run()
    
    assert stats['halted'], "Should halt"
    assert stats['accumulator'] == 42, f"Acc=42 expected, got {stats['accumulator']}"
    
    # Verify memory was actually written
    stored_val = cpu.memory[5, 5, 0]
    assert stored_val == 42, f"Memory[5,5]=42 expected, got {stored_val}"
    
    print("✓ PASS\n")

def test_jz_loop():
    """Test 3: Loop: SET 3; LOOP: SUB 1; JZ DONE; JMP LOOP; DONE: HALT -> Acc=0"""
    print("=== Test 3: JZ Loop (decrement to zero) ===")
    
    prog = np.zeros((16, 16, 4), dtype=np.uint8)
    
    # Code at y=1
    prog[1, 0] = [OP_SET, 0, 0, 3]                        # SET 3
    prog[1, 1] = [OP_SUB, 0, 1, 0]                         # LOOP: SUB 1
    # JZ DONE: G=dest_x=4, B=dest_y=1 (jump to HALT if zero)
    prog[1, 2] = [OP_JZ, 4, 1, 0]                          # JZ DONE (skip JMP if zero)
    # JMP LOOP: G=dest_x=1, B=dest_y=1 (back to SUB)
    prog[1, 3] = [OP_JMP, 1, 1, 0]                         # JMP LOOP
    prog[1, 4] = [OP_HALT, 0, 0, 0]                        # DONE: HALT
    
    img = Image.fromarray(prog)
    img.save("/tmp/test3_prog.png")
    
    cpu = PixelCPU(16, 16)
    cpu.load_program(Path("/tmp/test3_prog.png"))
    stats = cpu.run()
    
    assert stats['halted'], "Should halt"
    assert stats['accumulator'] == 0, f"Acc=0 expected, got {stats['accumulator']}"
    assert stats['zero_flag'] == 1, f"ZF=1 expected, got {stats['zero_flag']}"
    
    print(f"Cycles: {stats['cycles']}")
    print("✓ PASS\n")

def test_jmp_forward():
    """Test 4: JMP forward: SET 1; JMP 5; SET 999 (should skip); SET 2 -> Acc=2"""
    print("=== Test 4: JMP Forward ===")
    
    prog = np.zeros((16, 16, 4), dtype=np.uint8)
    
    # Code at y=1
    prog[1, 0] = [OP_SET, 0, 0, 1]                        # SET 1
    # JMP to (4,1) skip two instructions
    prog[1, 1] = [OP_JMP, 4, 1, 0]                         # JMP to (4,1) (skip SET 999)
    prog[1, 2] = [OP_SET, 0, 0, 255]                       # Should be skipped (255 for visibility)
    prog[1, 3] = [OP_SET, 0, 0, 255]                       # Should be skipped
    prog[1, 4] = [OP_SET, 0, 0, 2]                         # SET 2
    prog[1, 5] = [OP_HALT, 0, 0, 0]                        # HALT
    
    img = Image.fromarray(prog)
    img.save("/tmp/test4_prog.png")
    
    cpu = PixelCPU(16, 16)
    cpu.load_program(Path("/tmp/test4_prog.png"))
    stats = cpu.run()
    
    assert stats['halted'], "Should halt"
    assert stats['accumulator'] == 2, f"Acc=2 expected, got {stats['accumulator']}"
    
    print("✓ PASS\n")

def test_memory_accumulation():
    """Test 5: Load values from memory and sum them"""
    print("=== Test 5: Memory Accumulation ===")
    
    prog = np.zeros((16, 16, 4), dtype=np.uint8)
    
    # Pre-populate data at y=5
    prog[5, 0] = [10, 0, 0, 0]   # Data[0] = 10
    prog[5, 1] = [20, 0, 0, 0]   # Data[1] = 20
    prog[5, 2] = [30, 0, 0, 0]   # Data[2] = 30
    
    # Code at y=1
    prog[1, 0] = [OP_SET, 0, 0, 0]                        # SET 0
    prog[1, 1] = [OP_LOAD, 0, 5, 0]                        # LOAD from (0,5) -> Acc=10
    # Store first value to temp location (3,10)
    prog[1, 2] = [OP_STORE, 3, 10, 0]                      # STORE (3,10)
    prog[1, 3] = [OP_LOAD, 1, 5, 0]                        # LOAD from (1,5) -> Acc=20
    # Add first value from temp: Acc = 20 + 10 = 30
    prog[1, 4] = [OP_ADD, 3, 10, 0]                        # ADD 10 (from temp location)
    prog[1, 5] = [OP_HALT, 0, 0, 0]                        # HALT
    
    img = Image.fromarray(prog)
    img.save("/tmp/test5_prog.png")
    
    cpu = PixelCPU(16, 16)
    cpu.load_program(Path("/tmp/test5_prog.png"))
    stats = cpu.run()
    
    # Expected: 0 -> LOAD 10 -> STORE 10 -> LOAD 20 -> ADD 10 = 30
    expected = 30
    assert stats['halted'], "Should halt"
    assert stats['accumulator'] == expected, f"Acc={expected} expected, got {stats['accumulator']}"
    
    print(f"Accumulated value: {stats['accumulator']}")
    print("✓ PASS\n")

def main():
    print("Running pixel-interpreter ISA smoke tests...\n")
    
    test_set_add_sub_halt()
    test_store_load()
    test_jz_loop()
    test_jmp_forward()
    test_memory_accumulation()
    
    print("=" * 50)
    print("All smoke tests PASSED")
    print("=" * 50)

if __name__ == "__main__":
    main()