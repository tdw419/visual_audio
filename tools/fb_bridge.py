#!/usr/bin/env python3
"""
fb_bridge.py — Zero-Dependency Token-to-Framebuffer Bridge for Geometry OS & Pixel Linux.

Bridges LLM text token streams directly to low-level Linux framebuffer (/dev/fb0)
or visual display files without requiring external packages (no numpy/PIL required).

Supported Command Syntax:
  [[FB:FILL #RRGGBB]]
  [[FB:RECT x y width height #RRGGBB]]
  [[FB:GRADIENT x y width height #HEX1 #HEX2 [horizontal|vertical]]]
  [[FB:TEXT x y "string" #RRGGBB]]
  [[FB:CLEAR]]

Modes:
  1. Direct CLI Mode:
     python3 fb_bridge.py rect 100 200 300 400 '#0000FF'
  2. Daemon Pipe Mode:
     python3 fb_bridge.py daemon --pipe /tmp/fb_bridge.pipe
  3. Stream Filter Mode:
     my_agent | python3 fb_bridge.py filter
"""

import argparse
import fcntl
import math
import mmap
import os
import re
import struct
import sys
import time
from typing import Optional, Tuple

# Linux Framebuffer ioctl constants
FBIOGET_VSCREENINFO = 0x4600
FBIOGET_FSCREENINFO = 0x4602

