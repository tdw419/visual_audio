#!/usr/bin/env python3
"""
wav_sector_container.py — WAV-native sector-addressable disk container (BL004).

Wraps an arbitrary binary (a disk image) in a minimal, valid RIFF/WAVE file
whose `data` chunk is the original bytes UNMODIFIED. Because the data chunk
is byte-identical to the source, any sector at disk offset `i * sector_size`
lives at WAV file offset `44 + i * sector_size` (44 = size of this minimal
header: RIFF+size+WAVE+fmt chunk(24B)+data chunk header(8B)) and can be
recovered with a single HTTP Range request against the .wav file — no audio
decoding (decodeAudioData) needed, since we read the header ourselves and
slice raw PCM bytes directly. This trades "sounds intelligible" for "byte-
exact, sector-addressable, real .wav file" — the disk's bytes are declared
as 16-bit PCM samples purely to produce a spec-valid RIFF/WAVE container;
playing it back will sound like static, not speech (unlike this repo's
dual_band.py/sonic_codec.py, which encode small payloads as modulated,
listenable audio — not usable here: BL004 needs O(10 MB) throughput with
trivial random-access decode, which FSK/phoneme modulation does not provide).

A JSON sidecar manifest carries the sha256 of the original file, sector
size, sector count, and a per-sector CRC32 (reusing dense_encoder.py's
crc32 convention) — kept OUT of the WAV data chunk so sector byte offsets
stay a pure `44 + i*sector_size` computation.
"""
import argparse
import hashlib
import json
import os
import struct
import sys
import zlib

HEADER_SIZE = 44  # standard minimal WAV/RIFF header size


def build_wav_header(data_len: int, sample_rate: int = 44100, bits_per_sample: int = 16, channels: int = 1) -> bytes:
    byte_rate = sample_rate * channels * bits_per_sample // 8
    block_align = channels * bits_per_sample // 8
    return (
        b'RIFF' + struct.pack('<I', 36 + data_len) + b'WAVE'
        + b'fmt ' + struct.pack('<IHHIIHH', 16, 1, channels, sample_rate, byte_rate, block_align, bits_per_sample)
        + b'data' + struct.pack('<I', data_len)
    )


def encode(input_path: str, wav_path: str, manifest_path: str, sector_size: int = 8192) -> dict:
    with open(input_path, 'rb') as f:
        data = f.read()
    header = build_wav_header(len(data))
    assert len(header) == HEADER_SIZE, f"header size drifted: {len(header)}"
    with open(wav_path, 'wb') as f:
        f.write(header)
        f.write(data)

    n_sectors = (len(data) + sector_size - 1) // sector_size
    sector_crcs = []
    for i in range(n_sectors):
        chunk = data[i * sector_size:(i + 1) * sector_size]
        sector_crcs.append(zlib.crc32(chunk) & 0xFFFFFFFF)

    manifest = {
        'original_file': os.path.basename(input_path),
        'original_size': len(data),
        'sha256': hashlib.sha256(data).hexdigest(),
        'sector_size': sector_size,
        'n_sectors': n_sectors,
        'header_size': HEADER_SIZE,
        'sector_crc32': sector_crcs,
    }
    with open(manifest_path, 'w') as f:
        json.dump(manifest, f)
    return manifest


def decode(wav_path: str, manifest_path: str, out_path: str) -> bool:
    with open(manifest_path) as f:
        manifest = json.load(f)
    with open(wav_path, 'rb') as f:
        f.seek(manifest['header_size'])
        data = f.read(manifest['original_size'])
    with open(out_path, 'wb') as f:
        f.write(data)
    return hashlib.sha256(data).hexdigest() == manifest['sha256']


def read_sector(wav_path: str, manifest_path: str, index: int) -> bytes:
    """Read one sector via seek (simulates what an HTTP Range GET returns)."""
    with open(manifest_path) as f:
        manifest = json.load(f)
    sector_size = manifest['sector_size']
    offset = manifest['header_size'] + index * sector_size
    length = min(sector_size, manifest['original_size'] - index * sector_size)
    with open(wav_path, 'rb') as f:
        f.seek(offset)
        chunk = f.read(length)
    expect_crc = manifest['sector_crc32'][index]
    got_crc = zlib.crc32(chunk) & 0xFFFFFFFF
    if got_crc != expect_crc:
        raise ValueError(f"sector {index}: CRC mismatch (expected {expect_crc:#010x}, got {got_crc:#010x})")
    return chunk


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='cmd', required=True)

    pe = sub.add_parser('encode')
    pe.add_argument('input')
    pe.add_argument('wav')
    pe.add_argument('manifest')
    pe.add_argument('--sector-size', type=int, default=8192)

    pd = sub.add_parser('decode')
    pd.add_argument('wav')
    pd.add_argument('manifest')
    pd.add_argument('output')

    pv = sub.add_parser('verify')
    pv.add_argument('wav')
    pv.add_argument('manifest')

    args = p.parse_args()
    if args.cmd == 'encode':
        m = encode(args.input, args.wav, args.manifest, args.sector_size)
        print(f"Encoded {m['original_size']} bytes -> {args.wav} ({m['n_sectors']} sectors of {m['sector_size']}B)")
        print(f"sha256={m['sha256']}")
    elif args.cmd == 'decode':
        ok = decode(args.wav, args.manifest, args.output)
        print(f"Decoded to {args.output}; sha256 match: {ok}")
        sys.exit(0 if ok else 1)
    elif args.cmd == 'verify':
        with open(args.manifest) as f:
            manifest = json.load(f)
        bad = 0
        for i in range(manifest['n_sectors']):
            try:
                read_sector(args.wav, args.manifest, i)
            except ValueError as e:
                bad += 1
                print(e)
        print(f"Verified {manifest['n_sectors']} sectors, {bad} CRC mismatches")
        sys.exit(1 if bad else 0)
