#!/usr/bin/env python3
"""
create_timeline_frame.py — Create Frame 4+: Temporal Memory (Execution History).

Each timeline frame is a full state snapshot at execution tick N.
Format: dense_encoder [UA][LEN][PAYLOAD][CRC32] wrapped snapshot.
Payload contains:
- System state snapshot (JSON)
- Diff overlay delta (10-byte records)
- Tick metadata (timestamp, execution time)
"""

import json
import struct
import sys
import time
import hashlib

sys.path.insert(0, "tools")
from dense_encoder import frame

def create_timeline_snapshot(state: dict, diff_delta: list, tick_id: int) -> bytes:
    """Create a timeline snapshot payload."""
    
    # Build snapshot structure
    snapshot = {
        "tick_id": tick_id,
        "timestamp": time.time(),
        "state": state,
        "diff_delta": diff_delta,
        "checksum": None  # Will be computed
    }
    
    # Serialize to JSON
    payload = json.dumps(snapshot).encode()
    
    # Add checksum
    snapshot["checksum"] = hashlib.sha256(payload).hexdigest()
    payload = json.dumps(snapshot).encode()
    
    return payload

def create_timeline_frame(state: dict, diff_delta: list, tick_id: int) -> bytes:
    """Create a timeline frame from snapshot."""
    payload = create_timeline_snapshot(state, diff_delta, tick_id)
    
    # Wrap in dense_encoder frame format
    framed = frame(payload)
    
    return framed

def main():
    # Default demo state
    state = {
        "x": 0,
        "y": 0,
        "mode": 0,
        "volume": 128,
        "layer": 0
    }
    
    # Default demo diff delta
    diff_delta = []
    
    # Default tick ID
    tick_id = 1
    
    # Parse args
    if len(sys.argv) > 1:
        state = json.loads(sys.argv[1])
    if len(sys.argv) > 2:
        diff_delta = json.loads(sys.argv[2])
    if len(sys.argv) > 3:
        tick_id = int(sys.argv[3])
    
    print(f"Creating timeline frame for tick {tick_id}")
    print(f"  State: {state}")
    print(f"  Diff delta: {len(diff_delta)} records")
    
    # Create frame data
    frame_data = create_timeline_frame(state, diff_delta, tick_id)
    
    # Save raw frame data (not full 450x450, just the framed payload)
    # This can be embedded in a full frame or stored as timeline payload
    output_path = f"timeline_tick_{tick_id:04d}.bin"
    with open(output_path, 'wb') as f:
        f.write(frame_data)
    
    print(f"Wrote timeline snapshot to {output_path}")
    print(f"  Frame data size: {len(frame_data)} bytes")
    print(f"  Tick ID: {tick_id}")

if __name__ == "__main__":
    main()