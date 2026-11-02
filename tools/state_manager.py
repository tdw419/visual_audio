#!/usr/bin/env python3
"""
state_manager.py — Live state tracking with efficient multi-frame seek.

State Manager:
- Tracks live state during execution
- Computes efficient diffs between ticks
- Provides seek(tick_id) API without replaying history
- Deterministic state hashing for verification
"""

import copy
import hashlib
import json
import struct
from typing import Dict, Any, List, Tuple, Optional
from dataclasses import dataclass, asdict


@dataclass
class State:
    """System state snapshot."""
    x: int = 0
    y: int = 0
    mode: int = 0
    volume: int = 128
    layer: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'State':
        """Create from dictionary."""
        return cls(**data)

    def copy(self) -> 'State':
        """Create a deep copy of this state."""
        return State(**self.to_dict())

    def to_bytes(self) -> bytes:
        """Serialize to bytes for hashing."""
        return json.dumps(self.to_dict(), sort_keys=True).encode()

    def get_hash(self) -> str:
        """Get deterministic state hash."""
        return hashlib.sha256(self.to_bytes()).hexdigest()

    def diff(self, other: 'State') -> List[Tuple[int, int, int, int]]:
        """
        Compute diff from self to other.

        Returns list of (x, y, operation, value) tuples.
        operation: 0=set, 1=clear, 2=toggle

        The diffs describe how to transform self into other.
        """
        diffs = []

        # Map fields to coordinate positions (matching create_state_frame.py layout)
        field_coords = {
            'x_low': (0, 0),
            'x_high': (1, 0),
            'y_low': (2, 0),
            'y_high': (3, 0),
            'mode': (4, 0),
            'volume': (5, 0),
            'layer': (6, 0),
        }

        # Compare each field
        self_dict = self.to_dict()
        other_dict = other.to_dict()

        # X position (16-bit, split into low/high bytes)
        # Diff is: what value do we SET to get from self to other?
        if self_dict['x'] != other_dict['x']:
            x_low_val = other_dict['x'] & 0xFF
            x_high_val = (other_dict['x'] >> 8) & 0xFF
            diffs.append((0, 0, 0, x_low_val))  # Set low byte to target value
            diffs.append((1, 0, 0, x_high_val))  # Set high byte to target value

        # Y position (16-bit, split into low/high bytes)
        if self_dict['y'] != other_dict['y']:
            y_low_val = other_dict['y'] & 0xFF
            y_high_val = (other_dict['y'] >> 8) & 0xFF
            diffs.append((2, 0, 0, y_low_val))  # Set low byte
            diffs.append((3, 0, 0, y_high_val))  # Set high byte

        # Other fields (8-bit)
        for field in ['mode', 'volume', 'layer']:
            if self_dict[field] != other_dict[field]:
                x, y = field_coords[field]
                diffs.append((x, y, 0, other_dict[field]))

        return diffs

    def apply_diff(self, diffs: List[Tuple[int, int, int, int]]) -> 'State':
        """
        Apply diff records to produce new state.

        Args:
            diffs: List of (x, y, operation, value) tuples

        Returns:
            New State with diffs applied
        """
        new_state_dict = self.to_dict()

        # Map coordinate positions to field updates
        coord_to_field = {
            (0, 0): ('x_low', lambda v: (v,)),
            (1, 0): ('x_high', lambda v: (v,)),
            (2, 0): ('y_low', lambda v: (v,)),
            (3, 0): ('y_high', lambda v: (v,)),
            (4, 0): ('mode', lambda v: (v,)),
            (5, 0): ('volume', lambda v: (v,)),
            (6, 0): ('layer', lambda v: (v,)),
        }

        for x, y, operation, value in diffs:
            if (x, y) not in coord_to_field:
                continue

            field, parser = coord_to_field[(x, y)]

            if operation == 0:  # set
                if field == 'x_low':
                    # Update low byte of X, preserve high byte
                    new_x = (new_state_dict['x'] & 0xFF00) | value
                    new_state_dict['x'] = new_x
                elif field == 'x_high':
                    # Update high byte of X, preserve low byte
                    new_x = (new_state_dict['x'] & 0xFF) | (value << 8)
                    new_state_dict['x'] = new_x
                elif field == 'y_low':
                    new_y = (new_state_dict['y'] & 0xFF00) | value
                    new_state_dict['y'] = new_y
                elif field == 'y_high':
                    new_y = (new_state_dict['y'] & 0xFF) | (value << 8)
                    new_state_dict['y'] = new_y
                else:
                    new_state_dict[field] = value
            elif operation == 1:  # clear
                if field in ['x_low', 'x_high']:
                    new_state_dict['x'] = 0
                elif field in ['y_low', 'y_high']:
                    new_state_dict['y'] = 0
                else:
                    new_state_dict[field] = 0
            elif operation == 2:  # toggle
                if field in ['mode', 'volume', 'layer']:
                    new_state_dict[field] = new_state_dict[field] ^ value

        return State.from_dict(new_state_dict)


