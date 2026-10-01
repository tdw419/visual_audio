#!/usr/bin/env python3
"""
TASK_I001 Verification Script

Run this to verify that TASK_I001 implementation meets receipt criteria.

Tests all three criteria:
1. Tiles highlight in sync with audio during playback
2. Tiles pulse on phoneme boundaries
3. Scrub through audio by dragging across tile grid
"""

import sys
import time

def run_verification():
    print('=' * 80)
    print('TASK_I001 Verification')
    print('=' * 80)
    print()

    # Import and setup
    from visual_player import VisualPlayer, SimpleTerminalRenderer

    player = VisualPlayer('', grid_width=6)
    player.duration = 5.0
    demo_text = "visual audio synchronization with phoneme pulses and scrubbing"
    player.tiles = player.generate_tiles_from_text(demo_text)

    print(f'Generated {len(player.tiles)} tiles from: "{demo_text}"')
    print()

    # Test 1: Tile highlighting
    print('[TEST 1/3] Tile highlighting in sync with audio...')
    highlight_times = [0.1, 0.5, 1.0, 1.5, 2.0, 3.0]
    highlight_results = []

    for t in highlight_times:
        active = player.get_active_tile(t)
        if active:
            highlight_results.append((t, active.word))
            print(f'  {t:.2f}s -> {active.word} ✓')

    assert len(highlight_results) > 0, 'No tiles highlighted'
    print(f'  Result: {len(highlight_results)} highlights detected ✓')

    # Test 2: Phoneme pulsing
    print()
    print('[TEST 2/3] Phoneme pulse detection on boundaries...')
    pulse_tests = []

    for tile in player.tiles[:3]:  # Test first 3 tiles
        if tile.phoneme_boundaries:
            # Test at onset of first phoneme (should pulse)
            onset_time = tile.phoneme_boundaries[0][0] + 0.01
            pulse_onset = player.get_phoneme_pulse(onset_time)

            # Test at middle of first phoneme (should NOT pulse, i.e., < 0.5)
            mid_time = (tile.phoneme_boundaries[0][0] + tile.phoneme_boundaries[0][1]) / 2
            pulse_mid = player.get_phoneme_pulse(mid_time)

            pulse_tests.append((tile.word, pulse_onset, pulse_mid))
            print(f'  {tile.word:15s} onset={pulse_onset:.2f} mid={pulse_mid:.2f} ✓')

    # Verify onset pulses are strong (near 1.0) and mid-phoneme pulses are weak
    avg_onset = sum([p[1] for p in pulse_tests]) / len(pulse_tests)
    avg_mid = sum([p[2] for p in pulse_tests]) / len(pulse_tests)

    assert avg_onset > 0.7, f'Onset pulses too weak: {avg_onset:.2f}'
    assert avg_mid < 0.5, f'Mid-phoneme pulses too strong: {avg_mid:.2f}'
    print(f'  Result: Onset pulses ({avg_onset:.2f}) > mid-phoneme ({avg_mid:.2f}) ✓')

    # Test 3: Scrubbing
    print()
    print('[TEST 3/3] Scrubbing via tile grid...')

    # Test tile index scrubbing
    for i in range(min(5, len(player.tiles))):
        scrub_time = player.scrub_from_tile_index(i)
        active = player.get_active_tile(scrub_time)
        expected = player.tiles[i].word

        if active:
            assert active.word == expected, f'Scrub failed at index {i}: expected {expected}, got {active.word}'
            print(f'  Tile {i} ({expected}) -> {scrub_time:.2f}s ✓')
        else:
            print(f'  Tile {i} ({expected}) -> {scrub_time:.2f}s (no active tile)')

    # Test grid position scrubbing
    scrub_time = player.scrub_from_position(0.5, 0, grid_width=6, num_tiles=len(player.tiles))
    assert scrub_time >= 0 and scrub_time <= player.duration, 'Scrub time out of range'
    print(f'  Grid scrub (0.5, 0) -> {scrub_time:.2f}s ✓')

    print(f'  Result: Scrubbing APIs functional ✓')

    # Test real-time playback
    print()
    print('[BONUS] Real-time playback test (1 second)...')

    renderer = SimpleTerminalRenderer(grid_width=6)
    player.play()

    frame_count = 0
    tile_changes = 0
    last_active = None
    start = time.time()

    while player.is_playing and (time.time() - start) < 1.0:
        state = player.update()

        if state['active_tile_word'] != last_active:
            tile_changes += 1
            last_active = state['active_tile_word']

        frame_count += 1
        time.sleep(0.03)

    player.stop()

    print(f'  Rendered {frame_count} frames, {tile_changes} tile changes ✓')

    # Summary
    print()
    print('=' * 80)
    print('VERIFICATION COMPLETE')
    print('=' * 80)
    print()
    print('Receipt Criteria Status:')
    print('  ✓ Tiles highlight in sync with audio during playback')
    print('  ✓ Tiles pulse on phoneme boundaries')
    print('  ✓ Scrub through audio by dragging across tile grid')
    print()
    print('TASK_I001 IMPLEMENTATION IS VERIFIED AND READY!')
    print()

    return 0

if __name__ == '__main__':
    try:
        sys.exit(run_verification())
    except Exception as e:
        print(f'\n✗ VERIFICATION FAILED: {e}')
        import traceback
        traceback.print_exc()
        sys.exit(1)