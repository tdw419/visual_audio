#!/usr/bin/env python3
"""
timeline.py — Append-only timeline storage with index and prune support.

Timeline Format:
- Frames 4+: Tick diffs (not full snapshots)
- Frame 100: Index mapping tick_id → byte_offset for O(1) seek
- Prunable history with configurable keep-last-N policy
"""

import os
import json
import struct
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

import sys
sys.path.insert(0, str(Path(__file__).parent))
from dense_encoder import frame, unframe


@dataclass
class TimelineEntry:
    """Single tick entry in timeline."""
    tick_id: int
    timestamp: float
    state_hash: str
    diff_records: List[Tuple[int, int, int, int]]  # (x, y, operation, value)
    metadata: Dict


class TimelineStorage:
    """
    Append-only timeline storage with index.

    Format:
      - Entry: [MAGIC:2][LEN:2][PAYLOAD][CRC:4]
      - Payload: JSON {tick_id, timestamp, state_hash, diff_records, metadata}
      - Index: tick_id → byte_offset (stored in frame 100)
    """

    INDEX_FRAME_ID = 100

    def __init__(self, storage_dir: Path, max_ticks: int = 1000):
        """
        Initialize timeline storage.

        Args:
            storage_dir: Directory to store timeline frames
            max_ticks: Maximum number of ticks to keep (pruning)
        """
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)

        self.max_ticks = max_ticks
        self._index: Dict[int, Dict] = {}  # tick_id → {frame_id, byte_offset, file_size}
        self._loaded_index = False

        self._load_index()

    def _load_index(self):
        """Load index from disk."""
        index_path = self.storage_dir / f"frame_{self.INDEX_FRAME_ID}.idx"

        if not index_path.exists():
            self._loaded_index = True
            return

        try:
            with open(index_path, 'r') as f:
                self._index = json.load(f)
            self._loaded_index = True
        except Exception as e:
            print(f"Warning: Failed to load index: {e}")
            self._index = {}
            self._loaded_index = True

    def _save_index(self):
        """Save index to disk."""
        index_path = self.storage_dir / f"frame_{self.INDEX_FRAME_ID}.idx"

        try:
            with open(index_path, 'w') as f:
                json.dump(self._index, f, indent=2)
        except Exception as e:
            print(f"Warning: Failed to save index: {e}")

    def append(self, entry: TimelineEntry) -> int:
        """
        Append entry to timeline.

        Args:
            entry: TimelineEntry to append

        Returns:
            Frame ID where entry was stored
        """
        # Build JSON payload
        payload_data = {
            'tick_id': entry.tick_id,
            'timestamp': entry.timestamp,
            'state_hash': entry.state_hash,
            'diff_records': entry.diff_records,
            'metadata': entry.metadata,
        }
        payload_bytes = json.dumps(payload_data).encode()

        # Frame with dense_encoder
        framed = frame(payload_bytes)

        # Calculate frame ID (start at frame 4, skip frame 100 for index)
        frame_id = 4 + len(self._index)
        if frame_id >= self.INDEX_FRAME_ID:
            frame_id += 1  # Skip index frame

        # Store record byte offset (before framing)
        byte_offset = 0  # Simplified: single entry per frame

        # Write frame
        frame_path = self.storage_dir / f"frame_{frame_id}.bin"
        with open(frame_path, 'wb') as f:
            f.write(framed)

        # Update index
        self._index[entry.tick_id] = {
            'frame_id': frame_id,
            'byte_offset': byte_offset,
            'file_size': len(framed),
        }

        self._save_index()

        # Prune if needed
        self._prune()

        return frame_id

    def get(self, tick_id: int) -> Optional[TimelineEntry]:
        """
        Get timeline entry by tick_id.

        Args:
            tick_id: Tick ID to retrieve

        Returns:
            TimelineEntry or None if not found
        """
        if tick_id not in self._index:
            return None

        index_entry = self._index[tick_id]
        frame_id = index_entry['frame_id']

        # Read frame
        frame_path = self.storage_dir / f"frame_{frame_id}.bin"
        if not frame_path.exists():
            return None

        try:
            with open(frame_path, 'rb') as f:
                framed = f.read()

            # Unframe
            payload_bytes = unframe(framed)
            payload_data = json.loads(payload_bytes.decode())

            return TimelineEntry(
                tick_id=payload_data['tick_id'],
                timestamp=payload_data['timestamp'],
                state_hash=payload_data['state_hash'],
                diff_records=[tuple(r) for r in payload_data['diff_records']],
                metadata=payload_data['metadata'],
            )
        except Exception as e:
            print(f"Warning: Failed to read frame {frame_id}: {e}")
            return None

    def get_range(self, start_tick: int, end_tick: int) -> List[TimelineEntry]:
        """
        Get range of timeline entries.

        Args:
            start_tick: Start tick (inclusive)
            end_tick: End tick (inclusive)

        Returns:
            List of TimelineEntry in tick order
        """
        entries = []
        for tick_id in range(start_tick, end_tick + 1):
            entry = self.get(tick_id)
            if entry:
                entries.append(entry)
        return entries

    def _prune(self):
        """Prune old entries beyond max_ticks."""
        if len(self._index) <= self.max_ticks:
            return

        # Sort tick IDs
        tick_ids = sorted(self._index.keys())

        # Calculate how many to remove
        to_remove_count = len(self._index) - self.max_ticks

        # Remove oldest
        for tick_id in tick_ids[:to_remove_count]:
            index_entry = self._index.pop(tick_id)

            # Delete frame file
            frame_id = index_entry['frame_id']
            frame_path = self.storage_dir / f"frame_{frame_id}.bin"
            try:
                if frame_path.exists():
                    frame_path.unlink()
            except Exception as e:
                print(f"Warning: Failed to delete frame {frame_id}: {e}")

        # Save updated index
        self._save_index()

    def clear(self):
        """Clear all timeline data."""
        # Delete all frame files
        for frame_path in self.storage_dir.glob("frame_*.bin"):
            try:
                frame_path.unlink()
            except Exception as e:
                print(f"Warning: Failed to delete {frame_path}: {e}")

        # Delete index
        index_path = self.storage_dir / f"frame_{self.INDEX_FRAME_ID}.idx"
        try:
            if index_path.exists():
                index_path.unlink()
        except Exception as e:
            print(f"Warning: Failed to delete index: {e}")

        self._index = {}
        self._loaded_index = False

    def get_summary(self) -> Dict:
        """Get timeline summary."""
        if self._index:
            tick_ids = sorted(self._index.keys())
            storage_size = sum(
                f.stat().st_size for f in self.storage_dir.glob("frame_*.bin")
            )
        else:
            tick_ids = []
            storage_size = 0

        return {
            'total_entries': len(self._index),
            'tick_range': (tick_ids[0], tick_ids[-1]) if tick_ids else (None, None),
            'storage_bytes': storage_size,
            'storage_mb': storage_size / (1024 * 1024),
            'max_ticks': self.max_ticks,
        }


