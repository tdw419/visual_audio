#!/usr/bin/env python3
"""
fb_text_editor.py — Pixel-native framebuffer text editor.

A minimalist text editor that writes directly to /dev/fb0 without X11/Wayland.
Uses VGA 8x16 bitmap fonts, evdev input handling, and direct framebuffer writes.

Architecture:
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  InputDevice │────▶│ TextBuffer   │────▶│ Framebuffer  │
│  (evdev)     │     │  (lines)     │     │  (/dev/fb0)  │
└──────────────┘     └──────────────┘     └──────────────┘
                            │                       │
                            ▼                       ▼
                      TextBufferLogic          FBRenderer
                      (edit, nav, etc.)       (VGA fonts)

Usage:
    sudo python3 fb_text_editor.py --fb /dev/fb0

Controls:
    Arrow keys: Move cursor
    Backspace: Delete character
    Enter: Insert newline
    Ctrl+Q: Quit
    Ctrl+S: Save to file
"""

import sys
import os
import struct
import fcntl
import time
from typing import List, Tuple, Optional
from dataclasses import dataclass, field

# Import components
from evdev_input import InputDevice, KeyEvent, MouseEvent, find_keyboard_device


# ============================================================================
# TEXT BUFFER
# ============================================================================

@dataclass
class Cursor:
    """Cursor position in text buffer."""
    row: int = 0
    col: int = 0

    def __post_init__(self):
        self.row = max(0, self.row)
        self.col = max(0, self.col)


@dataclass
class TextBuffer:
    """In-memory text buffer (like Vim/EasyMotion but simpler)."""
    lines: List[str] = field(default_factory=lambda: [''])
    cursor: Cursor = field(default_factory=Cursor)

    def insert_char(self, char: str) -> None:
        """Insert character at cursor position."""
        row, col = self.cursor.row, self.cursor.col
        line = self.lines[row]

        # Insert character
        new_line = line[:col] + char + line[col:]
        self.lines[row] = new_line

        # Move cursor
        self.cursor.col += 1

    def insert_newline(self) -> None:
        """Insert newline at cursor position."""
        row, col = self.cursor.row, self.cursor.col
        line = self.lines[row]

        # Split line at cursor
        left = line[:col]
        right = line[col:]

        # Insert new line
        self.lines[row] = left
        self.lines.insert(row + 1, right)

        # Move cursor to start of next line
        self.cursor.row += 1
        self.cursor.col = 0

    def delete_char(self) -> None:
        """Delete character before cursor (backspace)."""
        row, col = self.cursor.row, self.cursor.col

        if col > 0:
            # Delete character on current line
            line = self.lines[row]
            new_line = line[:col-1] + line[col:]
            self.lines[row] = new_line
            self.cursor.col -= 1
        elif row > 0:
            # Merge with previous line
            prev_line = self.lines[row-1]
            curr_line = self.lines[row]
            self.lines[row-1] = prev_line + curr_line
            self.lines.pop(row)
            self.cursor.row -= 1
            self.cursor.col = len(prev_line)

    def move_cursor(self, dx: int, dy: int, max_cols: int = 80) -> None:
        """Move cursor by dx/dy (clamped to buffer bounds)."""
        self.cursor.row = max(0, min(len(self.lines) - 1, self.cursor.row + dy))
        self.cursor.col = max(0, min(len(self.lines[self.cursor.row]), self.cursor.col + dx))

    def get_text(self) -> str:
        """Get full text as string."""
        return '\n'.join(self.lines)

    def set_text(self, text: str) -> None:
        """Set text from string."""
        self.lines = text.split('\n')
        if not self.lines:
            self.lines = ['']
        self.cursor.row = 0
        self.cursor.col = 0


# ============================================================================
# FRAMEBUFFER RENDERER
# ============================================================================

