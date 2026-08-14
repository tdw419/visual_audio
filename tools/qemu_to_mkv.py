#!/usr/bin/env python3
"""
qemu_to_mkv.py - Encode Linux boot execution as spatial video

Architecture: "Hyper-Dimensional Video Boot"
  1. QEMU QMP: Pause every N instructions, dump guest memory (CPU + RAM)
  2. Hilbert Curve: Map 1D RAM to 2D pixels preserving spatial locality
  3. FFV1 MKV: Lossless encoding - each frame = one execution snapshot

This transforms OS execution into a visual time-series:
  - Play in VLC: Watch kernel decompression as entropy waves
  - Pause on frame: Extract exact CPU/RAM state at that millisecond
  - Diff frames: Visual debugging of execution divergence

Usage:
    # Boot Alpine Linux and capture trace
    python3 tools/qemu_to_mkv.py alpine_riscv64.qcow2 \
        --arch riscv64 \
        --memory 512M \
        --output alpine_boot_trace.mkv \
        --interval 10000 \
        --max-frames 500

    # Play the trace in VLC
    vlc alpine_boot_trace.mkv

    # Extract frame 120 back to QEMU snapshot
    python3 tools/qemu_to_mkv.py alpine_boot_trace.mkv \
        --extract-frame 120 \
        --output snapshot_frame120.mem
"""

import argparse
import asyncio
import json
import os
import struct
import sys
import tempfile
import time
from pathlib import Path
from typing import Optional, Tuple

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

from dense_encoder_video import encode_mkv, decode_mkv


# ============================================================================
# Hilbert Curve Mapping
# ============================================================================

def hilbert_d2xy(n: int, d: int) -> Tuple[int, int]:
    """
    Convert distance d along Hilbert curve to (x, y) coordinates.
    
    Args:
        n: Grid size (must be power of 2)
        d: Distance along curve (0 to n*n-1)
    
    Returns:
        (x, y) coordinates
    """
    x, y = 0, 0
    s = 1
    rx = ry = 0
    
    while s < n:
        rx = (d >> 1) & 1
        ry = (d >> 0) & 1
        
        # Rotate/flip
        if ry == 0:
            if rx == 1:
                x = s - 1 - x
                y = s - 1 - y
            x, y = y, x
        
        x += s * rx
        y += s * ry
        d >>= 2
        s <<= 1
    
    return x, y


_hilbert_cache = {}

def map_ram_to_pixels(ram_data: bytes, width: int, height: int) -> np.ndarray:
    """
    Map linear RAM data to 2D pixel grid using Hilbert curve.
    
    Preserves spatial locality: contiguous RAM → neighboring pixels.
    Memory pages or C-structures become recognizable 2D patterns.
    
    Args:
        ram_data: Raw RAM bytes
        width: Pixel grid width
        height: Pixel grid height
    
    Returns:
        2D pixel array (width x height x 3 RGB)
    """
    key = (width, height)
    total_pixels = width * height
    required_bytes = total_pixels * 3
    
    if len(ram_data) < required_bytes:
        # Pad with zeros
        ram_data = ram_data + b'\x00' * (required_bytes - len(ram_data))
    else:
        # Truncate to fit
        ram_data = ram_data[:required_bytes]
    
    if key not in _hilbert_cache:
        n = max(width, height)
        y_coords = np.zeros(total_pixels, dtype=np.int32)
        x_coords = np.zeros(total_pixels, dtype=np.int32)
        for pixel_idx in range(total_pixels):
            x, y = hilbert_d2xy(n, pixel_idx)
            x_coords[pixel_idx] = x
            y_coords[pixel_idx] = y
        valid = (x_coords < width) & (y_coords < height)
        _hilbert_cache[key] = (y_coords[valid], x_coords[valid], valid)
    
    y_coords, x_coords, valid = _hilbert_cache[key]
    
    pixels = np.zeros((height, width, 3), dtype=np.uint8)
    ram_pixels = np.frombuffer(ram_data, dtype=np.uint8).reshape(total_pixels, 3)
    pixels[y_coords, x_coords] = ram_pixels[valid]
    
    return pixels


