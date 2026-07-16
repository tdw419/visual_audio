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
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.primitives import serialization
from cryptography.exceptions import InvalidSignature
import base64

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from speak import SAMPLE_RATE, say_text
from spoken_screen import synth_data_band, decode_data_band, NARRATION_CUTOFF
from wordbase_compat import connect, materialize, word_id, tokenize
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
    if tile.ndim == 3:  # RGB image
        h, w, _ = tile.shape
    else:  # Grayscale
        h, w = tile.shape
    x2, y2 = min(x + w, FB_W), min(y + h, FB_H)
    if x >= x2 or y >= y2:
        return
    region = tile[:y2 - y, :x2 - x].astype(np.float64) / 255.0
    # Handle both grayscale and RGB tiles
    if region.ndim == 2:  # Grayscale
        fb[y:y2, x:x2] = (region[..., None] * color + (1 - region[..., None]) * fb[y:y2, x:x2]).astype(np.uint8)
    else:  # RGB
        fb[y:y2, x:x2] = (region * color + (1 - region) * fb[y:y2, x:x2]).astype(np.uint8)


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

            # Look up color_hex for automatic coloring
            if c is None or c == 'auto':
                col = None  # Will be set per word below
            else:
                col = hex_color(c).astype(np.float64)

            cx = x
            for w_ in tokenize(text):
                wid = word_id(db, w_, cmudict)
                _, tile_path = materialize(db, wid, cmudict)
                tile = np.asarray(Image.open(tile_path), dtype=np.uint8)

                # Get color per word if using auto-color
                if col is None:
                    cursor = db.execute('SELECT color_hex FROM words WHERE id = ? LIMIT 1', (wid,))
                    row = cursor.fetchone()
                    if row and row[0]:
                        word_col = hex_color(row[0]).astype(np.float64)
                    else:
                        word_col = np.array([1.0, 1.0, 1.0], dtype=np.float64)  # fallback white
                else:
                    word_col = col

                if tile.ndim == 3:  # RGB image
                    th, tw, _ = tile.shape
                else:  # Grayscale
                    th, tw = tile.shape
                blit_tile(fb, tile, cx, y, word_col)
                cx += tw + 4
        elif kind == 'boot':
            # Boot command: ["boot", arch, image_path, extra_args...]
            # Returns: (success, message, pid) tuple
            _, arch, image_path, *extra_args = op
            success, message, pid = handle_boot_op(arch, image_path, extra_args)
            # Return metadata to caller for logging/display
            if len(op) > 2:
                op.append({'boot_result': {'success': success, 'message': message, 'pid': pid}})
    return fb


def utter(narration: str, ops, wav_path: str, private_key_path: str = None):
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
    
    # Sign utterance if private key provided
    if private_key_path:
        sign_utterance(wav_path, ops, private_key_path)
    
    return mixed


def generate_keypair(key_dir: str = None) -> tuple[str, str]:
    """Generate Ed25519 key pair for utterance signing.
    
    Returns:
        (private_key_path, public_key_path)
    """
    if key_dir is None:
        key_dir = os.path.join(os.path.dirname(__file__), '..', 'keys')
    os.makedirs(key_dir, exist_ok=True)
    
    private_key = ed25519.Ed25519PrivateKey.generate()
    public_key = private_key.public_key()
    
    private_key_path = os.path.join(key_dir, 'pixel_os_private.pem')
    public_key_path = os.path.join(key_dir, 'pixel_os_public.pem')
    
    # Save private key
    with open(private_key_path, 'wb') as f:
        f.write(private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        ))
    
    # Save public key
    with open(public_key_path, 'wb') as f:
        f.write(public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        ))
    
    print(f"Generated keypair:")
    print(f"  Private: {private_key_path}")
    print(f"  Public: {public_key_path}")
    
    return private_key_path, public_key_path