# Minimal 8x8 Bitmap Font for ASCII 32-126 (Standard IBM VGA BIOS 8x8 font slice)
FONT_8X8 = {
    ' ': [0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00],
    '!': [0x18, 0x3C, 0x3C, 0x18, 0x18, 0x00, 0x18, 0x00],
    '"': [0x66, 0x66, 0x24, 0x00, 0x00, 0x00, 0x00, 0x00],
    '#': [0x6C, 0x6C, 0xFE, 0x6C, 0xFE, 0x6C, 0x6C, 0x00],
    '$': [0x18, 0x7E, 0xC0, 0x7C, 0x06, 0xFC, 0x18, 0x00],
    '%': [0x00, 0xC6, 0xCC, 0x18, 0x30, 0x66, 0xC6, 0x00],
    '&': [0x38, 0x6C, 0x38, 0x76, 0xDC, 0xCC, 0x76, 0x00],
    "'": [0x18, 0x18, 0x30, 0x00, 0x00, 0x00, 0x00, 0x00],
    '(': [0x0C, 0x18, 0x30, 0x30, 0x30, 0x18, 0x0C, 0x00],
    ')': [0x30, 0x18, 0x0C, 0x0C, 0x0C, 0x18, 0x30, 0x00],
    '*': [0x00, 0x66, 0x3C, 0xFF, 0x3C, 0x66, 0x00, 0x00],
    '+': [0x00, 0x18, 0x18, 0x7E, 0x18, 0x18, 0x00, 0x00],
    ',': [0x00, 0x00, 0x00, 0x00, 0x00, 0x18, 0x18, 0x30],
    '-': [0x00, 0x00, 0x00, 0x7E, 0x00, 0x00, 0x00, 0x00],
    '.': [0x00, 0x00, 0x00, 0x00, 0x00, 0x18, 0x18, 0x00],
    '/': [0x06, 0x0C, 0x18, 0x30, 0x60, 0xC0, 0x80, 0x00],
    '0': [0x3C, 0x66, 0xC3, 0xC3, 0xC3, 0x66, 0x3C, 0x00],
    '1': [0x18, 0x38, 0x18, 0x18, 0x18, 0x18, 0x7E, 0x00],
    '2': [0x7C, 0xC6, 0x0E, 0x3C, 0x78, 0xE0, 0xFF, 0x00],
    '3': [0x7E, 0x0C, 0x18, 0x3C, 0x06, 0xC6, 0x7C, 0x00],
    '4': [0x1C, 0x3C, 0x6C, 0xCC, 0xFE, 0x0C, 0x1E, 0x00],
    '5': [0xFE, 0xC0, 0xFC, 0x06, 0x06, 0xC6, 0x7C, 0x00],
    '6': [0x38, 0x60, 0xC0, 0xFC, 0xC6, 0xC6, 0x7C, 0x00],
    '7': [0xFE, 0xC6, 0x0C, 0x18, 0x30, 0x30, 0x30, 0x00],
    '8': [0x7C, 0xC6, 0xC6, 0x7C, 0xC6, 0xC6, 0x7C, 0x00],
    '9': [0x7C, 0xC6, 0xC6, 0x7E, 0x06, 0x0C, 0x78, 0x00],
    ':': [0x00, 0x18, 0x18, 0x00, 0x18, 0x18, 0x00, 0x00],
    ';': [0x00, 0x18, 0x18, 0x00, 0x18, 0x18, 0x30, 0x00],
    '<': [0x06, 0x0C, 0x18, 0x30, 0x18, 0x0C, 0x06, 0x00],
    '=': [0x00, 0x7E, 0x00, 0x7E, 0x00, 0x00, 0x00, 0x00],
    '>': [0x60, 0x30, 0x18, 0x0C, 0x18, 0x30, 0x60, 0x00],
    '?': [0x7C, 0xC6, 0x0C, 0x18, 0x18, 0x00, 0x18, 0x00],
    '@': [0x7C, 0xC6, 0xDE, 0xDE, 0xDC, 0xC0, 0x7C, 0x00],
    'A': [0x38, 0x6C, 0xC6, 0xC6, 0xFE, 0xC6, 0xC6, 0x00],
    'B': [0xFC, 0x66, 0x66, 0x7C, 0x66, 0x66, 0xFC, 0x00],
    'C': [0x3C, 0x66, 0xC0, 0xC0, 0xC0, 0x66, 0x3C, 0x00],
    'D': [0xF8, 0x6C, 0x66, 0x66, 0x66, 0x6C, 0xF8, 0x00],
    'E': [0xFE, 0x62, 0x68, 0x78, 0x68, 0x62, 0xFE, 0x00],
    'F': [0xFE, 0x62, 0x68, 0x78, 0x68, 0x60, 0xF0, 0x00],
    'G': [0x3C, 0x66, 0xC0, 0xC0, 0xCE, 0x66, 0x3E, 0x00],
    'H': [0xC6, 0xC6, 0xC6, 0xFE, 0xC6, 0xC6, 0xC6, 0x00],
    'I': [0x7E, 0x18, 0x18, 0x18, 0x18, 0x18, 0x7E, 0x00],
    'J': [0x1E, 0x0C, 0x0C, 0x0C, 0xCC, 0xCC, 0x78, 0x00],
    'K': [0xE6, 0x66, 0x6C, 0x78, 0x6C, 0x66, 0xE6, 0x00],
    'L': [0xF0, 0x60, 0x60, 0x60, 0x62, 0x66, 0xFE, 0x00],
    'M': [0xC6, 0xEE, 0xFE, 0xFE, 0xD6, 0xC6, 0xC6, 0x00],
    'N': [0xC6, 0xE6, 0xF6, 0xDE, 0xCE, 0xC6, 0xC6, 0x00],
    'O': [0x38, 0x6C, 0xC6, 0xC6, 0xC6, 0x6C, 0x38, 0x00],
    'P': [0xFC, 0x66, 0x66, 0x7C, 0x60, 0x60, 0xF0, 0x00],
    'Q': [0x7C, 0xC6, 0xC6, 0xC6, 0xD6, 0x7C, 0x0E, 0x00],
    'R': [0xFC, 0x66, 0x66, 0x7C, 0x6C, 0x66, 0xE6, 0x00],
    'S': [0x7C, 0xC6, 0x60, 0x38, 0x0C, 0xC6, 0x7C, 0x00],
    'T': [0x7E, 0x7E, 0x18, 0x18, 0x18, 0x18, 0x18, 0x00],
    'U': [0xC6, 0xC6, 0xC6, 0xC6, 0xC6, 0xC6, 0x7C, 0x00],
    'V': [0xC6, 0xC6, 0xC6, 0xC6, 0x6C, 0x38, 0x10, 0x00],
    'W': [0xC6, 0xC6, 0xC6, 0xD6, 0xFE, 0xEE, 0xC6, 0x00],
    'X': [0xC6, 0x6C, 0x38, 0x38, 0x6C, 0xC6, 0xC6, 0x00],
    'Y': [0x66, 0x66, 0x66, 0x3C, 0x18, 0x18, 0x3C, 0x00],
    'Z': [0xFE, 0xC6, 0x0C, 0x18, 0x30, 0x63, 0xFE, 0x00],
    '[': [0x3C, 0x30, 0x30, 0x30, 0x30, 0x30, 0x3C, 0x00],
    '\\': [0xC0, 0x60, 0x30, 0x18, 0x0C, 0x06, 0x02, 0x00],
    ']': [0x3C, 0x0C, 0x0C, 0x0C, 0x0C, 0x0C, 0x3C, 0x00],
    '^': [0x10, 0x38, 0x6C, 0xC6, 0x00, 0x00, 0x00, 0x00],
    '_': [0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0xFF, 0x00],
    'a': [0x00, 0x00, 0x78, 0x0C, 0x7C, 0xCC, 0x76, 0x00],
    'b': [0xE0, 0x60, 0x7C, 0x66, 0x66, 0x66, 0xDC, 0x00],
    'c': [0x00, 0x00, 0x78, 0xCC, 0xC0, 0xCC, 0x78, 0x00],
    'd': [0x1C, 0x0C, 0x7C, 0xCC, 0xCC, 0xCC, 0x76, 0x00],
    'e': [0x00, 0x00, 0x78, 0xCC, 0xFC, 0xC0, 0x78, 0x00],
    'f': [0x38, 0x6C, 0x60, 0xF0, 0x60, 0x60, 0xF0, 0x00],
    'g': [0x00, 0x00, 0x76, 0xCC, 0xCC, 0x7C, 0x0C, 0xF8],
    'h': [0xE0, 0x60, 0x6C, 0x76, 0x66, 0x66, 0xE6, 0x00],
    'i': [0x18, 0x00, 0x38, 0x18, 0x18, 0x18, 0x3C, 0x00],
    'j': [0x06, 0x00, 0x0E, 0x06, 0x06, 0x66, 0x66, 0x3C],
    'k': [0xE0, 0x60, 0x66, 0x6C, 0x78, 0x6C, 0xE6, 0x00],
    'l': [0x38, 0x18, 0x18, 0x18, 0x18, 0x18, 0x3C, 0x00],
    'm': [0x00, 0x00, 0xEC, 0xFE, 0xD6, 0xD6, 0xD6, 0x00],
    'n': [0x00, 0x00, 0xDC, 0x66, 0x66, 0x66, 0x66, 0x00],
    'o': [0x00, 0x00, 0x78, 0xCC, 0xCC, 0xCC, 0x78, 0x00],
    'p': [0x00, 0x00, 0xDC, 0x66, 0x66, 0x7C, 0x60, 0xF0],
    'q': [0x00, 0x00, 0x76, 0xCC, 0xCC, 0x7C, 0x0C, 0x1E],
    'r': [0x00, 0x00, 0xDC, 0x76, 0x60, 0x60, 0xF0, 0x00],
    's': [0x00, 0x00, 0x7C, 0xC0, 0x78, 0x0C, 0xF8, 0x00],
    't': [0x10, 0x30, 0x7C, 0x30, 0x30, 0x34, 0x18, 0x00],
    'u': [0x00, 0x00, 0xCC, 0xCC, 0xCC, 0xCC, 0x76, 0x00],
    'v': [0x00, 0x00, 0xC6, 0xC6, 0xC6, 0x6C, 0x38, 0x00],
    'w': [0x00, 0x00, 0xC6, 0xD6, 0xD6, 0xFE, 0x6C, 0x00],
    'x': [0x00, 0x00, 0xC6, 0x6C, 0x38, 0x6C, 0xC6, 0x00],
    'y': [0x00, 0x00, 0xC6, 0xC6, 0xC6, 0x7E, 0x06, 0xFC],
    'z': [0x00, 0x00, 0xFE, 0x8C, 0x18, 0x32, 0xFE, 0x00],
}


