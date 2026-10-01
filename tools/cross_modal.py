#!/usr/bin/env python3
"""
cross_modal.py — Cross-modal translation tools for Visual Audio.

Enables bidirectional conversion between images, audio, and text using the
Visual Audio codec system.

Modes:
- from-image: Image → Description → Phonemes → Audio
- from-audio: Audio → Phonemes → Text → Image
- from-text:  Text → Audio → Image (full round-trip)

Architectural Standards:
- 20ms per phoneme/symbol
- 16-tone MFSK (800-3200 Hz, 150 Hz spacing)
- ARPAbet-like phoneme encoding
- 44100 Hz sample rate
"""

import argparse
import json
import os
import struct
import wave
from pathlib import Path
from typing import Dict, List, Tuple, Optional

import numpy as np
from PIL import Image, ImageDraw, ImageFont


# Constants matching Visual Audio architecture
SAMPLE_RATE = 44100
SYMBOL_DURATION = 0.020  # 20ms per phoneme/symbol
TONE_BASE = 800.0
TONE_STEP = 150.0
NUM_TONES = 16

# Phoneme mapping (simplified ARPAbet-like for common words)
PHONEME_MAP: Dict[str, List[str]] = {
    "the": ["DH", "AH"],
    "visual": ["V", "IH", "ZH", "UH", "W", "AH"],
    "audio": ["AO", "D", "IY", "OW"],
    "system": ["S", "IH", "S", "T", "AH", "M"],
    "image": ["IH", "M", "IH", "JH"],
    "red": ["R", "EH", "D"],
    "green": ["G", "R", "IY", "N"],
    "blue": ["B", "L", "UW"],
    "yellow": ["Y", "EH", "L", "OW"],
    "purple": ["P", "ER", "P", "AH", "L"],
    "cyan": ["S", "AY", "AH", "N"],
    "pixel": ["P", "IH", "K", "S", "AH", "L"],
    "white": ["W", "AY", "T"],
    "gray": ["G", "R", "EY"],
    "grey": ["G", "R", "EY"],
    "light": ["L", "AY", "T"],
    "dark": ["D", "AA", "R", "K"],
    "black": ["B", "L", "AE", "K"],
    "dimensions": ["D", "AY", "M", "EH", "N", "SH", "AH", "N", "Z"],
    "width": ["W", "IH", "D", "TH"],
    "height": ["HH", "AY", "T"],
    "color": ["K", "AH", "L", "ER"],
    "colors": ["K", "AH", "L", "ER", "Z"],
}

# Letter-to-sound fallback mapping
LETTER_TO_SOUND: Dict[str, str] = {
    'A': 'AE', 'B': 'B', 'C': 'K', 'D': 'D', 'E': 'EH', 'F': 'F',
    'G': 'G', 'H': 'HH', 'I': 'AY', 'J': 'JH', 'K': 'K', 'L': 'L',
    'M': 'M', 'N': 'N', 'O': 'OW', 'P': 'P', 'Q': 'K', 'R': 'R',
    'S': 'S', 'T': 'T', 'U': 'UW', 'V': 'V', 'W': 'W', 'X': 'K',
    'Y': 'Y', 'Z': 'Z'
}


def tone_for(symbol: int) -> float:
    """Get frequency for a symbol (0-15)."""
    return TONE_BASE + (symbol * TONE_STEP)


def symbol_for_tone(frequency: float) -> int:
    """Get symbol for a frequency (nearest tone)."""
    nearest = round((frequency - TONE_BASE) / TONE_STEP)
    return max(0, min(NUM_TONES - 1, nearest))


def text_to_phonemes(text: str) -> List[str]:
    """Convert text to phoneme sequence."""
    phonemes = []
    words = text.lower().split()

    for word in words:
        if word in PHONEME_MAP:
            phonemes.extend(PHONEME_MAP[word])
        else:
            # Fallback: letter-to-sound mapping
            for char in word.upper():
                if char in LETTER_TO_SOUND:
                    phonemes.append(LETTER_TO_SOUND[char])
        phonemes.append("SP")  # Space between words

    return phonemes


def phonemes_to_symbols(phonemes: List[str]) -> List[int]:
    """Convert phoneme sequence to symbol values (0-15)."""
    symbols = []
    for i, phoneme in enumerate(phonemes):
        # Map phoneme to symbol index (simple hash-like mapping)
        if phoneme == "SP":
            symbol = 15  # Silence marker
        else:
            # Use character codes to map to 0-14 range
            symbol = sum(ord(c) for c in phoneme) % 15
        symbols.append(symbol)
    return symbols


