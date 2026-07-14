#!/usr/bin/env python3
"""
wordbase.py — Word database: dictionary words <-> stable IDs <-> visual audio.

SQLite maps every CMUdict word to a stable integer ID and its phoneme string.
Audio (WAV) and image (spectrogram tile PNG) forms are deterministic derivations,
materialized lazily into voicebook/ and recorded on the row — the DB is the
index, phonemes are the source of truth, files are cache.

This is the lookup layer that turns LLM output into visual audio in O(1):
  text -> [word IDs] -> cached tiles (canvas) / cached WAVs (speaker)
IDs are stable across rebuilds (alphabetical CMUdict ingestion; G2P words
append after) so an ID stream is a valid transmission format on its own.

Commands:
  init                        build the database from CMUdict (~126k rows)
  ids "text"                  text -> ID sequence (G2P-inserts unknown words)
  lookup WORD | ID            show a row
  render "text" -o strip.png  materialize words; emit tile strip + WAV
  stats
"""

import argparse
import os
import re
import sqlite3
import sys

import numpy as np
import soundfile as sf
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from word_compiler import (
    ensure_cmudict, parse_cmudict, get_phonemes_for_word, compile_word,
)

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(REPO, 'voicebook', 'wordbase.db')
TILE_DIR = os.path.join(REPO, 'voicebook', 'tiles')
CODEC_VERSION = 'v1'          # bump when phonemes.py templates change
TILE_H = 48                   # px, spectrogram rows 0-4 kHz
TILE_FRAME_MS = 10.0


def connect():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    db = sqlite3.connect(DB_PATH)
    db.execute("""CREATE TABLE IF NOT EXISTS words (
        id INTEGER PRIMARY KEY,
        word TEXT UNIQUE NOT NULL,
        phonemes TEXT NOT NULL,
        codec_version TEXT NOT NULL,
        wav_path TEXT,
        tile_path TEXT)""")
    db.execute("CREATE INDEX IF NOT EXISTS idx_word ON words(word)")
    return db


def cmd_init(args):
    db = connect()
    if db.execute("SELECT COUNT(*) FROM words").fetchone()[0] > 0 and not args.force:
        print("wordbase already initialized (use --force to rebuild)")
        return
    cmudict = parse_cmudict(ensure_cmudict())
    rows = [(word, ' '.join(ph), CODEC_VERSION)
            for word, ph in sorted(cmudict.items())]
    with db:
        if args.force:
            db.execute("DELETE FROM words")
        db.executemany(
            "INSERT OR IGNORE INTO words (word, phonemes, codec_version) VALUES (?,?,?)",
            rows)
    n = db.execute("SELECT COUNT(*) FROM words").fetchone()[0]
    print(f"wordbase: {n} words indexed -> {DB_PATH}")


def word_id(db, word: str, cmudict=None) -> int:
    """Look up a word's ID; unknown words get G2P phonemes and a new row."""
    word = word.lower()
    row = db.execute("SELECT id FROM words WHERE word=?", (word,)).fetchone()
    if row:
        return row[0]
    if cmudict is None:
        cmudict = parse_cmudict(ensure_cmudict())
    phonemes = get_phonemes_for_word(word, cmudict)
    with db:
        cur = db.execute(
            "INSERT INTO words (word, phonemes, codec_version) VALUES (?,?,?)",
            (word, ' '.join(phonemes), CODEC_VERSION))
    return cur.lastrowid


def tokenize(text: str):
    return re.findall(r"[a-zA-Z']+", text.lower())


