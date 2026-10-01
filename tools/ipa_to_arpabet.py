#!/usr/bin/env python3
"""
IPA (Unicode) to ARPAbet phoneme mapping.

Phonemizer uses Unicode IPA notation (e.g., 'ə', 'ɔ', 'ʊ').
Our UPIC synthesis uses ARPAbet (e.g., 'ER', 'AO', 'UW').

This table maps common IPA symbols to ARPAbet equivalents for
multi-lingual support. Not all mappings are perfect, but they
provide English-ish approximations for foreign phonemes.
"""

# Vowels (IPA -> ARPAbet)
# IPA uses Unicode characters; ARPAbet is uppercase ASCII.
VOWELS = {
    # Close vowels
    'i': 'IY',      # /i/ as in "see"
    'ɪ': 'IH',      # /ɪ/ as in "bit"
    'u': 'UW',      # /u/ as in "boot"
    'ʊ': 'UW',      # /ʊ/ as in "book"
    'y': 'IY',      # /y/ as in French "tu" (approx as IY)

    # Close-mid vowels
    'e': 'EY',      # /e/ as in Spanish "me" (approx as EY)
    'ɛ': 'EH',      # /ɛ/ as in "met"
    'o': 'OW',      # /o/ as in Spanish "no" (approx as OW)
    'ɔ': 'AO',      # /ɔ/ as in "law"
    'ø': 'ER',      # /ø/ (French, approximate)

    # Open-mid vowels
    'ə': 'ER',      # /ə/ schwa
    'ɜ': 'ER',      # /ɜ/ as in "bird"
    'ɐ': 'AH',      # /ɐ/ near-open central

    # Open vowels
    'a': 'AA',      # /a/ as in Spanish "la" (approx as AA)
    'ɑ': 'AA',      # /ɑ/ as in "hot"
    'æ': 'AE',      # /æ/ as in "cat"
    'ɐ': 'AA',      # /ɐ/ near-open central

    # Nasal vowels (precomposed Unicode)
    'ã': 'AA',      # /ã/ nasal a (Spanish/Portuguese)
    'õ': 'OW',      # /õ/ nasal o (Spanish/Portuguese)
    'ẽ': 'EY',      # /ẽ/ nasal e (Portuguese)
    'ĩ': 'IY',      # /ĩ/ nasal i (Portuguese)
    'ũ': 'UW',      # /ũ/ nasal u (Portuguese)

    # Diphthongs (IPA uses combinations)
    'aɪ': 'AY',     # /aɪ/ as in "hide"
    'aʊ': 'AW',     # /aʊ/ as in "cow"
    'ɔɪ': 'OY',     # /ɔɪ/ as in "boy"
    'eɪ': 'EY',     # /eɪ/ as in "made"
    'oʊ': 'OW',     # /oʊ/ as in "go"

    # R-colored vowels
    'ɚ': 'ER',      # /ɚ/ as in "butter"
    'ɝ': 'ER',      # /ɝ/ as in "bird"
}

# Consonants (IPA -> ARPAbet)
CONSONANTS = {
    # Plosives
    'p': 'P',       # /p/
    'b': 'B',       # /b/
    't': 'T',       # /t/
    'd': 'D',       # /d/
    'k': 'K',       # /k/
    'g': 'G',       # /g/

    # Affricates
    'tʃ': 'CH',     # /tʃ/ as in "church"
    'dʒ': 'JH',     # /dʒ/ as in "judge"

    # Fricatives
    'f': 'F',       # /f/
    'v': 'V',       # /v/
    'θ': 'TH',      # /θ/ as in "thin"
    'ð': 'DH',      # /ð/ as in "this"
    's': 'S',       # /s/
    'z': 'Z',       # /z/
    'ʃ': 'SH',      # /ʃ/ as in "she"
    'ʒ': 'ZH',      # /ʒ/ as in "measure"
    'h': 'HH',      # /h/
    'x': 'HH',      # /x/ velar fricative (approx as HH)

    # Nasals
    'm': 'M',       # /m/
    'n': 'N',       # /n/
    'ŋ': 'NG',      # /ŋ/ as in "sing"
    'ɲ': 'N',       # /ɲ/ palatal nasal (approx as N)

    # Approximants
    'l': 'L',       # /l/
    'ɫ': 'L',       # /ɫ/ velarized L
    'ɾ': 'R',       # /ɾ/ flap
    'r': 'R',       # /ɹ/ alveolar
    'ɹ': 'R',       # /ɹ/ alveolar approximant
    'j': 'Y',       # /j/ as in "yes"
    'w': 'W',       # /w/
    'ɥ': 'W',       # /ɥ/ labio-palatal (approx as W)

    # Trill
    'r̩': 'R',      # /r/ trill (approx as R)
}

