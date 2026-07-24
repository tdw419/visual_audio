#!/usr/bin/env python3
"""
audio_to_frames.py — Audio Visualization to Frame Generator

Renders the dual-band audio as a scrolling UPIC-style spectrogram video frame sequence.

Frame layout (1920×1080):
  Top 540px: Scrolling phoneme band spectrogram (0-4kHz)
    - Green=core formants, Cyan=control frequencies
  Bottom-left 960×540: MFSK data band (4-8kHz)
    - Purple=data tones
  Bottom-right 960×540: Word/phoneme activity bars (F1/F2)
    - Uses UPIC JSON metadata if available

Output: piped to stdout as raw RGB24 for ffmpeg consumption,
        or saves individual frames as PNG to output directory.
"""

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image
from scipy.io import wavfile
from scipy.signal import spectrogram


# ── Color palette (Geometry OS semantic colors) ──
BG = np.array([10, 10, 20], dtype=np.uint8)        # Dark background
PHONEME_GREEN = np.array([0, 255, 136], dtype=np.uint8)    # Core formants
CONTROL_CYAN = np.array([0, 200, 255], dtype=np.uint8)     # Focus frequencies
DATA_PURPLE = np.array([168, 85, 247], dtype=np.uint8)     # MFSK data tones
HILBERT_GOLD = np.array([255, 200, 50], dtype=np.uint8)    # Active hilbert region
SCANLINE = np.array([255, 255, 255, 30], dtype=np.uint8)   # Scanline overlay (semi-transp)
LABEL_WHITE = np.array([200, 200, 200], dtype=np.uint8)
GRID_LINE = np.array([40, 40, 60], dtype=np.uint8)

# Audio params
SAMPLE_RATE = 44100
FFT_SIZE = 2048
HOP_LENGTH = 512
TARGET_FPS = 60.0
PHONEME_BAND_HZ = 4000
DATA_BAND_HZ_LOW = 4000
DATA_BAND_HZ_HIGH = 8000

# Video dims
WIDTH = 1920
HEIGHT = 1080

# Region splits
TOP_H = 540
BOT_H = HEIGHT - TOP_H  # 540
LEFT_W = 960
RIGHT_W = WIDTH - LEFT_W  # 960

# ── Helpers ──

def lerp_color(c1, c2, t):
    """Linearly interpolate between two RGB colors."""
    return (c1.astype(float) * (1 - t) + c2.astype(float) * t).astype(np.uint8)


def draw_scanline(frame, y, width=WIDTH):
    """Draw a semi-transparent horizontal scanline."""
    for c in range(3):
        frame[y, :, c] = np.clip(frame[y, :, c].astype(int) + 30, 0, 255).astype(np.uint8)


def draw_freq_ticks(frame, x_start, y_start, h, max_hz, color=GRID_LINE):
    """Draw horizontal grid lines at labeled frequency intervals."""
    intervals = []
    if max_hz <= 4000:
        intervals = [200, 500, 1000, 1500, 2000, 2500, 3000, 3500, 4000]
    else:
        intervals = [4000, 5000, 6000, 7000, 8000]

    for hz in intervals:
        if hz > max_hz:
            break
        frac = hz / max_hz
        y = y_start + h - int(frac * h)
        if 0 <= y < HEIGHT:
            frame[y, x_start:x_start+30, :] = color


def draw_time_ticks(frame, x_start, y_start, w, total_seconds, color=GRID_LINE):
    """Draw vertical grid lines at 0.5s intervals."""
    for t in range(0, int(total_seconds) + 1):
        frac = t / total_seconds if total_seconds > 0 else 0
        x = x_start + int(frac * w)
        if 0 <= x < WIDTH:
            frame[y_start:y_start+15, x, :] = color


