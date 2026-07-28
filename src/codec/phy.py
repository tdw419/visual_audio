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
from typing import Tuple, List, Optional
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


# Frame formats
# Unauthenticated: magic 'UA' | uint16 payload length | payload | crc32
# Authenticated:   magic 'VA' | uint16 total length | uint16 payload length | payload | signature (64 bytes) | timestamp (8 bytes) | crc32
MAGIC_UNAUTH = b'UA'
MAGIC_AUTH = b'VA'

# Constants for authenticated frames
SIGNATURE_LENGTH = 64  # Ed25519 signature length
TIMESTAMP_LENGTH = 8   # Unix timestamp (int64)
TIMESTAMP_MAX_AGE_SECONDS = 300  # Reject signatures older than 5 minutes


def frame(payload: bytes) -> bytes:
    """
    Frame payload with magic, length, and CRC (unauthenticated).
    Large payloads are chunked into multiple frames.

    Args:
        payload: Data bytes to frame

    Returns:
        Framed bytes (concatenated frames)
    """
    # Max payload per frame (uint16) minus any needed overhead
    MAX_CHUNK = 0xFFFF
    chunks = []
    offset = 0

    while offset < len(payload):
        chunk = payload[offset:offset + MAX_CHUNK]
        crc = binascii.crc32(chunk) & 0xFFFFFFFF
        frame_data = MAGIC_UNAUTH + struct.pack('>H', len(chunk)) + chunk + struct.pack('>I', crc)
        chunks.append(frame_data)
        offset += len(chunk)

    return b''.join(chunks)


def frame_authenticated(payload: bytes, signature: bytes, timestamp: Optional[int] = None) -> bytes:
    """
    Frame payload with Ed25519 signature and timestamp for provenance.
    Large payloads are chunked into multiple frames.

    Frame format: 'VA' | total_len | payload_len | payload | signature | timestamp | crc

    Args:
        payload: Data bytes to frame (typically JSON ops)
        signature: Ed25519 signature (64 bytes) of payload
        timestamp: Unix timestamp (default: current time)

    Returns:
        Authenticated framed bytes (concatenated frames)

    Raises:
        ValueError: If signature is not 64 bytes
    """
    if len(signature) != SIGNATURE_LENGTH:
        raise ValueError(f"signature must be {SIGNATURE_LENGTH} bytes, got {len(signature)}")

    if timestamp is None:
        import time
        timestamp = int(time.time())

    # Pack timestamp as big-endian int64
    timestamp_bytes = struct.pack('>Q', timestamp)

    # Max payload per frame (uint16) minus any needed overhead
    MAX_CHUNK = 0xFFFF
    chunks = []
    offset = 0

    while offset < len(payload):
        chunk = payload[offset:offset + MAX_CHUNK]

        # Build authenticated frame
        total_len = len(chunk) + SIGNATURE_LENGTH + TIMESTAMP_LENGTH
        frame_data = (
            MAGIC_AUTH +
            struct.pack('>H', total_len) +
            struct.pack('>H', len(chunk)) +
            chunk +
            signature +
            timestamp_bytes
        )

        # CRC covers everything except the CRC itself
        crc = binascii.crc32(frame_data) & 0xFFFFFFFF
        chunks.append(frame_data + struct.pack('>I', crc))
        offset += len(chunk)

    return b''.join(chunks)


def unframe(framed: bytes) -> Tuple[bytes, bool]:
    """
    Unframe payload(s), validate magic and CRC (unauthenticated mode).
    Handles multiple concatenated frames.

    Args:
        framed: Framed bytes (possibly multiple frames concatenated)

    Returns:
        Tuple of (concatenated_payloads, is_valid)
    """
    if len(framed) < 8:  # magic(2) + len(2) + crc(4) min
        return bytes(), False

    payloads = []
    offset = 0
    valid = True

    while offset + 8 <= len(framed):
        # Check magic
        if framed[offset:offset + 2] != MAGIC_UNAUTH:
            return bytes(), False

        try:
            (length,) = struct.unpack('>H', framed[offset + 2:offset + 4])
            if offset + 8 + length > len(framed):
                # Incomplete frame
                break

            payload = framed[offset + 4:offset + 4 + length]
            (crc,) = struct.unpack('>I', framed[offset + 4 + length:offset + 8 + length])
            actual = binascii.crc32(payload) & 0xFFFFFFFF

            if crc != actual:
                valid = False

            payloads.append(payload)
            offset += 8 + length
        except (struct.error, IndexError):
            valid = False
            break

    return b''.join(payloads), valid and len(payloads) > 0


