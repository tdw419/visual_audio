#!/usr/bin/env python3
"""
test_boot_over_air.py — the signed boot channel survives a realistic acoustic
path, and its security properties hold across that path.

No QEMU and no audio hardware here: these exercise encode -> channel -> decode
(+Ed25519 verify). The full boot is demonstrated by tools/boot_over_air.py.
"""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'tools'))

import numpy as np
import soundfile as sf

from spoken_screen import utter, decode_data_band
from boot_over_air import simulate_channel

KEYS = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'keys')
PRIV = os.path.join(KEYS, 'pixel_os_private.pem')
PUB = os.path.join(KEYS, 'pixel_os_public.pem')
OP = ["boot", "riscv64", "hello.img"]


def _signed_wav(tmp_path):
    wav = os.path.join(tmp_path, 'boot.wav')
    utter("boot hello", [OP], wav, private_key_path=PRIV)
    a, sr = sf.read(wav)
    return (a.mean(axis=1) if a.ndim > 1 else a), sr


def _decode(a, sr, key=PUB):
    return json.loads(decode_data_band(a, sr, key).decode('utf-8'))


def test_survives_realistic_channel(tmp_path):
    """±100 ppm drift, 15 dB SNR — well within consumer sound-card tolerance."""
    clean, sr = _signed_wav(str(tmp_path))
    for seed in range(5):  # not flaky across noise realizations
        recv = simulate_channel(clean, sr, noise_db=15, drift_ppm=100, seed=seed)
        assert _decode(recv, sr) == [OP], f"failed at seed {seed}"


def test_robust_to_low_snr_and_clipping(tmp_path):
    clean, sr = _signed_wav(str(tmp_path))
    # 0 dB SNR: matched-filter FSK still recovers every symbol.
    assert _decode(simulate_channel(clean, sr, noise_db=0, drift_ppm=0, seed=1), sr) == [OP]
    # Hard clipping preserves the dominant tone.
    assert _decode(np.clip(clean, -0.1, 0.1), sr) == [OP]


def test_gross_clock_drift_is_rejected(tmp_path):
    """Documents the real failure mode: ~0.3% clock mismatch corrupts symbol
    timing, and the CRC/signature correctly refuses it rather than booting garbage."""
    clean, sr = _signed_wav(str(tmp_path))
    try:
        _decode(simulate_channel(clean, sr, noise_db=40, drift_ppm=3000, seed=1), sr)
        assert False, "3000 ppm drift should not verify"
    except ValueError:
        pass


def test_payload_tampering_rejected_over_channel(tmp_path):
    """Provenance holds across the channel: a tampered high band fails to verify."""
    clean, sr = _signed_wav(str(tmp_path))
    recv = simulate_channel(clean, sr, noise_db=30, drift_ppm=0, seed=2)
    # Corrupt a chunk squarely in the data band region (second half of the signal).
    recv = recv.copy()
    mid = len(recv) // 2
    recv[mid:mid + 4000] += 0.5 * np.sin(2 * np.pi * 6000 * np.arange(4000) / sr)
    try:
        _decode(recv, sr)
        assert False, "tampered payload should not verify"
    except ValueError:
        pass


def test_unsigned_boot_rejected_over_channel(tmp_path):
    """An unsigned utterance cannot boot even if it survives the channel cleanly."""
    wav = os.path.join(str(tmp_path), 'legacy.wav')
    utter("boot hello", [OP], wav, private_key_path=None)  # legacy/unsigned
    a, sr = sf.read(wav)
    a = a.mean(axis=1) if a.ndim > 1 else a
    try:
        _decode(simulate_channel(a, sr, noise_db=30, drift_ppm=0, seed=3), sr, key=PUB)
        assert False, "unsigned frame must be rejected when a key is required"
    except ValueError:
        pass


if __name__ == '__main__':
    import pytest
    sys.exit(pytest.main([__file__, '-v']))