class FBRenderer:
    """Direct framebuffer renderer using VGA fonts."""

    def __init__(self, fb_path: str = '/dev/fb0'):
        self.fb_path = fb_path
        self.fd = None
        self.width = 0
        self.height = 0
        self.bits_per_pixel = 0
        self.bytes_per_pixel = 0

        # VGA font
        self.char_width = 8
        self.char_height = 16

    def open(self) -> bool:
        """Open framebuffer device."""
        try:
            self.fd = os.open(self.fb_path, os.O_RDWR | os.O_SYNC)
            self._get_screen_info()
            print(f"Framebuffer: {self.width}x{self.height}, {self.bits_per_pixel}bpp")
            return True
        except (FileNotFoundError, PermissionError) as e:
            print(f"Failed to open framebuffer: {e}")
            return False

    def close(self) -> None:
        """Close framebuffer device."""
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None

    def _get_screen_info(self) -> None:
        """Get screen dimensions and format."""
        # Get variable info
        FBIOGET_VSCREENINFO = 0x4600
        vinfo = bytearray(88)
        fcntl.ioctl(self.fd, FBIOGET_VSCREENINFO, vinfo)

        self.width = struct.unpack_from('I', vinfo, 0)[0]
        self.height = struct.unpack_from('I', vinfo, 4)[0]
        self.bits_per_pixel = struct.unpack_from('I', vinfo, 28)[0]
        self.bytes_per_pixel = self.bits_per_pixel // 8

    def clear(self, color: Tuple[int, int, int] = (0, 0, 0)) -> None:
        """Clear screen with color (RGB)."""
        # Create full-screen pixel buffer
        if self.bits_per_pixel == 32:
            # RGBA/BGRX format
            pixel = struct.pack('BBBB', color[2], color[1], color[0], 255)  # BGRA
            pixels = pixel * (self.width * self.height)
        elif self.bits_per_pixel == 24:
            # RGB format
            pixel = struct.pack('BBB', color[2], color[1], color[0])  # BGR
            pixels = pixel * (self.width * self.height)
        elif self.bits_per_pixel == 16:
            # RGB565 format
            rgb565 = ((color[0] & 0xF8) << 8) | ((color[1] & 0xFC) << 3) | (color[2] >> 3)
            pixel = struct.pack('H', rgb565)
            pixels = pixel * (self.width * self.height)
        else:
            raise ValueError(f"Unsupported format: {self.bits_per_pixel}bpp")

        # Write to framebuffer
        os.pwrite(self.fd, pixels, 0)

    def render_char(
        self,
        char: str,
        x: int,
        y: int,
        fg_color: Tuple[int, int, int] = (255, 255, 255),
        bg_color: Tuple[int, int, int] = (0, 0, 0)
    ) -> None:
        """Render character at position using VGA font."""
        # Get VGA bitmap
        from vga_font_8x16 import VGA_FONT_8X16, vga_row_to_pixels

        if char not in VGA_FONT_8X16:
            return  # Skip unknown characters

        glyph_data = VGA_FONT_8X16[char]
        bitmap = [vga_row_to_pixels(row) for row in glyph_data]

        # Render to framebuffer
        for row_idx, row_pixels in enumerate(bitmap):
            for col_idx, pixel_val in enumerate(row_pixels):
                px_x = x + col_idx
                px_y = y + row_idx

                # Skip if out of bounds
                if px_x >= self.width or px_y >= self.height:
                    continue

                # Choose color
                color = fg_color if pixel_val > 0 else bg_color

                # Write pixel
                self._write_pixel(px_x, px_y, color)

    def render_text(
        self,
        text: str,
        x: int,
        y: int,
        fg_color: Tuple[int, int, int] = (255, 255, 255),
        bg_color: Tuple[int, int, int] = (0, 0, 0)
    ) -> None:
        """Render text at position using VGA fonts."""
        cursor_x = x

        for char in text:
            if char == '\n':
                cursor_x = x
                y += self.char_height
                continue

            self.render_char(char, cursor_x, y, fg_color, bg_color)
            cursor_x += self.char_width

    def render_buffer(
        self,
        buffer: TextBuffer,
        x: int = 0,
        y: int = 0,
        fg_color: Tuple[int, int, int] = (255, 255, 255),
        bg_color: Tuple[int, int, int] = (0, 0, 0)
    ) -> None:
        """Render entire text buffer to screen."""
        line_y = y

        for line_num, line in enumerate(buffer.lines):
            line_x = x

            # Highlight cursor line
            if line_num == buffer.cursor.row:
                cursor_bg = (40, 40, 40)  # Dark gray
            else:
                cursor_bg = bg_color

            # Render line
            for char in line:
                self.render_char(char, line_x, line_y, fg_color, cursor_bg)
                line_x += self.char_width

            line_y += self.char_height

        # Render cursor
        cursor_x = x + buffer.cursor.col * self.char_width
        cursor_y = y + buffer.cursor.row * self.char_height

        # Draw cursor block
        for cy in range(self.char_height):
            for cx in range(self.char_width):
                self._write_pixel(cursor_x + cx, cursor_y + cy, (0, 255, 0))

    def _write_pixel(self, x: int, y: int, color: Tuple[int, int, int]) -> None:
        """Write single pixel to framebuffer."""
        offset = (y * self.width + x) * self.bytes_per_pixel

        if self.bits_per_pixel == 32:
            pixel = struct.pack('BBBB', color[2], color[1], color[0], 255)
        elif self.bits_per_pixel == 24:
            pixel = struct.pack('BBB', color[2], color[1], color[0])
        elif self.bits_per_pixel == 16:
            rgb565 = ((color[0] & 0xF8) << 8) | ((color[1] & 0xFC) << 3) | (color[2] >> 3)
            pixel = struct.pack('H', rgb565)
        else:
            return

        os.pwrite(self.fd, pixel, offset)


