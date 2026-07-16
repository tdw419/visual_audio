#!/usr/bin/env python3
"""
Compatibility layer for compose.py and pixel_screen.py

This provides the legacy API (connect, materialize, word_id, tokenize) that the
pixel-OS renderers expect, backed by the new WordbaseManager.
"""

import sqlite3
import sys
import os
from pathlib import Path
from typing import Tuple, List, Dict, Optional

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.wordbase import WordbaseManager

# Deterministic pronunciation table for code symbols and spoken forms
# Consulted BEFORE CMUdict for these specific tokens
_SYMBOL_PRONUNCIATIONS = {
    # Multi-character operators
    'greater_equal': 'G R EY T ER IY K W AO L',
    'less_equal': 'L E S IY K W AO L',
    'equal_equal': 'IY K W AO L IY K W AO L',
    'not_equal': 'N AA T IY K W AO L',
    'plus_equal': 'P L AH S IY K W AO L',
    'minus_equal': 'M AY N AH S IY K W AO L',
    'times_equal': 'T AY M Z IY K W AO L',
    'divide_equal': 'D IH V AY D IY K W AO L',
    'floor_divide_equal': 'F L AO R D IH V AY D IY K W AO L',
    'modulo_equal': 'M AA J AH L OW IY K W AO L',
    'and_equal': 'AE N D IY K W AO L',
    'or_equal': 'AO R IY K W AO L',
    'xor_equal': 'E K S AO R IY K W AO L',
    'left_shift_equal': 'L E F T SH IY F T IY K W AO L',
    'right_shift_equal': 'R AY T SH IY F T IY K W AO L',
    'arrow': 'AE R OW',
    'fat_arrow': 'F AE T AE R OW',

    # Single symbols
    'plus': 'P L AH S',
    'minus': 'M AY N AH S',
    'times': 'T AY M Z',
    'divide': 'D IH V AY D',
    'modulo': 'M AA J AH L OW',
    'floor_divide': 'F L AO R D IH V AY D',
    'less': 'L E S',
    'greater': 'G R EY T ER',
    'assign': 'AH S AY N',
    'open_paren': 'OW P AH N P EH R AH N',
    'close_paren': 'K L OW Z P EH R AH N',
    'open_bracket': 'OW P AH N B R AE K AH T',
    'close_bracket': 'K L OW Z B R AE K AH T',
    'open_brace': 'OW P AH N B R EY S',
    'close_brace': 'K L OW Z B R EY S',
    'comma': 'K AA M AH',
    'semicolon': 'S E M IY K OW L AH N',
    'colon': 'K OW L AH N',
    'dot': 'D AA T',
    'hash': 'HH AE SH',
    'at': 'AE T',
    'dollar': 'D AA L ER',
    'ampersand': 'AE M P ER S AE N D',
    'pipe': 'P AY P',
    'caret': 'K AE R EH T',
    'tilde': 'T IH L D AH',
    'exclamation': 'EH K S K L AH M EY SH AH N',
    'question': 'K W EH S CH AH N',
    'single_quote': 'S IH NG G AH L K W OW T',
    'double_quote': 'D AH B AH L K W OW T',
    'backtick': 'B AE K T IH K',

    # Spoken number words (from tokenizer - lowercase for DB consistency)
    'zero': 'Z IH R OW',
    'one': 'W AH N',
    'two': 'T UW',
    'three': 'TH R IY',
    'four': 'F AO R',
    'five': 'F AY V',
    'six': 'S IH K S',
    'seven': 'S EH V AH N',
    'eight': 'EY T',
    'nine': 'N AY N',
    'point': 'P OY N T',
}

