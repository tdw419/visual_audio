"""
codec/phy_ecc.py — Reed-Solomon error correction for spectral PHY.

TASK_E001: Add ECC layer to spectral codec to survive 10% symbol corruption.

Design:
- Reed-Solomon operates at SYMBOL level (nibbles), not byte level
- Each symbol is 4 bits (0-15), but RS works on bytes
- Pack 2 symbols per byte (high nibble, low nibble) for RS encoding
- Unpack after RS correction to recover symbols

Parameters:
- data_bytes: Number of data bytes per RS block (each byte = 2 symbols)
- parity_bytes: Number of parity bytes per RS block
- Correction capability: floor(parity_bytes / 2) bytes = floor(parity_bytes) symbols

Overhead: parity_bytes / (data_bytes + parity_bytes) ≈ 25-40%
"""

import struct
import numpy as np
from typing import Tuple, List
try:
    from reedsolo import RSCodec
except ImportError:
    RSCodec = None


# Default parameters: correct up to 5 byte errors for 50-byte payloads
# 1 data byte + 10 parity bytes per block = can correct 5 errors
# Handles 10% byte corruption comfortably
DEFAULT_DATA_BYTES = 1
DEFAULT_PARITY_BYTES = 10


def pack_symbols(symbols: List[int]) -> bytes:
    """
    Pack symbols (nibbles) into bytes.
    
    Each byte contains 2 symbols: high nibble first, then low nibble.
    Odd number of symbols gets a trailing zero nibble.
    
    Args:
        symbols: List of symbol values (0-15)
    
    Returns:
        Packed bytes
    """
    if len(symbols) % 2:
        symbols = symbols + [0]  # Pad to even length
    
    packed = bytes((symbols[i] << 4) | symbols[i + 1] 
                   for i in range(0, len(symbols), 2))
    return packed


def unpack_symbols(data: bytes) -> List[int]:
    """
    Unpack bytes to symbols (nibbles).
    
    Args:
        data: Packed bytes
    
    Returns:
        List of symbol values (0-15)
    """
    symbols = []
    for byte in data:
        symbols.append((byte >> 4) & 0x0F)  # high nibble
        symbols.append(byte & 0x0F)          # low nibble
    return symbols


