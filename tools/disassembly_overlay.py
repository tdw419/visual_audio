#!/usr/bin/env python3
"""
Disassembly overlay for hello.img boot trace.

Extracts kernel memory from QMP dump, disassembles RISC-V instructions,
and composites annotated overlays onto a Hilbert-mapped pixel grid.

Outputs:
1. Full 1024×1024 grid with micro-scale code annotations (as before)
2. Magnified inset panel of just the code region (8×-16× zoom)
"""

import sys
import struct
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))

from dense_encoder_video import decode_mkv


# ============================================================================
# RISC-V Disassembly (Capstone)
# ============================================================================

try:
    from capstone import Cs, CS_ARCH_RISCV, CS_MODE_RISCV64
    CS_AVAILABLE = True
except ImportError:
    CS_AVAILABLE = False


def disassemble_riscv(code_bytes: bytes, base_addr: int = 0x80200000):
    """Disassemble RISC-V bytes using Capstone."""
    if not CS_AVAILABLE:
        print("Capstone not available, skipping disassembly")
        return []

    md = Cs(CS_ARCH_RISCV, CS_MODE_RISCV64)
    md.detail = True

    instructions = []
    for insn in md.disasm(code_bytes, base_addr):
        instructions.append({
            'address': insn.address,
            'size': insn.size,
            'mnemonic': insn.mnemonic,
            'op_str': insn.op_str,
            'bytes': insn.bytes,
        })

    return instructions


# ============================================================================
# Hilbert Curve Mapping (same as qemu_to_mkv.py)
# ============================================================================

def hilbert_d2xy(n: int, d: int):
    """Convert distance d along Hilbert curve to (x, y) coordinates."""
    x, y = 0, 0
    s = 1
    rx = ry = 0

    while s < n:
        rx = (d >> 1) & 1
        ry = (d >> 0) & 1

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


def map_ram_to_pixels(ram_data: bytes, width: int = 1024, height: int = 1024):
    """Map linear RAM data to 2D pixel grid using Hilbert curve."""
    total_pixels = width * height
    required_bytes = total_pixels * 3

    if len(ram_data) < required_bytes:
        ram_data = ram_data + b'\x00' * (required_bytes - len(ram_data))
    else:
        ram_data = ram_data[:required_bytes]

    # Precompute Hilbert coordinates
    y_coords = np.zeros(total_pixels, dtype=np.int32)
    x_coords = np.zeros(total_pixels, dtype=np.int32)
    for pixel_idx in range(total_pixels):
        x, y = hilbert_d2xy(max(width, height), pixel_idx)
        x_coords[pixel_idx] = x
        y_coords[pixel_idx] = y
    valid = (x_coords < width) & (y_coords < height)

    pixels = np.zeros((height, width, 3), dtype=np.uint8)
    ram_pixels = np.frombuffer(ram_data, dtype=np.uint8).reshape(total_pixels, 3)
    pixels[y_coords[valid], x_coords[valid]] = ram_pixels[valid]

    return pixels


# ============================================================================
# Elf Parsing
# ============================================================================

