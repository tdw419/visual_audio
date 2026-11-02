#!/usr/bin/env python3
"""
Boot Ubuntu directly from MKV using qemu-nbd.

Extracts disk to /dev/shm and serves via NBD on localhost:10809.
QEMU boots from NBD server.

Usage:
    python3 tools/boot_ubuntu_from_mkv_nbd.py
"""

import os
import sys
import subprocess
import signal
import atexit
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
MKV_PATH = REPO_ROOT / "visual_audio.mkv"
MKV_DISK_NAME = "ubuntu/desktop/ubuntu-24.04-desktop.qcow2"
RAMDISK_DISK = Path("/dev/shm/ubuntu_mkv_nbd.qcow2")
NBD_PORT = 10809
NBD_DEVICE = f"/dev/nbd0"

nbd_server_pid = None


def cleanup():
    """Cleanup NBD server on exit."""
    global nbd_server_pid
    if nbd_server_pid:
        print("\nCleaning up NBD server...")
        try:
            os.kill(nbd_server_pid, signal.SIGTERM)
            os.waitpid(nbd_server_pid, 0)
        except:
            pass

        # Disconnect NBD device
        subprocess.run(["sudo", "qemu-nbd", "-d", NBD_DEVICE], stderr=subprocess.DEVNULL)

        # Remove ramdisk
        if RAMDISK_DISK.exists():
            RAMDISK_DISK.unlink()


def extract_to_ramdisk():
    """Extract Ubuntu disk to RAMdisk."""
    print("=" * 70)
    print("Extracting Ubuntu from MKV to RAMdisk for NBD")
    print("=" * 70)
    print(f"  MKV: {MKV_PATH}")
    print(f"  Entry: {MKV_DISK_NAME}")
    print(f"  Output: {RAMDISK_DISK}")
    print()

    # Extract using va_container.py
    result = subprocess.run(
        ["python3", "tools/va_container.py", "cat", str(MKV_PATH), MKV_DISK_NAME, "-o", str(RAMDISK_DISK)],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT)
    )

    if result.returncode != 0:
        print(f"Failed to extract: {result.stderr}")
        return False

    print(f"Extracted: {RAMDISK_DISK.stat().st_size:,} bytes to RAMdisk")
    return True


def start_nbd_server():
    """Start qemu-nbd server."""
    global nbd_server_pid

    print("\n" + "=" * 70)
    print("Starting NBD server")
    print("=" * 70)

    # Start qemu-nbd in background
    cmd = [
        "qemu-nbd",
        "-f", "qcow2",
        "--socket", f"/tmp/nbd_mkv_{NBD_PORT}.sock",
        "--read-only",
        str(RAMDISK_DISK)
    ]

    print(f"  Serving: {RAMDISK_DISK}")
    print(f"  Socket: /tmp/nbd_mkv_{NBD_PORT}.sock")
    print()

    # Use TCP socket (writable for QEMU)
    tcp_cmd = [
        "qemu-nbd",
        "-f", "qcow2",
        "-b", "127.0.0.1",
        "-p", str(NBD_PORT),
        str(RAMDISK_DISK)
    ]

    print(f"  Starting: {' '.join(tcp_cmd)}")

    nbd_server = subprocess.Popen(tcp_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    nbd_server_pid = nbd_server.pid

    # Register cleanup
    atexit.register(cleanup)

    # Wait for server to start
    import time
    time.sleep(1)

    if nbd_server.poll() is not None:
        print("Failed to start NBD server")
        return False

    print("✓ NBD server started")
    return True


def boot_ubuntu():
    """Boot Ubuntu QEMU from NBD."""
    print("\n" + "=" * 70)
    print("Booting Ubuntu QEMU from NBD")
    print("=" * 70)

    # QEMU command with NBD
    cmd = [
        "qemu-system-riscv64",
        "-machine", "virt",
        "-cpu", "rv64",
        "-m", "2048",  # 2GB RAM
        "-smp", "2",  # 2 cores
        "-bios", "default",
        "-device", "virtio-gpu-device",
        "-device", "virtio-net-device,netdev=net0",
        "-netdev", "user,id=net0,hostfwd=tcp::2222-:22",
        f"-drive", f"file=nbd:127.0.0.1:{NBD_PORT},if=virtio",
        "-serial", "mon:stdio",
        "-display", "sdl",
    ]

    print(f"  RAM: 2GB")
    print(f"  Cores: 2")
    print(f"  Disk: NBD @ 127.0.0.1:{NBD_PORT} (served from RAMdisk)")
    print(f"  Network: SSH forwarded to localhost:2222")
    print("\nStarting QEMU... (Ctrl+C to exit)")

    # Exec QEMU (replaces current process)
    os.execvp(cmd[0], cmd)


def main():
    # Extract to RAMdisk
    if not extract_to_ramdisk():
        return 1

    # Start NBD server
    if not start_nbd_server():
        return 1

    # Boot Ubuntu
    boot_ubuntu()
    return 0


if __name__ == "__main__":
    sys.exit(main())