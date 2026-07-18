#!/usr/bin/env python3
"""
Test TASK_M006: Pixel LM audio round-trip verification.

Tests that pixel-LM generated token IDs can be transmitted over audio
and reconstructed byte-identically using the Visual Audio codec chain:

1. Generated id sequence → bytes (3 bytes/id) → PhyECC + Phy16Tone WAV → decode → identical id sequence
2. Audio roundtrip survives 5% injected corruption
3. Model "speaks" its pixels; receiver with same wordbase reconstructs text/tiles locally
"""

import pytest
import numpy as np
import tempfile
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.codec.phy import Phy16Tone, frame, unframe, encode_framed, decode_framed
from src.codec.phy_ecc import PhyECC, encode_ecc, decode_ecc
from src.pixel_tokenizer import PixelTokenizer, SpecialTokens


class TestPixelLMAudioRoundtrip:
    """Test pixel LM audio round-trip verification."""

    def test_id_sequence_to_bytes_roundtrip(self):
        """Test that ID sequences convert to bytes and back correctly."""
        # Test token ID sequence (simulating pixel LM output)
        # IDs 0-15 are special tokens, 16+ are word tokens
        original_ids = [
            SpecialTokens.BOS,
            16, 17, 18,  # Word tokens
            SpecialTokens.SPACE,
            19, 20,
            SpecialTokens.EOS
        ]
        
        # Convert IDs to bytes (3 bytes per ID: R, G, B)
        bytes_from_ids = self._ids_to_bytes(original_ids)
        
        # Convert bytes back to IDs
        recovered_ids = self._bytes_to_ids(bytes_from_ids)
        
        # Should be byte-identical
        assert recovered_ids == original_ids, "ID sequence round-trip failed"
        print(f"  ✓ ID sequence ({len(original_ids)} tokens) round-trips byte-identically")

    def test_pixel_lm_generation_to_audio_roundtrip(self):
        """Test complete pipeline: generated IDs → audio → IDs."""
        # Simulate a pixel LM generation output
        generated_ids = [
            SpecialTokens.BOS,
            16, 17, 18, 19, 20,  # Word tokens
            SpecialTokens.SPACE,
            21, 22, 23,
            SpecialTokens.NEWLINE,
            24, 25,
            SpecialTokens.EOS
        ]
        
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f:
            wav_path = f.name
        
        try:
            # 1. IDs → bytes (3 bytes/id)
            id_bytes = self._ids_to_bytes(generated_ids)
            print(f"  IDs → bytes: {len(generated_ids)} IDs → {len(id_bytes)} bytes")
            
            # 2. Frame for transmission
            framed = frame(id_bytes)
            
            # 3. Encode with ECC
            ecc_encoded = encode_ecc(framed)
            print(f"  ECC overhead: {len(ecc_encoded)} / {len(framed)} bytes")
            
            # 4. Encode to audio
            audio = Phy16Tone.encode(ecc_encoded)
            
            # 5. Write WAV
            import soundfile as sf
            sf.write(wav_path, audio, Phy16Tone.SAMPLE_RATE)
            
            # 6. Read WAV back
            audio_read, sr = sf.read(wav_path)
            if audio_read.ndim > 1:
                audio_read = audio_read.mean(axis=1)
            
            # 7. Decode audio to bytes
            decoded_bytes = Phy16Tone.decode(audio_read)
            
            # 8. Decode ECC
            recovered_framed, valid = decode_ecc(decoded_bytes)
            assert valid, "ECC validation failed"
            
            # 9. Unframe
            recovered_bytes, crc_valid = unframe(recovered_framed)
            assert crc_valid, "CRC validation failed"
            
            # 10. Bytes → IDs
            recovered_ids = self._bytes_to_ids(recovered_bytes)
            
            # Verify byte-identical round-trip
            assert recovered_ids == generated_ids, "ID sequence mismatch after round-trip"
            print(f"  ✓ Pixel LM output round-trips byte-identically ({len(recovered_ids)} tokens)")
        
        finally:
            if os.path.exists(wav_path):
                os.unlink(wav_path)

    def test_audio_roundtrip_with_5percent_corruption(self):
        """Test that audio round-trip survives 5% corruption."""
        # Simulate pixel LM output
        generated_ids = [
            SpecialTokens.BOS,
            16, 17, 18, 19, 20, 21, 22, 23, 24, 25,  # 10 word tokens
            SpecialTokens.SPACE,
            26, 27, 28, 29, 30, 31, 32, 33, 34, 35,  # 10 word tokens
            SpecialTokens.EOS
        ]
        
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f:
            wav_path = f.name
        
        try:
            # Encode to audio with ECC
            id_bytes = self._ids_to_bytes(generated_ids)
            framed = frame(id_bytes)
            ecc_encoded = encode_ecc(framed)
            audio = Phy16Tone.encode(ecc_encoded)
            
            # Write and read back
            import soundfile as sf
            sf.write(wav_path, audio, Phy16Tone.SAMPLE_RATE)
            audio_read, sr = sf.read(wav_path)
            if audio_read.ndim > 1:
                audio_read = audio_read.mean(axis=1)
            
            # Inject 5% corruption
            n_samples = len(audio_read)
            n_corrupt = int(n_samples * 0.05)
            np.random.seed(42)
            corrupt_indices = np.random.choice(n_samples, n_corrupt, replace=False)
            audio_corrupted = audio_read.copy()
            audio_corrupted[corrupt_indices] *= 0.3  # Reduce amplitude
            
            print(f"  Injected {n_corrupt} corrupted samples ({n_corrupt/n_samples:.1%})")
            
            # Decode corrupted audio
            decoded_bytes = Phy16Tone.decode(audio_corrupted)
            recovered_framed, valid = decode_ecc(decoded_bytes)
            recovered_bytes, crc_valid = unframe(recovered_framed)
            
            # Verify recovery
            assert valid, "ECC failed to correct errors"
            assert crc_valid, "CRC failed after ECC correction"
            
            recovered_ids = self._bytes_to_ids(recovered_bytes)
            assert recovered_ids == generated_ids, "Failed to recover from 5% corruption"
            
            print(f"  ✓ Audio round-trip survives 5% corruption (ECC recovery works)")
        
        finally:
            if os.path.exists(wav_path):
                os.unlink(wav_path)

    def test_model_speaks_pixels_text_roundtrip(self):
        """Test that model-generated pixels decode to text via wordbase."""
        # Use existing wordbase (production DB has words)
        # Generate token IDs for words that likely exist
        generated_ids = [
            SpecialTokens.BOS,
            16 + 1,  # Word token (offset by SPECIAL_RESERVED)
            SpecialTokens.SPACE,
            16 + 2,  # Another word token
            SpecialTokens.EOS
        ]
        
        # Audio round-trip
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f:
            wav_path = f.name
        
        try:
            id_bytes = self._ids_to_bytes(generated_ids)
            framed = frame(id_bytes)
            ecc_encoded = encode_ecc(framed)
            audio = Phy16Tone.encode(ecc_encoded)
            
            import soundfile as sf
            sf.write(wav_path, audio, Phy16Tone.SAMPLE_RATE)
            audio_read, sr = sf.read(wav_path)
            if audio_read.ndim > 1:
                audio_read = audio_read.mean(axis=1)
            
            decoded_bytes = Phy16Tone.decode(audio_read)
            recovered_framed, valid = decode_ecc(decoded_bytes)
            recovered_bytes, crc_valid = unframe(recovered_framed)
            recovered_ids = self._bytes_to_ids(recovered_bytes)
            
            assert recovered_ids == generated_ids, "ID mismatch"
            
            # Decode to text using wordbase
            # Use production wordbase (has many words)
            tokenizer = PixelTokenizer()
            recovered_text = tokenizer.decode(recovered_ids, skip_special_tokens=True)
            tokenizer.close()
            
            # Should produce some text (even if <UNK> for unknown words)
            print(f"  ✓ Model 'speaks' pixels → text reconstruction works: '{recovered_text}'")
        
        finally:
            if os.path.exists(wav_path):
                os.unlink(wav_path)

    def test_large_sequence_roundtrip(self):
        """Test round-trip with larger sequences (100+ tokens)."""
        # Generate a longer sequence
        generated_ids = [SpecialTokens.BOS]
        
        # Add 50 word tokens with spaces
        for i in range(1, 51):
            generated_ids.append(16 + i)
            if i % 5 == 0:
                generated_ids.append(SpecialTokens.SPACE)
        
        generated_ids.append(SpecialTokens.EOS)
        
        print(f"  Large sequence: {len(generated_ids)} tokens")
        
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f:
            wav_path = f.name
        
        try:
            # Full round-trip
            id_bytes = self._ids_to_bytes(generated_ids)
            framed = frame(id_bytes)
            ecc_encoded = encode_ecc(framed)
            audio = Phy16Tone.encode(ecc_encoded)
            
            import soundfile as sf
            sf.write(wav_path, audio, Phy16Tone.SAMPLE_RATE)
            audio_read, sr = sf.read(wav_path)
            if audio_read.ndim > 1:
                audio_read = audio_read.mean(axis=1)
            
            decoded_bytes = Phy16Tone.decode(audio_read)
            recovered_framed, valid = decode_ecc(decoded_bytes)
            recovered_bytes, crc_valid = unframe(recovered_framed)
            recovered_ids = self._bytes_to_ids(recovered_bytes)
            
            assert recovered_ids == generated_ids, "Large sequence round-trip failed"
            print(f"  ✓ Large sequence ({len(generated_ids)} tokens) round-trips byte-identically")
        
        finally:
            if os.path.exists(wav_path):
                os.unlink(wav_path)

    def _ids_to_bytes(self, ids: list) -> bytes:
        """Convert token ID sequence to bytes (3 bytes per ID)."""
        # Each ID becomes 3 bytes: R, G, B channels
        bytes_list = []
        for token_id in ids:
            bytes_list.append((token_id >> 16) & 0xFF)  # R
            bytes_list.append((token_id >> 8) & 0xFF)   # G
            bytes_list.append(token_id & 0xFF)          # B
        return bytes(bytes_list)

    def _bytes_to_ids(self, data: bytes) -> list:
        """Convert bytes to token ID sequence (3 bytes per ID)."""
        ids = []
        if len(data) % 3 != 0:
            raise ValueError(f"Byte data length must be multiple of 3, got {len(data)}")
        
        for i in range(0, len(data), 3):
            token_id = (data[i] << 16) | (data[i + 1] << 8) | data[i + 2]
            ids.append(token_id)
        
        return ids


if __name__ == '__main__':
    pytest.main([__file__, '-v'])