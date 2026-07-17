"""
Debug script to understand fixture behavior
"""

import pytest
import sqlite3
import tempfile
import os
from pathlib import Path


@pytest.fixture
def temp_wordbase():
    """Create a temporary wordbase with test data."""
    fd, db_path = tempfile.mkstemp(suffix=".db")
    
    print(f"Creating temp db at {db_path}")
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Create schema
    cursor.execute('''
        CREATE TABLE words (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            word TEXT NOT NULL UNIQUE COLLATE NOCASE,
            pronunciation TEXT NOT NULL,
            color_hex TEXT,
            pos TEXT NOT NULL,
            definition TEXT,
            frequency INTEGER DEFAULT 0
        )
    ''')
    
    # Insert test words with phonetic/semantic patterns
    test_words = [
        # Phonetically similar words (rhyming)
        ("embed_test", "T EH S T", "#508F6B", "noun", "A procedure", 1000),
        ("embed_best", "B EH S T", "#609F7B", "adjective", "Highest quality", 900),
        ("embed_rest", "R EH S T", "#70AF8B", "noun", "Repose", 800),
        
        # Semantically similar words (same POS, similar color)
        ("embed_visual", "V IH ZH UH L", "#50FB6B", "adjective", "Relating to sight", 1000),
        ("embed_optical", "AA P T IH K AH L", "#40EA5A", "adjective", "Relating to vision", 900),
        
        # Different words for contrast
        ("embed_audio", "AO D IY OW", "#A5CA50", "noun", "Sound", 1000),
        ("embed_code", "K OW D", "#20B2AA", "noun", "Programming", 1000),
    ]
    
    print(f"Inserting {len(test_words)} test words")
    for word, pron, color, pos, defn, freq in test_words:
        cursor.execute('''
            INSERT INTO words (word, pronunciation, color_hex, pos, definition, frequency)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (word, pron, color, pos, defn, freq))
    
    conn.commit()
    
    # Check count before yield
    cursor.execute('SELECT COUNT(*) FROM words')
    count = cursor.fetchone()[0]
    print(f"Words in DB before yield: {count}")
    
    conn.close()
    
    yield Path(db_path)
    
    # Cleanup
    print(f"Cleaning up {db_path}")
    import os
    os.close(fd)
    os.unlink(db_path)


def test_count(temp_wordbase):
    """Debug test to count words."""
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
    from pixel_embeddings import PixelEmbeddings
    
    # Check DB directly
    conn = sqlite3.connect(temp_wordbase)
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM words')
    count = cursor.fetchone()[0]
    print(f"Direct DB count: {count}")
    
    # List all words
    cursor.execute('SELECT word FROM words')
    words = cursor.fetchall()
    print(f"Words in DB: {[w[0] for w in words]}")
    conn.close()
    
    # Build embeddings
    embeddings = PixelEmbeddings(temp_wordbase)
    matrix = embeddings.build_embeddings(max_vocab=100)
    print(f"Built {matrix.shape[0]} embeddings")
    print(f"Vocab: {list(embeddings.word_to_id.keys())}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])