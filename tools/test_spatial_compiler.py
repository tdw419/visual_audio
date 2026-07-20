#!/usr/bin/env python3
"""
Test Spatial Compiler - Verify VLM patch application to VRAM

Tests:
1. Test patch payload generation
2. Test single pixel write
3. Test rectangular fill
4. Test region clear
5. Test full patch application cycle
6. Test VLM observer → Spatial Compiler integration
"""

import sys
import json
import time

sys.path.insert(0, '.')

from tools.spatial_compiler import SpatialCompiler
from tools.spatial_os_kernel_3d import SpatialOS3D


def test_single_pixel_write():
    """Test single pixel write operation"""
    print("=== Test 1: Single Pixel Write ===")

    os_kernel = SpatialOS3D()
    os_kernel.init_kernel()

    compiler = SpatialCompiler(os_kernel)

    # Create patch with single pixel write
    patch = {
        "version": "1.0",
        "source": "Test Script",
        "patches": [
            {
                "type": "WRITE_PIXEL",
                "target": "(5, 5)",
                "rationale": "Test pixel write",
                "color": [236, 80, 80],
            }
        ]
    }

    # Apply patch
    success = compiler.apply_patch(patch, verify=True)

    if success:
        print("✓ Single pixel write test passed")
    else:
        print("✗ Single pixel write test failed")
    print()

    return success


def test_rectangular_fill():
    """Test rectangular fill operation"""
    print("=== Test 2: Rectangular Fill ===")

    os_kernel = SpatialOS3D()
    os_kernel.init_kernel()

    compiler = SpatialCompiler(os_kernel)

    # Create patch with rectangular fill
    patch = {
        "version": "1.0",
        "source": "Test Script",
        "patches": [
            {
                "type": "FILL_RECT",
                "target": "(10, 10)",
                "rationale": "Test fill rect",
                "color": [80, 236, 120],
            }
        ]
    }

    # Apply patch
    success = compiler.apply_patch(patch, verify=True)

    if success:
        print("✓ Rectangular fill test passed")
    else:
        print("✗ Rectangular fill test failed")
    print()

    return success


def test_region_clear():
    """Test region clear operation"""
    print("=== Test 3: Region Clear ===")

    os_kernel = SpatialOS3D()
    os_kernel.init_kernel()

    compiler = SpatialCompiler(os_kernel)

    # First fill a region
    fill_patch = {
        "version": "1.0",
        "source": "Test Script",
        "patches": [
            {
                "type": "FILL_RECT",
                "target": "(20, 20)",
                "rationale": "Pre-fill region",
                "color": [247, 83, 80],
            }
        ]
    }

    compiler.apply_patch(fill_patch, verify=False)

    # Then clear it
    clear_patch = {
        "version": "1.0",
        "source": "Test Script",
        "patches": [
            {
                "type": "CLEAR_REGION",
                "target": "(20, 20)",
                "rationale": "Test clear region",
            }
        ]
    }

    # Apply clear patch
    success = compiler.apply_patch(clear_patch, verify=True)

    if success:
        print("✓ Region clear test passed")
    else:
        print("✗ Region clear test failed")
    print()

    return success


def test_full_patch_cycle():
    """Test complete patch application with multiple operations"""
    print("=== Test 4: Full Patch Cycle ===")

    os_kernel = SpatialOS3D()
    os_kernel.init_kernel()

    compiler = SpatialCompiler(os_kernel)

    # Create patch with multiple operations
    patch = {
        "version": "1.0",
        "source": "Test Script",
        "patches": [
            {
                "type": "WRITE_PIXEL",
                "target": "(5, 5)",
                "rationale": "Test pixel write",
                "color": [236, 80, 80],
            },
            {
                "type": "FILL_RECT",
                "target": "(10, 10)",
                "rationale": "Test fill rect",
                "color": [80, 236, 120],
            },
            {
                "type": "CLEAR_REGION",
                "target": "(20, 20)",
                "rationale": "Test clear region",
            },
            {
                "type": "COMPACTION",
                "target": "(30, 30)",
                "rationale": "Test compaction",
            },
        ]
    }

    # Apply patch
    success = compiler.apply_patch(patch, verify=True)

    if success:
        print("✓ Full patch cycle test passed")
    else:
        print("✗ Full patch cycle test failed")
    print()

    return success


def test_vlm_observer_integration():
    """Test VLM observer → Spatial Compiler integration"""
    print("=== Test 5: VLM Observer Integration ===")

    from tools.vlm_spatial_observer import VLMSpatialObserver

    os_kernel = SpatialOS3D()
    os_kernel.init_kernel()

    # Run VLM observer
    observer = VLMSpatialObserver(os_kernel)
    analysis = observer.observe_and_analyze()

    # Generate patch payload
    patch = observer.generate_patch_payload(analysis)

    # Apply via spatial compiler
    compiler = SpatialCompiler(os_kernel)
    success = compiler.apply_patch(patch, verify=True)

    if success:
        print("✓ VLM observer integration test passed")
    else:
        print("✗ VLM observer integration test failed")
    print()

    return success


