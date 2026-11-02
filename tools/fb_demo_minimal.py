#!/usr/bin/env python3
"""
fb_demo_minimal.py — Minimal framebuffer demo.

Shows how to write pixels directly to /dev/fb0.
Run with: sudo python3 fb_demo_minimal.py
"""

import os
import struct
import fcntl
import sys


def main():
    fb_path = '/dev/fb0'

    print(f"Opening framebuffer: {fb_path}")

    # Open framebuffer
    try:
        fd = os.open(fb_path, os.O_RDWR | os.O_SYNC)
    except (FileNotFoundError, PermissionError) as e:
        print(f"Failed to open {fb_path}: {e}")
        print("Try running with: sudo")
        return

    # Get screen info
    FBIOGET_VSCREENINFO = 0x4600
    FBIOGET_FSCREENINFO = 0x4602

    vinfo = bytearray(88)
    finfo = bytearray(32)

    fcntl.ioctl(fd, FBIOGET_VSCREENINFO, vinfo)
    fcntl.ioctl(fd, FBIOGET_FSCREENINFO, finfo)

    width = struct.unpack_from('I', vinfo, 0)[0]
    height = struct.unpack_from('I', vinfo, 4)[0]
    bits_per_pixel = struct.unpack_from('I', vinfo, 28)[0]
    bytes_per_pixel = bits_per_pixel // 8

    print(f"Screen: {width}x{height}, {bits_per_pixel}bpp ({bytes_per_pixel} bytes/pixel)")

    # Clear screen (black)
    print("Clearing screen...")
    if bits_per_pixel == 32:
        pixel = struct.pack('BBBB', 0, 0, 0, 255)  # BGRA black
    elif bits_per_pixel == 24:
        pixel = struct.pack('BBB', 0, 0, 0)  # BGR black
    elif bits_per_pixel == 16:
        pixel = struct.pack('H', 0)  # RGB565 black
    else:
        print(f"Unsupported format: {bits_per_pixel}bpp")
        os.close(fd)
        return

    pixels = pixel * (width * height)
    os.pwrite(fd, pixels, 0)

    # Draw a white rectangle
    print("Drawing white rectangle...")
    if bits_per_pixel == 32:
        white = struct.pack('BBBB', 255, 255, 255, 255)
    elif bits_per_pixel == 24:
        white = struct.pack('BBB', 255, 255, 255)
    elif bits_per_pixel == 16:
        # RGB565 white
        white = struct.pack('H', 0xFFFF)

    # Draw 100×100 rectangle at (100, 100)
    for y in range(100, 200):
        for x in range(100, 200):
            offset = (y * width + x) * bytes_per_pixel
            os.pwrite(fd, white, offset)

    print("Done! Press Ctrl+C to clear and exit...")

    try:
        while True:
            import time
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nClearing screen and exiting...")
        os.pwrite(fd, pixels, 0)
        os.close(fd)


if __name__ == '__main__':
    main()