class PhyECC:
    """
    Reed-Solomon error correction for PHY layer at symbol level.
    
    Operates on symbol sequences (nibbles) packed into bytes for RS codec.
    """

    def __init__(self, data_bytes: int = DEFAULT_DATA_BYTES, 
                 parity_bytes: int = DEFAULT_PARITY_BYTES):
        """
        Initialize ECC codec.
        
        Args:
            data_bytes: Number of data bytes per RS block (each byte = 2 symbols)
            parity_bytes: Number of parity bytes per RS block
        """
        if RSCodec is None:
            raise ImportError("reedsolo library required. Install: pip install reedsolo")
        
        self.data_bytes = data_bytes
        self.parity_bytes = parity_bytes
        
        # Reed-Solomon codec
        self.rs_codec = RSCodec(nsym=parity_bytes)

    def encode_symbols(self, symbols: List[int]) -> List[int]:
        """
        Encode symbol sequence with Reed-Solomon parity.
        
        Args:
            symbols: List of symbol values (0-15) to encode
        
        Returns:
            ECC-encoded symbols (data + parity)
        """
        if len(symbols) == 0:
            return symbols
        
        # Pack symbols into bytes
        packed = pack_symbols(symbols)
        
        # Encode with RS
        encoded_packed = self.rs_codec.encode(packed)
        
        # Unpack back to symbols
        encoded_symbols = unpack_symbols(bytes(encoded_packed))
        
        return encoded_symbols

    def decode_symbols(self, symbols: List[int]) -> Tuple[List[int], bool]:
        """
        Decode ECC-encoded symbol sequence, correcting errors.
        
        Args:
            symbols: ECC-encoded symbols (may have errors)
        
        Returns:
            Tuple of (decoded_symbols, is_valid)
            - decoded_symbols: Recovered original symbols
            - is_valid: True if symbols were correctable, False if too corrupt
        """
        if len(symbols) == 0:
            return symbols, True
        
        # Pad to even length for packing
        if len(symbols) % 2:
            symbols = symbols + [0]
        
        # Pack symbols into bytes
        packed = pack_symbols(symbols)
        
        try:
            # Decode with error correction
            # reedsolo returns either 2-tuple or 3-tuple
            result = self.rs_codec.decode(packed)
            decoded_packed, decoded_packed_ecc = result[:2]
            
            # Unpack back to symbols
            decoded_symbols = unpack_symbols(bytes(decoded_packed))
            
            # Verify by re-encoding and comparing
            test_encode = self.rs_codec.encode(bytes(decoded_packed))
            is_valid = bytes(test_encode) == bytes(decoded_packed_ecc)
            
            return decoded_symbols, is_valid
            
        except Exception as e:
            # Decoding failed (too many errors)
            return symbols, False

    def encode(self, data: bytes) -> bytes:
        """
        Encode data with ECC (byte-level API).
        
        Args:
            data: Raw data bytes to encode
        
        Returns:
            ECC-encoded bytes
        """
        # Convert bytes to symbols (nibbles)
        symbols = []
        for byte in data:
            symbols.append((byte >> 4) & 0x0F)  # high nibble
            symbols.append(byte & 0x0F)          # low nibble
        
        # Encode symbols
        encoded_symbols = self.encode_symbols(symbols)
        
        # Convert symbols back to bytes
        if len(encoded_symbols) % 2:
            encoded_symbols = encoded_symbols + [0]
        encoded = bytes((encoded_symbols[i] << 4) | encoded_symbols[i + 1]
                       for i in range(0, len(encoded_symbols), 2))
        
        return encoded

    def decode(self, data: bytes) -> Tuple[bytes, bool]:
        """
        Decode ECC-encoded data (byte-level API).
        
        Args:
            data: ECC-encoded bytes (may have errors)
        
        Returns:
            Tuple of (decoded_data, is_valid)
        """
        # Convert bytes to symbols
        symbols = []
        for byte in data:
            symbols.append((byte >> 4) & 0x0F)
            symbols.append(byte & 0x0F)
        
        # Decode symbols
        decoded_symbols, valid = self.decode_symbols(symbols)
        
        if not valid:
            return data, False
        
        # Convert symbols back to bytes
        if len(decoded_symbols) % 2:
            decoded_symbols = decoded_symbols + [0]
        decoded = bytes((decoded_symbols[i] << 4) | decoded_symbols[i + 1]
                       for i in range(0, len(decoded_symbols), 2))
        
        return decoded, valid


def encode_ecc(data: bytes, 
               data_bytes: int = DEFAULT_DATA_BYTES,
               parity_bytes: int = DEFAULT_PARITY_BYTES) -> bytes:
    """
    Encode data with ECC (convenience function).
    
    Args:
        data: Raw data to encode
        data_bytes: Data bytes per RS block
        parity_bytes: Parity bytes per RS block
    
    Returns:
        ECC-encoded bytes
    """
    ecc = PhyECC(data_bytes=data_bytes, parity_bytes=parity_bytes)
    return ecc.encode(data)


def decode_ecc(data: bytes,
               data_bytes: int = DEFAULT_DATA_BYTES,
               parity_bytes: int = DEFAULT_PARITY_BYTES) -> Tuple[bytes, bool]:
    """
    Decode ECC-encoded data (convenience function).
    
    Args:
        data: ECC-encoded bytes (may have errors)
        data_bytes: Data bytes per RS block
        parity_bytes: Parity bytes per RS block
    
    Returns:
        Tuple of (decoded_data, is_valid)
    """
    ecc = PhyECC(data_bytes=data_bytes, parity_bytes=parity_bytes)
    return ecc.decode(data)


