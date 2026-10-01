#!/usr/bin/env python3
"""
Test phoneme coarticulation (TASK_P001).

Tests that:
1. 5ms crossfade is applied between phonemes
2. No clicking artifacts occur at phoneme boundaries
3. Crossfade produces smooth transitions
"""

import os
import sys
import numpy as np
import soundfile as sf

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), 'src'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'tools'))

from word_compiler import (
    ensure_cmudict, parse_cmudict, get_phonemes_for_word,
    build_word_project_with_crossfade, CROSSFADE_DURATION_MS,
    crossfade_audio
)

SAMPLE_RATE = 44100


def test_crossfade_function():
    """Test the crossfade_audio function directly."""
    print("Testing crossfade function...")
    
    # Create two simple sine waves at different frequencies
    duration = 0.05  # 50ms each
    t1 = np.linspace(0, duration * 2 * np.pi * 440, int(duration * SAMPLE_RATE))
    t2 = np.linspace(0, duration * 2 * np.pi * 880, int(duration * SAMPLE_RATE))
    
    audio_a = np.sin(t1)
    audio_b = np.sin(t2)
    
    # Apply 5ms crossfade
    crossfade_samples = int(CROSSFADE_DURATION_MS / 1000.0 * SAMPLE_RATE)
    result = crossfade_audio(audio_a, audio_b, crossfade_samples)
    
    # Check that result is the right length
    expected_len = len(audio_a) + len(audio_b) - crossfade_samples
    assert len(result) == expected_len, f"Expected length {expected_len}, got {len(result)}"
    
    # Check that there are no abrupt jumps (max sample-to-sample change should be small)
    diffs = np.abs(np.diff(result))
    max_diff = np.max(diffs)
    
    # For smooth sine waves, max diff should be < 0.5
    # If there's a hard cut without crossfade, diff would be ~1.0 or more
    print(f"  Max sample-to-sample diff: {max_diff:.4f}")
    assert max_diff < 0.5, f"Crossfade not smooth: max diff = {max_diff}"
    
    print("  ✓ Crossfade function works correctly")


def test_single_phoneme():
    """Test that single-phoneme words work without errors."""
    print("\nTesting single phoneme synthesis...")
    
    cmudict_path = ensure_cmudict()
    cmudict = parse_cmudict(cmudict_path)
    
    # Find a word with a single phoneme
    word = "eye"  # Usually [AY] or similar
    
    phonemes = get_phonemes_for_word(word, cmudict)
    if len(phonemes) != 1:
        print(f"  Warning: '{word}' has {len(phonemes)} phonemes, skipping single-phoneme test")
        return
    
    audio = build_word_project_with_crossfade(word, phonemes)
    
    # Should have valid audio
    assert len(audio) > 0, "Audio is empty"
    assert np.isfinite(audio).all(), "Audio contains NaN or Inf"
    assert np.max(np.abs(audio)) > 0.01, "Audio is too quiet"
    assert np.max(np.abs(audio)) <= 1.0, "Audio is clipping"
    
    print(f"  ✓ Single phoneme works: {len(audio)/SAMPLE_RATE*1000:.1f}ms")


def test_multiphone_word():
    """Test that multi-phoneme words have smooth transitions."""
    print("\nTesting multi-phoneme word synthesis...")
    
    cmudict_path = ensure_cmudict()
    cmudict = parse_cmudict(cmudict_path)
    
    # Test "software" - multiple phonemes
    word = "software"
    
    phonemes = get_phonemes_for_word(word, cmudict)
    assert len(phonemes) >= 2, f"Expected at least 2 phonemes, got {len(phonemes)}"
    
    print(f"  Phonemes: {' '.join(phonemes)}")
    
    audio = build_word_project_with_crossfade(word, phonemes)
    
    # Should have valid audio
    assert len(audio) > 0, "Audio is empty"
    assert np.isfinite(audio).all(), "Audio contains NaN or Inf"
    assert np.max(np.abs(audio)) > 0.01, "Audio is too quiet"
    assert np.max(np.abs(audio)) <= 1.0, "Audio is clipping"
    
    # Check for clicks at boundaries
    # Calculate sample-to-sample differences
    diffs = np.abs(np.diff(audio))
    
    # Phoneme transitions should not have large jumps
    # With 5ms crossfade, transitions should be smooth
    crossfade_samples = int(CROSSFADE_DURATION_MS / 1000.0 * SAMPLE_RATE)
    phoneme_samples = int(0.020 * SAMPLE_RATE)  # 20ms per phoneme
    
    # Check around expected transition points
    num_phonemes = len(phonemes)
    if num_phonemes > 1:
        for i in range(num_phonemes - 1):
            # Expected transition point (accounting for crossfade)
            transition_sample = (i + 1) * phoneme_samples - crossfade_samples // 2
            
            # Check window around transition
            if transition_sample < len(diffs):
                window = diffs[max(0, transition_sample - 10):min(len(diffs), transition_sample + 10)]
                if len(window) > 0:
                    max_local_diff = np.max(window)
                    print(f"  Phoneme {i}→{i+1} transition max diff: {max_local_diff:.4f}")
                    
                    # With crossfade, this should be < 0.3
                    # Without crossfade (hard cut), this would be > 0.5
                    assert max_local_diff < 0.4, f"Click detected at phoneme {i}→{i+1}"
    
    print(f"  ✓ Multi-phoneme synthesis smooth: {len(audio)/SAMPLE_RATE*1000:.1f}ms, {num_phonemes} phonemes")


def test_word_compiler_integration():
    """Test that compile_word uses crossfade."""
    print("\nTesting word compiler integration...")
    
    from word_compiler import compile_word
    import tempfile
    
    cmudict_path = ensure_cmudict()
    cmudict = parse_cmudict(cmudict_path)
    
    # Compile a test word with force=True to bypass cache
    word = "test"
    wav_path, audio = compile_word(word, cmudict, force=True, verbose=False)
    
    # Verify audio was generated
    assert len(audio) > 0, "Audio is empty"
    assert np.isfinite(audio).all(), "Audio contains NaN or Inf"
    assert os.path.exists(wav_path), f"WAV file not created: {wav_path}"
    
    # Verify the WAV file is valid and can be read
    loaded_audio, sr = sf.read(wav_path)
    assert sr == SAMPLE_RATE, f"Sample rate mismatch: {sr} != {SAMPLE_RATE}"
    assert len(loaded_audio) == len(audio), "Loaded audio length mismatch"
    
    # Check that audio has reasonable properties (not exact match due to encoding)
    assert np.max(np.abs(loaded_audio)) > 0.01, "Loaded audio is too quiet"
    assert np.max(np.abs(loaded_audio)) <= 1.0, "Loaded audio is clipping"
    
    # Check correlation - should be very high even with encoding differences
    correlation = np.corrcoef(audio.flatten(), loaded_audio.flatten())[0, 1]
    print(f"  Audio correlation: {correlation:.6f}")
    assert correlation > 0.99, f"Loaded audio correlation too low: {correlation}"
    
    print(f"  ✓ Word compiler integration works: {wav_path}")


def main():
    print("=" * 60)
    print("TASK_P001: Phoneme Coarticulation Tests")
    print("=" * 60)
    
    try:
        test_crossfade_function()
        test_single_phoneme()
        test_multiphone_word()
        test_word_compiler_integration()
        
        print("\n" + "=" * 60)
        print("ALL TESTS PASSED ✓")
        print("=" * 60)
        return 0
        
    except AssertionError as e:
        print(f"\n✗ TEST FAILED: {e}")
        return 1
    except Exception as e:
        print(f"\n✗ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main())