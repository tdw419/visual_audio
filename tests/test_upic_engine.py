"""
Unit tests for UPIC Engine.
"""

import pytest
import numpy as np
import json
import tempfile
import os

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from upic_engine import (
    UPICWaveformTable, UPICEnvelope, UPICVoice, UPICProject,
    create_basic_waveform, create_custom_wavetable
)


class TestUPICWaveformTable:
    """Test UPICWaveformTable functionality."""
    
    def test_create_sine_wavetable(self):
        """Test creating a sine wave wavetable."""
        t = np.linspace(0, 2 * np.pi, 1024, endpoint=False)
        samples = np.sin(t)
        wavetable = UPICWaveformTable("sine_test", samples, 44100.0)
        
        assert wavetable.name == "sine_test"
        assert wavetable.length == 1024
        assert wavetable.sample_rate == 44100.0
        assert len(wavetable.samples) == 1024
    
    def test_get_interpolated_sample(self):
        """Test wavetable sample interpolation."""
        t = np.linspace(0, 2 * np.pi, 100, endpoint=False)
        samples = np.sin(t)
        wavetable = UPICWaveformTable("sine", samples, 44100.0)
        
        # Test at various phases
        sample_0 = wavetable.get_interpolated_sample(0.0)
        sample_25 = wavetable.get_interpolated_sample(0.25)
        sample_50 = wavetable.get_interpolated_sample(0.5)
        sample_75 = wavetable.get_interpolated_sample(0.75)
        
        # Sine wave should have specific values at these phases
        # Note: With only 100 samples, values won't be exact
        assert abs(sample_0) < 0.1  # sin(0) ≈ 0
        assert sample_25 > 0.8  # sin(pi/2) ≈ 1
        assert abs(sample_50) < 0.1  # sin(pi) ≈ 0
        assert sample_75 < -0.8  # sin(3pi/2) ≈ -1
    
    def test_phase_wrapping(self):
        """Test that phase wraps correctly around 0.0 and 1.0."""
        samples = np.sin(np.linspace(0, 2 * np.pi, 100, endpoint=False))
        wavetable = UPICWaveformTable("sine", samples, 44100.0)
        
        # These should give similar values
        sample_negative = wavetable.get_interpolated_sample(-0.1)
        sample_wrapped = wavetable.get_interpolated_sample(0.9)
        
        assert abs(sample_negative - sample_wrapped) < 0.1
    
    def test_serialization(self):
        """Test wavetable serialization to dict and back."""
        samples = np.sin(np.linspace(0, 2 * np.pi, 100, endpoint=False))
        wavetable1 = UPICWaveformTable("test", samples, 48000.0)
        
        # Serialize
        data = wavetable1.to_dict()
        
        # Deserialize
        wavetable2 = UPICWaveformTable.from_dict(data)
        
        assert wavetable2.name == wavetable1.name
        assert wavetable2.sample_rate == wavetable1.sample_rate
        assert wavetable2.length == wavetable1.length
        np.testing.assert_array_almost_equal(wavetable2.samples, wavetable1.samples)


