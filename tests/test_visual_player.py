#!/usr/bin/env python3
"""
Test visual player implementation without audio hardware

This test creates a demo.wav file and tests the visual player in fallback mode.
"""

import os
import sys
import numpy as np
import time

# Add tools to path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'tools'))

def create_demo_wav(output_path='data/demo.wav'):
    """Create a simple demo WAV file for testing."""
    os.makedirs('data', exist_ok=True)
    
    # Create 10 seconds of audio (silence with some simple tones)
    sample_rate = 44100
    duration = 10.0
    t = np.linspace(0, duration, int(sample_rate * duration))
    
    # Add some simple tones for variety
    audio = 0.3 * np.sin(2 * np.pi * 440 * t)  # 440 Hz tone
    audio += 0.2 * np.sin(2 * np.pi * 880 * t)  # 880 Hz tone
    
    # Normalize
    audio = audio / np.max(np.abs(audio)) * 0.5
    
    # Save using scipy
    from scipy.io import wavfile
    wavfile.write(output_path, sample_rate, audio)
    
    print(f"Created {output_path}: {duration}s at {sample_rate}Hz")
    return output_path


def test_visual_player():
    """Test the visual player."""
    from visual_player import VisualPlayer, SimpleTerminalRenderer
    
    # Create demo audio
    demo_path = create_demo_wav()
    
    # Initialize player
    player = VisualPlayer(demo_path, grid_width=8)
    
    # Generate tiles from text
    text = "visual audio word tile synchronization demo with live playback"
    print(f"Generating {len(text.split())} word tiles...")
    player.tiles = player.generate_tiles_from_text(text)
    print(f"Created {len(player.tiles)} tiles")
    
    # Print tile timing info
    print("\nTile timing breakdown:")
    for i, tile in enumerate(player.tiles):
        print(f"  {i+1}. '{tile.word}': {tile.start_time:.2f}s - {tile.end_time:.2f}s "
              f"(duration: {tile.duration:.2f}s, phonemes: {len(tile.phonemes)})")
        if i < 3:  # Show phoneme boundaries for first few tiles
            for j, (start, end) in enumerate(tile.phoneme_boundaries):
                print(f"      Phoneme {j}: {start:.2f}s - {end:.2f}s")
    
    # Test update loop
    print("\nTesting visual update loop (5 seconds)...")
    renderer = SimpleTerminalRenderer(grid_width=8)
    
    player.play()
    
    start_time = time.time()
    frames = 0
    last_active_word = None
    
    try:
        while time.time() - start_time < 5.0:
            state = player.update()
            
            # Track changes
            if state['active_tile_word'] != last_active_word:
                print(f"[{state['current_time']:.2f}s] Now on: '{state['active_tile_word']}' "
                      f"(pulse: {state['phoneme_pulse_intensity']:.2f})")
                last_active_word = state['active_tile_word']
            
            # Test phoneme pulse detection
            if state['phoneme_pulse_intensity'] > 0.8:
                print(f"  *** PHONEME BOUNDARY DETECTED (pulse: {state['phoneme_pulse_intensity']:.2f}) ***")
            
            frames += 1
            time.sleep(0.1)  # Simulate ~10 FPS
            
    except KeyboardInterrupt:
        print("\nInterrupted by user")
    
    player.stop()
    
    # Get final state for reporting
    final_state = state if 'state' in locals() else player.update()
    
    print(f"\nTest complete:")
    print(f"  Total frames: {frames}")
    print(f"  FPS: {frames / 5.0:.1f}")
    print(f"  Final position: {final_state['current_time']:.2f}s")
    
    # Test seek functionality
    print("\nTesting seek functionality...")
    player.seek(3.5)
    state = player.update()
    print(f"  Seeked to 3.5s, actual position: {state['current_time']:.2f}s")
    print(f"  Active tile at 3.5s: '{state['active_tile_word']}'")
    
    player.seek(7.0)
    state = player.update()
    print(f"  Seeked to 7.0s, actual position: {state['current_time']:.2f}s")
    print(f"  Active tile at 7.0s: '{state['active_tile_word']}'")
    
    # Test scrubbing functionality
    print("\nTesting scrub functionality...")
    # Scrub to tile index 3 (should be 'tile')
    scrub_time = player.scrub_from_tile_index(3)
    state = player.update()
    print(f"  Scrubbed to tile 3, position: {scrub_time:.2f}s")
    print(f"  Active tile: '{state['active_tile_word']}'")
    assert state['active_tile_word'] == 'tile', f"Expected 'tile', got '{state['active_tile_word']}'"
    
    # Scrub to middle of tile index 4 (should be 'synchronization')
    scrub_time = player.scrub_from_tile_index(4, position_in_tile=0.5)
    state = player.update()
    print(f"  Scrubbed to middle of tile 4, position: {scrub_time:.2f}s")
    print(f"  Active tile: '{state['active_tile_word']}'")
    assert state['active_tile_word'] == 'synchronization', f"Expected 'synchronization', got '{state['active_tile_word']}'"
    
    # Scrub using grid position
    scrub_time = player.scrub_from_position(0.0, 0.0, grid_width=8, num_tiles=9)
    state = player.update()
    print(f"  Scrubbed to grid (0,0), position: {scrub_time:.2f}s")
    print(f"  Active tile: '{state['active_tile_word']}'")
    
    scrub_time = player.scrub_from_position(1.5, 1.0, grid_width=8, num_tiles=9)
    state = player.update()
    print(f"  Scrubbed to grid (1.5,1.0), position: {scrub_time:.2f}s")
    print(f"  Active tile: '{state['active_tile_word']}'")
    
    print("\n✓ All tests passed!")
    return True


if __name__ == '__main__':
    try:
        test_visual_player()
        sys.exit(0)
    except Exception as e:
        print(f"\n✗ Test failed: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)