class FramebufferDevice:
    """Zero-dependency direct Linux framebuffer (/dev/fb0) interface."""

    def __init__(self, dev_path: str = "/dev/fb0", fallback_bmp: str = "/tmp/simulated_fb0.bmp", default_res: Tuple[int, int] = (1024, 768)):
        self.dev_path = dev_path
        self.fallback_bmp = fallback_bmp
        self.width = default_res[0]
        self.height = default_res[1]
        self.bpp = 32
        self.line_length = self.width * 4
        self.is_hardware = False
        self.fb_file = None
        self.mm = None
        self.software_buf = None

        self._init_device()

    def _init_device(self):
        if os.path.exists(self.dev_path):
            try:
                self.fb_file = open(self.dev_path, "r+b")
                vinfo = fcntl.ioctl(self.fb_file, FBIOGET_VSCREENINFO, b"\x00" * 160)
                self.width, self.height, vxres, vyres, xoff, yoff, self.bpp = struct.unpack("IIIIIII", vinfo[:28])

                finfo = fcntl.ioctl(self.fb_file, FBIOGET_FSCREENINFO, b"\x00" * 80)
                self.line_length = struct.unpack("I", finfo[44:48])[0]
                smem_len = struct.unpack("I", finfo[24:28])[0] or (self.line_length * self.height)

                self.mm = mmap.mmap(self.fb_file.fileno(), smem_len, mmap.MAP_SHARED, mmap.PROT_WRITE | mmap.PROT_READ)
                self.is_hardware = True
                print(f"[fb_bridge] Direct hardware {self.dev_path} active: {self.width}x{self.height} @ {self.bpp}bpp (stride {self.line_length})")
                return
            except Exception as e:
                print(f"[fb_bridge] Hardware {self.dev_path} unmapped ({e}). Falling back to software buffer.")

        # Software buffer fallback (BGRA bytearray)
        self.is_hardware = False
        self.software_buf = bytearray(self.width * self.height * 4)
        print(f"[fb_bridge] Virtual Framebuffer active ({self.width}x{self.height} @ 32bpp) -> {self.fallback_bmp}")

    def hex_to_bgra(self, hex_color: str) -> Tuple[int, int, int, int]:
        """Parse #RGB, #RRGGBB, or #RRGGBBAA into (B, G, R, A)."""
        hex_color = hex_color.lstrip("#")
        if len(hex_color) == 6:
            r = int(hex_color[0:2], 16)
            g = int(hex_color[2:4], 16)
            b = int(hex_color[4:6], 16)
            a = 255
        elif len(hex_color) == 8:
            r = int(hex_color[0:2], 16)
            g = int(hex_color[2:4], 16)
            b = int(hex_color[4:6], 16)
            a = int(hex_color[6:8], 16)
        elif len(hex_color) == 3:
            r = int(hex_color[0] * 2, 16)
            g = int(hex_color[1] * 2, 16)
            b = int(hex_color[2] * 2, 16)
            a = 255
        else:
            r, g, b, a = 255, 255, 255, 255
        return (b, g, r, a)

    def fill(self, hex_color: str):
        self.draw_rect(0, 0, self.width, self.height, hex_color)

    def draw_rect(self, x: int, y: int, w: int, h: int, hex_color: str, flush: bool = True):
        b, g, r, a = self.hex_to_bgra(hex_color)
        x1 = max(0, min(x, self.width))
        y1 = max(0, min(y, self.height))
        x2 = max(0, min(x + w, self.width))
        y2 = max(0, min(y + h, self.height))

        rw = x2 - x1
        rh = y2 - y1
        if rw <= 0 or rh <= 0:
            return

        row_bytes = bytes([b, g, r, a]) * rw
        if self.is_hardware:
            for row in range(y1, y2):
                offset = (row * self.line_length) + (x1 * 4)
                self.mm[offset:offset + len(row_bytes)] = row_bytes
        else:
            for row in range(y1, y2):
                offset = (row * self.width * 4) + (x1 * 4)
                self.software_buf[offset:offset + len(row_bytes)] = row_bytes
            if flush:
                self._save_bmp()

    def draw_gradient(self, x: int, y: int, w: int, h: int, hex1: str, hex2: str, orientation: str = "horizontal"):
        b1, g1, r1, a1 = self.hex_to_bgra(hex1)
        b2, g2, r2, a2 = self.hex_to_bgra(hex2)
        x1 = max(0, min(x, self.width))
        y1 = max(0, min(y, self.height))
        x2 = max(0, min(x + w, self.width))
        y2 = max(0, min(y + h, self.height))
        rw, rh = x2 - x1, y2 - y1
        if rw <= 0 or rh <= 0:
            return

        if orientation == "horizontal":
            row_buf = bytearray(rw * 4)
            for i in range(rw):
                f = i / max(1, rw - 1)
                b = int(b1 * (1.0 - f) + b2 * f)
                g = int(g1 * (1.0 - f) + g2 * f)
                r = int(r1 * (1.0 - f) + r2 * f)
                a = int(a1 * (1.0 - f) + a2 * f)
                idx = i * 4
                row_buf[idx:idx + 4] = bytes([b, g, r, a])
            row_bytes = bytes(row_buf)

            if self.is_hardware:
                for row in range(y1, y2):
                    offset = (row * self.line_length) + (x1 * 4)
                    self.mm[offset:offset + len(row_bytes)] = row_bytes
            else:
                for row in range(y1, y2):
                    offset = (row * self.width * 4) + (x1 * 4)
                    self.software_buf[offset:offset + len(row_bytes)] = row_bytes
                self._save_bmp()
        else:
            # Vertical gradient
            for row_idx, row in enumerate(range(y1, y2)):
                f = row_idx / max(1, rh - 1)
                b = int(b1 * (1.0 - f) + b2 * f)
                g = int(g1 * (1.0 - f) + g2 * f)
                r = int(r1 * (1.0 - f) + r2 * f)
                a = int(a1 * (1.0 - f) + a2 * f)
                row_bytes = bytes([b, g, r, a]) * rw

                if self.is_hardware:
                    offset = (row * self.line_length) + (x1 * 4)
                    self.mm[offset:offset + len(row_bytes)] = row_bytes
                else:
                    offset = (row * self.width * 4) + (x1 * 4)
                    self.software_buf[offset:offset + len(row_bytes)] = row_bytes
            if not self.is_hardware:
                self._save_bmp()

    def draw_text(self, x: int, y: int, text: str, hex_color: str, scale: int = 2):
        """Draw text using built-in 8x8 font with scaling."""
        cx = x
        for ch in text:
            bitmap = FONT_8X8.get(ch, FONT_8X8.get('?', [0xFF]*8))
            for row_i, byte_val in enumerate(bitmap):
                for col_i in range(8):
                    if (byte_val >> (7 - col_i)) & 1:
                        px = cx + (col_i * scale)
                        py = y + (row_i * scale)
                        self.draw_rect(px, py, scale, scale, hex_color, flush=False)
            cx += 8 * scale + 1
        if not self.is_hardware:
            self._save_bmp()

    def _save_bmp(self):
        """Write self.software_buf directly to a standard uncompressed Windows BMP file."""
        row_size = self.width * 4
        image_size = row_size * self.height
        file_size = 54 + image_size

        # BMP Header (14 bytes)
        bmp_header = struct.pack("<2sIHHI", b"BM", file_size, 0, 0, 54)
        # DIB Header (BITMAPINFOHEADER - 40 bytes)
        # Note: height is negative to indicate top-down row order
        dib_header = struct.pack("<IIIHHIIIIII", 40, self.width, -self.height & 0xFFFFFFFF, 1, 32, 0, image_size, 2835, 2835, 0, 0)

        with open(self.fallback_bmp, "wb") as f:
            f.write(bmp_header)
            f.write(dib_header)
            f.write(self.software_buf)

    def close(self):
        if self.mm is not None:
            self.mm.close()
        if self.fb_file is not None:
            self.fb_file.close()


