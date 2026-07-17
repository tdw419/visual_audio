#!/usr/bin/env python3
"""
Add color_hex encoding to words based on semantic properties.

Maps words to colors for semantic visualization.
"""

import sqlite3
import sys
from pathlib import Path
from typing import Dict, List, Tuple

# Color palette mapping by word category and sound properties
COLOR_PALETTES = {
    'warm': {
        'colors': ['#FF5733', '#FF6B35', '#FF8C00', '#FFA500', '#FFB347'],
        'keywords': ['hot', 'fire', 'warm', 'burn', 'heat', 'sun', 'red', 'orange', 'yellow']
    },
    'cool': {
        'colors': ['#00BFFF', '#1E90FF', '#4169E1', '#0000FF', '#00008B'],
        'keywords': ['cold', 'cool', 'ice', 'freeze', 'water', 'ocean', 'sea', 'blue']
    },
    'nature': {
        'colors': ['#228B22', '#32CD32', '#00FF00', '#7CFC00', '#90EE90'],
        'keywords': ['tree', 'plant', 'leaf', 'forest', 'grass', 'green', 'nature']
    },
    'action': {
        'colors': ['#FF0000', '#DC143C', '#B22222', '#8B0000', '#800000'],
        'keywords': ['run', 'jump', 'go', 'move', 'fast', 'quick', 'speed', 'action']
    },
    'calm': {
        'colors': ['#87CEEB', '#ADD8E6', '#E0FFFF', '#F0F8FF', '#F5F5DC'],
        'keywords': ['calm', 'quiet', 'peace', 'soft', 'slow', 'gentle', 'light']
    },
    'danger': {
        'colors': ['#FF0000', '#FF4500', '#FF6347', '#FF7F50', '#FFA07A'],
        'keywords': ['danger', 'warning', 'alert', 'error', 'fail', 'wrong', 'stop']
    },
    'success': {
        'colors': ['#00FF00', '#32CD32', '#7CFC00', '#98FB98', '#90EE90'],
        'keywords': ['success', 'pass', 'ok', 'good', 'done', 'complete', 'ready']
    },
    'tech': {
        'colors': ['#00FFFF', '#00CED1', '#20B2AA', '#008B8B', '#008080'],
        'keywords': ['code', 'data', 'system', 'tech', 'computer', 'digital', 'ai']
    }
}


def infer_color_from_word(word: str) -> str:
    """
    Infer a color for a word based on its semantic properties.

    Args:
        word: The word to colorize

    Returns:
        Hex color string (e.g., '#FF5733')
    """
    word_lower = word.lower()

    # Direct color names
    color_map = {
        'red': '#FF0000',
        'blue': '#0000FF',
        'green': '#008000',
        'yellow': '#FFFF00',
        'orange': '#FFA500',
        'purple': '#800080',
        'pink': '#FFC0CB',
        'black': '#000000',
        'white': '#FFFFFF',
        'gray': '#808080',
        'brown': '#A52A2A',
        'cyan': '#00FFFF',
        'magenta': '#FF00FF'
    }

    if word_lower in color_map:
        return color_map[word_lower]

    # Semantic category matching
    for category, data in COLOR_PALETTES.items():
        for keyword in data['keywords']:
            if keyword in word_lower or word_lower in keyword:
                # Pick color based on word hash for consistency
                idx = hash(word_lower) % len(data['colors'])
                return data['colors'][idx]

    # Fallback: generate color from word hash
    return color_from_hash(word_lower)


def color_from_hash(word: str) -> str:
    """
    Generate a deterministic color from word hash.

    Args:
        word: The word to hash

    Returns:
        Hex color string
    """
    import hashlib

    # Hash the word
    h = hashlib.md5(word.encode()).hexdigest()

    # Use first 6 chars for RGB
    r = int(h[0:2], 16)
    g = int(h[2:4], 16)
    b = int(h[4:6], 16)

    # Ensure colors aren't too dark
    r = max(r, 80)
    g = max(g, 80)
    b = max(b, 80)

    return f'#{r:02X}{g:02X}{b:02X}'


def batch_colorize(db_path: Path, batch_size: int = 1000):
    """
    Batch update color_hex for all words.

    Args:
        db_path: Path to database
        batch_size: Number of words per batch
    """
    conn = sqlite3.connect(str(db_path))

    try:
        # Get words without colors
        cursor = conn.execute(
            "SELECT id, word FROM words WHERE color_hex IS NULL"
        )
        words = cursor.fetchall()

        print(f"Found {len(words)} words to colorize...")

        updated = 0
        batch = []

        for word_id, word in words:
            color = infer_color_from_word(word)
            batch.append((color, word_id))

            # Execute batch
            if len(batch) >= batch_size:
                conn.executemany(
                    "UPDATE words SET color_hex = ? WHERE id = ?",
                    batch
                )
                conn.commit()
                updated += len(batch)
                batch = []
                print(f"  Updated {updated}/{len(words)} words...")

        # Execute remaining batch
        if batch:
            conn.executemany(
                "UPDATE words SET color_hex = ? WHERE id = ?",
                batch
            )
            conn.commit()
            updated += len(batch)

        print(f"\n✓ Updated {updated} words with colors")

        # Verify sample words
        print("\nVerifying color assignments:")
        for test_word in ['red', 'blue', 'danger', 'calm', 'code', 'hello']:
            cursor = conn.execute(
                "SELECT word, color_hex FROM words WHERE word = ? LIMIT 1",
                (test_word,)
            )
            row = cursor.fetchone()
            if row:
                print(f"  ✓ {test_word}: {row[1]}")

    finally:
        conn.close()


def main():
    db_path = Path(__file__).parent / "db" / "wordbase.db"

    if not db_path.exists():
        print(f"Error: Database not found at {db_path}")
        return 1

    batch_colorize(db_path)
    return 0


if __name__ == '__main__':
    sys.exit(main())