# POS and color categories for symbols
_SYMBOL_METADATA = {
    # Operators get specific colors
    'greater_equal': ('operator', '#FF6B35'),  # Orange for comparison
    'less_equal': ('operator', '#FF6B35'),
    'equal_equal': ('operator', '#FF6B35'),
    'not_equal': ('operator', '#FF6B35'),
    'less': ('operator', '#FF6B35'),
    'greater': ('operator', '#FF6B35'),

    # Arithmetic operators - blue tones
    'plus': ('operator', '#4A90E2'),
    'minus': ('operator', '#4A90E2'),
    'times': ('operator', '#4A90E2'),
    'divide': ('operator', '#4A90E2'),
    'modulo': ('operator', '#4A90E2'),
    'floor_divide': ('operator', '#4A90E2'),

    # Assignment operators - green tones
    'assign': ('operator', '#2ECC71'),
    'plus_equal': ('operator', '#2ECC71'),
    'minus_equal': ('operator', '#2ECC71'),
    'times_equal': ('operator', '#2ECC71'),
    'divide_equal': ('operator', '#2ECC71'),

    # Brackets/parens - gray/neutral
    'open_paren': ('punctuation', '#7F8C8D'),
    'close_paren': ('punctuation', '#7F8C8D'),
    'open_bracket': ('punctuation', '#7F8C8D'),
    'close_bracket': ('punctuation', '#7F8C8D'),
    'open_brace': ('punctuation', '#7F8C8D'),
    'close_brace': ('punctuation', '#7F8C8D'),

    # Comment/markup - yellow
    'hash': ('punctuation', '#F1C40F'),
    'at': ('punctuation', '#F1C40F'),

    # Strings - purple
    'single_quote': ('punctuation', '#9B59B6'),
    'double_quote': ('punctuation', '#9B59B6'),
    'backtick': ('punctuation', '#9B59B6'),

    # Numbers - cyan
    'zero': ('number', '#00CED1'),
    'one': ('number', '#00CED1'),
    'two': ('number', '#00CED1'),
    'three': ('number', '#00CED1'),
    'four': ('number', '#00CED1'),
    'five': ('number', '#00CED1'),
    'six': ('number', '#00CED1'),
    'seven': ('number', '#00CED1'),
    'eight': ('number', '#00CED1'),
    'nine': ('number', '#00CED1'),
    'point': ('number', '#00CED1'),
}

# Global CMUdict cache (lazy load)
_cmudict: Optional[Dict[str, List[str]]] = None
_cmudict_path: Optional[str] = None


def connect() -> sqlite3.Connection:
    """
    Connect to the wordbase database.

    Returns a raw SQLite connection for backward compatibility.
    """
    db_path = Path(__file__).parent.parent / "db" / "wordbase.db"
    return sqlite3.connect(str(db_path))


def _get_cmudict() -> Dict[str, List[str]]:
    """Lazy load CMUdict."""
    global _cmudict, _cmudict_path

    # Import here to avoid module load issues
    from tools.word_compiler import ensure_cmudict, parse_cmudict

    cmudict_path = ensure_cmudict()
    if _cmudict is None or _cmudict_path != cmudict_path:
        _cmudict = parse_cmudict(cmudict_path)
        _cmudict_path = cmudict_path

    return _cmudict