def symbols_to_phonemes(symbols: List[int]) -> List[str]:
    """Convert symbol values back to phoneme names (lossy)."""
    phonemes = []
    for symbol in symbols:
        if symbol == 15:
            phonemes.append("SP")
        else:
            # Simple reverse mapping (note: this is lossy)
            phonemes.append(f"P{symbol}")
    return phonemes


def generate_mfsk_audio(symbols: List[int], sample_rate: int = SAMPLE_RATE) -> np.ndarray:
    """Generate 16-tone MFSK audio from symbol sequence."""
    samples_per_symbol = int(sample_rate * SYMBOL_DURATION)
    total_samples = len(symbols) * samples_per_symbol
    audio = np.zeros(total_samples, dtype=np.float32)

    # Attack/decay envelope (2ms each) to prevent clicking
    attack_samples = int(sample_rate * 0.002)
    decay_samples = int(sample_rate * 0.002)

    t = np.arange(samples_per_symbol)

    for i, symbol in enumerate(symbols):
        start = i * samples_per_symbol
        freq = tone_for(symbol)

        if symbol == 15:  # Silence
            audio[start:start + samples_per_symbol] = 0
        else:
            # Generate tone with envelope
            tone = np.sin(2 * np.pi * freq * t / sample_rate)

            # Apply envelope
            envelope = np.ones(samples_per_symbol)
            if attack_samples > 0:
                envelope[:attack_samples] = np.linspace(0, 1, attack_samples)
            if decay_samples > 0:
                envelope[-decay_samples:] = np.linspace(1, 0, decay_samples)

            audio[start:start + samples_per_symbol] = tone * envelope * 0.8

    return audio


def decode_mfsk_audio(audio: np.ndarray, sample_rate: int = SAMPLE_RATE) -> List[int]:
    """Decode MFSK audio back to symbol sequence."""
    samples_per_symbol = int(sample_rate * SYMBOL_DURATION)
    num_symbols = len(audio) // samples_per_symbol

    symbols = []
    window_size = int(sample_rate * 0.010)  # 10ms center window

    for i in range(num_symbols):
        start = i * samples_per_symbol
        end = start + samples_per_symbol

        # Get center portion of symbol (avoid attack/decay)
        center_start = start + (samples_per_symbol - window_size) // 2
        center_end = center_start + window_size
        segment = audio[center_start:center_end]

        if len(segment) == 0:
            symbols.append(15)  # Silence
            continue

        # FFT to find dominant frequency
        spectrum = np.abs(np.fft.rfft(segment))
        freqs = np.fft.rfftfreq(len(segment), 1 / sample_rate)

        # Find peak frequency
        if len(spectrum) > 0:
            peak_idx = np.argmax(spectrum)
            peak_freq = freqs[peak_idx]

            # Check if it's silence (low energy)
            if np.max(spectrum) < 0.1:
                symbol = 15
            else:
                symbol = symbol_for_tone(peak_freq)
        else:
            symbol = 15

        symbols.append(symbol)

    return symbols


def save_wav(audio: np.ndarray, output_path: Path, sample_rate: int = SAMPLE_RATE):
    """Save audio to WAV file."""
    # Convert to 16-bit PCM
    audio_int16 = (audio * 32767).astype(np.int16)

    with wave.open(str(output_path), 'wb') as wav_file:
        wav_file.setnchannels(1)  # Mono
        wav_file.setsampwidth(2)  # 16-bit
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(audio_int16.tobytes())


def load_wav(input_path: Path) -> Tuple[np.ndarray, int]:
    """Load audio from WAV file."""
    with wave.open(str(input_path), 'rb') as wav_file:
        sample_rate = wav_file.getframerate()
        frames = wav_file.readframes(wav_file.getnframes())
        audio = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32767.0

    return audio, sample_rate


def analyze_image(image_path: Path) -> Dict:
    """Analyze image to extract visual features."""
    img = Image.open(image_path)
    img_array = np.array(img)

    # Get dimensions
    height, width = img_array.shape[:2]

    # Analyze colors
    if len(img_array.shape) == 3:  # RGB
        avg_color = img_array.mean(axis=(0, 1)).astype(int)
        colors = detect_colors(img_array)
    else:  # Grayscale
        avg_color = img_array.mean().astype(int)
        colors = ["gray"]

    return {
        "width": width,
        "height": height,
        "avg_color": avg_color.tolist() if len(avg_color.shape) > 0 else int(avg_color),
        "dominant_colors": colors,
        "mode": img.mode
    }


