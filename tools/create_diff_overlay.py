#!/usr/bin/env python3
"""
create_diff_overlay.py — Create Frame 3: Active Chunk Cache (Diff Overlay).

Diff overlay stores sparse coordinate→change records.
Format: 10-byte records concatenated:
  - Bytes 0-3: X coordinate (32-bit, little-endian)
  - Bytes 4-7: Y coordinate (32-bit, little-endian)
  - Byte 8: Operation (0=set, 1=clear, 2=toggle)
  - Byte 9: Value (0-255)

These bytes are packed into the frame using dense_encoder format (3 bytes/pixel).
"""

import numpy as np
from PIL import Image
import struct
import sys

FRAME_SIZE = 450

def pack_diff_records(records: list) -> bytes:
    """Pack diff records into bytes."""
    data = b""
    for x, y, operation, value in records:
        # Pack: X(4) + Y(4) + operation(1) + value(1) = 10 bytes
        data += struct.pack("<iiBB", x, y, operation, value)
    return data

def create_diff_frame(records: list) -> np.ndarray:
    """Create a diff overlay frame from records."""
    data = pack_diff_records(records)
    
    # Import dense_encoder for packing
    sys.path.insert(0, "tools")
    from dense_encoder import frame, MAGIC
    
    # Wrap data in dense_encoder frame format
    framed = frame(data)
    
    # Pad to full frame
    FRAME_BYTES = FRAME_SIZE * FRAME_SIZE * 3
    padded = framed + b"\x00" * (FRAME_BYTES - len(framed))
    
    # Convert to numpy array
    frame_array = np.frombuffer(padded, dtype=np.uint8).reshape(FRAME_SIZE, FRAME_SIZE, 3)
    return frame_array

def main():
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <record_file.json>")
        print("  Record file format: [[x, y, operation, value], ...]")
        print("  operation: 0=set, 1=clear, 2=toggle")
        sys.exit(1)
    
    # Load records from JSON
    import json
    with open(sys.argv[1]) as f:
        records = json.load(f)
    
    print(f"Creating diff overlay with {len(records)} records")
    
    frame = create_diff_frame(records)
    
    # Save as PNG
    img = Image.fromarray(frame, mode='RGB')
    output_path = "diff_overlay_frame.png"
    img.save(output_path)
    
    print(f"Wrote {FRAME_SIZE}x{FRAME_SIZE} RGB24 diff overlay to {output_path}")
    print(f"  Records: {len(records)}")
    print(f"  Data size: {len(pack_diff_records(records))} bytes")
    print(f"  Packed as dense_encoder frame format")

if __name__ == "__main__":
    main()