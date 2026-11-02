#!/usr/bin/env python3
"""
spoken_screen.py — An AI speaks, and the screen changes.

One WAV, two carriers, truly mixed:
  mid band  (<3.5 kHz)     : phoneme narration — what the human hears
  high band (4.2-7.5 kHz)  : framed screen-ops  — what the machine obeys

Screen ops ride the same 16-symbol MFSK as speak.py, shifted up an octave-plus
so both carriers coexist in a single mixed waveform. The narration is low-passed
before mixing so fricative noise can't splash into the data band.

Ops payload: JSON list of drawing commands applied to a persistent text screen.
  ["clear"]                  wipe the screen
  ["box", x, y, w, h]        draw a border box
  ["text", x, y, "string"]   place text

Commands:
  utter   narration + ops -> mixed dual-band WAV
  listen  mixed WAV -> decode high band -> apply ops -> render screen
  show    render current screen state
"""

import argparse
import json
import os
import sys
from typing import Optional

import numpy as np
import soundfile as sf
from scipy.signal import butter, sosfilt

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from speak import (
    SAMPLE_RATE, SYMBOL_SEC, frame, bytes_to_symbols, symbols_to_bytes,
    CHUNK_BYTES, say_text,
)
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))
from upic_engine import UPICWaveformTable, UPICEnvelope, UPICVoice, UPICProject, create_basic_waveform
from codec.phy import (
    Phy16Tone, frame as phy_frame, unframe as phy_unframe,
    frame_authenticated, unframe_authenticated, MAGIC_UNAUTH, MAGIC_AUTH
)

import binascii
import struct
import tempfile

HB_TONE_BASE = 4200.0     # high-band nibble 0x0
HB_TONE_STEP = 220.0      # 4200..7500 Hz, well clear of the narration band
NARRATION_CUTOFF = 3500.0
SCREEN_W, SCREEN_H = 48, 14
MAGIC = b'UA'  # Legacy compatibility


def hb_tone(nibble: int) -> float:
    return HB_TONE_BASE + HB_TONE_STEP * nibble


# ---------- screen state ----------

def load_screen(path: str):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)['rows']
    return [' ' * SCREEN_W for _ in range(SCREEN_H)]


def save_screen(path: str, rows):
    with open(path, 'w') as f:
        json.dump({'w': SCREEN_W, 'h': SCREEN_H, 'rows': rows}, f)


def put(rows, x, y, s):
    if 0 <= y < len(rows):
        row = rows[y]
        rows[y] = (row[:x] + s + row[x + len(s):])[:SCREEN_W]


def apply_ops(rows, ops):
    for op in ops:
        kind = op[0]
        if kind == 'clear':
            for y in range(len(rows)):
                rows[y] = ' ' * SCREEN_W
        elif kind == 'box':
            _, x, y, w, h = op
            put(rows, x, y, '+' + '-' * (w - 2) + '+')
            put(rows, x, y + h - 1, '+' + '-' * (w - 2) + '+')
            for yy in range(y + 1, y + h - 1):
                put(rows, x, yy, '|')
                put(rows, x + w - 1, yy, '|')
        elif kind == 'text':
            _, x, y, s = op
            put(rows, x, y, s)
    return rows


def render(rows) -> str:
    bar = '=' * (SCREEN_W + 2)
    return bar + '\n' + '\n'.join('|' + r + '|' for r in rows) + '\n' + bar


# ---------- high-band data carrier (through the UPIC engine) ----------

def synth_data_band(payload: bytes) -> np.ndarray:
    """
    Synthesize data band audio from payload bytes.

    Args:
        payload: Pre-framed payload bytes (from phy_frame or frame_authenticated)

    Returns:
        Audio samples
    """
    symbols = bytes_to_symbols(payload)
    return encode_symbols_to_audio(symbols)


def encode_symbols_to_audio(symbols: list) -> np.ndarray:
    """Encode symbols to high-band audio using UPIC engine."""
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
        project = UPICProject('screen_ops_chunk')
        project.add_wavetable(wavetable)
        env = UPICEnvelope('ops', points)
        project.add_envelope(env)
        voice = UPICVoice('ops', wavetable)
        voice.base_frequency = 1.0
        voice.base_amplitude = 0.9
        voice.set_frequency_envelope(env)
        project.add_voice(voice)
        pieces.append(project.synthesize(duration, SAMPLE_RATE))
    return np.concatenate(pieces)


