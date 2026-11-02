#!/usr/bin/env python3
"""
vamp_query.py — Voice query interface for VAMP.

Accepts spoken queries (text from STT), converts to phonemes,
fuzzy matches against fact summaries in the wordbase,
and optionally plays back the answer.
"""

import sys
import os
import json
import argparse
import re
from pathlib import Path

try:
    from thefuzz import fuzz
except ImportError:
    fuzz = None

sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.wordbase import WordbaseManager
from tools.speak import say_text

def text_to_phonemes(text: str, wb: WordbaseManager) -> str:
    """Convert text phrase to phonemes using Wordbase."""
    words = re.sub(r'[^a-zA-Z\s]', '', text).lower().split()
    phonemes = []
    for w in words:
        record = wb.get_word(w)
        if record and record["pronunciation"]:
            phonemes.append(record["pronunciation"])
        else:
            # Fallback simple spelling approximation if not in DB
            # A real implementation might use an ML G2P model here
            fallback = " ".join(list(w.upper())) 
            phonemes.append(fallback)
    return " ".join(phonemes)

def vamp_query(query: str, db_path: str = None, play_audio: bool = False, top_n: int = 3):
    if db_path is None:
        db_path = str(Path(__file__).parent.parent / "db" / "wordbase.db")
        
    wb = WordbaseManager(Path(db_path))
    
    # Parse query into phonemes
    query_phonemes = text_to_phonemes(query, wb)
    
    c = wb.conn.cursor()
    # Fetch all records with a definition to match against
    c.execute("SELECT word, pronunciation, definition FROM words WHERE definition IS NOT NULL AND definition != ''")
    rows = c.fetchall()
    
    results = []
    for row in rows:
        word = row["word"]
        definition = row["definition"]
        
        # In this implementation, we convert the fact summary (definition) to phonemes 
        # and do a fuzzy match between phonemes, which handles homophones.
        fact_phonemes = text_to_phonemes(definition, wb)
        
        if fuzz:
            # Compare phonemes for phonetic fuzzy matching
            phoneme_score = fuzz.token_set_ratio(query_phonemes, fact_phonemes)
            
            # Also compare text just in case (hybrid approach)
            text_score = fuzz.token_set_ratio(query.lower(), definition.lower())
            
            # Use max score
            score = max(phoneme_score, text_score)
        else:
            # Basic overlap if thefuzz is not installed
            q_ph = set(query_phonemes.split())
            f_ph = set(fact_phonemes.split())
            overlap = len(q_ph.intersection(f_ph))
            score = int((overlap / max(1, len(q_ph))) * 100)
            
        # Boost if the query directly mentions the word
        if word.lower() in query.lower():
            score = max(score, 90)
            
        if score > 0:
            results.append({
                "word": word,
                "fact_summary": definition,
                "confidence": score,
                "phonemes_matched": fact_phonemes
            })
            
    # Sort by confidence
    results.sort(key=lambda x: x["confidence"], reverse=True)
    top_results = results[:top_n]
    
    # Optional audio playback via speak.py
    if play_audio and top_results:
        best_match = top_results[0]
        output_wav = "/tmp/vamp_query_response.wav"
        print(f"Synthesizing response for: {best_match['word']}...")
        say_text(best_match['fact_summary'], output_wav)
        
    wb.close()
    
    return {
        "query": query,
        "query_phonemes": query_phonemes,
        "matches": top_results
    }

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--query", required=True, help="Spoken query text")
    parser.add_argument("--db", help="Path to wordbase.db")
    parser.add_argument("--play", action="store_true", help="Play audio of top match (generates /tmp/vamp_query_response.wav)")
    args = parser.parse_args()
    
    result = vamp_query(args.query, db_path=args.db, play_audio=args.play)
    print(json.dumps(result, indent=2))
