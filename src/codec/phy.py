"""
codec/phy.py — Unified 16-tone MFSK Physical Layer.

TASK_S001: Replace all ad-hoc spectral codecs with this proven PHY.
Based on speak.py's 16-tone MFSK which already round-trips all bytes 0-255.

Spec:
- 16 equally-spaced tones: 800 Hz to 3050 Hz (150 Hz step)
- 1 symbol = 4 bits (nibble), encoded as 20ms tone burst
- 1 byte = 2 symbols (high nibble, low nibble)
- Raw throughput: 100 bytes/sec (50 symbols/sec)
- Effective throughput: ~24 bytes/sec with frame overhead (8 bytes) and guard intervals

Why this spacing: 150 Hz is 10-30x above a 46ms window's ~21 Hz resolution,
so adjacent bytes (e.g., space=0x20 vs !=0x33) don't spectrally leak.
The 128-band log scheme failed because low bytes were single-digit Hz apart.

Reference: tools/speak.py lines 39-41, 46-47, 134-143 (encode/decode).
"""

import numpy as np
import struct
import binascii
from typing import Tuple, List
import soundfile as sf


class Phy16Tone:
    """
    16-tone MFSK Physical Layer.

    Encodes bytes to audio using 16 equally-spaced frequency tones.
    Decodes audio back to bytes using matched filtering.
    """

    # PHY parameters (from speak.py, proven working)
    SAMPLE_RATE = 44100
    SYMBOL_SEC = 0.020          # 20 ms per symbol
    TONE_BASE = 800.0           # Hz for nibble 0x0
    TONE_STEP = 150.0           # Hz between adjacent nibbles
    NUM_TONES = 16              # 0x0 to 0xF

    @classmethod
    def tone_for(cls, nibble: int) -> float:
        """Get frequency in Hz for a 4-bit nibble value."""
        if not (0 <= nibble < cls.NUM_TONES):
            raise ValueError(f"nibble must be 0-15, got {nibble}")
        return cls.TONE_BASE + cls.TONE_STEP * nibble

    @classmethod
    def nibble_for(cls, frequency: float) -> int:
        """Get nearest nibble value for a frequency in Hz."""
        offset = frequency - cls.TONE_BASE
        nibble = round(offset / cls.TONE_STEP)
        return int(np.clip(nibble, 0, cls.NUM_TONES - 1))

    @classmethod
    def bytes_to_symbols(cls, data: bytes) -> List[int]:
        """
        Convert bytes to symbol sequence (nibbles).

        Each byte becomes two symbols: high nibble first, then low nibble.
        """
        symbols = []
        for b in data:
            symbols.append(b >> 4)     # high nibble
            symbols.append(b & 0x0F)   # low nibble
        return symbols

    @classmethod
    def symbols_to_bytes(cls, symbols: List[int]) -> bytes:
        """
        Convert symbol sequence (nibbles) back to bytes.

        Paired symbols: high nibble + low nibble = byte.
        Odd-length sequences drop the last symbol.
        """
        if len(symbols) % 2:
            symbols = symbols[:-1]
        return bytes((symbols[i] << 4) | symbols[i + 1]
                    for i in range(0, len(symbols), 2))

    @classmethod
    def encode_symbols(cls, symbols: List[int]) -> np.ndarray:
        """
        Encode symbol sequence to audio waveform.

        Each symbol is a 20ms tone burst at the mapped frequency.

        Args:
            symbols: List of nibble values (0-15)

        Returns:
            Audio samples at SAMPLE_RATE
        """
        sym_len = int(cls.SAMPLE_RATE * cls.SYMBOL_SEC)
        total_samples = len(symbols) * sym_len
        audio = np.zeros(total_samples)

        t = np.arange(sym_len) / cls.SAMPLE_RATE

        for i, sym in enumerate(symbols):
            freq = cls.tone_for(sym)
            tone = np.sin(2 * np.pi * freq * t)
            audio[i * sym_len:(i + 1) * sym_len] = tone

        return audio

    @classmethod
    def decode_symbols(cls, audio: np.ndarray) -> List[int]:
        """
        Decode audio waveform to symbol sequence.

        Uses matched filtering: correlate each window against all 16 tone templates.

        Args:
            audio: Audio samples at SAMPLE_RATE

        Returns:
            List of nibble values (0-15)
        """
        sym_len = int(cls.SAMPLE_RATE * cls.SYMBOL_SEC)
        n_syms = len(audio) // sym_len

        # Analyze center 50% of each symbol window for stability
        lo, hi = int(sym_len * 0.25), int(sym_len * 0.75)
        win = hi - lo
        t = np.arange(win) / cls.SAMPLE_RATE

        # Build tone probes: all 16 frequencies
        tones = np.array([cls.tone_for(n) for n in range(cls.NUM_TONES)])
        probe = np.exp(-2j * np.pi * tones[:, None] * t[None, :])  # 16 x win

        # Extract windows and correlate
        windows = np.stack([audio[i * sym_len + lo: i * sym_len + hi]
                           for i in range(n_syms)])
        scores = np.abs(windows @ probe.T)  # n_syms x 16

        # Best match for each window
        symbols = scores.argmax(axis=1).tolist()

        return symbols

    @classmethod
    def encode(cls, data: bytes) -> np.ndarray:
        """
        Encode bytes to audio waveform.

        Args:
            data: Bytes to encode

        Returns:
            Audio samples at SAMPLE_RATE
        """
        symbols = cls.bytes_to_symbols(data)
        return cls.encode_symbols(symbols)

    @classmethod
    def decode(cls, audio: np.ndarray) -> bytes:
        """
        Decode audio waveform to bytes.

        Args:
            audio: Audio samples at SAMPLE_RATE

        Returns:
            Decoded bytes
        """
        symbols = cls.decode_symbols(audio)
        return cls.symbols_to_bytes(symbols)


