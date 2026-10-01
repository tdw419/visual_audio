#!/usr/bin/env python3
"""
QEMU Frame Server — captures live QEMU framebuffer output via QMP
`screendump` and streams it as PNG frames to the pxOS Node server
over WebSocket, for display inside a SpatialTile "live" tile.

This does NOT boot Alpine Linux — Alpine's graphical boot is currently
blocked by a documented QEMU 8.2.2 CONFIG pre-check bug (see
QEMU_CONFIG_PATCH.md). This proves the capture -> relay -> browser-tile
texture pipeline against a QEMU target that reliably boots today
(default: no disk attached, so QEMU falls through to its iPXE ROM).
Swap --qemu-args to point at a real bootable target once available.

Usage:
    tools/qemu_frame_server.py [--tile-id 1] [--fps 2] [--ws ws://localhost:3000]
"""
import argparse
import asyncio
import base64
import io
import json
import os
import socket
import subprocess
import time

from PIL import Image
import websockets

DEFAULT_QEMU_ARGS = ["-m", "128", "-vga", "std"]


class QMPClient:
    def __init__(self, sock_path):
        self.sock_path = sock_path
        self.sock = None
        self.f = None

    def connect(self, timeout=10):
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                self.sock.connect(self.sock_path)
                break
            except (FileNotFoundError, ConnectionRefusedError):
                time.sleep(0.1)
        else:
            raise TimeoutError(f"QMP socket {self.sock_path} never appeared")

        self.f = self.sock.makefile("rwb")
        self._recv()  # greeting
        self._send({"execute": "qmp_capabilities"})
        self._recv()

    def _send(self, obj):
        self.f.write(json.dumps(obj).encode() + b"\n")
        self.f.flush()

    def _recv(self):
        line = self.f.readline()
        return json.loads(line)

    def screendump(self, path):
        self._send({"execute": "screendump", "arguments": {"filename": path}})
        return self._recv()


def capture_frame_png(qmp, ppm_path):
    qmp.screendump(ppm_path)
    img = Image.open(ppm_path).convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


async def stream_frames(qemu_args, tile_id, fps, ws_url):
    qmp_sock = f"/tmp/qemu_frame_server_{os.getpid()}.qmp"
    ppm_path = f"/tmp/qemu_frame_server_{os.getpid()}.ppm"

    cmd = [
        "qemu-system-x86_64",
        "-display", "none",
        "-qmp", f"unix:{qmp_sock},server,nowait",
    ] + qemu_args

    print("Launching:", " ".join(cmd))
    proc = subprocess.Popen(cmd)

    try:
        qmp = QMPClient(qmp_sock)
        qmp.connect()
        print("QMP connected.")

        async with websockets.connect(ws_url) as ws:
            print(f"Connected to {ws_url}, streaming tile_id={tile_id} at {fps}fps")
            period = 1.0 / fps
            while proc.poll() is None:
                start = time.time()
                png_bytes = capture_frame_png(qmp, ppm_path)
                await ws.send(json.dumps({
                    "type": "tile_frame",
                    "tile_id": tile_id,
                    "png_b64": base64.b64encode(png_bytes).decode("ascii"),
                }))
                elapsed = time.time() - start
                await asyncio.sleep(max(0, period - elapsed))
    finally:
        proc.terminate()
        for p in (qmp_sock, ppm_path):
            try:
                os.remove(p)
            except OSError:
                pass


def main():
    parser = argparse.ArgumentParser(description="Stream a live QEMU framebuffer into a pxOS SpatialTile")
    parser.add_argument("--tile-id", type=int, default=1, help="Tile ID this stream targets (must be registered as a 'live' tile in app.js)")
    parser.add_argument("--fps", type=float, default=2.0)
    parser.add_argument("--ws", default="ws://localhost:3000")
    parser.add_argument("--qemu-arg", action="append", dest="qemu_args", default=None,
                         help="Extra QEMU arg (repeatable). Defaults to a disk-less boot (iPXE ROM) to prove the pipeline.")
    args = parser.parse_args()

    qemu_args = args.qemu_args if args.qemu_args else DEFAULT_QEMU_ARGS
    asyncio.run(stream_frames(qemu_args, args.tile_id, args.fps, args.ws))


if __name__ == "__main__":
    main()
