#!/usr/bin/env python3
"""
Self-Hosting MKV Boot - Fully Autonomous

This script boots Ubuntu from the MKV without relying on host QEMU.
All components are extracted from the MKV on-demand.

Usage:
    python3 tools/boot_mkv_self_hosting.py
"""

import os
import sys
import subprocess
import threading
import time
from pathlib import Path

# Import working NBD server from existing code
sys.path.insert(0, str(Path(__file__).parent))
from boot_ubuntu_from_mkv_streaming import MKVNBDServer, MKV_PATH, MKV_DISK_NAME, NBD_PORT


def main():
    print("=" * 70)
    print("Self-Hosting MKV Boot")
    print("=" * 70)

    # Extract QEMU from MKV
    qemu_path = MKV_PATH.parent / "qemu_bootstrap"
    print(f"\nExtracting QEMU from MKV to {qemu_path}...")

    if qemu_path.exists():
        print(f"QEMU already exists at {qemu_path}")
    else:
        result = subprocess.run([
            "python3", "tools/va_container.py", "cat",
            str(MKV_PATH), "qemu_bootstrap",
            "-o", str(qemu_path)
        ], cwd=str(MKV_PATH.parent), capture_output=True, text=True)

        if result.returncode != 0:
            print(f"ERROR: Failed to extract QEMU from MKV: {result.stderr}")
            return 1

        qemu_path.chmod(0o755)
        print(f"✓ QEMU extracted to {qemu_path}")

    # Start NBD server
    print(f"\nInitializing NBD server...")
    nbd_server = MKVNBDServer(MKV_PATH, MKV_DISK_NAME, NBD_PORT)
    print(f"NBD server initialized, serving: {MKV_DISK_NAME}")

    # Start NBD server in background thread
    server_ready = False

    def server_wrapper():
        nonlocal server_ready
        try:
            print("NBD server thread: calling start()")
            nbd_server.start()
            print("NBD server thread: start() returned")
        except Exception as e:
            print(f"NBD server error: {e}")
            import traceback
            traceback.print_exc()

    server_thread = threading.Thread(target=server_wrapper, daemon=True)
    server_thread.start()
    print(f"NBD server thread started")
    time.sleep(0.5)  # Give thread time to initialize

    # Wait for server to be listening
    import socket
    for i in range(20):  # Max 2 seconds
        try:
            test_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            test_sock.settimeout(0.1)
            test_sock.connect(("127.0.0.1", NBD_PORT))
            test_sock.close()
            print(f"NBD server is ready after {i * 0.1:.1f}s")
            break
        except:
            if i == 0:
                print(f"Waiting for port {NBD_PORT} to open...")
            time.sleep(0.1)
    else:
        print("ERROR: NBD server failed to start within 2 seconds")
        return 1

    # Extra delay for socket to be fully ready
    time.sleep(1)

    # Boot with extracted QEMU
    print(f"\nBooting with extracted QEMU...")
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
        "-serial", "mon:stdio",
        "-display", "sdl",
    ]

    print(f"\nQEMU command: {' '.join(cmd)}")
    print("\nStarting QEMU... (Ctrl+C to exit)")

    os.execvp(str(qemu_path), cmd)


if __name__ == "__main__":
    sys.exit(main())