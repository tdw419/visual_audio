#!/usr/bin/env python3
"""
Fountain Code Tests - TASK_R018
Tests for LT fountain code error correction on lossy channels.

Uses src.codec.fountain for Luby Transform (LT) fountain codes with CRC-32
packet integrity, Gaussian elimination fallback for trapped symbols, and
optional XChaCha20-Poly1305 encryption.

Reference: /home/jericho/zion/docs/research/Video Container Virtual Machines.md
- Wirehair-like LT fountain codes: endless repair packets, decode from N > K
- XChaCha20-Poly1305 encryption for authenticated packets
- CRC-32 packet validation (built into packet format)
- Bit-exact recovery after lossy transcoding (YouTube VP9 simulation)
"""

import pytest
import hashlib
import zlib
import os
import struct
from typing import List, Optional

from src.codec.fountain import (
    Encoder,
    Decoder,
    encode_packets,
    decode_from_packets,
    PACKET_HEADER_FMT,
    PACKET_FLAG_EXT,
    CRC_LEN,
)

try:
    from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
    HAS_CRYPTO = True
except ImportError:
    HAS_CRYPTO = False


class TestFountainCodeBasics:
    """Test basic fountain code encoding/decoding."""

    def test_generate_repair_packets(self):
        """Generate repair packets from source data."""
        source = b"hello world this is test data" * 10  # 270 bytes

        # Create encoder
        encoder = Encoder(source)
        assert encoder is not None
        assert encoder.K >= 1

        # Generate repair packets
        packets = []
        for i in range(20):
            packet = encoder.encode(i)
            packets.append(packet)
            assert len(packet) > 0

        # Verify we can generate many more packets
        for i in range(20, 100):
            packet = encoder.encode(i)
            packets.append(packet)
            assert len(packet) > 0

        assert len(packets) == 100

    def test_decode_from_subset(self):
        """Decode original data from subset of packets."""
        source = b"hello world this is test data" * 10  # 270 bytes
        source_hash = hashlib.sha256(source).hexdigest()

        # Create encoder
        encoder = Encoder(source)

        # Generate repair packets
        packets = [encoder.encode(i) for i in range(50)]

        # Simulate packet loss: drop 40% of packets
        import random
        random.seed(42)
        surviving = [p for p in packets if random.random() > 0.4]

        # Decode
        decoder = Decoder(encoder.K, encoder.symbol_size)
        for packet_id, packet in enumerate(surviving):
            decoder.decode(packet_id, packet)

        # Recover data
        recovered = decoder.recover()
        assert recovered is not None

        # Verify bit-exact recovery
        recovered_hash = hashlib.sha256(recovered).hexdigest()
        assert recovered_hash == source_hash
        assert recovered == source


class TestEncryptionIntegration:
    """Test XChaCha20-Poly1305 encryption with fountain codes."""

    @pytest.mark.skipif(not HAS_CRYPTO, reason="cryptography not installed")
    def test_packet_encryption_decryption(self):
        """Encrypt individual fountain packets with AEAD."""
        key = ChaCha20Poly1305.generate_key()
        cipher = ChaCha20Poly1305(key)

        packet_data = b"this is a fountain packet"
        nonce = os.urandom(12)  # XChaCha20 requires 12-byte nonce

        # Encrypt
        ciphertext = cipher.encrypt(nonce, packet_data, None)
        assert len(ciphertext) > len(packet_data)  # Adds authentication tag

        # Decrypt
        decrypted = cipher.decrypt(nonce, ciphertext, None)
        assert decrypted == packet_data

    @pytest.mark.skipif(not HAS_CRYPTO, reason="cryptography not installed")
    def test_encrypted_fountain_recovery(self):
        """Full pipeline: encode -> encrypt -> lose packets -> decrypt -> recover."""
        source = b"hello world this is test data" * 10  # 270 bytes
        source_hash = hashlib.sha256(source).hexdigest()

        key = ChaCha20Poly1305.generate_key()
        cipher = ChaCha20Poly1305(key)

        # Encode using our fountain code
        from src.codec.fountain import encrypt_packets, decrypt_packets

        encoder = Encoder(source)
        packets = [encoder.encode(i) for i in range(50)]

        # Encrypt
        encrypted = encrypt_packets(packets, key)

        # Simulate loss: drop 50%
        import random
        random.seed(42)
        surviving = [(n, p) for n, p in encrypted if random.random() > 0.5]

        # Decrypt
        decrypted = decrypt_packets(surviving, key)

        # Recover
        recovered = decode_from_packets(decrypted, encoder.K, encoder.symbol_size)
        assert recovered is not None

        # Verify bit-exact
        recovered_hash = hashlib.sha256(recovered).hexdigest()
        assert recovered_hash == source_hash
        assert recovered == source


class TestLossyChannelSimulation:
    """Simulate YouTube VP9 transcoding and verify recovery."""

    def test_simulate_youtube_transcoding(self):
        """Simulate aggressive lossy transcoding and recover."""
        # Original data: 1KB payload
        source = os.urandom(1024)
        source_hash = hashlib.sha256(source).hexdigest()

        # Encode with fountain codes
        encoder = Encoder(source)
        packets = [encoder.encode(i) for i in range(100)]

        # Simulate YouTube transcoding: 70% packet loss + 10% corruption
        import random
        random.seed(42)

        surviving_raw = []
        for i, packet in enumerate(packets):
            if random.random() > 0.7:  # 30% survive
                # 10% corruption chance
                if random.random() < 0.1:
                    # Corrupt a random byte
                    packet = bytearray(packet)
                    if len(packet) > 1:
                        packet[random.randint(0, len(packet) - 1)] ^= 0xFF
                    packet = bytes(packet)
                surviving_raw.append(packet)

        # Decode (CRC validation is built into Decoder.decode)
        decoder = Decoder(encoder.K, encoder.symbol_size)
        valid_count = 0
        for packet_id, packet in enumerate(surviving_raw):
            if decoder.decode(packet_id, packet):
                valid_count += 1

        # Recover
        recovered = decoder.recover()
        assert recovered is not None, (
            f"Failed to recover from {len(surviving_raw)} packets "
            f"({valid_count} valid after CRC filtering)"
        )

        # Verify bit-exact recovery
        recovered_hash = hashlib.sha256(recovered).hexdigest()
        assert recovered_hash == source_hash


class TestLargeFileRecovery:
    """Test fountain codes with realistic container file sizes."""

    def test_recover_large_file(self):
        """Recover large file (~100KB) with aggressive packet loss."""
        source = os.urandom(100 * 1024)  # 100KB
        source_hash = hashlib.sha256(source).hexdigest()

        # Encode with 1KB symbols
        encoder = Encoder(source, symbol_size=1024)

        # Generate enough packets for 80% loss with LT code overhead
        packets = [encoder.encode(i) for i in range(800)]

        # Simulate 80% loss (aggressive)
        import random
        random.seed(42)
        surviving = [p for p in packets if random.random() > 0.8]

        # Recover
        decoder = Decoder(encoder.K, encoder.symbol_size)
        for packet_id, packet in enumerate(surviving):
            decoder.decode(packet_id, packet)

        recovered = decoder.recover()
        assert recovered is not None, (
            f"Only recovered {sum(1 for s in decoder._recovered if s is not None)}/"
            f"{encoder.K} symbols from {len(surviving)} packets"
        )

        # Verify bit-exact
        recovered_hash = hashlib.sha256(recovered).hexdigest()
        assert recovered_hash == source_hash


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