class CommandParser:
    """Parses plain English tokens and escape sequences into framebuffer actions."""

    TOKEN_REGEX = re.compile(r"\[\[FB:(.*?)\]\]", re.IGNORECASE)

    def __init__(self, fb: FramebufferDevice):
        self.fb = fb

    def execute_line(self, line: str):
        matches = self.TOKEN_REGEX.findall(line)
        if matches:
            for match in matches:
                self._execute_single_op(match.strip())
            return

        clean = line.strip()
        if clean:
            self._execute_single_op(clean)

    def _execute_single_op(self, op: str):
        parts = op.split()
        if not parts:
            return
        cmd = parts[0].upper()
        try:
            if cmd in ("FILL", "PAINT_SCREEN"):
                color = parts[1] if len(parts) > 1 else "#0000FF"
                self.fb.fill(color)
                print(f"[fb_bridge] ✓ FILL -> {color}")

            elif cmd in ("RECT", "PAINT_RECT", "FILL_RECT"):
                x, y, w, h = int(parts[1]), int(parts[2]), int(parts[3]), int(parts[4])
                color = parts[5] if len(parts) > 5 else "#00FF00"
                self.fb.draw_rect(x, y, w, h, color)
                print(f"[fb_bridge] ✓ RECT ({x}, {y}, {w}, {h}) -> {color}")

            elif cmd in ("GRADIENT", "PAINT_GRADIENT"):
                x, y, w, h = int(parts[1]), int(parts[2]), int(parts[3]), int(parts[4])
                c1 = parts[5]
                c2 = parts[6]
                orient = parts[7] if len(parts) > 7 else "horizontal"
                self.fb.draw_gradient(x, y, w, h, c1, c2, orient)
                print(f"[fb_bridge] ✓ GRADIENT ({x}, {y}, {w}, {h}) {c1} -> {c2} ({orient})")

            elif cmd in ("TEXT", "PAINT_TEXT"):
                x, y = int(parts[1]), int(parts[2])
                rest = " ".join(parts[3:])
                match = re.search(r'["\'](.*?)["\']\s*(#\w+)?', rest)
                if match:
                    text = match.group(1)
                    color = match.group(2) or "#FFFFFF"
                else:
                    text = parts[3]
                    color = parts[4] if len(parts) > 4 else "#FFFFFF"
                self.fb.draw_text(x, y, text, color)
                print(f"[fb_bridge] ✓ TEXT ({x}, {y}) '{text}' -> {color}")

            elif cmd in ("CLEAR", "RESET"):
                self.fb.fill("#000000")
                print(f"[fb_bridge] ✓ CLEAR -> #000000")
        except Exception as e:
            print(f"[fb_bridge] Error executing '{op}': {e}", file=sys.stderr)


