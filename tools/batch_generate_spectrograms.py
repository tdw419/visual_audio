#!/usr/bin/env python3
"""
Batch spectrogram generator - process all words in wordbase with missing spectrograms.

This script generates spectrograms for words that don't have them yet,
using the wordbase_spectrogram_generator module.

Usage:
    python3 tools/batch_generate_spectrograms.py --limit 100
    python3 tools/batch_generate_spectrograms.py --all
"""

import argparse
import sys
import sqlite3
from pathlib import Path
from typing import Optional

# Add tools to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'tools'))

from wordbase_spectrogram_generator import get_spectrogram_for_word, batch_generate_spectrograms

DB_PATH = Path(__file__).parent.parent / 'db' / 'wordbase.db'


def get_words_without_spectrograms(limit: Optional[int] = None) -> list:
    """Get words from wordbase that don't have cached spectrograms yet."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Join with spectrogram_cache to find words without spectrograms
    query = """
        SELECT w.word, w.pronunciation, w.id
        FROM words w
        WHERE w.pronunciation IS NOT NULL
        AND w.pronunciation != ''
        AND NOT EXISTS (
            SELECT 1 FROM spectrogram_cache sc WHERE sc.word_id = w.id
        )
        ORDER BY w.frequency DESC
    """
    if limit is not None:
        query += f" LIMIT {limit}"

    cursor.execute(query)
    results = cursor.fetchall()
    conn.close()

    return [(row[0], row[1], row[2]) for row in results]


def batch_generate(limit: Optional[int] = None, parallel: bool = False):
    """
    Generate spectrograms for words that don't have them.

    Args:
        limit: Maximum number of words to process (None = all)
        parallel: Use parallel processing (experimental)
    """
    # Get words to process (word, pronunciation, word_id)
    words_data = get_words_without_spectrograms(limit)

    if not words_data:
        print("No words found needing spectrograms")
        return

    total = len(words_data)
    print(f"Found {total} words in wordbase needing spectrograms")

    # Process
    print("\nGenerating spectrograms and caching to DB...\n")

    # Import wordbase manager for DB writes
    from wordbase import WordbaseManager
    wb = WordbaseManager()

    # Import for PNG conversion
    from PIL import Image
    import numpy as np
    import io

    success = 0
    failed = 0
    for i, (word, pronunciation, word_id) in enumerate(words_data, 1):
        result = get_spectrogram_for_word(word, pronunciation)
        if result:
            # Convert spectrogram data to PNG bytes and cache to DB
            spec_array = np.array(result['spectrogram_normalized'])
            spec_image = Image.fromarray((spec_array * 255).astype(np.uint8), mode='L')
            img_buffer = io.BytesIO()
            spec_image.save(img_buffer, format='PNG')
            img_bytes = img_buffer.getvalue()

            wb.cache_spectrogram(word_id, img_bytes, version='v1')
            print(f"[{i}/{total}] ✓ {word}: {result['spectrogram_shape']} ({result['duration']:.2f}s)")
            success += 1
        else:
            print(f"[{i}/{total}] ✗ {word}: failed")
            failed += 1

    wb.close()

    print(f"\nDone: {success} succeeded, {failed} failed")


def main():
    parser = argparse.ArgumentParser(
        description='Batch generate spectrograms for wordbase words',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  # Generate first 100 spectrograms
  python3 batch_generate_spectrograms.py --limit 100

  # Generate all missing spectrograms
  python3 batch_generate_spectrograms.py --all
        '''
    )
    parser.add_argument('--limit', type=int, help='Limit number of words to process')
    parser.add_argument('--all', action='store_true', help='Process all words (no limit)')
    parser.add_argument('--parallel', action='store_true', help='Use parallel processing (experimental)')

    args = parser.parse_args()

    if not args.all and not args.limit:
        print("Error: specify --limit N or --all")
        sys.exit(1)

    limit: Optional[int] = None if args.all else args.limit
    batch_generate(limit, parallel=args.parallel)


if __name__ == '__main__':
    main()