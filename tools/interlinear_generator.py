#!/usr/bin/env python3
"""
Interlinear Translation Generator for Visual Audio

Uses wordbase.db to render books in interlinear format:
  [Source Word]   [Source ARPAbet]   [Target Word]   [Target ARPAbet]

Schema Pattern (per visual-audio-wordbase skill):
  - words.lang: Language code ('en', 'es', etc.)
  - translations table: Links src_id <-> dst_id

Usage:
  python3 tools/interlinear_generator.py setup      # Initialize schema
  python3 tools/interlinear_generator.py add <src> <dst> <lang>  # Add manual translation
  python3 tools/interlinear_generator.py render <text> <target_lang>  # Render view
"""

import sqlite3
import sys
import os

# Add tools to path for wordbase_compat
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'tools'))
from wordbase_compat import connect, word_id

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'db', 'wordbase.db')

def ensure_schema(db):
    """
    Apply the recommended Visual Audio translation schema pattern.
    """
    cursor = db.cursor()

    # 1. Add 'lang' column to words table (default 'en')
    try:
        cursor.execute("ALTER TABLE words ADD COLUMN lang TEXT DEFAULT 'en'")
        print("[Schema] Added 'lang' column to words table")
    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e):
            pass  # Already exists
        else:
            raise

    # 2. Create translations table (many-to-many relationship)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS translations (
            src_id INTEGER NOT NULL,
            dst_id INTEGER NOT NULL,
            lang TEXT NOT NULL,
            confidence REAL DEFAULT 1.0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (src_id, dst_id, lang),
            FOREIGN KEY (src_id) REFERENCES words(id) ON DELETE CASCADE,
            FOREIGN KEY (dst_id) REFERENCES words(id) ON DELETE CASCADE
        )
    """)
    print("[Schema] Ensured translations table exists")

    # 3. Create index for faster lookups
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_translations_src
        ON translations(src_id, lang)
    """)
    db.commit()


def get_or_create_word(db, word_text, lang='en'):
    """
    Get word ID from DB or create it using wordbase logic.
    Uses phonemizer for OOV words automatically.
    """
    # Normalize input
    word_text = word_text.strip().lower()

    # Check if exists in this language
    cursor = db.cursor()
    cursor.execute("SELECT id FROM words WHERE word = ? AND lang = ?", (word_text, lang))
    row = cursor.fetchone()

    if row:
        return row[0]

    # Fallback: use existing wordbase logic (word_id handles CMUdict/phonemizer)
    # Note: word_id doesn't respect 'lang' arg in the compat layer perfectly,
    # so we insert explicitly if needed.
    # For this demo, we'll rely on the tokenizer's phonemizer integration.

    # Insert with lang tag
    # In a real scenario, we'd call word_id() to get pronunciation, then insert.
    # Here we assume wordbase_compat handles the phonetic lookup.
    word_id_val = word_id(db, word_text, {}, lang=lang)  # Returns int ID

    # Update the lang tag for this entry (word_id might default to 'en')
    cursor.execute("UPDATE words SET lang = ? WHERE id = ?", (lang, word_id_val))
    db.commit()

    return word_id_val


def add_translation(db, src_word, dst_word, target_lang, confidence=1.0):
    """
    Manually link a source word to a target word.
    """
    src_id = get_or_create_word(db, src_word, 'en')  # Assuming English source for now
    dst_id = get_or_create_word(db, dst_word, target_lang)

    cursor = db.cursor()
    try:
        cursor.execute("""
            INSERT INTO translations (src_id, dst_id, lang, confidence)
            VALUES (?, ?, ?, ?)
        """, (src_id, dst_id, target_lang, confidence))
        db.commit()
        print(f"[Translation] Added: '{src_word}' -> '{dst_word}' ({target_lang})")
        return True
    except sqlite3.IntegrityError:
        print(f"[Translation] Already exists: '{src_word}' -> '{dst_word}' ({target_lang})")
        return False


def get_translation_id(db, src_word, target_lang):
    """
    Find the ID of the translated word for a given source word.
    Returns None if no translation exists.
    """
    cursor = db.cursor()
    cursor.execute("""
        SELECT dst_id
        FROM translations
        JOIN words src ON translations.src_id = src.id
        WHERE src.word = ? AND translations.lang = ?
        LIMIT 1
    """, (src_word.lower(), target_lang))

    row = cursor.fetchone()
    return row[0] if row else None


def render_interlinear(db, text, target_lang):
    """
    Renders text in interlinear format.

    Output:
        [Source] [Source ARPAbet]   [Target] [Target ARPAbet]
    """
    # Import tokenize from wordbase_compat
    from wordbase_compat import tokenize

    tokens = tokenize(text)
    cursor = db.cursor()

    print(f"\n=== Interlinear View (Target: {target_lang.upper()}) ===")
    print(f"{'Source':<15} {'Source Phoneme':<30} {'Target':<15} {'Target Phoneme':<30}")
    print("-" * 90)

    for token in tokens:
        # 1. Get Source Data
        cursor.execute(
            "SELECT word, pronunciation FROM words WHERE word = ? AND lang = 'en'",
            (token,)
        )
        src_row = cursor.fetchone()

        if not src_row:
            # OOV or non-English word in source (unlikely for this demo)
            src_word, src_pron = token, "[UNK]"
        else:
            src_word, src_pron = src_row

        # 2. Get Translation ID
        trans_id = get_translation_id(db, token, target_lang)

        # 3. Get Target Data
        if trans_id:
            cursor.execute(
                "SELECT word, pronunciation FROM words WHERE id = ?",
                (trans_id,)
            )
            dst_row = cursor.fetchone()
            dst_word, dst_pron = dst_row if dst_row else ("[ERR]", "[ERR]")
        else:
            dst_word, dst_pron = "[MISSING]", "[MISSING]"

        # 4. Print Line
        print(f"{src_word:<15} {src_pron:<30} {dst_word:<15} {dst_pron:<30}")


def demo():
    """
    Quick demo of the interlinear pipeline.
    """
    import textwrap

    db = connect()  # Uses default DB path

    # 1. Setup Schema
    ensure_schema(db)

    # 2. Seed some manual translations (English -> Spanish)
    # In production, this would come from an MT API (DeepL, Google Translate)
    sample_translations = [
        ("the", "el"),
        ("book", "libro"),
        ("is", "es"),
        ("on", "en"),
        ("table", "mesa"),
        ("hello", "hola"),
        ("world", "mundo"),
        ("software", "software"),
        ("exists", "existe"),
    ]

    print("\n[Demo] Seeding sample translations...")
    for src, dst in sample_translations:
        add_translation(db, src, dst, 'es')

    # 3. Render a sample text
    sample_text = "the book is on the table. hello world. software exists."

    render_interlinear(db, sample_text, 'es')

    db.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        demo()
    else:
        db = connect()  # Uses default DB path
        command = sys.argv[1]

        if command == "setup":
            ensure_schema(db)
            print("Schema setup complete.")

        elif command == "add":
            if len(sys.argv) != 5:
                print("Usage: add <src_word> <dst_word> <target_lang>")
                sys.exit(1)
            add_translation(db, sys.argv[2], sys.argv[3], sys.argv[4])

        elif command == "render":
            if len(sys.argv) != 4:
                print("Usage: render '<text>' <target_lang>")
                sys.exit(1)
            render_interlinear(db, sys.argv[2], sys.argv[3])

        else:
            print(f"Unknown command: {command}")
            sys.exit(1)

        db.close()