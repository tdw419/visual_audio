#!/usr/bin/env python3
"""
Boot Ubuntu directly from MKV using RAMdisk.

Extracts disk to /dev/shm (tmpfs) and boots QEMU.
No permanent disk extraction required.

Usage:
    python3 tools/boot_ubuntu_from_mkv_ramdisk.py
"""

import os
import sys
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
MKV_PATH = REPO_ROOT / "visual_audio.mkv"
MKV_DISK_NAME = "ubuntu/desktop/ubuntu-24.04-desktop.qcow2"
RAMDISK_DISK = Path("/dev/shm/ubuntu_mkv.qcow2")


def extract_to_ramdisk():
    """Extract Ubuntu disk to RAMdisk."""
    print("=" * 70)
    print("Extracting Ubuntu from MKV to RAMdisk")
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


def boot_ubuntu():
    """Boot Ubuntu QEMU from RAMdisk."""
    print("\n" + "=" * 70)
    print("Booting Ubuntu QEMU from RAMdisk")
    print("=" * 70)

    # QEMU command for Ubuntu RISC-V
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
        "-drive", f"file={RAMDISK_DISK},if=none,format=qcow2,id=hd0",
        "-device", "virtio-blk-pci,drive=hd0",
        "-serial", "mon:stdio",
        "-display", "sdl",
    ]

    print(f"  RAM: 2GB")
    print(f"  Cores: 2")
    print(f"  Disk: {RAMDISK_DISK} (RAMdisk)")
    print(f"  Network: SSH forwarded to localhost:2222")
    print("\nStarting QEMU... (Ctrl+C to exit)")
    print("NOTE: RAMdisk disk persists in /dev/shm until reboot or manual deletion")

    # Exec QEMU (replaces current process)
    os.execvp(cmd[0], cmd)


def main():
    import os

    # Extract to RAMdisk
    if not extract_to_ramdisk():
        return 1

    # Boot Ubuntu
    boot_ubuntu()
    return 0


if __name__ == "__main__":
    sys.exit(main())