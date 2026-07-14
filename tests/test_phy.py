"""
Unit tests for codec/phy.py (TASK_S001 - Unified PHY).
"""

import pytest
import numpy as np
import tempfile
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from codec.phy import Phy16Tone, frame, unframe, encode_framed, decode_framed, MAGIC


class TestPhy16Tone:
    """Test 16-tone MFSK physical layer."""

    def test_tone_for_all_nibbles(self):
        """Test tone frequency calculation for all 16 nibbles."""
        for nibble in range(16):
            freq = Phy16Tone.tone_for(nibble)
            expected = 800.0 + 150.0 * nibble
            assert freq == expected

    def test_tone_for_invalid_nibble(self):
        """Test that invalid nibbles raise ValueError."""
        with pytest.raises(ValueError):
            Phy16Tone.tone_for(-1)
        with pytest.raises(ValueError):
            Phy16Tone.tone_for(16)

    def test_nibble_for_frequency(self):
        """Test nibble recovery from frequency."""
        for nibble in range(16):
            freq = Phy16Tone.tone_for(nibble)
            recovered = Phy16Tone.nibble_for(freq)
            assert recovered == nibble

    def test_nibble_for_clipping(self):
        """Test that nibble_for clips out-of-range frequencies."""
        assert Phy16Tone.nibble_for(0) == 0      # below base
        assert Phy16Tone.nibble_for(10000) == 15  # above max

    def test_bytes_to_symbols_single_byte(self):
        """Test byte to symbols conversion."""
        # High/low nibble pairs
        assert Phy16Tone.bytes_to_symbols(b'\x00') == [0, 0]
        assert Phy16Tone.bytes_to_symbols(b'\x0F') == [0, 15]
        assert Phy16Tone.bytes_to_symbols(b'\xF0') == [15, 0]
        assert Phy16Tone.bytes_to_symbols(b'\xFF') == [15, 15]

    def test_bytes_to_symbols_multiple_bytes(self):
        """Test multiple bytes to symbols."""
        symbols = Phy16Tone.bytes_to_symbols(b'\x12\x34')
        assert symbols == [1, 2, 3, 4]

    def test_symbols_to_bytes_single(self):
        """Test symbols to bytes conversion."""
        assert Phy16Tone.symbols_to_bytes([0, 0]) == b'\x00'
        assert Phy16Tone.symbols_to_bytes([0, 15]) == b'\x0F'
        assert Phy16Tone.symbols_to_bytes([15, 0]) == b'\xF0'
        assert Phy16Tone.symbols_to_bytes([15, 15]) == b'\xFF'

    def test_symbols_to_bytes_odd_length(self):
        """Test that odd-length symbol lists drop last symbol."""
        assert Phy16Tone.symbols_to_bytes([0, 1, 2]) == b'\x01'

    def test_bytes_symbols_roundtrip(self):
        """Test bytes -> symbols -> bytes round-trip."""
        original = bytes(range(256))
        symbols = Phy16Tone.bytes_to_symbols(original)
        recovered = Phy16Tone.symbols_to_bytes(symbols)
        assert recovered == original

    def test_encode_symbols_basic(self):
        """Test symbol encoding to audio."""
        symbols = [0, 8, 15]  # 800 Hz, 2000 Hz, 3050 Hz
        audio = Phy16Tone.encode_symbols(symbols)

        expected_len = len(symbols) * int(Phy16Tone.SAMPLE_RATE * Phy16Tone.SYMBOL_SEC)
        assert len(audio) == expected_len

        # Check first symbol is ~800 Hz tone
        sym_len = int(Phy16Tone.SAMPLE_RATE * Phy16Tone.SYMBOL_SEC)
        first_symbol = audio[:sym_len]
        # Should have energy near 800 Hz, zero elsewhere
        fft = np.abs(np.fft.rfft(first_symbol))
        freqs = np.fft.rfftfreq(len(first_symbol), 1/Phy16Tone.SAMPLE_RATE)
        peak_idx = np.argmax(fft)
        peak_freq = freqs[peak_idx]
        # Peak should be close to 800 Hz
        assert 700 < peak_freq < 900

    def test_decode_symbols_basic(self):
        """Test symbol decoding from audio."""
        symbols = [0, 8, 15]
        audio = Phy16Tone.encode_symbols(symbols)
        decoded = Phy16Tone.decode_symbols(audio)
        assert decoded == symbols

    def test_decode_all_symbols(self):
        """Test decoding all 16 possible symbols."""
        symbols = list(range(16))
        audio = Phy16Tone.encode_symbols(symbols)
        decoded = Phy16Tone.decode_symbols(audio)
        assert decoded == symbols

    def test_encode_decode_roundtrip_all_bytes(self):
        """Test round-trip of all 256 possible byte values."""
        original = bytes(range(256))
        audio = Phy16Tone.encode(original)
        decoded = Phy16Tone.decode(audio)
        assert decoded == original

    def test_encode_decode_random_data(self):
        """Test round-trip of random data."""
        np.random.seed(42)
        original = np.random.randint(0, 256, 1000, dtype=np.uint8).tobytes()
        audio = Phy16Tone.encode(original)
        decoded = Phy16Tone.decode(audio)
        assert decoded == original