class StateManager:
    """
    Live state tracking with multi-frame seek capability.

    Usage:
        manager = StateManager()
        manager.tick()  # Advance to tick 1
        state_at_0 = manager.seek(0)  # Get state at tick 0 (no replay)
        state_at_10 = manager.seek(10)  # Will compute state efficiently
    """

    def __init__(self, initial_state: Optional[State] = None):
        """Initialize state manager."""
        self._initial_state = initial_state or State()
        self._current_tick = 0
        self._current_state = self._initial_state
        self._tick_cache: Dict[int, State] = {0: self._initial_state.copy()}
        self._diffs: Dict[int, List[Tuple[int, int, int, int]]] = {}

    def tick(self, state_changes: Optional[State] = None) -> int:
        """
        Advance to next tick with optional state changes.

        Args:
            state_changes: New state for this tick (if None, current state unchanged)

        Returns:
            New tick ID
        """
        self._current_tick += 1

        if state_changes is None:
            # No changes, copy current state
            new_state = State(**self._current_state.to_dict())
        else:
            new_state = state_changes

        # Compute diff from previous state
        diffs = self._current_state.diff(new_state)
        self._diffs[self._current_tick] = diffs

        # Cache new state
        self._tick_cache[self._current_tick] = new_state

        # Update current
        prev_state = self._current_state
        self._current_state = new_state

        # Prune cache (keep last 100 ticks for efficiency)
        self._prune_cache(max_cached=100)

        return self._current_tick

    def seek(self, tick_id: int) -> State:
        """
        Get state at tick_id without replaying all ticks.

        Uses cached states and diffs for efficient reconstruction.

        Args:
            tick_id: Tick ID to seek to

        Returns:
            State at tick_id
        """
        if tick_id < 0:
            raise ValueError(f"tick_id must be >= 0, got {tick_id}")

        if tick_id == 0:
            return self._initial_state

        if tick_id in self._tick_cache:
            return self._tick_cache[tick_id]

        # Find nearest cached tick (use binary search on sorted keys)
        cached_ticks = sorted(self._tick_cache.keys())
        nearest_tick = max([t for t in cached_ticks if t < tick_id], default=0)

        # Start from nearest cached state
        state = self._tick_cache[nearest_tick].copy()

        # Apply diffs forward to target tick
        for t in range(nearest_tick + 1, tick_id + 1):
            if t in self._diffs:
                state = state.apply_diff(self._diffs[t])

        # Cache the result
        self._tick_cache[tick_id] = state

        return state

    def get_diff(self, tick_id: int) -> List[Tuple[int, int, int, int]]:
        """Get diff records for tick_id."""
        if tick_id not in self._diffs:
            return []
        return self._diffs[tick_id]

    def get_current_state(self) -> State:
        """Get current state."""
        return self._current_state

    def get_current_tick(self) -> int:
        """Get current tick ID."""
        return self._current_tick

    def get_state_hash(self, tick_id: int) -> str:
        """Get deterministic hash for state at tick_id."""
        state = self.seek(tick_id)
        return state.get_hash()

    def verify_tick(self, tick_id: int, expected_hash: str) -> bool:
        """
        Verify that state at tick_id matches expected hash.

        Args:
            tick_id: Tick to verify
            expected_hash: Expected state hash

        Returns:
            True if hashes match
        """
        return self.get_state_hash(tick_id) == expected_hash

    def _prune_cache(self, max_cached: int = 100):
        """Prune cache to keep only recent ticks."""
        if len(self._tick_cache) <= max_cached:
            return

        # Keep initial tick and last N ticks
        tick_ids = sorted(self._tick_cache.keys())
        to_keep = [0] + tick_ids[-max_cached:]

        self._tick_cache = {
            t: self._tick_cache[t] for t in to_keep
        }

    def get_history_summary(self) -> Dict[str, Any]:
        """Get summary of state history."""
        return {
            'total_ticks': self._current_tick,
            'cached_ticks': len(self._tick_cache),
            'diffs_count': len(self._diffs),
            'cache_keys': sorted(self._tick_cache.keys()),
        }


def pack_diffs(diffs: List[Tuple[int, int, int, int]]) -> bytes:
    """
    Pack diff records into bytes (10 bytes each).

    Format per record:
      - Bytes 0-3: X coordinate (32-bit, little-endian)
      - Bytes 4-7: Y coordinate (32-bit, little-endian)
      - Byte 8: Operation (0=set, 1=clear, 2=toggle)
      - Byte 9: Value (0-255)
    """
    data = b''
    for x, y, operation, value in diffs:
        data += struct.pack('<iiBB', x, y, operation, value)
    return data


def unpack_diffs(data: bytes) -> List[Tuple[int, int, int, int]]:
    """Unpack diff records from bytes."""
    diffs = []
    for i in range(0, len(data), 10):
        if i + 10 > len(data):
            break
        x, y, operation, value = struct.unpack('<iiBB', data[i:i+10])
        diffs.append((x, y, operation, value))
    return diffs


if __name__ == "__main__":
    # Demo
    print("=== State Manager Demo ===\n")

    manager = StateManager()

    print(f"Initial state: {manager.get_current_state()}")
    print(f"Initial hash: {manager.get_state_hash(0)}\n")

    # Simulate some state changes
    for i in range(1, 6):
        new_state = State(x=i*10, y=i*20, mode=i%4, volume=128+i*10, layer=i%3)
        tick_id = manager.tick(new_state)
        print(f"Tick {tick_id}: {new_state}")
        print(f"  Hash: {manager.get_state_hash(tick_id)}")
        print(f"  Diff: {manager.get_diff(tick_id)}\n")

    # Seek back without replay
    print("=== Seek Backwards (No Replay) ===")
    state_at_2 = manager.seek(2)
    print(f"State at tick 2: {state_at_2}")
    print(f"Hash matches: {manager.verify_tick(2, manager.get_state_hash(2))}\n")

    # Seek forward
    print("=== Seek Forward ===")
    state_at_4 = manager.seek(4)
    print(f"State at tick 4: {state_at_4}")
    print(f"Hash: {manager.get_state_hash(4)}\n")

    # Summary
    print("=== History Summary ===")
    print(json.dumps(manager.get_history_summary(), indent=2))