def word_id(db: sqlite3.Connection, word: str, cmudict: Dict[str, List[str]], lang: str = 'en') -> int:
    """
    Get the ID for a word, adding it if necessary.

    Priority order:
    1. Check if word already exists in database
    2. Check deterministic symbol table (operators, numbers)
    3. Check CMUdict (English)
    4. Try phonemizer for multilingual support (approximate)
    5. Fall back to grapheme pronunciation

    Args:
        db: Database connection
        word: Word to lookup or add
        cmudict: CMUdict mapping
        lang: Language code (e.g., 'en', 'es', 'de')

    Returns:
        Word ID
    """
    word_lower = word.lower()

    # Try to find existing word
    cursor = db.execute(
        "SELECT id FROM words WHERE word = ? LIMIT 1",
        (word_lower,)
    )
    row = cursor.fetchone()

    if row:
        return row[0]

    # Check deterministic symbol table first
    if word_lower in _SYMBOL_PRONUNCIATIONS:
        pronunciation = _SYMBOL_PRONUNCIATIONS[word_lower]
        pos, color_hex = _SYMBOL_METADATA.get(word_lower, ('operator', '#808080'))

        cursor = db.execute(
            """
            INSERT INTO words (word, pronunciation, pos, frequency, color_hex)
            VALUES (?, ?, ?, 1, ?)
            """,
            (word_lower, pronunciation, pos, color_hex)
        )
        db.commit()
        return cursor.lastrowid

    # Word not found - add it from CMUdict
    phonemes = cmudict.get(word_lower)

    if phonemes:
        # Infer POS (simple heuristic)
        pos = _infer_pos(word)

        # Insert word
        cursor = db.execute(
            """
            INSERT INTO words (word, pronunciation, pos, frequency)
            VALUES (?, ?, ?, 1)
            """,
            (word_lower, ' '.join(phonemes), pos)
        )
        db.commit()
        return cursor.lastrowid
    else:
        # Try phonemizer for multilingual support
        pronunciation = _try_phonemizer(word_lower, lang)

        if pronunciation:
            # Phonemizer succeeded - use the ARPAbet pronunciation
            pos = _infer_pos(word)
            cursor = db.execute(
                """
                INSERT INTO words (word, pronunciation, pos, frequency)
                VALUES (?, ?, ?, 1)
                """,
                (word_lower, pronunciation, pos)
            )
            db.commit()
            return cursor.lastrowid
        else:
            # Word not in any dictionary - insert with default phonemes (grapheme fallback)
            pos = _infer_pos(word)
            cursor = db.execute(
                """
                INSERT INTO words (word, pronunciation, pos, frequency)
                VALUES (?, ?, ?, 1)
                """,
                (word_lower, word.upper(), pos)
            )
            db.commit()
            return cursor.lastrowid


def _try_phonemizer(word: str, lang: str = 'en') -> str:
    """
    Try to get pronunciation using phonemizer (multilingual support).

    Phonemizer produces XSAMPA; this maps to ARPAbet via xsampa_to_arpabet.

    Args:
        word: Word to pronounce
        lang: Language code (e.g., 'en-us', 'es', 'de-de')

    Returns:
        ARPAbet phoneme sequence, or empty string on failure
    """
    try:
        from phonemizer.backend import EspeakBackend
        import sys
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'tools'))
        from xsampa_to_arpabet import map_xsampa_sequence

        # Normalize language code for phonemizer
        lang_code = lang if '-' in lang else f'{lang}-{lang}'  # es → es-es

        # Create backend
        backend = EspeakBackend(lang_code)

        # Get XSAMPA phonemes
        xsampa_output = backend.phonemize([word])
        if not xsampa_output or not xsampa_output[0]:
            return ''

        # Map XSAMPA to ARPAbet
        arpa_pronunciation = map_xsampa_sequence(xsampa_output[0])

        return arpa_pronunciation

    except ImportError:
        # phonemizer not installed - silent fallback
        return ''
    except Exception as e:
        # Phonemizer failed - silent fallback
        return ''


