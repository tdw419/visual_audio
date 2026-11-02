#!/usr/bin/env python3
"""
Test multilingual word support via phonemizer + XSAMPA→ARPAbet mapping.

This tests that foreign words (Spanish, French, German, etc.) can be added
to the wordbase with ARPAbet pronunciations that render as tiles.
"""

import sys
sys.path.insert(0, 'tools')

from wordbase_compat import connect, word_id

# Mock CMUdict for testing (empty - all words go through phonemizer or grapheme fallback)
mock_cmudict = {}

def test_multilingual():
    """Test that multilingual words get pronunciations via phonemizer."""

    db = connect()

    # Test cases: (word, expected_has_pronunciation)
    test_words = [
        # Latin words (should use grapheme fallback without phonemizer)
        ('hello', True),
        ('world', True),

        # Spanish words (should use phonemizer if available)
        ('hola', True),      # "hello"
        ('mundo', True),     # "world"
        ('gracias', True),   # "thank you"

        # French words
        ('bonjour', True),   # "hello"
        ('merci', True),     # "thank you"

        # German words
        ('hallo', True),     # "hello"
        ('danke', True),     # "thank you"
    ]

    print("Testing multilingual word_id with phonemizer integration:")
    print("=" * 70)

    for word, expected_has_pron in test_words:
        # Try with different language codes
        for lang in ['en', 'es', 'fr', 'de']:
            try:
                wid = word_id(db, word, mock_cmudict, lang=lang)
                cursor = db.execute(
                    'SELECT word, pronunciation FROM words WHERE id = ?',
                    (wid,)
                )
                result = cursor.fetchone()

                if result:
                    word_db, pron = result
                    has_pron = bool(pron and pron != word.upper())

                    status = "✓" if has_pron == expected_has_pron else "✗"

                    # Show first 3 phonemes for brevity
                    pron_short = ' '.join(pron.split()[:3]) + ('...' if len(pron.split()) > 3 else '')

                    print(f"{status} {word:12s} (lang={lang:4s}) → {pron_short:20s}")

                    # Clean up for next test
                    db.execute('DELETE FROM words WHERE id = ?', (wid,))
                    db.commit()

            except Exception as e:
                print(f"✗ {word:12s} (lang={lang:4s}) → ERROR: {e}")

    print("=" * 70)
    print("\nNote: Without phonemizer installed, all words fall back to")
    print("      grapheme pronunciation (uppercase letters).")
    print("\nWith phonemizer, foreign words get ARPAbet pronunciations")
    print("      via XSAMPA→ARPAbet mapping.")

if __name__ == '__main__':
    test_multilingual()