#!/usr/bin/env python3
"""
Glyph-Wordbase Integration (Semantic Translator)

This module maps semantic tokens from wordbase.db directly to spatial Glyph assembly
macros, enabling the AI to interact with the OS purely through visual/spatial shapes
instead of text strings.

Example usage:
    python tools/glyph_wordbase.py translate "read directory"
"""

import sqlite3
import argparse
import os
from pathlib import Path

# Static Mapping of semantic OS operations to their spatial Opcode equivalents
# In Phase 3, this will be generated dynamically, but for now we define the contract.
SEMANTIC_TO_OPCODE = {
    "read": 19539,   # 0x4C53 ('LS')
    "list": 19539,
    "ls": 19539,
    "write": 22359,  # 0x5757 ('WW')
    "move": 19822,   # 0x4D6E ('MV')
    "execute": 17752 # 0x4558 ('EX')
}

def get_wordbase_semantics(word: str, db_path: str = "db/wordbase.db") -> dict:
    """Fetch the semantic definition and POS from Wordbase."""
    if not os.path.exists(db_path):
        return {"error": f"Database not found at {db_path}"}
        
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM words WHERE word = ? COLLATE NOCASE", (word,))
    row = cursor.fetchone()
    conn.close()
    
    if row:
        return dict(row)
    return None

def translate_to_glyph(semantic_intent: str) -> str:
    """
    Translates a human/AI semantic intent string (e.g., 'read 8192')
    into the corresponding SpaDSL macro call.
    """
    tokens = semantic_intent.lower().split()
    if not tokens:
        return ""
        
    action = tokens[0]
    opcode = SEMANTIC_TO_OPCODE.get(action)
    
    if not opcode:
        return f"# Error: No spatial mapping found for intent '{action}'"
        
    target_addr = 0
    if len(tokens) > 1 and tokens[1].isdigit():
        target_addr = int(tokens[1])
        
    spadsl_code = [
        f"# --- Glyph-Wordbase Expansion: {semantic_intent.upper()} ---",
        "ctrl = region(shape=(16, 16), layout='hilbert', initial=0)",
        f"sys_ls(target_address={target_addr}, control_region=ctrl)  # Opcode {opcode}"
    ]
    
    return "\n".join(spadsl_code)

def main():
    parser = argparse.ArgumentParser(description="Semantic Translator for Glyph OS")
    parser.add_argument("command", choices=["translate", "lookup"])
    parser.add_argument("intent", help="The semantic intent (e.g. 'read 8192')")
    args = parser.parse_args()
    
    if args.command == "lookup":
        result = get_wordbase_semantics(args.intent)
        if result:
            print(f"Wordbase Entry: {result['word']} ({result['pos']})")
            print(f"Definition: {result['definition']}")
        else:
            print(f"No entry found in wordbase for '{args.intent}'")
            
    elif args.command == "translate":
        code = translate_to_glyph(args.intent)
        print("Generated SpaDSL Semantic Macros:")
        print("---------------------------------")
        print(code)

if __name__ == "__main__":
    main()
