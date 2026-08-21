#!/usr/bin/env python3
"""
Boot Ubuntu from MKV - Serial Output to Terminal (working version).

This shows ALL boot output in the terminal (no SDL window).

Usage:
    python3 tools/boot_mkv_works.py
"""

import os
import sys
import pty
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

    # Initialize and start NBD server
    print(f"\nInitializing NBD server...")
    nbd_server = MKVNBDServer(MKV_PATH, MKV_DISK_NAME, NBD_PORT)

    # Start NBD in daemon thread that won't die on exec
    def run_nbd():
        try:
            nbd_server.start()
        except Exception as e:
            print(f"NBD error: {e}")
            import traceback
            traceback.print_exc()

    # QEMU's "-serial mon:stdio" fully buffers its output when stdout isn't a
    # real TTY, so redirecting to a file or pipe silently swallows all boot
    # output. Give QEMU a real pty and pump it to our own stdout instead.
    master_fd, slave_fd = pty.openpty()

    # fork(): returns 0 in the new child process, the child's PID in this
    # (the original/parent) process.
    pid = os.fork()

    if pid == 0:
        # Child: becomes QEMU, attached to the pty slave.
        os.close(master_fd)
        os.setsid()
        os.dup2(slave_fd, 0)
        os.dup2(slave_fd, 1)
        os.dup2(slave_fd, 2)
        if slave_fd > 2:
            os.close(slave_fd)

        import time
        time.sleep(3)

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

        os.execvp(str(qemu_path), cmd)
    else:
        # Parent: runs the NBD server and pumps QEMU's pty output to our stdout.
        os.close(slave_fd)
        print(f"[Parent] Starting NBD server (QEMU PID: {pid})")

        def pump_pty():
            while True:
                try:
                    data = os.read(master_fd, 4096)
                except OSError:
                    break
                if not data:
                    break
                os.write(1, data)

        threading.Thread(target=pump_pty, daemon=True).start()

        try:
            nbd_server.start()
        except Exception as e:
            print(f"NBD error: {e}")
            import traceback
            traceback.print_exc()

        _, status = os.waitpid(pid, 0)
        print(f"\nQEMU exited with status {status}")
        return status >> 8 if os.WIFEXITED(status) else 1


if __name__ == "__main__":
    sys.exit(main())