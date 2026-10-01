#!/usr/bin/env python3
"""
boot_over_air.py — Boot an OS from a *signed* utterance carried over audio.

This ties the three verified pieces together into one flow:

    signed boot manifest  ->  dual-band WAV (spoken_screen.utter)
        ->  [ acoustic channel ]  ->  decode_data_band (Ed25519 verified)
        ->  boot_manifest.launch_boot  ->  QEMU boots the named image

Two channels:
  --simulate   applies a software model of a real speaker->mic path (attenuation,
               reverb, noise, clock drift). Runs anywhere; used as the acceptance
               test here. Clock drift is the dominant failure mode — the 16-tone
               matched-filter FSK shrugs off noise/clipping/HF roll-off but a
               sample-clock mismatch beyond ~0.1-0.3% corrupts symbol timing.
  --play       plays the WAV through the real speakers (aplay) and records from
               the microphone (arecord), then decodes+verifies+boots. This is the
               genuine air-gap test; it needs working audio hardware.

The provenance gate is mandatory: only a signature that verifies against the
public key is allowed to launch QEMU, so an unsigned tone blast off a phone can't
boot the machine.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile

import numpy as np
import soundfile as sf

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from spoken_screen import utter, decode_data_band, SAMPLE_RATE
import boot_manifest


def simulate_channel(audio, sr, *, noise_db=15.0, drift_ppm=100.0,
                     echo=0.25, atten=0.8, seed=None):
    """Model a real speaker->mic path: attenuation, 50ms reverb, white noise
    at the given SNR, and a playback/record clock mismatch in ppm."""
    from scipy.signal import resample
    rng = np.random.default_rng(seed)
    a = audio * atten
    d = int(0.05 * sr)
    if d < len(a):
        e = np.zeros_like(a)
        e[d:] = a[:-d] * echo
        a = a + e
    power = np.mean(a ** 2)
    n = power / (10 ** (noise_db / 10.0))
    a = a + rng.normal(0, np.sqrt(n), a.shape)
    if drift_ppm:
        a = resample(a, int(len(a) * (1 + drift_ppm / 1e6)))
    return a


def play_and_record(wav_path, sr, duration_s):
    """Play through speakers (aplay) while recording the mic (arecord)."""
    rec = tempfile.NamedTemporaryFile(suffix='.wav', delete=False).name
    recorder = subprocess.Popen(
        ['arecord', '-f', 'S16_LE', '-r', str(sr), '-c', '1',
         '-d', str(int(duration_s) + 2), rec],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    import time
    time.sleep(0.5)
    subprocess.run(['aplay', wav_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    recorder.wait()
    audio, _ = sf.read(rec)
    os.unlink(rec)
    return audio.mean(axis=1) if audio.ndim > 1 else audio


def run(args):
    op = ["boot", args.arch, args.image]
    if args.bios or args.drive:
        opts = {}
        if args.bios:
            opts["bios"] = args.bios
        if args.drive:
            opts["drive"] = args.drive
        op.append(opts)

    wav = args.wav or tempfile.NamedTemporaryFile(suffix='.wav', delete=False).name
    print(f"1. Encoding signed boot manifest {op} -> {wav}")
    utter(f"boot {args.image}", [op], wav, private_key_path=args.private_key)

    clean, sr = sf.read(wav)
    if clean.ndim > 1:
        clean = clean.mean(axis=1)

    if args.play:
        print("2. Playing through speaker / recording from mic ...")
        received = play_and_record(wav, sr, len(clean) / sr)
    else:
        print(f"2. Simulating acoustic channel "
              f"(SNR={args.noise_db}dB, drift={args.drift_ppm}ppm) ...")
        received = simulate_channel(clean, sr, noise_db=args.noise_db,
                                    drift_ppm=args.drift_ppm, seed=args.seed)

    print("3. Decoding + verifying Ed25519 signature from received audio ...")
    ops = json.loads(decode_data_band(received, sr, args.public_key).decode('utf-8'))
    print(f"   verified ops: {ops}")

    print("4. Launching QEMU from the verified manifest ...")
    serial = args.serial or tempfile.NamedTemporaryFile(suffix='.log', delete=False).name

    def runner(argv):
        p = subprocess.Popen(argv + ['-serial', f'file:{serial}'],
                             stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            p.wait(timeout=args.timeout)
        except subprocess.TimeoutExpired:
            p.kill()

    argv = boot_manifest.launch_boot(ops[0], args.boot_image_dir,
                                     dry_run=args.dry_run, runner=runner)
    print(f"   qemu: {' '.join(argv)}")
    if args.dry_run:
        return 0

    out = open(serial).read().replace('\r', '')
    banner = out.strip().splitlines()[-3:] if out.strip() else []
    print("5. Kernel serial output (tail):")
    for line in banner:
        print("   |", line)
    ok = any(k in out for k in ("SPOKEN KERNEL", "xv6 kernel is booting"))
    print("\nRESULT:", "PASS ✅ signed audio booted the OS over the channel"
          if ok else "FAIL ❌ no kernel banner")
    return 0 if ok else 1


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--image', default='hello.img', help='image filename in --boot-image-dir')
    p.add_argument('--arch', default='riscv64')
    p.add_argument('--bios', choices=['default', 'none'], help='bios option')
    p.add_argument('--drive', help='disk image filename (riscv virtio-blk)')
    p.add_argument('--private-key', default='keys/pixel_os_private.pem')
    p.add_argument('--public-key', default='keys/pixel_os_public.pem')
    p.add_argument('--boot-image-dir', default='boot_images')
    p.add_argument('--wav', help='where to write the encoded WAV')
    p.add_argument('--serial', help='where to write qemu serial output')
    p.add_argument('--timeout', type=float, default=5.0, help='qemu run seconds')
    p.add_argument('--dry-run', action='store_true', help='validate/verify but do not launch qemu')

    ch = p.add_mutually_exclusive_group()
    ch.add_argument('--simulate', action='store_true', default=True,
                    help='software acoustic channel model (default)')
    ch.add_argument('--play', action='store_true',
                    help='real speaker->mic via aplay/arecord (needs audio hardware)')
    p.add_argument('--noise-db', type=float, default=15.0, help='simulated channel SNR (dB)')
    p.add_argument('--drift-ppm', type=float, default=100.0, help='simulated clock drift (ppm)')
    p.add_argument('--seed', type=int, default=None)

    args = p.parse_args()
    sys.exit(run(args))


if __name__ == '__main__':
    main()
