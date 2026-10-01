#!/usr/bin/env python3
"""
test_vamp_voice_query.py — Verify VAMP voice query interface.

Tests:
1. Phoneme query parsing
2. Fuzzy match accuracy (>85% for clear speech)
3. Confidence scoring
4. Audio playback invocation
5. JSON round-trip / data structure correctness
"""

import sys
import os
import tempfile
import json
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.vamp_query import vamp_query, text_to_phonemes
from tools.wordbase import WordbaseManager

def setup_test_wordbase(db_path: Path):
    wb = WordbaseManager(db_path)
    c = wb.conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS words (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            word TEXT NOT NULL COLLATE NOCASE,
            pronunciation TEXT NOT NULL,
            pos TEXT DEFAULT 'noun',
            definition TEXT,
            examples TEXT,
            image_path TEXT,
            image_link TEXT,
            color_hex TEXT,
            frequency INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(word)
        )
    """)
    # Add a few facts
    wb.add_word("roadmap", "R OW D M AE P", "noun", "completion status is currently in progress")
    wb.add_word("completion", "K AH M P L IY SH AH N", "noun", "finishing a task")
    wb.add_word("status", "S T AE T AH S", "noun", "current state of affairs")
    wb.add_word("progress", "P R AA G R EH S", "noun", "moving forward")
    wb.add_word("currently", "K ER AH N T L IY", "adverb", "at this moment")
    wb.add_word("is", "IH Z", "verb", "to be")
    wb.add_word("in", "IH N", "preposition", "inside")
    
    # Also add some random words to ensure fuzzy matching has alternatives
    wb.add_word("apple", "AE P AH L", "noun", "a red fruit")
    wb.add_word("banana", "B AH N AE N AH", "noun", "a yellow fruit")
    wb.close()


def test_vamp_query():
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "test_wordbase.db"
        setup_test_wordbase(db_path)
        
        # 1. Phoneme query parsing & Fuzzy Match Accuracy
        query = "what is the roadmap completion status"
        # Using a mock for play_audio to verify it gets called
        with patch("tools.vamp_query.say_text") as mock_speak:
            result = vamp_query(query, db_path=str(db_path), play_audio=True)
            
            # JSON round-trip verification
            json_str = json.dumps(result)
            loaded_result = json.loads(json_str)
            
            # Verify basic structure
            assert "query" in loaded_result
            assert "query_phonemes" in loaded_result
            assert "matches" in loaded_result
            
            # Phonemes should be parsed
            assert "R OW D M AE P" in loaded_result["query_phonemes"]
            
            # Matches should be found
            assert len(loaded_result["matches"]) > 0
            
            # Best match should be "roadmap" because its definition matches the query terms heavily
            best_match = loaded_result["matches"][0]
            
            # Confidence scoring
            assert best_match["confidence"] > 85, f"Expected confidence > 85%, got {best_match['confidence']}%"
            
            # Audio playback
            mock_speak.assert_called_once()
            args, kwargs = mock_speak.call_args
            assert best_match["fact_summary"] == args[0]
            assert str(args[1]) == "/tmp/vamp_query_response.wav"

            print("✓ Voice query tests passed (phoneme parse, fuzzy match >85%, confidence score, audio, JSON)")


if __name__ == "__main__":
    test_vamp_query()
