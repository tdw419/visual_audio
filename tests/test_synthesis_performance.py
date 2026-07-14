"""
Performance Benchmark for TASK_S002

Verifies that vectorized upic_engine achieves target performance:
- 2.5KB payload encodes in <2s (target: ~1000x speedup from original)
- Tests with realistic phoneme sequence workload
"""

import pytest
import numpy as np
import time
import os

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from upic_engine import UPICWaveformTable, UPICEnvelope, UPICVoice, UPICProject


class TestSynthesisPerformance:
    """Test that vectorized synthesis meets performance targets."""
    
    def test_realistic_phoneme_workload(self):
        """
        Test realistic workload: ~100 phonemes with 5 envelope points each.
        
        Simulates the workload that was taking ~100s before vectorization.
        """
        # Create realistic phoneme envelope (similar to actual phoneme sequences)
        # Each phoneme has ADSR-like envelope with ~5 control points
        num_phonemes = 100
        envelope_points = []
        
        for i in range(num_phonemes):
            t_start = i / num_phonemes
            t_end = (i + 1) / num_phonemes
            # ADSR envelope for each phoneme segment
            envelope_points.extend([
                (t_start, 0.0),               # Attack start
                (t_start + (t_end - t_start) * 0.2, 1.0),  # Attack peak
                (t_start + (t_end - t_start) * 0.4, 0.7),  # Decay
                (t_start + (t_end - t_start) * 0.8, 0.7),  # Sustain
                (t_end, 0.0)                  # Release
            ])
        
        # Create wavetable
        samples = np.sin(np.linspace(0, 2 * np.pi, 2048, endpoint=False))
        wt = UPICWaveformTable("sine", samples)
        
        # Create envelope with realistic control point count
        envelope = UPICEnvelope("phoneme_envelope", envelope_points)
        
        # Create voice
        voice = UPICVoice("phoneme_voice", wt)
        voice.set_amplitude_envelope(envelope)
        voice.base_frequency = 440.0
        voice.base_amplitude = 0.5
        
        # Synthesize realistic duration (100 phonemes ~ 2-3 seconds of speech)
        duration = 2.5  # seconds
        sample_rate = 44100
        
        # Time synthesis
        start = time.time()
        output = voice.synthesize(duration, sample_rate)
        elapsed = time.time() - start
        
        print(f"\nRealistic Phoneme Workload:")
        print(f"  Phonemes: {num_phonemes}")
        print(f"  Envelope control points: {len(envelope_points)}")
        print(f"  Duration: {duration}s")
        print(f"  Samples: {len(output)}")
        print(f"  Synthesis time: {elapsed:.4f}s")
        
        # Verify output is valid
        assert len(output) == int(duration * sample_rate)
        assert np.all(np.isfinite(output))
        
        # Target: <2s for realistic workload ( roadmap requirement: 2.5KB in <2s)
        # This workload simulates ~2.5KB of phoneme data
        assert elapsed < 2.0, f"Synthesis time ({elapsed:.4f}s) exceeds target (2.0s)"
    
    def test_complex_multi_voice_workload(self):
        """Test complex multi-voice synthesis (chorus effect)."""
        # Create project with multiple voices
        project = UPICProject("chorus_test")
        project.create_basic_wavetables()
        project.create_basic_envelopes()
        
        # Add 4 voices for chorus effect
        for i in range(4):
            voice = UPICVoice(f"voice_{i}", project.wavetables["sine"])
            voice.set_amplitude_envelope(project.envelopes["ADSR"])
            voice.base_frequency = 440.0 * (1.0 + i * 0.01)  # Slightly detuned
            voice.base_amplitude = 0.2
            project.add_voice(voice)
        
        # Synthesize
        duration = 5.0
        sample_rate = 44100
        
        start = time.time()
        output = project.synthesize(duration, sample_rate)
        elapsed = time.time() - start
        
        print(f"\nMulti-Voice Chorus Workload:")
        print(f"  Voices: {len(project.voices)}")
        print(f"  Duration: {duration}s")
        print(f"  Samples: {len(output)}")
        print(f"  Synthesis time: {elapsed:.4f}s")
        
        # Verify output
        assert len(output) == int(duration * sample_rate)
        assert np.all(np.isfinite(output))
        
        # Should still be very fast even with multiple voices
        assert elapsed < 1.0, f"Multi-voice synthesis time ({elapsed:.4f}s) exceeds target (1.0s)"
    
    def test_long_duration_workload(self):
        """Test very long duration synthesis (real-time processing test)."""
        # Create simple voice
        samples = np.sin(np.linspace(0, 2 * np.pi, 2048, endpoint=False))
        wt = UPICWaveformTable("sine", samples)
        
        voice = UPICVoice("test_voice", wt)
        voice.base_frequency = 440.0
        voice.base_amplitude = 0.5
        
        # Synthesize 30 seconds of audio
        duration = 30.0
        sample_rate = 44100
        
        start = time.time()
        output = voice.synthesize(duration, sample_rate)
        elapsed = time.time() - start
        
        print(f"\nLong Duration Workload:")
        print(f"  Duration: {duration}s")
        print(f"  Samples: {len(output)}")
        print(f"  Synthesis time: {elapsed:.4f}s")
        print(f"  Real-time factor: {duration/elapsed:.1f}x")
        
        # Verify output
        assert len(output) == int(duration * sample_rate)
        assert np.all(np.isfinite(output))
        
        # For real-time processing, we need to synthesize faster than playback
        # Target: synthesis should be >10x faster than real-time
        real_time_factor = duration / elapsed
        assert real_time_factor > 10, f"Real-time factor ({real_time_factor:.1f}x) below target (10x)"
    
    def test_extreme_envelope_density(self):
        """Test with extremely dense envelopes (stress test)."""
        # Create envelope with 1000 control points
        envelope_points = [(i/999.0, np.sin(i/999.0 * 4 * np.pi) * 0.5 + 0.5) 
                          for i in range(1000)]
        
        # Create voice with complex envelope
        samples = np.sin(np.linspace(0, 2 * np.pi, 2048, endpoint=False))
        wt = UPICWaveformTable("sine", samples)
        
        envelope = UPICEnvelope("complex", envelope_points)
        
        voice = UPICVoice("complex_voice", wt)
        voice.set_amplitude_envelope(envelope)
        voice.set_frequency_envelope(envelope)  # Dual envelope for max complexity
        voice.base_frequency = 440.0
        voice.base_amplitude = 0.5
        
        # Synthesize
        duration = 5.0
        sample_rate = 44100
        
        start = time.time()
        output = voice.synthesize(duration, sample_rate)
        elapsed = time.time() - start
        
        print(f"\nExtreme Envelope Density Test:")
        print(f"  Envelope control points: {len(envelope_points)}")
        print(f"  Dual envelopes: freq + amp")
        print(f"  Duration: {duration}s")
        print(f"  Synthesis time: {elapsed:.4f}s")
        
        # Verify output
        assert len(output) == int(duration * sample_rate)
        assert np.all(np.isfinite(output))
        
        # Even with 1000 control points, should be fast
        assert elapsed < 2.0, f"Complex envelope synthesis time ({elapsed:.4f}s) exceeds target (2.0s)"


if __name__ == '__main__':
    # Run tests
    pytest.main([__file__, '-v', '-s'])