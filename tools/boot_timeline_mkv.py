#!/usr/bin/env python3
"""
Boot Timeline MKV — Capture boot process as milestone-based video frames

Each frame represents a distinct boot milestone, not arbitrary time slices.
This creates a human-readable visual timeline of the boot sequence.

Architecture:
  1. Boot monitor watches for milestone markers in QMP output/memory
  2. On milestone detection, pause guest, capture memory dump
  3. Encode dump as FFV1 frame with milestone metadata
  4. Resume boot and continue watching

Milestone types:
  - QMP events: SHUTDOWN, RESET, STOP
  - Memory patterns: specific signatures appearing at known addresses
  - Console output: matching boot messages via QMP
  - Instruction计数: PC reaching known addresses
"""

import argparse
import asyncio
import json
import os
import socket
import struct
import tempfile
import time
from pathlib import Path
from typing import Dict, List, Optional, Callable, Tuple
import numpy as np

from dense_encoder_video import encode_mkv, decode_mkv, md5_hash


# Hilbert cache for coordinate mapping
_hilbert_cache = {}


# ============================================================================
# Milestone Detection
# ============================================================================

class Milestone:
    """Represents a single boot milestone."""
    
    def __init__(self, name: str, description: str, frame_index: int,
                 timestamp: float, metadata: dict = None):
        self.name = name
        self.description = description
        self.frame_index = frame_index
        self.timestamp = timestamp
        self.metadata = metadata or {}
    
    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "frame_index": self.frame_index,
            "timestamp": self.timestamp,
            "metadata": self.metadata
        }


class MilestoneDetector:
    """Detects boot milestones from various sources."""
    
    # Known RISC-V boot milestones (xv6, Linux, Alpine)
    COMMON_MILESTONES = {
        # xv6 milestones
        "xv6_start": ("0x80000000", "xv6 kernel entry point"),
        "xv6_main": ("0x80001000", "xv6 main() function"),
        "xv6_user_init": ("0x80100000", "first user process init"),
        "xv6_shell": ("0x80200000", "shell process start"),
        
        # Linux RISC-V milestones
        "linux_entry": ("0x80200000", "Linux kernel entry"),
        "linux_start_kernel": ("0x80201000", "start_kernel()"),
        "linux_rest_init": ("0x80202000", "rest_init()"),
        "linux_init": ("0x80203000", "kernel_init()"),
        
        # OpenSBI firmware
        "opensbi_entry": ("0x80000000", "OpenSBI firmware entry"),
        "opensbi_handoff": ("0x80100000", "OpenSBI→OS handoff"),
    }
    
    def __init__(self):
        self.detected_milestones: List[Milestone] = []
        self.start_time = time.time()
    
    def check_memory_signature(self, ram_data: bytes, address: int, 
                               signature: bytes) -> bool:
        """Check if signature exists at address in RAM dump."""
        offset = address - 0x80000000  # Assuming physical memory base
        if offset < 0 or offset + len(signature) > len(ram_data):
            return False
        return ram_data[offset:offset + len(signature)] == signature
    
    def check_qmp_event(self, event: dict) -> Optional[Milestone]:
        """Check if QMP event is a milestone."""
        event_name = event.get("event", "")
        
        milestone_map = {
            "SHUTDOWN": "system_shutdown",
            "RESET": "system_reset", 
            "STOP": "guest_stop",
            "RESUME": "guest_resume",
        }
        
        if event_name in milestone_map:
            name = milestone_map[event_name]
            return Milestone(
                name=name,
                description=f"QMP event: {event_name}",
                frame_index=len(self.detected_milestones),
                timestamp=time.time() - self.start_time,
                metadata={"qmp_event": event}
            )
        return None
    
    def check_console_pattern(self, console_output: str) -> Optional[Milestone]:
        """Check console output for boot messages."""
        patterns = {
            r"Starting kernel": "linux_kernel_start",
            r"Welcome to Alpine": "alpine_boot_start",
            r"login:": "login_prompt",
            r"root@.*:~#": "shell_prompt",
            r"xv6 kernel is booting": "xv6_boot",
            r"cpu\d+:": "cpu_online",
            r"init:": "init_start",
        }
        
        import re
        for pattern, milestone_name in patterns.items():
            if re.search(pattern, console_output):
                return Milestone(
                    name=milestone_name,
                    description=f"Console: matched '{pattern}'",
                    frame_index=len(self.detected_milestones),
                    timestamp=time.time() - self.start_time,
                    metadata={"console_pattern": pattern}
                )
        return None
    
    def add_milestone(self, milestone: Milestone):
        """Add a detected milestone."""
        self.detected_milestones.append(milestone)
        print(f"[MILESTONE {milestone.frame_index}] {milestone.name}")
        print(f"  {milestone.description}")
        print(f"  T+{milestone.timestamp:.2f}s")


