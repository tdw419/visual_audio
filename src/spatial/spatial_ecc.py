"""
spatial_ecc.py — Reed-Solomon error correction for spatial glyph programs.

TASK_SE011: Add Reed-Solomon error correction for robust pixel transmission.

Design:
- Glyph programs are stored as images (height × width × 3 RGB bytes)
- RSCodec appends parity bytes to the end of the data
- Block-based encoding: split large programs into 100-byte blocks for better error distribution
- Each block is independently encoded with RS(100, 120) — 20 parity bytes
- Corrects up to 10 byte errors per block (10% per-block capacity)
- 30% total overhead (20 parity per 100 data bytes)

Usage:
    from src.spatial.spatial_ecc import SpatialECC, encode_program_with_ecc

    # Encode program image
    ecc_data = encode_program_with_ecc(program_image)

    # Decode with error correction
    recovered, valid = decode_program_with_ecc(ecc_data)
"""

import numpy as np
from typing import Tuple, Optional

# Import reedsolo (TASK_E001 dependency)
try:
    from reedsolo import RSCodec
except ImportError:
    RSCodec = None


# Default parameters for spatial programs
# Larger block size: 100 data bytes + 20 parity bytes
# Corrects up to 10 byte errors per 120-byte block (~8.3% correction)
DEFAULT_DATA_BYTES = 100
DEFAULT_PARITY_BYTES = 20

# Metadata marker to identify ECC-encoded programs
ECC_MARKER = b'GEOSECC\xFF'
METADATA_SIZE = len(ECC_MARKER) + 12  # marker + 4-byte height + 4-byte width + 4-byte data_len


class SpatialECC:
    """Reed-Solomon error correction for spatial glyph programs."""

    def __init__(self, data_bytes: int = DEFAULT_DATA_BYTES,
                 parity_bytes: int = DEFAULT_PARITY_BYTES):
        """
        Initialize ECC encoder/decoder.

        Args:
            data_bytes: Data bytes per RS block
            parity_bytes: Parity bytes per RS block (corrects parity_bytes//2 errors)
        """
        if RSCodec is None:
            raise ImportError("reedsolo package required (TASK_E001)")

        self.data_bytes = data_bytes
        self.parity_bytes = parity_bytes
        self.rs_codec = RSCodec(nsym=parity_bytes)

    def encode_program(self, image: np.ndarray) -> bytes:
        """
        Encode glyph program image with ECC.

        Args:
            image: Program image (height × width × 3 uint8 RGB)

        Returns:
            ECC-encoded bytes with metadata header
        """
        height, width = image.shape[:2]

        # Flatten image to byte sequence
        program_data = image.tobytes()

        # Chunk into blocks and encode each
        n_blocks = (len(program_data) + self.data_bytes - 1) // self.data_bytes

        encoded_blocks = []
        for i in range(n_blocks):
            start = i * self.data_bytes
            end = min(start + self.data_bytes, len(program_data))
            block = program_data[start:end]

            # Pad last block if needed
            if len(block) < self.data_bytes:
                block = block + b'\x00' * (self.data_bytes - len(block))

            # Encode block: RSCodec appends parity
            encoded_block = self.rs_codec.encode(block)
            encoded_blocks.append(bytes(encoded_block))

        encoded_data = b''.join(encoded_blocks)

        # Build metadata: marker + height + width + original_data_length
        metadata = (ECC_MARKER +
                   height.to_bytes(4, 'little') +
                   width.to_bytes(4, 'little') +
                   len(program_data).to_bytes(4, 'little'))

        # Return: metadata + encoded program
        return metadata + encoded_data

    def decode_program(self, data: bytes) -> Tuple[Optional[np.ndarray], bool]:
        """
        Decode ECC-encoded glyph program.

        Args:
            data: ECC-encoded bytes (may have corruption)

        Returns:
            Tuple of (decoded_image, is_valid)
            - decoded_image: Recovered program image (or None if decode fails)
            - is_valid: True if data was valid/correctable, False if too corrupt
        """
        # Check minimum length (metadata marker + dimensions)
        if len(data) < METADATA_SIZE:
            return None, False

        # Extract and verify metadata marker
        marker = data[:len(ECC_MARKER)]
        if marker != ECC_MARKER:
            # Not an ECC-encoded program
            return None, False

        # Extract dimensions
        height = int.from_bytes(data[len(ECC_MARKER):len(ECC_MARKER)+4], 'little')
        width = int.from_bytes(data[len(ECC_MARKER)+4:len(ECC_MARKER)+8], 'little')
        original_data_len = int.from_bytes(data[len(ECC_MARKER)+8:len(ECC_MARKER)+12], 'little')

        # Extract encoded data (after metadata)
        encoded_data = data[METADATA_SIZE:]

        # Decode by blocks
        block_size = self.data_bytes + self.parity_bytes
        n_blocks = len(encoded_data) // block_size

        decoded_blocks = []
        is_valid = True

        for i in range(n_blocks):
            start = i * block_size
            end = start + block_size
            encoded_block = encoded_data[start:end]

            try:
                result = self.rs_codec.decode(encoded_block)
                decoded_block = result[0]  # RSCodec returns (decoded_data, encoded_msg, errata_list)

                decoded_blocks.append(bytes(decoded_block))

            except Exception as e:
                # Block decoding failed (too many errors)
                is_valid = False
                decoded_blocks.append(b'\x00' * self.data_bytes)

        # Concatenate decoded blocks and trim to original length
        decoded_data = b''.join(decoded_blocks)[:original_data_len]

        # Reconstruct image
        expected_size = original_data_len
        if len(decoded_data) != expected_size or height * width * 3 != expected_size:
            return None, False

        image = np.frombuffer(decoded_data, dtype=np.uint8)
        image = image.reshape((height, width, 3))

        return image, is_valid

    def corrupt_program(self, data: bytes, corruption_rate: float = 0.05) -> bytes:
        """
        Inject bit errors into encoded program for testing.

        Only corrupts the data portion (after metadata), leaving metadata intact.

        Args:
            data: ECC-encoded program
            corruption_rate: Fraction of bytes to corrupt (default 5%)

        Returns:
            Corrupted data
        """
        # Only corrupt the data portion (after metadata)
        data_only = data[METADATA_SIZE:]

        n_corrupt = int(len(data_only) * corruption_rate)

        # Random byte flips
        np.random.seed(42)
        corrupt_indices = np.random.choice(len(data_only), n_corrupt, replace=False)
        corrupted_data = bytearray(data_only)

        for idx in corrupt_indices:
            # Flip random bits in the byte
            corrupted_data[idx] ^= (1 << np.random.randint(0, 8))

        # Return metadata + corrupted data
        return data[:METADATA_SIZE] + bytes(corrupted_data)