class TestUPICEnvelope:
    """Test UPICEnvelope functionality."""
    
    def test_create_envelope(self):
        """Test creating an envelope from control points."""
        control_points = [(0.0, 0.0), (0.5, 1.0), (1.0, 0.0)]
        envelope = UPICEnvelope("test_env", control_points)
        
        assert envelope.name == "test_env"
        assert len(envelope.control_points) == 3
        assert envelope.control_points[0] == (0.0, 0.0)
    
    def test_envelope_evaluation(self):
        """Test envelope evaluation at various time points."""
        control_points = [(0.0, 0.0), (0.5, 1.0), (1.0, 0.0)]
        envelope = UPICEnvelope("ramp", control_points)
        
        # Test at key points
        value_0 = envelope.evaluate(0.0)
        value_05 = envelope.evaluate(0.5)
        value_1 = envelope.evaluate(1.0)
        value_025 = envelope.evaluate(0.25)
        
        assert value_0 == 0.0
        assert value_05 == 1.0
        assert value_1 == 0.0
        assert value_025 == 0.5  # Linear interpolation
    
    def test_envelope_clipping(self):
        """Test that envelope clips time values to [0, 1]."""
        control_points = [(0.0, 0.0), (1.0, 1.0)]
        envelope = UPICEnvelope("clip_test", control_points)
        
        # Test out-of-range values
        value_negative = envelope.evaluate(-0.5)
        value_over = envelope.evaluate(1.5)
        
        assert value_negative == 0.0
        assert value_over == 1.0
    
    def test_single_point_envelope(self):
        """Test envelope with single control point."""
        envelope = UPICEnvelope("single", [(0.0, 0.5)])
        
        assert envelope.evaluate(0.0) == 0.5
        assert envelope.evaluate(0.5) == 0.5
        assert envelope.evaluate(1.0) == 0.5
    
    def test_invalid_envelope(self):
        """Test that invalid envelopes raise errors."""
        # Empty envelope
        with pytest.raises(ValueError):
            UPICEnvelope("empty", [])
        
        # Out of range time
        with pytest.raises(ValueError):
            UPICEnvelope("invalid", [(2.0, 0.0)])


class TestUPICVoice:
    """Test UPICVoice functionality."""
    
    def test_create_voice(self):
        """Test creating a voice with wavetable."""
        samples = np.sin(np.linspace(0, 2 * np.pi, 100, endpoint=False))
        wavetable = UPICWaveformTable("sine", samples, 44100.0)
        voice = UPICVoice("test_voice", wavetable)
        
        assert voice.name == "test_voice"
        assert voice.wavetable.name == "sine"
        assert voice.base_frequency == 440.0
        assert voice.base_amplitude == 0.5
    
    def test_voice_synthesis(self):
        """Test basic voice synthesis."""
        samples = np.sin(np.linspace(0, 2 * np.pi, 100, endpoint=False))
        wavetable = UPICWaveformTable("sine", samples, 44100.0)
        voice = UPICVoice("test", wavetable)
        voice.base_frequency = 220.0  # Lower frequency
        
        audio = voice.synthesize(duration=1.0, sample_rate=44100)
        
        assert len(audio) == 44100
        assert np.max(np.abs(audio)) <= 0.5  # Should not exceed amplitude
        assert np.isfinite(audio).all()
    
    def test_voice_with_amplitude_envelope(self):
        """Test voice with amplitude envelope."""
        samples = np.sin(np.linspace(0, 2 * np.pi, 100, endpoint=False))
        wavetable = UPICWaveformTable("sine", samples, 44100.0)
        voice = UPICVoice("test", wavetable)
        
        # Add amplitude envelope (fade in)
        amp_env = UPICEnvelope("fade_in", [(0.0, 0.0), (1.0, 1.0)])
        voice.set_amplitude_envelope(amp_env)
        
        audio = voice.synthesize(duration=1.0, sample_rate=44100)
        
        # Check that audio starts quiet and gets louder
        first_quarter = np.abs(audio[:11025]).mean()
        last_quarter = np.abs(audio[-11025:]).mean()
        
        assert last_quarter > first_quarter * 2  # Should be significantly louder
    
    def test_voice_with_frequency_envelope(self):
        """Test voice with frequency envelope."""
        samples = np.sin(np.linspace(0, 2 * np.pi, 100, endpoint=False))
        wavetable = UPICWaveformTable("sine", samples, 44100.0)
        voice = UPICVoice("test", wavetable)
        
        # Add frequency envelope (frequency sweep)
        freq_env = UPICEnvelope("sweep", [(0.0, 0.5), (1.0, 2.0)])  # 0.5x to 2.0x
        voice.set_frequency_envelope(freq_env)
        
        audio = voice.synthesize(duration=1.0, sample_rate=44100)
        
        assert len(audio) == 44100
        assert np.isfinite(audio).all()
    
    def test_voice_serialization(self):
        """Test voice serialization."""
        samples = np.sin(np.linspace(0, 2 * np.pi, 100, endpoint=False))
        wavetable = UPICWaveformTable("sine", samples, 44100.0)
        voice1 = UPICVoice("test", wavetable)
        voice1.base_frequency = 330.0
        
        # Serialize
        data = voice1.to_dict()
        
        # Deserialize
        voice2 = UPICVoice.from_dict(data)
        
        assert voice2.name == voice1.name
        assert voice2.base_frequency == voice1.base_frequency
        assert voice2.base_amplitude == voice1.base_amplitude