# ============================================================================
# QMP Client
# ============================================================================

class QMPClient:
    """Connect to QEMU via QMP (Machine Protocol)"""
    
    def __init__(self, socket_path: str):
        self.socket_path = socket_path
        self.reader = None
        self.writer = None
    
    async def connect(self):
        """Connect to QMP socket"""
        self.reader, self.writer = await asyncio.open_unix_connection(
            self.socket_path
        )
        
        # Receive greeting (QMP sends it immediately on connect)
        greeting = await self.reader.readline()
        if not greeting:
            raise RuntimeError("No QMP greeting received")
        
        # QMP greeting is multi-line JSON, read until we have complete object
        greeting_str = greeting.decode()
        while True:
            try:
                greeting_data = json.loads(greeting_str)
                break
            except json.JSONDecodeError:
                # Need more data
                line = await self.reader.readline()
                if not line:
                    raise RuntimeError("Incomplete QMP greeting")
                greeting_str += line.decode()
        
        # Execute qmp_capabilities
        await self.execute({'execute': 'qmp_capabilities'})
    
    async def execute(self, command: dict) -> dict:
        """Send command and wait for its matching response, transparently
        skipping any unsolicited QMP events (e.g. RESUME/STOP) that may be
        sitting in the stream ahead of the reply."""
        cmd_json = json.dumps(command) + '\n'
        self.writer.write(cmd_json.encode())
        await self.writer.drain()

        while True:
            response_line = await self.reader.readline()
            if not response_line:
                raise RuntimeError("QMP connection closed")

            response = json.loads(response_line)

            if 'event' in response:
                continue  # unsolicited event, not our command's reply

            if 'error' in response:
                raise RuntimeError(f"QMP error: {response['error']}")

            return response
    
    async def pause(self):
        """Pause VM execution"""
        await self.execute({'execute': 'stop'})
    
    async def cont(self):
        """Resume VM execution"""
        await self.execute({'execute': 'cont'})
    
    async def dump_guest_memory(self, output_path: str) -> int:
        """
        Dump guest memory to file.
        
        Returns:
            Size of dumped memory in bytes
        """
        # Use 'dump-guest-memory' command
        await self.execute({
            'execute': 'dump-guest-memory',
            'arguments': {
                'paging': False,  # Don't use paging
                'protocol': f'file:{output_path}',
                'detach': False   # Wait for completion
            }
        })
        
        # Wait for dump to complete
        size = os.path.getsize(output_path)
        return size
    
    async def query_status(self) -> dict:
        """Query VM status"""
        result = await self.execute({'execute': 'query-status'})
        return result['return']
    
    async def close(self):
        """Close connection"""
        if self.writer:
            self.writer.close()
            await self.writer.wait_closed()


# ============================================================================
# Main Capture Loop
# ============================================================================

