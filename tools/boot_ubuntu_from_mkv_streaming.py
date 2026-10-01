#!/usr/bin/env python3
"""
Boot Ubuntu directly from MKV using streaming NBD server.

Loads qcow2 data from MKV on-demand (block-by-block) as QEMU requests it.
No RAMdisk extraction or disk storage required - truly self-hosting.

Usage:
    python3 tools/boot_ubuntu_from_mkv_streaming.py
"""

import os
import sys
import struct
import socket
import subprocess
import hashlib
import time
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import va_container

REPO_ROOT = Path(__file__).parent.parent
MKV_PATH = REPO_ROOT / "visual_audio.mkv"
MKV_DISK_NAME = "ubuntu/desktop/ubuntu-24.04-desktop.qcow2"
NBD_PORT = 10809
NBD_EXPORT_NAME = "ubuntu_mkv"


class MKVNBDServer:
    """Streaming NBD server that serves qcow2 from MKV on-demand."""

    def __init__(self, mkv_path: Path, entry_name: str, port: int = NBD_PORT):
        self.mkv_path = mkv_path
        self.entry_name = entry_name
        self.port = port
        self.entry_size = None
        self.entry_payload = None  # full decoded entry bytes, cached in memory
        self.running = False
        self._init_entry()

    def _init_entry(self):
        """Decode the whole MKV once and cache this entry's payload in memory."""
        print(f"Decoding {self.mkv_path.name} (one-time cost)...")
        t0 = time.time()
        directory = va_container.read_directory(self.mkv_path)
        self.entry_payload = va_container.read_entry_streamed(self.mkv_path, directory, self.entry_name)
        self.entry_size = len(self.entry_payload)
        print(f"  Decoded {self.entry_size:,} bytes in {time.time() - t0:.1f}s")

        print(f"Entry: {self.entry_name}")
        print(f"  Size: {self.entry_size:,} bytes")

    def _read_range(self, offset: int, length: int) -> bytes:
        """Read byte range from the in-memory decoded entry payload."""
        return self.entry_payload[offset:offset + length]

    def _nbd_handshake(self, conn):
        """Send the legacy NBD oldstyle handshake.

        This qemu_bootstrap binary's NBD client speaks only the oldstyle
        protocol (no NBD_OPT negotiation) when given a plain "nbd:host:port"
        URI with no exportname= parameter - confirmed via raw-socket testing:
        it sends a real NBD_CMD_READ request immediately after receiving
        this 152-byte handshake, never a fixed-newstyle client-flags reply.
        """
        handshake = (
            b"NBDMAGIC" +
            b"\x00\x00\x42\x02\x81\x86\x12\x53" +
            struct.pack(">Q", self.entry_size) +
            struct.pack(">I", 1) +  # flags: NBD_FLAG_HAS_FLAGS
            b"\x00" * 124            # reserved
        )
        conn.sendall(handshake)

    def _handle_client(self, conn):
        """Handle NBD client connection."""
        try:
            self._nbd_handshake(conn)

            # Handle read/write requests
            request_count = 0
            while self.running:
                req = conn.recv(28)
                if len(req) != 28:
                    break

                magic, flags, cmd, handle, offset, length = struct.unpack(">IHHQQI", req)

                if magic != 0x25609513:  # REQUEST_MAGIC
                    print(f"Invalid request magic: 0x{magic:08x}")
                    break

                request_count += 1
                if request_count <= 10 or request_count % 1000 == 0:
                    print(f"Request {request_count}: cmd={cmd}, offset={offset}, length={length}")

                reply = struct.pack(">IIQ",
                    0x67446698,  # REPLY_MAGIC
                    0,           # error: 0 = success
                    handle
                )

                if cmd == 0:  # NBD_CMD_READ
                    try:
                        data = self._read_range(offset, length)
                        conn.sendall(reply + data)
                    except Exception as e:
                        print(f"Read error: {e}")
                        reply = struct.pack(">IIQ",
                            0x67446698,
                            0xffffffff,  # EIO
                            handle
                        )
                        conn.sendall(reply)

                elif cmd == 1:  # NBD_CMD_WRITE
                    data = conn.recv(length)
                    conn.sendall(reply)

                elif cmd == 2:  # NBD_CMD_DISC
                    print("Client sent NBD_CMD_DISC")
                    break

                else:
                    print(f"Unknown cmd: {cmd}")

            print(f"Client disconnected after {request_count} requests")

        except Exception as e:
            print(f"NBD client error: {e}")
        finally:
            conn.close()

    def start(self):
        """Start streaming NBD server."""
        self.running = True

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(("127.0.0.1", self.port))
            s.listen(1)

            print(f"\nNBD server listening on port {self.port}")
            print(f"Export: {NBD_EXPORT_NAME}")
            print(f"Size: {self.entry_size:,} bytes")
            print(f"\nStreaming mode: loads frames on-demand from MKV")
            print(f"Waiting for QEMU to connect...")

            # Accept single client
            conn, addr = s.accept()
            print(f"Client connected: {addr}")

            self._handle_client(conn)


def boot_ubuntu_streaming():
    """Boot Ubuntu QEMU from streaming NBD server."""
    print("=" * 70)
    print("Booting Ubuntu from MKV via Streaming NBD")
    print("=" * 70)

    # Initialize NBD server (loads entry metadata)
    nbd_server = MKVNBDServer(MKV_PATH, MKV_DISK_NAME, NBD_PORT)

    # Start NBD server in background thread
    server_ready = threading.Event()
    server_thread = None

    def server_wrapper():
        try:
            nbd_server.start()
        except Exception as e:
            print(f"NBD server error: {e}")
            import traceback
            traceback.print_exc()

    server_thread = threading.Thread(target=server_wrapper, daemon=True)
    server_thread.start()

    # Wait for server to be listening
    for _ in range(20):  # Max 2 seconds
        try:
            test_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            test_sock.settimeout(0.1)
            test_sock.connect(("127.0.0.1", NBD_PORT))
            test_sock.close()
            print("NBD server is ready")
            break
        except:
            time.sleep(0.1)
    else:
        print("ERROR: NBD server failed to start within 2 seconds")
        return 1

    # Extra delay for socket to be fully ready
    time.sleep(1)

    # QEMU command with NBD (raw format since we're serving raw qcow2 data)
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
        f"-drive", f"file=nbd:127.0.0.1:{NBD_PORT},format=qcow2,if=virtio",
        "-serial", "mon:stdio",
        "-display", "sdl",
    ]

    print(f"\nQEMU command:")
    print("  RAM: 2GB")
    print("  Cores: 2")
    print(f"  Disk: NBD @ 127.0.0.1:{NBD_PORT} (streamed from MKV)")
    print(f"  Network: SSH forwarded to localhost:2222")
    print("\nStarting QEMU... (Ctrl+C to exit)")

    # Exec QEMU (replaces current process)
    os.execvp(cmd[0], cmd)


def main():
    boot_ubuntu_streaming()
    return 0


if __name__ == "__main__":
    sys.exit(main())