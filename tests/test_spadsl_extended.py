#!/usr/bin/env python3
"""
Tests for SpaDSL extended primitives: conv2d, shift, where.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.spadsl import SpaDSLCompiler, SpaDSLError, compile_and_run
import pytest


def compile_and_run_str(source: str, max_instructions: int = 100000):
    """Run a SpaDSL source string through a temp file (compile_and_run takes a path)."""
    import tempfile
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
        f.write(source)
        path = Path(f.name)
    return compile_and_run(path, max_instructions=max_instructions)


def test_2d_region_decl():
    """Test 2D region declaration."""
    compiler = SpaDSLCompiler()
    source = """
A = region(shape=(3, 4), initial=1)
"""
    code, regions = compile_source(source)
    assert 'A' in regions
    assert regions['A'].shape == (3, 4)
    assert regions['A'].size == 12


def test_shift_operation():
    """Test shift operation."""
    source = """
A = region(shape=(5,), initial=1)
B = shift(A, offset=2)
total = reduce(B, sum)
print(total)
"""
    code, cpu, regions = compile_and_run_str(source, max_instructions=50000)
    # Shifting doesn't change the sum for circular shift
    # Original: [1,1,1,1,1] sum=5
    # Shifted by 2: [1,1,1,1,1] sum=5
    assert cpu.output == [5]


def test_where_operation():
    """Test where conditional selection."""
    source = """
A = region(shape=(4,), initial=5)
B = region(shape=(4,), initial=3)
C = region(shape=(4,), initial=1)
D = where(C, A, B)  # Pick from A where C is non-zero
total = reduce(D, sum)
print(total)
"""
    code, cpu, regions = compile_and_run_str(source, max_instructions=50000)
    # C is all 1s, so D should be all 5s
    # sum = 5+5+5+5 = 20
    assert cpu.output == [20]


def test_conv2d_3x3():
    """Test 3x3 convolution."""
    source = """
A = region(shape=(4, 4), initial=1)
# Identity kernel (3x3)
kernel = [[0, 0, 0], [0, 1, 0], [0, 0, 0]]
B = conv2d(A, kernel)
total = reduce(B, sum)
print(total)
"""
    code, cpu, regions = compile_and_run_str(source, max_instructions=100000)
    # Identity kernel (center=1) with zero padding: out[y][x] = in[y][x],
    # so 4x4 all-ones input -> 4x4 all-ones output, sum = 16.
    assert cpu.output == [16]


def compile_source(source: str):
    from tools.spadsl import compile_source as cs
    return cs(source)


if __name__ == "__main__":
    # Run tests manually
    print("Running test_2d_region_decl...")
    try:
        test_2d_region_decl()
        print("✓ test_2d_region_decl passed")
    except Exception as e:
        print(f"✗ test_2d_region_decl failed: {e}")

    print("Running test_shift_operation...")
    try:
        test_shift_operation()
        print("✓ test_shift_operation passed")
    except Exception as e:
        print(f"✗ test_shift_operation failed: {e}")

    print("Running test_where_operation...")
    try:
        test_where_operation()
        print("✓ test_where_operation passed")
    except Exception as e:
        print(f"✗ test_where_operation failed: {e}")

    print("Running test_conv2d_3x3...")
    try:
        test_conv2d_3x3()
        print("✓ test_conv2d_3x3 passed")
    except Exception as e:
        print(f"✗ test_conv2d_3x3 failed: {e}")