def detect_colors(img_array: np.ndarray) -> List[str]:
    """Detect dominant colors in image."""
    if len(img_array.shape) != 3:
        return ["gray"]

    # Simple thresholding for common colors
    r, g, b = img_array[:, :, 0], img_array[:, :, 1], img_array[:, :, 2]
    avg_r, avg_g, avg_b = r.mean(), g.mean(), b.mean()

    colors = []

    # Check for dominant color channels
    if avg_r > 150 and avg_g < 100 and avg_b < 100:
        colors.append("red")
    if avg_g > 150 and avg_r < 100 and avg_b < 100:
        colors.append("green")
    if avg_b > 150 and avg_r < 100 and avg_g < 100:
        colors.append("blue")

    # Check for combinations
    if avg_r > 150 and avg_g > 150 and avg_b < 100:
        colors.append("yellow")
    if avg_r > 150 and avg_b > 150 and avg_g < 100:
        colors.append("purple")
    if avg_g > 150 and avg_b > 150 and avg_r < 100:
        colors.append("cyan")

    # Check brightness
    brightness = (avg_r + avg_g + avg_b) / 3
    if brightness > 200:
        colors.append("light")
    elif brightness < 50:
        colors.append("dark")

    if not colors:
        colors.append("gray")

    return colors


def generate_description(analysis: Dict) -> str:
    """Generate text description from image analysis."""
    parts = []

    # Dimensions
    parts.append(f"image {analysis['width']} by {analysis['height']}")

    # Colors
    colors = analysis['dominant_colors']
    if colors:
        parts.append("with colors")
        parts.extend(colors)
    else:
        parts.append("gray scale")

    return " ".join(parts)


def render_text_as_image(text: str, output_path: Path, metadata: Optional[Dict] = None):
    """Render text as a styled image document."""
    # Create image with white background
    img = Image.new('RGB', (800, 400), color='white')
    draw = ImageDraw.Draw(img)

    # Try to load a system font
    try:
        font_large = ImageFont.truetype("DejaVuSans.ttf", 32)
        font_medium = ImageFont.truetype("DejaVuSans.ttf", 24)
        font_small = ImageFont.truetype("DejaVuSans.ttf", 16)
    except:
        try:
            font_large = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 32)
            font_medium = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 24)
            font_small = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 16)
        except:
            font_large = ImageFont.load_default()
            font_medium = ImageFont.load_default()
            font_small = ImageFont.load_default()

    # Draw border
    draw.rectangle([(10, 10), (790, 390)], outline='black', width=2)

    # Draw title
    draw.text((30, 30), "Visual Audio Decoded", font=font_large, fill='black')

    # Draw text (simple word wrap)
    words = text.split()
    lines = []
    current_line = ""
    for word in words:
        test_line = current_line + " " + word if current_line else word
        bbox = draw.textbbox((0, 0), test_line, font=font_medium)
        if bbox[2] < 740:
            current_line = test_line
        else:
            lines.append(current_line)
            current_line = word
    if current_line:
        lines.append(current_line)

    y_offset = 80
    for line in lines:
        draw.text((30, y_offset), line, font=font_medium, fill='black')
        y_offset += 35

    # Draw metadata footer
    if metadata:
        y_offset = 340
        draw.text((30, y_offset), f"Original: {metadata.get('source', 'unknown')}",
                  font=font_small, fill='gray')
        draw.text((30, y_offset + 20), f"Symbols: {metadata.get('num_symbols', 0)}",
                  font=font_small, fill='gray')

    # Save image
    img.save(output_path)


def from_image_mode(image_path: Path, output_path: Path):
    """Mode: Image → Audio."""
    print(f"[1/3] Analyzing image: {image_path}")
    analysis = analyze_image(image_path)

    print(f"[2/3] Generating description...")
    description = generate_description(analysis)
    print(f"  Description: {description}")

    print(f"[3/3] Encoding as MFSK audio...")
    phonemes = text_to_phonemes(description)
    symbols = phonemes_to_symbols(phonemes)
    audio = generate_mfsk_audio(symbols)

    save_wav(audio, output_path)
    print(f"  ✓ Audio saved to: {output_path}")
    print(f"  Duration: {len(audio) / SAMPLE_RATE:.2f}s, Symbols: {len(symbols)}")


