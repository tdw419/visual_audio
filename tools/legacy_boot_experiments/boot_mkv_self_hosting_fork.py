#!/usr/bin/env python3
"""
Self-Hosting MKV Boot - Fully Autonomous (fork version with debug)

This script boots Ubuntu from the MKV without relying on host QEMU.
All components are extracted from the MKV on-demand.

Usage:
    python3 tools/boot_mkv_self_hosting_fork.py
"""

import os
import sys
import subprocess
import time
from pathlib import Path

# Import working NBD server from existing code
sys.path.insert(0, str(Path(__file__).parent))
from boot_ubuntu_from_mkv_streaming import MKVNBDServer, MKV_PATH, MKV_DISK_NAME, NBD_PORT


def run_nbd_server():
    """Run NBD server in child process."""
    try:
        print(f"[NBD] Initializing NBD server for {MKV_DISK_NAME}...")
        nbd_server = MKVNBDServer(MKV_PATH, MKV_DISK_NAME, NBD_PORT)
        print(f"[NBD] Starting NBD server on port {NBD_PORT}...")
        nbd_server.start()
        print(f"[NBD] NBD server start() returned")
    except Exception as e:
        print(f"[NBD] Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


def main():
    print("=" * 70)
    print("Self-Hosting MKV Boot (fork version)")
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

    # Fork: child runs NBD, parent waits then execs QEMU
    print(f"\nForking to create NBD server process...")
    pid = os.fork()

    if pid == 0:
        # Child process - runs NBD server
        print(f"[Child] PID: {os.getpid()}, starting NBD server...")
        run_nbd_server()
        print(f"[Child] Exiting")
        sys.exit(0)
    else:
        # Parent process - waits for NBD then launches QEMU
        print(f"[Parent] Child PID: {pid}")
        print(f"[Parent] Waiting for port {NBD_PORT} to open...")

        import socket
        for i in range(30):  # Max 3 seconds
            try:
                test_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                test_sock.settimeout(0.1)
                test_sock.connect(("127.0.0.1", NBD_PORT))
                test_sock.close()
                print(f"[Parent] NBD server is ready after {i * 0.1:.1f}s")
                break
            except:
                time.sleep(0.1)
        else:
            print("[Parent] ERROR: NBD server failed to start within 3 seconds")
            print("[Parent] Killing child process...")
            os.kill(pid, 9)
            return 1

        # Extra delay for socket to be fully ready
        time.sleep(1)

        # Boot with extracted QEMU
        print(f"\n[Parent] Booting with extracted QEMU...")
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

        # Exec QEMU - replaces this process
        os.execvp(str(qemu_path), cmd)


if __name__ == "__main__":
    sys.exit(main())