#!/usr/bin/env python3
"""
Boot Ubuntu from MKV - Serial Output to Terminal (subprocess version).

This shows ALL boot output in the terminal (no SDL window).

Usage:
    python3 tools/boot_mkv_serial_subprocess.py
"""

import os
import sys
import subprocess
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

    # Start NBD server as subprocess
    print(f"\nStarting NBD server as subprocess...")
    nbd_script = Path(__file__).parent / "mkv_nbd_server.py"
    nbd_process = subprocess.Popen(
        ["python3", str(nbd_script)],
        cwd=str(MKV_PATH.parent),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    print(f"NBD server PID: {nbd_process.pid}")
    print("Waiting 3 seconds for NBD to start...")
    import time
    time.sleep(3)

    # Check if NBD server is still running
    if nbd_process.poll() is not None:
        print(f"ERROR: NBD server exited early")
        stdout, stderr = nbd_process.communicate()
        print(f"stdout: {stdout}")
        print(f"stderr: {stderr}")
        return 1

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
    try:
        os.execvp(str(qemu_path), cmd)
    finally:
        nbd_process.terminate()


if __name__ == "__main__":
    sys.exit(main())