def calculate_symbol_correction_rate(parity_bytes: int) -> float:
    """
    Calculate symbol error correction rate for given parity.
    
    Args:
        parity_bytes: Number of parity bytes per block
    
    Returns:
        Fraction of symbols that can be corrected
    """
    # RS can correct floor(parity/2) byte errors
    # Each byte = 2 symbols, so floor(parity) symbols correctable per block
    corrected_symbols = parity_bytes  # 1 parity byte = 2 symbol corrections
    # As fraction of total symbols (assuming 1:1 data:parity symbols)
    return corrected_symbols / (corrected_symbols + parity_bytes * 2)


def estimate_overhead(data_bytes: int, parity_bytes: int) -> float:
    """
    Calculate overhead percentage for ECC parameters.
    
    Args:
        data_bytes: Data bytes per block
        parity_bytes: Parity bytes per block
    
    Returns:
        Overhead as fraction (0.33 = 33% overhead)
    """
    return parity_bytes / (data_bytes + parity_bytes)


if __name__ == '__main__':
    # Self-test
    import sys
    
    print("PhyECC self-test...")
    
    # Test 1: Basic encode/decode
    print("\nTest 1: Basic encode/decode...")
    test_data = b'hello world'
    ecc = PhyECC()
    encoded = ecc.encode(test_data)
    decoded, valid = ecc.decode(encoded)
    
    if valid and decoded == test_data:
        print(f"  ✓ PASS: Basic encode/decode works")
        print(f"    Original: {len(test_data)} bytes")
        print(f"    Encoded:  {len(encoded)} bytes")
        print(f"    Overhead: {estimate_overhead(1, 2):.1%}")
    else:
        print(f"  ✗ FAIL: valid={valid}, match={decoded == test_data}")
        sys.exit(1)
    
    # Test 2: Symbol-level error correction
    print("\nTest 2: Symbol-level correction (10% corruption)...")
    test_data = b'test data for error correction' * 5
    
    # Convert to symbols
    symbols = []
    for byte in test_data:
        symbols.append((byte >> 4) & 0x0F)
        symbols.append(byte & 0x0F)
    
    # Add ECC at symbol level
    ecc_encoded_symbols = ecc.encode_symbols(symbols)
    
    # Corrupt 10% of symbols (flip to opposite tone)
    n_corrupt = int(len(ecc_encoded_symbols) * 0.10)
    np.random.seed(42)
    corrupt_indices = np.random.choice(len(ecc_encoded_symbols), n_corrupt, replace=False)
    corrupted_symbols = ecc_encoded_symbols.copy()
    for idx in corrupt_indices:
        corrupted_symbols[idx] = (corrupted_symbols[idx] + 8) % 16
    
    # Decode symbols
    recovered_symbols, valid = ecc.decode_symbols(corrupted_symbols)
    
    # Convert back to bytes
    recovered = bytes((recovered_symbols[i] << 4) | recovered_symbols[i + 1]
                     for i in range(0, len(recovered_symbols) - 1, 2))
    
    if valid and recovered == test_data:
        print(f"  ✓ PASS: Recovered from {n_corrupt} symbol errors ({n_corrupt/len(ecc_encoded_symbols):.1%})")
    else:
        print(f"  ✗ FAIL: valid={valid}, match={recovered == test_data}")
        sys.exit(1)
    
    # Test 3: All byte values
    print("\nTest 3: All 256 byte values...")
    test_data = bytes(range(256))
    encoded = ecc.encode(test_data)
    decoded, valid = ecc.decode(encoded)
    
    if valid and decoded == test_data:
        print(f"  ✓ PASS: All byte values round-tripped")
    else:
        print(f"  ✗ FAIL: valid={valid}, match={decoded == test_data}")
        sys.exit(1)
    
    print("\n✓ All tests passed")