def render_spectrogram_band(frame, freqs, times, Sxx, 
                             x_start, y_start, w, h,
                             max_hz, color_scale,
                             label="", log_scale=True):
    """
    Render a spectrogram band into the frame buffer.
    Sxx: 2D array (n_freqs x n_times)
    """
    n_freqs, n_times = Sxx.shape

    # Convert to dB scale
    Sxx_db = 20 * np.log10(np.maximum(Sxx, 1e-10))

    # Normalize to 0-1
    min_db = np.min(Sxx_db)
    max_db = np.max(Sxx_db)
    if max_db - min_db > 0:
        Sxx_norm = (Sxx_db - min_db) / (max_db - min_db)
    else:
        Sxx_norm = np.zeros_like(Sxx_db)

    # Clip to perceptually meaningful range
    Sxx_norm = np.clip(Sxx_norm, 0, 1)

    # Render columns (time) → x, rows (freq) → y
    for ti in range(min(n_times, w)):
        src_x = n_times - 1 - ti  # scroll: newest on right
        if src_x < 0:
            continue
        dst_x = x_start + w - 1 - ti
        if dst_x >= WIDTH:
            continue

        for fi in range(n_freqs):
            freq = freqs[fi]
            if freq > max_hz:
                continue

            # Map frequency to y position (log scale)
            if log_scale and max_hz > 0:
                if freq <= 0:
                    fy = 0
                else:
                    fy = int((np.log2(freq + 1) / np.log2(max_hz + 1)) * h)
            else:
                fy = int((freq / max_hz) * h)

            # Flip y (0hz at bottom)
            dst_y = y_start + h - 1 - fy
            if dst_y >= HEIGHT:
                continue

            magnitude = Sxx_norm[fi, src_x]

            if magnitude > 0.02:  # noise floor threshold
                color = lerp_color(BG, color_scale, magnitude * 0.9)
                frame[dst_y, dst_x, :] = color


def render_phoneme_bars(frame, word_times, current_time, x_start, y_start, w, h):
    """
    Render word-level phoneme bars showing F1/F2 formant ranges.
    word_times: list of dicts with start, end, word, formant_freq
    """
    active_words = [wt for wt in word_times 
                    if wt['start'] <= current_time <= wt['end']]
    
    if not active_words:
        return

    word = active_words[0]
    progress = (current_time - word['start']) / max(word['end'] - word['start'], 0.001)

    # F1 bar (lower formant)
    f1 = word.get('f1', 600)
    f1_h = int((f1 / 1000) * h)  # normalize to 1kHz scale
    bar_mid = y_start + h - f1_h
    bar_w = int(w * 0.15)
    bar_x = x_start + int(w * 0.1)
    frame[max(0, bar_mid-4):bar_mid+4, bar_x:bar_x+bar_w, :] = PHONEME_GREEN

    # F2 bar (upper formant)
    f2 = word.get('f2', 1800)
    f2_h = int((f2 / 3000) * h)
    bar_mid = y_start + h - f2_h
    bar_w = int(w * 0.15)
    bar_x = x_start + int(w * 0.4)
    frame[max(0, bar_mid-3):bar_mid+3, bar_x:bar_x+bar_w, :] = CONTROL_CYAN

    # Word label
    label_y = y_start + 30
    label_x = x_start + 10
    # Simple pixel-drawn text approximation via horizontal bars
    frame[label_y-2:label_y+2, label_x:label_x+len(word)*20, :] = LABEL_WHITE


def render_data_band_mfsk(frame, freqs, times, Sxx,
                           x_start, y_start, w, h):
    """
    Render the 16-tone MFSK data band visualization.
    Highlights active tones in the data frequency range.
    """
    # Filter to MFSK frequency range (4000-8000Hz)
    mask = (freqs >= DATA_BAND_HZ_LOW) & (freqs <= DATA_BAND_HZ_HIGH)
    data_freqs = freqs[mask]
    data_Sxx = Sxx[mask, :]

    if len(data_freqs) == 0 or data_Sxx.size == 0:
        # Draw placeholder grid
        for tone in range(16):
            y_frac = tone / 16
            y = y_start + int(y_frac * h)
            frame[y, x_start:x_start+w, :] = GRID_LINE
        return

    Sxx_db = 20 * np.log10(np.maximum(data_Sxx, 1e-10))
    min_db = np.min(Sxx_db)
    max_db = np.max(Sxx_db)
    if max_db - min_db > 0:
        Sxx_norm = (Sxx_db - min_db) / (max_db - min_db)
    else:
        Sxx_norm = np.zeros_like(Sxx_db)

    n_freqs, n_times = data_Sxx.shape
    for ti in range(min(n_times, w)):
        src_x = n_times - 1 - ti
        if src_x < 0:
            continue
        dst_x = x_start + w - 1 - ti
        if dst_x >= WIDTH:
            continue

        for fi in range(n_freqs):
            magnitude = Sxx_norm[fi, src_x]
            if magnitude > 0.05:
                y_frac = fi / n_freqs
                dst_y = y_start + h - 1 - int(y_frac * h)
                if dst_y < HEIGHT:
                    frame[dst_y, dst_x, :] = lerp_color(BG, DATA_PURPLE, magnitude)