# Frame format: from speak.py
# magic 'UA' | uint16 payload length | payload | crc32
MAGIC = b'UA'


def frame(payload: bytes) -> bytes:
    """
    Frame payload with magic, length, and CRC.

    Args:
        payload: Data bytes to frame

    Returns:
        Framed bytes
    """
    if len(payload) > 0xFFFF:
        raise ValueError("payload too large for uint16 length field")
    crc = binascii.crc32(payload) & 0xFFFFFFFF
    return MAGIC + struct.pack('>H', len(payload)) + payload + struct.pack('>I', crc)


def unframe(framed: bytes) -> Tuple[bytes, bool]:
    """
    Unframe payload, validate magic and CRC.

    Args:
        framed: Framed bytes

    Returns:
        Tuple of (payload, is_valid)
    """
    if len(framed) < 8:  # magic(2) + len(2) + crc(4) min
        return bytes(), False

    if framed[:2] != MAGIC:
        return bytes(), False

    try:
        (length,) = struct.unpack('>H', framed[2:4])
        if len(framed) < 8 + length:
            return bytes(), False

        payload = framed[4:4 + length]
        (crc,) = struct.unpack('>I', framed[4 + length:8 + length])
        actual = binascii.crc32(payload) & 0xFFFFFFFF

        return payload, (crc == actual)
    except (struct.error, IndexError):
        return bytes(), False


def encode_framed(data: bytes, wav_path: str) -> None:
    """
    Encode data with framing and save to WAV.

    Args:
        data: Bytes to encode
        wav_path: Output WAV file path
    """
    framed = frame(data)
    audio = Phy16Tone.encode(framed)
    sf.write(wav_path, audio, Phy16Tone.SAMPLE_RATE)


def decode_framed(wav_path: str) -> Tuple[bytes, bool]:
    """
    Decode WAV file with framing, validate CRC.

    Args:
        wav_path: Input WAV file path

    Returns:
        Tuple of (payload, is_valid)
    """
    audio, sr = sf.read(wav_path)
    if sr != Phy16Tone.SAMPLE_RATE:
        raise ValueError(f"unexpected sample rate: {sr} (expected {Phy16Tone.SAMPLE_RATE})")

    if audio.ndim > 1:
        audio = audio.mean(axis=1)

    framed = Phy16Tone.decode(audio)
    return unframe(framed)


if __name__ == '__main__':
    # Self-test: round-trip all byte values
    import sys
    import tempfile
    import os

    print("PHY16Tone self-test...")
    print(f"  Tones: {Phy16Tone.NUM_TONES} ({Phy16Tone.TONE_BASE} - {Phy16Tone.tone_for(15):.0f} Hz)")
    print(f"  Symbol time: {Phy16Tone.SYMBOL_SEC*1000:.0f} ms")
    print(f"  Throughput: {1/Phy16Tone.SYMBOL_SEC * 2:.1f} bytes/sec")

    # Test 1: All byte values (0-255)
    all_bytes = bytes(range(256))
    print(f"\nTest 1: Round-trip all 256 byte values...")
    audio = Phy16Tone.encode(all_bytes)
    decoded = Phy16Tone.decode(audio)
    errors = sum(1 for i, (a, d) in enumerate(zip(all_bytes, decoded)) if a != d)
    if errors == 0:
        print(f"  ✓ PASS: All 256 bytes round-tripped correctly")
    else:
        print(f"  ✗ FAIL: {errors} errors")
        sys.exit(1)

    # Test 2: Framed round-trip
    test_data = b'Hello, World!' + bytes(range(100))
    print(f"\nTest 2: Framed round-trip ({len(test_data)} bytes)...")
    with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f:
        wav_path = f.name
    try:
        encode_framed(test_data, wav_path)
        payload, valid = decode_framed(wav_path)
        if valid and payload == test_data:
            print(f"  ✓ PASS: Framed data round-tripped correctly")
        else:
            print(f"  ✗ FAIL: valid={valid}, payload match={payload == test_data}")
            sys.exit(1)
    finally:
        os.unlink(wav_path)

    print("\n✓ All tests passed")