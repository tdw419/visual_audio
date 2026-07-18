#!/usr/bin/env python3
"""
Fountain Code Tests - TASK_R018
Tests for Wirehair fountain code error correction on lossy channels.

Reference: /home/jericho/zion/docs/research/Video Container Virtual Machines.md
- Wirehair fountain codes: endless repair packets, decode from N > original_size
- XChaCha20-Poly1305 encryption for authenticated packets
- CRC-32 packet validation
- Bit-exact recovery after lossy transcoding (YouTube VP9)
"""

import pytest
import hashlib
import zlib
import os
from pathlib import Path

try:
    import wirehair
    HAS_WIREHAIR = True
except ImportError:
    HAS_WIREHAIR = False

try:
    from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
    HAS_CRYPTO = True
except ImportError:
    HAS_CRYPTO = False


class TestFountainCodeBasics:
    """Test basic fountain code encoding/decoding."""

    @pytest.mark.skipif(not HAS_WIREHAIR, reason="wirehair not installed")
    def test_generate_repair_packets(self):
        """Generate endless repair packets from source data."""
        source = b"hello world this is test data" * 10  # 270 bytes

        # Create encoder
        encoder = wirehair.Encoder(b"test_seed", len(source))
        assert encoder is not None

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

    @pytest.mark.skipif(not HAS_WIREHAIR, reason="wirehair not installed")
    def test_decode_from_subset(self):
        """Decode original data from subset of packets."""
        source = b"hello world this is test data" * 10  # 270 bytes
        source_hash = hashlib.sha256(source).hexdigest()

        # Create encoder
        encoder = wirehair.Encoder(b"test_seed", len(source))

        # Generate repair packets
        packets = []
        for i in range(50):
            packets.append(encoder.encode(i))

        # Simulate packet loss: drop 40% of packets
        import random
        random.seed(42)
        surviving_packets = [p for p in packets if random.random() > 0.4]

        # Verify we have enough packets (should need slightly more than original)
        assert len(surviving_packets) > len(source)

        # Decode
        decoder = wirehair.Decoder(b"test_seed", len(source))
        for packet_id, packet in enumerate(surviving_packets):
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

    @pytest.mark.skipif(not HAS_WIREHAIR or not HAS_CRYPTO, reason="missing dependencies")
    def test_encrypted_fountain_recovery(self):
        """Full pipeline: encode → encrypt → lose packets → decrypt → recover."""
        source = b"hello world this is test data" * 10  # 270 bytes
        source_hash = hashlib.sha256(source).hexdigest()

        key = ChaCha20Poly1305.generate_key()
        cipher = ChaCha20Poly1305(key)

        # Encode
        encoder = wirehair.Encoder(b"test_seed", len(source))
        encrypted_packets = []

        for i in range(50):
            packet = encoder.encode(i)
            nonce = os.urandom(12)
            encrypted = cipher.encrypt(nonce, packet, None)
            encrypted_packets.append((nonce, encrypted))

        # Simulate loss: drop 50%
        import random
        random.seed(42)
        surviving = [(n, p) for n, p in encrypted_packets if random.random() > 0.5]

        # Decrypt
        decrypted_packets = []
        for nonce, enc_p in surviving:
            dec_p = cipher.decrypt(nonce, enc_p, None)
            decrypted_packets.append(dec_p)

        # Recover
        decoder = wirehair.Decoder(b"test_seed", len(source))
        for packet_id, packet in enumerate(decrypted_packets):
            decoder.decode(packet_id, packet)

        recovered = decoder.recover()
        assert recovered is not None

        # Verify bit-exact
        recovered_hash = hashlib.sha256(recovered).hexdigest()
        assert recovered_hash == source_hash


