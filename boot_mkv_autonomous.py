#!/usr/bin/env python3
"""
Self-hosting boot script for MKV - extracts QEMU and boots autonomously.

This script runs entirely from the MKV container, extracting QEMU and
booting Ubuntu without relying on host system QEMU.

Usage:
    python3 boot_mkv_self_hosting.py
"""

import os
import sys
import struct
import socket
import subprocess
import threading
import time
from pathlib import Path

MKV_PATH = Path(__file__).parent / "visual_audio.mkv"
NBD_PORT = 10809
MKV_DISK_NAME = "ubuntu/desktop/ubuntu-24.04-desktop.qcow2"


class MKVNBDServer:
    """Streaming NBD server that serves qcow2 from MKV on-demand."""

    def __init__(self, mkv_path: Path, entry_name: str, port: int = NBD_PORT):
        self.mkv_path = mkv_path
        self.entry_name = entry_name
        self.port = port
        self.entry_size = None
        self.entry_frames = None
        self.frame_cache = {}
        self.running = False
        self._init_entry()

    def _init_entry(self):
        """Initialize entry metadata."""
        result = subprocess.run(
            ["python3", "tools/va_container.py", "ls", str(self.mkv_path)],
            capture_output=True, text=True,
            cwd=str(self.mkv_path.parent)
        )

        if result.returncode != 0:
            raise RuntimeError(f"Failed to load MKV directory: {result.stderr}")

        for line in result.stdout.split('\n'):
            if self.entry_name in line:
                import re
                match = re.search(r'frames (\d+)\.\.(\d+)', line)
                if match:
                    start = int(match.group(1))
                    end = int(match.group(2))
                    self.entry_frames = (start, end - start + 1)

                match = re.search(r'(\d+) bytes', line)
                if match:
                    self.entry_size = int(match.group(1))
                break

        if not self.entry_frames or not self.entry_size:
            raise RuntimeError(f"Entry {self.entry_name} not found in MKV")

        print(f"Entry: {self.entry_name}")
        print(f"  Size: {self.entry_size:,} bytes")
        print(f"  Frames: {self.entry_frames[0]}..{self.entry_frames[0] + self.entry_frames[1] - 1}")

    def _load_frame(self, frame_id: int) -> bytes:
        """Load a specific frame from MKV."""
        if frame_id in self.frame_cache:
            return self.frame_cache[frame_id]

        result = subprocess.run(
            ["python3", "tools/va_container.py", "read-frame", str(self.mkv_path),
             str(frame_id), "-o", f"/tmp/mkv_frame_{frame_id}.png"],
            capture_output=True, text=True,
            cwd=str(self.mkv_path.parent)
        )

        if result.returncode != 0:
            raise RuntimeError(f"Failed to load frame {frame_id}: {result.stderr}")

        from PIL import Image
        img = Image.open(f"/tmp/mkv_frame_{frame_id}.png")
        data = img.tobytes()
        os.unlink(f"/tmp/mkv_frame_{frame_id}.png")

        self.frame_cache[frame_id] = data
        return data

    def _read_range(self, offset: int, length: int) -> bytes:
        """Read byte range from MKV."""
        result = bytearray()
        FRAME_SIZE = 450 * 450 * 3
        frame_start, frame_count = self.entry_frames

        first_frame_idx = offset // FRAME_SIZE
        last_frame_idx = (offset + length - 1) // FRAME_SIZE

        for frame_idx in range(first_frame_idx, last_frame_idx + 1):
            if frame_idx >= frame_count:
                break
            frame_id = frame_start + frame_idx
            frame_data = self._load_frame(frame_id)
            frame_offset_in_entry = frame_idx * FRAME_SIZE
            read_offset = max(0, offset - frame_offset_in_entry)
            read_length = min(FRAME_SIZE - read_offset, length - len(result))
            result.extend(frame_data[read_offset:read_offset + read_length])

        return bytes(result)

    def _nbd_handshake(self, conn):
        """Perform NBD handshake."""
        handshake = b"NBDMAGIC" + b"\x00\x00\x42\x02\x81\x86\x12\x53"
        flags = struct.pack(">H", 1)
        conn.sendall(handshake + flags)

        client_flags = conn.recv(4)
        if len(client_flags) != 4:
            return None
        return struct.unpack(">I", client_flags)[0]

    def _handle_client(self, conn):
        """Handle NBD client."""
        try:
            client_flags = self._nbd_handshake(conn)
            if client_flags is None:
                return

            print(f"Client connected, flags: 0x{client_flags:08x}")

            # Handle NBD_OPT_GO
            while True:
                opt_header = conn.recv(16)
                if len(opt_header) != 16:
                    break

                opt_magic, opt_cmd, opt_len = struct.unpack(">IIQ", opt_header)

                if opt_magic != 0x49484156:
                    break

                if opt_cmd == 0x7fe09902:  # NBD_OPT_GO
                    name_len = struct.unpack(">I", conn.recv(4))[0]
                    conn.recv(name_len)
                    nr_infos_bytes = conn.recv(2)
                    if len(nr_infos_bytes) < 2:
                        break
                    nr_infos = struct.unpack(">H", nr_infos_bytes)[0]

                    for _ in range(nr_infos if nr_infos else 0):
                        conn.recv(4)

                    reply = struct.pack(">IIQ", 0x0003e889, opt_cmd, 0x00000000, 0)
                    conn.sendall(reply)
                    break

            # Handle requests
            request_count = 0
            while self.running:
                req = conn.recv(28)
                if len(req) != 28:
                    break

                magic, cmd, handle, offset, length = struct.unpack(">IIQII", req)
                if magic != 0x25609513:
                    break

                request_count += 1
                if request_count <= 10 or request_count % 1000 == 0:
                    print(f"Request {request_count}: cmd={cmd}, offset={offset}, length={length}")

                reply = struct.pack(">IIQ", 0x67446698, 0, handle)

                if cmd == 0:  # NBD_CMD_READ
                    try:
                        data = self._read_range(offset, length)
                        conn.sendall(reply + data)
                    except Exception as e:
                        print(f"Read error: {e}")
                        reply = struct.pack(">IIQ", 0x67446698, 0xffffffff, handle)
                        conn.sendall(reply)

                elif cmd == 1:  # NBD_CMD_WRITE
                    conn.recv(length)
                    conn.sendall(reply)

                elif cmd == 2:  # NBD_CMD_DISC
                    break

            print(f"Client disconnected after {request_count} requests")

        except Exception as e:
            print(f"NBD client error: {e}")
        finally:
            conn.close()

    def start(self):
        """Start server."""
        self.running = True

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(("127.0.0.1", self.port))
            s.listen(1)

            print(f"\nNBD server listening on port {self.port}")

            conn, addr = s.accept()
            print(f"Client connected: {addr}")
            self._handle_client(conn)


