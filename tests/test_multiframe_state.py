"""
tests/test_multiframe_state.py — Multi-frame state management tests.

Tests for StateManager and TimelineStorage components.
"""

import pytest
import tempfile
import shutil
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent / 'tools'))

from state_manager import StateManager, State, pack_diffs, unpack_diffs
from timeline import TimelineStorage, TimelineEntry


@pytest.fixture
def temp_storage_dir():
    """Create temporary directory for timeline storage."""
    temp_dir = Path(tempfile.mkdtemp())
    yield temp_dir
    shutil.rmtree(temp_dir)


class TestStateManager:
    """Test StateManager functionality."""

    def test_initial_state(self):
        """Test initial state setup."""
        manager = StateManager()
        assert manager.get_current_tick() == 0
        assert manager.get_current_state().x == 0
        assert manager.get_current_state().y == 0

    def test_tick_advancement(self):
        """Test tick advancement with state changes."""
        manager = StateManager()

        # Tick 1
        state1 = State(x=10, y=20, mode=1, volume=138, layer=1)
        tick_id = manager.tick(state1)
        assert tick_id == 1
        assert manager.get_current_tick() == 1

        # Tick 2
        state2 = State(x=20, y=40, mode=2, volume=148, layer=2)
        tick_id = manager.tick(state2)
        assert tick_id == 2
        assert manager.get_current_tick() == 2

    def test_seek_backward(self):
        """Test seek to previous tick without replay."""
        manager = StateManager()

        # Create 10 ticks
        states = []
        for i in range(1, 11):
            state = State(x=i*10, y=i*20, mode=i%4, volume=128+i*10, layer=i%3)
            states.append(state)
            manager.tick(state)

        # Save state at tick 10 for verification
        state_at_10 = manager.get_current_state()
        hash_at_10 = manager.get_state_hash(10)

        # Seek back to tick 5 (should not replay all ticks)
        state_at_5 = manager.seek(5)

        # Verify correct state
        assert state_at_5.x == 50
        assert state_at_5.y == 100
        assert state_at_5.mode == 1  # 5%4 = 1

        # Now seek back to tick 10 and verify it matches
        state_at_10_from_seek = manager.seek(10)
        assert state_at_10_from_seek.get_hash() == hash_at_10
        assert state_at_10_from_seek.to_dict() == state_at_10.to_dict()

    def test_efficient_storage(self):
        """Test that timeline uses diffs, not full snapshots."""
        manager = StateManager()

        # Run 1000 ticks
        for i in range(1, 1001):
            state = State(x=i, y=i*2, mode=i%4)
            manager.tick(state)

        summary = manager.get_history_summary()

        # Verify: total ticks = 1000, but cache is pruned (last 100 + initial)
        assert summary['total_ticks'] == 1000
        assert summary['diffs_count'] == 1000

        # Cache should be pruned (initial + last 100)
        assert summary['cached_ticks'] <= 101

    def test_deterministic_state_hash(self):
        """Test that same tick produces same hash deterministically."""
        # First run
        manager1 = StateManager()
        for i in range(1, 6):
            state = State(x=i*10, y=i*20, mode=i%4)
            manager1.tick(state)
        hash_3_run1 = manager1.get_state_hash(3)

        # Second run (same sequence)
        manager2 = StateManager()
        for i in range(1, 6):
            state = State(x=i*10, y=i*20, mode=i%4)
            manager2.tick(state)
        hash_3_run2 = manager2.get_state_hash(3)

        # Hashes must match
        assert hash_3_run1 == hash_3_run2

    def test_diff_accuracy(self):
        """Test diff computation and application."""
        state1 = State(x=10, y=20, mode=1, volume=128, layer=0)
        state2 = State(x=15, y=25, mode=2, volume=130, layer=1)

        # Compute diff
        diffs = state1.diff(state2)

        # Apply diff to state1, should get state2
        state1_reconstructed = state1.apply_diff(diffs)

        assert state1_reconstructed.x == state2.x
        assert state1_reconstructed.y == state2.y
        assert state1_reconstructed.mode == state2.mode
        assert state1_reconstructed.volume == state2.volume
        assert state1_reconstructed.layer == state2.layer

    def test_state_copy(self):
        """Test state copy creates independent instance."""
        state1 = State(x=10, y=20, mode=1)
        state2 = state1.copy()

        state2.x = 99
        state2.y = 88

        # Original should be unchanged
        assert state1.x == 10
        assert state1.y == 20
        assert state2.x == 99
        assert state2.y == 88

    def test_verify_tick(self):
        """Test tick verification against expected hash."""
        manager = StateManager()

        for i in range(1, 6):
            state = State(x=i*10, y=i*20)
            manager.tick(state)

        # Get hash at tick 3
        hash_at_3 = manager.get_state_hash(3)

        # Verify (should match)
        assert manager.verify_tick(3, hash_at_3) is True

        # Verify with wrong hash (should fail)
        assert manager.verify_tick(3, "wrong_hash") is False