# ============================================================================
# QMP Client for Boot Capture
# ============================================================================

class BootCaptureClient:
    """QMP client specialized for boot timeline capture."""
    
    def __init__(self, socket_path: str, detector: MilestoneDetector):
        self.socket_path = socket_path
        self.detector = detector
        self.reader: Optional[asyncio.StreamReader] = None
        self.writer: Optional[asyncio.StreamWriter] = None
    
    async def connect(self):
        """Connect to QMP socket."""
        self.reader, self.writer = await asyncio.open_unix_connection(
            self.socket_path
        )
        # Read QMP greeting
        greeting = await self.reader.read(4096)
        greeting_data = json.loads(greeting.decode())
        print(f"Connected to QMP: {greeting_data.get('QMP', {}).get('version', {})}")
        
        # Negotiate capabilities
        await self.execute({"execute": "qmp_capabilities"})
    
    async def execute(self, command: dict) -> dict:
        """Execute QMP command and return response."""
        cmd_str = json.dumps(command) + "\n"
        self.writer.write(cmd_str.encode())
        await self.writer.drain()
        
        # Read response, skipping events
        while True:
            line = await self.reader.readline()
            if not line:
                raise RuntimeError("QMP connection closed")
            
            response = json.loads(line.decode())
            if "event" in response:
                # Check if event is a milestone
                milestone = self.detector.check_qmp_event(response)
                if milestone:
                    self.detector.add_milestone(milestone)
            else:
                return response
    
    async def pause_guest(self):
        """Pause guest execution."""
        await self.execute({"execute": "stop"})
    
    async def resume_guest(self):
        """Resume guest execution."""
        await self.execute({"execute": "cont"})
    
    async def dump_memory(self, output_path: str, paging: bool = False) -> int:
        """Dump guest memory to file."""
        await self.execute({
            "execute": "dump-guest-memory",
            "arguments": {
                "paging": paging,
                "protocol": f"file:{output_path}"
            }
        })
        # Wait for dump to complete
        await asyncio.sleep(1)
        return os.path.getsize(output_path)
    
    async def monitor_events(self, callback: Callable):
        """Monitor QMP events and call callback for each."""
        while True:
            line = await self.reader.readline()
            if not line:
                break
            
            try:
                event = json.loads(line.decode())
                if "event" in event:
                    await callback(event)
            except json.JSONDecodeError:
                continue


# ============================================================================
# Hilbert Mapping (shared with qemu_capture_simple.py)
# ============================================================================

def hilbert_d2xy(n: int, d: int) -> Tuple[int, int]:
    """Convert distance d along Hilbert curve of order n to (x, y)."""
    x, y = 0, 0
    s = 1
    while s < n:
        rx = 1 & (d >> 1)
        ry = 1 & (d ^ rx)
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


def map_ram_to_pixels(ram_data: bytes, width: int = 256, height: int = 256) -> np.ndarray:
    """
    Map RAM bytes to 2D pixel grid using Hilbert curve.
    
    Preserves spatial locality: contiguous RAM → neighboring pixels.
    Memory pages or C-structures become recognizable 2D patterns.
    
    Args:
        ram_data: Raw RAM bytes
        width: Pixel grid width
        height: Pixel grid height
    
    Returns:
        RGB24 pixel array (height × width × 3)
    """
    total_pixels = width * height
    required_bytes = total_pixels * 3
    
    # Pad or truncate to exact size
    if len(ram_data) < required_bytes:
        ram_data = ram_data + b'\x00' * (required_bytes - len(ram_data))
    else:
        ram_data = ram_data[:required_bytes]
    
    # Vectorized Hilbert mapping with cache
    key = (width, height)
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


