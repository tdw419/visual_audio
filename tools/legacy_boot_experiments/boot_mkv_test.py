#!/usr/bin/env python3
"""
Quick boot test - shows serial output, no display.

Usage:
    python3 tools/boot_mkv_test.py
"""

import subprocess
import time
from pathlib import Path
from boot_ubuntu_from_mkv_streaming import MKVNBDServer, MKV_PATH, MKV_DISK_NAME, NBD_PORT
import threading

# Start NBD
print("Starting NBD server...")
nbd = MKVNBDServer(MKV_PATH, MKV_DISK_NAME, NBD_PORT)
t = threading.Thread(target=nbd.start, daemon=True)
t.start()
time.sleep(2)

# Boot with serial output only
qemu_path = MKV_PATH.parent / "qemu_bootstrap"
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
    "-serial", "mon:stdio",
]

print("Running QEMU (30 second test):")
print(" ".join(cmd))
print("\n--- Boot output ---\n")

# Run with timeout, showing output directly
import os
os.execvp(str(qemu_path), cmd)