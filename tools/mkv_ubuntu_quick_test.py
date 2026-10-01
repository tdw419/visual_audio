#!/usr/bin/env python3
"""
Quick Ubuntu MKV boot test - extract and boot QEMU.
"""

import os
import sys
import subprocess
import time
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
MKV_PATH = REPO_ROOT / "visual_audio.mkv"
MKV_DISK_NAME = "ubuntu/desktop/ubuntu-24.04-desktop.qcow2"
OUTPUT_DISK = REPO_ROOT / "ubuntu_verify.qcow2"

def main():
    print("=" * 70)
    print("Ubuntu MKV Boot Test")
    print("=" * 70)
    
    # Extract
    print(f"\n[1/2] Extracting {MKV_DISK_NAME} from MKV...")
    t0 = time.time()
    result = subprocess.run([
        "python3", "tools/va_container.py", "cat",
        str(MKV_PATH), MKV_DISK_NAME, "-o", str(OUTPUT_DISK)
    ], cwd=str(REPO_ROOT), capture_output=True, text=True)
    
    if result.returncode != 0:
        print(f"ERROR: {result.stderr}")
        return 1
    
    print(f"Extracted {OUTPUT_DISK.stat().st_size:,} bytes in {time.time() - t0:.1f}s")
    
    # Boot QEMU (nographic, timeout after 40s)
    print(f"\n[2/2] Booting QEMU (40s timeout to see login prompt)...")
    cmd = [
        "qemu-system-riscv64",
        "-machine", "virt",
        "-cpu", "rv64",
        "-m", "2048",
        "-smp", "2",
        "-bios", "default",
        "-device", "virtio-gpu-device",
        "-device", "virtio-net-device,netdev=net0",
        "-netdev", "user,id=net0,hostfwd=tcp::2222-:22",
        f"-drive", f"file={OUTPUT_DISK},if=virtio,format=qcow2",
        "-nographic",
        "-serial", "mon:stdio",
    ]
    
    print(f"  Running: {' '.join(cmd[:8])}...")
    print(f"  Ctrl+C to exit")
    print()
    
    try:
        proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        
        # Read output for 40 seconds or until login prompt
        start = time.time()
        while time.time() - start < 40:
            try:
                line = proc.stdout.readline()
                if not line:
                    break
                print(line, end='')
                if "login:" in line:
                    print(f"\n✓ Login prompt reached in {time.time() - start:.1f}s")
                    break
            except KeyboardInterrupt:
                break
        
        proc.terminate()
        proc.wait(timeout=2)
        return 0
        
    except Exception as e:
        print(f"ERROR: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())