def parse_elf_sections(mem_dump: bytes, kernel_base: int = 0x80200000):
    """
    Parse ELF section headers from memory dump.

    Returns dict: {section_name: (offset, size, type)}
    """
    if mem_dump[:4] != b'\x7fELF':
        print("  ⚠ Not an ELF file")
        return {}

    # ELF header for 64-bit
    if len(mem_dump) < 64:
        print("  ⚠ ELF header too short")
        return {}

    ei_class = mem_dump[4]
    if ei_class != 2:  # 2 = ELF64
        print(f"  ⚠ Not ELF64 (ei_class={ei_class})")
        return {}

    # Parse section header table
    e_shoff = struct.unpack('<Q', mem_dump[40:48])[0]
    e_shentsize = struct.unpack('<H', mem_dump[58:60])[0]
    e_shnum = struct.unpack('<H', mem_dump[60:62])[0]
    e_shstrndx = struct.unpack('<H', mem_dump[62:64])[0]

    print(f"  Section headers: offset=0x{e_shoff:x}, num={e_shnum}, entsize={e_shentsize}")

    # Check if we have enough data
    if e_shoff + e_shnum * e_shentsize > len(mem_dump):
        print(f"  ⚠ Section header table beyond available data ({len(mem_dump)} bytes)")
        return {}

    sections = {}

    # Get string table
    sh_offset = e_shoff + e_shstrndx * e_shentsize
    if sh_offset + 40 > len(mem_dump):
        print(f"  ⚠ String table header out of bounds")
        return {}

    sh_type = struct.unpack('<I', mem_dump[sh_offset + 4:sh_offset + 8])[0]
    sh_offset_val = struct.unpack('<Q', mem_dump[sh_offset + 24:sh_offset + 32])[0]
    sh_size = struct.unpack('<Q', mem_dump[sh_offset + 32:sh_offset + 40])[0]

    print(f"  String table: offset=0x{sh_offset_val:x}, size={sh_size}")

    if sh_offset_val + sh_size > len(mem_dump):
        print(f"  ⚠ String table data beyond available data")
        return {}

    string_table = mem_dump[sh_offset_val:sh_offset_val + sh_size]

    # Parse all sections
    for i in range(e_shnum):
        sh_offset = e_shoff + i * e_shentsize
        if sh_offset + 40 > len(mem_dump):
            break

        sh_name = struct.unpack('<I', mem_dump[sh_offset:sh_offset + 4])[0]

        # Extract section name
        if sh_name >= len(string_table):
            continue
        name_end = string_table.find(b'\x00', sh_name)
        if name_end == -1:
            continue
        section_name = string_table[sh_name:name_end].decode('ascii', errors='ignore')

        sh_type = struct.unpack('<I', mem_dump[sh_offset + 4:sh_offset + 8])[0]
        sh_flags = struct.unpack('<Q', mem_dump[sh_offset + 8:sh_offset + 16])[0]
        sh_addr = struct.unpack('<Q', mem_dump[sh_offset + 16:sh_offset + 24])[0]
        sh_offset_val = struct.unpack('<Q', mem_dump[sh_offset + 24:sh_offset + 32])[0]
        sh_size = struct.unpack('<Q', mem_dump[sh_offset + 32:sh_offset + 40])[0]

        if sh_size > 0:
            sections[section_name] = {
                'offset': sh_offset_val,
                'size': sh_size,
                'type': sh_type,
                'addr': sh_addr,
                'flags': sh_flags
            }

    return sections


# ============================================================================
# Main Overlay Pipeline
# ============================================================================

