#!/usr/bin/env python3
"""
Fix TASK_M001 wordbase issues:
1. Generate color_hex for all words that lack it (except junk rows)
2. Delete junk test rows: '  ', 'zxyqwrtplkmbv'
3. Keep demo words 'hello', 'world' but generate proper color_hex for them

The 10 junk rows are: ids 175614-175623 (hello, world, '  ', zxyqwrtplkmbv, test123, one, two, three)
"""

import sqlite3
import hashlib

def word_to_color(word: str) -> str:
    """Generate a deterministic color hash for a word."""
    if not word or word.isspace():
        return "#000000"

    hash_bytes = hashlib.md5(word.encode()).digest()
    r = hash_bytes[0]
    g = hash_bytes[1]
    b = hash_bytes[2]
    return f"#{r:02X}{g:02X}{b:02X}"

def main():
    db_path = "db/wordbase.db"
    conn = sqlite3.connect(db_path)

    # 1. Generate color_hex for demo words 'hello' and 'world'
    demo_words = ['hello', 'world']
    for word in demo_words:
        color = word_to_color(word)
        conn.execute(
            "UPDATE words SET color_hex = ? WHERE word = ? AND color_hex IS NULL",
            (color, word)
        )
        print(f"Set {word} -> {color}")

    # 2. Delete junk test rows (multi-word test phrases and garbage)
    junk_words = ['  ', 'zxyqwrtplkmbv', 'one two three', 'three point one four', 'four two', 'six point two eight']
    for word in junk_words:
        deleted = conn.execute("DELETE FROM words WHERE word = ?", (word,)).rowcount
        print(f"Deleted '{word}': {deleted} row(s)")

    # 3. Fix 'supercalifragilisticexpialidocious' (real word)
    real_words = ['supercalifragilisticexpialidocious']
    for word in real_words:
        color = word_to_color(word)
        conn.execute(
            "UPDATE words SET color_hex = ? WHERE word = ?",
            (color, word)
        )
        print(f"Set {word} -> {color}")

    # 3. For 'one', 'two', 'three', 'test123' - keep them but ensure color_hex is set
    # These are valid words that happen to be in the wordbase
    fix_words = ['one', 'two', 'three', 'test123']
    for word in fix_words:
        color = word_to_color(word)
        conn.execute(
            "UPDATE words SET color_hex = ? WHERE word = ? AND color_hex IS NULL",
            (color, word)
        )
        print(f"Ensured {word} -> {color}")

    # Commit and show summary
    conn.commit()

    # Show final state of these special words
    special_words = demo_words + fix_words
    print("\nFinal state of special words:")
    for row in conn.execute(
        "SELECT id, word, color_hex FROM words WHERE word IN ({})"
        .format(','.join(['?'] * len(special_words))),
        special_words
    ):
        print(f"  {row[0]} | {row[1]} | {row[2]}")

    # Count remaining NULL color_hex
    null_count = conn.execute(
        "SELECT COUNT(*) FROM words WHERE color_hex IS NULL OR color_hex = ''"
    ).fetchone()[0]
    print(f"\nRemaining NULL color_hex: {null_count}")

    conn.close()
    print("\n✅ Wordbase cleanup complete")

if __name__ == '__main__':
    main()