def map_full_ram_to_tiles(ram_data: bytes, tile_width: int, tile_height: int) -> Tuple[List[bytes], int]:
    """
    Map full RAM to tiled pixel grids for complete memory capture.
    
    Instead of truncating to first N bytes, tile entire RAM across multiple
    frames. Each tile covers (tile_width × tile_height × 3) bytes of RAM.
    
    Args:
        ram_data: Raw RAM bytes (full guest memory dump)
        tile_width: Width of each tile in pixels
        tile_height: Height of each tile in pixels
    
    Returns:
        (tile_frames_bytes, num_tiles): List of encoded tile frames, number of tiles
    """
    tile_size = tile_width * tile_height * 3
    num_tiles = (len(ram_data) + tile_size - 1) // tile_size
    
    # Pad to multiple of tile_size
    if len(ram_data) % tile_size != 0:
        ram_data = ram_data + b'\x00' * (tile_size - (len(ram_data) % tile_size))
    
    tile_frames_bytes = []
    for tile_idx in range(num_tiles):
        tile_ram = ram_data[tile_idx * tile_size : (tile_idx + 1) * tile_size]
        pixels = map_ram_to_pixels(tile_ram, tile_width, tile_height)
        tile_frames_bytes.append(pixels.tobytes())
    
    return tile_frames_bytes, num_tiles


# ============================================================================
# Boot Timeline Capture
# ============================================================================