def test_persistence_across_ticks():
    """Test that patches persist across kernel execution ticks"""
    print("=== Test 6: Persistence Across Ticks ===")

    os_kernel = SpatialOS3D()
    os_kernel.init_kernel()

    compiler = SpatialCompiler(os_kernel)

    # Apply a patch
    patch = {
        "version": "1.0",
        "source": "Test Script",
        "patches": [
            {
                "type": "WRITE_PIXEL",
                "target": "(5, 5)",
                "rationale": "Test persistence",
                "color": [236, 80, 80],
            }
        ]
    }

    compiler.apply_patch(patch, verify=False)

    # Run a few kernel ticks
    print("  Running 5 kernel ticks...")
    for i in range(5):
        os_kernel.tick(1)

    # Verify pixel is still there
    data = os_kernel.device.queue.read_buffer(os_kernel.vram_buf)
    pixels = (np.frombuffer(data, dtype=np.uint32).reshape(
        os_kernel.vram_depth, os_kernel.vram_height, os_kernel.vram_width, 4
    ).astype(np.uint8))

    expected = (236, 80, 80)
    actual = tuple(pixels[0, 5, 5, :3])

    if actual == expected:
        print(f"  ✓ Pixel persisted after 5 ticks: {actual}")
        success = True
    else:
        print(f"  ✗ Pixel changed after 5 ticks: expected {expected}, got {actual}")
        success = False

    print()
    return success


def test_coordinate_parsing():
    """Test coordinate string parsing"""
    print("=== Test 7: Coordinate Parsing ===")

    os_kernel = SpatialOS3D()
    os_kernel.init_kernel()

    compiler = SpatialCompiler(os_kernel)

    test_cases = [
        ("(5, 10)", (5, 10, 0)),
        ("(15, 20, 0)", (15, 20, 0)),
        ("( 25 , 30 )", (25, 30, 0)),  # With spaces
    ]

    success = True
    for coord_str, expected in test_cases:
        try:
            result = compiler._parse_coordinate(coord_str)
            if result == expected:
                print(f"  ✓ '{coord_str}' → {result}")
            else:
                print(f"  ✗ '{coord_str}' → {result} (expected {expected})")
                success = False
        except Exception as e:
            print(f"  ✗ '{coord_str}' → ERROR: {e}")
            success = False

    print()
    return success


def test_command_line_interface():
    """Test command line interface"""
    print("=== Test 8: Command Line Interface ===")

    import subprocess
    import tempfile
    import os

    # Create a test patch file
    patch = {
        "version": "1.0",
        "source": "Test Script",
        "patches": [
            {
                "type": "WRITE_PIXEL",
                "target": "(5, 5)",
                "rationale": "Test CLI",
                "color": [236, 80, 80],
            }
        ]
    }

    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(patch, f)
        patch_file = f.name

    try:
        # Run spatial_compiler.py via command line
        result = subprocess.run(
            ["python3", "tools/spatial_compiler.py", "--patch-file", patch_file],
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode == 0:
            print("  ✓ Command line interface test passed")
            success = True
        else:
            print(f"  ✗ Command line failed with return code {result.returncode}")
            print(f"     stdout: {result.stdout}")
            print(f"     stderr: {result.stderr}")
            success = False
    except Exception as e:
        print(f"  ✗ Command line test raised exception: {e}")
        success = False
    finally:
        os.unlink(patch_file)

    print()
    return success


if __name__ == '__main__':
    import numpy as np

    print("Spatial Compiler Test Suite")
    print("=" * 60)
    print()

    results = []

    # Run tests
    results.append(("Single Pixel Write", test_single_pixel_write()))
    results.append(("Rectangular Fill", test_rectangular_fill()))
    results.append(("Region Clear", test_region_clear()))
    results.append(("Full Patch Cycle", test_full_patch_cycle()))
    results.append(("VLM Observer Integration", test_vlm_observer_integration()))
    results.append(("Persistence Across Ticks", test_persistence_across_ticks()))
    results.append(("Coordinate Parsing", test_coordinate_parsing()))
    results.append(("Command Line Interface", test_command_line_interface()))

    # Summary
    print("=" * 60)
    print("Test Summary")
    print("=" * 60)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status}: {name}")

    print()
    print(f"Total: {passed}/{total} tests passed")

    if passed == total:
        print()
        print("SUCCESS: All spatial compiler tests passed!")
        print()
        print("The autonomous evolution loop is now complete:")
        print("  1. VLM Observer watches MKV surface ✓")
        print("  2. VLM generates optimization patches ✓")
        print("  3. Spatial Compiler applies patches to VRAM ✓")
        print("  4. Kernel continues execution with optimized code ✓")
        sys.exit(0)
    else:
        print()
        print("FAILURE: Some tests failed")
        sys.exit(1)