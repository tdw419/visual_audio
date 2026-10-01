"""
Tests for pixel embeddings from wordbase features.

Verifies that:
1. Embeddings are built correctly from wordbase
2. Neighbors share phonetic/semantic structure
3. Embeddings are normalized
4. Save/load works
"""

import pytest
import numpy as np
import sqlite3
import tempfile
from pathlib import Path
import sys

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from pixel_embeddings import PixelEmbeddings


@pytest.fixture
def temp_wordbase():
    """Create a temporary wordbase with test data."""
    fd, db_path = tempfile.mkstemp(suffix=".db")
    
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
    
    for word, pron, color, pos, defn, freq in test_words:
        cursor.execute('''
            INSERT INTO words (word, pronunciation, color_hex, pos, definition, frequency)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (word, pron, color, pos, defn, freq))
    
    conn.commit()
    conn.close()
    
    yield Path(db_path)
    
    # Cleanup
    import os
    os.close(fd)
    os.unlink(db_path)


def test_pixel_embeddings_basic(temp_wordbase):
    """Test that embeddings are built correctly."""
    embeddings = PixelEmbeddings(temp_wordbase)
    matrix = embeddings.build_embeddings(max_vocab=100)
    
    # Check shape
    assert matrix.shape[0] == 7  # 7 words in test data
    assert matrix.shape[1] == 64  # 64-dimensional embeddings
    
    # Check normalization (all vectors should have unit norm)
    norms = np.linalg.norm(matrix, axis=1)
    assert np.allclose(norms, 1.0, atol=1e-6)


def test_pixel_embeddings_neighbors(temp_wordbase):
    """Test that neighbors share phonetic/semantic structure."""
    embeddings = PixelEmbeddings(temp_wordbase)
    embeddings.build_embeddings(max_vocab=100)
    
    # Test phonetically similar words (embed_test, embed_best, embed_rest)
    neighbors_test = embeddings.get_neighbors("embed_test", k=3)
    neighbor_words = [n[0] for n in neighbors_test]
    
    # At least one should be phonetically similar (embed_best or embed_rest)
    assert any(word in ["embed_best", "embed_rest"] for word in neighbor_words), \
        f"Expected phonetic neighbors for 'embed_test', got {neighbor_words}"
    
    # Test semantically similar words (embed_visual, embed_optical)
    neighbors_visual = embeddings.get_neighbors("embed_visual", k=3)
    neighbor_words = [n[0] for n in neighbors_visual]
    
    # Should find 'embed_optical' as a semantic neighbor
    assert "embed_optical" in neighbor_words, \
        f"Expected 'embed_optical' as semantic neighbor for 'embed_visual', got {neighbor_words}"


def test_pixel_embeddings_save_load(temp_wordbase, tmp_path):
    """Test that embeddings can be saved and loaded."""
    # Build embeddings
    embeddings1 = PixelEmbeddings(temp_wordbase)
    matrix1 = embeddings1.build_embeddings(max_vocab=100)
    
    # Save
    save_path = tmp_path / "embeddings.npz"
    embeddings1.save(save_path)
    assert save_path.exists()
    
    # Load into new instance
    embeddings2 = PixelEmbeddings(temp_wordbase)
    embeddings2.load(save_path)
    
    # Verify matrices are the same
    assert np.allclose(embeddings1.embeddings, embeddings2.embeddings)
    
    # Verify word mappings are the same
    assert embeddings1.word_to_id == embeddings2.word_to_id
    assert embeddings1.id_to_word == embeddings2.id_to_word


def test_pixel_embeddings_word_not_found(temp_wordbase):
    """Test error handling for unknown words."""
    embeddings = PixelEmbeddings(temp_wordbase)
    embeddings.build_embeddings(max_vocab=100)
    
    # Should raise ValueError for unknown word
    with pytest.raises(ValueError, match="not in vocabulary"):
        embeddings.get_embedding("nonexistent_word")
    
    with pytest.raises(ValueError, match="not in vocabulary"):
        embeddings.get_neighbors("nonexistent_word")


def test_pixel_embeddings_not_built(temp_wordbase):
    """Test error handling when embeddings aren't built."""
    embeddings = PixelEmbeddings(temp_wordbase)
    
    # Should raise RuntimeError before build_embeddings is called
    with pytest.raises(RuntimeError, match="not built"):
        embeddings.get_embedding("test")
    
    with pytest.raises(RuntimeError, match="not built"):
        embeddings.get_neighbors("test")


def test_pixel_embeddings_feature_integration(temp_wordbase):
    """Test that all feature types (color, phonemes, POS) are integrated."""
    embeddings = PixelEmbeddings(temp_wordbase)
    matrix = embeddings.build_embeddings(max_vocab=100)
    
    # Check that embeddings vary (not all identical)
    # Compute pairwise distances
    center = np.mean(matrix, axis=0, keepdims=True)
    distances = np.linalg.norm(matrix - center, axis=1)
    
    # Should have variation in distances
    assert np.std(distances) > 0, "All embeddings are too similar - features may not be integrated"


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v"])