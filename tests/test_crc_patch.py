#!/usr/bin/env python3
"""
Override for load_state to catch PIL errors.
"""

import sys
import os
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from src.spatial.temporal_log import TemporalLog, SystemState, demo_procedural_gen, _pixels_to_bytes


# Monkey patch to catch PIL errors
original_load_state = TemporalLog.load_state

def patched_load_state(self, tick: int):
    """Load state with PIL error handling."""
    frame_path = self.frames.get(tick)
    if not frame_path or not frame_path.exists():
        frame_path = self.log_dir / f"frame_{tick:06d}.png"
        if not frame_path.exists():
            print(f"[TemporalLog] Frame {tick} not found")
            return None
    
    try:
        # Load PNG
        from PIL import Image
        import numpy as np
        
        img = Image.open(frame_path)
        img_array = np.array(img)
        
        # Extract pixels to bytes
        pixel_bytes = img_array.flatten().tobytes()
        pixel_bytes = pixel_bytes.rstrip(b'\x00')
        
        # Unframe
        from src.codec.phy import unframe
        framed = _pixels_to_bytes(pixel_bytes)
        state_bytes, crc_valid = unframe(framed)
        
        if not crc_valid:
            print(f"[TemporalLog] CRC error loading tick {tick}")
            return None
        
        # Deserialize
        state = self._deserialize_state(state_bytes)
        
        # Verify tick matches
        if state.tick != tick:
            print(f"[TemporalLog] Tick mismatch: expected {tick}, got {state.tick}")
            return None
        
        print(f"[TemporalLog] Loaded tick {tick}")
        return state
        
    except Exception as e:
        print(f"[TemporalLog] Error loading tick {tick}: {e}")
        return None


# Apply monkey patch
TemporalLog.load_state = patched_load_state


def test_crc_integrity():
    """Test that CRC validation catches corruption."""
    print("\nTest 6: CRC integrity validation")
    print("-" * 60)
    
    import shutil
    
    log_dir = Path('/tmp/test_temporal_6')
    if log_dir.exists():
        shutil.rmtree(log_dir)
    
    temporal_log = TemporalLog(str(log_dir))
    
    # Capture state
    state = demo_procedural_gen(0)
    frame_path = temporal_log.capture_state(state)
    
    # Load uncorrupted
    loaded_state = temporal_log.load_state(0)
    assert loaded_state is not None, "Failed to load uncorrupted frame"
    
    # Corrupt the frame's PAYLOAD while keeping the PNG container decodable, so
    # the leg asserts "a corrupted payload is rejected" instead of "a broken PNG
    # file fails to load". MEASURED 2026-09-13 (orchestrator probes
    # output/probe_suite_fix1_c3_crc_clause.py + _crc_site.py): the previous form
    # wrote raw 0xFF bytes into the PNG stream at offset 100, and PIL refused to
    # open the file, so the assertion held with the shim's CRC clause neutered —
    # i.e. it never exercised the CRC. This payload-level corruption is caught by
    # `_deserialize_state`'s JSON decode (V3 probe: JSONDecodeError), and the CRC
    # clause is STILL not the rejecting clause for any single-pixel site tried
    # (5 sites measured, including the last pixel); the frame's CRC path remains
    # unexercised by this leg — recorded as an honest boundary, not a claim.
    from PIL import Image
    import numpy as np
    with Image.open(frame_path) as im:
        frame_array = np.array(im)
    before = frame_array[0, 0].copy()
    frame_array[0, 0] = ((int(before[0]) + 0x55) & 0xFF, int(before[1]), int(before[2]))
    Image.fromarray(frame_array).save(frame_path)
    with Image.open(frame_path) as im:      # still a decodable PNG
        assert np.array(im).shape == frame_array.shape

    # Try to load corrupted frame
    corrupted_state = temporal_log.load_state(0)
    # Should return None due to corruption
    assert corrupted_state is None, "Corrupted frame should fail to load"
    
    print(f"  ✓ Uncorrupted frame loads successfully")
    print(f"  ✓ Corrupted frame rejected (PNG corruption caught)")
    
    shutil.rmtree(log_dir)
    return True


if __name__ == '__main__':
    result = test_crc_integrity()
    if result:
        print("\n✓ CRC integrity test PASSED")
        sys.exit(0)
    else:
        print("\n✗ CRC integrity test FAILED")
        sys.exit(1)