def decode_data_band(audio: np.ndarray, sr: float, public_key_path: Optional[str] = None) -> bytes:
    """Decode high band data with optional authentication."""
    sym_len = int(round(sr * SYMBOL_SEC))
    n_syms = len(audio) // sym_len
    lo, hi = int(sym_len * 0.25), int(sym_len * 0.75)
    t = np.arange(hi - lo) / sr
    tones = np.array([hb_tone(n) for n in range(16)])
    probe = np.exp(-2j * np.pi * tones[:, None] * t[None, :])
    windows = np.stack([audio[i * sym_len + lo: i * sym_len + hi] for i in range(n_syms)])
    symbols = np.abs(windows @ probe.T).argmax(axis=1).tolist()

    data = symbols_to_bytes(symbols)

    # Determine frame type by magic bytes
    if len(data) >= 2:
        if data[:2] == MAGIC_AUTH:
            # Authenticated frame - requires public key
            if public_key_path is None:
                raise ValueError("authenticated frame requires --public-key")
            payload, valid, error = unframe_authenticated(data, public_key_path)
            if not valid:
                raise ValueError(f"authentication failed: {error}")
            return payload
        elif data[:2] == MAGIC_UNAUTH:
            # Legacy unauthenticated frame. When a public key is supplied,
            # provenance is required, so an unsigned frame must be rejected
            # rather than silently accepted (prevents downgrade attacks).
            if public_key_path is not None:
                raise ValueError("provenance required: unsigned (legacy) frame rejected")
            payload, valid = phy_unframe(data)
            if not valid:
                raise ValueError("invalid unauthenticated frame")
            return payload
        else:
            raise ValueError(f"unknown frame magic: {data[:2]}")

    raise ValueError("no valid data frame found")


# ---------- dual-band mixing ----------

def utter(narration: str, ops, wav_path: str, private_key_path: Optional[str] = None):
    with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tf:
        say_text(narration, tf.name)
        voice_audio, _ = sf.read(tf.name)
    os.unlink(tf.name)
    if voice_audio.ndim > 1:
        voice_audio = voice_audio.mean(axis=1)

    # Confine the voice below the data band before mixing.
    sos = butter(8, NARRATION_CUTOFF, 'low', fs=SAMPLE_RATE, output='sos')
    voice_audio = sosfilt(sos, voice_audio)

    # Encode payload with or without authentication
    payload_bytes = json.dumps(ops, separators=(',', ':')).encode('utf-8')

    if private_key_path:
        # Authenticated utterance
        from cryptography.hazmat.primitives.asymmetric import ed25519
        from cryptography.hazmat.primitives import serialization

        with open(private_key_path, 'rb') as f:
            private_key = serialization.load_pem_private_key(f.read(), password=None)

        signature = private_key.sign(payload_bytes)
        framed = frame_authenticated(payload_bytes, signature)
        print(f"  ✓ Signed with Ed25519 (64-byte signature + timestamp)")
    else:
        # Legacy unauthenticated utterance
        framed = phy_frame(payload_bytes)
        print(f"  ℹ Unauthenticated (legacy mode)")

    # Encode framed payload to high band
    data_audio = synth_data_band(framed)

    n = max(len(voice_audio), len(data_audio))
    mixed = np.zeros(n)
    mixed[:len(voice_audio)] += 0.7 * voice_audio
    mixed[:len(data_audio)] += 0.35 * data_audio
    peak = np.abs(mixed).max()
    if peak > 0.95:
        mixed *= 0.95 / peak
    sf.write(wav_path, mixed, SAMPLE_RATE)
    return mixed


def main():
    parser = argparse.ArgumentParser(description="AI speech that redraws the screen")
    sub = parser.add_subparsers(dest='cmd', required=True)

    p_u = sub.add_parser('utter')
    p_u.add_argument('narration')
    p_u.add_argument('--ops', required=True, help='JSON list of screen ops (or @file.json)')
    p_u.add_argument('-o', '--wav', default='utterance.wav')
    p_u.add_argument('--private-key', help='Path to Ed25519 private key for signing (creates authenticated utterance)')

    p_l = sub.add_parser('listen')
    p_l.add_argument('wav')
    p_l.add_argument('--screen', default='screen.json')
    p_l.add_argument('--public-key', help='Path to Ed25519 public key for verification (required for authenticated utterances)')

    p_s = sub.add_parser('show')
    p_s.add_argument('--screen', default='screen.json')

    args = parser.parse_args()

    if args.cmd == 'utter':
        ops_src = args.ops
        if ops_src.startswith('@'):
            with open(ops_src[1:]) as f:
                ops_src = f.read()
        ops = json.loads(ops_src)
        mixed = utter(args.narration, ops, args.wav, args.private_key)
        print(f"uttered {len(mixed) / SAMPLE_RATE:.1f}s -> {args.wav} "
              f"(voice: {args.narration!r}, ops: {len(ops)})")

    elif args.cmd == 'listen':
        audio, sr = sf.read(args.wav)
        if audio.ndim > 1:
            audio = audio.mean(axis=1)
        ops = json.loads(decode_data_band(audio, sr, args.public_key).decode('utf-8'))
        rows = apply_ops(load_screen(args.screen), ops)
        save_screen(args.screen, rows)
        print(f"heard {len(ops)} ops in high band, screen updated:")
        print(render(rows))

    elif args.cmd == 'show':
        print(render(load_screen(args.screen)))


if __name__ == '__main__':
    main()
