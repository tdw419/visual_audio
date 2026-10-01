#!/usr/bin/env python3
"""
Integration test for Phase 3.3: Variophone Emulator.

Tests the complete workflow from cog configuration to audio output,
including polyphonic synthesis and film strip simulation.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

import numpy as np
import subprocess
import tempfile
from PIL import Image


def test_cli_basic_polyphonic():
    """Test basic polyphonic Variophone synthesis."""
    print("\n" + "="*60)
    print("TEST 1: Basic Polyphonic Synthesis")
    print("="*60)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = os.path.join(tmpdir, "polyphonic.wav")
        
        result = subprocess.run([
            'python', 'variophone.py',
            output_path,
            '--cog', '3:440',
            '--cog', '4:880',
            '--cog', '5:1320',
            '--duration', '2.0',
            '--verbose'
        ], capture_output=True, text=True, cwd=os.path.dirname(__file__))
        
        print("STDOUT:", result.stdout)
        if result.stderr:
            print("STDERR:", result.stderr)
        
        assert result.returncode == 0, "Polyphonic synthesis failed"
        assert os.path.exists(output_path), "Output file not created"
        
        # Check file properties
        file_size = os.path.getsize(output_path)
        print(f"Output file size: {file_size} bytes")
        assert file_size > 1000, "Output file too small"
        
        # Verify audio properties in output
        assert "Duration: 2.000 seconds" in result.stdout
        assert "Cogs configured: 3" in result.stdout
        
        print("✅ Basic polyphonic synthesis test passed")


def test_cli_ring_modulation():
    """Test ring modulation synthesis."""
    print("\n" + "="*60)
    print("TEST 2: Ring Modulation Synthesis")
    print("="*60)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = os.path.join(tmpdir, "ring_mod.wav")
        
        result = subprocess.run([
            'python', 'variophone.py',
            output_path,
            '--cog', '3:440:1.0:0.8',
            '--cog', '5:880:0.5:0.6',
            '--mix-mode', 'ring_mod',
            '--duration', '2.0',
            '--verbose'
        ], capture_output=True, text=True, cwd=os.path.dirname(__file__))
        
        print("STDOUT:", result.stdout)
        if result.stderr:
            print("STDERR:", result.stderr)
        
        assert result.returncode == 0, "Ring modulation failed"
        assert os.path.exists(output_path), "Ring mod output not created"
        assert "Mix mode: ring_mod" in result.stdout
        
        print("✅ Ring modulation synthesis test passed")


def test_cli_fm_synthesis():
    """Test FM synthesis."""
    print("\n" + "="*60)
    print("TEST 3: FM Synthesis")
    print("="*60)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = os.path.join(tmpdir, "fm_synth.wav")
        
        result = subprocess.run([
            'python', 'variophone.py',
            output_path,
            '--cog', '3:440',
            '--cog', '5:100',
            '--mix-mode', 'fm',
            '--duration', '2.5',
            '--verbose'
        ], capture_output=True, text=True, cwd=os.path.dirname(__file__))
        
        print("STDOUT:", result.stdout)
        if result.stderr:
            print("STDERR:", result.stderr)
        
        assert result.returncode == 0, "FM synthesis failed"
        assert os.path.exists(output_path), "FM synthesis output not created"
        assert "Mix mode: fm" in result.stdout
        
        print("✅ FM synthesis test passed")


def test_film_strip_generation():
    """Test film strip visualization generation."""
    print("\n" + "="*60)
    print("TEST 4: Film Strip Visualization")
    print("="*60)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        output_wav = os.path.join(tmpdir, "audio.wav")
        film_strip_path = os.path.join(tmpdir, "film_strip.png")
        
        result = subprocess.run([
            'python', 'variophone.py',
            output_wav,
            '--cog', '3:440',
            '--cog', '4:880',
            '--film-strip', film_strip_path,
            '--duration', '2.0',
            '--verbose'
        ], capture_output=True, text=True, cwd=os.path.dirname(__file__))
        
        print("STDOUT:", result.stdout)
        if result.stderr:
            print("STDERR:", result.stderr)
        
        assert result.returncode == 0, "Film strip generation failed"
        assert os.path.exists(output_wav), "Audio output not created"
        assert os.path.exists(film_strip_path), "Film strip image not created"
        
        # Verify film strip image
        img = Image.open(film_strip_path)
        print(f"Film strip dimensions: {img.size}")
        
        # Should be grayscale (from film strip simulation)
        assert img.mode == 'L', f"Expected grayscale image, got {img.mode}"
        
        # Should have reasonable dimensions
        assert img.size[0] == 512, f"Expected width 512, got {img.size[0]}"
        assert img.size[1] == 48, f"Expected height 48 (2s @ 24fps), got {img.size[1]}"
        
        print("✅ Film strip visualization test passed")


def test_module_direct_usage():
    """Test direct module usage."""
    print("\n" + "="*60)
    print("TEST 5: Direct Module Integration")
    print("="*60)
    
    from variophone_emulator import VariophoneEmulator, generate_variophone_waveform
    
    # Test with convenience function
    cogs_config = [
        (3, 440.0, 1.0, 0.8),
        (4, 880.0, 0.5, 0.6),
        (5, 1320.0, 1.0, 0.4)
    ]
    
    waveform = generate_variophone_waveform(cogs_config, duration=2.0)
    print(f"Generated waveform length: {len(waveform)} samples")
    
    assert len(waveform) == 2 * 44100, "Waveform length incorrect"
    assert np.isfinite(waveform).all(), "Waveform contains invalid values"
    assert np.abs(waveform).max() <= 0.95, "Waveform not normalized"
    
    # Test with emulator object
    emulator = VariophoneEmulator(sample_rate=48000)
    emulator.add_cog(3, 440.0, 1.0, 0.7)
    emulator.add_cog(4, 880.0, 0.5, 0.5)
    
    waveform = emulator.generate_polyphonic_waveform(duration=1.5, mix_mode='additive')
    print(f"Emulator waveform length: {len(waveform)} samples")
    
    assert len(waveform) == 1.5 * 48000, "Emulator waveform length incorrect"
    assert np.isfinite(waveform).all(), "Emulator waveform contains invalid values"
    
    # Test film strip simulation
    emulator.set_film_speed(24.0)
    film_strip = emulator.simulate_film_strip(frames=48, width=512)
    print(f"Film strip shape: {film_strip.shape}")
    
    assert film_strip.shape == (48, 512), "Film strip dimensions incorrect"
    assert np.all(film_strip >= 0.0), "Film strip contains negative values"
    assert np.all(film_strip <= 1.0), "Film strip contains values > 1.0"
    
    # Test cog info
    info = emulator.get_cog_info()
    print(f"Cog info: {len(info)} cogs configured")
    
    assert len(info) == 2, "Cog info incorrect"
    assert info[0]['num_teeth'] == 3, "First cog info incorrect"
    assert info[1]['num_teeth'] == 4, "Second cog info incorrect"
    
    print("✅ Direct module integration test passed")


def test_audio_parameters():
    """Test different audio parameters."""
    print("\n" + "="*60)
    print("TEST 6: Different Audio Parameters")
    print("="*60)
    
    configs = [
        {'sample_rate': 44100, 'bit_depth': 16},
        {'sample_rate': 48000, 'bit_depth': 24},
        {'sample_rate': 96000, 'bit_depth': 32},
    ]
    
    with tempfile.TemporaryDirectory() as tmpdir:
        for config in configs:
            print(f"\nTesting SR={config['sample_rate']}, Depth={config['bit_depth']}")
            output_path = os.path.join(tmpdir, f"output_sr{config['sample_rate']}_depth{config['bit_depth']}.wav")
            
            result = subprocess.run([
                'python', 'variophone.py',
                output_path,
                '--cog', '3:440',
                '--sample-rate', str(config['sample_rate']),
                '--bit-depth', str(config['bit_depth']),
                '--duration', '1.0'
            ], capture_output=True, text=True, cwd=os.path.dirname(__file__))
            
            assert result.returncode == 0, f"Config {config} failed"
            assert os.path.exists(output_path), f"Config {config} output not created"
            
            # Verify output contains expected info
            assert f"Sample rate: {config['sample_rate']}" in result.stdout
            assert f"Bit depth: {config['bit_depth']}" in result.stdout
            
            print(f"  ✅ Config test passed")


def main():
    """Run all integration tests."""
    print("\n" + "="*70)
    print("PHASE 3.3 VARIOPHONE EMULATOR INTEGRATION TEST SUITE")
    print("="*70)
    
    try:
        test_cli_basic_polyphonic()
        test_cli_ring_modulation()
        test_cli_fm_synthesis()
        test_film_strip_generation()
        test_module_direct_usage()
        test_audio_parameters()
        
        print("\n" + "="*70)
        print("✅ ALL VARIOPHONE INTEGRATION TESTS PASSED!")
        print("="*70)
        
        print("\nPhase 3.3 Integration Testing Complete:")
        print("  • Polyphonic synthesis: ✅ Working")
        print("  • Ring modulation: ✅ Working")
        print("  • FM synthesis: ✅ Working")
        print("  • Film strip visualization: ✅ Working")
        print("  • Module integration: ✅ Working")
        print("  • Audio parameters: ✅ Working")
        
        return 0
        
    except Exception as e:
        print(f"\n❌ INTEGRATION TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    exit(main())