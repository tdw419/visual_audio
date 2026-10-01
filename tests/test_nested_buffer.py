#!/usr/bin/env python3
"""
Tests for TASK_SE005: Nested frame buffer compositing.
"""

import numpy as np
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from src.spatial.nested_buffer import NestedBuffer

def test_metadata_zone_parsing():
    buf = NestedBuffer()
    buf.system_tick = 1234
    buf.media_tick = 567
    buf.volume = 0.5
    buf.fps = 60.0
    
    buf.composite()
    
    parsed = buf.parse_metadata_zone()
    
    assert parsed['system_tick'] == 1234
    assert parsed['media_tick'] == 567
    # Use approximate equality for float conversions via 8-bit rgb
    assert abs(parsed['volume'] - 0.5) < 0.01
    assert parsed['fps'] == 60.0
    print("✓ metadata zone parsing passed")


def test_display_zone_rendering():
    display_rect = (10, 10, 100, 100)
    buf = NestedBuffer(width=200, height=200, display_rect=display_rect)
    
    # Create a red video frame
    red_frame = np.zeros((100, 100, 3), dtype=np.uint8)
    red_frame[:, :, 0] = 255
    
    buf.set_video_source([red_frame])
    buf.composite()
    
    # Check that display zone is red in the composited frame
    x, y, w, h = display_rect
    display_region = buf.frame[y:y+h, x:x+w]
    assert np.all(display_region[:, :, 0] == 255)
    assert np.all(display_region[:, :, 1] == 0)
    assert np.all(display_region[:, :, 2] == 0)
    
    # Check that outside the display zone (and metadata zone) is black
    outside = buf.frame[150, 150]
    assert np.all(outside == 0)
    print("✓ display zone rendering passed")


def test_time_vector_independence():
    buf = NestedBuffer()
    
    buf.advance_system_time(10)
    assert buf.system_tick == 10
    assert buf.media_tick == 0
    
    buf.advance_media_time(5)
    assert buf.system_tick == 10
    assert buf.media_tick == 5
    
    print("✓ time vector independence passed")


def test_seekable_media_time():
    buf = NestedBuffer()
    
    # create 10 distinct frames
    frames = [np.ones((10, 10, 3), dtype=np.uint8) * i for i in range(10)]
    buf.set_video_source(frames)
    
    # media fps is 24.0. Seek to 0.25 seconds -> frame 6 (0.25 * 24 = 6)
    buf.seek_media_time(0.25)
    assert buf.media_tick == 6
    
    frame = buf.get_current_video_frame()
    assert np.all(frame == 6)
    
    # Seek out of bounds
    buf.seek_media_time(1.0) # frame 24, clamped to 9
    assert buf.media_tick == 9
    
    print("✓ seekable Media Time passed")


if __name__ == '__main__':
    test_metadata_zone_parsing()
    test_display_zone_rendering()
    test_time_vector_independence()
    test_seekable_media_time()
    print("All tests passed.")