class TestFraming:
    """Test frame format (magic + length + payload + CRC)."""

    def test_frame_basic(self):
        """Test basic framing."""
        payload = b'hello'
        framed = frame(payload)

        assert framed[:2] == MAGIC
        assert len(framed) >= 8  # magic(2) + len(2) + payload + crc(4)

    def test_frame_length_field(self):
        """Test length field is correct."""
        payload = b'hello world'
        framed = frame(payload)

        import struct
        (length,) = struct.unpack('>H', framed[2:4])
        assert length == len(payload)

    def test_frame_crc(self):
        """Test CRC is correct."""
        payload = b'test data'
        framed = frame(payload)

        import struct
        import binascii
        (crc,) = struct.unpack('>I', framed[4 + len(payload):8 + len(payload)])
        expected = binascii.crc32(payload) & 0xFFFFFFFF
        assert crc == expected

    def test_frame_large_payload(self):
        """Test framing fails for too-large payload."""
        payload = b'x' * 0xFFFF  # max uint16
        framed = frame(payload)  # should work

        payload = b'x' * (0xFFFF + 1)  # too large
        with pytest.raises(ValueError):
            frame(payload)

    def test_unframe_valid(self):
        """Test unframing valid data."""
        payload = b'test payload'
        framed = frame(payload)
        recovered, valid = unframe(framed)

        assert valid is True
        assert recovered == payload

    def test_unframe_bad_magic(self):
        """Test unframing fails with bad magic."""
        bad_framed = b'XX' + frame(b'test')[2:]
        recovered, valid = unframe(bad_framed)

        assert valid is False
        assert recovered == b''

    def test_unframe_bad_crc(self):
        """Test unframing fails with corrupted CRC."""
        framed = frame(b'test')
        # Corrupt CRC byte
        corrupt = framed[:-1] + bytes([framed[-1] ^ 0xFF])
        recovered, valid = unframe(corrupt)

        assert valid is False

    def test_unframe_bad_payload(self):
        """Test unframing fails with corrupted payload."""
        framed = frame(b'test')
        # Corrupt middle of payload
        corrupt = bytearray(framed)
        corrupt[6] ^= 0xFF
        recovered, valid = unframe(bytes(corrupt))

        assert valid is False


class TestFramedEncodeDecode:
    """Test encode_framed and decode_framed with WAV files."""

    def test_framed_roundtrip_small(self):
        """Test framed encode/decode with small payload."""
        payload = b'hello world'
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f:
            wav_path = f.name

        try:
            encode_framed(payload, wav_path)
            recovered, valid = decode_framed(wav_path)

            assert valid is True
            assert recovered == payload
        finally:
            os.unlink(wav_path)

    def test_framed_roundtrip_all_bytes(self):
        """Test framed encode/decode with all byte values."""
        payload = bytes(range(256))
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f:
            wav_path = f.name

        try:
            encode_framed(payload, wav_path)
            recovered, valid = decode_framed(wav_path)

            assert valid is True
            assert recovered == payload
        finally:
            os.unlink(wav_path)

    def test_framed_roundtrip_large(self):
        """Test framed encode/decode with large payload."""
        payload = b'x' * 1000
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f:
            wav_path = f.name

        try:
            encode_framed(payload, wav_path)
            recovered, valid = decode_framed(wav_path)

            assert valid is True
            assert recovered == payload
        finally:
            os.unlink(wav_path)

    def test_decode_framed_bad_sample_rate(self):
        """Test decode fails with wrong sample rate."""
        payload = b'test'
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f:
            wav_path = f.name

        try:
            # Encode at wrong rate
            import soundfile as sf
            framed = frame(payload)
            audio = Phy16Tone.encode(framed)
            sf.write(wav_path, audio, 48000)  # wrong rate

            with pytest.raises(ValueError, match="unexpected sample rate"):
                decode_framed(wav_path)
        finally:
            os.unlink(wav_path)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])