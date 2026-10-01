#!/usr/bin/env python3
"""
Simple IPA tokenizer for multi-lingual phoneme extraction.

Splits IPA strings into individual phoneme tokens, handling:
- Simple consonants/vowels: 'p', 'a', 'o'
- Diphthongs: 'aɪ', 'oʊ', 'eɪ'
- Affricates: 'tʃ', 'dʒ'
- Nasal vowels with diacritics: 'ɔ̃', 'ɑ̃'
- Precomposed nasal vowels: 'ã', 'õ', 'ẽ'
- Stress markers: 'ˈ', 'ˌ'
- Syllable boundaries: '.', '-'
"""

# Two-character phonemes (diphthongs, affricates, long vowels)
DIPHTHONGS = {
    'aɪ', 'aʊ', 'ɔɪ', 'eɪ', 'oʊ', 'ɛɪ', 'øɪ', 'øʏ',
    'tʃ', 'dʒ', 'ts', 'dz',
    'aː', 'eː', 'iː', 'oː', 'uː', 'ɛː', 'ɔː', 'ʌː', 'əː',
}

# Nasal vowels (base vowel + combining tilde)
NASAL_VOWELS = {
    'ɑ̃', 'ɔ̃', 'ɛ̃', 'œ̃', 'ĩ', 'ỹ', 'õ', 'ũ', 'ə̃', 'æ̃',
    'ã', 'õ',  # Common tilde variants (precomposed)
}

# Consonants with diacritics (handle common ones)
CONSONANTS_WITH_DIACRITICS = {
    'ɹ̩', 'l̩', 'n̩', 'm̩', 'ɾ̃',
}

# Additional nasal vowels (precomposed Unicode characters) - for ARPAbet mapping
PRECOMPOSED_NASAL_TO_ARPA = {
    'ã': 'AH',  # nasal a
    'õ': 'OW',  # nasal o
    'ẽ': 'EY',  # nasal e
    'ĩ': 'IY',  # nasal i
    'ũ': 'UW',  # nasal u
    'ỹ': 'IY',  # nasal y (approx)
}


def tokenize_ipa(ipa_string: str) -> list[str]:
    """
    Split IPA string into individual phoneme tokens.

    Args:
        ipa_string: IPA string (e.g., 'ola', 'haloː', 'bɔ̃ʒuʁ')

    Returns:
        List of phoneme tokens (e.g., ['o', 'l', 'a'], ['h', 'a', 'l', 'oː'])

    Examples:
        >>> tokenize_ipa('ola')
        ['o', 'l', 'a']
        >>> tokenize_ipa('haloː')
        ['h', 'a', 'l', 'oː']
        >>> tokenize_ipa('bɔ̃ʒuʁ')
        ['b', 'ɔ̃', 'ʒ', 'u', 'ʁ']
    """
    # Remove stress markers and syllable boundaries
    cleaned = ipa_string.replace('ˈ', '').replace('ˌ', '').replace('.', ' ').replace('-', ' ')

    tokens = []
    i = 0

    while i < len(cleaned):
        # Skip spaces
        if cleaned[i] == ' ':
            i += 1
            continue

        # Check for combining diacritics (tilde, ring, etc.)
        if i + 1 < len(cleaned) and ord(cleaned[i + 1]) >= 0x300 and ord(cleaned[i + 1]) <= 0x36F:
            # Combining diacritic - append to current character
            token = cleaned[i:i+2]

            # Check if this forms a nasal vowel
            if token in NASAL_VOWELS:
                tokens.append(token)
                i += 2
            elif token in CONSONANTS_WITH_DIACRITICS:
                tokens.append(token)
                i += 2
            else:
                # Unknown combination - just append the base char
                tokens.append(cleaned[i])
                i += 2
            continue

        # Check for two-character phonemes
        if i + 1 < len(cleaned):
            two_char = cleaned[i:i+2]
            if two_char in DIPHTHONGS:
                tokens.append(two_char)
                i += 2
                continue

        # Single character phoneme
        tokens.append(cleaned[i])
        i += 1

    return tokens


if __name__ == '__main__':
    # Test tokenization
    test_cases = [
        ('ola', ['o', 'l', 'a']),
        ('haloː', ['h', 'a', 'l', 'oː']),
        ('bɔ̃ʒuʁ', ['b', 'ɔ̃', 'ʒ', 'u', 'ʁ']),
        ('həloʊ', ['h', 'ə', 'l', 'oʊ']),
        ('tʃeɪ', ['tʃ', 'eɪ']),
        ('ˈhɛləʊ', ['h', 'ɛ', 'l', 'ə', 'ʊ']),
        ('não', ['n', 'ã']),  # Portuguese with precomposed tilde
    ]

    print("IPA tokenization tests:")
    all_pass = True
    for ipa, expected in test_cases:
        result = tokenize_ipa(ipa)
        status = "✓" if result == expected else "✗"
        print(f"  {status} '{ipa}' → {result} (expected: {expected})")
        if result != expected:
            all_pass = False

    if all_pass:
        print("\nAll tests passed!")
    else:
        print("\nSome tests failed")