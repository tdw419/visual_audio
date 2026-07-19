#!/usr/bin/env python3
"""
DEMO: Code → Pixels → MKV → Execute workflow

This script demonstrates the complete Visual Audio pattern:
1. Tokenize code using wordbase.db (semantic pixel mapping)
2. Store code in visual_audio.mkv via dense encoding (byte-perfect)
3. Extract and execute the code from the MKV
"""

import sys
import os
import tempfile
import subprocess

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.pixel_tokenizer import PixelTokenizer
import tools.va_container as va_container


def tokenize_code_semantic(code: str, wordbase_path: str = "db/wordbase.db"):
    """
    Convert code to semantic pixel tokens using wordbase.db.

    Returns list of token IDs (each maps to an RGB pixel in wordbase).
    """
    print(f"=== STEP 1: Tokenizing code via wordbase.db ===")
    print(f"Code: {code[:50]}{'...' if len(code) > 50 else ''}")

    tokenizer = PixelTokenizer(wordbase_path=wordbase_path)
    token_ids = tokenizer.encode(code)

    print(f"Tokenized into {len(token_ids)} semantic tokens")
    print(f"First 10 token IDs: {token_ids[:10]}")

    # Show what the first few tokens map to
    # Convert single IDs to RGB using the formula: id = R << 16 | G << 8 | B
    pixels = tokenizer.ids_to_pixels(token_ids[:5])
    for i, (tid, pixel) in enumerate(zip(token_ids[:5], pixels)):
        word = tokenizer.decode([tid])
        r, g, b = pixel
        print(f"  Token {i}: ID={tid:4d} -> RGB({r:3d},{g:3d},{b:3d}) -> '{word}'")

    return token_ids


def store_code_in_mkv(mkv_path: str, code: str, content_name: str = "demo_code.py"):
    """
    Store code byte-perfectly in the MKV container using dense encoding.

    Each RGB pixel = 3 bytes of raw source code.
    """
    print(f"\n=== STEP 2: Storing code in MKV via dense encoding ===")
    print(f"MKV: {mkv_path}")
    print(f"Content name: {content_name}")
    print(f"Code size: {len(code)} bytes")

    # Write code to temp file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as tmp:
        tmp.write(code)
        tmp_path = tmp.name

    try:
        # Add to MKV container
        result = subprocess.run(
            ["python3", "tools/va_container.py", "add", mkv_path, tmp_path,
             "--name", content_name, "--role", "content"],
            capture_output=True,
            text=True
        )

        if result.returncode == 0:
            print("✓ Code successfully added to MKV container")
            print(f"  Stored as dense RGB24: {len(code)} bytes → {(len(code) + 2) // 3} pixels")
        else:
            print(f"✗ Failed to add to MKV: {result.stderr}")
            return False
    finally:
        os.unlink(tmp_path)

    return True


def extract_and_execute_from_mkv(mkv_path: str, content_name: str = "demo_code.py"):
    """
    Extract code from MKV and execute it.
    """
    print(f"\n=== STEP 3: Extracting and executing code from MKV ===")

    # Extract to temp file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as tmp:
        tmp_path = tmp.name

    try:
        result = subprocess.run(
            ["python3", "tools/va_container.py", "cat", mkv_path, content_name, "-o", tmp_path],
            capture_output=True,
            text=True
        )

        if result.returncode != 0:
            print(f"✗ Failed to extract from MKV: {result.stderr}")
            return None

        print(f"✓ Extracted to: {tmp_path}")

        # Show the extracted code
        with open(tmp_path, 'r') as f:
            extracted_code = f.read()
        print(f"Extracted code ({len(extracted_code)} bytes):")
        print("-" * 50)
        print(extracted_code)
        print("-" * 50)

        # Execute it
        print("\n=== STEP 4: Executing extracted code ===")
        exec_result = subprocess.run(
            ["python3", tmp_path],
            capture_output=True,
            text=True,
            timeout=5
        )

        print("STDOUT:", exec_result.stdout)
        if exec_result.stderr:
            print("STDERR:", exec_result.stderr)

        return exec_result.stdout

    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


def main():
    """Run the complete demo workflow."""
    DEMO_CODE = '''#!/usr/bin/env python3
"""Demo code executed from visual_audio.mkv"""
import sys

print("Hello from Visual Audio MKV!")
print(f"Python version: {sys.version}")
print(f"Executed from pixel storage")
'''

    MKV_PATH = "visual_audio.mkv"

    print("=" * 60)
    print("VISUAL AUDIO: Code → Pixels → MKV → Execute Workflow")
    print("=" * 60)

    # Step 1: Semantic tokenization (wordbase.db)
    token_ids = tokenize_code_semantic(DEMO_CODE)

    # Step 2: Dense storage in MKV
    if not store_code_in_mkv(MKV_PATH, DEMO_CODE, "demo_code.py"):
        print("\n✗ Demo failed at storage step")
        return 1

    # Step 3: Extract and execute
    output = extract_and_execute_from_mkv(MKV_PATH, "demo_code.py")

    if output and "Hello from Visual Audio MKV!" in output:
        print("\n" + "=" * 60)
        print("✓ COMPLETE: Code successfully round-tripped through pixels!")
        print("=" * 60)
        return 0
    else:
        print("\n✗ Demo failed at execution step")
        return 1


if __name__ == "__main__":
    sys.exit(main())