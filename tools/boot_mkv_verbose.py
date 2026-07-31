#!/usr/bin/env python3
"""
Boot Ubuntu from MKV with extracted QEMU (verbose, serial output).

This version shows both SDL display AND serial console output.

Usage:
    python3 tools/boot_mkv_verbose.py
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
    """Boot Ubuntu from MKV using extracted QEMU (verbose)."""
    print("=" * 70)
    print("Boot Ubuntu from MKV with Extracted QEMU (verbose)")
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

    # QEMU command with extracted QEMU (SDL + serial to file)
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
        "-display", "sdl",
        "-serial", "file:/tmp/qemu_serial.log",
    ]

    print(f"\nCommand: {' '.join(cmd)}")
    print(f"\nSerial output logged to: /tmp/qemu_serial.log")
    print("Starting QEMU... (Ctrl+C to exit)")
    print("SDL window should appear shortly...\n")

    # Launch QEMU with subprocess
    process = subprocess.Popen(cmd, cwd=str(MKV_PATH.parent))

    # Monitor serial log file
    print("--- Serial output (live) ---")
    try:
        import select
        with open("/tmp/qemu_serial.log", "a") as log_file:
            log_file.write("=== Boot started ===\n")
            log_file.flush()

        # Tail the log file
        last_size = 0
        import time as t
        import select
        while True:
            if process.poll() is not None:
                print(f"\nQEMU exited with code {process.returncode}")
                break

            try:
                stat = os.stat("/tmp/qemu_serial.log")
                if stat.st_size > last_size:
                    with open("/tmp/qemu_serial.log", "r") as f:
                        f.seek(last_size)
                        new_data = f.read()
                        if new_data:
                            print(new_data, end="", flush=True)
                        last_size = stat.st_size
                t.sleep(0.1)
            except FileNotFoundError:
                t.sleep(0.1)

    except KeyboardInterrupt:
        print("\nCtrl+C caught, terminating QEMU...")
        process.terminate()
        process.wait(timeout=5)

    return process.returncode if process.returncode is not None else 0


if __name__ == "__main__":
    sys.exit(boot_ubuntu_with_extracted_qemu())