def run_daemon(pipe_path: str, fb: FramebufferDevice):
    if os.path.exists(pipe_path):
        os.remove(pipe_path)
    os.mkfifo(pipe_path)
    print(f"[fb_bridge] Daemon active. Listening on FIFO pipe: {pipe_path}")
    parser = CommandParser(fb)
    try:
        while True:
            with open(pipe_path, "r") as fifo:
                for line in fifo:
                    parser.execute_line(line)
    except KeyboardInterrupt:
        print("\n[fb_bridge] Daemon terminated.")
    finally:
        if os.path.exists(pipe_path):
            os.remove(pipe_path)


def run_filter(fb: FramebufferDevice):
    parser = CommandParser(fb)
    for line in sys.stdin:
        sys.stdout.write(line)
        sys.stdout.flush()
        parser.execute_line(line)


def main():
    parser = argparse.ArgumentParser(description="Token-to-Framebuffer Bridge for Geometry OS")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_rect = sub.add_parser("rect")
    p_rect.add_argument("x", type=int)
    p_rect.add_argument("y", type=int)
    p_rect.add_argument("w", type=int)
    p_rect.add_argument("h", type=int)
    p_rect.add_argument("color", type=str, default="#0000FF", nargs="?")

    p_fill = sub.add_parser("fill")
    p_fill.add_argument("color", type=str, default="#0000FF")

    p_text = sub.add_parser("text")
    p_text.add_argument("x", type=int)
    p_text.add_argument("y", type=int)
    p_text.add_argument("text", type=str)
    p_text.add_argument("color", type=str, default="#FFFFFF", nargs="?")
    p_text.add_argument("--scale", type=int, default=2)

    p_grad = sub.add_parser("gradient")
    p_grad.add_argument("x", type=int)
    p_grad.add_argument("y", type=int)
    p_grad.add_argument("w", type=int)
    p_grad.add_argument("h", type=int)
    p_grad.add_argument("c1", type=str)
    p_grad.add_argument("c2", type=str)
    p_grad.add_argument("--orientation", default="horizontal", choices=["horizontal", "vertical"])

    p_daemon = sub.add_parser("daemon")
    p_daemon.add_argument("--pipe", default="/tmp/fb_bridge.pipe")

    sub.add_parser("filter")

    args = parser.parse_args()
    fb = FramebufferDevice()

    try:
        if args.cmd == "rect":
            fb.draw_rect(args.x, args.y, args.w, args.h, args.color)
        elif args.cmd == "fill":
            fb.fill(args.color)
        elif args.cmd == "text":
            fb.draw_text(args.x, args.y, args.text, args.color, scale=args.scale)
        elif args.cmd == "gradient":
            fb.draw_gradient(args.x, args.y, args.w, args.h, args.c1, args.c2, args.orientation)
        elif args.cmd == "daemon":
            run_daemon(args.pipe, fb)
        elif args.cmd == "filter":
            run_filter(fb)
    finally:
        fb.close()


if __name__ == "__main__":
    main()
