#!/usr/bin/env python3
"""
Boot Ubuntu from MKV with extracted QEMU (nographic, no display).

This version uses -nographic for testing without SDL.

Usage:
    python3 tools/boot_mkv_extracted_nographic.py
"""

import os
import sys
import subprocess
import time
import threading
from pathlib import Path

# Import working code
from boot_ubuntu_from_mkv_streaming import (
    MKVNBDServer, MKV_PATH, MKV_DISK_NAME, NBD_PORT
)


def boot_ubuntu_with_extracted_qemu():
    """Boot Ubuntu from MKV using extracted QEMU (nographic)."""
    print("=" * 70)
    print("Boot Ubuntu from MKV with Extracted QEMU (nographic)")
    print("=" * 70)

    # Extract QEMU from MKV
    qemu_path = MKV_PATH.parent / "qemu_bootstrap"
    print(f"\nChecking for extracted QEMU at {qemu_path}...")

    if not qemu_path.exists():
        print("Extracting QEMU from MKV...")
        result = subprocess.run([
            "python3", "tools/va_container.py", "cat",
            str(MKV_PATH), "qemu_bootstrap",
            "-o", str(qemu_path)
        ], cwd=str(MKV_PATH.parent), capture_output=True, text=True)

        if result.returncode != 0:
            print(f"ERROR: Failed to extract QEMU: {result.stderr}")
            return 1

        qemu_path.chmod(0o755)
        print(f"✓ QEMU extracted to {qemu_path}")
    else:
        print(f"✓ QEMU found at {qemu_path}")

    # Initialize NBD server (loads entry metadata)
    print(f"\nInitializing NBD server...")
    nbd_server = MKVNBDServer(MKV_PATH, MKV_DISK_NAME, NBD_PORT)

    # Start NBD server in background thread
    server_ready = threading.Event()
    server_thread = None

    def server_wrapper():
        try:
            print("NBD server thread: calling start()")
            nbd_server.start()
        except Exception as e:
            print(f"NBD server error: {e}")
            import traceback
            traceback.print_exc()

    server_thread = threading.Thread(target=server_wrapper, daemon=True)
    server_thread.start()
    print("NBD server thread started, waiting for server to initialize...")

    # Wait for server to start (no test socket - it crashes NBD)
    time.sleep(2)
    print("NBD server should be ready")

    # QEMU command with extracted QEMU (nographic)
    print(f"\nBooting with extracted QEMU: {qemu_path}")
    cmd = [
        str(qemu_path),
        "-machine", "virt",
        "-cpu", "rv64",
        "-m", "2048",
        "-smp", "2",
        "-bios", "default",
        "-device", "virtio-gpu-device",
        "-device", "virtio-net-device,netdev=net0",
        "-netdev", "user,id=net0,hostfwd=tcp::2222-:22",
        f"-drive", f"file=nbd:127.0.0.1:{NBD_PORT},format=qcow2,if=virtio",
        "-nographic",
    ]

    print(f"Command: {' '.join(cmd)}")
    print("\nStarting QEMU... (Ctrl+A then X to exit)")

    # Launch QEMU with subprocess (not exec, to show QEMU output)
    process = subprocess.Popen(cmd, cwd=str(MKV_PATH.parent))
    process.wait()
    return process.returncode


if __name__ == "__main__":
    sys.exit(boot_ubuntu_with_extracted_qemu())