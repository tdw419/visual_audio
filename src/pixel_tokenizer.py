#!/usr/bin/env python3
"""
Pixel Tokenizer — text ↔ word ID ↔ RGB pixel.

A tokenizer where each word maps to a unique 24-bit RGB pixel (id = R<<16 | G<<8 | B).
The model's vocabulary IS the wordbase: tokens are pixels, pixels are words.

Architecture:
- Text → word IDs (via wordbase lookup or auto-add via G2P)
- Word IDs → RGB pixels (id = R<<16 | G<<8 | B)
- RGB pixels → word IDs (reverse mapping)
- Word IDs → text (via wordbase word lookup)

Special tokens occupy IDs 0-15 (PAD, BOS, EOS, UNK, NEWLINE, etc.)
Real words start from ID 16 (offset by SPECIAL_RESERVED = 16)
"""

import numpy as np
from typing import List, Tuple, Optional, Dict
from pathlib import Path
import sys
import os

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.wordbase import WordbaseManager


# Special token IDs (0-15 reserved)
class SpecialTokens:
    """Special token definitions."""
    PAD = 0       # Padding token
    BOS = 1       # Beginning of sequence
    EOS = 2       # End of sequence
    UNK = 3       # Unknown word
    NEWLINE = 4   # Line break
    TAB = 5       # Tab character
    SPACE = 6     # Space character
    NUM_SPECIAL = 16  # Total reserved special tokens (0-15)


SPECIAL_NAMES = {
    0: "PAD",
    1: "BOS",
    2: "EOS",
    3: "UNK",
    4: "NEWLINE",
    5: "TAB",
    6: "SPACE"
}


