#!/usr/bin/env python3
"""
test_pixel_os_daemon.py — Test the pixel OS listener daemon.

This script creates example utterances and feeds them to the daemon
to verify that it correctly processes them and updates the framebuffer.
"""

import os
import sys
import time
import json
import tempfile
import shutil
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pixel_screen import utter
from PIL import Image
import numpy as np

def test_queue_mode():
    """Test the daemon in queue mode."""
    print("Testing Pixel OS Listener Daemon (Queue Mode)")
    print("=" * 60)

    # Setup test directory
    test_queue = Path("./test_queue")
    test_fb = Path("./test_framebuffer.png")

    # Clean up from previous runs
    if test_queue.exists():
        shutil.rmtree(test_queue)
    if test_fb.exists():
        test_fb.unlink()

    test_queue.mkdir(parents=True, exist_ok=True)

    # Create initial framebuffer (black)
    fb = np.zeros((200, 320, 3), dtype=np.uint8)
    Image.fromarray(fb, mode='RGB').save(test_fb)
    print(f"Created initial framebuffer: {test_fb}")

    # Test 1: Fill with blue
    print("\n[TEST 1] Creating utterance: 'turn the screen blue'")
    ops1 = [["fill", "#1a3a8a"]]
    wav1 = test_queue / "test1_blue.wav"

    mixed = utter("turn the screen blue", ops1, str(wav1))
    print(f"  Created {wav1.name} ({len(mixed)/44100:.1f}s)")

    # Test 2: Add white rectangle
    print("\n[TEST 2] Creating utterance: 'add a white panel'")
    ops2 = [["rect", 20, 20, 280, 60, "#ffffff"]]
    wav2 = test_queue / "test2_panel.wav"

    mixed = utter("add a white panel", ops2, str(wav2))
    print(f"  Created {wav2.name} ({len(mixed)/44100:.1f}s)")

    # Test 3: Write text
    print("\n[TEST 3] Creating utterance: 'write system status'")
    ops3 = [["word", "system status", 30, 35, "#000000"]]
    wav3 = test_queue / "test3_text.wav"

    mixed = utter("write system status", ops3, str(wav3))
    print(f"  Created {wav3.name} ({len(mixed)/44100:.1f}s)")

    # Test 4: Draw a frame
    print("\n[TEST 4] Creating utterance: 'draw a red border'")
    ops4 = [["frame", 10, 10, 300, 180, "#ff0000"]]
    wav4 = test_queue / "test4_border.wav"

    mixed = utter("draw a red border", ops4, str(wav4))
    print(f"  Created {wav4.name} ({len(mixed)/44100:.1f}s)")

    # Test 5: Multiple ops
    print("\n[TEST 5] Creating utterance: 'add status indicators'")
    ops5 = [
        ["word", "running", 30, 120, "#00ff00"],
        ["word", "since", 110, 120, "#ffffff"],
        ["word", "boot", 160, 120, "#ffffff"]
    ]
    wav5 = test_queue / "test5_multi.wav"

    mixed = utter("add status indicators", ops5, str(wav5))
    print(f"  Created {wav5.name} ({len(mixed)/44100:.1f}s)")

    print("\n" + "=" * 60)
    print(f"Created {len(list(test_queue.glob('*.wav')))} test utterances in {test_queue}")
    print("\nTo test the daemon:")
    print(f"  python3 tools/pixel_os_listener.py --mode queue --watch-dir {test_queue} --fb {test_fb}")
    print("\nThe daemon will process each file and update the framebuffer.")
    print("You can watch the framebuffer update in real-time with:")
    print(f"  python3 -c \"from PIL import Image; import time; fb=Image.open('{test_fb}'); fb.show(); time.sleep(30)\"")

    return test_queue, test_fb


def test_live_mode():
    """Test instructions for live mode."""
    print("\nTesting Pixel OS Listener Daemon (Live Mode)")
    print("=" * 60)
    print("\nLive mode requires an audio input device.")
    print("To test live mode:")
    print("\n1. List available audio devices:")
    print("   python3 -c \"import sounddevice as sd; print(sd.query_devices())\"")
    print("\n2. Start the daemon with your device ID:")
    print("   python3 tools/pixel_os_listener.py --mode live --device-id 0")
    print("\n3. Create and play test utterances:")
    print("   python3 tools/pixel_screen.py utter 'test command' --ops '[[\"fill\",\"#ff0000\"]]' -o test.wav")
    print("   # Play test.wav through your speakers")
    print("\nThe daemon will detect commands via microphone and update the framebuffer.")


def verify_fb_state(fb_path: Path):
    """Verify and report framebuffer state."""
    if not fb_path.exists():
        print(f"Framebuffer not found: {fb_path}")
        return

    fb = np.asarray(Image.open(fb_path))
    print(f"\nFramebuffer state: {fb_path}")
    print(f"  Resolution: {fb.shape[1]}x{fb.shape[0]}")
    print(f"  Mean color: RGB({fb[...,0].mean():.0f}, {fb[...,1].mean():.0f}, {fb[...,2].mean():.0f})")
    print(f"  Non-black pixels: {np.count_nonzero(fb.sum(axis=2)) / (fb.shape[0]*fb.shape[1]) * 100:.1f}%")


if __name__ == '__main__':
    # Test queue mode
    queue_dir, fb_path = test_queue_mode()

    # Instructions for live mode
    test_live_mode()

    # Verify initial state
    verify_fb_state(fb_path)

    print("\n" + "=" * 60)
    print("Test setup complete!")
    print("Run the daemon commands above to verify functionality.")
    print("=" * 60)