async def capture_boot_trace(
    disk_path: str,
    output_mkv: str,
    arch: str = "riscv64",
    memory: str = "512M",
    interval: int = 10000,
    max_frames: int = 500,
    qmp_socket: str = "/tmp/qemu_qmp.sock",
    memory_width: int = 512,
    memory_height: int = 512
):
    """
    Capture Linux boot execution as spatial MKV video.
    
    Args:
        disk_path: Path to boot disk image
        output_mkv: Output MKV file
        arch: QEMU architecture
        memory: Memory size (e.g., "512M")
        interval: Instructions between captures
        max_frames: Maximum number of frames to capture
        qmp_socket: QMP socket path
        memory_width: Pixel grid width for RAM mapping
        memory_height: Pixel grid height for RAM mapping
    """
    print("=" * 70)
    print("Hyper-Dimensional Video Boot - QEMU to MKV")
    print("=" * 70)
    print(f"Disk: {disk_path}")
    print(f"Architecture: {arch}")
    print(f"Memory: {memory}")
    print(f"Capture interval: {interval} instructions")
    print(f"Max frames: {max_frames}")
    print(f"Memory grid: {memory_width}x{memory_height}")
    print(f"Output: {output_mkv}")
    print("=" * 70)
    
    # Calculate memory size from grid
    total_pixels = memory_width * memory_height
    total_bytes = total_pixels * 3
    print(f"\nCapture capacity: {total_bytes / (1024*1024):.1f} MB per frame")
    
    # Build QEMU command
    qemu_binary = f"qemu-system-{arch}"
    
    cmd = [
        qemu_binary,
        "-m", memory,
        "-nographic",  # No display needed
        "-qmp", f"unix:{qmp_socket},server,nowait",  # QMP socket
    ]
    
    # Add disk
    if arch == "riscv64":
        cmd.extend(["-M", "virt"])
        cmd.extend(["-drive", f"file={disk_path},format=qcow2,if=virtio"])
        # Alpine RISC-V boots from disk, need OpenSBI firmware
        cmd.extend(["-bios", "default"])
    elif arch == "x86_64":
        cmd.extend(["-M", "pc"])
        cmd.extend(["-drive", f"file={disk_path},format=qcow2,if=virtio"])
    
    print(f"\n[1] Starting QEMU...")
    print(f"Command: {' '.join(cmd)}")
    
    # Start QEMU in background
    print(f"  Spawning QEMU process...")
    qemu_proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    
    print(f"  QEMU PID: {qemu_proc.pid}")
    print(f"  Waiting for QMP socket at {qmp_socket}...")
    
    # Wait for QMP socket to be ready
    for i in range(30):  # 30 seconds timeout
        if os.path.exists(qmp_socket):
            print(f"  ✓ QMP socket ready after {i+1}s")
            break
        await asyncio.sleep(1)
    else:
        print(f"  ✗ QMP socket not created after 30s")
        stderr_data = await qemu_proc.stderr.read()
        print(f"  QEMU stderr: {stderr_data.decode() if stderr_data else 'empty'}")
        raise RuntimeError(f"QMP socket not created: {qmp_socket}")
    
    # Connect to QMP
    print("[3] Connecting to QMP...")
    qmp = QMPClient(qmp_socket)
    await qmp.connect()
    print("  ✓ Connected")
    
    # Initial pause
    print("[4] Pausing VM for initial capture...")
    await qmp.pause()
    
    # Capture loop
    print(f"\n[5] Starting capture loop ({max_frames} frames, every {interval} instructions)...")
    frames_data = []
    captured = 0
    
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        mem_dump_path = tmpdir / "guest_memory.dump"
        
        prev_pixels = None
        hang_count = 0
        
        while captured < max_frames:
            # Dump memory
            print(f"  Frame {captured + 1}/{max_frames}: Dumping memory...", end="\r")

            # QEMU writes dump-guest-memory output as read-only (mode 0400);
            # reusing the same path on the next capture fails to overwrite it.
            if mem_dump_path.exists():
                mem_dump_path.unlink()

            try:
                size = await qmp.dump_guest_memory(str(mem_dump_path))
                print(f"  Frame {captured + 1}/{max_frames}: {size / (1024*1024):.1f} MB    ", end="\r")
            except Exception as e:
                print(f"\n[!] Memory dump failed: {e}")
                break
            
            # Read RAM dump
            with open(mem_dump_path, 'rb') as f:
                ram_data = f.read()
            
            # Tile mapping for full RAM capture
            tile_size = memory_width * memory_height * 3
            num_tiles = (len(ram_data) + tile_size - 1) // tile_size
            
            # Pad to multiple of tile_size
            if len(ram_data) % tile_size != 0:
                ram_data += b'\x00' * (tile_size - (len(ram_data) % tile_size))
                
            capture_frames_bytes = []
            capture_identical_tiles = 0
            
            if prev_pixels is None:
                prev_pixels = [None] * num_tiles
                
            for tile_idx in range(num_tiles):
                tile_ram = ram_data[tile_idx * tile_size : (tile_idx + 1) * tile_size]
                pixels = map_ram_to_pixels(tile_ram, memory_width, memory_height)
                
                if prev_pixels[tile_idx] is not None:
                    if np.array_equal(pixels, prev_pixels[tile_idx]):
                        capture_identical_tiles += 1
                    
                    delta_pixels = np.bitwise_xor(pixels, prev_pixels[tile_idx])
                    frame_bytes = delta_pixels.tobytes()
                else:
                    frame_bytes = pixels.tobytes()
                    
                prev_pixels[tile_idx] = pixels.copy()
                capture_frames_bytes.append(frame_bytes)
            
            # Hang Detection
            if capture_identical_tiles == num_tiles:
                hang_count += 1
                print(f"\n[!] Hang detected at capture {captured + 1}! All tiles identical to previous.")
                if hang_count >= 3:
                    print("  Stopping capture due to consecutive hangs.")
                    break
            else:
                hang_count = 0
                
            frames_data.extend(capture_frames_bytes)
            captured += 1
            
            # Resume execution
            await qmp.cont()
            
            # Wait for instructions to execute
            # This is a crude approximation - in practice we'd use
            # QMP 'query-status' and instruction counters
            await asyncio.sleep(0.1)
            
            # Pause for next capture
            await qmp.pause()
        
        print(f"\n  Captured {captured} frames")
    
    # Pause VM
    await qmp.pause()
    
    # Encode MKV
    print(f"\n[6] Encoding {captured} frames to MKV...")
    all_frames = b''.join(frames_data)
    
    encode_mkv(
        payload=all_frames,
        output_path=output_mkv,
        metadata={
            'type': 'qemu_boot_trace',
            'architecture': arch,
            'memory': memory,
            'interval': interval,
            'grid_width': memory_width,
            'grid_height': memory_height,
            'total_captures': captured,
            'tiles_per_capture': num_tiles if captured > 0 else 1,
            'capture_time': time.time(),
            'delta_encoding': 'xor'
        }
    )
    
    # Shutdown
    print(f"\n[7] Shutting down QEMU...")
    await qmp.execute({'execute': 'quit'})
    await qmp.close()
    
    print(f"\n✓ Boot trace complete: {output_mkv}")
    print(f"\nPlay in VLC: vlc {output_mkv}")
    print(f"Extract frame: python3 tools/qemu_to_mkv.py {output_mkv} --extract-frame <N>")


