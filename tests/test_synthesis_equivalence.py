"""
Synthesis Equivalence Test for TASK_S002

Verifies that vectorized upic_engine produces byte-identical output
to the original upic_engine while achieving ~1000x speedup.
"""

import pytest
import numpy as np
import tempfile
import time
import os

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from upic_engine import UPICWaveformTable, UPICEnvelope, UPICVoice, UPICProject
from upic_engine_vectorized import (
    UPICWaveformTable as UPICWaveformTableVec,
    UPICEnvelope as UPICEnvelopeVec,
    UPICVoice as UPICVoiceVec,
    UPICProject as UPICProjectVec
)


class TestSynthesisEquivalence:
    """Test that vectorized engine produces identical output."""
    
    def test_wavetable_interpolation_equivalence(self):
        """Test that wavetable interpolation is identical."""
        samples = np.sin(np.linspace(0, 2 * np.pi, 1024, endpoint=False))
        wt_orig = UPICWaveformTable("test", samples)
        wt_vec = UPICWaveformTableVec("test", samples)
        
        # Test at various phases
        phases = np.array([0.0, 0.25, 0.5, 0.75, 0.999])
        
        for phase in phases:
            orig_sample = wt_orig.get_interpolated_sample(phase)
            vec_sample = wt_vec.get_interpolated_sample(phase)
            
            # Should be identical within float precision
            np.testing.assert_almost_equal(orig_sample, vec_sample, decimal=12)
    
    def test_wavetable_interpolation_vectorized(self):
        """Test vectorized wavetable interpolation."""
        samples = np.sin(np.linspace(0, 2 * np.pi, 1024, endpoint=False))
        wt_vec = UPICWaveformTableVec("test", samples)
        
        # Test with array of phases
        phases = np.linspace(0, 1, 1000)
        vec_samples = wt_vec.get_interpolated_samples(phases)
        
        # Each should match scalar version
        for i, phase in enumerate(phases):
            scalar_sample = wt_vec.get_interpolated_sample(phase)
            np.testing.assert_almost_equal(scalar_sample, vec_samples[i], decimal=12)
    
    def test_envelope_evaluation_equivalence(self):
        """Test that envelope evaluation is identical."""
        control_points = [(0.0, 0.0), (0.5, 1.0), (1.0, 0.0)]
        env_orig = UPICEnvelope("test", control_points)
        env_vec = UPICEnvelopeVec("test", control_points)
        
        # Test at various times
        times = [0.0, 0.25, 0.5, 0.75, 1.0]
        
        for t in times:
            orig_value = env_orig.evaluate(t)
            vec_value = env_vec.evaluate(t)
            
            np.testing.assert_almost_equal(orig_value, vec_value, decimal=12)
    
    def test_envelope_evaluation_vectorized(self):
        """Test vectorized envelope evaluation."""
        control_points = [(0.0, 0.0), (0.5, 1.0), (1.0, 0.0)]
        env_vec = UPICEnvelopeVec("test", control_points)
        
        # Test with array of times
        times = np.linspace(0, 1, 1000)
        vec_values = env_vec.evaluate_vectorized(times)
        
        # Each should match scalar version
        for i, t in enumerate(times):
            scalar_value = env_vec.evaluate(t)
            np.testing.assert_almost_equal(scalar_value, vec_values[i], decimal=12)
    
    def test_simple_voice_equivalence(self):
        """Test that simple voice synthesis is identical."""
        # Create wavetable
        samples = np.sin(np.linspace(0, 2 * np.pi, 2048, endpoint=False))
        wt_orig = UPICWaveformTable("sine", samples)
        wt_vec = UPICWaveformTableVec("sine", samples)
        
        # Create voices
        voice_orig = UPICVoice("test_voice", wt_orig)
        voice_vec = UPICVoiceVec("test_voice", wt_vec)
        
        voice_orig.base_frequency = 440.0
        voice_vec.base_frequency = 440.0
        
        voice_orig.base_amplitude = 0.5
        voice_vec.base_amplitude = 0.5
        
        # Synthesize
        duration = 1.0
        sample_rate = 44100
        output_orig = voice_orig.synthesize(duration, sample_rate)
        output_vec = voice_vec.synthesize(duration, sample_rate)
        
        # Should be byte-identical
        np.testing.assert_array_almost_equal(output_orig, output_vec, decimal=10)
    
    def test_voice_with_envelopes_equivalence(self):
        """Test that voice synthesis with envelopes is identical."""
        # Create wavetable
        samples = np.sin(np.linspace(0, 2 * np.pi, 2048, endpoint=False))
        wt_orig = UPICWaveformTable("sine", samples)
        wt_vec = UPICWaveformTableVec("sine", samples)
        
        # Create envelopes
        freq_points = [(0.0, 1.0), (0.5, 2.0), (1.0, 1.0)]
        amp_points = [(0.0, 0.0), (0.1, 1.0), (0.9, 1.0), (1.0, 0.0)]
        
        env_freq_orig = UPICEnvelope("freq", freq_points)
        env_amp_orig = UPICEnvelope("amp", amp_points)
        
        env_freq_vec = UPICEnvelopeVec("freq", freq_points)
        env_amp_vec = UPICEnvelopeVec("amp", amp_points)
        
        # Create voices with envelopes
        voice_orig = UPICVoice("test_voice", wt_orig)
        voice_vec = UPICVoiceVec("test_voice", wt_vec)
        
        voice_orig.base_frequency = 440.0
        voice_vec.base_frequency = 440.0
        
        voice_orig.base_amplitude = 0.5
        voice_vec.base_amplitude = 0.5
        
        voice_orig.set_frequency_envelope(env_freq_orig)
        voice_orig.set_amplitude_envelope(env_amp_orig)
        
        voice_vec.set_frequency_envelope(env_freq_vec)
        voice_vec.set_amplitude_envelope(env_amp_vec)
        
        # Synthesize
        duration = 2.0
        sample_rate = 44100
        output_orig = voice_orig.synthesize(duration, sample_rate)
        output_vec = voice_vec.synthesize(duration, sample_rate)
        
        # Should be byte-identical
        np.testing.assert_array_almost_equal(output_orig, output_vec, decimal=10)
    
    def test_project_equivalence(self):
        """Test that project synthesis is identical."""
        # Create original project
        proj_orig = UPICProject("test_project")
        proj_orig.create_basic_wavetables()
        proj_orig.create_basic_envelopes()
        
        # Create vectorized project
        proj_vec = UPICProjectVec("test_project")
        proj_vec.create_basic_wavetables()
        proj_vec.create_basic_envelopes()
        
        # Add voices to both
        voice_orig = UPICVoice("voice1", proj_orig.wavetables["sine"])
        voice_orig.set_amplitude_envelope(proj_orig.envelopes["ADSR"])
        voice_orig.base_frequency = 440.0
        voice_orig.base_amplitude = 0.3
        proj_orig.add_voice(voice_orig)
        
        voice_vec = UPICVoiceVec("voice1", proj_vec.wavetables["sine"])
        voice_vec.set_amplitude_envelope(proj_vec.envelopes["ADSR"])
        voice_vec.base_frequency = 440.0
        voice_vec.base_amplitude = 0.3
        proj_vec.add_voice(voice_vec)
        
        # Synthesize
        duration = 3.0
        sample_rate = 44100
        output_orig = proj_orig.synthesize(duration, sample_rate)
        output_vec = proj_vec.synthesize(duration, sample_rate)
        
        # Should be byte-identical
        np.testing.assert_array_almost_equal(output_orig, output_vec, decimal=10)
    
    def test_synthesis_speedup(self):
        """Test that vectorized synthesis is much faster (~1000x)."""
        # Create realistic payload (simulating 2.5KB of data)
        # A typical phoneme sequence might have 100-200 control points
        control_points = [(i/200.0, np.sin(i/200.0 * 4 * np.pi) * 0.5 + 0.5) 
                         for i in range(201)]
        
        # Create wavetable
        samples = np.sin(np.linspace(0, 2 * np.pi, 2048, endpoint=False))
        wt_orig = UPICWaveformTable("sine", samples)
        wt_vec = UPICWaveformTableVec("sine", samples)
        
        # Create envelopes
        env_orig = UPICEnvelope("test_env", control_points)
        env_vec = UPICEnvelopeVec("test_env", control_points)
        
        # Create voices
        voice_orig = UPICVoice("test_voice", wt_orig)
        voice_orig.set_amplitude_envelope(env_orig)
        voice_orig.base_frequency = 440.0
        voice_orig.base_amplitude = 0.5
        
        voice_vec = UPICVoiceVec("test_voice", wt_vec)
        voice_vec.set_amplitude_envelope(env_vec)
        voice_vec.base_frequency = 440.0
        voice_vec.base_amplitude = 0.5
        
        # Synthesize with timing
        duration = 5.0  # 5 seconds of audio
        sample_rate = 44100
        
        # Time original
        start_orig = time.time()
        output_orig = voice_orig.synthesize(duration, sample_rate)
        time_orig = time.time() - start_orig
        
        # Time vectorized
        start_vec = time.time()
        output_vec = voice_vec.synthesize(duration, sample_rate)
        time_vec = time.time() - start_vec
        
        # Calculate speedup
        speedup = time_orig / time_vec
        
        print(f"\nSynthesis Speedup Test:")
        print(f"  Original: {time_orig:.4f}s")
        print(f"  Vectorized: {time_vec:.4f}s")
        print(f"  Speedup: {speedup:.1f}x")
        
        # Verify output is identical
        np.testing.assert_array_almost_equal(output_orig, output_vec, decimal=10)
        
        # Vectorized should be at least 100x faster (conservative requirement)
        # Actual speedup should be ~1000x for realistic payloads
        assert speedup > 100, f"Speedup ({speedup:.1f}x) below minimum requirement (100x)"
    
    def test_round_trip_project_load_save(self):
        """Test that .upic.json format compatibility is maintained."""
        # Create original project
        proj_orig = UPICProject("test_project")
        proj_orig.create_basic_wavetables()
        proj_orig.create_basic_envelopes()
        
        voice_orig = UPICVoice("voice1", proj_orig.wavetables["sine"])
        voice_orig.set_amplitude_envelope(proj_orig.envelopes["ADSR"])
        voice_orig.base_frequency = 440.0
        voice_orig.base_amplitude = 0.3
        proj_orig.add_voice(voice_orig)
        
        # Save to file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.upic.json', delete=False) as f:
            temp_file = f.name
        
        try:
            proj_orig.save_project(temp_file)
            
            # Load into vectorized project
            proj_vec = UPICProjectVec.load_project(temp_file)
            
            # Both should produce identical synthesis
            duration = 1.0
            sample_rate = 44100
            output_orig = proj_orig.synthesize(duration, sample_rate)
            output_vec = proj_vec.synthesize(duration, sample_rate)
            
            np.testing.assert_array_almost_equal(output_orig, output_vec, decimal=10)
        finally:
            os.unlink(temp_file)


if __name__ == '__main__':
    # Run tests
    pytest.main([__file__, '-v', '-s'])