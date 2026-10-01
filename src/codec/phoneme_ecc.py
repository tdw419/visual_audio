"""
codec/phoneme_ecc.py — Reed-Solomon error correction for phoneme sequences.

Provides Reed-Solomon encoding/decoding over phoneme symbol sequences to
enable recovery from transmission corruption in the acoustic channel.

Design:
- Phonemes are encoded as symbol indices (0-39 for 39 ARPAbet phonemes + SIL)
- Reed-Solomon operates on bytes, so we pack symbols as bytes (1 symbol = 1 byte)
- RS(nsym=8) adds 8 parity bytes → can correct up to floor(8/2) = 4 symbol errors
- Correction capacity: floor(ecc_symbols / 2) symbol errors

Parameters:
- ecc_symbols: Number of parity symbols to add (default 8)
- Pack 1 symbol per byte for RS encoding
- Unpack after RS correction to recover symbols

Overhead: ecc_symbols symbols ≈ 20-30% for typical 20-40 phoneme sentences
"""

import random
from typing import List, Tuple, Dict, Optional
try:
    from reedsolo import RSCodec
except ImportError:
    RSCodec = None


# 39 ARPAbet phonemes + SIL = 40 symbols total
# From tools/phonemes.py and tools/neural_synthesis.py
PHONEMES = [
    'AA', 'AE', 'AH', 'AO', 'AW', 'AY', 'B', 'CH', 'D', 'DH',
    'EH', 'ER', 'EY', 'F', 'G', 'HH', 'IH', 'IY', 'JH', 'K',
    'L', 'M', 'N', 'NG', 'OW', 'OY', 'P', 'R', 'S', 'SH',
    'T', 'TH', 'UH', 'UW', 'V', 'W', 'Y', 'Z', 'ZH', 'SIL'
]

# Map phonemes to symbol indices (0-39)
PHONEME_INDEX = {p: i for i, p in enumerate(PHONEMES)}
INDEX_TO_PHONEME = {i: p for i, p in enumerate(PHONEMES)}


# Default parameters: correct up to 4 byte errors = 8 symbol errors
DEFAULT_ECC_SYMBOLS = 8


def pack_symbols(symbols: List[int]) -> bytes:
    """
    Pack symbol indices into bytes for RS encoding.
    
    Each symbol is 0-39 (40 phonemes), which fits in 6 bits.
    We pack each symbol as its own byte since 40 < 256.
    
    Args:
        symbols: List of symbol indices (0-39)
    
    Returns:
        Packed bytes (one symbol per byte)
    """
    return bytes(symbols)


def unpack_symbols(data: bytes) -> List[int]:
    """
    Unpack bytes to symbol indices.
    
    Args:
        data: Packed bytes
    
    Returns:
        List of symbol indices (0-39)
    """
    return list(data)


