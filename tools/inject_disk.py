#!/usr/bin/env python3
"""Inject a disk image into the GPU pixel memory at the disk offset (0x81000000)."""
import sys
import numpy as np

def inject_disk(npy_path: str, disk_path: str, output_path: str = None) -> None:
    """Read the .npy pixel memory, inject disk at 0x81000000 / 4, save back."""
    if output_path is None:
        output_path = npy_path  # modify in-place
    
    print(f"[1] Loading pixel memory: {npy_path}")
    pixels = np.load(npy_path)
    print(f"    Shape: {pixels.shape}, dtype: {pixels.dtype}")
    
    # 0x81000000 is the disk base in GPU memory
    # Each pixel is 4 x uint8 (RGBA), we treat it as 4 x u32 per pixel
    # pixels shape is (H, W, 4) where each channel is uint8
    # Memory is linear: pixel[y][x][c] = byte_at(y * W * 4 + x * 4 + c)
    total_bytes = pixels.size
    
    disk_addr = 0x02000000  # 32MB, within 64MB pixel memory
    
    if disk_addr >= total_bytes:
        print(f"ERROR: disk address 0x{disk_addr:08x} is beyond memory size {total_bytes}")
        sys.exit(1)
    
    print(f"[2] Loading disk: {disk_path}")
    with open(disk_path, "rb") as f:
        disk_data = f.read()
    print(f"    {len(disk_data)} bytes")
    
    # Convert pixels to flat byte array for easy indexing
    flat = pixels.ravel()
    
    end_addr = disk_addr + len(disk_data)
    if end_addr > total_bytes:
        print(f"    WARNING: disk extends past end of memory, truncating to {total_bytes - disk_addr} bytes")
        disk_data = disk_data[:total_bytes - disk_addr]
    
    # Write disk data into flat byte array
    for i, b in enumerate(disk_data):
        flat[disk_addr + i] = b
    
    # Reshape back
    pixels[:] = flat.reshape(pixels.shape)
    
    print(f"[3] Saving: {output_path}")
    np.save(output_path, pixels)
    print(f"    Done. Wrote {len(disk_data)} bytes starting at 0x{disk_addr:08x}")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: inject_disk.py <npy_path> <disk_path> [output_path]")
        sys.exit(1)
    inject_disk(*sys.argv[1:4])