async def capture_boot_timeline(
    qemu_cmd: List[str],
    output_mkv: str,
    max_milestones: int = 20,
    capture_delay: float = 0.5,
    pixel_width: int = 256,
    pixel_height: int = 256,
    boot_timeout: float = 60.0,
    use_tiling: bool = False
) -> Tuple[str, List[Milestone]]:
    """
    Capture boot process as milestone-based MKV video.
    
    Args:
        qemu_cmd: QEMU command list to run
        output_mkv: Path for output MKV file
        max_milestones: Maximum milestones to capture
        capture_delay: Delay after resume before next check (seconds)
        pixel_width: Width of pixel grid for memory visualization
        pixel_height: Height of pixel grid
        boot_timeout: Maximum time to wait for boot completion
        use_tiling: If True, tile entire RAM across multiple frames per capture
    
    Returns:
        (mkv_path, milestones_list)
    """
    detector = MilestoneDetector()
    qmp_socket = "/tmp/boot_timeline.sock"
    
    # Ensure clean socket
    try:
        os.unlink(qmp_socket)
    except FileNotFoundError:
        pass
    
    # Build QEMU command with QMP + serial output capture
    # Use -serial mon:stdio to get console on stdout, -nographic still needed
    qemu_cmd_full = qemu_cmd + [
        "-qmp", f"unix:{qmp_socket},server,nowait",
        "-nographic"
    ]
    
    print(f"Starting QEMU: {' '.join(qemu_cmd_full)}")
    
    # Start QEMU subprocess with console capture
    import subprocess
    qemu_proc = subprocess.Popen(
        qemu_cmd_full,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    
    # Console reader task for pattern detection
    console_buffer = []
    console_task = None
    
    async def read_console():
        """Read QEMU stdout for console patterns."""
        nonlocal console_buffer
        try:
            while qemu_proc.poll() is None:
                line = qemu_proc.stdout.readline()
                if not line:
                    await asyncio.sleep(0.01)
                    continue
                
                # Detect milestones from console output
                milestone = detector.check_console_pattern(line)
                if milestone:
                    detector.add_milestone(milestone)
                
                console_buffer.append(line)
                if len(console_buffer) > 1000:  # Keep last 1000 lines
                    console_buffer.pop(0)
        except Exception as e:
            print(f"Console reader error: {e}")
    
    # Wait for QMP socket to appear
    print("Waiting for QMP socket to appear...")
    for i in range(50):  # 5 second timeout
        if os.path.exists(qmp_socket):
            print(f"QMP socket ready after {i*0.1:.1f}s")
            break
        await asyncio.sleep(0.1)
    else:
        raise RuntimeError("QMP socket did not appear")
    
    # Additional small delay for socket to be fully ready
    await asyncio.sleep(0.5)
    
    # Connect to QMP with retries
    client = BootCaptureClient(qmp_socket, detector)
    max_retries = 10
    for attempt in range(max_retries):
        try:
            await client.connect()
            break
        except (ConnectionRefusedError, FileNotFoundError) as e:
            if attempt < max_retries - 1:
                print(f"Connection attempt {attempt + 1} failed: {e}, retrying...")
                await asyncio.sleep(0.5)
            else:
                raise RuntimeError(f"Failed to connect to QMP after {max_retries} attempts: {e}")
    
    # Add initial milestone
    detector.add_milestone(Milestone(
        name="qemu_start",
        description="QEMU process started",
        frame_index=0,
        timestamp=0.0
    ))
    
    # Start console reader task
    console_task = asyncio.create_task(read_console())
    print("Console pattern detection enabled")
    
    # Capture loop
    frames_data = []
    frame_index = 0
    start_time = time.time()
    last_frame_data = None
    
    print("\n=== Boot Timeline Capture ===")
    print(f"Max milestones: {max_milestones}")
    print(f"Capture delay: {capture_delay}s")
    print(f"Pixel grid: {pixel_width}×{pixel_height}")
    print(f"Full-RAM tiling: {'ON' if use_tiling else 'OFF'}")
    print("=" * 50)
    
    try:
        while frame_index < max_milestones:
            # Check timeout
            if time.time() - start_time > boot_timeout:
                print(f"Boot timeout after {boot_timeout}s")
                break
            
            # Pause guest
            await client.pause_guest()
            
            # Dump memory
            with tempfile.NamedTemporaryFile(suffix=".dump", delete=False) as dump_file:
                dump_path = dump_file.name
            
            try:
                dump_size = await client.dump_memory(dump_path)
                
                # Read full RAM dump (skip ELF header)
                with open(dump_path, "rb") as f:
                    f.seek(64)
                    ram_data = f.read()
                
                # Map to pixel grid (tiling or single frame)
                if use_tiling:
                    tile_frames_bytes, num_tiles = map_full_ram_to_tiles(
                        ram_data, pixel_width, pixel_height
                    )
                    print(f"Frame {frame_index}: captured {dump_size} bytes RAM "
                          f"→ {num_tiles} tiles ({len(ram_data) / (1024*1024):.1f} MB)")
                    
                    # Compute deltas per tile
                    if last_frame_data is not None and len(last_frame_data) == num_tiles:
                        unchanged_tiles = 0
                        for tile_idx in range(num_tiles):
                            current_tile = np.frombuffer(tile_frames_bytes[tile_idx], dtype=np.uint8)
                            prev_tile = np.frombuffer(last_frame_data[tile_idx], dtype=np.uint8)
                            delta_tile = np.bitwise_xor(current_tile, prev_tile)
                            tile_frames_bytes[tile_idx] = delta_tile.tobytes()
                            if not np.any(delta_tile):
                                unchanged_tiles += 1
                        
                        if unchanged_tiles == num_tiles:
                            print(f"Frame {frame_index}: all {num_tiles} tiles unchanged, skipping")
                            await client.resume_guest()
                            await asyncio.sleep(capture_delay)
                            continue
                    else:
                        # First capture or RAM size changed
                        pass
                    
                    # Store all tiles for this frame
                    for tile_bytes in tile_frames_bytes:
                        frames_data.append(tile_bytes)
                    
                    last_frame_data = tile_frames_bytes.copy()
                else:
                    # Legacy single-frame mode (truncated)
                    pixels = map_ram_to_pixels(ram_data, pixel_width, pixel_height)
                    
                    # Compute delta against previous frame
                    if last_frame_data is not None:
                        delta_pixels = pixels ^ last_frame_data
                        # Check if anything changed
                        if not np.any(delta_pixels):
                            print(f"Frame {frame_index}: no change, skipping")
                            await client.resume_guest()
                            await asyncio.sleep(capture_delay)
                            continue
                    else:
                        delta_pixels = pixels
                    
                    # Store frame (use delta for compression)
                    frames_data.append(delta_pixels.tobytes())
                    last_frame_data = [pixels.tobytes()]
                    
                    print(f"Frame {frame_index}: captured {dump_size} bytes RAM, "
                          f"{len(delta_pixels.tobytes())} bytes pixels (truncated)")
                
                frame_index += 1
                
            finally:
                # Cleanup dump file
                try:
                    os.unlink(dump_path)
                except:
                    pass
            
            # Resume guest
            await client.resume_guest()
            
            # Wait for next capture
            await asyncio.sleep(capture_delay)
    
    except KeyboardInterrupt:
        print("\nCapture interrupted by user")
    
    finally:
        # Cleanup
        if console_task:
            console_task.cancel()
            try:
                await console_task
            except asyncio.CancelledError:
                pass
        
        try:
            await client.execute({"execute": "quit"})
        except:
            pass
        
        qemu_proc.terminate()
        try:
            qemu_proc.wait(timeout=5)
        except:
            qemu_proc.kill()
        
        try:
            os.unlink(qmp_socket)
        except:
            pass
    
    # Encode frames to MKV
    if not frames_data:
        raise RuntimeError("No frames captured")
    
    print(f"\n=== Encoding {len(frames_data)} frames to MKV ===")
    
    # Concatenate all frames
    all_frames_data = b''.join(frames_data)
    
    # Build metadata
    metadata = {
        "capture_type": "boot_timeline",
        "total_frames": len(frames_data),
        "milestones": [m.to_dict() for m in detector.detected_milestones],
        "pixel_width": pixel_width,
        "pixel_height": pixel_height,
        "qemu_cmd": " ".join(qemu_cmd),
        "capture_delay": capture_delay,
        "use_tiling": use_tiling,
    }
    if use_tiling:
        metadata["tiles_per_capture"] = (last_frame_data and len(last_frame_data)) or 0
    
    # Encode MKV
    mkv_path, manifest = encode_mkv(
        payload=all_frames_data,
        output_path=output_mkv,
        metadata=metadata
    )
    
    print(f"\n=== Boot Timeline Capture Complete ===")
    print(f"MKV: {mkv_path}")
    print(f"Milestones detected: {len(detector.detected_milestones)}")
    print(f"Frames captured: {len(frames_data)}")
    
    for m in detector.detected_milestones:
        print(f"  [{m.frame_index}] {m.name}: {m.description}")
    
    return mkv_path, detector.detected_milestones


# ============================================================================
# CLI
# ============================================================================

def main():
    # Parse options only first
    parser = argparse.ArgumentParser(
        description="Capture boot process as milestone-based MKV video",
        add_help=False
    )
    parser.add_argument(
        "-o", "--output",
        default="/tmp/boot_timeline.mkv",
        help="Output MKV file path"
    )
    parser.add_argument(
        "-m", "--max-milestones",
        type=int,
        default=20,
        help="Maximum milestones to capture"
    )
    parser.add_argument(
        "-d", "--delay",
        type=float,
        default=0.5,
        help="Delay between captures (seconds)"
    )
    parser.add_argument(
        "-W", "--pixel-width",
        type=int,
        default=256,
        help="Pixel grid width"
    )
    parser.add_argument(
        "-H", "--pixel-height", 
        type=int,
        default=256,
        help="Pixel grid height"
    )
    parser.add_argument(
        "-t", "--timeout",
        type=float,
        default=60.0,
        help="Boot timeout (seconds)"
    )
    parser.add_argument(
        "--tiling",
        action="store_true",
        help="Enable full-RAM tiling (capture entire RAM across multiple frames)"
    )
    parser.add_argument(
        "-h", "--help",
        action="store_true",
        help="Show help message"
    )
    
    args, qemu_cmd = parser.parse_known_args()
    
    # Strip '--' separator if present
    if qemu_cmd and qemu_cmd[0] == '--':
        qemu_cmd = qemu_cmd[1:]
    
    if args.help:
        parser.print_help()
        print("\nQEMU command should be provided after all options.")
        print("Example: boot_timeline_mkv.py -m 5 -- qemu-system-riscv64 -kernel kernel")
        return
    
    if not qemu_cmd:
        parser.error("QEMU command is required")
    
    # Run async capture
    mkv_path, milestones = asyncio.run(capture_boot_timeline(
        qemu_cmd=qemu_cmd,
        output_mkv=args.output,
        max_milestones=args.max_milestones,
        capture_delay=args.delay,
        pixel_width=args.pixel_width,
        pixel_height=args.pixel_height,
        boot_timeout=args.timeout,
        use_tiling=args.tiling
    ))
    
    print(f"\n✓ Boot timeline captured to: {mkv_path}")


if __name__ == "__main__":
    main()