class PixelTokenizer:
    """
    Pixel tokenizer for text ↔ word ID ↔ RGB pixel conversion.

    Each word maps to a unique wordbase ID (offset by SPECIAL_RESERVED),
    then to a 24-bit RGB pixel where id = (R << 16) | (G << 8) | B.
    """

    def __init__(self, wordbase_path: Optional[Path] = None):
        """
        Initialize pixel tokenizer with wordbase connection.

        Args:
            wordbase_path: Path to wordbase database (default: db/wordbase.db)
        """
        if wordbase_path is None:
            wordbase_path = Path(__file__).parent.parent / "db" / "wordbase.db"

        self.wordbase = WordbaseManager(wordbase_path)
        self.special_offset = SpecialTokens.NUM_SPECIAL

        # Cache for word → ID lookups (frequent words)
        self._word_cache: Dict[str, int] = {}

    def close(self):
        """Close wordbase connection."""
        self.wordbase.close()

    def _get_word_id(self, word: str) -> int:
        """
        Get wordbase ID for a word, auto-adding OOV words.

        Args:
            word: Word to look up (case-insensitive)

        Returns:
            Wordbase ID (offset by special tokens)
        """
        word_lower = word.lower()

        # Check cache first
        if word_lower in self._word_cache:
            return self._word_cache[word_lower]

        # Look up in wordbase
        result = self.wordbase.get_word(word_lower)
        if result:
            word_id = result['id']
            self._word_cache[word_lower] = word_id
            return word_id

        # OOV word: auto-add via phonemizer
        word_id = self._add_oov_word(word_lower)
        self._word_cache[word_lower] = word_id
        return word_id

    def _add_oov_word(self, word: str) -> int:
        """
        Add an out-of-vocabulary word using phonemizer.

        Args:
            word: Word to add (lowercase)

        Returns:
            New wordbase ID
        """
        try:
            from phonemizer.backend import EspeakBackend

            # Use phonemizer for pronunciation
            backend = EspeakBackend('en-us', preserve_punctuation=True)
            phonemes = backend.phonemize([word], strip=True)[0]

            # Map XSAMPA to ARPAbet (simplified mapping for common phonemes)
            # In production, use the full xsampa_to_arpabet mapping
            pronunciation = self._xsampa_to_arpabet(phonemes)

        except Exception:
            # Fallback to grapheme-based pronunciation
            pronunciation = word.upper()

        # Infer part of speech
        pos = self._infer_pos(word)

        # Add to wordbase
        word_id = self.wordbase.add_word(
            word=word,
            pronunciation=pronunciation,
            pos=pos,
            frequency=1
        )

        return word_id

    def _xsampa_to_arpabet(self, xsampa: str) -> str:
        """
        Convert XSAMPA phoneme string to ARPAbet using the full mapping table.

        Args:
            xsampa: XSAMPA phoneme string from phonemizer

        Returns:
            ARPAbet phoneme string
        """
        # Import the proper mapping function
        sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))
        from xsampa_to_arpabet import map_xsampa_sequence

        # Use the full sequence mapping
        return map_xsampa_sequence(xsampa)

    def _infer_pos(self, word: str) -> str:
        """
        Infer part of speech from word ending.

        Args:
            word: Word to analyze

        Returns:
            Part of speech string
        """
        # Simple suffix-based inference
        if word.endswith('ing'):
            return 'verb'
        elif word.endswith(('ed', 'd')):
            return 'verb'
        elif word.endswith(('ly', 'wise')):
            return 'adverb'
        elif word.endswith(('tion', 'sion', 'ment', 'ness', 'ity', 'ance', 'ence')):
            return 'noun'
        elif word.endswith(('able', 'ible', 'ive', 'al', 'ic', 'ful', 'less')):
            return 'adjective'
        elif word.endswith(('er', 'or')):
            return 'noun'

        return 'noun'  # Default

    def encode(self, text: str, add_special_tokens: bool = True) -> List[int]:
        """
        Encode text to word ID sequence.

        Args:
            text: Input text
            add_special_tokens: Add BOS/EOS tokens

        Returns:
            List of word IDs (offset by special tokens)
        """
        ids = []

        if add_special_tokens:
            ids.append(SpecialTokens.BOS)

        # Tokenize: handle newlines, tabs, and spaces as special tokens
        # Split on whitespace while preserving special characters
        import re

        # Tokenize: split on boundaries, keep punctuation separate
        tokens = re.findall(r'\S+|\s+', text)

        for token in tokens:
            # Handle whitespace as special tokens
            if token == '\n':
                ids.append(SpecialTokens.NEWLINE)
            elif token == '\t':
                ids.append(SpecialTokens.TAB)
            elif token == ' ':
                ids.append(SpecialTokens.SPACE)
            elif token.startswith(' '):
                # Multiple consecutive spaces: emit SPACE tokens for each
                for _ in range(len(token)):
                    ids.append(SpecialTokens.SPACE)
            # Handle punctuation as separate tokens
            elif token in ('.', ',', '!', '?', ';', ':'):
                # Punctuation becomes part of adjacent words or gets UNK
                # For simplicity, skip punctuation in this version
                continue
            else:
                # Clean punctuation from word
                clean_word = token.strip('.,!?;:()[]{}"\'')
                if clean_word:
                    word_id = self._get_word_id(clean_word)
                    ids.append(word_id + self.special_offset)

        if add_special_tokens:
            ids.append(SpecialTokens.EOS)

        return ids

    def decode(self, ids: List[int], skip_special_tokens: bool = False) -> str:
        """
        Decode word ID sequence to text.

        Args:
            ids: List of word IDs (offset by special tokens)
            skip_special_tokens: Skip special tokens in output

        Returns:
            Decoded text
        """
        words = []

        for word_id in ids:
            # Handle special tokens
            if word_id < self.special_offset:
                if skip_special_tokens:
                    continue
                if word_id == SpecialTokens.NEWLINE:
                    words.append('\n')
                elif word_id == SpecialTokens.TAB:
                    words.append('\t')
                elif word_id == SpecialTokens.SPACE:
                    words.append(' ')
                elif word_id == SpecialTokens.UNK:
                    words.append('<UNK>')
                continue

            # Convert to actual wordbase ID
            actual_id = word_id - self.special_offset

            # Look up word
            cursor = self.wordbase.conn.execute(
                "SELECT word FROM words WHERE id = ?",
                (actual_id,)
            )
            row = cursor.fetchone()
            if row and row[0]:
                words.append(row[0])
            else:
                words.append('<UNK>')

        # Reconstruct text from word/special token sequence
        # Special tokens (SPACE, NEWLINE, TAB) are already literal chars in words list
        # Only need to space-separate regular words
        result = []
        for i, word in enumerate(words):
            if word in ('\n', '\t', ' '):
                # Special whitespace tokens: append directly
                result.append(word)
            else:
                # Regular word: add space if previous wasn't whitespace
                if result and result[-1] not in ('\n', '\t', ' '):
                    result.append(' ')
                result.append(word)

        return ''.join(result)

    def ids_to_pixels(self, ids: List[int]) -> np.ndarray:
        """
        Convert word ID sequence to RGB pixel array.

        Each word ID becomes one pixel: R = (id >> 16) & 0xFF,
        G = (id >> 8) & 0xFF, B = id & 0xFF.

        Args:
            ids: List of word IDs

        Returns:
            NumPy array of shape (len(ids), 3) with RGB values
        """
        pixels = np.zeros((len(ids), 3), dtype=np.uint8)

        for i, word_id in enumerate(ids):
            pixels[i, 0] = (word_id >> 16) & 0xFF  # Red channel
            pixels[i, 1] = (word_id >> 8) & 0xFF   # Green channel
            pixels[i, 2] = word_id & 0xFF          # Blue channel

        return pixels

    def pixels_to_ids(self, pixels) -> List[int]:
        """
        Convert RGB pixel array to word ID sequence.

        Each pixel becomes one word ID: id = R << 16 | G << 8 | B.

        Args:
            pixels: NumPy array or list of shape (N, 3) with RGB values

        Returns:
            List of word IDs
        """
        ids = []

        # Convert to numpy array if needed
        if not isinstance(pixels, np.ndarray):
            pixels = np.array(pixels, dtype=np.uint8)

        for pixel in pixels:
            r, g, b = pixel
            # Convert to int to avoid uint8 overflow
            word_id = (int(r) << 16) | (int(g) << 8) | int(b)
            ids.append(word_id)

        return ids

    def encode_to_pixels(self, text: str, add_special_tokens: bool = True) -> np.ndarray:
        """
        Encode text directly to pixel array.

        Args:
            text: Input text
            add_special_tokens: Add BOS/EOS tokens

        Returns:
            NumPy array of shape (N, 3) with RGB pixel values
        """
        ids = self.encode(text, add_special_tokens=add_special_tokens)
        return self.ids_to_pixels(ids)

    def decode_from_pixels(self, pixels: np.ndarray, skip_special_tokens: bool = False) -> str:
        """
        Decode pixel array directly to text.

        Args:
            pixels: NumPy array of shape (N, 3) with RGB pixel values
            skip_special_tokens: Skip special tokens in output

        Returns:
            Decoded text
        """
        ids = self.pixels_to_ids(pixels)
        return self.decode(ids, skip_special_tokens=skip_special_tokens)