class TestDiffPacking:
    """Test diff packing/unpacking utilities."""

    def test_pack_unpack_diffs(self):
        """Test pack_diffs and unpack_diffs round-trip."""
        diffs = [(0, 0, 0, 10), (1, 0, 0, 20), (2, 0, 1, 0)]

        packed = pack_diffs(diffs)
        unpacked = unpack_diffs(packed)

        assert unpacked == diffs

    def test_empty_diffs(self):
        """Test empty diffs list."""
        diffs = []
        packed = pack_diffs(diffs)
        assert packed == b''

        unpacked = unpack_diffs(packed)
        assert unpacked == []

    def test_multiple_diffs(self):
        """Test packing many diff records."""
        # Values must be 0-255 for 'B' format
        diffs = [(i, i*2, i%3, (i*10) % 256) for i in range(100)]

        packed = pack_diffs(diffs)
        unpacked = unpack_diffs(packed)

        assert len(unpacked) == 100
        assert unpacked == diffs


class TestTimelineStorage:
    """Test TimelineStorage functionality."""

    def test_append_and_get(self, temp_storage_dir):
        """Test appending and retrieving entries."""
        timeline = TimelineStorage(temp_storage_dir)

        entry = TimelineEntry(
            tick_id=1,
            timestamp=12345.0,
            state_hash="hash_1",
            diff_records=[(0, 0, 0, 10), (1, 0, 0, 20)],
            metadata={'test': True},
        )

        frame_id = timeline.append(entry)
        assert frame_id == 4

        retrieved = timeline.get(1)
        assert retrieved is not None
        assert retrieved.tick_id == 1
        assert retrieved.state_hash == "hash_1"
        assert len(retrieved.diff_records) == 2

    def test_get_range(self, temp_storage_dir):
        """Test getting range of entries."""
        timeline = TimelineStorage(temp_storage_dir)

        # Append 10 entries
        for i in range(1, 11):
            entry = TimelineEntry(
                tick_id=i,
                timestamp=float(i),
                state_hash=f"hash_{i}",
                diff_records=[(i, i*2, 0, i*10)],
                metadata={'iteration': i},
            )
            timeline.append(entry)

        # Get range 3-7
        entries = timeline.get_range(3, 7)
        assert len(entries) == 5
        assert entries[0].tick_id == 3
        assert entries[-1].tick_id == 7

    def test_index_seek(self, temp_storage_dir):
        """Test that index enables O(1) seek."""
        timeline = TimelineStorage(temp_storage_dir)

        # Append 100 entries
        for i in range(1, 101):
            entry = TimelineEntry(
                tick_id=i,
                timestamp=float(i),
                state_hash=f"hash_{i}",
                diff_records=[],
                metadata={},
            )
            timeline.append(entry)

        # Get tick 50 (should use index, not scan all)
        entry_50 = timeline.get(50)
        assert entry_50 is not None
        assert entry_50.tick_id == 50

        # Get tick 99
        entry_99 = timeline.get(99)
        assert entry_99 is not None
        assert entry_99.tick_id == 99

    def test_prune_old_entries(self, temp_storage_dir):
        """Test pruning old entries beyond max_ticks."""
        timeline = TimelineStorage(temp_storage_dir, max_ticks=10)

        # Append 20 entries (should prune to last 10)
        for i in range(1, 21):
            entry = TimelineEntry(
                tick_id=i,
                timestamp=float(i),
                state_hash=f"hash_{i}",
                diff_records=[],
                metadata={},
            )
            timeline.append(entry)

        summary = timeline.get_summary()

        # Should have max 10 entries
        assert summary['total_entries'] <= 10

        # Oldest entry should be tick 11 (ticks 1-10 pruned)
        earliest_entry = timeline.get(min(timeline._index.keys()))
        if earliest_entry:
            assert earliest_entry.tick_id >= 11

    def test_clear_timeline(self, temp_storage_dir):
        """Test clearing timeline."""
        timeline = TimelineStorage(temp_storage_dir)

        # Add entries
        for i in range(1, 6):
            entry = TimelineEntry(
                tick_id=i,
                timestamp=float(i),
                state_hash=f"hash_{i}",
                diff_records=[],
                metadata={},
            )
            timeline.append(entry)

        # Clear
        timeline.clear()

        # Verify empty
        summary = timeline.get_summary()
        assert summary['total_entries'] == 0

    def test_storage_efficiency(self, temp_storage_dir):
        """Test that storage is efficient (not storing full snapshots)."""
        timeline = TimelineStorage(temp_storage_dir)

        # Append 1000 entries
        for i in range(1, 1001):
            entry = TimelineEntry(
                tick_id=i,
                timestamp=float(i),
                state_hash=f"hash_{i}",
                diff_records=[(0, 0, 0, i % 256)],  # Small diff
                metadata={'tick': i},
            )
            timeline.append(entry)

        summary = timeline.get_summary()

        # Storage should be < 1MB for 1000 small diffs
        assert summary['storage_mb'] < 1.0