def materialize(db: sqlite3.Connection, word_id: int, cmudict: Dict[str, List[str]]) -> Tuple[str, str]:
    """
    Generate WAV and tile for a word (lazy evaluation).

    Args:
        db: Database connection
        word_id: Word ID
        cmudict: CMUdict mapping

    Returns:
        (wav_path, tile_path)
    """
    # Get word record
    cursor = db.execute(
        "SELECT word, pronunciation, image_path FROM words WHERE id = ? LIMIT 1",
        (word_id,)
    )
    row = cursor.fetchone()

    if not row:
        raise ValueError(f"Word ID {word_id} not found")

    word, pronunciation, tile_path = row

    # If tile already exists, return it
    if tile_path and Path(tile_path).exists():
        # Construct WAV path from tile path
        wav_path = Path(tile_path).with_suffix('.wav')
        if wav_path.exists():
            return str(wav_path), tile_path

    # Generate WAV and tile
    try:
        from tools.word_compiler import compile_word
        wav_path, audio = compile_word(pronunciation, cmudict, force=True)

        # Convert audio to tile (spectrogram)
        # TODO: Implement proper tile generation
        # For now, use a placeholder tile
        tile_dir = Path(__file__).parent.parent / "voicebook" / "tiles"
        tile_dir.mkdir(parents=True, exist_ok=True)

        # Generate simple tile from audio spectrogram
        import numpy as np
        from scipy import signal
        from PIL import Image

        # Compute spectrogram
        f, t, Sxx = signal.spectrogram(audio, 44100)
        Sxx_log = 10 * np.log10(Sxx + 1e-10)

        # Normalize to 0-255
        Sxx_norm = ((Sxx_log - Sxx_log.min()) / (Sxx_log.max() - Sxx_log.min()) * 255).astype(np.uint8)

        # Create tile (height=20, variable width)
        tile_height = 20
        tile_width = min(Sxx_norm.shape[1], 100)
        tile = Sxx_norm[:tile_height, :tile_width]

        # Pad to 20x100 if needed
        if tile.shape[1] < 100:
            tile = np.pad(tile, ((0, 0), (0, 100 - tile.shape[1])), mode='constant')

        # Convert to RGB (grayscale)
        tile_rgb = np.stack([tile] * 3, axis=-1)

        # Save tile
        tile_path = tile_dir / f"{word}_{word_id}.png"
        Image.fromarray(tile_rgb).save(tile_path)

        # Update database with tile path
        db.execute(
            "UPDATE words SET image_path = ? WHERE id = ?",
            (str(tile_path), word_id)
        )
        db.commit()

        return wav_path, str(tile_path)

    except Exception as e:
        print(f"Warning: Failed to materialize word {word} (ID {word_id}): {e}")
        # Return placeholder paths
        return "", ""


def tokenize(text: str) -> List[str]:
    """
    Split text into word and symbol tokens.

    Handles:
    - Regular words (alphanumeric + underscores)
    - Multi-character operators (>=, <=, ==, !=, +=, -=, etc.)
    - Single symbols (#, {, }, [, ], (, ), ;, :, ,, ., etc.)
    - Numbers (integers and floats)
    - Non-Latin scripts (CJK, Arabic, etc.) captured as UTF-8 byte sequences

    Args:
        text: Input text

    Returns:
        List of tokens (words, symbols, numbers, byte sequences)
    """
    import re

    # Order matters: longer patterns first
    patterns = [
        # Multi-character operators (must come before single chars)
        (r'>=', 'greater_equal'),
        (r'<=', 'less_equal'),
        (r'==', 'equal_equal'),
        (r'!=', 'not_equal'),
        (r'\+=', 'plus_equal'),
        (r'-=', 'minus_equal'),
        (r'\*=', 'times_equal'),
        (r'/=', 'divide_equal'),
        (r'//=', 'floor_divide_equal'),
        (r'%=', 'modulo_equal'),
        (r'&=', 'and_equal'),
        (r'\|=', 'or_equal'),
        (r'\^=', 'xor_equal'),
        (r'<<=', 'left_shift_equal'),
        (r'>>=', 'right_shift_equal'),
        (r'->', 'arrow'),
        (r'=>', 'fat_arrow'),

        # Single symbols
        (r'\+', 'plus'),
        (r'-', 'minus'),
        (r'\*', 'times'),
        (r'/', 'divide'),
        (r'%', 'modulo'),
        (r'//', 'floor_divide'),
        (r'<', 'less'),
        (r'>', 'greater'),
        (r'=', 'assign'),
        (r'\(', 'open_paren'),
        (r'\)', 'close_paren'),
        (r'\[', 'open_bracket'),
        (r'\]', 'close_bracket'),
        (r'\{', 'open_brace'),
        (r'\}', 'close_brace'),
        (r',', 'comma'),
        (r';', 'semicolon'),
        (r':', 'colon'),
        (r'\.', 'dot'),
        (r'#', 'hash'),
        (r'@', 'at'),
        (r'\$', 'dollar'),
        (r'&', 'ampersand'),
        (r'\|', 'pipe'),
        (r'\^', 'caret'),
        (r'~', 'tilde'),
        (r'!', 'exclamation'),
        (r'\?', 'question'),
        (r"'", 'single_quote'),
        (r'"', 'double_quote'),
        (r'`', 'backtick'),

        # Numbers (floats and integers)
        (r'\d+\.\d+', lambda m: _speak_number(m.group(0))),
        (r'\d+', lambda m: _speak_number(m.group(0))),

        # Words (ASCII alphanumeric + underscore only)
        (r'[a-zA-Z_][a-zA-Z0-9_]*', lambda m: m.group(0).lower()),

        # Non-Latin: sequences of non-ASCII chars
        # Capture contiguous runs as UTF-8 byte sequences
        (r'[^\x00-\x7F]+', lambda m: f'0x{m.group(0).encode("utf-8").hex()}'),
    ]

    tokens = []
    remaining = text
    original_case = {}  # Track original case for letters

    while remaining:
        matched = False

        # Skip whitespace first
        if remaining and remaining[0].isspace():
            remaining = remaining[1:]
            continue

        for pattern, replacer in patterns:
            match = re.match(pattern, remaining)
            if match:
                token = replacer(match) if callable(replacer) else replacer
                matched = True
                consumed = len(match.group(0))

                # Track original case for single letters
                if re.match(r'[A-Za-z]', match.group(0)):
                    original_case[token.lower()] = match.group(0)

                tokens.append(token)
                remaining = remaining[consumed:]
                break

        if not matched and remaining:
            # Fallback: single char as hex byte
            unknown_char = remaining[0]
            tokens.append(f'0x{unknown_char.encode("utf-8").hex()}')
            remaining = remaining[1:]

    return tokens


