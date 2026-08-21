#!/usr/bin/env python3
"""
Boot Ubuntu from MKV with extracted QEMU - Serial to terminal.

This shows ALL boot output in the terminal (no SDL window).

Usage:
    python3 tools/boot_mkv_serial.py
"""

import os
import sys
import subprocess
import threading
from pathlib import Path

# Import working code
from boot_ubuntu_from_mkv_streaming import (
    MKVNBDServer, MKV_PATH, MKV_DISK_NAME, NBD_PORT
)


def main():
    print("=" * 70)
    print("Boot Ubuntu from MKV - Serial Output to Terminal")
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

    # Fork: child runs NBD, parent runs QEMU
    print(f"\nForking to start NBD server...")
    pid = os.fork()

    if pid == 0:
        # Child process - runs NBD server
        print(f"[NBD] PID: {os.getpid()}, starting NBD server...")
        nbd_server = MKVNBDServer(MKV_PATH, MKV_DISK_NAME, NBD_PORT)
        try:
            nbd_server.start()
        except Exception as e:
            print(f"[NBD] Error: {e}")
            import traceback
            traceback.print_exc()
        sys.exit(0)
    else:
        # Parent process - waits then execs QEMU
        print(f"[Parent] NBD server PID: {pid}")
        print(f"[Parent] Waiting 3 seconds for NBD to start...")
        import time
        time.sleep(3)

        # QEMU command - serial to terminal, no display
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
            "-display", "none",
            "-serial", "mon:stdio",
        ]

        print(f"\nQEMU command: {' '.join(cmd)}")
        print("\n" + "=" * 70)
        print("QEMU Boot Output (Ctrl+A then X to exit)")
        print("=" * 70 + "\n")

        # Execute QEMU directly - replaces Python process
        os.execvp(str(qemu_path), cmd)


if __name__ == "__main__":
    sys.exit(main())