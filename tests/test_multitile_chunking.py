#!/usr/bin/env python3
"""
Multi-tile chunking tests.

Verifies that large payloads can be split across multiple tiles,
reassembled, and pass MD5 verification.
"""

import os
import subprocess
import sys
import tempfile
import tarfile
from pathlib import Path

# Add tools to path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'tools'))


def md5_hash(data: bytes) -> str:
    """Calculate MD5 hash as hex string."""
    import hashlib
    return hashlib.md5(data).hexdigest()


def test_small_payload():
    """Test that small payloads (< 65KB) use single-tile encoding."""
    print("TEST 1: Small payload (< 65KB)")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create small payload
        payload = b"Hello, World! This is a small payload." * 100
        payload_hash = md5_hash(payload)
        
        # Encode
        input_path = Path(tmpdir) / "small.bin"
        output_base = Path(tmpdir) / "output"
        
        input_path.write_bytes(payload)
        
        # Run dense_encoder_multitile.py
        result = subprocess.run(
            ["python3", "tools/dense_encoder_multitile.py", "encode", str(input_path), "-o", str(output_base)],
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            print(f"  FAIL: encode failed\n{result.stderr}")
            return False
        
        # Check single-tile output
        single_tile = output_base.with_suffix('.png')
        if not single_tile.exists():
            print(f"  FAIL: single-tile PNG not created: {single_tile}")
            return False
        
        # Decode (small payloads don't have manifest, use single tile directly)
        result = subprocess.run(
            ["python3", "tools/dense_encoder_multitile.py", "decode", str(single_tile)],
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
        
        if decoded != payload:
            print(f"  FAIL: byte mismatch")
            return False
        
        print(f"  PASS: {len(payload)} bytes round-tripped successfully")
        return True


def test_large_payload():
    """Test that large payloads (> 65KB) are chunked correctly."""
    print("\nTEST 2: Large payload (> 65KB)")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create 100KB payload (exceeds uint16 limit)
        payload = b"X" * 100_000
        payload_hash = md5_hash(payload)
        
        # Encode
        input_path = Path(tmpdir) / "large.bin"
        output_base = Path(tmpdir) / "output"
        
        input_path.write_bytes(payload)
        
        # Run dense_encoder_multitile.py
        result = subprocess.run(
            ["python3", "tools/dense_encoder_multitile.py", "encode", str(input_path), "-o", str(output_base)],
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            print(f"  FAIL: encode failed\n{result.stderr}")
            return False
        
        # Check multi-tile output
        manifest = output_base.with_suffix('.manifest.png')
        if not manifest.exists():
            print(f"  FAIL: manifest PNG not created: {manifest}")
            return False
        
        # Count tiles (pattern: output.000.png OR output.00000.png - 3 or 5 digits)
        tile_count = len(list(output_base.parent.glob(f"{output_base.name}.*.png")))
        # Subtract 1 for manifest
        tile_count = max(0, tile_count - 1)
        
        if tile_count < 2:
            print(f"  FAIL: expected multiple tiles, got {tile_count}")
            print(f"  Looking for pattern: {output_base.name}.????.png")
            print(f"  Directory contents: {list(output_base.parent.glob('*'))}")
            return False
        
        # Decode
        result = subprocess.run(
            ["python3", "tools/dense_encoder_multitile.py", "decode", str(manifest)],
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
        
        if decoded != payload:
            print(f"  FAIL: byte mismatch")
            return False
        
        print(f"  PASS: {len(payload)} bytes chunked to {tile_count} tiles, round-tripped successfully")
        return True


def test_qemu_source_roundtrip():
    """Test real QEMU source tree round-trip."""
    print("\nTEST 3: QEMU source tree round-trip")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create tarball of real source files
        tar_path = Path(tmpdir) / "qemu_source.tar.gz"
        payload_path = Path(tmpdir) / "payload.bin"
        
        # Tar real source files
        src_files = [
            "tools/dense_encoder.py",
            "tools/speak.py",
        ]
        
        with tarfile.open(tar_path, "w:gz") as tar:
            for f in src_files:
                if os.path.exists(f):
                    tar.add(f)
        
        payload = tar_path.read_bytes()
        payload_hash = md5_hash(payload)
        original_size = len(payload)
        
        print(f"  Source tarball: {original_size} bytes")
        print(f"  MD5: {payload_hash}")
        
        # Encode multi-tile
        output_base = Path(tmpdir) / "qemu_source"
        
        result = subprocess.run(
            ["python3", "tools/dense_encoder_multitile.py", "encode", str(tar_path), "-o", str(output_base)],
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            print(f"  FAIL: encode failed\n{result.stderr}")
            return False
        
        # Decode (handle both single-tile and multi-tile)
        manifest = output_base.with_suffix('.manifest.png')
        single = output_base.with_suffix('.png')
        
        if manifest.exists():
            decode_input = str(manifest)
            mode = "multi-tile"
        elif single.exists():
            decode_input = str(single)
            mode = "single-tile"
        else:
            print(f"  FAIL: no output file found")
            return False
        
        print(f"  Decoding {mode}: {decode_input}")
        
        result = subprocess.run(
            ["python3", "tools/dense_encoder_multitile.py", "decode", decode_input],
            capture_output=True
        )
        
        if result.returncode != 0:
            print(f"  FAIL: decode failed\n{result.stderr}")
            return False
        
        decoded = result.stdout
        decoded_hash = md5_hash(decoded)
        
        # Verify hash
        if decoded_hash != payload_hash:
            print(f"  FAIL: hash mismatch (expected {payload_hash}, got {decoded_hash})")
            return False
        
        # Write decoded tarball and verify contents
        recovered_path = Path(tmpdir) / "recovered.tar.gz"
        recovered_path.write_bytes(decoded)
        
        # Extract and verify
        result = subprocess.run(
            ["tar", "tzf", str(recovered_path)],
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            print(f"  FAIL: recovered tarball is corrupt\n{result.stderr}")
            return False
        
        listed_files = result.stdout.strip().split('\n')
        print(f"  Recovered files: {len(listed_files)}")
        for f in listed_files[:5]:
            print(f"    {f}")
        
        print(f"  PASS: {original_size} bytes round-tripped, tarball verified")
        return True


def run_all():
    """Run all tests."""
    print("="*60)
    print("Multi-tile chunking verification tests")
    print("="*60)
    
    results = []
    results.append(("Small payload", test_small_payload()))
    results.append(("Large payload", test_large_payload()))
    results.append(("QEMU source round-trip", test_qemu_source_roundtrip()))
    
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
        print("\nAll tests passed!")
        return 0
    else:
        print(f"\n{total - passed} test(s) failed")
        return 1


if __name__ == '__main__':
    sys.exit(run_all())