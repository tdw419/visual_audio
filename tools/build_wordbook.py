#!/usr/bin/env python3
import sqlite3
import hashlib
from PIL import Image
import os

DB_PATH = 'db/wordbase.db'
OUTPUT_PATH = 'wordbook.png'
WIDTH = 4096
HEIGHT = 32

def build_wordbook():
    print(f"Connecting to {DB_PATH}...")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Get all words with IDs
    cursor.execute("SELECT id, color_hex FROM words")
    rows = cursor.fetchall()
    
    print(f"Fetched {len(rows)} words from database.")
    
    # Create image (RGBA to support potential flags in alpha channel later)
    img = Image.new('RGBA', (WIDTH, HEIGHT), color=(0, 0, 0, 255))
    pixels = img.load()
    
    mapped_count = 0
    max_id = 0
    
    for row in rows:
        word_id, color_hex = row
        
        if word_id > max_id:
            max_id = word_id
            
        if word_id >= WIDTH * HEIGHT:
            print(f"WARNING: ID {word_id} exceeds texture capacity ({WIDTH * HEIGHT})")
            continue
            
        x = word_id % WIDTH
        y = word_id // WIDTH
        
        if color_hex:
            # Parse hex string (e.g., "#1a2b3c")
            color_hex = color_hex.strip('#')
            if len(color_hex) == 6:
                r = int(color_hex[0:2], 16)
                g = int(color_hex[2:4], 16)
                b = int(color_hex[4:6], 16)
                pixels[x, y] = (r, g, b, 255)
                mapped_count += 1
                
    img.save(OUTPUT_PATH)
    print(f"Saved {OUTPUT_PATH} (Mapped {mapped_count}/{len(rows)} colors, Max ID: {max_id})")
    
    # Compute SHA256 for VCC validation
    with open(OUTPUT_PATH, 'rb') as f:
        data = f.read()
        sha256 = hashlib.sha256(data).hexdigest()
        
    print(f"VCC Hashes:\nwordbook.png: {sha256}")
    
    # Also dump metadata
    with open('wordbook.meta.json', 'w') as f:
        f.write(f'{{"sha256": "{sha256}", "width": {WIDTH}, "height": {HEIGHT}, "max_id": {max_id}, "colored_words": {mapped_count}}}')
    
if __name__ == '__main__':
    build_wordbook()