async def extract_frame_from_mkv(mkv_path: str, capture_num: int, output_path: str):
    """
    Extract a specific capture (which spans multiple tile frames) back to memory dump.
    
    Args:
        mkv_path: MKV file
        capture_num: Capture number to extract
        output_path: Output memory dump path
    """
    print(f"Extracting capture {capture_num} from {mkv_path}...")
    
    # Decode MKV
    payload, manifest = decode_mkv(mkv_path)
    
    # Get frame dimensions from metadata
    if 'metadata' in manifest:
        meta = manifest['metadata']
        width = meta.get('grid_width', 512)
        height = meta.get('grid_height', 512)
        is_delta = meta.get('delta_encoding') == 'xor'
        tiles_per_capture = meta.get('tiles_per_capture', 1)
        total_captures = meta.get('total_captures', len(payload) // (width * height * 3))
    else:
        width = height = 512
        is_delta = False
        tiles_per_capture = 1
        total_captures = len(payload) // (width * height * 3)
    
    frame_size = width * height * 3  # RGB24
    
    if capture_num >= total_captures:
        raise ValueError(f"Capture {capture_num} out of range (total captures: {total_captures})")
    
    # Fast reverse Hilbert mapping
    key = (width, height)
    total_pixels = width * height
    if key not in _hilbert_cache:
        n = max(width, height)
        y_coords = np.zeros(total_pixels, dtype=np.int32)
        x_coords = np.zeros(total_pixels, dtype=np.int32)
        for pixel_idx in range(total_pixels):
            x, y = hilbert_d2xy(n, pixel_idx)
            x_coords[pixel_idx] = x
            y_coords[pixel_idx] = y
        valid = (x_coords < width) & (y_coords < height)
        _hilbert_cache[key] = (y_coords[valid], x_coords[valid], valid)
        
    y_coords, x_coords, valid = _hilbert_cache[key]
    
    ram_data_chunks = []
    
    for tile_idx in range(tiles_per_capture):
        # Extract specific tile
        if is_delta:
            accumulated_pixels = np.zeros(frame_size, dtype=np.uint8)
            for i in range(capture_num + 1):
                offset = (i * tiles_per_capture + tile_idx) * frame_size
                frame_data_chunk = np.frombuffer(payload[offset:offset + frame_size], dtype=np.uint8)
                accumulated_pixels = np.bitwise_xor(accumulated_pixels, frame_data_chunk)
            frame_data = accumulated_pixels.tobytes()
        else:
            offset = (capture_num * tiles_per_capture + tile_idx) * frame_size
            frame_data = payload[offset:offset + frame_size]
        
        # Convert back to linear RAM
        frame_pixels = np.frombuffer(frame_data, dtype=np.uint8).reshape(height, width, 3)
        tile_ram_pixels = np.zeros((total_pixels, 3), dtype=np.uint8)
        tile_ram_pixels[valid] = frame_pixels[y_coords, x_coords]
        ram_data_chunks.append(tile_ram_pixels.tobytes())
    
    full_ram = b''.join(ram_data_chunks)
    
    # Write to output
    with open(output_path, 'wb') as f:
        f.write(full_ram)
    
    print(f"✓ Capture {capture_num} extracted to {output_path}")
    print(f"  Size: {len(full_ram) / (1024*1024):.1f} MB (from {tiles_per_capture} tiles)")
    
    return manifest


# ============================================================================
# CLI
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Capture Linux boot execution as spatial MKV video",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Capture Alpine Linux boot
  python3 tools/qemu_to_mkv.py alpine_riscv64.qcow2 \\
      --arch riscv64 \\
      --output alpine_boot_trace.mkv \\
      --interval 10000 \\
      --max-frames 500

  # Extract frame 120 back to memory dump
  python3 tools/qemu_to_mkv.py alpine_boot_trace.mkv \\
      --extract-frame 120 \\
      --output snapshot_frame120.mem
        """
    )
    
    parser.add_argument('input', help='Disk image or MKV file')
    
    # Capture mode arguments
    parser.add_argument('--output', '-o', help='Output MKV file')
    parser.add_argument('--arch', default='riscv64', choices=['riscv64', 'x86_64'])
    parser.add_argument('--memory', default='512M', help='Memory size')
    parser.add_argument('--interval', type=int, default=10000,
                       help='Instructions between captures')
    parser.add_argument('--max-frames', type=int, default=500,
                       help='Maximum frames to capture')
    parser.add_argument('--qmp-socket', default='/tmp/qemu_qmp.sock',
                       help='QMP socket path')
    parser.add_argument('--memory-width', type=int, default=512,
                       help='Pixel grid width')
    parser.add_argument('--memory-height', type=int, default=512,
                       help='Pixel grid height')
    
    # Extract mode arguments
    parser.add_argument('--extract-frame', type=int, help='Extract specific frame')
    
    args = parser.parse_args()
    
    # Detect mode
    if args.input.endswith('.mkv') and args.extract_frame is not None:
        # Extract mode
        asyncio.run(extract_frame_from_mkv(
            args.input,
            args.extract_frame,
            args.output or f"frame_{args.extract_frame}.mem"
        ))
    else:
        # Capture mode
        if not args.output:
            parser.error("--output required for capture mode")
        
        asyncio.run(capture_boot_trace(
            disk_path=args.input,
            output_mkv=args.output,
            arch=args.arch,
            memory=args.memory,
            interval=args.interval,
            max_frames=args.max_frames,
            qmp_socket=args.qmp_socket,
            memory_width=args.memory_width,
            memory_height=args.memory_height
        ))


if __name__ == '__main__':
    main()