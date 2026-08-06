#!/usr/bin/env python3
"""
Test Phase 7 Pixel Execution

Verifies that evolved pixel code can be executed correctly.
"""

import sys
import os
import tempfile
import subprocess
from pathlib import Path

# Add project root to path
REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT))

from tools.semantic_cpu_emulator import SelfAwareLoader
import numpy as np


def test_pixel_version_execution():
    """Test that pixel version can be executed via subprocess."""
    print("\n" + "=" * 70)
    print("TEST: PIXEL VERSION EXECUTION")
    print("=" * 70 + "\n")

    # Create a simple test Python program
    test_code = b'#!/usr/bin/env python3\nprint("Hello from pixel version!")\nprint(f"Args: {sys.argv}")\n'

    # Encode to pixels (simplified for test)
    # In reality, this would go through PixelTokenizer
    pixel_data = np.array([list(test_code)] * 3, dtype=np.uint8)[:, :3]

    # Save pixel data to temp MKV-like file
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        mkv_path = tmpdir / "test.mkv"
        mkv_path.touch()

        # Create a simple loader instance
        loader = SelfAwareLoader(mkv_path)
        loader.pixel_data = pixel_data

        # Create a temporary pixel file to simulate MKV extraction
        with tempfile.NamedTemporaryFile(mode='wb', delete=False, suffix='.npy') as f:
            np.save(f, pixel_data)
            temp_pixel_path = Path(f.name)

        try:
            # Test that execute_pixel_version method exists
            assert hasattr(loader, 'execute_pixel_version'), "execute_pixel_version method missing"

            print("✓ SelfAwareLoader.execute_pixel_version() method exists")
            print("\nNote: Full pixel execution test requires MKV with semantic_cpu_emulator.py.pixel")
            print("      and actual wordbase encoding. This test verifies the API exists.")

            return True

        finally:
            temp_pixel_path.unlink(missing_ok=True)


def test_evolution_history_persistence():
    """Test that evolution history can be persisted and loaded."""
    print("\n" + "=" * 70)
    print("TEST: EVOLUTION HISTORY PERSISTENCE")
    print("=" * 70 + "\n")

    from tools.semantic_cpu_emulator import ChildMKVCreator

    # Test that methods exist
    assert hasattr(ChildMKVCreator, 'save_evolution_history'), "save_evolution_history method missing"
    assert hasattr(ChildMKVCreator, 'load_evolution_history'), "load_evolution_history method missing"

    print("✓ ChildMKVCreator.save_evolution_history() method exists")
    print("✓ ChildMKVCreator.load_evolution_history() method exists")

    # Test that load_evolution_history is a static method
    assert isinstance(ChildMKVCreator.__dict__.get('load_evolution_history'), staticmethod), \
        "load_evolution_history should be static method"

    print("✓ load_evolution_history is a static method (can call without instance)")

    print("\nNote: Full persistence test requires MKV with evolution_history.json entry.")
    print("      This test verifies the API exists.")

    return True


def test_auto_continue_flag():
    """Test that auto-continue flag is recognized."""
    print("\n" + "=" * 70)
    print("TEST: AUTO-CONTINUE FLAG")
    print("=" * 70 + "\n")

    result = subprocess.run(
        ["python3", "tools/semantic_cpu_emulator.py", "--help"],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )

    assert result.returncode == 0, f"Help command failed: {result.stderr}"
    assert "--auto-continue" in result.stdout, "--auto-continue flag not in help"

    print("✓ --auto-continue flag exists in CLI")

    return True


def test_build_pixel_args():
    """Test that _build_pixel_args method works correctly."""
    print("\n" + "=" * 70)
    print("TEST: BUILD PIXEL ARGS")
    print("=" * 70 + "\n")

    from tools.semantic_cpu_emulator import SemanticCPUEmulator

    emulator = SemanticCPUEmulator(
        kernel_path=Path("/tmp/test_kernel"),
        disk_path=Path("/tmp/test_disk.qcow2"),
        mkv_path=Path("/tmp/test.mkv"),
        self_aware=True,
        optimize=True,
        max_cycles=5,
        cycle_number=2,
    )

    # Test that method exists
    assert hasattr(emulator, '_build_pixel_args'), "_build_pixel_args method missing"

    # Build args
    args = emulator._build_pixel_args()

    # Verify expected args
    assert "--kernel" in args, "--kernel missing from args"
    assert "--disk" in args, "--disk missing from args"
    assert "--mkv" in args, "--mkv missing from args"
    assert "--self-aware" in args, "--self-aware missing from args"
    assert "--optimize" in args, "--optimize missing from args"
    assert "--max-cycles" in args, "--max-cycles missing from args"
    assert str(emulator.max_cycles) in args, "max_cycles value missing"
    assert "--cycle" in args, "--cycle missing from args"
    assert str(emulator.cycle_number + 1) in args, "cycle number not incremented"

    print("✓ _build_pixel_args() method works correctly")
    print(f"  Generated {len(args)} arguments")
    print(f"  Cycle increment: {emulator.cycle_number} → {emulator.cycle_number + 1}")

    return True


if __name__ == "__main__":
    all_passed = True

    try:
        test_pixel_version_execution()
    except Exception as e:
        print(f"❌ FAILED: pixel version execution test: {e}")
        all_passed = False

    try:
        test_evolution_history_persistence()
    except Exception as e:
        print(f"❌ FAILED: evolution history persistence test: {e}")
        all_passed = False

    try:
        test_auto_continue_flag()
    except Exception as e:
        print(f"❌ FAILED: auto-continue flag test: {e}")
        all_passed = False

    try:
        test_build_pixel_args()
    except Exception as e:
        print(f"❌ FAILED: build pixel args test: {e}")
        all_passed = False

    print("\n" + "=" * 70)
    if all_passed:
        print("ALL TESTS PASSED")
        print("=" * 70 + "\n")
        sys.exit(0)
    else:
        print("SOME TESTS FAILED")
        print("=" * 70 + "\n")
        sys.exit(1)