def spectrogram_tile(audio: np.ndarray, sr: float) -> np.ndarray:
    """Word audio -> (TILE_H, frames) grayscale spectrogram, 0-4 kHz."""
    frame_len = int(sr * TILE_FRAME_MS / 1000)
    n_frames = max(1, len(audio) // frame_len)
    window = np.hanning(frame_len)
    frames = np.stack([audio[i * frame_len:(i + 1) * frame_len] * window
                       for i in range(n_frames)])
    spec = np.abs(np.fft.rfft(frames, axis=1))
    freqs = np.fft.rfftfreq(frame_len, 1 / sr)
    keep = freqs <= 4000.0
    spec = spec[:, keep].T                       # (freq, time), low at row 0
    spec = np.log1p(spec / (spec.max() or 1.0) * 40)
    spec /= spec.max() or 1.0
    # resample freq axis to TILE_H rows, flip so low frequencies at bottom
    idx = np.linspace(0, spec.shape[0] - 1, TILE_H).astype(int)
    return np.flipud(spec[idx])


def materialize(db, wid: int, cmudict) -> tuple:
    """Ensure WAV + tile PNG exist for a word ID; return (wav_path, tile_path)."""
    word, phonemes, wav_path, tile_path = db.execute(
        "SELECT word, phonemes, wav_path, tile_path FROM words WHERE id=?",
        (wid,)).fetchone()
    if wav_path and tile_path and os.path.exists(wav_path) and os.path.exists(tile_path):
        return wav_path, tile_path

    wav_path, audio = compile_word(word, cmudict)
    os.makedirs(TILE_DIR, exist_ok=True)
    tile_path = os.path.join(TILE_DIR, f"{wid}.png")
    tile = (spectrogram_tile(audio, 44100.0) * 255).astype(np.uint8)
    Image.fromarray(tile, mode='L').save(tile_path)
    with db:
        db.execute("UPDATE words SET wav_path=?, tile_path=? WHERE id=?",
                   (wav_path, tile_path, wid))
    return wav_path, tile_path


def cmd_ids(args):
    db = connect()
    cmudict = parse_cmudict(ensure_cmudict())
    ids = [word_id(db, w, cmudict) for w in tokenize(args.text)]
    print(ids)


def cmd_lookup(args):
    db = connect()
    key = args.key
    if key.isdigit():
        row = db.execute("SELECT * FROM words WHERE id=?", (int(key),)).fetchone()
    else:
        row = db.execute("SELECT * FROM words WHERE word=?", (key.lower(),)).fetchone()
    if not row:
        print("not found")
        return
    wid, word, phonemes, ver, wav, tile = row
    print(f"id={wid}  word={word!r}  phonemes=[{phonemes}]  codec={ver}")
    print(f"wav={wav or '(not materialized)'}  tile={tile or '(not materialized)'}")


def cmd_render(args):
    db = connect()
    cmudict = parse_cmudict(ensure_cmudict())
    words = tokenize(args.text)
    ids = [word_id(db, w, cmudict) for w in words]

    tiles, audios = [], []
    gap_samples = int(44100 * 0.05)
    gap_px = 2
    for wid in ids:
        wav_path, tile_path = materialize(db, wid, cmudict)
        audio, _ = sf.read(wav_path)
        audios += [audio, np.zeros(gap_samples)]
        tile = np.asarray(Image.open(tile_path), dtype=np.uint8)
        tiles += [tile, np.zeros((TILE_H, gap_px), dtype=np.uint8)]

    strip = np.concatenate(tiles, axis=1)
    Image.fromarray(strip, mode='L').save(args.output)
    audio = np.concatenate(audios)
    if args.wav:
        sf.write(args.wav, audio, 44100)
    print(f"ids: {ids}")
    print(f"tile strip: {args.output} ({strip.shape[1]}x{strip.shape[0]}px)")
    if args.wav:
        print(f"audio: {args.wav} ({len(audio) / 44100:.2f}s)")


def cmd_stats(args):
    db = connect()
    total = db.execute("SELECT COUNT(*) FROM words").fetchone()[0]
    mat = db.execute("SELECT COUNT(*) FROM words WHERE tile_path IS NOT NULL").fetchone()[0]
    print(f"{total} words indexed, {mat} materialized (wav+tile)")


def main():
    parser = argparse.ArgumentParser(description="Word <-> ID <-> visual audio database")
    sub = parser.add_subparsers(dest='cmd', required=True)

    p = sub.add_parser('init'); p.add_argument('--force', action='store_true')
    p = sub.add_parser('ids'); p.add_argument('text')
    p = sub.add_parser('lookup'); p.add_argument('key')
    p = sub.add_parser('render')
    p.add_argument('text')
    p.add_argument('-o', '--output', default='strip.png')
    p.add_argument('-w', '--wav', default=None)
    sub.add_parser('stats')

    args = parser.parse_args()
    {'init': cmd_init, 'ids': cmd_ids, 'lookup': cmd_lookup,
     'render': cmd_render, 'stats': cmd_stats}[args.cmd](args)


if __name__ == '__main__':
    main()