def sign_utterance(wav_path: str, ops, private_key_path: str):
    """Sign an utterance with Ed25519 private key.
    
    Creates a .sig file alongside the WAV containing base64-encoded signature.
    """
    # Load private key
    with open(private_key_path, 'rb') as f:
        private_key = serialization.load_pem_private_key(
            f.read(),
            password=None
        )
    
    # Sign the ops JSON (the actual command payload)
    payload = json.dumps(ops, separators=(',', ':')).encode('utf-8')
    signature = private_key.sign(payload)
    
    # Save signature as base64
    sig_path = wav_path + '.sig'
    with open(sig_path, 'w') as f:
        f.write(base64.b64encode(signature).decode('ascii'))
    
    print(f"Signed utterance: {sig_path}")


def verify_utterance(wav_path: str, ops, public_key_path: str) -> bool:
    """Verify an utterance's signature against Ed25519 public key.
    
    Returns True if signature is valid, False otherwise.
    """
    sig_path = wav_path + '.sig'
    if not os.path.exists(sig_path):
        print(f"No signature found for {wav_path}")
        return False
    
    # Load public key
    with open(public_key_path, 'rb') as f:
        public_key = serialization.load_pem_public_key(f.read())
    
    # Load signature
    with open(sig_path, 'r') as f:
        signature = base64.b64decode(f.read())
    
    # Verify against the ops payload
    payload = json.dumps(ops, separators=(',', ':')).encode('utf-8')
    
    try:
        public_key.verify(signature, payload)
        print(f"✓ Verified signature for {wav_path}")
        return True
    except InvalidSignature:
        print(f"✗ Invalid signature for {wav_path}")
        return False
    except Exception as e:
        print(f"✗ Signature verification failed: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Spoken pixel framebuffer")
    sub = parser.add_subparsers(dest='cmd', required=True)

    p = sub.add_parser('utter')
    p.add_argument('narration')
    p.add_argument('--ops', required=True)
    p.add_argument('-o', '--wav', default='utterance.wav')
    p.add_argument('--private-key', help='Path to Ed25519 private key for signing')

    p = sub.add_parser('listen')
    p.add_argument('wav')
    p.add_argument('--fb', default='framebuffer.png')
    p.add_argument('--public-key', help='Path to Ed25519 public key for verification')

    p = sub.add_parser('show')
    p.add_argument('--fb', default='framebuffer.png')

    p = sub.add_parser('gen-keys')
    p.add_argument('--key-dir', help='Directory to store keys (default: ./keys)')

    args = parser.parse_args()

    if args.cmd == 'utter':
        ops = json.loads(args.ops)
        mixed = utter(args.narration, ops, args.wav, args.private_key)
        print(f"uttered {len(mixed) / SAMPLE_RATE:.1f}s -> {args.wav} "
              f"(voice: {args.narration!r}, {len(ops)} pixel ops)")

    elif args.cmd == 'listen':
        audio, sr = sf.read(args.wav)
        if audio.ndim > 1:
            audio = audio.mean(axis=1)
        ops = json.loads(decode_data_band(audio, sr).decode('utf-8'))
        
        # Verify signature if public key provided
        if args.public_key:
            if not verify_utterance(args.wav, ops, args.public_key):
                print(f"✗ REJECTED: Invalid or missing signature for {args.wav}")
                return 1
        
        fb = apply_ops(load_fb(args.fb), ops)
        Image.fromarray(fb, mode='RGB').save(args.fb)
        print(f"heard {len(ops)} pixel ops -> {args.fb} updated")

    elif args.cmd == 'show':
        fb = load_fb(args.fb)
        print(f"{args.fb}: {fb.shape[1]}x{fb.shape[0]}, "
              f"mean color rgb({fb[..., 0].mean():.0f},{fb[..., 1].mean():.0f},{fb[..., 2].mean():.0f})")

    elif args.cmd == 'gen-keys':
        generate_keypair(args.key_dir)


if __name__ == '__main__':
    main()