def pack_diff_records(records: List[Tuple[int, int, int, int]]) -> bytes:
    """
    Pack diff records into bytes (10 bytes each).

    Format per record:
      - Bytes 0-3: X coordinate (32-bit, little-endian)
      - Bytes 4-7: Y coordinate (32-bit, little-endian)
      - Byte 8: Operation (0=set, 1=clear, 2=toggle)
      - Byte 9: Value (0-255)
    """
    data = b''
    for x, y, operation, value in records:
        data += struct.pack('<iiBB', x, y, operation, value)
    return data


def unpack_diff_records(data: bytes) -> List[Tuple[int, int, int, int]]:
    """Unpack diff records from bytes."""
    records = []
    for i in range(0, len(data), 10):
        if i + 10 > len(data):
            break
        x, y, operation, value = struct.unpack('<iiBB', data[i:i+10])
        records.append((x, y, operation, value))
    return records


if __name__ == "__main__":
    # Demo
    print("=== Timeline Storage Demo ===\n")

    import time

    # Create timeline
    storage_dir = Path("/tmp/timeline_test")
    timeline = TimelineStorage(storage_dir, max_ticks=100)

    # Append some entries
    for i in range(1, 6):
        entry = TimelineEntry(
            tick_id=i,
            timestamp=time.time(),
            state_hash=f"hash_{i}",
            diff_records=[(i, i*2, 0, i*10)],
            metadata={'iteration': i},
        )
        frame_id = timeline.append(entry)
        print(f"Tick {i} → Frame {frame_id}")

    print()

    # Query entries
    print("=== Query Entries ===")
    entry_3 = timeline.get(3)
    if entry_3:
        print(f"Entry at tick 3: {entry_3}")

    range_entries = timeline.get_range(2, 4)
    print(f"Entries 2-4: {[e.tick_id for e in range_entries]}")

    print()

    # Summary
    print("=== Timeline Summary ===")
    print(json.dumps(timeline.get_summary(), indent=2))

    # Cleanup
    timeline.clear()
    print(f"\nCleared timeline at {storage_dir}")