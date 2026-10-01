#!/usr/bin/env python3
"""
Comprehensive integration test for Phase 2 spectrogram to audio pipeline.
Tests the complete workflow from spectrogram image to WAV output.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

import numpy as np
from PIL import Image
import subprocess
import tempfile


def create_test_spectrogram_image(path):
    """Create a test spectrogram image for integration testing."""
    # Create a spectrogram with harmonic content
    height, width = 512, 1024
    rgb_data = np.zeros((height, width, 3), dtype=np.uint8)
    
    # Time-varying frequency content
    t = np.linspace(0, 1, width)
    
    # Red channel: Low frequency sweep (100-500 Hz)
    for i, time_val in enumerate(t):
        freq_bin = int(10 + time_val * 50)  # Sweep from 10 to 60
        rgb_data[max(0, freq_bin-2):min(height//3, freq_bin+3), i, 0] = 200
    
    # Green channel: Mid frequency harmonics (500-2000 Hz)  
    for i, time_val in enumerate(t):
        freq_bin = int(100 + time_val * 100)  # Sweep from 100 to 200
        rgb_data[height//3:max(2*height//3, freq_bin+5), i, 1] = 150
    
    # Blue channel: High frequency content (2000-10000 Hz)
    for i, time_val in enumerate(t):
        freq_bin = int(200 + time_val * 150)  # Sweep from 200 to 350
        rgb_data[2*height//3:min(height, freq_bin+8), i, 2] = 100
    
    # Add some noise for realism
    noise = np.random.randint(0, 30, rgb_data.shape, dtype=np.uint8)
    rgb_data = np.clip(rgb_data.astype(np.int16) + noise, 0, 255).astype(np.uint8)
    
    # Save image
    Image.fromarray(rgb_data).save(path)
    print(f"Created test spectrogram: {width}x{height} RGB")
    return path


def test_cli_basic_conversion():
    """Test basic CLI conversion."""
    print("\n" + "="*60)
    print("TEST 1: Basic Spectrogram to WAV Conversion")
    print("="*60)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create test spectrogram
        spec_path = os.path.join(tmpdir, "test_spectrogram.png")
        output_path = os.path.join(tmpdir, "output.wav")
        
        create_test_spectrogram_image(spec_path)
        
        # Run CLI
        result = subprocess.run([
            'python', 'spectrogram2wav.py',
            spec_path, output_path,
            '--iterations', '20',
            '--verbose'
        ], capture_output=True, text=True, cwd=os.path.dirname(__file__))
        
        print("STDOUT:", result.stdout)
        if result.stderr:
            print("STDERR:", result.stderr)
        
        # Check success
        assert result.returncode == 0, f"CLI failed with return code {result.returncode}"
        assert os.path.exists(output_path), "Output WAV file not created"
        
        # Check file properties
        file_size = os.path.getsize(output_path)
        print(f"Output file size: {file_size} bytes")
        assert file_size > 1000, "Output file too small"
        
        print("✅ Basic conversion test passed")


def test_cli_multi_band():
    """Test multi-band synthesis."""
    print("\n" + "="*60)
    print("TEST 2: Multi-Band Synthesis")
    print("="*60)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create test spectrogram
        spec_path = os.path.join(tmpdir, "test_spectrogram.png")
        output_path = os.path.join(tmpdir, "output_multiband.wav")
        
        create_test_spectrogram_image(spec_path)
        
        # Run CLI with multi-band
        result = subprocess.run([
            'python', 'spectrogram2wav.py',
            spec_path, output_path,
            '--iterations', '15',
            '--multi-band',
            '--verbose'
        ], capture_output=True, text=True, cwd=os.path.dirname(__file__))
        
        print("STDOUT:", result.stdout)
        if result.stderr:
            print("STDERR:", result.stderr)
        
        # Check success
        assert result.returncode == 0, f"Multi-band CLI failed with return code {result.returncode}"
        assert os.path.exists(output_path), "Multi-band output not created"
        
        print("✅ Multi-band synthesis test passed")


def test_cli_frequency_scales():
    """Test different frequency scales."""
    print("\n" + "="*60)
    print("TEST 3: Different Frequency Scales")
    print("="*60)
    
    scales = ['log', 'mel']
    
    with tempfile.TemporaryDirectory() as tmpdir:
        spec_path = os.path.join(tmpdir, "test_spectrogram.png")
        create_test_spectrogram_image(spec_path)
        
        for scale in scales:
            print(f"\nTesting {scale} frequency scale...")
            output_path = os.path.join(tmpdir, f"output_{scale}.wav")
            
            result = subprocess.run([
                'python', 'spectrogram2wav.py',
                spec_path, output_path,
                '--iterations', '10',
                '--frequency-scale', scale
            ], capture_output=True, text=True, cwd=os.path.dirname(__file__))
            
            assert result.returncode == 0, f"{scale} scale failed"
            assert os.path.exists(output_path), f"{scale} output not created"
            
            print(f"  ✅ {scale} scale test passed")


def test_cli_convergence():
    """Test convergence detection."""
    print("\n" + "="*60)
    print("TEST 4: Convergence Detection")
    print("="*60)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        spec_path = os.path.join(tmpdir, "test_spectrogram.png")
        output_path = os.path.join(tmpdir, "output_convergence.wav")
        
        create_test_spectrogram_image(spec_path)
        
        # Run CLI with convergence detection
        result = subprocess.run([
            'python', 'spectrogram2wav.py',
            spec_path, output_path,
            '--convergence',
            '--iterations', '50',
            '--verbose'
        ], capture_output=True, text=True, cwd=os.path.dirname(__file__))
        
        print("STDOUT:", result.stdout)
        if result.stderr:
            print("STDERR:", result.stderr)
        
        # Check success and convergence info
        assert result.returncode == 0, "Convergence test failed"
        assert "Converged:" in result.stdout, "Convergence info not shown"
        
        print("✅ Convergence detection test passed")


def test_cli_audio_parameters():
    """Test different audio parameters."""
    print("\n" + "="*60)
    print("TEST 5: Different Audio Parameters")
    print("="*60)
    
    configs = [
        {'sample_rate': 44100, 'bit_depth': 16},
        {'sample_rate': 48000, 'bit_depth': 24},
    ]
    
    with tempfile.TemporaryDirectory() as tmpdir:
        spec_path = os.path.join(tmpdir, "test_spectrogram.png")
        create_test_spectrogram_image(spec_path)
        
        for config in configs:
            print(f"\nTesting SR={config['sample_rate']}, Depth={config['bit_depth']}")
            output_path = os.path.join(tmpdir, f"output_sr{config['sample_rate']}_depth{config['bit_depth']}.wav")
            
            result = subprocess.run([
                'python', 'spectrogram2wav.py',
                spec_path, output_path,
                '--sample-rate', str(config['sample_rate']),
                '--bit-depth', str(config['bit_depth']),
                '--iterations', '10'
            ], capture_output=True, text=True, cwd=os.path.dirname(__file__))
            
            assert result.returncode == 0, f"Config {config} failed"
            assert os.path.exists(output_path), f"Config {config} output not created"
            
            # Verify output contains expected info
            assert f"Sample rate: {config['sample_rate']}" in result.stdout
            assert f"Bit depth: {config['bit_depth']}" in result.stdout
            
            print(f"  ✅ Config test passed")


def test_module_integration():
    """Test direct module integration."""
    print("\n" + "="*60)
    print("TEST 6: Direct Module Integration")
    print("="*60)
    
    from spectrogram_processor import SpectrogramProcessor
    from griffin_lim import GriffinLim
    from frequency_mapper import FrequencyMapper
    
    # Create test spectrogram data
    n_fft = 512
    n_frames = 100
    spectrogram = np.random.rand(n_fft // 2 + 1, n_frames) * 0.5
    
    print(f"Test spectrogram shape: {spectrogram.shape}")
    
    # Initialize modules
    spec_proc = SpectrogramProcessor()
    griffin_lim = GriffinLim(n_iter=20, n_fft=n_fft)
    freq_mapper = FrequencyMapper(sample_rate=44100, n_fft=n_fft)
    
    print("✅ Modules initialized successfully")
    
    # Test frequency mapping
    log_spectrogram = freq_mapper.map_spectrogram_to_log_scale(spectrogram, n_bins=64)
    print(f"Log spectrogram shape: {log_spectrogram.shape}")
    assert log_spectrogram.shape[0] == 64
    
    # Test Griffin-Lim reconstruction
    audio = griffin_lim.reconstruct(spectrogram, verbose=False)
    print(f"Reconstructed audio length: {len(audio)} samples")
    assert len(audio) > 0
    assert np.isfinite(audio).all()
    
    print("✅ Module integration test passed")


def main():
    """Run all integration tests."""
    print("\n" + "="*70)
    print("PHASE 2 INTEGRATION TEST SUITE")
    print("="*70)
    
    try:
        test_cli_basic_conversion()
        test_cli_multi_band()
        test_cli_frequency_scales()
        test_cli_convergence()
        test_cli_audio_parameters()
        test_module_integration()
        
        print("\n" + "="*70)
        print("✅ ALL INTEGRATION TESTS PASSED!")
        print("="*70)
        
        print("\nPhase 2 Integration Testing Complete:")
        print("  • CLI tool: ✅ Working")
        print("  • Multi-band synthesis: ✅ Working")
        print("  • Frequency scales: ✅ Working")
        print("  • Convergence detection: ✅ Working")
        print("  • Audio parameters: ✅ Working")
        print("  • Module integration: ✅ Working")
        
        return 0
        
    except Exception as e:
        print(f"\n❌ INTEGRATION TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    exit(main())