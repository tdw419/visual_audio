#!/usr/bin/env python3
"""
tools/text_to_container_note.py

Convert arbitrary text into a labeled note inside a visual audio container.
Pipeline: Text -> wordbase/word_compiler -> WAV -> container (as role='note')

Usage:
  python3 tools/text_to_container_note.py <container.mkv> <entry_name> "your text here"
  echo "your text" | python3 tools/text_to_container_note.py <container.mkv> <entry_name>
"""

import sys
import argparse
import subprocess
import tempfile
from pathlib import Path

# Import existing tools to handle the real heavy lifting
from text_to_visual_audio import WordbaseManager, convert_text_to_audio

def add_to_container(mkv_path: str, payload_path: str, name: str, note: str):
    """Adds the payload to the specified container."""
    cmd = [
        sys.executable, "tools/va_container.py", "add", 
        mkv_path, payload_path, 
        "--name", name, 
        "--role", "note",
        "--note", note
    ]
    print(f"Adding to container: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Error adding to container: {result.stderr}", file=sys.stderr)
        return False
    return True

def main():
    parser = argparse.ArgumentParser(description="Convert text to a visual audio container note")
    parser.add_argument('container', help='Path to the .mkv container')
    parser.add_argument('name', help='Name of the entry in the container')
    parser.add_argument('text', nargs='*', help='Text to convert (or read from stdin)')
    
    args = parser.parse_args()
    
    if args.text:
        text = ' '.join(args.text)
    else:
        text = sys.stdin.read().strip()
        
    if not text:
        print("Error: No text provided.", file=sys.stderr)
        sys.exit(1)
        
    print(f"Creating note '{args.name}' with text: {text[:50]}...")
    
    # Generate WAV
    wb = WordbaseManager()
    with tempfile.NamedTemporaryFile(suffix='.wav') as tmp_wav:
        try:
            success = convert_text_to_audio(
                text=text,
                wb=wb,
                output_path=tmp_wav.name,
                use_wordbase=True
            )
        finally:
            wb.close()
            
        if not success:
            print("Failed to generate audio from text.", file=sys.stderr)
            sys.exit(1)
            
        # Add to container
        if add_to_container(args.container, tmp_wav.name, args.name, "Auto-generated note"):
            print(f"Successfully added note '{args.name}' to {args.container}")
        else:
            sys.exit(1)

if __name__ == '__main__':
    main()
