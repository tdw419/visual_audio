#!/usr/bin/env python3
"""
Visualize Game of Life grid from Pixel Interpreter memory.
Reads the state from a saved PNG and renders the cell grid.
"""

from pathlib import Path
import argparse
import numpy as np
from PIL import Image, ImageDraw

def extract_grid(img_path: Path, grid_start_y: int, grid_size: int = 16):
    """Extract the live/dead grid from memory image."""
    img = Image.open(img_path).convert("RGBA")
    mem = np.asarray(img, dtype=np.uint8)
    
    grid = []
    for y in range(grid_size):
        row = []
        for x in range(grid_size):
            # Cell value is in R channel at (x, grid_start_y + y)
            cell = mem[grid_start_y + y, x, 0]
            is_alive = cell > 128  # 255 = alive, 0 = dead
            row.append(is_alive)
        grid.append(row)
    
    return grid

def render_grid(grid: list[list[bool]], cell_size: int = 20) -> Image.Image:
    """Render the grid as an image."""
    height = len(grid)
    width = len(grid[0]) if height > 0 else 0
    
    img = Image.new("RGB", (width * cell_size, height * cell_size), "white")
    draw = ImageDraw.Draw(img)
    
    for y, row in enumerate(grid):
        for x, alive in enumerate(row):
            if alive:
                x0 = x * cell_size
                y0 = y * cell_size
                x1 = x0 + cell_size
                y1 = y0 + cell_size
                draw.rectangle([x0, y0, x1, y1], fill="black")
            else:
                # Draw light grid lines
                x0 = x * cell_size
                y0 = y * cell_size
                x1 = x0 + cell_size
                y1 = y0 + cell_size
                draw.rectangle([x0, y0, x1, y1], outline="#e0e0e0")
    
    return img

def main():
    parser = argparse.ArgumentParser(description="Visualize Game of Life grid from memory")
    parser.add_argument("image", type=Path, help="Memory state PNG file")
    parser.add_argument("--grid-y", type=int, default=81, help="Y offset of grid in memory")
    parser.add_argument("--grid-size", type=int, default=16, help="Grid size (NxN)")
    parser.add_argument("--cell-size", type=int, default=20, help="Pixel size per cell")
    parser.add_argument("-o", "--output", type=Path, help="Output image path")
    
    args = parser.parse_args()
    
    if not args.image.exists():
        print(f"Error: {args.image} not found")
        return
    
    grid = extract_grid(args.image, args.grid_y, args.grid_size)
    img = render_grid(grid, args.cell_size)
    
    # Count live cells
    live_count = sum(sum(row) for row in grid)
    print(f"Grid {args.grid_size}x{args.grid_size} at y={args.grid_y}")
    print(f"Live cells: {live_count}")
    
    # Print ASCII representation
    print("\nGrid:")
    for row in grid:
        print("".join("█" if cell else "░" for cell in row))
    
    out_path = args.output or args.image.with_stem(f"{args.image.stem}_grid").with_suffix(".png")
    img.save(out_path)
    print(f"\nSaved visualization to {out_path}")

if __name__ == "__main__":
    main()