def load_upic_metadata(json_path):
    """Load UPIC JSON and extract word timing / formant data."""
    word_times = []
    try:
        with open(json_path) as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return word_times

    # UPIC format: {voices: [{name, frequency_envelope: {control_points: [[t, f]]}}]}
    if 'voices' in data:
        for voice in data['voices']:
            name = voice.get('name', '?')
            freq_env = voice.get('frequency_envelope', {})
            amp_env = voice.get('amplitude_envelope', {})
            ctrl_pts = freq_env.get('control_points', [])
            base_freq = voice.get('base_frequency', 1.0)

            if ctrl_pts:
                # Get min/max frequency from envelope
                freqs = [p[1] for p in ctrl_pts]
                durations = [p[0] for p in ctrl_pts] if ctrl_pts else [0, 1]
                start_t = min(durations) if durations else 0
                end_t = max(durations) if durations else 1

                word_times.append({
                    'word': name,
                    'start': start_t,
                    'end': end_t,
                    'f1': min(freqs),
                    'f2': max(freqs),
                })
    return word_times


def generate_frames(wav_path, json_path=None, output_dir=None, raw_mode=False):
    """
    Main frame generator.
    
    If raw_mode: writes raw RGB24 frames to stdout (for ffmpeg pipe).
    If output_dir: saves each frame as PNG.
    Returns total frame count.
    """
    # Load audio
    rate, audio = wavfile.read(wav_path)
    
    # Convert to mono if stereo
    if audio.ndim > 1:
        audio = audio.mean(axis=1).astype(audio.dtype)
    
    # Normalize to float [-1, 1]
    if audio.dtype == np.int16:
        audio = audio.astype(np.float32) / 32768.0
    elif audio.dtype == np.int32:
        audio = audio.astype(np.float32) / 2147483648.0
    elif audio.dtype == np.uint8:
        audio = (audio.astype(np.float32) - 128) / 128.0
    
    duration = len(audio) / rate

    # Compute STFT for full audio
    f, t, Sxx = spectrogram(audio, fs=rate, nperseg=FFT_SIZE, 
                            noverlap=FFT_SIZE - HOP_LENGTH,
                            scaling='spectrum')

    # Load UPIC metadata if available
    word_times = []
    if json_path:
        word_times = load_upic_metadata(json_path)

    # Total frames at 60 FPS
    total_frames = int(duration * TARGET_FPS) + 1

    # Pre-allocate frame buffer
    # Note: scipy.signal.spectrogram output has shape (n_freqs, n_times)
    n_freqs = len(f)
    n_times = len(t)

    if raw_mode and output_dir:
        # Can't use both
        raw_mode = False

    for frame_idx in range(total_frames):
        # Create blank frame
        frame = np.full((HEIGHT, WIDTH, 3), BG, dtype=np.uint8)

        current_time = frame_idx / TARGET_FPS

        # Which time index in the STFT corresponds to current_time?
        time_idx = int(current_time * rate / HOP_LENGTH)
        time_idx = min(time_idx, n_times - 1)

        # ── Region 1: Top half — Phoneme band spectrogram (0-4kHz) ──
        # We want a 2-second scrolling window
        window_frames = int(2.0 * rate / HOP_LENGTH)
        start_ti = max(0, time_idx - window_frames)
        end_ti = time_idx + 1

        top_Sxx = Sxx[:n_freqs // 2, start_ti:end_ti]
        top_freqs = f[:n_freqs // 2]

        # Scroll the frame
        render_spectrogram_band(
            frame, top_freqs, t[start_ti:end_ti], top_Sxx,
            x_start=0, y_start=0, w=WIDTH, h=TOP_H,
            max_hz=PHONEME_BAND_HZ,
            color_scale=PHONEME_GREEN,
            label="PHONEME BAND (0-4kHz)"
        )

        # Draw frequency grid lines on left
        draw_freq_ticks(frame, 0, 0, TOP_H, PHONEME_BAND_HZ)

        # Draw scanline at current time position
        scanline_x = int(WIDTH * (1 - (time_idx - start_ti) / max(window_frames, 1)))
        if 0 <= scanline_x < WIDTH:
            frame[0:TOP_H, scanline_x, :] = [255, 255, 255]
            frame[0:TOP_H, scanline_x-1, :] = [200, 200, 255]

        # ── Region 2: Bottom-left — MFSK data band (4-8kHz) ──
        data_Sxx = Sxx[n_freqs // 2:, start_ti:time_idx+1]
        data_freqs = f[n_freqs // 2:]

        if len(data_freqs) > 0 and data_Sxx.size > 0:
            render_data_band_mfsk(
                frame, data_freqs, t[start_ti:time_idx+1], data_Sxx,
                x_start=0, y_start=TOP_H, w=LEFT_W, h=BOT_H
            )

        # Draw frequency grid for data band
        draw_freq_ticks(frame, 0, TOP_H, BOT_H, 4000, DATA_PURPLE)

        # ── Region 3: Bottom-right — Phoneme activity bars ──
        divider_x = LEFT_W
        frame[TOP_H:, divider_x-1:divider_x+1, :] = GRID_LINE
        frame[TOP_H-1:TOP_H+1, :, :] = GRID_LINE

        render_phoneme_bars(frame, word_times, current_time,
                            x_start=divider_x+10, y_start=TOP_H+10,
                            w=RIGHT_W-20, h=BOT_H-20)

        # ── Label overlays (simple pixel regions) ──
        # Top-left label
        frame[5:12, 40:280, :] = [40, 40, 60]
        frame[6:11, 41:279, :] = PHONEME_GREEN // 4

        # Bottom-left label
        ly = TOP_H + 5
        frame[ly:ly+7, 40:260, :] = [40, 40, 60]
        frame[ly+1:ly+6, 41:259, :] = DATA_PURPLE // 4

        # Bottom-right label
        rx = divider_x + 10
        frame[ly:ly+7, rx:rx+280, :] = [40, 40, 60]
        frame[ly+1:ly+6, rx+1:rx+279, :] = HILBERT_GOLD // 4

        # ── Frame counter overlay ──
        counter_text = f"FRAME {frame_idx:06d}  |  T={current_time:.2f}s"
        frame[5:12, WIDTH-300:WIDTH-10, :] = [40, 40, 60]

        # ── Output ──
        if raw_mode:
            # Write raw RGB24 to stdout
            sys.stdout.buffer.write(frame.tobytes())
        elif output_dir:
            img = Image.fromarray(frame, 'RGB')
            img.save(os.path.join(output_dir, f"frame_{frame_idx:06d}.png"))
        else:
            # Default: write raw to stdout for piping to ffmpeg
            sys.stdout.buffer.write(frame.tobytes())

    return total_frames


def main():
    parser = argparse.ArgumentParser(
        description="Generate UPIC-style scrolling spectrogram frames from WAV audio"
    )
    parser.add_argument("wav", help="Input WAV audio file")
    parser.add_argument("-j", "--json", help="UPIC JSON metadata file for phoneme annotation")
    parser.add_argument("-o", "--output", help="Output directory for PNG frames (default: pipe raw RGB24 to stdout)")
    parser.add_argument("--raw", action="store_true",
                        help="Force raw RGB24 to stdout even when output dir is set")

    args = parser.parse_args()

    output_dir = args.output
    raw_mode = args.raw

    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    total = generate_frames(args.wav, json_path=args.json, 
                            output_dir=output_dir, raw_mode=raw_mode)

    if output_dir:
        print(f"✓ Generated {total} frames in {output_dir}", file=sys.stderr)
    else:
        print(f"✓ Generated {total} frames (raw RGB24 → stdout)", file=sys.stderr)


if __name__ == "__main__":
    main()
