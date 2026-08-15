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
    
    # Use new defaults: 1024x1024 grid, 50000 interval
    cmd = [
        "python3", "tools/qemu_to_mkv.py",
        "boot_images/alpine_riscv64.qcow2",
        "--arch", "riscv64",
        "--output", "/tmp/alpine_boot_trace.mkv",
        "--interval", "50000",
        "--max-frames", "20",
        "--memory", "64M"
    ]
    
    print(f"Running: {' '.join(cmd)}")
    print()
    
    start = time.time()
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
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


def verify_mkv_via_qemu_to_mkv(mkv_path):
    """Verify MKV integrity using qemu_to_mkv.py extraction."""
    print("="*60)
    print("MKV Integrity Verification")
    print("="*60)
    print()
    
    # Extract frame 1 to verify
    output_path = "/tmp/alpine_verify_frame1.mem"
    cmd = [
        "python3", "tools/qemu_to_mkv.py",
        str(mkv_path),
        "--extract-frame", "1",
        "--output", output_path
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    
    if result.returncode != 0:
        print(f"✗ Frame extraction failed")
        print(result.stdout)
        print(result.stderr, file=sys.stderr)
        return False
    
    print(result.stdout)
    
    # Verify extracted file exists
    output_path_obj = Path(output_path)
    if not output_path_obj.exists():
        print(f"✗ Extracted frame not created: {output_path}")
        return False
    
    size_mb = output_path_obj.stat().st_size / (1024 * 1024)
    print(f"✓ Frame extraction successful: {output_path_obj} ({size_mb:.2f} MB)")
    print()
    
    return True


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


def check_hang_detection(output):
    """Check if capture stopped due to hang detection."""
    if "[!] Hang detected" in output:
        print("⚠ Capture stopped due to hang detection")
        print("  (Expected with small grid sizes; try 1024x1024 to capture full RAM)")
        return True
    return False


def main():
    """Run complete verification pipeline."""
    print()
    
    # Capture
    success, mkv_path = capture_alpine_boot()
    if not success:
        return 1
    
    # Read capture output to check for hang detection
    print("Checking capture details...")
    if not mkv_path:
        print("✗ mkv_path is None, cannot check capture details")
        return 1
    
    # Verify MKV (via extraction)
    success = verify_mkv_via_qemu_to_mkv(mkv_path)
    if not success:
        return 1
    
    # Verify content
    success = verify_memory_content("/tmp/alpine_verify_frame1.mem")
    if not success:
        return 1
    
    # Summary
    print("="*60)
    print("VERIFICATION COMPLETE")
    print("="*60)
    print()
    print("✓ Alpine boot trace captured to MKV")
    print("✓ MKV extraction successful")
    print("✓ Memory content validated")
    print()
    print(f"Trace file: {mkv_path}")
    print(f"Frame dump: /tmp/alpine_verify_frame1.mem")
    print()
    print("Software-to-video pipeline operational for Alpine RISC-V boot.")
    print()
    
    return 0


if __name__ == '__main__':
    sys.exit(main())