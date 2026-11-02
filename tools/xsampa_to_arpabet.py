#!/usr/bin/env python3
"""
XSAMPA to ARPAbet phoneme mapping.

Phonemizer library uses XSAMPA notation (e.g., 'o' = /o/, 'oU' = /oʊ/).
Our UPIC synthesis uses ARPAbet (e.g., 'OW' = /oʊ/).

This table maps common XSAMPA symbols to ARPAbet equivalents for
approximate multilingual support. Not all mappings are perfect,
but they provide English-ish approximations for foreign words.
"""

# Vowels (XSAMPA -> ARPAbet)
# XSAMPA vowels are typically lowercase; ARPAbet is uppercase.
VOWELS = {
    # Close vowels
    'i': 'IY',      # /i/ as in "see"
    'I': 'IH',      # /ɪ/ as in "bit"
    'u': 'UW',      # /u/ as in "boot"
    'U': 'UW',      # /ʊ/ as in "book" (XSAMPA uses U for /ʊ/)
    'y': 'IY',      # /y/ as in French "tu" (approx as IY)

    # Close-mid vowels
    'e': 'EY',      # /e/ as in Spanish "me" (approx as EY - closer to /eɪ/)
    'E': 'EH',      # /ɛ/ as in "met"
    'o': 'OW',      # /o/ as in Spanish "no" (approx as OW)
    'O': 'AO',      # /ɔ/ as in "law"

    # Open-mid vowels
    '3': 'ER',      # /ɜ/ as in "bird"
    '9': 'ER',      # /ə/ as in "about"
    '@': 'ER',      # /ə/ schwa

    # Open vowels
    'a': 'AA',      # /a/ as in Spanish "la" (approx as AA)
    'A': 'AA',      # /ɑ/ as in "hot"

    # Diphthongs (XSAMPA uses uppercase for second element)
    'aI': 'AY',     # /aɪ/ as in "hide"
    'aU': 'AW',     # /aʊ/ as in "cow"
    'oI': 'OY',     # /ɔɪ/ as in "boy"
    'eI': 'EY',     # /eɪ/ as in "made"
    'oU': 'OW',     # /oʊ/ as in "go"
    'OI': 'OY',     # /ɔɪ/ (alternative)

    # Rhotacized vowels
    '@r': 'ER',     # /ɚ/ as in "butter"
    '3r': 'ER',     # /ɝ/ as in "bird"
}

# Consonants (XSAMPA -> ARPAbet)
# Note: XSAMPA uses lowercase; ARPAbet is uppercase.
CONSONANTS = {
    # Plosives
    'p': 'P',       # /p/
    'b': 'B',       # /b/
    't': 'T',       # /t/
    'd': 'D',       # /d/
    'k': 'K',       # /k/
    'g': 'G',       # /g/

    # Affricates
    'tS': 'CH',     # /tʃ/ as in "church"
    'dZ': 'JH',     # /dʒ/ as in "judge"

    # Fricatives
    'f': 'F',       # /f/
    'v': 'V',       # /v/
    'T': 'TH',      # /θ/ as in "thin"
    'D': 'DH',      # /ð/ as in "this"
    's': 'S',       # /s/
    'z': 'Z',       # /z/
    'S': 'SH',      # /ʃ/ as in "she"
    'Z': 'ZH',      # /ʒ/ as in "measure"
    'h': 'HH',      # /h/

    # Nasals
    'm': 'M',       # /m/
    'n': 'N',       # /n/
    'N': 'NG',      # /ŋ/ as in "sing"

    # Approximants
    'l': 'L',       # /l/
    'r': 'R',       # /ɹ/
    'j': 'Y',       # /j/ as in "yes"
    'w': 'W',       # /w/

    # Trill (common in Spanish)
    'r\\': 'R',     # /r/ trill (approx as R)

    # Flap/tap (common in Spanish)
    '4': 'R',       # /ɾ/ flap (approx as R)
}

# Combined lookup
XSTOARPA = {**VOWELS, **CONSONANTS}