def add_overlay(image: Image.Image, sections: dict, instructions: list):
    """Add color-coded overlay to Hilbert image."""
    draw = ImageDraw.Draw(image)

    # Color palette
    colors = {
        '.text': (0, 255, 0),      # Green
        '.rodata': (128, 0, 255),  # Purple
        '.data': (0, 100, 255),    # Blue
        '.bss': (255, 255, 0),     # Yellow
        'stack': (255, 50, 50),    # Red
    }

    # Get bounding boxes of sections
    width, height = image.size
    region_boxes = []

    for name, section in sections.items():
        if section['size'] == 0:
            continue

        # Calculate Hilbert coordinates for this memory region
        # For simplicity, just map center point
        addr = section['addr']
        rel_offset = addr - 0x80200000  # kernel base

        # Approximate pixel position (not exact for large regions)
        # This is a simplified mapping for visualization
        total_pixels = width * height
        pixel_idx = (rel_offset // 3) % total_pixels
        x, y = hilbert_d2xy(max(width, height), pixel_idx)

        color = colors.get(name, (200, 200, 200))
        box_size = max(2, int(np.log2(section['size'] + 1)))
        draw.rectangle([x, y, x + box_size, y + box_size], outline=color, width=2)

        # Store for inset panel
        region_boxes.append((name, x, y, box_size, color))

    # Draw instruction markers
    if instructions:
        for insn in instructions[:20]:  # First 20 instructions only
            addr = insn['address']
            rel_offset = addr - 0x80200000
            total_pixels = width * height
            pixel_idx = (rel_offset // 3) % total_pixels
            x, y = hilbert_d2xy(max(width, height), pixel_idx)

            # Mark with a small dot
            draw.ellipse([x - 1, y - 1, x + 1, y + 1], fill=(255, 0, 0))

    return image, region_boxes


def create_code_inset(mem_dump: bytes, kernel_base: int = 0x80200000,
                     code_size: int = 2048, zoom: int = 16):
    """
    Create a magnified inset panel showing just the code region.

    Renders:
    - RISC-V instructions as text
    - Color-coded by section
    - Address annotations
    """
    if not CS_AVAILABLE:
        # Fallback: raw bytes
        code_bytes = mem_dump[:code_size]
        # Create simple visualization
        img_width = 256
        img_height = 256
        inset = Image.new('RGB', (img_width, img_height), (20, 20, 30))
        draw = ImageDraw.Draw(inset)

        for i, byte in enumerate(code_bytes[:64]):
            x = (i % 8) * 32
            y = (i // 8) * 32
            color = byte, byte, byte
            draw.rectangle([x + 1, y + 1, x + 30, y + 30], fill=color)

        draw.text((5, 5), f"Raw bytes (no Capstone)", fill=(255, 255, 255))
        return inset

    # Disassemble code region
    code_offset = kernel_base - 0x80200000  # Should be 0 for hello.img
    if code_offset < 0:
        code_offset = 0
        code_bytes = mem_dump[:code_size]
    else:
        code_bytes = mem_dump[code_offset:code_offset + code_size]

    instructions = disassemble_riscv(code_bytes, kernel_base)

    # Calculate dimensions
    line_height = 14 * zoom
    padding = 5 * zoom
    font_size = 10 * zoom

    # Try to load a monospace font
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", font_size)
    except:
        font = ImageFont.load_default()

    # Count instructions that fit
    max_lines = 30
    display_instructions = instructions[:max_lines]

    # Create inset image
    img_width = 70 * zoom
    img_height = padding * 2 + len(display_instructions) * line_height

    inset = Image.new('RGB', (img_width, img_height), (15, 15, 25))
    draw = ImageDraw.Draw(inset)

    # Header
    draw.text((padding, padding), f"Code Region @ 0x{kernel_base:x}", fill=(200, 200, 255), font=font)

    # Instructions
    y = padding + line_height * 1.5
    for i, insn in enumerate(display_instructions):
        # Color code by instruction type
        if insn.mnemonic in ('add', 'sub', 'mul', 'div', 'rem'):
            color = (0, 255, 128)  # Math: green
        elif insn.mnemonic in ('ld', 'sd', 'lw', 'sw'):
            color = (100, 150, 255)  # Memory: blue
        elif insn.mnemonic in ('beq', 'bne', 'blt', 'bge', 'jal', 'jalr'):
            color = (255, 100, 100)  # Branch: red
        else:
            color = (255, 255, 255)  # Other: white

        line = f"0x{insn.address:08x}:  {insn.mnemonic:<6} {insn.op_str}"
        draw.text((padding, y), line, fill=color, font=font)
        y += line_height

    # Section boundaries
    draw.line([padding, padding + line_height * 1.2, img_width - padding, padding + line_height * 1.2],
              fill=(100, 100, 100), width=2)

    return inset


def main():
    import argparse

    parser = argparse.ArgumentParser(description='Disassembly overlay for boot trace')
    parser.add_argument('mkv_path', help='Path to MKV file')
    parser.add_argument('--output', '-o', default='/tmp/disassembly_overlay.png',
                       help='Output PNG path')
    parser.add_argument('--frame', '-f', type=int, default=0,
                       help='Frame number to extract')
    parser.add_argument('--zoom', '-z', type=int, default=12,
                       help='Zoom factor for inset panel')
    args = parser.parse_args()

    print("=" * 70)
    print("Disassembly Overlay for Boot Trace")
    print("=" * 70)

    # Decode MKV
    print(f"\n[1] Decoding {args.mkv_path}...")
    payload, manifest = decode_mkv(args.mkv_path)

    # Get metadata
    meta = manifest.get('metadata', {})
    grid_width = meta.get('grid_width', 1024)
    grid_height = meta.get('grid_height', 1024)
    tiles_per_capture = meta.get('tiles_per_capture', 1)
    total_captures = meta.get('total_captures', 1)

    print(f"  Grid: {grid_width}×{grid_height}")
    print(f"  Tiles per capture: {tiles_per_capture}")
    print(f"  Total captures: {total_captures}")
    print(f"  Total payload: {len(payload)} bytes")

    # Extract specific logical capture
    # Each capture spans `tiles_per_capture` * frame_size bytes
    frame_size = grid_width * grid_height * 3
    capture_size = tiles_per_capture * frame_size

    if args.frame >= total_captures:
        print(f"✗ Capture {args.frame} out of range (total: {total_captures})")
        return 1

    capture_offset = args.frame * capture_size
    if capture_offset + capture_size > len(payload):
        print(f"✗ Capture {args.frame} data incomplete")
        return 1

    capture_data = payload[capture_offset:capture_offset + capture_size]
    print(f"  ✓ Capture {args.frame} extracted ({len(capture_data)} bytes = {capture_size/frame_size} tiles)")

    # Use the first tile of the capture for visualization
    frame_data = capture_data[:frame_size]  # Hilbert-mapped pixels

    # Find which tile contains the kernel
    kernel_vaddr = 0x80200000

    # Extract raw RAM bytes (reverse Hilbert mapping)
    # The MKV stores Hilbert-mapped RGB24 pixels; we need to reverse this
    # to get back to linear RAM bytes

    print(f"\n[2] Extracting raw RAM from Hilbert frame...")

    # Reverse Hilbert mapping
    def reverse_hilbert_mapping(pixels, width, height):
        """Convert Hilbert-mapped pixels back to linear RAM bytes."""
        total_pixels = width * height
        ram_bytes = bytearray(total_pixels * 3)

        # Precompute Hilbert coordinates
        y_coords = np.zeros(total_pixels, dtype=np.int32)
        x_coords = np.zeros(total_pixels, dtype=np.int32)
        for pixel_idx in range(total_pixels):
            x, y = hilbert_d2xy(max(width, height), pixel_idx)
            x_coords[pixel_idx] = x
            y_coords[pixel_idx] = y

        # Valid pixels are those within the grid
        valid = (x_coords < width) & (y_coords < height)

        # Extract RGB values from valid pixel positions
        pixel_array = np.array(pixels)
        ram_pixels = pixel_array[y_coords[valid], x_coords[valid]]

        # Convert back to bytes (flatten RGB)
        ram_bytes[:] = ram_pixels.flatten().tobytes()

        return ram_bytes

    # Convert frame_data (bytes) to numpy array first
    pixel_array = np.frombuffer(frame_data, dtype=np.uint8).reshape(height, width, 3)
    ram_bytes = reverse_hilbert_mapping(pixel_array, grid_width, grid_height)
    print(f"  ✓ Reversed Hilbert mapping: {len(ram_bytes)} bytes of linear RAM")

    # Now find kernel in raw RAM
    # hello.img is at physical 0 for bare-metal kernels
    # The entry point 0x80200000 is virtual; physical offset is 0
    kernel_offset = 0

    print(f"\n[3] Analyzing kernel code region @ physical 0x{kernel_offset:x}...")

    # Parse ELF64 entry point from header in raw RAM
    if len(ram_bytes) >= 32:
        e_entry = struct.unpack('<Q', ram_bytes[24:32])[0]
        print(f"  ELF entry point (virtual): 0x{e_entry:x}")

        # For bare-metal kernels loaded directly, the code starts at file offset 0
        # The entry point is a virtual address; physical code starts at 0
        entry_offset = 0
    else:
        entry_offset = 0
        print(f"  Using default entry offset: 0x{entry_offset:x}")

    # Disassemble from entry offset
    code_size = min(2048, len(ram_bytes) - entry_offset)
    code_data = ram_bytes[entry_offset:entry_offset + code_size]

    if CS_AVAILABLE and code_data:
        print(f"  Disassembling {code_size} bytes @ 0x{entry_offset:x}...")
        instructions = disassemble_riscv(code_data, entry_offset)
        print(f"  ✓ Disassembled {len(instructions)} instructions")
        for insn in instructions[:8]:  # Show first 8
            print(f"    0x{insn.address:08x}:  {insn.mnemonic:<6} {insn.op_str}")

        # Create simple section boundaries based on analysis
        if instructions:
            sections = {
                '.text': {'offset': entry_offset, 'size': code_size, 'type': 1, 'addr': entry_offset, 'flags': 6},
            }
            print(f"  ✓ Created {len(sections)} synthetic sections")
        else:
            sections = {}
            print(f"  ⚠ No instructions disassembled")
    else:
        print(f"  ⚠ {'Capstone not available' if not CS_AVAILABLE else 'No code data found'}")
        instructions = []
        sections = {}

    # Map RAM to Hilbert pixels
    print(f"\n[4] Mapping RAM to Hilbert curve (1024x1024)...")
    pixels = map_ram_to_pixels(frame_data)
    print(f"  ✓ Hilbert mapping complete")

    # Create PIL image
    print(f"\n[5] Creating overlay image...")
    image = Image.fromarray(pixels)
    image, region_boxes = add_overlay(image, sections, instructions)
    print(f"  ✓ Overlay added ({len(region_boxes)} region markers)")

    # Create code inset
    print(f"\n[6] Creating magnified code inset (zoom={args.zoom}x)...")
    inset = create_code_inset(kernel_data, kernel_offset, zoom=args.zoom)
    print(f"  ✓ Inset created ({inset.width}×{inset.height})")

    # Composite full grid + inset
    panel_width = image.width + inset.width + 20
    panel_height = max(image.height, inset.height)

    panel = Image.new('RGB', (panel_width, panel_height), (10, 10, 15))

    # Paste full grid
    panel.paste(image, (0, 0))

    # Paste inset
    panel.paste(inset, (image.width + 20, 0))

    # Add legend
    draw = ImageDraw.Draw(panel)
    legend_y = 20
    legend_x = image.width + 20

    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", 12)
    except:
        font = ImageFont.load_default()

    draw.text((legend_x, inset.height + 10), "Legend:", fill=(255, 255, 255), font=font)

    legend_items = [
        (".text (Green)", (0, 255, 0)),
        (".rodata (Purple)", (128, 0, 255)),
        (".data (Blue)", (0, 100, 255)),
        (".bss (Yellow)", (255, 255, 0)),
    ]

    for i, (label, color) in enumerate(legend_items):
        y = legend_y + 30 + i * 20
        draw.rectangle([legend_x, y, legend_x + 15, y + 15], outline=color, width=3)
        draw.text((legend_x + 25, y - 2), label, fill=(200, 200, 200), font=font)

    # Add title
    title = f"Boot Trace Frame {args.frame}: Disassembly Overlay"
    draw.text((10, 10), title, fill=(255, 255, 255), font=font)

    # Save output
    print(f"\n[7] Saving to {args.output}...")
    panel.save(args.output)
    print(f"  ✓ Saved ({panel.width}×{panel.height})")

    print(f"\n{'=' * 70}")
    print(f"Overlay complete: {args.output}")
    print(f"{'=' * 70}\n")

    return 0


if __name__ == '__main__':
    sys.exit(main())