# ============================================================================
# TEXT EDITOR
# ============================================================================

class FBTextEditor:
    """Pixel-native framebuffer text editor."""

    def __init__(self, fb_path: str = '/dev/fb0'):
        self.fb_path = fb_path
        self.buffer = TextBuffer()
        self.renderer = FBRenderer(fb_path)
        self.input_device = None

        # State
        self.running = False
        self.save_path = None

    def start(self) -> None:
        """Start the editor main loop."""
        print("Starting FB Text Editor...")

        # Open framebuffer
        if not self.renderer.open():
            return

        # Find and open keyboard
        kb_path = find_keyboard_device()
        if not kb_path:
            print("No keyboard device found")
            self.renderer.close()
            return

        print(f"Using keyboard: {kb_path}")

        self.input_device = InputDevice(kb_path)
        if not self.input_device.open():
            self.renderer.close()
            return

        # Clear screen
        self.renderer.clear()

        # Render initial buffer
        self._render()

        # Main loop
        self.running = True
        print("Editor running (Ctrl+Q to quit, Ctrl+S to save)")

        try:
            while self.running:
                self._process_input()
                time.sleep(0.01)  # 100Hz polling
        except KeyboardInterrupt:
            print("\nInterrupted")
        finally:
            self._cleanup()

    def _process_input(self) -> None:
        """Process keyboard input."""
        key_events, _ = self.input_device.poll_events()

        for event in key_events:
            if not event.pressed:
                continue

            if event.char:
                # Printable character
                self.buffer.insert_char(event.char)
                self._render()
            else:
                # Special keys
                self._handle_special_key(event)

    def _handle_special_key(self, event: KeyEvent) -> None:
        """Handle special keys (arrows, backspace, etc.)."""
        code = event.key_code

        from evdev_input import KEY_BACKSPACE, KEY_ENTER, KEY_UP, KEY_DOWN, KEY_LEFT, KEY_RIGHT

        if code == KEY_BACKSPACE:
            self.buffer.delete_char()
            self._render()

        elif code == KEY_ENTER:
            self.buffer.insert_newline()
            self._render()

        elif code == KEY_LEFT:
            self.buffer.move_cursor(-1, 0)
            self._render()

        elif code == KEY_RIGHT:
            self.buffer.move_cursor(1, 0)
            self._render()

        elif code == KEY_UP:
            self.buffer.move_cursor(0, -1)
            self._render()

        elif code == KEY_DOWN:
            self.buffer.move_cursor(0, 1)
            self._render()

        # Ctrl+Q: Quit
        elif code == 16 and event.modifiers.get('ctrl'):  # KEY_Q = 16
            print("Quitting...")
            self.running = False

        # Ctrl+S: Save
        elif code == 31 and event.modifiers.get('ctrl'):  # KEY_S = 31
            self._save_buffer()

    def _render(self) -> None:
        """Render current buffer to screen."""
        # Clear screen
        self.renderer.clear()

        # Render buffer
        self.renderer.render_buffer(self.buffer, x=10, y=10)

        # Render status line
        status = f"Row {self.buffer.cursor.row + 1}, Col {self.buffer.cursor.col + 1}  |  Ctrl+Q: Quit  Ctrl+S: Save"
        if self.save_path:
            status = f"{status}  |  File: {self.save_path}"

        self.renderer.render_text(status, x=10, y=self.renderer.height - 20)

    def _save_buffer(self) -> None:
        """Save buffer to file."""
        if not self.save_path:
            self.save_path = '/tmp/fb_editor.txt'

        with open(self.save_path, 'w') as f:
            f.write(self.buffer.get_text())

        print(f"Saved to {self.save_path}")
        self._render()  # Update status line

    def _cleanup(self) -> None:
        """Clean up resources."""
        if self.input_device:
            self.input_device.close()
        if self.renderer:
            self.renderer.clear()
            self.renderer.close()
        print("Editor closed")


def main():
    import argparse

    parser = argparse.ArgumentParser(description='Pixel-native framebuffer text editor')
    parser.add_argument('--fb', default='/dev/fb0', help='Framebuffer device (default: /dev/fb0)')
    parser.add_argument('--file', help='Load file on start')

    args = parser.parse_args()

    editor = FBTextEditor(args.fb)

    # Load file if specified
    if args.file:
        try:
            with open(args.file, 'r') as f:
                editor.buffer.set_text(f.read())
            editor.save_path = args.file
            print(f"Loaded {args.file}")
        except FileNotFoundError:
            print(f"File not found: {args.file}")

    # Start editor
    editor.start()


if __name__ == '__main__':
    main()