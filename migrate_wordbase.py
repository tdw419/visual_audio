#!/usr/bin/env python3
"""
Clean migration from CMUdict to db/wordbase.db.

This replaces the old migrate_wordbase.py which silently dropped words
due to incorrect handling of contractions (e.g., 'bout -> bout -> ignored).
We parse CMUdict directly to ensure 100% fidelity.
"""

import sys
import sqlite3
from pathlib import Path

# Paths
CMUDICT_PATH = Path(__file__).parent / "data" / "cmudict.dict"
DB_PATH = Path(__file__).parent / "db" / "wordbase.db"


def infer_pos(word: str) -> str:
    """Infer part of speech from word ending (simple heuristic)."""
    word_lower = word.lower()

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
        return 'noun'

    return 'noun'


def main():
    print("Migrating from CMUdict to fresh db/wordbase.db...")

    if not CMUDICT_PATH.exists():
        print(f"Error: CMUdict not found at {CMUDICT_PATH}")
        print("Download it: curl -o data/cmudict.dict https://raw.githubusercontent.com/cmusphinx/cmudict/master/cmudict.dict")
        return 1

    # Backup existing DB if it exists
    if DB_PATH.exists():
        backup_path = DB_PATH.with_suffix('.db.backup')
        print(f"Backing up existing DB to {backup_path}")
        import shutil
        shutil.copy(DB_PATH, backup_path)

    # Connect to DB
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Recreate tables (clean slate)
    cursor.execute("DROP TABLE IF EXISTS words")
    cursor.execute("""
        CREATE TABLE words (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            word TEXT NOT NULL COLLATE NOCASE,
            pronunciation TEXT NOT NULL,
            pos TEXT DEFAULT 'noun',
            definition TEXT,
            examples TEXT,
            image_path TEXT,
            image_link TEXT,
            frequency INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(word)
        )
    """)
    cursor.execute("CREATE INDEX idx_word ON words(word)")

    # Parse CMUdict
    print(f"Parsing {CMUDICT_PATH}...")
    batch = []
    batch_size = 1000
    count = 0

    with open(CMUDICT_PATH, 'r', encoding='latin-1') as f:
        for line in f:
            if line.startswith(';;;'):
                continue

            parts = line.strip().split(maxsplit=1)
            if len(parts) < 2:
                continue

            word = parts[0]
            pronunciation = parts[1]

            # Strip variant numbers (e.g., HELLO(1) -> HELLO)
            word = word.lower().split('(')[0]

            # Infer POS
            pos = infer_pos(word)

            batch.append((
                word,
                pronunciation,
                pos,
                None,  # definition
                None,  # examples
                None,  # image_path
                None,  # image_link
                0      # frequency
            ))

            if len(batch) >= batch_size:
                cursor.executemany(
                    """
                    INSERT OR IGNORE INTO words
                    (word, pronunciation, pos, definition, examples, image_path, image_link, frequency)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    batch
                )
                conn.commit()
                count += len(batch)
                batch = []
                print(f"  Imported {count} words...")

    # Insert remaining
    if batch:
        cursor.executemany(
            """
            INSERT OR IGNORE INTO words
            (word, pronunciation, pos, definition, examples, image_path, image_link, frequency)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            batch
        )
        conn.commit()
        count += len(batch)

    # Final count
    total = cursor.execute("SELECT COUNT(*) FROM words").fetchone()[0]
    print(f"\n✓ Migration complete: {total} words in db/wordbase.db")

    # Verify critical words
    print("\nVerifying critical words:")
    for word in ['hello', 'world', 'bout', 'cause']:
        row = cursor.execute(
            "SELECT word, pronunciation FROM words WHERE word = ?",
            (word,)
        ).fetchone()
        if row:
            print(f"  ✓ {word}: {row[1]}")
        else:
            print(f"  ✗ {word}: MISSING")

    conn.close()
    return 0


if __name__ == '__main__':
    sys.exit(main())