#!/usr/bin/env python3
"""
qemu_capture_simple.py - Simple proof-of-concept for spatial execution capture

Uses QMP polling to capture memory snapshots during boot. 
Simpler than full async approach for initial validation.

Usage:
    python3 tools/qemu_capture_simple.py boot_images/alpine_riscv64.qcow2 \
        --output alpine_boot_simple.mkv \
        --max-frames 10
"""

import argparse
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

from dense_encoder_video import encode_mkv
from geos_hilbert import hilbert_d2xy_legacy_qemu as hilbert_d2xy


def map_ram_to_pixels(ram_data: bytes, width: int, height: int) -> np.ndarray:
    """Map linear RAM data to 2D pixel grid using Hilbert curve."""
    total_pixels = width * height
    required_bytes = total_pixels * 3
    
    if len(ram_data) < required_bytes:
        ram_data = ram_data + b'\x00' * (required_bytes - len(ram_data))
    else:
        ram_data = ram_data[:required_bytes]
    
    pixels = np.zeros((height, width, 3), dtype=np.uint8)
    n = max(width, height)
    
    for pixel_idx in range(total_pixels):
        if pixel_idx * 3 >= len(ram_data):
            break
        
        x, y = hilbert_d2xy(n, pixel_idx)
        
        if x >= width or y >= height:
            continue
        
        pixels[y, x] = [
            ram_data[pixel_idx * 3 + 0],
            ram_data[pixel_idx * 3 + 1],
            ram_data[pixel_idx * 3 + 2]
        ]
    
    return pixels


# ============================================================================
# Simple QMP Client (synchronous)
# ============================================================================

class SimpleQMP:
    """Synchronous QMP client using socket"""
    
    def __init__(self, socket_path: str):
        self.socket_path = socket_path
        self.sock = None
        self._recv_buf = b''
    
    def connect(self, max_retries=5, initial_delay=0.5):
        """Connect to QMP socket with retry logic"""
        for attempt in range(max_retries):
            try:
                self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                self.sock.connect(self.socket_path)
                break
            except (FileNotFoundError, ConnectionRefusedError):
                if attempt < max_retries - 1:
                    delay = initial_delay * (2 ** attempt)
                    time.sleep(delay)
                    continue
                raise
        
        # Receive greeting (first line on the wire is always the QMP greeting)
        self._read_json_object()

        # Capabilities handshake
        self._send_command({'execute': 'qmp_capabilities'})
    
    def _read_json_object(self) -> dict:
        """Read one complete JSON object from the socket, buffering across recv() calls
        and across multiple newline-delimited objects that arrive in the same chunk."""
        buf = self._recv_buf
        while True:
            newline = buf.find(b'\n')
            if newline != -1:
                line, buf = buf[:newline], buf[newline + 1:]
                self._recv_buf = buf
                if not line.strip():
                    continue
                return json.loads(line.decode())
            chunk = self.sock.recv(4096)
            if not chunk:
                raise RuntimeError("QMP socket closed unexpectedly")
            buf += chunk

    def _send_command(self, command: dict) -> dict:
        """Send command and wait for its matching response, transparently
        skipping any unsolicited QMP events (e.g. RESUME/STOP) that may be
        sitting in the stream ahead of the reply."""
        cmd_json = json.dumps(command) + '\n'
        self.sock.sendall(cmd_json.encode())

        while True:
            msg = self._read_json_object()
            if 'event' in msg:
                continue  # unsolicited event, not our command's reply
            return msg

    def query_status(self) -> str:
        """Get VM status"""
        result = self._send_command({'execute': 'query-status'})
        return result['return']['status']
    
    def stop(self):
        """Stop VM execution"""
        self._send_command({'execute': 'stop'})
    
    def cont(self):
        """Resume VM execution"""
        self._send_command({'execute': 'cont'})
    
    def close(self):
        """Close connection"""
        if self.sock:
            self.sock.close()


# ============================================================================
# Simplified Capture (no memory dumps, just QMP status polling)
# ============================================================================

