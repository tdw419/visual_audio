#!/usr/bin/env python3
"""
Integration test for Phase 3.1: UPIC-Inspired Drawing Interface.

Tests the complete workflow from project creation to audio synthesis,
including CLI interface and core engine integration.
"""

import sys
import os
import subprocess
import tempfile
import json
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from upic_engine import (
    UPICWaveformTable, UPICEnvelope, UPICVoice, UPICProject
)
import soundfile as sf


def test_cli_create_project():
    """Test creating a project via CLI."""
    print("\n" + "="*60)
    print("TEST 1: CLI Project Creation")
    print("="*60)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        output_file = os.path.join(tmpdir, "test_project.upic.json")
        
        result = subprocess.run([
            'python3', 'upic.py',
            'create-project', 'test_cli_project',
            '--output', output_file
        ], capture_output=True, text=True, cwd=os.path.dirname(__file__))
        
        print("STDOUT:", result.stdout)
        if result.stderr:
            print("STDERR:", result.stderr)
        
        assert result.returncode == 0, "Project creation failed"
        assert os.path.exists(output_file), "Project file not created"
        
        # Verify project structure
        with open(output_file, 'r') as f:
            data = json.load(f)
        
        assert data['name'] == 'test_cli_project'
        assert len(data['wavetables']) == 4  # Basic wavetables
        assert len(data['envelopes']) == 4  # Basic envelopes
        assert len(data['voices']) == 0
        
        print("✅ CLI project creation test passed")


def test_cli_add_voice():
    """Test adding voices via CLI."""
    print("\n" + "="*60)
    print("TEST 2: CLI Voice Addition")
    print("="*60)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        project_file = os.path.join(tmpdir, "test_project.upic.json")
        
        # First create project
        subprocess.run([
            'python3', 'upic.py',
            'create-project', 'test_project',
            '--output', project_file
        ], capture_output=True, text=True, cwd=os.path.dirname(__file__))
        
        # Add voice
        result = subprocess.run([
            'python3', 'upic.py',
            'add-voice', project_file,
            'test_voice',
            '--wavetable', 'sine',
            '--frequency', '330.0',
            '--amplitude', '0.4',
            '--amp-envelope', 'ADSR'
        ], capture_output=True, text=True, cwd=os.path.dirname(__file__))
        
        print("STDOUT:", result.stdout)
        if result.stderr:
            print("STDERR:", result.stderr)
        
        assert result.returncode == 0, "Voice addition failed"
        
        # Verify voice was added
        with open(project_file, 'r') as f:
            data = json.load(f)
        
        assert len(data['voices']) == 1
        assert data['voices'][0]['name'] == 'test_voice'
        assert data['voices'][0]['base_frequency'] == 330.0
        assert data['voices'][0]['amplitude_envelope'] is not None
        
        print("✅ CLI voice addition test passed")


def test_cli_add_envelope():
    """Test adding custom envelopes via CLI."""
    print("\n" + "="*60)
    print("TEST 3: CLI Custom Envelope")
    print("="*60)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        project_file = os.path.join(tmpdir, "test_project.upic.json")
        
        # Create project
        subprocess.run([
            'python3', 'upic.py',
            'create-project', 'test_project',
            '--output', project_file
        ], capture_output=True, text=True, cwd=os.path.dirname(__file__))
        
        # Add custom envelope
        result = subprocess.run([
            'python3', 'upic.py',
            'add-envelope', project_file,
            'custom_fade',
            '--points', '0.0:0.0', '0.3:0.8', '1.0:0.2'
        ], capture_output=True, text=True, cwd=os.path.dirname(__file__))
        
        print("STDOUT:", result.stdout)
        if result.stderr:
            print("STDERR:", result.stderr)
        
        assert result.returncode == 0, "Envelope addition failed"
        
        # Verify envelope was added
        with open(project_file, 'r') as f:
            data = json.load(f)
        
        assert 'custom_fade' in data['envelopes']
        assert len(data['envelopes']['custom_fade']['control_points']) == 3
        
        print("✅ CLI custom envelope test passed")


def test_cli_synthesize():
    """Test audio synthesis via CLI."""
    print("\n" + "="*60)
    print("TEST 4: CLI Audio Synthesis")
    print("="*60)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        project_file = os.path.join(tmpdir, "test_project.upic.json")
        output_wav = os.path.join(tmpdir, "test_output.wav")
        
        # Create demo project
        subprocess.run([
            'python3', 'upic.py',
            'demo',
            '--output', project_file
        ], capture_output=True, text=True, cwd=os.path.dirname(__file__))
        
        # Synthesize
        result = subprocess.run([
            'python3', 'upic.py',
            'synthesize', project_file,
            output_wav,
            '--duration', '3.0'
        ], capture_output=True, text=True, cwd=os.path.dirname(__file__))
        
        print("STDOUT:", result.stdout)
        if result.stderr:
            print("STDERR:", result.stderr)
        
        assert result.returncode == 0, "Synthesis failed"
        assert os.path.exists(output_wav), "WAV file not created"
        
        # Verify audio properties
        audio, sr = sf.read(output_wav)
        assert len(audio) == 3 * 44100  # 3 seconds at 44.1kHz
        assert sr == 44100
        assert np.max(np.abs(audio)) > 0.01  # Should have audio content
        assert np.max(np.abs(audio)) <= 0.95  # Should be normalized
        
        print("✅ CLI audio synthesis test passed")