class TestCRCValidation:
    """Test CRC-32 packet validation for fountain codes."""

    def test_crc_packet_integrity(self):
        """Add CRC-32 to packets and validate."""
        packet = b"test fountain packet data"

        # Calculate CRC
        crc = zlib.crc32(packet) & 0xFFFFFFFF
        crc_bytes = crc.to_bytes(4, 'big')

        # Append CRC to packet
        packet_with_crc = packet + crc_bytes

        # Validate
        received_data = packet_with_crc[:-4]
        received_crc = int.from_bytes(packet_with_crc[-4:], 'big')

        calculated_crc = zlib.crc32(received_data) & 0xFFFFFFFF
        assert calculated_crc == received_crc

    def test_crc_corruption_detection(self):
        """Detect corruption in fountain packets using CRC."""
        import zlib

        packet = b"test fountain packet data"
        crc = zlib.crc32(packet) & 0xFFFFFFFF

        # Corrupt packet
        corrupted = packet[:-1] + bytes([(packet[-1] + 1) % 256])

        # CRC should mismatch
        corrupted_crc = zlib.crc32(corrupted) & 0xFFFFFFFF
        assert corrupted_crc != crc


class TestLossyChannelSimulation:
    """Simulate YouTube VP9 transcoding and verify recovery."""

    @pytest.mark.skipif(not HAS_WIREHAIR, reason="wirehair not installed")
    def test_simulate_youtube_transcoding(self):
        """Simulate aggressive lossy transcoding and recover."""
        # Original data: 1KB payload
        source = os.urandom(1024)
        source_hash = hashlib.sha256(source).hexdigest()

        # Encode with fountain codes
        encoder = wirehair.Encoder(b"test_seed", len(source))
        packets = [encoder.encode(i) for i in range(100)]

        # Simulate YouTube transcoding: 70% packet loss + 10% corruption
        import random
        random.seed(42)

        surviving_packets = []
        for i, packet in enumerate(packets):
            if random.random() > 0.7:  # 30% survive
                # 10% corruption chance
                if random.random() < 0.1:
                    # Corrupt a random byte
                    packet = bytearray(packet)
                    packet[random.randint(0, len(packet) - 1)] ^= 0xFF
                    packet = bytes(packet)

                # Add CRC for corruption detection
                import zlib
                crc = zlib.crc32(packet) & 0xFFFFFFFF
                packet = packet + crc.to_bytes(4, 'big')

                surviving_packets.append(packet)

        # Strip CRC and validate
        valid_packets = []
        for packet_with_crc in surviving_packets:
            data = packet_with_crc[:-4]
            crc_received = int.from_bytes(packet_with_crc[-4:], 'big')

            crc_calculated = zlib.crc32(data) & 0xFFFFFFFF
            if crc_calculated == crc_received:
                valid_packets.append(data)

        # Verify we have enough valid packets
        assert len(valid_packets) > len(source)

        # Recover
        decoder = wirehair.Decoder(b"test_seed", len(source))
        for packet_id, packet in enumerate(valid_packets):
            decoder.decode(packet_id, packet)

        recovered = decoder.recover()
        assert recovered is not None

        # Verify bit-exact recovery
        recovered_hash = hashlib.sha256(recovered).hexdigest()
        assert recovered_hash == source_hash


class TestLargeFileRecovery:
    """Test fountain codes with realistic container file sizes."""

    @pytest.mark.skipif(not HAS_WIREHAIR, reason="wirehair not installed")
    def test_recover_large_container(self):
        """Recover large file (~100KB) with aggressive packet loss."""
        # Simulate visual_audio.mkv size
        source = os.urandom(100 * 1024)  # 100KB
        source_hash = hashlib.sha256(source).hexdigest()

        # Encode
        encoder = wirehair.Encoder(b"test_seed", len(source))

        # Generate 200 repair packets
        packets = [encoder.encode(i) for i in range(200)]

        # Simulate 80% loss (aggressive)
        import random
        random.seed(42)
        surviving = [p for p in packets if random.random() > 0.8]

        assert len(surviving) > len(source), "Enough packets survived"

        # Recover
        decoder = wirehair.Decoder(b"test_seed", len(source))
        for packet_id, packet in enumerate(surviving):
            decoder.decode(packet_id, packet)

        recovered = decoder.recover()
        assert recovered is not None

        # Verify bit-exact
        recovered_hash = hashlib.sha256(recovered).hexdigest()
        assert recovered_hash == source_hash


if __name__ == "__main__":
    pytest.main([__file__, "-v"])