def main():
    print("=" * 70)
    print("Self-Hosting MKV Boot")
    print("=" * 70)

    # Check for extracted QEMU
    qemu_path = Path(__file__).parent / "qemu_bootstrap"

    if not qemu_path.exists():
        print("\nQEMU not found. Extracting from MKV...")

        # Extract QEMU
        result = subprocess.run([
            "python3", "tools/va_container.py", "cat",
            str(MKV_PATH), "qemu_bootstrap",
            "-o", str(qemu_path)
        ], cwd=str(MKV_PATH.parent), capture_output=True, text=True)

        if result.returncode != 0:
            print(f"ERROR: Failed to extract QEMU from MKV: {result.stderr}")
            return 1

        # Make executable
        qemu_path.chmod(0o755)
        print(f"✓ QEMU extracted to {qemu_path}")

    # Start NBD server
    nbd_server = MKVNBDServer(MKV_PATH, MKV_DISK_NAME, NBD_PORT)

    # Start NBD server in background
    server_thread = threading.Thread(target=nbd_server.start, daemon=True)
    server_thread.start()

    # Wait for NBD server to be ready
    print(f"Waiting for NBD server to start on port {NBD_PORT}...")
    for i in range(20):  # Max 10 seconds
        try:
            test_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            test_sock.settimeout(0.5)
            test_sock.connect(("127.0.0.1", NBD_PORT))
            test_sock.close()
            print(f"✓ NBD server ready after {i * 0.5:.1f}s")
            break
        except (ConnectionRefusedError, socket.timeout):
            time.sleep(0.5)
    else:
        print("ERROR: NBD server failed to start within 10 seconds")
        return 1

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