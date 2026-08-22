# `geos_pixel` — Geometry OS Spatial Foundation

## Overview
`geos_pixel` is the core Rust library for spatial mapping and pixel-programming within Geometry OS. It bridges the gap between linear bytes (symbolic computation) and 2D visual structures (spatial computation).

The library is specifically designed to support the **Visual Audio Container (VAC1)** ecosystem and the generation of `.rts.png` (PixelRTS v2) spatial payloads.

## Core Modules

### 1. The True Hilbert Curve (`geos_pixel::hilbert`)
The fundamental mapping algorithm that translates a linear 1D byte offset into a 2D `(x, y)` coordinate, preserving strict spatial locality (Manhattan distance = 1).

**CRITICAL ARCHITECTURAL NOTE (The Z-Order Divergence):**
During the development of Geometry OS, several legacy Python tools (`qemu_capture_simple.py`, `qemu_to_mkv.py`, `vac3_demo.py`) accidentally implemented a Z-order curve (Morton code) while naming it `hilbert_d2xy`. 

`geos_pixel` implements the **True Hacker's Delight Hilbert Curve**. It is mathematically identical to the mapping used in the VCC (Visual Consistency Contract) Engine and `spadsl`. 

```rust
use geos_pixel::HilbertCurve;

let grid_size = 4096;
let distance = 500;

// Map linear offset to 2D coordinate
let (x, y) = HilbertCurve::d2xy(grid_size, distance);

// Map 2D coordinate back to linear offset
let d = HilbertCurve::xy2d(grid_size, x, y);
```

### 2. The Pixel Canvas (`geos_pixel::canvas`)
The spatial abstraction that handles packing linear bytes directly into the RGBA channels of a 2D grid, routing them along the Hilbert curve. 

It enforces power-of-two constraints required by the math and outputs bootable `image::RgbaImage` PNGs.

```rust
use geos_pixel::PixelCanvas;

// 1. Initialize a 4096x4096 spatial tensor
let mut canvas = PixelCanvas::new(4096);

// 2. Pack linear bytes (e.g. from a binary or .glyph assembly) 
// into RGB pixels (Alpha is auto-set to 255)
let payload = vec![0xDE, 0xAD, 0xBE, 0xEF, 0x00];
canvas.write_bytes(0, &payload);

// 3. Export as a bootable PixelRTS v2 visual container
canvas.save_png("output_container.rts.png").expect("Failed to save container");
```

## Integration with VAC1
This crate serves as the performance foundation for:
1. **Container Builders**: Generating massive (15GB+) `.rts.png` frames in Rust without the OOM overhead of Python.
2. **Spatial Assemblers**: Translating `.glyph` spatial opcodes (e.g., `LDI r0, 10`) into their correct 2D Hilbert offsets.
3. **VCC Validation**: Fast, host-side validation of Phase Alignment Stability (PAS) by recalculating expected pixel hashes in Rust.
