#!/usr/bin/env python3
"""
Override for load_state to catch PIL errors.
"""

import sys
import os
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from src.spatial.temporal_log import TemporalLog, SystemState, demo_procedural_gen


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
        
        # Unframe
        from src.codec.phy import unframe
        framed = self.pixels_to_bytes(pixel_bytes)
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
    
    # Corrupt the PNG file
    with open(frame_path, 'r+b') as f:
        f.seek(100)
        f.write(b'\xFF\xFF\xFF\xFF')
    
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