# Combined lookup
IPATOARPA = {**VOWELS, **CONSONANTS}

# Common combinations (diphthongs, affricates) that need special handling
SPECIAL = {
    'oʊ': 'OW',     # /oʊ/ as in "go"
    'aɪ': 'AY',     # /aɪ/ as in "hide"
    'eɪ': 'EY',     # /eɪ/ as in "made"
    'ɔɪ': 'OY',     # /ɔɪ/ as in "boy"
    'aʊ': 'AW',     # /aʊ/ as in "cow"
    'tʃ': 'CH',     # /tʃ/ affricate
    'dʒ': 'JH',     # /dʒ/ affricate
}


def ipa_to_arpabet(ipa: str) -> str | None:
    """
    Convert IPA phoneme to ARPAbet.

    Args:
        ipa: IPA phoneme (e.g., 'oʊ', 'tʃ', 'ɾ')

    Returns:
        ARPAbet phoneme (e.g., 'OW', 'CH', 'R'), or None if no mapping

    Examples:
        >>> ipa_to_arpabet('oʊ')
        'OW'
        >>> ipa_to_arpabet('tʃ')
        'CH'
        >>> ipa_to_arpabet('ɾ')
        'R'
    """
    # Handle special combinations first
    if ipa in SPECIAL:
        return SPECIAL[ipa]

    # Direct lookup
    return IPATOARPA.get(ipa)


def map_ipa_sequence(ipa_text: str) -> str:
    """
    Convert a sequence of IPA phonemes to ARPAbet space-separated string.

    Handles various IPA conventions:
    - Syllable boundaries: use period or hyphen
    - Stress markers: ' for primary stress, ˌ for secondary (ignored)
    - Multi-character phonemes: handles 'oʊ', 'tʃ', etc.

    Args:
        ipa_text: IPA phoneme sequence (e.g., "h oʊ l ə" or "ola")

    Returns:
        ARPAbet phoneme sequence (e.g., "HH OW L ER"), or empty string on failure

    Examples:
        >>> map_ipa_sequence("h oʊ l ə")
        'HH OW L ER'
        >>> map_ipa_sequence("ola")
        'OW L AA'
    """
    import sys
    import os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
    from tools.ipa_tokenizer import tokenize_ipa

    # Tokenize IPA string into individual phonemes
    tokens = tokenize_ipa(ipa_text)

    arpa_phonemes = []
    i = 0
    while i < len(tokens):
        token = tokens[i]

        # Single phoneme
        arpa = ipa_to_arpabet(token)
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
        ("h ə l oʊ", "HH ER L OW"),          # Spanish "hola" (IPA)
        ("m u n d o", "M UW N D OW"),        # Spanish "mundo"
        ("tʃ e s", "CH EY S"),              # Spanish "che" (approx)
        ("b o n ʒ u ʁ", "B OW N ZH U R"),     # French "bonjour" (approx: phonemizer outputs nasal vowels as single chars)
        ("h a l o", "HH AA L OW"),           # Alternative
    ]

    print("IPA to ARPAbet mapping tests:")
    all_pass = True
    for ipa, expected in test_cases:
        result = map_ipa_sequence(ipa)
        status = "✓" if result == expected else "✗"
        print(f"  {status} '{ipa}' → '{result}' (expected: '{expected}')")
        if result != expected:
            all_pass = False

    if all_pass:
        print("\nAll tests passed!")
    else:
        print("\nSome tests failed - review mapping table (may be approximations)")