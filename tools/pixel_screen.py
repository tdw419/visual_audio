#!/usr/bin/env python3
"""
pixel_screen.py — A pixel framebuffer driven by spoken dual-band audio.

The screen IS an image file (framebuffer.png). AI utterances arrive as mixed
WAVs: the mid band speaks ("turn the screen blue"), the high band carries the
pixel ops that make it true. Words are drawn using wordbase spectrogram tiles,
so text on this screen is playable audio.

Ops (JSON list, colors are #rrggbb):
  ["fill", color]                     flood the whole screen
  ["rect", x, y, w, h, color]         filled rectangle
  ["frame", x, y, w, h, color]        rectangle outline
  ["word", "text", x, y, color]       blit wordbase tiles, tinted

Commands:
  utter   narration + ops -> dual-band WAV      (the AI side)
  listen  WAV -> decode -> mutate framebuffer   (the OS side)
  show    print framebuffer info
"""

import argparse
import json
import os
import sys

import numpy as np
import soundfile as sf
from PIL import Image
from scipy.signal import butter, sosfilt

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from speak import SAMPLE_RATE, say_text
from spoken_screen import synth_data_band, decode_data_band, NARRATION_CUTOFF
from wordbase import connect, materialize, word_id, tokenize
from word_compiler import ensure_cmudict, parse_cmudict

import tempfile

FB_W, FB_H = 320, 200


def load_fb(path: str) -> np.ndarray:
    if os.path.exists(path):
        return np.asarray(Image.open(path).convert('RGB'), dtype=np.uint8).copy()
    return np.zeros((FB_H, FB_W, 3), dtype=np.uint8)


def hex_color(s: str):
    s = s.lstrip('#')
    return np.array([int(s[i:i + 2], 16) for i in (0, 2, 4)], dtype=np.uint8)


def blit_tile(fb, tile: np.ndarray, x: int, y: int, color):
    h, w = tile.shape
    x2, y2 = min(x + w, FB_W), min(y + h, FB_H)
    if x >= x2 or y >= y2:
        return
    region = tile[:y2 - y, :x2 - x].astype(np.float64) / 255.0
    fb[y:y2, x:x2] = (region[..., None] * color + (1 - region[..., None]) * fb[y:y2, x:x2]).astype(np.uint8)


def apply_ops(fb: np.ndarray, ops) -> np.ndarray:
    db = cmudict = None
    for op in ops:
        kind = op[0]
        if kind == 'fill':
            fb[:, :] = hex_color(op[1])
        elif kind == 'rect':
            _, x, y, w, h, c = op
            fb[y:y + h, x:x + w] = hex_color(c)
        elif kind == 'frame':
            _, x, y, w, h, c = op
            col = hex_color(c)
            fb[y:y + h, x:x + 2] = col; fb[y:y + h, x + w - 2:x + w] = col
            fb[y:y + 2, x:x + w] = col; fb[y + h - 2:y + h, x:x + w] = col
        elif kind == 'word':
            _, text, x, y, c = op
            if db is None:
                db = connect()
                cmudict = parse_cmudict(ensure_cmudict())
            col = hex_color(c).astype(np.float64)
            cx = x
            for w_ in tokenize(text):
                wid = word_id(db, w_, cmudict)
                _, tile_path = materialize(db, wid, cmudict)
                tile = np.asarray(Image.open(tile_path), dtype=np.uint8)
                blit_tile(fb, tile, cx, y, col)
                cx += tile.shape[1] + 4
    return fb


def utter(narration: str, ops, wav_path: str):
    with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tf:
        say_text(narration, tf.name)
        voice, _ = sf.read(tf.name)
    os.unlink(tf.name)
    if voice.ndim > 1:
        voice = voice.mean(axis=1)
    sos = butter(8, NARRATION_CUTOFF, 'low', fs=SAMPLE_RATE, output='sos')
    voice = sosfilt(sos, voice)

    data = synth_data_band(json.dumps(ops, separators=(',', ':')).encode('utf-8'))
    n = max(len(voice), len(data))
    mixed = np.zeros(n)
    mixed[:len(voice)] += 0.8 * voice
    mixed[:len(data)] += 0.25 * data
    peak = np.abs(mixed).max()
    if peak > 0.95:
        mixed *= 0.95 / peak
    sf.write(wav_path, mixed, SAMPLE_RATE)
    return mixed


def main():
    parser = argparse.ArgumentParser(description="Spoken pixel framebuffer")
    sub = parser.add_subparsers(dest='cmd', required=True)

    p = sub.add_parser('utter')
    p.add_argument('narration')
    p.add_argument('--ops', required=True)
    p.add_argument('-o', '--wav', default='utterance.wav')

    p = sub.add_parser('listen')
    p.add_argument('wav')
    p.add_argument('--fb', default='framebuffer.png')

    p = sub.add_parser('show')
    p.add_argument('--fb', default='framebuffer.png')

    args = parser.parse_args()

    if args.cmd == 'utter':
        ops = json.loads(args.ops)
        mixed = utter(args.narration, ops, args.wav)
        print(f"uttered {len(mixed) / SAMPLE_RATE:.1f}s -> {args.wav} "
              f"(voice: {args.narration!r}, {len(ops)} pixel ops)")

    elif args.cmd == 'listen':
        audio, sr = sf.read(args.wav)
        if audio.ndim > 1:
            audio = audio.mean(axis=1)
        ops = json.loads(decode_data_band(audio, sr).decode('utf-8'))
        fb = apply_ops(load_fb(args.fb), ops)
        Image.fromarray(fb, mode='RGB').save(args.fb)
        print(f"heard {len(ops)} pixel ops -> {args.fb} updated")

    elif args.cmd == 'show':
        fb = load_fb(args.fb)
        print(f"{args.fb}: {fb.shape[1]}x{fb.shape[0]}, "
              f"mean color rgb({fb[..., 0].mean():.0f},{fb[..., 1].mean():.0f},{fb[..., 2].mean():.0f})")


if __name__ == '__main__':
    main()