class TestUPICProject:
    """Test UPICProject functionality."""
    
    def test_create_project(self):
        """Test creating a project."""
        project = UPICProject("test_project")
        
        assert project.name == "test_project"
        assert len(project.wavetables) == 0
        assert len(project.envelopes) == 0
        assert len(project.voices) == 0
    
    def test_add_wavetable(self):
        """Test adding wavetables to project."""
        project = UPICProject("test")
        samples = np.sin(np.linspace(0, 2 * np.pi, 100, endpoint=False))
        wavetable = UPICWaveformTable("sine", samples, 44100.0)
        
        project.add_wavetable(wavetable)
        
        assert "sine" in project.wavetables
        assert len(project.wavetables) == 1
    
    def test_add_envelope(self):
        """Test adding envelopes to project."""
        project = UPICProject("test")
        envelope = UPICEnvelope("test_env", [(0.0, 0.0), (1.0, 1.0)])
        
        project.add_envelope(envelope)
        
        assert "test_env" in project.envelopes
        assert len(project.envelopes) == 1
    
    def test_add_voice(self):
        """Test adding voices to project."""
        project = UPICProject("test")
        samples = np.sin(np.linspace(0, 2 * np.pi, 100, endpoint=False))
        wavetable = UPICWaveformTable("sine", samples, 44100.0)
        voice = UPICVoice("test_voice", wavetable)
        
        project.add_voice(voice)
        
        assert len(project.voices) == 1
        assert project.voices[0].name == "test_voice"
    
    def test_create_basic_wavetables(self):
        """Test creating standard wavetables."""
        project = UPICProject("test")
        project.create_basic_wavetables()
        
        assert "sine" in project.wavetables
        assert "triangle" in project.wavetables
        assert "square" in project.wavetables
        assert "sawtooth" in project.wavetables
        assert len(project.wavetables) == 4
    
    def test_create_basic_envelopes(self):
        """Test creating standard envelopes."""
        project = UPICProject("test")
        project.create_basic_envelopes()
        
        assert "ADSR" in project.envelopes
        assert "ramp_up" in project.envelopes
        assert "ramp_down" in project.envelopes
        assert "LFO_sine" in project.envelopes
        assert len(project.envelopes) == 4
    
    def test_project_synthesis_empty(self):
        """Test synthesis with no voices."""
        project = UPICProject("empty")
        audio = project.synthesize(duration=1.0, sample_rate=44100)
        
        assert len(audio) == 44100
        assert np.all(audio == 0.0)
    
    def test_project_synthesis_single_voice(self):
        """Test synthesis with single voice."""
        project = UPICProject("test")
        project.create_basic_wavetables()
        
        voice = UPICVoice("voice1", project.wavetables["sine"])
        voice.base_frequency = 440.0
        voice.base_amplitude = 0.5
        project.add_voice(voice)
        
        audio = project.synthesize(duration=1.0, sample_rate=44100)
        
        assert len(audio) == 44100
        assert np.max(np.abs(audio)) > 0.1  # Should have audio
        assert np.max(np.abs(audio)) <= 0.95  # Should be normalized
    
    def test_project_synthesis_multiple_voices(self):
        """Test synthesis with multiple voices."""
        project = UPICProject("test")
        project.create_basic_wavetables()
        
        # Add three voices
        for i, freq in enumerate([220.0, 440.0, 880.0]):
            voice = UPICVoice(f"voice{i}", project.wavetables["sine"])
            voice.base_frequency = freq
            voice.base_amplitude = 0.3
            project.add_voice(voice)
        
        audio = project.synthesize(duration=1.0, sample_rate=44100)
        
        assert len(audio) == 44100
        assert np.max(np.abs(audio)) > 0.1  # Should have audio
        assert np.max(np.abs(audio)) <= 0.95  # Should be normalized
    
    def test_project_save_load(self):
        """Test project save and load."""
        project1 = UPICProject("test")
        project1.create_basic_wavetables()
        project1.create_basic_envelopes()
        
        # Add a voice
        voice = UPICVoice("voice1", project1.wavetables["sine"])
        voice.base_frequency = 440.0
        project1.add_voice(voice)
        
        # Save and load
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            temp_file = f.name
        
        try:
            project1.save_project(temp_file)
            project2 = UPICProject.load_project(temp_file)
            
            assert project2.name == project1.name
            assert len(project2.wavetables) == len(project1.wavetables)
            assert len(project2.envelopes) == len(project1.envelopes)
            assert len(project2.voices) == len(project1.voices)
            
            # Check wavetable names match
            assert set(project2.wavetables.keys()) == set(project1.wavetables.keys())
            
            # Check envelope names match
            assert set(project2.envelopes.keys()) == set(project1.envelopes.keys())
            
            # Check voice properties
            assert project2.voices[0].name == project1.voices[0].name
            assert project2.voices[0].base_frequency == project1.voices[0].base_frequency
            
        finally:
            os.unlink(temp_file)
    
    def test_export_wav(self):
        """Test WAV export."""
        project = UPICProject("test")
        project.create_basic_wavetables()
        
        voice = UPICVoice("voice1", project.wavetables["sine"])
        voice.base_frequency = 440.0
        voice.base_amplitude = 0.5
        project.add_voice(voice)
        
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f:
            temp_file = f.name
        
        try:
            project.export_wav(temp_file, duration=1.0, sample_rate=44100)
            
            # Check file exists and has content
            assert os.path.exists(temp_file)
            assert os.path.getsize(temp_file) > 1000
            
            # Try to read it back
            import soundfile as sf
            audio, sr = sf.read(temp_file)
            
            assert len(audio) == 44100
            assert sr == 44100
            assert np.max(np.abs(audio)) > 0.1
            
        finally:
            os.unlink(temp_file)


class TestUtilityFunctions:
    """Test utility functions."""
    
    def test_create_basic_waveform(self):
        """Test basic waveform creation."""
        size = 100
        
        # Sine wave
        sine = create_basic_waveform("sine", size)
        assert len(sine) == size
        assert np.max(np.abs(sine)) <= 1.0
        
        # Triangle wave
        triangle = create_basic_waveform("triangle", size)
        assert len(triangle) == size
        
        # Square wave
        square = create_basic_waveform("square", size)
        assert len(square) == size
        assert np.unique(square).size == 2  # Should only have two values
        
        # Sawtooth wave
        sawtooth = create_basic_waveform("sawtooth", size)
        assert len(sawtooth) == size
    
    def test_create_basic_waveform_invalid(self):
        """Test invalid waveform type."""
        with pytest.raises(ValueError):
            create_basic_waveform("invalid")
    
    def test_create_custom_wavetable(self):
        """Test custom wavetable creation."""
        samples = np.random.randn(100)
        wavetable = create_custom_wavetable(samples, "custom")
        
        assert wavetable.name == "custom"
        assert wavetable.length == 100
        assert wavetable.sample_rate == 44100.0
        np.testing.assert_array_equal(wavetable.samples, samples)