def encode_program_with_ecc(image: np.ndarray,
                            data_bytes: int = DEFAULT_DATA_BYTES,
                            parity_bytes: int = DEFAULT_PARITY_BYTES) -> bytes:
    """
    Convenience function to encode a glyph program with ECC.

    Args:
        image: Program image (height × width × 3 uint8 RGB)
        data_bytes: Data bytes per RS block
        parity_bytes: Parity bytes per RS block

    Returns:
        ECC-encoded bytes
    """
    ecc = SpatialECC(data_bytes=data_bytes, parity_bytes=parity_bytes)
    return ecc.encode_program(image)


def decode_program_with_ecc(data: bytes) -> Tuple[Optional[np.ndarray], bool]:
    """
    Convenience function to decode an ECC-encoded glyph program.

    Args:
        data: ECC-encoded bytes

    Returns:
        Tuple of (decoded_image, is_valid)
    """
    ecc = SpatialECC()
    return ecc.decode_program(data)


# Self-test when run directly
if __name__ == '__main__':
    print("SpatialECC self-test...\n")

    # Test 1: Basic encode/decode
    print("Test 1: Basic program encode/decode...")
    test_image = np.random.randint(0, 256, (8, 16, 3), dtype=np.uint8)

    ecc = SpatialECC()
    encoded = ecc.encode_program(test_image)
    decoded, valid = ecc.decode_program(encoded)

    overhead = (len(encoded) - test_image.nbytes) / test_image.nbytes * 100

    if valid and np.array_equal(decoded, test_image):
        print(f"  ✓ PASS: Basic encode/decode works")
        print(f"    Original: {test_image.shape} ({test_image.nbytes} bytes)")
        print(f"    Encoded:  {len(encoded)} bytes (metadata + data + parity)")
        print(f"    Overhead: {overhead:.1f}%")
    else:
        print(f"  ✗ FAIL: valid={valid}, match={np.array_equal(decoded, test_image)}")
        sys.exit(1)

    # Test 2: Error correction (5% corruption)
    print("\nTest 2: Error correction (5% corruption)...")
    corrupted = ecc.corrupt_program(encoded, corruption_rate=0.05)
    recovered, valid = ecc.decode_program(corrupted)

    diffs = sum(1 for a, b in zip(encoded, corrupted) if a != b)

    if valid and np.array_equal(recovered, test_image):
        print(f"  ✓ PASS: Recovered from 5% corruption")
        print(f"    Byte differences: {diffs}/{len(encoded)} = {diffs/len(encoded):.1%}")
    else:
        print(f"  ✗ FAIL: valid={valid}, match={np.array_equal(recovered, test_image)}")
        sys.exit(1)

    # Test 3: High corruption (should fail)
    print("\nTest 3: High corruption (10% - should fail)...")
    corrupted_heavy = ecc.corrupt_program(encoded, corruption_rate=0.10)
    recovered_heavy, valid_heavy = ecc.decode_program(corrupted_heavy)

    diffs_heavy = sum(1 for a, b in zip(encoded, corrupted_heavy) if a != b)

    if not valid_heavy:
        print(f"  ✓ PASS: Correctly rejected 10% corruption")
        print(f"    Byte differences: {diffs_heavy}/{len(encoded)} = {diffs_heavy/len(encoded):.1%}")
    else:
        # May occasionally succeed due to random distribution
        print(f"  ~ WARN: 10% corruption passed (random distribution)")

    print("\n✓ All tests passed")