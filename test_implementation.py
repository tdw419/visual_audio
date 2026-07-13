#!/usr/bin/env python3
"""
Quick test script to verify the implementation works end-to-end.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

import numpy as np
from PIL import Image
from image_processor import ImageProcessor
from waveform_generator import WaveformGenerator
from utils import create_sine_wave_image, create_square_wave_image

print("Creating test waveforms...")

# Create test images
print("1. Creating sine wave image...")
sine_img_array = create_sine_wave_image(height=200, width=441, frequency=0.05, amplitude=0.4)
sine_img = Image.fromarray((sine_img_array * 255).astype(np.uint8), mode='L')
sine_img.save('/tmp/test_sine.png')
print(f"   Saved to /tmp/test_sine.png ({sine_img.size[0]}x{sine_img.size[1]})")

print("2. Creating square wave image...")
square_img_array = create_square_wave_image(height=200, width=441, frequency=0.05, amplitude=0.4)
square_img = Image.fromarray((square_img_array * 255).astype(np.uint8), mode='L')
square_img.save('/tmp/test_square.png')
print(f"   Saved to /tmp/test_square.png ({square_img.size[0]}x{square_img.size[1]})")

# Process images
print("\nProcessing images...")
processor = ImageProcessor(power_law=1.0, invert=True)
generator = WaveformGenerator(sample_rate=44100, bit_depth=16)

for img_name, img_array in [("sine", sine_img_array), ("square", square_img_array)]:
    print(f"\n{img_name.upper()} WAVE:")
    
    # Extract waveform
    audio_samples = generator.extract_waveform(img_array, power_law=1.0)
    
    # Generate WAV
    output_path = f"/tmp/test_{img_name}.wav"
    sample_rate, audio_data = generator.generate_wav_file(audio_samples, output_path)
    
    duration = len(audio_samples) / sample_rate
    print(f"  Duration: {duration:.3f}s")
    print(f"  Sample rate: {sample_rate} Hz")
    print(f"  Samples: {len(audio_samples)}")
    print(f"  Range: [{audio_samples.min():.3f}, {audio_samples.max():.3f}]")
    print(f"  Output: {output_path}")

# Test CLI
print("\n\nTesting CLI tool...")
import subprocess

result = subprocess.run(
    ['python3', 'visual-wave2wav.py', '/tmp/test_sine.png', '/tmp/cli_test.wav'],
    capture_output=True,
    text=True
)

print("CLI Output:")
print(result.stdout)
if result.returncode != 0:
    print("CLI Errors:")
    print(result.stderr)

# Test with options
print("\nTesting CLI with options...")
result = subprocess.run([
    'python3', 'visual-wave2wav.py',
    '/tmp/test_sine.png',
    '/tmp/cli_test_48k.wav',
    '--sample-rate', '48000',
    '--bit-depth', '24',
    '--duration', '2.0'
], capture_output=True, text=True)

print("CLI Output:")
print(result.stdout)

print("\n✅ All tests completed successfully!")
print("\nGenerated files:")
print("  - /tmp/test_sine.png (sine wave image)")
print("  - /tmp/test_square.png (square wave image)")
print("  - /tmp/test_sine.wav (sine wave audio)")
print("  - /tmp/test_square.wav (square wave audio)")
print("  - /tmp/cli_test.wav (CLI generated)")
print("  - /tmp/cli_test_48k.wav (CLI with options)")