def unframe_authenticated(framed: bytes, public_key_path: str) -> Tuple[bytes, bool, str]:
    """
    Unframe and verify authenticated payload with Ed25519 signature.
    Handles multiple concatenated frames.

    Args:
        framed: Authenticated framed bytes (possibly multiple frames concatenated)
        public_key_path: Path to Ed25519 public key for verification

    Returns:
        Tuple of (concatenated_payloads, is_valid, error_message)

    error_message is empty string on success, contains reason on failure.
    """
    import time
    from cryptography.hazmat.primitives.asymmetric import ed25519
    from cryptography.hazmat.primitives import serialization
    from cryptography.exceptions import InvalidSignature

    # Minimum size: magic(2) + total_len(2) + payload_len(2) + sig(64) + timestamp(8) + crc(4)
    min_size = 2 + 2 + 2 + SIGNATURE_LENGTH + TIMESTAMP_LENGTH + 4
    if len(framed) < min_size:
        return bytes(), False, "frame too short"

    payloads = []
    offset = 0
    errors = []
    valid = True

    # Load public key once
    try:
        with open(public_key_path, 'rb') as f:
            public_key = serialization.load_pem_public_key(f.read())
    except FileNotFoundError:
        return bytes(), False, f"public key not found: {public_key_path}"
    except Exception as e:
        return bytes(), False, f"failed to load public key: {e}"

    now = int(time.time())

    while offset + min_size <= len(framed):
        # Check magic
        if framed[offset:offset + 2] != MAGIC_AUTH:
            return bytes(), False, "invalid magic (not an authenticated frame)"

        try:
            # Parse frame structure
            (total_len,) = struct.unpack('>H', framed[offset + 2:offset + 4])
            (payload_len,) = struct.unpack('>H', framed[offset + 4:offset + 6])

            # Calculate expected frame size
            expected_size = offset + 6 + total_len + 4  # offset + header + data + crc
            if expected_size > len(framed):
                # Incomplete frame
                break

            # Extract components
            payload = framed[offset + 6:offset + 6 + payload_len]
            signature = framed[offset + 6 + payload_len:offset + 6 + payload_len + SIGNATURE_LENGTH]
            timestamp_bytes = framed[offset + 6 + payload_len + SIGNATURE_LENGTH:offset + 6 + payload_len + SIGNATURE_LENGTH + TIMESTAMP_LENGTH]
            received_crc_bytes = framed[offset + 6 + payload_len + SIGNATURE_LENGTH + TIMESTAMP_LENGTH:offset + 6 + total_len + 4]

            # Verify CRC over everything except CRC itself
            frame_data = framed[offset:offset + 6 + payload_len + SIGNATURE_LENGTH + TIMESTAMP_LENGTH]
            expected_crc = binascii.crc32(frame_data) & 0xFFFFFFFF
            (received_crc,) = struct.unpack('>I', received_crc_bytes)

            if received_crc != expected_crc:
                errors.append(f"CRC mismatch: expected {expected_crc:#010x}, got {received_crc:#010x}")
                valid = False
                offset += 6 + total_len + 4
                continue

            # Verify timestamp freshness (replay protection)
            (timestamp,) = struct.unpack('>Q', timestamp_bytes)
            age = now - timestamp

            if age < 0:
                errors.append(f"timestamp from future: {timestamp} > {now}")
                valid = False
                offset += 6 + total_len + 4
                continue
            if age > TIMESTAMP_MAX_AGE_SECONDS:
                errors.append(f"timestamp too old: {age}s (max {TIMESTAMP_MAX_AGE_SECONDS}s)")
                valid = False
                offset += 6 + total_len + 4
                continue

            # Verify Ed25519 signature
            try:
                public_key.verify(signature, payload)
                payloads.append(payload)
            except InvalidSignature:
                errors.append("invalid Ed25519 signature")
                valid = False

            offset += 6 + total_len + 4

        except (struct.error, IndexError) as e:
            errors.append(f"frame parsing error: {e}")
            valid = False
            break
        except Exception as e:
            errors.append(f"verification error: {e}")
            valid = False
            break

    error_msg = "; ".join(errors) if errors else ""
    return b''.join(payloads), valid and len(payloads) > 0, error_msg


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