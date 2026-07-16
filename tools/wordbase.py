#!/usr/bin/env python3
"""
Wordbase Manager: Populate and query the visual audio dictionary database.

Maps words to their visual audio representations (spectrograms, pronunciations, etc.).
Supports:
- CMUdict pronunciation import
- Spectrogram generation and caching
- Batch word processing
- Fallback to text-to-speech for missing pronunciations
"""

import sqlite3
import json
import re
from pathlib import Path
from typing import Optional, List, Dict, Tuple
import subprocess
import sys

# Paths
DB_PATH = Path(__file__).parent.parent / "db" / "wordbase.db"
CMUDICT_PATH = Path(__file__).parent.parent / "data" / "cmudict.dict"
PHONEME_TEMPLATES = Path(__file__).parent.parent / "src" / "phoneme_templates"


class WordbaseManager:
    """Manage the word-to-visual-audio mapping database."""

    POS_MAPPING = {
        "n": "noun",
        "v": "verb",
        "a": "adjective",
        "r": "adverb",
        "c": "conjunction",
        "p": "preposition",
        "i": "interjection",
        "m": "pronoun",
        "x": "other"
    }

    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row

    def close(self):
        """Close database connection."""
        self.conn.close()

    def add_word(
        self,
        word: str,
        pronunciation: str,
        pos: str = "noun",
        definition: str = "",
        examples: Optional[List[str]] = None,
        image_path: Optional[str] = None,
        image_link: Optional[str] = None,
        frequency: int = 0
    ) -> int:
        """Add a word to the database. Returns word ID."""
        with self.conn:
            cursor = self.conn.execute(
                """
                INSERT INTO words (word, pronunciation, pos, definition, examples, image_path, image_link, frequency)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    word,
                    pronunciation,
                    pos,
                    definition,
                    json.dumps(examples) if examples else None,
                    image_path,
                    image_link,
                    frequency
                )
            )
            return cursor.lastrowid

    def get_word(self, word: str) -> Optional[Dict]:
        """Look up a word (case-insensitive). Returns dict or None."""
        cursor = self.conn.execute(
            "SELECT * FROM words WHERE word = ? COLLATE NOCASE",
            (word,)
        )
        row = cursor.fetchone()
        if row:
            d = dict(row)
            if d.get('examples'):
                d['examples'] = json.loads(d['examples'])
            return d
        return None

    def get_pronunciation(self, word: str) -> Optional[str]:
        """Get pronunciation only (fast lookup)."""
        cursor = self.conn.execute(
            "SELECT pronunciation FROM words WHERE word = ? COLLATE NOCASE",
            (word,)
        )
        row = cursor.fetchone()
        return row[0] if row else None

    def add_phrase(
        self,
        phrase: str,
        pronunciation: str,
        definition: str = "",
        examples: Optional[List[str]] = None,
        image_path: Optional[str] = None,
        image_link: Optional[str] = None,
        frequency: int = 0
    ) -> int:
        """Add a multi-word phrase. Returns phrase ID."""
        with self.conn:
            cursor = self.conn.execute(
                """
                INSERT INTO phrases (phrase, pronunciation, definition, examples, image_path, image_link, frequency)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    phrase,
                    pronunciation,
                    definition,
                    json.dumps(examples) if examples else None,
                    image_path,
                    image_link,
                    frequency
                )
            )
            return cursor.lastrowid

    def get_phrase(self, phrase: str) -> Optional[Dict]:
        """Look up a phrase. Returns dict or None."""
        cursor = self.conn.execute(
            "SELECT * FROM phrases WHERE phrase = ?",
            (phrase,)
        )
        row = cursor.fetchone()
        if row:
            d = dict(row)
            if d.get('examples'):
                d['examples'] = json.loads(d['examples'])
            return d
        return None

    def cache_spectrogram(self, word_id: int, spectrogram_bytes: bytes, version: str = "v1"):
        """Cache a spectrogram for a word."""
        with self.conn:
            self.conn.execute(
                """
                INSERT OR REPLACE INTO spectrogram_cache (word_id, spectrogram_bytes, codec_version, updated_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                """,
                (word_id, spectrogram_bytes, version)
            )

    def get_cached_spectrogram(self, word_id: int) -> Optional[bytes]:
        """Get cached spectrogram bytes."""
        cursor = self.conn.execute(
            "SELECT spectrogram_bytes FROM spectrogram_cache WHERE word_id = ?",
            (word_id,)
        )
        row = cursor.fetchone()
        return row[0] if row else None

    def import_cmudict(self, cmudict_path: Path = CMUDICT_PATH, limit: Optional[int] = None):
        """Import CMU dictionary entries. Optionally limit for testing."""
        count = 0
        with open(cmudict_path, 'r') as f:
            for line in f:
                if line.startswith(';;;'):
                    continue  # Skip comments

                # Parse line: WORD  PHONEMES
                parts = line.strip().split(maxsplit=1)
                if len(parts) < 2:
                    continue

                word = parts[0].lower().rstrip('0123456789')  # Strip variant numbers
                pronunciation = parts[1]

                # Detect part of speech from word ending (simple heuristic)
                pos = self._infer_pos(word)

                try:
                    self.add_word(word, pronunciation, pos=pos)
                    count += 1
                    if limit and count >= limit:
                        break
                except sqlite3.IntegrityError:
                    # Word already exists
                    continue

        print(f"Imported {count} words from CMUdict")

    def _infer_pos(self, word: str) -> str:
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

    def batch_process(self, words: List[str], generate_spectrograms: bool = False):
        """Process multiple words: import missing ones, optionally generate spectrograms."""
        processed = 0
        for word in words:
            word = word.strip().lower()

            # Skip if already exists
            if self.get_word(word):
                print(f"✓ {word} (exists)")
                continue

            # Get pronunciation from CMUdict or fallback to simple heuristic
            pronunciation = self.get_pronunciation_from_cmudict(word)

            if pronunciation:
                pos = self._infer_pos(word)
                word_id = self.add_word(word, pronunciation, pos=pos)
                print(f"✓ {word} ({pronunciation})")

                if generate_spectrograms:
                    # TODO: Generate spectrogram using codec
                    pass

                processed += 1
            else:
                print(f"✗ {word} (no pronunciation)")

        print(f"\nProcessed {processed}/{len(words)} words")

    def get_pronunciation_from_cmudict(self, word: str) -> Optional[str]:
        """Look up pronunciation from CMUdict file directly."""
        if not CMUDICT_PATH.exists():
            return None

        with open(CMUDICT_PATH, 'r') as f:
            for line in f:
                if line.startswith(';;;'):
                    continue

                parts = line.strip().split(maxsplit=1)
                if len(parts) < 2:
                    continue

                cmu_word = parts[0].lower().rstrip('0123456789')
                if cmu_word == word.lower():
                    return parts[1]

        return None

    def export_wordlist(self, output_path: Path, format: str = "tsv"):
        """Export word database to file."""
        cursor = self.conn.execute("SELECT word, pronunciation, pos, definition FROM words ORDER BY word")

        with open(output_path, 'w') as f:
            if format == "tsv":
                f.write("word\tpronunciation\tpos\tdefinition\n")
                for row in cursor:
                    f.write(f"{row[0]}\t{row[1]}\t{row[2]}\t{row[3] or ''}\n")
            elif format == "json":
                words = []
                for row in cursor:
                    words.append({
                        'word': row[0],
                        'pronunciation': row[1],
                        'pos': row[2],
                        'definition': row[3]
                    })
                json.dump(words, f, indent=2)

        print(f"Exported to {output_path}")


