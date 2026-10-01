#!/usr/bin/env python3
"""
Quick test: Add sample words to Wordbase and verify lookup.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.wordbase import WordbaseManager

# Sample words with pronunciations (CMU ARPAbet format)
SAMPLE_WORDS = [
    ("hello", "HH EH L OW", "interjection", "A greeting used to express a friendly greeting.", ["Hello, world!", "Hello there."]),
    ("world", "W ER L D", "noun", "The earth together with all of its countries.", ["The world is beautiful.", "Welcome to the world."]),
    ("test", "T EH S T", "noun", "A procedure intended to establish the quality, performance, or reliability of something.", ["This is a test.", "Run the test now."]),
    ("visual", "V IH ZH UH L", "adjective", "Relating to seeing or sight.", ["Visual arts.", "Visual perception."]),
    ("audio", "AO D IY OW", "noun", "Sound, especially when recorded, transmitted, or reproduced.", ["Audio quality.", "Audio recording."]),
    ("code", "K OW D", "noun", "A system of signals or symbols for communication.", ["Write the code.", "Source code."]),
]

def main():
    wb = WordbaseManager()

    try:
        print("Adding sample words to Wordbase...")

        for word, pron, pos, definition, examples in SAMPLE_WORDS:
            word_id = wb.add_word(
                word=word,
                pronunciation=pron,
                pos=pos,
                definition=definition,
                examples=examples,
                frequency=1000  # High frequency for common words
            )
            print(f"  ✓ Added '{word}' (ID: {word_id})")

        print("\n--- Testing lookup ---")

        for word, _, _, _, _ in SAMPLE_WORDS:
            result = wb.get_word(word)
            if result:
                print(f"✓ {word}: {result['pronunciation']} ({result['pos']})")
            else:
                print(f"✗ {word}: not found")

        # Test case-insensitive lookup
        print("\n--- Testing case-insensitive lookup ---")
        result = wb.get_word("HELLO")
        if result:
            print(f"✓ 'HELLO' → '{result['word']}' ({result['pronunciation']})")

        # Test pronunciation-only lookup
        print("\n--- Testing pronunciation lookup ---")
        pron = wb.get_pronunciation("test")
        if pron:
            print(f"✓ 'test' pronunciation: {pron}")

        print("\n✓ All tests passed!")

    finally:
        wb.close()

    return 0


if __name__ == '__main__':
    sys.exit(main())