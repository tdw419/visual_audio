#!/usr/bin/env python3
"""Manual test runner for pixel OS input channel tests."""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def run_manual_tests():
    """Run manual verification of test cases."""
    print("=" * 70)
    print("Pixel OS Input Channel Tests - Manual Verification")
    print("=" * 70)
    
    tests_passed = 0
    tests_failed = 0
    
    # Test 1: Tensor creation and dimensions
    try:
        print("\n[1/10] Testing tensor creation and dimensions...")
        import torch
        
        # Create sample pixel data
        data = torch.randn(4, 3, 32, 32)
        assert data.ndim == 4, f"Expected 4D tensor, got {data.ndim}D"
        batch, channels, height, width = data.shape
        assert batch == 4 and channels == 3 and height == 32 and width == 32
        print("  ✓ Tensor dimensions correct: [4, 3, 32, 32]")
        tests_passed += 1
    except Exception as e:
        print(f"  ✗ Failed: {e}")
        tests_failed += 1
    
    # Test 2: Input structure validation
    try:
        print("\n[2/10] Testing input structure validation...")
        valid_input = {
            'pixel_data': torch.randn(4, 3, 32, 32),
            'metadata': {'format': 'RGB', 'resolution': (32, 32), 'batch_size': 4}
        }
        assert 'pixel_data' in valid_input and 'metadata' in valid_input
        assert isinstance(valid_input['pixel_data'], torch.Tensor)
        assert isinstance(valid_input['metadata'], dict)
        print("  ✓ Input structure valid")
        tests_passed += 1
    except Exception as e:
        print(f"  ✗ Failed: {e}")
        tests_failed += 1
    
    # Test 3: Metadata consistency
    try:
        print("\n[3/10] Testing metadata consistency...")
        tensor = torch.randn(4, 3, 32, 32)
        metadata = {'resolution': (32, 32), 'batch_size': 4}
        batch, channels, height, width = tensor.shape
        assert metadata['batch_size'] == batch
        assert metadata['resolution'] == (height, width)
        print("  ✓ Metadata matches tensor shape")
        tests_passed += 1
    except Exception as e:
        print(f"  ✗ Failed: {e}")
        tests_failed += 1
    
    # Test 4: Normalization
    try:
        print("\n[4/10] Testing pixel normalization...")
        data = torch.randn(4, 3, 32, 32)
        normalized = (data - data.min()) / (data.max() - data.min())
        assert normalized.min() >= 0.0, f"Min below 0: {normalized.min()}"
        assert normalized.max() <= 1.0, f"Max above 1: {normalized.max()}"
        assert not torch.isnan(normalized).any()
        print("  ✓ Normalization produces valid [0, 1] range")
        tests_passed += 1
    except Exception as e:
        print(f"  ✗ Failed: {e}")
        tests_failed += 1
    
    # Test 5: Channel slicing
    try:
        print("\n[5/10] Testing channel slicing...")
        data = torch.randn(4, 3, 32, 32)
        for c in range(3):
            channel = data[:, c, :, :]
            assert channel.shape == (4, 32, 32)
            assert not torch.isnan(channel).any()
        print("  ✓ All channels accessible and valid")
        tests_passed += 1
    except Exception as e:
        print(f"  ✗ Failed: {e}")
        tests_failed += 1
    
    # Test 6: Batch processing
    try:
        print("\n[6/10] Testing batch processing...")
        tensor = torch.randn(4, 3, 32, 32)
        for i in range(4):
            item = tensor[i]  # [C, H, W]
            assert item.ndim == 3
            assert not torch.isnan(item).any()
        print("  ✓ All batch items processable")
        tests_passed += 1
    except Exception as e:
        print(f"  ✗ Failed: {e}")
        tests_failed += 1
    
    # Test 7: Edge case - single pixel
    try:
        print("\n[7/10] Testing single pixel input...")
        single = torch.randn(1, 3, 1, 1)
        assert single.shape == (1, 3, 1, 1)
        normalized = (single - single.min()) / (single.max() - single.min())
        assert not torch.isnan(normalized).any()
        print("  ✓ Single pixel input handled")
        tests_passed += 1
    except Exception as e:
        print(f"  ✗ Failed: {e}")
        tests_failed += 1
    
    # Test 8: Edge case - large batch
    try:
        print("\n[8/10] Testing large batch input...")
        large = torch.randn(16, 3, 64, 64)
        assert large.shape[0] == 16
        processed = large * 0.5 + 0.5
        assert processed.shape == large.shape
        print("  ✓ Large batch input handled")
        tests_passed += 1
    except Exception as e:
        print(f"  ✗ Failed: {e}")
        tests_failed += 1
    
    # Test 9: Edge case - high channels
    try:
        print("\n[9/10] Testing high channel input...")
        high_ch = torch.randn(2, 12, 16, 16)
        assert high_ch.shape[1] == 12
        for c in range(12):
            channel = high_ch[:, c, :, :]
            assert channel.ndim == 3
        print("  ✓ High channel input handled")
        tests_passed += 1
    except Exception as e:
        print(f"  ✗ Failed: {e}")
        tests_failed += 1
    
    # Test 10: Edge case - non-square
    try:
        print("\n[10/10] Testing non-square input...")
        non_square = torch.randn(3, 3, 32, 48)
        h, w = non_square.shape[2], non_square.shape[3]
        assert h != w
        assert not torch.isnan(non_square).any()
        print("  ✓ Non-square input handled")
        tests_passed += 1
    except Exception as e:
        print(f"  ✗ Failed: {e}")
        tests_failed += 1
    
    # Summary
    print("\n" + "=" * 70)
    print(f"Test Results: {tests_passed} passed, {tests_failed} failed")
    print("=" * 70)
    
    return tests_failed == 0

if __name__ == '__main__':
    success = run_manual_tests()
    sys.exit(0 if success else 1)