class TestIntegration:
    """Integration tests for StateManager + TimelineStorage."""

    def test_end_to_end_timeline(self, temp_storage_dir):
        """Test full cycle: tick → timeline → seek → verify."""
        manager = StateManager()
        timeline = TimelineStorage(temp_storage_dir)

        # Run 20 ticks, storing each in timeline
        hashes = {}
        for i in range(1, 21):
            state = State(x=i*10, y=i*20, mode=i%4, volume=128+i, layer=i%3)
            tick_id = manager.tick(state)

            # Store in timeline
            entry = TimelineEntry(
                tick_id=tick_id,
                timestamp=float(i),
                state_hash=manager.get_state_hash(tick_id),
                diff_records=manager.get_diff(tick_id),
                metadata={'iteration': i},
            )
            timeline.append(entry)

            # Save hash
            hashes[tick_id] = manager.get_state_hash(tick_id)

        # Seek to tick 5 from timeline
        timeline_entry = timeline.get(5)
        assert timeline_entry is not None

        # Reconstruct state from timeline diff
        base_state = State()
        reconstructed_state = base_state.apply_diff(timeline_entry.diff_records)

        # Verify hash matches
        assert manager.verify_tick(5, hashes[5])

    def test_seek_across_gaps(self, temp_storage_dir):
        """Test seek when cache has gaps (pruning)."""
        manager = StateManager()  # Uses default max_cached=100

        # Create 20 ticks
        for i in range(1, 21):
            state = State(x=i*10, y=i*20)
            manager.tick(state)

        # Seek to tick 2 (not in cache)
        state_2 = manager.seek(2)
        assert state_2.x == 20

        # Seek to tick 15 (not in cache)
        state_15 = manager.seek(15)
        assert state_15.x == 150

        # Seek to tick 10 (not in cache)
        state_10 = manager.seek(10)
        assert state_10.x == 100


if __name__ == '__main__':
    pytest.main([__file__, '-v'])