# Common multi-character XSAMPA symbols that need special handling
# XSAMPA sometimes uses \ for diacritics
SPECIAL = {
    'l\\': 'L',     # /l/ with special articulation (approx as L)
    'n\\': 'N',     # /n/ with special articulation (approx as N)
}


def xsampa_to_arpabet(xsampa: str) -> str | None:
    """
    Convert XSAMPA phoneme to ARPAbet.

    Args:
        xsampa: XSAMPA phoneme (e.g., 'oU', 'tS', 'r\\')

    Returns:
        ARPAbet phoneme (e.g., 'OW', 'CH', 'R'), or None if no mapping

    Examples:
        >>> xsampa_to_arpabet('oU')
        'OW'
        >>> xsampa_to_arpabet('tS')
        'CH'
        >>> xsampa_to_arpabet('r\\')
        'R'
    """
    # Handle special diacritics first
    if xsampa in SPECIAL:
        return SPECIAL[xsampa]

    # Handle backslash-escaped characters
    if '\\' in xsampa:
        # Remove diacritic markers, approximate as base
        base = xsampa.replace('\\', '')
        return XSTOARPA.get(base)

    # Direct lookup
    return XSTOARPA.get(xsampa)


def map_xsampa_sequence(xsampa_text: str) -> str:
    """
    Convert a sequence of XSAMPA phonemes to ARPAbet space-separated string.

    Handles XSAMPA's various boundary conventions:
    - Syllable boundaries: use period or hyphen
    - Stress markers: ' for primary stress, % for secondary stress (ignored)
    - Multi-character phonemes: handles 'tS', 'dZ', 'oU', 'aI', etc.

    Args:
        xsampa_text: XSAMPA phoneme sequence (e.g., "h o l a" or "oU l A")

    Returns:
        ARPAbet phoneme sequence (e.g., "HH OW L AA"), or empty string on failure

    Examples:
        >>> map_xsampa_sequence("h o l a")
        'HH OW L AA'
        >>> map_xsampa_sequence("oU l A")
        'OW L AA'
    """
    import re

    # Remove stress markers
    cleaned = xsampa_text.replace("'", "").replace("%", "")

    # Split by syllable boundaries
    tokens = cleaned.replace('.', ' ').replace('-', ' ').split()

    arpa_phonemes = []
    i = 0
    while i < len(tokens):
        token = tokens[i]

        # Check for multi-character XSAMPA phonemes
        # Look ahead to see if current + next forms a valid multi-char phoneme
        if i + 1 < len(tokens):
            combined = token + tokens[i + 1]
            if combined in XSTOARPA or combined in VOWELS or combined in CONSONANTS:
                arpa = xsampa_to_arpabet(combined)
                if arpa:
                    arpa_phonemes.append(arpa)
                i += 2
                continue

        # Single phoneme
        arpa = xsampa_to_arpabet(token)
        if arpa:
            arpa_phonemes.append(arpa)
        else:
            # Unknown phoneme - skip (could warn in debug mode)
            pass

        i += 1

    return ' '.join(arpa_phonemes) if arpa_phonemes else ''


if __name__ == '__main__':
    # Test mapping
    test_cases = [
        ("h o l a", "HH OW L AA"),          # Spanish "hola" (space-separated)
        ("oU l A", "OW L AA"),              # Spanish "hola" (multi-char XSAMPA)
        ("tS e s", "CH EY S"),              # Spanish "che" (approx, /e/ → EY)
        ("m u n d o", "M UW N D OW"),        # Spanish "mundo"
        ("a I", "AY"),                      # Diphthong test
        ("o U", "OW"),                      # Diphthong test
    ]

    print("XSAMPA to ARPAbet mapping tests:")
    all_pass = True
    for xsampa, expected in test_cases:
        result = map_xsampa_sequence(xsampa)
        status = "✓" if result == expected else "✗"
        print(f"  {status} '{xsampa}' → '{result}' (expected: '{expected}')")
        if result != expected:
            all_pass = False

    if all_pass:
        print("\nAll tests passed!")
    else:
        print("\nSome tests failed - review mapping table (may be approximations)")