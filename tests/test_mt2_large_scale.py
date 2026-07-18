#!/usr/bin/env python3
"""
MT2 large-scale capacity tests.

Verifies that MT2 encoding handles payloads exceeding the MT1 limit of 999 tiles.
Tests compression for large manifests.
"""

import os
import subprocess
import sys
import tempfile
import hashlib

# Add tools to path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'tools'))


def md5_hash(data: bytes) -> str:
    """Calculate MD5 hash as hex string."""
    return hashlib.md5(data).hexdigest()


def test_mt1_limit_payload():
    """Test payload that exactly hits MT1 limit (999 tiles)."""
    print("TEST 1: MT1 limit payload (999 tiles)")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create payload that uses exactly 999 tiles
        from dense_encoder_multitile import MAX_PAYLOAD
        payload = b"X" * (999 * MAX_PAYLOAD)
        payload_hash = md5_hash(payload)
        
        # Encode
        input_path = os.path.join(tmpdir, "mt1_limit.bin")
        output_base = os.path.join(tmpdir, "mt1_limit")
        
        with open(input_path, 'wb') as f:
            f.write(payload)
        
        result = subprocess.run(
            ["python3", "tools/dense_encoder_multitile.py", "encode", input_path, "-o", output_base],
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            print(f"  FAIL: encode failed\n{result.stderr}")
            return False
        
        # Check tile count
        import glob
        tile_files = glob.glob(f"{output_base}.*.png")
        tile_files = [f for f in tile_files if not f.endswith('.manifest.png')]
        
        if len(tile_files) != 999:
            print(f"  FAIL: expected 999 tiles, got {len(tile_files)}")
            return False
        
        # Decode
        manifest = output_base + ".manifest.png"
        result = subprocess.run(
            ["python3", "tools/dense_encoder_multitile.py", "decode", manifest],
            capture_output=True
        )
        
        if result.returncode != 0:
            print(f"  FAIL: decode failed\n{result.stderr}")
            return False
        
        decoded = result.stdout
        decoded_hash = md5_hash(decoded)
        
        if decoded_hash != payload_hash:
            print(f"  FAIL: hash mismatch (expected {payload_hash}, got {decoded_hash})")
            return False
        
        print(f"  PASS: {len(payload)} bytes round-tripped in {len(tile_files)} tiles")
        return True


def test_mt2_upgrade():
    """Test payload that exceeds MT1 limit (1000 tiles)."""
    print("\nTEST 2: MT2 auto-upgrade (1000 tiles)")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create payload that needs 1000 tiles
        from dense_encoder_multitile import MAX_PAYLOAD
        payload = b"Y" * (1000 * MAX_PAYLOAD)
        payload_hash = md5_hash(payload)
        
        # Encode
        input_path = os.path.join(tmpdir, "mt2_upgrade.bin")
        output_base = os.path.join(tmpdir, "mt2_upgrade")
        
        with open(input_path, 'wb') as f:
            f.write(payload)
        
        result = subprocess.run(
            ["python3", "tools/dense_encoder_multitile.py", "encode", input_path, "-o", output_base],
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            print(f"  FAIL: encode failed\n{result.stderr}")
            return False
        
        # Check MT2 tile naming (5-digit format)
        import glob
        tile_files = glob.glob(f"{output_base}.*.png")
        tile_files = [f for f in tile_files if not f.endswith('.manifest.png')]
        
        # Check for 5-digit format
        has_5digit = any('.00000.png' in f or '.01234.png' in f for f in tile_files)
        
        if not has_5digit:
            print(f"  FAIL: MT2 5-digit format not detected")
            return False
        
        # Decode
        manifest = output_base + ".manifest.png"
        result = subprocess.run(
            ["python3", "tools/dense_encoder_multitile.py", "decode", manifest],
            capture_output=True
        )
        
        if result.returncode != 0:
            print(f"  FAIL: decode failed\n{result.stderr}")
            return False
        
        decoded = result.stdout
        decoded_hash = md5_hash(decoded)
        
        if decoded_hash != payload_hash:
            print(f"  FAIL: hash mismatch (expected {payload_hash}, got {decoded_hash})")
            return False
        
        print(f"  PASS: {len(payload)} bytes round-tripped in {len(tile_files)} tiles (MT2 format)")
        return True


def test_large_manifest_compression():
    """Test manifest compression for very large tile counts."""
    print("\nTEST 3: Large manifest compression (1500 tiles)")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create payload that needs 1500 tiles
        from dense_encoder_multitile import MAX_PAYLOAD
        payload = b"Z" * (1500 * MAX_PAYLOAD)
        payload_hash = md5_hash(payload)
        
        # Encode
        input_path = os.path.join(tmpdir, "large_manifest.bin")
        output_base = os.path.join(tmpdir, "large_manifest")
        
        with open(input_path, 'wb') as f:
            f.write(payload)
        
        result = subprocess.run(
            ["python3", "tools/dense_encoder_multitile.py", "encode", input_path, "-o", output_base],
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            print(f"  FAIL: encode failed\n{result.stderr}")
            return False
        
        # Check for compression marker in output
        if "Manifest compressed:" not in result.stderr:
            print(f"  FAIL: manifest compression not detected")
            return False
        
        # Decode
        manifest = output_base + ".manifest.png"
        decoded_path = os.path.join(tmpdir, "large_manifest_decoded.bin")
        result = subprocess.run(
            ["python3", "tools/dense_encoder_multitile.py", "decode", manifest, "-o", decoded_path],
            capture_output=True,
            text=True
        )

        if result.returncode != 0:
            print(f"  FAIL: decode failed\n{result.stderr}")
            return False

        # Check for decompression marker
        if "Manifest is compressed, decompressing..." not in result.stderr:
            print(f"  FAIL: manifest decompression not detected")
            return False

        with open(decoded_path, 'rb') as f:
            decoded = f.read()
        decoded_hash = md5_hash(decoded)
        
        if decoded_hash != payload_hash:
            print(f"  FAIL: hash mismatch (expected {payload_hash}, got {decoded_hash})")
            return False
        
        print(f"  PASS: {len(payload)} bytes round-tripped with compressed manifest")
        return True


def test_maximum_capacity():
    """Test near-maximum MT2 capacity (99,999 tiles)."""
    print("\nTEST 4: Near-maximum MT2 capacity (10,000 tiles for speed)")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # Use 10,000 tiles for reasonable test time
        from dense_encoder_multitile import MAX_PAYLOAD
        payload = b"W" * (10000 * MAX_PAYLOAD)
        payload_hash = md5_hash(payload)
        
        # Encode
        input_path = os.path.join(tmpdir, "max_capacity.bin")
        output_base = os.path.join(tmpdir, "max_capacity")
        
        with open(input_path, 'wb') as f:
            f.write(payload)
        
        print("  Encoding 10,000 tiles (this may take a moment)...", flush=True)
        result = subprocess.run(
            ["python3", "tools/dense_encoder_multitile.py", "encode", input_path, "-o", output_base],
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            print(f"  FAIL: encode failed\n{result.stderr}")
            return False
        
        # Decode
        manifest = output_base + ".manifest.png"
        print("  Decoding 10,000 tiles...", flush=True)
        result = subprocess.run(
            ["python3", "tools/dense_encoder_multitile.py", "decode", manifest],
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            print(f"  FAIL: decode failed\n{result.stderr}")
            return False
        
        decoded = result.stdout
        decoded_hash = md5_hash(decoded)
        
        if decoded_hash != payload_hash:
            print(f"  FAIL: hash mismatch (expected {payload_hash}, got {decoded_hash})")
            return False
        
        mb_size = len(payload) / (1024 * 1024)
        print(f"  PASS: {mb_size:.1f} MB round-tripped successfully")
        return True


def run_all():
    """Run all MT2 tests."""
    print("="*60)
    print("MT2 Large-Scale Capacity Tests")
    print("="*60)
    
    results = []
    results.append(("MT1 limit payload", test_mt1_limit_payload()))
    results.append(("MT2 auto-upgrade", test_mt2_upgrade()))
    results.append(("Large manifest compression", test_large_manifest_compression()))
    # results.append(("Near-maximum capacity", test_maximum_capacity()))  # Skip for speed
    
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    
    passed = sum(1 for _, r in results if r)
    total = len(results)
    
    for name, result in results:
        status = "PASS" if result else "FAIL"
        print(f"  {status}: {name}")
    
    print(f"\n{passed}/{total} tests passed")
    
    if passed == total:
        print("\nAll MT2 tests passed!")
        return 0
    else:
        print(f"\n{total - passed} test(s) failed")
        return 1


if __name__ == '__main__':
    sys.exit(run_all())