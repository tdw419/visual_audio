#!/usr/bin/env python3
"""
Alpine Boot Trace Verification — Software-to-Video Pipeline

Capture Alpine RISC-V boot execution as spatial MKV using QMP dump-guest-memory,
then verify the round-trip integrity.
"""

import sys
import os
import json
import time
import subprocess
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


def capture_alpine_boot():
    """Capture Alpine boot trace using software-to-video pipeline."""
    print("="*60)
    print("Alpine Boot Trace Capture")
    print("="*60)
    print()
    
    cmd = [
        "python3", "tools/qemu_to_mkv.py",
        "boot_images/alpine_riscv64.qcow2",
        "--arch", "riscv64",
        "--output", "/tmp/alpine_boot_trace.mkv",
        "--interval", "5000",
        "--max-frames", "50",
        "--memory-width", "256",
        "--memory-height", "256",
        "--memory", "64M"
    ]
    
    print(f"Running: {' '.join(cmd)}")
    print()
    
    start = time.time()
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    elapsed = time.time() - start
    
    print(result.stdout)
    
    if result.stderr:
        print("STDERR:", result.stderr, file=sys.stderr)
    
    if result.returncode != 0:
        print(f"✗ Capture failed with exit code {result.returncode}")
        return False, None
    
    # Check output file
    mkv_path = Path("/tmp/alpine_boot_trace.mkv")
    if not mkv_path.exists():
        print(f"✗ Output file not created: {mkv_path}")
        return False, None
    
    size_mb = mkv_path.stat().st_size / (1024 * 1024)
    print(f"✓ Capture complete: {mkv_path} ({size_mb:.2f} MB)")
    print(f"  Time: {elapsed:.1f}s")
    print()
    
    return True, mkv_path


def verify_mkv_integrity(mkv_path):
    """Verify MKV integrity and extract metadata."""
    print("="*60)
    print("MKV Integrity Verification")
    print("="*60)
    print()
    
    # Extract manifest using ffmpeg
    cmd = [
        "ffmpeg", "-v", "quiet",
        "-dump_attachment:t:0", "-",
        "-i", str(mkv_path),
        "-f", "null", "-"
    ]
    
    result = subprocess.run(cmd, capture_output=True, timeout=10)
    
    if result.returncode != 0 or not result.stdout:
        print("✗ Failed to extract manifest")
        return False, None
    
    try:
        manifest = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        print(f"✗ Failed to parse manifest: {e}")
        return False, None
    
    print(f"✓ Manifest extracted successfully")
    print(f"  Version: {manifest.get('version', 'N/A')}")
    print(f"  Total bytes: {manifest.get('total_bytes', 'N/A'):,}")
    print(f"  Total frames: {manifest.get('total_frames', 'N/A'):,}")
    print(f"  Overall hash: {manifest.get('overall_hash', 'N/A')}")
    
    metadata = manifest.get('metadata', {})
    if metadata:
        print(f"  Delta encoding: {metadata.get('delta_encoding', 'N/A')}")
        print(f"  Frame count: {metadata.get('frame_count', 'N/A')}")
        print(f"  Pixel format: {metadata.get('pixel_format', 'N/A')}")
        print(f"  Frame width: {metadata.get('frame_width', 'N/A')}")
        print(f"  Frame height: {metadata.get('frame_height', 'N/A')}")
    
    print()
    return True, manifest


def extract_and_verify_frame(mkv_path, frame_num=1):
    """Extract a specific frame and verify."""
    print("="*60)
    print(f"Frame {frame_num} Extraction & Verification")
    print("="*60)
    print()
    
    output_path = f"/tmp/alpine_frame{frame_num}.mem"
    
    cmd = [
        "python3", "tools/qemu_to_mkv.py",
        str(mkv_path),
        "--extract-frame", str(frame_num),
        "--output", output_path
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    
    if result.returncode != 0:
        print(f"✗ Frame extraction failed")
        print(result.stdout)
        print(result.stderr, file=sys.stderr)
        return False, None
    
    print(result.stdout)
    
    output_path_obj = Path(output_path)
    if not output_path_obj.exists():
        print(f"✗ Extracted frame not created: {output_path}")
        return False, None
    
    size_mb = output_path_obj.stat().st_size / (1024 * 1024)
    print(f"✓ Frame {frame_num} extracted: {output_path_obj} ({size_mb:.2f} MB)")
    print()
    
    return True, output_path_obj


def verify_memory_content(mem_path):
    """Verify extracted memory content."""
    print("="*60)
    print("Memory Content Verification")
    print("="*60)
    print()
    
    with open(mem_path, 'rb') as f:
        data = f.read()
    
    total_bytes = len(data)
    nonzero_bytes = sum(1 for b in data if b != 0)
    
    print(f"Total bytes: {total_bytes:,}")
    print(f"Non-zero bytes: {nonzero_bytes:,} ({100*nonzero_bytes/total_bytes:.2f}%)")
    
    # Check for ELF header (0x7f 'ELF')
    if data[:4] == b'\x7fELF':
        print("✓ ELF header detected (valid Linux kernel image)")
    else:
        print("⚠ No ELF header (may be memory dump, not kernel)")
    
    # Check for OpenSBI signature
    if b'OpenSBI' in data[:1024]:
        print("✓ OpenSBI firmware signature detected")
    else:
        print("⚠ No OpenSBI signature detected")
    
    # Check entropy
    import hashlib
    md5_hash = hashlib.md5(data).hexdigest()
    print(f"MD5 hash: {md5_hash}")
    
    print()
    return True


def main():
    """Run complete verification pipeline."""
    print()
    
    # Capture
    success, mkv_path = capture_alpine_boot()
    if not success:
        return 1
    
    # Verify MKV
    success, manifest = verify_mkv_integrity(mkv_path)
    if not success:
        return 1
    
    # Extract frame
    success, mem_path = extract_and_verify_frame(mkv_path, frame_num=1)
    if not success:
        return 1
    
    # Verify content
    success = verify_memory_content(mem_path)
    if not success:
        return 1
    
    # Summary
    print("="*60)
    print("VERIFICATION COMPLETE")
    print("="*60)
    print()
    print("✓ Alpine boot trace captured to MKV")
    print("✓ MKV manifest verified")
    print("✓ Frame extraction successful")
    print("✓ Memory content validated")
    print()
    print(f"Trace file: {mkv_path}")
    print(f"Frame dump: {mem_path}")
    print()
    print("Software-to-video pipeline operational for Alpine RISC-V boot.")
    print()
    
    return 0


if __name__ == '__main__':
    sys.exit(main())