#!/usr/bin/env python3
"""
vac3_real_capture.py - Build a VAC3 bundle whose Z=1 layer is real captured
RAM from a live QEMU guest, instead of the synthetic patterns in
vac3_demo.py.

Z=0 (display) stays a synthetic placeholder UI mockup -- it represents what
a human-facing framebuffer would show, which this project doesn't render yet.
Z=1 (ram_substrate) is real: dumped via QMP dump-guest-memory from a running
QEMU guest and Hilbert-mapped, using the same primitives already verified in
tools/qemu_to_mkv.py.
Z=2 (diagnostics) stays a synthetic crash marker placeholder.

Usage:
    python3 tools/vac3_real_capture.py boot_images/alpine_riscv64.qcow2 \
        --output vac3_real.mkv --width 256 --height 256 --memory 64M
"""

import argparse
import asyncio
import os
import sys
import tempfile
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

from dense_encoder_video import encode_mkv
from qemu_to_mkv import QMPClient, map_ram_to_pixels
from vac3_demo import create_display_layer, create_diagnostics_layer


async def capture_real_z1(disk_path: str, arch: str, memory: str,
                           width: int, height: int) -> tuple[bytes, int]:
    """Boot QEMU, pause it, dump real guest memory, Hilbert-map it into a
    tiled width x height RGB24 layer. Returns (raw pixel bytes, num_tiles)."""
    qmp_socket = "/tmp/vac3_real_qmp.sock"
    if os.path.exists(qmp_socket):
        os.remove(qmp_socket)

    qemu_binary = f"qemu-system-{arch}"
    cmd = [
        qemu_binary, "-m", memory, "-nographic",
        "-qmp", f"unix:{qmp_socket},server,nowait",
        "-M", "virt",
        "-drive", f"file={disk_path},format=qcow2,if=virtio",
        "-bios", "default",
    ]

    print(f"[1] Starting QEMU: {' '.join(cmd)}")
    qemu_proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    for _ in range(30):
        if os.path.exists(qmp_socket):
            break
        await asyncio.sleep(1)
    else:
        qemu_proc.kill()
        raise RuntimeError("QMP socket never appeared")

    print("[2] Connecting QMP + pausing guest...")
    qmp = QMPClient(qmp_socket)
    await qmp.connect()
    await qmp.pause()

    with tempfile.TemporaryDirectory() as tmpdir:
        dump_path = Path(tmpdir) / "z1_ram.dump"
        print("[3] Dumping real guest memory via QMP dump-guest-memory...")
        await qmp.dump_guest_memory(str(dump_path))
        with open(dump_path, "rb") as f:
            ram_data = f.read()

    print(f"    Got {len(ram_data)} bytes of real RAM")

    print("[4] Shutting down QEMU...")
    await qmp.execute({"execute": "quit"})
    await qemu_proc.wait()

    print(f"[5] Hilbert-mapping entire RAM into tiled Z=1 layer...")
    tile_size = width * height * 3
    num_tiles = (len(ram_data) + tile_size - 1) // tile_size
    
    if len(ram_data) % tile_size != 0:
        ram_data += b'\x00' * (tile_size - (len(ram_data) % tile_size))
        
    tiles_bytes = []
    for tile_idx in range(num_tiles):
        tile_ram = ram_data[tile_idx * tile_size : (tile_idx + 1) * tile_size]
        pixels = map_ram_to_pixels(tile_ram, width, height)
        tiles_bytes.append(pixels.tobytes())
        
    return b''.join(tiles_bytes), num_tiles


def build_vac3_bundle(z1_ram_bytes: bytes, num_tiles: int, output_path: str, width: int, height: int):
    print("\n[6] Building Z=0 (synthetic placeholder) and Z=2 (synthetic placeholder)...")
    z0_display = create_display_layer(width, height)
    z2_diagnostics = create_diagnostics_layer(width, height)

    total_payload = z0_display + z1_ram_bytes + z2_diagnostics

    manifest = {
        "vac3_version": "1.0",
        "layers": [
            {"z_index": 0, "name": "display", "width": width, "height": height,
             "format": "RGB24", "source": "synthetic_placeholder",
             "offset": 0, "size": len(z0_display)},
            {"z_index": 1, "name": "ram_substrate", "width": width, "height": height,
             "format": "RGB24", "hilbert_mapped": True,
             "source": "real_qemu_dump_guest_memory", "tiles": num_tiles,
             "offset": len(z0_display), "size": len(z1_ram_bytes)},
            {"z_index": 2, "name": "diagnostics", "width": width, "height": height,
             "format": "RGB24", "source": "synthetic_placeholder",
             "offset": len(z0_display) + len(z1_ram_bytes), "size": len(z2_diagnostics)},
        ],
        "total_layers": 3,
    }

    print(f"[7] Encoding VAC3 bundle to {output_path}...")
    encode_mkv(payload=total_payload, output_path=output_path, metadata=manifest)
    print(f"\n✓ VAC3 bundle with REAL Z=1 written: {output_path}")


def main():
    parser = argparse.ArgumentParser(description="Build a VAC3 bundle with real captured RAM in Z=1")
    parser.add_argument("disk", help="QCOW2 disk image to boot")
    parser.add_argument("--output", "-o", default="vac3_real.mkv")
    parser.add_argument("--arch", default="riscv64")
    parser.add_argument("--memory", default="64M")
    parser.add_argument("--width", type=int, default=256)
    parser.add_argument("--height", type=int, default=256)
    args = parser.parse_args()

    z1_bytes, num_tiles = asyncio.run(
        capture_real_z1(args.disk, args.arch, args.memory, args.width, args.height)
    )
    build_vac3_bundle(z1_bytes, num_tiles, args.output, args.width, args.height)


if __name__ == "__main__":
    main()