def capture_boot_trace_simple(disk_path: str, output_mkv: str, max_frames: int = 100):
    """
    Capture boot trace using simple QMP polling.
    
    This is a simplified version that doesn't require memory dumps.
    It captures VM status and instruction count as proof-of-concept.
    """
    print("=" * 70)
    print("Simplified Spatial Boot Trace (Proof of Concept)")
    print("=" * 70)
    
    qmp_socket = '/tmp/qemu_simple.sock'
    
    # Start QEMU
    cmd = [
        'qemu-system-riscv64',
        '-m', '512M',
        '-nographic',
        '-qmp', f'unix:{qmp_socket},server,nowait',
        '-M', 'virt',
        '-drive', f'file={disk_path},format=qcow2,if=virtio',
        '-bios', 'default'
    ]
    
    print(f"\n[1] Starting QEMU...")
    print(f"Command: {' '.join(cmd)}")
    
    qemu_proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.DEVNULL)
    
    # Wait for QMP socket
    print(f"[2] Waiting for QMP socket...")
    for i in range(30):
        if os.path.exists(qmp_socket):
            print(f"  ✓ Socket exists after {i+1}s")
            # Give QEMU a moment to finish setting up the socket
            time.sleep(0.5)
            print(f"  ✓ Socket ready")
            break
        time.sleep(1)
    else:
        qemu_proc.kill()
        raise RuntimeError("QMP socket not created")
    
    # Connect QMP (reused across frames)
    print(f"[3] Connecting QMP...")
    qmp = SimpleQMP(qmp_socket)
    qmp.connect()
    print(f"  ✓ Connected")
    
    # Capture loop
    print(f"\n[4] Capturing {max_frames} frames...")
    frames_data = []
    
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        dump_path = tmpdir / 'memory.dump'
        
        prev_pixels = None
        hang_count = 0
        
        for frame_num in range(max_frames):
            print(f"  Frame {frame_num + 1}/{max_frames}: ", end='\r')
            
            # Stop VM for memory dump
            status = qmp.query_status()
            if status == 'running':
                qmp.stop()
                time.sleep(0.1)  # Give it a moment to fully stop
            
            # Capture status
            status = qmp.query_status()
            
            # Try memory dump via qmp command (may fail on older QEMU)
            try:
                result = qmp._send_command({
                    'execute': 'dump-guest-memory',
                    'arguments': {
                        'paging': False,
                        'protocol': f'file:{dump_path}',
                        'detach': False
                    }
                })
                
                # Wait for dump to complete (file exists and stable)
                for _ in range(10):
                    if os.path.exists(dump_path):
                        time.sleep(0.2)
                        break
                    time.sleep(0.2)
                else:
                    raise RuntimeError("Memory dump file not created")
                
                # Read memory dump if successful
                if os.path.exists(dump_path):
                    with open(dump_path, 'rb') as f:
                        ram_data = f.read()
                    
                    # Map to pixels (256x256 grid for faster capture)
                    pixels = map_ram_to_pixels(ram_data, 256, 256)
                    
                    if prev_pixels is not None:
                        if np.array_equal(pixels, prev_pixels):
                            hang_count += 1
                            print(f"\n[!] Hang detected at frame {frame_num + 1}!")
                            if hang_count >= 3:
                                print("  Stopping capture due to consecutive hangs.")
                                break
                        else:
                            hang_count = 0
                            
                        delta_pixels = np.bitwise_xor(pixels, prev_pixels)
                        frame_bytes = delta_pixels.tobytes()
                    else:
                        frame_bytes = pixels.tobytes()
                        
                    prev_pixels = pixels.copy()
                    
                    frames_data.append(frame_bytes)
                    
                    print(f"  Frame {frame_num + 1}/{max_frames}: {len(ram_data)/1024/1024:.1f} MB")
                else:
                    # Fallback: encode status info as synthetic frame
                    status_bytes = json.dumps({'status': status, 'frame': frame_num}).encode()
                    status_bytes = status_bytes[:256*256*3].ljust(256*256*3, b'\x00')
                    frames_data.append(status_bytes)
                    print(f"  Frame {frame_num + 1}/{max_frames}: status-only")
                    
            except Exception as e:
                # Fallback: synthetic frame
                status_bytes = json.dumps({'status': status, 'frame': frame_num, 'error': str(e)}).encode()
                status_bytes = status_bytes[:256*256*3].ljust(256*256*3, b'\x00')
                frames_data.append(status_bytes)
                print(f"  Frame {frame_num + 1}/{max_frames}: synthetic ({status})")
            
            # Resume VM if it was running
            if frame_num < max_frames - 1:  # Don't resume after last frame
                qmp.cont()
                time.sleep(1)  # Wait for execution to advance
            
            # Wait a bit between captures
            time.sleep(0.5)
    
    # Shutdown
    print(f"\n[5] Shutting down QEMU...")
    qmp._send_command({'execute': 'quit'})
    qmp.close()
    qemu_proc.wait(timeout=10)
    
    # Encode MKV
    if frames_data:
        print(f"\n[6] Encoding {len(frames_data)} frames to MKV...")
        all_frames = b''.join(frames_data)
        
        encode_mkv(
            payload=all_frames,
            output_path=output_mkv,
            metadata={
                'type': 'simple_boot_trace',
                'total_frames': len(frames_data),
                'grid_width': 256,
                'grid_height': 256,
                'delta_encoding': 'xor'
            }
        )
        
        print(f"\n✓ Trace complete: {output_mkv}")
        return output_mkv
    else:
        print(f"\n✗ No frames captured")
        return None


def main():
    parser = argparse.ArgumentParser(
        description="Simplified spatial boot trace capture"
    )
    parser.add_argument('disk', help='Disk image path')
    parser.add_argument('--output', '-o', default='boot_trace.mkv')
    parser.add_argument('--max-frames', type=int, default=100)
    
    args = parser.parse_args()
    
    capture_boot_trace_simple(args.disk, args.output, args.max_frames)


if __name__ == '__main__':
    main()