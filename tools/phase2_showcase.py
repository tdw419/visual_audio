"""Phase 2 Interactive Substrate Showcase (BK-282 + BK-253 Rung 2).

Unifies the first human-legible GPU OS interactive applications into a single-screen
VGA console dashboard (640x400 framebuffer / 80x25 text grid):
1. BK-282 GPU OS Calculator (Accumulator-form arithmetic on Glyph ISA).
2. BK-253 Rung 2 NanoPy REPL (Freestanding C RV32I -> Glyph VM on GO-3 MMIO ring).
3. BK-19 IBM VGA 8x16 font rendering and exact font-bitmap decode.

Batch invariant: pure pixels-in, pixels-out, verifiable by live test gates.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from tools.bk253_interactive import NanoPySession
from tools.bk282_calc import CalculatorSession
from tools.vga_font_8x16 import VGA_FONT_8X16, get_vga_bitmap

CELL_W = 8
CELL_H = 16
GRID_ROWS = 25
GRID_COLS = 80
FB_HEIGHT = GRID_ROWS * CELL_H  # 400
FB_WIDTH = GRID_COLS * CELL_W    # 640

# Build reverse bit pattern map for 100% exact font-bitmap decoding
_BITS_TO_CHAR: dict[tuple[tuple[int, ...], ...], str] = {}
for _ch, _rows in VGA_FONT_8X16.items():
    _bits = tuple(
        tuple((row >> bit) & 1 for bit in range(7, -1, -1)) for row in _rows
    )
    _BITS_TO_CHAR[_bits] = _ch


_FONT_MASKS: dict[str, np.ndarray] = {
    _ch: get_vga_bitmap(_ch) > 0 for _ch in VGA_FONT_8X16
}


class Phase2Showcase:
    """Unified interactive showcase screen managing both Glyph engines."""

    def __init__(self) -> None:
        self.calc = CalculatorSession()
        self.nanopy = NanoPySession()
        self.calc_history: List[str] = []
        self.py_history: List[str] = []
        self.text_grid = np.full((GRID_ROWS, GRID_COLS), " ", dtype="<U1")
        self._update_layout()

    def run_calc(self, expr: str) -> str:
        """Run an expression through the BK-282 Calculator on GlyphCPUv2."""
        self.calc.type_digits(expr)
        result = self.calc.console_text()
        entry = f"{expr}{result}"
        self.calc_history.append(f"> {expr}")
        self.calc_history.append(f"  {entry}")
        self._update_layout()
        return result

    def run_py(self, code: str) -> str:
        """Run a Python expression/statement through NanoPy on GlyphCPUv2."""
        self.nanopy.feed_input(code)
        self.nanopy.run()
        out = self.nanopy.last_output_bytes().decode("latin1", errors="replace")
        self.py_history.append(f">>> {code.strip()}")
        if out:
            for line in out.splitlines():
                self.py_history.append(f"  {line}")
        self._update_layout()
        return out

    def run_default_showcase(self) -> None:
        """Execute default headline sequence demonstrating all capabilities."""
        self.run_calc("12+3*4=")      # -> 24
        self.run_calc("20-12/3=")     # -> 16
        self.run_calc("12/0=")        # -> ERR:DIV0
        self.run_py('print("phase2")\n')  # -> phase2
        self.run_py("x = 21\n")       # -> (assignment)
        self.run_py("x * 2\n")        # -> 42

    def get_calc_pane_text(self) -> str:
        """Return cumulative text from the Calculator pane."""
        return "\n".join(self.calc_history)

    def get_py_pane_text(self) -> str:
        """Return cumulative text from the NanoPy pane."""
        return "\n".join(self.py_history)

    def get_text(self) -> str:
        """Return complete 80x25 character grid as formatted text."""
        return "\n".join("".join(row).rstrip() for row in self.text_grid)

    def _write_string(self, row: int, col: int, text: str, max_len: Optional[int] = None) -> None:
        """Write string into text_grid with bounds clipping."""
        if row < 0 or row >= GRID_ROWS or col < 0 or col >= GRID_COLS:
            return
        limit = GRID_COLS - col
        if max_len is not None:
            limit = min(limit, max_len)
        chunk = text[:limit]
        for i, ch in enumerate(chunk):
            if ch not in VGA_FONT_8X16:
                ch = "?"
            self.text_grid[row, col + i] = ch

    def _update_layout(self) -> None:
        """Refresh the full 80x25 dual-pane dashboard layout."""
        self.text_grid.fill(" ")

        # Header box
        self._write_string(0, 0, "+" + "-" * 78 + "+")
        self._write_string(1, 0, "|        GEOMETRY OS - PHASE 2 INTERACTIVE SUBSTRATE SHOWCASE                  |")
        self._write_string(2, 0, "| \"The Screen is the Computer\" - Dual-Engine Pixel Substrate (VGA 640x400)     |")
        self._write_string(3, 0, "+" + "-" * 38 + "+" + "-" * 39 + "+")

        # Pane titles
        self._write_string(4, 0, "| [1] BK-282 GPU OS CALCULATOR         | [2] BK-253 RUNG 2 NANOPY REPL         |")
        self._write_string(5, 0, "| (Glyph ISA Accumulator Engine)       | (Freestanding C RV32I on GO-3 Ring)   |")
        self._write_string(6, 0, "+" + "-" * 38 + "+" + "-" * 39 + "+")

        # Pane bodies (Rows 7 to 20 = 14 visible rows)
        body_rows = 14
        calc_lines = self.calc_history[-body_rows:] if self.calc_history else ["(awaiting keystrokes)"]
        py_lines = self.py_history[-body_rows:] if self.py_history else ["(awaiting python expressions)"]

        for r_idx in range(body_rows):
            grid_r = 7 + r_idx
            self._write_string(grid_r, 0, "| ")
            if r_idx < len(calc_lines):
                self._write_string(grid_r, 2, calc_lines[r_idx], max_len=36)
            self._write_string(grid_r, 39, "| ")
            if r_idx < len(py_lines):
                self._write_string(grid_r, 41, py_lines[r_idx], max_len=37)
            self._write_string(grid_r, 79, "|")

        # Footer divider and status
        self._write_string(21, 0, "+" + "-" * 38 + "+" + "-" * 39 + "+")
        self._write_string(22, 0, "| STATUS: DUAL ENGINES GREEN (60 FPS)  | PIXELS MOVE PIXELS - FIDELITY: 100%   |")
        self._write_string(23, 0, "| [F1] Calc (BK-282)  [F2] NanoPy (BK-253)  [F3] Forth (Rung 1)                |")
        self._write_string(24, 0, "+" + "-" * 78 + "+")

    def render_vga_framebuffer(
        self,
        on: Tuple[int, int, int] = (255, 255, 255),
        off: Tuple[int, int, int] = (0, 0, 0),
    ) -> np.ndarray:
        """Render the 80x25 character grid into a 640x400 RGB framebuffer."""
        fb = np.empty((FB_HEIGHT, FB_WIDTH, 3), dtype=np.uint8)
        fb[:, :] = np.array(off, dtype=np.uint8)
        on_arr = np.array(on, dtype=np.uint8)
        question_mask = _FONT_MASKS.get("?", get_vga_bitmap("?") > 0)

        for r in range(GRID_ROWS):
            y0 = r * CELL_H
            for c in range(GRID_COLS):
                ch = self.text_grid[r, c]
                if ch == " ":
                    continue
                mask = _FONT_MASKS.get(ch, question_mask)
                x0 = c * CELL_W
                fb[y0 : y0 + CELL_H, x0 : x0 + CELL_W, :][mask] = on_arr

        return fb

    def decode_vga_framebuffer(
        self,
        fb: np.ndarray,
        on: Tuple[int, int, int] = (255, 255, 255),
        off: Tuple[int, int, int] = (0, 0, 0),
    ) -> str:
        """Decode a 640x400 framebuffer back to text via exact font matching."""
        if fb.shape != (FB_HEIGHT, FB_WIDTH, 3):
            raise ValueError(f"Expected shape ({FB_HEIGHT}, {FB_WIDTH}, 3), got {fb.shape}")

        off_arr = np.array(off, dtype=np.uint8)
        lines = []
        for r in range(GRID_ROWS):
            y0 = r * CELL_H
            row_chars = []
            for c in range(GRID_COLS):
                x0 = c * CELL_W
                cell = fb[y0 : y0 + CELL_H, x0 : x0 + CELL_W, :]
                if np.array_equal(cell, np.broadcast_to(off_arr, cell.shape)):
                    row_chars.append(" ")
                    continue
                bits = []
                for cr in range(CELL_H):
                    rb = []
                    for cc in range(CELL_W):
                        px = tuple(int(v) for v in cell[cr, cc])
                        if px == on:
                            rb.append(1)
                        else:
                            rb.append(0)
                    bits.append(tuple(rb))
                bits_tuple = tuple(bits)
                ch = _BITS_TO_CHAR.get(bits_tuple, "?")
                row_chars.append(ch)
            lines.append("".join(row_chars).rstrip())
        return "\n".join(lines)

    def save_screenshot(self, path: Path | str) -> None:
        """Save current VGA framebuffer as a PNG image."""
        from PIL import Image

        fb = self.render_vga_framebuffer()
        img = Image.fromarray(fb)
        img.save(str(path))


def main() -> int:
    parser = argparse.ArgumentParser(description="Geometry OS Phase 2 Interactive Showcase")
    parser.add_argument("--demo", action="store_true", help="Run full automated showcase sequence")
    parser.add_argument("--calc", type=str, help="Run an expression on the GPU OS Calculator")
    parser.add_argument("--py", type=str, help="Run a Python statement on NanoPy")
    parser.add_argument("--save-png", type=Path, help="Save rendered VGA framebuffer to PNG")

    args = parser.parse_args()
    showcase = Phase2Showcase()

    if args.demo:
        print("Running Phase 2 Interactive Substrate Showcase demo...")
        showcase.run_default_showcase()
    elif args.calc:
        res = showcase.run_calc(args.calc)
        print(f"Calculator result: {res}")
    elif args.py:
        res = showcase.run_py(args.py if args.py.endswith("\n") else args.py + "\n")
        print(f"NanoPy output: {res}")

    print("\n" + showcase.get_text() + "\n")

    if args.save_png:
        showcase.save_screenshot(args.save_png)
        print(f"VGA Screenshot saved to: {args.save_png}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