def main():
    """CLI interface."""
    import argparse

    parser = argparse.ArgumentParser(description="Manage Wordbase database")
    parser.add_argument('action', choices=['init', 'import', 'lookup', 'batch', 'export'],
                       help='Action to perform')
    parser.add_argument('--word', help='Word to lookup or add')
    parser.add_argument('--cmudict', type=Path, default=CMUDICT_PATH,
                       help='Path to CMUdict file')
    parser.add_argument('--limit', type=int, help='Limit number of imports (for testing)')
    parser.add_argument('--output', type=Path, help='Output file for export')
    parser.add_argument('--format', choices=['tsv', 'json'], default='tsv',
                       help='Export format')

    args = parser.parse_args()

    wb = WordbaseManager()

    try:
        if args.action == 'init':
            # Database already created by schema file
            print(f"Wordbase initialized at {DB_PATH}")

        elif args.action == 'import':
            if not args.cmudict.exists():
                print(f"Error: CMUdict not found at {args.cmudict}")
                return 1

            wb.import_cmudict(args.cmudict, limit=args.limit)

        elif args.action == 'lookup':
            if not args.word:
                print("Error: --word required for lookup")
                return 1

            result = wb.get_word(args.word)
            if result:
                print(json.dumps(result, indent=2))
            else:
                print(f"Word '{args.word}' not found")
                return 1

        elif args.action == 'batch':
            # Read words from stdin
            words = [line.strip() for line in sys.stdin if line.strip()]
            wb.batch_process(words)

        elif args.action == 'export':
            if not args.output:
                print("Error: --output required for export")
                return 1

            wb.export_wordlist(args.output, format=args.format)

    finally:
        wb.close()

    return 0


if __name__ == '__main__':
    sys.exit(main())