def from_audio_mode(audio_path: Path, output_path: Path):
    """Mode: Audio → Image."""
    print(f"[1/4] Loading audio: {audio_path}")
    audio, sr = load_wav(audio_path)
    print(f"  Duration: {len(audio) / sr:.2f}s, Sample rate: {sr} Hz")

    print(f"[2/4] Decoding MFSK symbols...")
    symbols = decode_mfsk_audio(audio, sr)
    print(f"  Decoded {len(symbols)} symbols")

    print(f"[3/4] Reconstructing text...")
    phonemes = symbols_to_phonemes(symbols)
    # For display, just show the symbol-based representation
    text = " ".join([p for p in phonemes if p != "SP"])
    print(f"  Text: {text[:100]}{'...' if len(text) > 100 else ''}")

    print(f"[4/4] Rendering as image...")
    metadata = {
        'source': str(audio_path),
        'num_symbols': len(symbols)
    }
    render_text_as_image(text, output_path, metadata)
    print(f"  ✓ Image saved to: {output_path}")


def from_text_mode(text: str, output_dir: Path):
    """Mode: Text → Audio → Image (full round-trip)."""
    output_dir = Path(output_dir)
    output_dir.mkdir(exist_ok=True)

    print(f"[ROUND-TRIP DEMO] Input text: \"{text}\"")
    print()

    # Step 1: Text → Audio
    print("[Step 1] Text → Phonemes → Audio")
    phonemes = text_to_phonemes(text)
    symbols = phonemes_to_symbols(phonemes)
    audio = generate_mfsk_audio(symbols)

    audio_path = output_dir / "round_trip.wav"
    save_wav(audio, audio_path)
    print(f"  ✓ Audio saved: {audio_path} ({len(audio) / SAMPLE_RATE:.2f}s, {len(symbols)} symbols)")
    print()

    # Step 2: Audio → Text
    print("[Step 2] Audio → Phonemes → Text")
    decoded_symbols = decode_mfsk_audio(audio)
    decoded_phonemes = symbols_to_phonemes(decoded_symbols)
    decoded_text = " ".join([p for p in decoded_phonemes if p != "SP"])
    print(f"  Decoded: {decoded_text[:100]}{'...' if len(decoded_text) > 100 else ''}")
    print()

    # Step 3: Render final image
    print("[Step 3] Render as Image")
    image_path = output_dir / "round_trip_output.png"
    metadata = {
        'source': f"Text: \"{text}\"",
        'num_symbols': len(decoded_symbols)
    }
    render_text_as_image(decoded_text, image_path, metadata)
    print(f"  ✓ Image saved: {image_path}")
    print()

    # Summary
    print("[ROUND-TRIP SUMMARY]")
    print(f"  Original symbols: {len(symbols)}")
    print(f"  Decoded symbols: {len(decoded_symbols)}")
    print(f"  Match rate: {sum(1 for a, b in zip(symbols, decoded_symbols) if a == b) / len(symbols) * 100:.1f}%")
    print()
    print("Artifacts created:")
    print(f"  - {audio_path}")
    print(f"  - {image_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Cross-modal translation tools for Visual Audio",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Image → Audio
  python3 tools/cross_modal.py from-image scene.png --output scene.wav

  # Audio → Image
  python3 tools/cross_modal.py from-audio scene.wav --output scene_reconstructed.png

  # Text → Audio → Image (round-trip)
  python3 tools/cross_modal.py from-text "visual audio system" --output-dir ./output
        """
    )

    subparsers = parser.add_subparsers(dest='mode', help='Translation mode')

    # from-image mode
    image_parser = subparsers.add_parser('from-image', help='Image → Audio')
    image_parser.add_argument('input', type=Path, help='Input image file')
    image_parser.add_argument('--output', '-o', type=Path, required=True,
                              help='Output WAV file')

    # from-audio mode
    audio_parser = subparsers.add_parser('from-audio', help='Audio → Image')
    audio_parser.add_argument('input', type=Path, help='Input WAV file')
    audio_parser.add_argument('--output', '-o', type=Path, required=True,
                              help='Output PNG file')

    # from-text mode
    text_parser = subparsers.add_parser('from-text', help='Text → Audio → Image (round-trip)')
    text_parser.add_argument('text', help='Input text')
    text_parser.add_argument('--output-dir', '-d', type=Path, default='./output',
                            help='Output directory for artifacts')

    args = parser.parse_args()

    if args.mode == 'from-image':
        if not args.input.exists():
            print(f"Error: Input file not found: {args.input}")
            return 1
        from_image_mode(args.input, args.output)

    elif args.mode == 'from-audio':
        if not args.input.exists():
            print(f"Error: Input file not found: {args.input}")
            return 1
        from_audio_mode(args.input, args.output)

    elif args.mode == 'from-text':
        from_text_mode(args.text, args.output_dir)

    else:
        parser.print_help()
        return 1

    return 0


if __name__ == '__main__':
    exit(main())