#!/usr/bin/env python3
"""
Boot Ubuntu Desktop from GPU-native VirtIO Pixel block device.

This script orchestrates the complete "Screen is the Hard Drive" pipeline:
1. Launches wgsl_virtio_hypervisor_hilbert.py as a socket server
2. Exposes a Unix domain socket that QEMU's virtio-blk can connect to
3. For each sector request, triggers GPU extraction from visual_audio.mkv
4. Returns bytes directly to QEMU via the socket

This enables Ubuntu Desktop to boot from a purely spatial representation
without any on-disk extraction.
"""

import asyncio
import os
import sys
import socket
import struct
import subprocess
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.wgsl_virtio_hypervisor_hilbert import WGPUVirtioHypervisorHilbert


class VirtIOGPUServer:
    """
    Socket server that bridges QEMU's virtio-blk to GPU-native pixel extraction.

    Protocol:
    - Client (QEMU) sends: [sector_id (4 bytes LE)][sector_count (4 bytes LE)]
    - Server responds: [sector_count * 512 bytes] (extracted from GPU)
    """

    def __init__(self, socket_path: str = "/tmp/virtio_gpu.sock", mkv_path: str = "visual_audio.mkv"):
        self.socket_path = socket_path
        self.mkv_path = Path(mkv_path)
        self.hypervisor = None
        self.server = None
        self.running = False
        self.gpu_state = None
        self.stats = {
            'requests': 0,
            'sectors_read': 0,
            'errors': 0,
        }

    async def start(self):
        """Start the VirtIO GPU server."""
        print("=" * 80)
        print("VIRTIO GPU SERVER - Booting Ubuntu from Spatial Pixels")
        print("=" * 80)

        # Clean up old socket
        if os.path.exists(self.socket_path):
            os.unlink(self.socket_path)

        # Initialize GPU hypervisor
        print("\n[1] Initializing GPU VirtIO hypervisor...")
        self.hypervisor = WGPUVirtioHypervisorHilbert()
        success = await self.hypervisor.initialize()
        if not success:
            print("✗ GPU initialization failed")
            return False

        # Compile shader
        print("[2] Compiling VirtIO WGSL shader...")
        if not self.hypervisor.compile_shader():
            print("✗ Shader compilation failed")
            return False

        # Load MKV frame (for now, use a pre-extracted test frame)
        # TODO: Extract first frame from full visual_audio.mkv
        mkv_frame_path = Path("mkv_frame_test.png")
        if not mkv_frame_path.exists():
            print(f"⚠ MKV frame not found: {mkv_frame_path}")
            print("  Extracting first frame from MKV...")
            try:
                subprocess.run([
                    "ffmpeg", "-i", str(self.mkv_path),
                    "-vf", "select='eq(n\\,0)'", "-vframes", "1",
                    "-pix_fmt", "rgb24", str(mkv_frame_path)
                ], check=True, capture_output=True)
                print(f"  ✓ Extracted frame: {mkv_frame_path}")
            except subprocess.CalledProcessError as e:
                print(f"✗ Frame extraction failed: {e}")
                return False

        print(f"[3] Loading MKV frame: {mkv_frame_path}")
        mkv_texture, width, height = self.hypervisor.load_mkv_frame_texture(str(mkv_frame_path))
        print(f"  ✓ Loaded MKV frame: {width}×{height} pixels")

        # Load driver (use test driver for now)
        print("[4] Loading VirtIO Pixel driver...")
        driver_path = Path("virtio_pixel_multi_sector_test.glyph")
        if not driver_path.exists():
            print(f"✗ Driver not found: {driver_path}")
            return False

        driver_buffer, driver_width, driver_height = self.hypervisor.load_driver_image(str(driver_path))
        print(f"  ✓ Loaded driver: {driver_width}×{driver_height} pixels")

        # Create GPU buffers
        print("[5] Creating GPU buffers...")
        cpu_state_buffer = self.hypervisor.create_cpu_state_buffer()
        output_buffer = self.hypervisor.create_output_buffer()
        dims_buffer = self.hypervisor.create_image_dims_buffer(driver_width, driver_height, max_instructions=5000, hilbert_order=9)
        virtio_mmio_buffer = self.hypervisor.create_virtio_mmio_buffer(sector_count=8)
        dma_buffer = self.hypervisor.create_dma_buffer(size=4096)  # 8 sectors × 512 bytes

        # Store buffers for reuse
        self.gpu_state = {
            'driver_buffer': driver_buffer,
            'mkv_texture': mkv_texture,
            'width': driver_width,
            'height': driver_height,
            'cpu_state_buffer': cpu_state_buffer,
            'output_buffer': output_buffer,
            'dims_buffer': dims_buffer,
            'virtio_mmio_buffer': virtio_mmio_buffer,
            'dma_buffer': dma_buffer,
        }

        # Create Unix socket server
        print(f"[6] Starting socket server: {self.socket_path}")
        self.server = await asyncio.start_unix_server(
            self.handle_client,
            path=self.socket_path
        )
        os.chmod(self.socket_path, 0o666)  # Make socket accessible

        self.running = True
        print("✓ VirtIO GPU server ready")
        print("\n" + "=" * 80)
        print("SERVER READY - Waiting for QEMU connections")
        print("=" * 80 + "\n")

        return True

    async def handle_client(self, reader, writer):
        """Handle QEMU virtio-blk client requests."""
        client_addr = writer.get_extra_info('peername')
        print(f"[+] Client connected: {client_addr}")

        try:
            while self.running:
                # Read request: sector_id (4 bytes) + sector_count (4 bytes)
                request_header = await reader.readexactly(8)
                sector_id, sector_count = struct.unpack('<II', request_header)

                print(f"[REQUEST] sector_id={sector_id}, sector_count={sector_count}")

                # Trigger GPU extraction
                try:
                    extracted_data = await self.extract_sector_gpu(sector_id, sector_count)

                    # Write response: sector_count * 512 bytes
                    writer.write(extracted_data)
                    await writer.drain()

                    self.stats['requests'] += 1
                    self.stats['sectors_read'] += sector_count

                    print(f"[RESPONSE] {len(extracted_data)} bytes sent")

                except Exception as e:
                    print(f"[ERROR] GPU extraction failed: {e}")
                    self.stats['errors'] += 1
                    # Send zeros on error
                    writer.write(bytes(sector_count * 512))
                    await writer.drain()

        except asyncio.IncompleteReadError:
            print(f"[-] Client disconnected: {client_addr}")
        except Exception as e:
            print(f"[-] Client error: {e}")
        finally:
            writer.close()
            await writer.wait_closed()

    async def extract_sector_gpu(self, sector_id: int, sector_count: int) -> bytes:
        """
        Extract sectors using GPU VirtIO hypervisor.

        This is the core "Screen is the Hard Drive" operation:
        1. Write sector_id and sector_count to MMIO registers
        2. Trigger GPU compute shader
        3. .glyph driver loops through sectors, maps via Hilbert d2xy
        4. LDP opcodes fetch pixels from MKV texture
        5. STR opcodes write to DMA buffer
        6. Read DMA buffer and return bytes
        """
        if not self.hypervisor:
            raise RuntimeError("Hypervisor not initialized")

        # Update DMA buffer size if needed
        dma_size_needed = sector_count * 512 // 4  # u32 count
        if dma_size_needed > self.gpu_state['dma_buffer'].size // 4:
            print(f"[WARN] DMA buffer too small, need {dma_size_needed} u32")
            # For now, truncate to buffer size
            sector_count = (self.gpu_state['dma_buffer'].size // 4) // 512

        # Trigger VirtIO request
        self.hypervisor.trigger_virtio_request(
            self.gpu_state['virtio_mmio_buffer'],
            sector_id,
            sector_count
        )

        # Run GPU compute
        self.hypervisor.run_compute(
            driver_buffer=self.gpu_state['driver_buffer'],
            mkv_frame_texture=self.gpu_state['mkv_texture'],
            width=self.gpu_state['width'],
            height=self.gpu_state['height'],
            cpu_state_buffer=self.gpu_state['cpu_state_buffer'],
            output_buffer=self.gpu_state['output_buffer'],
            dims_buffer=self.gpu_state['dims_buffer'],
            virtio_mmio_buffer=self.gpu_state['virtio_mmio_buffer'],
            dma_buffer=self.gpu_state['dma_buffer'],
            max_instructions=5000,
            debug=False
        )

        # Read DMA buffer
        dma_values = await self.hypervisor.read_dma_buffer(
            self.gpu_state['dma_buffer'],
            sector_count * 512 // 4
        )

        # Convert to bytes (little-endian)
        extracted_bytes = struct.pack(f"<{len(dma_values)}I", *dma_values)

        return extracted_bytes

    async def stop(self):
        """Stop the server and cleanup."""
        self.running = False
        if self.server:
            self.server.close()
            await self.server.wait_closed()

        if os.path.exists(self.socket_path):
            os.unlink(self.socket_path)

        print("\n" + "=" * 80)
        print("VIRTIO GPU SERVER STATISTICS")
        print("=" * 80)
        print(f"Requests handled: {self.stats['requests']}")
        print(f"Sectors read: {self.stats['sectors_read']}")
        print(f"Errors: {self.stats['errors']}")
        print("=" * 80)


async def launch_qemu(socket_path: str = "/tmp/virtio_gpu.sock"):
    """
    Launch QEMU with virtio-blk connected to our GPU socket.

    QEMU virtio-blk can connect to a Unix socket via the "socket:" backend.
    """
    print("\n" + "=" * 80)
    print("LAUNCHING QEMU WITH VIRTIO GPU STORAGE")
    print("=" * 80)

    # TODO: For now, this is a stub. The actual QEMU launch requires:
    # 1. A kernel (Ubuntu kernel with virtio-blk support)
    # 2. An initrd (Ubuntu initramfs)
    # 3. Proper QEMU command line with -drive file=socket:...,format=raw,if=virtio

    qemu_cmd = [
        "qemu-system-x86_64",
        "-m", "2G",
        "-smp", "2",
        "-nographic",
        "-drive", f"file=socket:{socket_path},format=raw,if=virtio,index=0",
        # TODO: Add kernel, initrd, append parameters
    ]

    print("QEMU command (not yet executed):")
    print(" ".join(qemu_cmd))
    print("\n⚠ QEMU launch not implemented yet")
    print("  This requires:")
    print("  - Ubuntu kernel image")
    print("  - Initramfs")
    print("  - Boot parameters")
    print("=" * 80)

    return None


async def main():
    """Main entry point."""
    socket_path = "/tmp/virtio_gpu.sock"

    # Start server
    server = VirtIOGPUServer(socket_path=socket_path)
    if not await server.start():
        print("✗ Failed to start server")
        return 1

    # In the future, we can launch QEMU in parallel
    # qemu_process = await launch_qemu(socket_path)

    # Keep server running
    print("Press Ctrl+C to stop server...")
    try:
        while server.running:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        print("\n\nShutting down...")
        await server.stop()

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))