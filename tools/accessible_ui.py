#!/usr/bin/env python3
"""
accessible_ui.py — Accessibility as first-class output

Every UI element is inherently speakable and every spoken thing is inherently visible.
The same artifact serves blind/low-vision and deaf/hard-of-hearing without translation layer.

This demo shows a simple button UI that:
- Renders visually to the terminal
- Generates dual-band audio (narration + visual state in high band)
- Plays audio describing the UI elements
- Demonstrates 1:1 visual/speech match

Commands:
  demo    Show accessible UI demo with audio
"""

import argparse
import json
import os
import sys
import tempfile

import numpy as np
import soundfile as sf

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from speak import SAMPLE_RATE, say_text, frame, bytes_to_symbols, CHUNK_BYTES
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))
from upic_engine import UPICWaveformTable, UPICEnvelope, UPICVoice, UPICProject, create_basic_waveform

# High-band carrier for data (different from speech band)
HB_TONE_BASE = 4200.0
HB_TONE_STEP = 220.0
NARRATION_CUTOFF = 3500.0

SCREEN_W = 60

def hb_tone(nibble: int) -> float:
    return HB_TONE_BASE + HB_TONE_STEP * nibble

def synth_data_band(payload: bytes) -> np.ndarray:
    """Generate high-band audio carrying UI state"""
    from speak import SYMBOL_SEC, symbols_to_bytes, MAGIC, bytes_to_symbols
    import struct
    import binascii
    
    symbols = bytes_to_symbols(frame(payload))
    wavetable = UPICWaveformTable('sine', create_basic_waveform('sine'), SAMPLE_RATE)
    pieces = []
    chunk_syms = CHUNK_BYTES * 2
    
    for c in range(0, len(symbols), chunk_syms):
        chunk = symbols[c:c + chunk_syms]
        duration = len(chunk) * SYMBOL_SEC
        points = []
        for i, sym in enumerate(chunk):
            f = hb_tone(sym)
            points.append((round((i + 0.1) * SYMBOL_SEC / duration, 6), f))
            points.append((round((i + 0.9) * SYMBOL_SEC / duration, 6), f))
        
        project = UPICProject('ui_state')
        project.add_wavetable(wavetable)
        env = UPICEnvelope('ui', points)
        project.add_envelope(env)
        voice = UPICVoice('ui', wavetable)
        voice.base_frequency = 1.0
        voice.base_amplitude = 0.9
        voice.set_frequency_envelope(env)
        project.add_voice(voice)
        pieces.append(project.synthesize(duration, SAMPLE_RATE))
    
    return np.concatenate(pieces)

def render_ui():
    """Render a simple accessible UI"""
    ui_elements = [
        ("Main Menu", "separator"),
        ("[A] Open File", "button"),
        ("[B] Save", "button"),
        ("[C] Settings", "button"),
        ("", "separator"),
        ("Status: Ready", "label"),
    ]
    
    output = []
    for text, elem_type in ui_elements:
        if elem_type == "separator":
            output.append("=" * SCREEN_W)
        elif elem_type == "button":
            output.append(f"  {text}")
        elif elem_type == "label":
            output.append(f"  {text}")
    
    return "\n".join(output), ui_elements

def narrate_ui(ui_elements):
    """Generate narration for UI elements"""
    narration_parts = []
    for text, elem_type in ui_elements:
        if elem_type == "separator":
            continue
        elif elem_type == "button":
            narration_parts.append(f"{text}. Press the letter to activate.")
        elif elem_type == "label":
            narration_parts.append(text)
    
    return " ".join(narration_parts)

def create_dual_band_audio(narration: str, ui_state: str, output_path: str):
    """Create dual-band audio with narration and UI state"""
    from scipy.signal import butter, sosfilt
    
    # Generate narration audio
    with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tf:
        say_text(narration, tf.name)
        voice_audio, _ = sf.read(tf.name)
    os.unlink(tf.name)
    
    if voice_audio.ndim > 1:
        voice_audio = voice_audio.mean(axis=1)
    
    # Low-pass filter voice to avoid crosstalk
    sos = butter(8, NARRATION_CUTOFF, 'low', fs=SAMPLE_RATE, output='sos')
    voice_audio = sosfilt(sos, voice_audio)
    
    # Generate data band with UI state
    ui_state_bytes = ui_state.encode('utf-8')
    data_audio = synth_data_band(ui_state_bytes)
    
    # Mix bands
    n = max(len(voice_audio), len(data_audio))
    mixed = np.zeros(n)
    mixed[:len(voice_audio)] += 0.7 * voice_audio
    mixed[:len(data_audio)] += 0.35 * data_audio
    
    # Normalize
    peak = np.abs(mixed).max()
    if peak > 0.95:
        mixed *= 0.95 / peak
    
    sf.write(output_path, mixed, SAMPLE_RATE)
    return mixed

def demo():
    """Run the accessible UI demo"""
    print("Visual Audio — Accessible UI Demo")
    print("=" * 60)
    print("\nRendering UI visually and as audio...\n")
    
    # Render UI
    visual_ui, ui_elements = render_ui()
    print(visual_ui)
    print()
    
    # Generate narration
    narration = narrate_ui(ui_elements)
    print(f"Narration: {narration}\n")
    
    # Create dual-band audio
    output_wav = "accessible_ui_demo.wav"
    audio = create_dual_band_audio(narration, visual_ui, output_wav)
    
    duration = len(audio) / SAMPLE_RATE
    print(f"✓ Generated dual-band audio: {output_wav}")
    print(f"  Duration: {duration:.2f}s")
    print(f"  Narration band: <{NARRATION_CUTOFF} Hz (phonemes)")
    print(f"  Data band: {HB_TONE_BASE}-{HB_TONE_BASE + 15*HB_TONE_STEP} Hz (UI state)")
    print()
    
    # Play audio if sounddevice is available
    try:
        import sounddevice as sd
        print("Playing audio...")
        sd.play(audio, SAMPLE_RATE)
        sd.wait()
        print("✓ Audio playback complete\n")
    except ImportError:
        print("Note: Install sounddevice to hear audio: pip install sounddevice")
        print(f"Audio saved to: {output_wav}\n")
    except Exception as e:
        print(f"Note: Could not play audio: {e}")
        print(f"Audio saved to: {output_wav}\n")
    
    print("Demo complete. The UI element shown above is:")
    print("  1. Visually rendered (ASCII art)")
    print("  2. Spoken (phoneme narration)")
    print("  3. Encoded in high-band audio for machine decoding")
    print("\nVisual and speech match 1:1 — accessibility is first-class.")

def main():
    parser = argparse.ArgumentParser(description="Accessible UI — visual and speech as one artifact")
    sub = parser.add_subparsers(dest='cmd', required=True)
    
    p_demo = sub.add_parser('demo', help='Run accessible UI demo')
    
    args = parser.parse_args()
    
    if args.cmd == 'demo':
        demo()

if __name__ == '__main__':
    main()