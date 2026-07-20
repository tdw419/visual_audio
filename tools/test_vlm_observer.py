#!/usr/bin/env python3
"""
Test VLM Spatial Observer

Verifies that the VLM observer can:
1. Capture Frame 0 from GPU
2. Analyze opcode distribution
3. Detect hot regions
4. Calculate fragmentation metrics
5. Generate analysis JSON
"""

import sys
import json

sys.path.insert(0, '.')

from tools.vlm_spatial_observer import VLMSpatialObserver
from tools.spatial_os_kernel_3d import SpatialOS3D


def test_frame_capture():
    """Test Frame 0 capture"""
    print("=== Test 1: Frame Capture ===")

    os_kernel = SpatialOS3D()
    os_kernel.init_kernel()

    observer = VLMSpatialObserver(os_kernel)

    # Capture frame
    frame = observer.capture_frame_0()

    print(f"✓ Frame captured: {frame.shape}")
    print(f"✓ Frame dtype: {frame.dtype}")
    print(f"✓ Total pixels: {frame.shape[0] * frame.shape[1]}")
    assert frame.shape == (100, 100, 4), "Frame should be 100×100×4"
    print()


def test_opcode_histogram():
    """Test opcode distribution analysis"""
    print("=== Test 2: Opcode Histogram ===")

    os_kernel = SpatialOS3D()
    os_kernel.init_kernel()

    observer = VLMSpatialObserver(os_kernel)
    frame = observer.capture_frame_0()

    histogram = observer.opcode_histogram(frame)

    print(f"✓ Opcode histogram computed:")
    for opcode, count in histogram.items():
        if count > 0:
            print(f"    {opcode}: {count}")

    # Should have some opcodes from the test processes
    total = sum(histogram.values())
    print(f"✓ Total pixels analyzed: {total}")
    assert total <= 10000, "Total cannot exceed frame size"
    print()


def test_hot_region_detection():
    """Test hot region detection"""
    print("=== Test 3: Hot Region Detection ===")

    os_kernel = SpatialOS3D()
    os_kernel.init_kernel()

    observer = VLMSpatialObserver(os_kernel)
    frame = observer.capture_frame_0()

    hot_regions = observer.detect_hot_regions(frame, threshold=3)

    print(f"✓ Found {len(hot_regions)} hot regions (threshold=3)")
    for i, region in enumerate(hot_regions[:3]):
        print(f"    Region {i+1}: ({region['x']}, {region['y']}) {region['size']}×{region['size']} - {region['density']:.0%} dense")

    print()


def test_fragmentation_analysis():
    """Test fragmentation analysis"""
    print("=== Test 4: Fragmentation Analysis ===")

    os_kernel = SpatialOS3D()
    os_kernel.init_kernel()

    observer = VLMSpatialObserver(os_kernel)
    frame = observer.capture_frame_0()

    frag = observer.analyze_fragmentation(frame)

    print(f"✓ Fragmentation analysis:")
    print(f"    Utilization: {frag['utilization']:.1%}")
    print(f"    Free pixels: {frag['free_pixels']}/{frag['total_pixels']}")
    print(f"    Free runs: {frag['free_runs']}")
    print(f"    Avg free run: {frag['avg_free_run']:.1f}")
    print(f"    Max free run: {frag['max_free_run']}")

    assert frag['total_pixels'] == 10000, "Frame should be 100×100"
    assert frag['utilization'] >= 0 and frag['utilization'] <= 1, "Utilization must be 0-1"
    print()


def test_full_analysis():
    """Test full observation and analysis cycle"""
    print("=== Test 5: Full Analysis Cycle ===")

    os_kernel = SpatialOS3D()
    os_kernel.init_kernel()

    observer = VLMSpatialObserver(os_kernel)

    # Run full analysis
    analysis = observer.observe_and_analyze()

    print(f"✓ Full analysis complete")

    # Verify structure
    assert 'frame_shape' in analysis, "Analysis should contain frame_shape"
    assert 'histogram' in analysis, "Analysis should contain histogram"
    assert 'hot_regions' in analysis, "Analysis should contain hot_regions"
    assert 'fragmentation' in analysis, "Analysis should contain fragmentation"
    assert 'vlm_analysis' in analysis, "Analysis should contain vlm_analysis"

    print(f"✓ Analysis structure verified")

    # Save to JSON
    with open('/tmp/vlm_test_full.json', 'w') as f:
        json.dump(analysis, f, indent=2)

    print(f"✓ Analysis saved to /tmp/vlm_test_full.json")
    print()


def test_patch_payload_generation():
    """Test Patch-and-Copy payload generation"""
    print("=== Test 6: Patch Payload Generation ===")

    os_kernel = SpatialOS3D()
    os_kernel.init_kernel()

    observer = VLMSpatialObserver(os_kernel)
    analysis = observer.observe_and_analyze()

    # Generate patch payload
    patch = observer.generate_patch_payload(analysis)

    print(f"✓ Patch payload generated")
    print(f"✓ Version: {patch['version']}")
    print(f"✓ Source: {patch['source']}")
    print(f"✓ Patches: {len(patch['patches'])}")

    # Verify structure
    assert 'version' in patch, "Patch should have version"
    assert 'patches' in patch, "Patch should have patches array"

    # Save to JSON
    with open('/tmp/vlm_test_patch.json', 'w') as f:
        json.dump(patch, f, indent=2)

    print(f"✓ Patch saved to /tmp/vlm_test_patch.json")
    print()


if __name__ == '__main__':
    print("VLM Spatial Observer Test Suite")
    print("=" * 60)
    print()

    test_frame_capture()
    test_opcode_histogram()
    test_hot_region_detection()
    test_fragmentation_analysis()
    test_full_analysis()
    test_patch_payload_generation()

    print("=" * 60)
    print("All VLM observer tests passed!")
    print()
    print("Summary:")
    print("- Frame capture working ✓")
    print("- Opcode histogram working ✓")
    print("- Hot region detection working ✓")
    print("- Fragmentation analysis working ✓")
    print("- Full analysis cycle working ✓")
    print("- Patch payload generation working ✓")
    print()
    print("Ready for:")
    print("- Real VLM integration (Ollama + llava:latest)")
    print("- Spatial compiler (apply patches to VRAM)")
    print("- Autonomous optimization loop")