def test_cli_list():
    """Test project listing via CLI."""
    print("\n" + "="*60)
    print("TEST 5: CLI Project Listing")
    print("="*60)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        project_file = os.path.join(tmpdir, "test_project.upic.json")
        
        # Create demo project
        subprocess.run([
            'python3', 'upic.py',
            'demo',
            '--output', project_file
        ], capture_output=True, text=True, cwd=os.path.dirname(__file__))
        
        # List project
        result = subprocess.run([
            'python3', 'upic.py',
            'list', project_file
        ], capture_output=True, text=True, cwd=os.path.dirname(__file__))
        
        print("STDOUT:", result.stdout)
        if result.stderr:
            print("STDERR:", result.stderr)
        
        assert result.returncode == 0, "List command failed"
        assert "demo_project" in result.stdout
        assert "Wavetables (4):" in result.stdout
        assert "Envelopes (4):" in result.stdout
        assert "Voices (3):" in result.stdout
        
        print("✅ CLI project listing test passed")


def test_module_integration():
    """Test direct module integration."""
    print("\n" + "="*60)
    print("TEST 6: Direct Module Integration")
    print("="*60)
    
    # Create project programmatically
    project = UPICProject("test_module_project")
    project.create_basic_wavetables()
    project.create_basic_envelopes()
    
    # Add voice with envelopes
    voice = UPICVoice("test_voice", project.wavetables["sine"])
    voice.base_frequency = 220.0
    voice.base_amplitude = 0.5
    voice.set_amplitude_envelope(project.envelopes["ADSR"])
    voice.set_frequency_envelope(project.envelopes["LFO_sine"])
    project.add_voice(voice)
    
    # Synthesize
    audio = project.synthesize(duration=2.0, sample_rate=44100)
    
    assert len(audio) == 2 * 44100
    assert np.max(np.abs(audio)) > 0.01
    assert np.max(np.abs(audio)) <= 0.95
    assert np.isfinite(audio).all()
    
    print(f"Generated audio: {len(audio)} samples")
    print(f"Peak amplitude: {np.max(np.abs(audio)):.3f}")
    
    # Test save/load
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        temp_file = f.name
    
    try:
        project.save_project(temp_file)
        loaded_project = UPICProject.load_project(temp_file)
        
        assert loaded_project.name == project.name
        assert len(loaded_project.voices) == len(project.voices)
        assert loaded_project.voices[0].name == project.voices[0].name
        
        print("✅ Direct module integration test passed")
        
    finally:
        os.unlink(temp_file)


def test_complex_synthesis():
    """Test complex multi-voice synthesis."""
    print("\n" + "="*60)
    print("TEST 7: Complex Multi-Voice Synthesis")
    print("="*60)
    
    project = UPICProject("complex_test")
    project.create_basic_wavetables()
    project.create_basic_envelopes()
    
    # Create custom envelope
    custom_env = UPICEnvelope("custom_sweep", [
        (0.0, 0.5),
        (0.3, 1.5),
        (0.7, 0.8),
        (1.0, 0.5)
    ])
    project.add_envelope(custom_env)
    
    # Add multiple voices
    voices_config = [
        ("bass", "sawtooth", 110.0, 0.4, "ADSR", None),
        ("mid", "triangle", 220.0, 0.3, "ramp_down", "LFO_sine"),
        ("high", "sine", 440.0, 0.2, "ramp_up", "custom_sweep"),
    ]
    
    for name, wavetable, freq, amp, amp_env, freq_env in voices_config:
        voice = UPICVoice(name, project.wavetables[wavetable])
        voice.base_frequency = freq
        voice.base_amplitude = amp
        voice.set_amplitude_envelope(project.envelopes[amp_env])
        if freq_env:
            if freq_env in project.envelopes:
                voice.set_frequency_envelope(project.envelopes[freq_env])
            else:
                voice.set_frequency_envelope(custom_env)
        project.add_voice(voice)
    
    # Synthesize
    audio = project.synthesize(duration=3.0, sample_rate=48000)
    
    assert len(audio) == 3 * 48000
    assert np.max(np.abs(audio)) > 0.01
    assert np.max(np.abs(audio)) <= 0.95
    assert np.isfinite(audio).all()
    
    print(f"Complex synthesis: {len(audio)} samples @ 48kHz")
    print(f"Voices: {len(project.voices)}")
    print(f"Peak amplitude: {np.max(np.abs(audio)):.3f}")
    
    # Export
    with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f:
        temp_file = f.name
    
    try:
        project.export_wav(temp_file, duration=3.0, sample_rate=48000)
        assert os.path.exists(temp_file)
        
        # Verify exported file
        exported_audio, sr = sf.read(temp_file)
        assert len(exported_audio) == 3 * 48000
        assert sr == 48000
        
        print("✅ Complex multi-voice synthesis test passed")
        
    finally:
        os.unlink(temp_file)


def main():
    """Run all integration tests."""
    print("\n" + "="*70)
    print("PHASE 3.1 UPIC-INSPIRED DRAWING INTERFACE INTEGRATION TEST SUITE")
    print("="*70)
    
    try:
        test_cli_create_project()
        test_cli_add_voice()
        test_cli_add_envelope()
        test_cli_synthesize()
        test_cli_list()
        test_module_integration()
        test_complex_synthesis()
        
        print("\n" + "="*70)
        print("✅ ALL UPIC INTEGRATION TESTS PASSED!")
        print("="*70)
        
        print("\nPhase 3.1 Integration Testing Complete:")
        print("  • CLI project creation: ✅ Working")
        print("  • CLI voice addition: ✅ Working")
        print("  • CLI custom envelopes: ✅ Working")
        print("  • CLI audio synthesis: ✅ Working")
        print("  • CLI project listing: ✅ Working")
        print("  • Direct module integration: ✅ Working")
        print("  • Complex multi-voice synthesis: ✅ Working")
        
        return 0
        
    except Exception as e:
        print(f"\n❌ INTEGRATION TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    exit(main())