class PhonemeECC:
    """
    Reed-Solomon error correction for phoneme sequences.
    
    Operates on phoneme symbol sequences packed into bytes for RS codec.
    """

    def __init__(self, ecc_symbols: int = DEFAULT_ECC_SYMBOLS):
        """
        Initialize phoneme ECC codec.
        
        Args:
            ecc_symbols: Number of parity symbols to add (default 8)
                        Corrects up to floor(ecc_symbols/2) symbol errors
        """
        if RSCodec is None:
            raise ImportError("reedsolo library required. Install: pip install reedsolo")
        
        self.ecc_symbols = ecc_symbols
        
        # RS(nsym) adds nsym parity bytes
        # Each byte holds 1 symbol, so we get ecc_symbols symbol protection
        # Can correct up to floor(ecc_symbols/2) errors
        self.rs_codec = RSCodec(nsym=ecc_symbols)

    def _phonemes_to_symbols(self, phonemes: List[str]) -> List[int]:
        """Convert phoneme sequence to symbol indices."""
        symbols = []
        for p in phonemes:
            if p not in PHONEME_INDEX:
                # Unknown phoneme: map to SIL as fallback
                symbols.append(PHONEME_INDEX['SIL'])
            else:
                symbols.append(PHONEME_INDEX[p])
        return symbols

    def _symbols_to_phonemes(self, symbols: List[int]) -> List[str]:
        """Convert symbol indices to phoneme sequence."""
        phonemes = []
        for s in symbols:
            if s == 0:  # Padding symbol
                continue
            if s in INDEX_TO_PHONEME:
                phonemes.append(INDEX_TO_PHONEME[s])
            else:
                # Invalid symbol: map to SIL as fallback
                phonemes.append('SIL')
        return phonemes

    def encode(self, phonemes: List[str]) -> List[str]:
        """
        Encode phoneme sequence with Reed-Solomon parity.
        
        Args:
            phonemes: List of ARPAbet phonemes
        
        Returns:
            Encoded phoneme sequence (original + parity phonemes)
        """
        # Convert to symbols
        symbols = self._phonemes_to_symbols(phonemes)
        
        # Pack symbols into bytes
        packed = pack_symbols(symbols)
        
        # Apply RS encoding
        encoded_array = self.rs_codec.encode(packed)
        encoded_packed = bytes(encoded_array)
        
        # Unpack back to symbols
        encoded_symbols = unpack_symbols(encoded_packed)
        
        # Convert back to phonemes (including parity)
        encoded_phonemes = self._symbols_to_phonemes(encoded_symbols)
        
        return encoded_phonemes

    def decode(self, phonemes: List[str]) -> Tuple[List[str], bool, int]:
        """
        Decode and correct phoneme sequence with Reed-Solomon.
        
        Args:
            phonemes: List of phonemes (may include parity phonemes)
        
        Returns:
            Tuple of:
            - recovered_phonemes: Corrected phoneme sequence (data only)
            - valid: Whether RS decode reported success
            - errors_fixed: Number of errors corrected by RS codec
        """
        # Convert to symbols
        symbols = self._phonemes_to_symbols(phonemes)
        
        # Pack symbols into bytes
        packed = pack_symbols(symbols)
        
        # Apply RS decoding/correction
        try:
            result = self.rs_codec.decode(packed)
            corrected_array = result[0]
            errata_pos = result[2] if len(result) > 2 else []
            corrected_packed = bytes(corrected_array)
            
            # Count errors fixed
            errors_fixed = len(errata_pos)
            
            # Valid if decode completed without exception
            # RS will throw exception if too many errors to correct
            valid = True
        except Exception as e:
            # Decoding failed (too many errors)
            return phonemes, False, 0
        
        # Unpack corrected bytes to symbols
        corrected_symbols = unpack_symbols(corrected_packed)
        
        # Calculate original data length (subtract parity symbols)
        # Each parity byte = 1 symbol (changed from 2)
        data_symbols_count = len(corrected_symbols) - self.ecc_symbols
        
        # Extract only data symbols
        data_symbols = corrected_symbols[:data_symbols_count]
        
        # Convert back to phonemes
        recovered_phonemes = self._symbols_to_phonemes(data_symbols)
        
        return recovered_phonemes, valid, errors_fixed

    def corrupt(self, phonemes: List[str], num_errors: int, seed: Optional[int] = None) -> List[str]:
        """
        Simulate corruption by replacing phonemes with random ones.
        
        Args:
            phonemes: Original phoneme sequence
            num_errors: Number of phonemes to corrupt
            seed: Random seed for reproducibility
        
        Returns:
            Corrupted phoneme sequence
        """
        rng = random.Random(seed)
        corrupted = phonemes.copy()
        
        if num_errors > len(corrupted):
            num_errors = len(corrupted)
        
        # Random positions to corrupt
        error_positions = rng.sample(range(len(corrupted)), num_errors)
        
        # Corrupt each position with a different random phoneme
        for i in error_positions:
            original = corrupted[i]
            possible = [p for p in PHONEMES if p != original]
            if possible:
                corrupted[i] = rng.choice(possible)
        
        return corrupted


# Convenience functions for backward compatibility

def encode_phonemes(phonemes: List[str], ecc_symbols: int = DEFAULT_ECC_SYMBOLS) -> List[str]:
    """Encode phonemes with Reed-Solomon parity."""
    ecc = PhonemeECC(ecc_symbols=ecc_symbols)
    return ecc.encode(phonemes)


def decode_phonemes(phonemes: List[str], ecc_symbols: int = DEFAULT_ECC_SYMBOLS) -> Tuple[List[str], bool, int]:
    """Decode and correct phonemes with Reed-Solomon."""
    ecc = PhonemeECC(ecc_symbols=ecc_symbols)
    return ecc.decode(phonemes)