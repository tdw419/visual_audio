#!/usr/bin/env python3
"""
Quick benchmark to verify vectorization speedup for TASK_S002.

Simulates encoding a ~2.5KB payload (the roadmap's performance target).
"""

import sys
import os
import time
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from upic_engine import UPICProject, UPICVoice, UPICEnvelope


def benchmark_realistic_payload():
    """
    Benchmark simulating ~2.5KB payload encoding.

    A 2.5KB text file at ~24 bytes/sec ≈ 100 seconds of audio.
    This means ~100 phonemes with complex envelopes.
    """
    print("=" * 60)
    print("TASK_S002 Vectorization Benchmark")
    print("=" * 60)
    print("\nSimulating 2.5KB payload encoding...")
    print("Target: <2s synthesis time (roadmap requirement)")
    print()

    # Create project
    project = UPICProject("benchmark")
    project.create_basic_wavetables()

    # Simulate ~100 phonemes with 5 control points each
    # This is roughly equivalent to a 2.5KB text file
    num_phonemes = 100
    envelope_points = []

    for i in range(num_phonemes):
        t_start = i / num_phonemes
        t_end = (i + 1) / num_phonemes
        # ADSR envelope for each phoneme
        envelope_points.extend([
            (t_start, 0.0),
            (t_start + (t_end - t_start) * 0.2, 1.0),
            (t_start + (t_end - t_start) * 0.4, 0.7),
            (t_start + (t_end - t_start) * 0.8, 0.7),
            (t_end, 0.0)
        ])

    # Create envelope
    envelope = UPICEnvelope("phonemes", envelope_points)

    # Create voice with frequency modulation for phoneme variety
    voice = UPICVoice("phoneme_voice", project.wavetables["sine"])
    voice.set_amplitude_envelope(envelope)
    voice.base_frequency = 440.0
    voice.base_amplitude = 0.5

    # Add frequency variation (simulating different phoneme pitches)
    freq_points = [(i/num_phonemes, 200 + (i % 10) * 40) for i in range(num_phonemes + 1)]
    freq_envelope = UPICEnvelope("freq", freq_points)
    voice.set_frequency_envelope(freq_envelope)

    # Synthesize (100 seconds of audio at ~24 bytes/sec = ~2.5KB)
    duration = 100.0
    sample_rate = 44100

    print(f"Workload:")
    print(f"  - Duration: {duration}s")
    print(f"  - Phonemes: {num_phonemes}")
    print(f"  - Control points: {len(envelope_points)}")
    print(f"  - Samples: {int(duration * sample_rate):,}")
    print()

    # Benchmark synthesis
    print("Synthesizing...")
    start = time.time()
    output = voice.synthesize(duration, sample_rate)
    elapsed = time.time() - start

    print(f"Results:")
    print(f"  - Synthesis time: {elapsed:.4f}s")
    print(f"  - Real-time factor: {duration/elapsed:.1f}x")
    print(f"  - Sample rate: {sample_rate} Hz")
    print()

    # Verify output
    assert len(output) == int(duration * sample_rate)
    assert np.all(np.isfinite(output))

    # Check against target
    print(f"Target Check:")
    if elapsed < 2.0:
        print(f"  ✓ PASS: {elapsed:.4f}s < 2.0s target")
    else:
        print(f"  ✗ FAIL: {elapsed:.4f}s > 2.0s target")

    print()
    print("=" * 60)

    return elapsed


if __name__ == '__main__':
    elapsed = benchmark_realistic_payload()

    # Exit with appropriate code
    sys.exit(0 if elapsed < 2.0 else 1)