def _speak_number(num_str: str) -> str:
    """
    Convert number to spoken form (lowercase for DB key consistency).

    Examples:
        '123' → 'one two three'
        '3.14' → 'three point one four'
        '42' → 'four two' (digit-by-digit for now)
    """
    import re

    if '.' in num_str:
        # Float: "3.14" → "three point one four"
        parts = num_str.split('.')
        integer_part = _speak_integer(parts[0])
        decimal_part = ' '.join(_speak_digit(d) for d in parts[1])
        return f"{integer_part} point {decimal_part}"
    else:
        # Integer
        return _speak_integer(num_str)


def _speak_integer(num_str: str) -> str:
    """Convert integer string to spoken form (lowercase)."""
    num = int(num_str)

    if num == 0:
        return "zero"

    # For now, digit-by-digit (simple and reliable)
    # TODO: Could add proper number-to-words (e.g., "one hundred twenty three")
    return ' '.join(_speak_digit(d) for d in num_str)


def _speak_digit(digit: str) -> str:
    """Single digit to spoken form (lowercase for DB consistency)."""
    digit_words = {
        '0': 'zero',
        '1': 'one',
        '2': 'two',
        '3': 'three',
        '4': 'four',
        '5': 'five',
        '6': 'six',
        '7': 'seven',
        '8': 'eight',
        '9': 'nine',
    }
    return digit_words.get(digit, digit.lower())


def _infer_pos(word: str) -> str:
    """Simple heuristic to infer part of speech from word ending."""
    word_lower = word.lower()

    # Common suffixes
    if word_lower.endswith('ing'):
        return 'verb'
    elif word_lower.endswith(('ed', 'd')):
        return 'verb'
    elif word_lower.endswith(('ly', 'wise')):
        return 'adverb'
    elif word_lower.endswith(('tion', 'sion', 'ment', 'ness', 'ity', 'ance', 'ence')):
        return 'noun'
    elif word_lower.endswith(('able', 'ible', 'ive', 'al', 'ic', 'ful', 'less')):
        return 'adjective'
    elif word_lower.endswith(('er', 'or')):
        return 'noun'  # agent nouns

    return 'noun'  # Default


# Re-export for backward compatibility
__all__ = ['connect', 'materialize', 'word_id', 'tokenize']