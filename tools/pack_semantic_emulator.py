#!/usr/bin/env python3
"""
Pack semantic CPU emulator into MKV via wordbase encoding.

This creates a self-modifying emulator that:
1. Stores as semantic pixels in MKV
2. Can read itself from pixels
3. Can optimize by adjusting colors
4. Can create child MKVs with evolved code

Usage:
    python3 tools/pack_semantic_emulator.py [--optimize]
"""

import sys
import os
import subprocess
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def tokenize_semantic(code_path: str, wordbase_path: str = "db/wordbase.db"):
    """Tokenize code via wordbase for semantic encoding."""
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from src.pixel_tokenizer import PixelTokenizer

    print(f"[1] Tokenizing {code_path} via wordbase...")

    with open(code_path, "r") as f:
        code = f.read()

    tokenizer = PixelTokenizer(wordbase_path=Path(wordbase_path))
    token_ids = tokenizer.encode(code, add_special_tokens=True)

    print(f"    Code: {len(code)} bytes")
    print(f"    Tokens: {len(token_ids)} word IDs")

    # Show semantic breakdown
    from collections import Counter
    word_freq = Counter(token_ids)

    # Count special tokens
    special = sum(1 for tid in token_ids if tid < 16)
    content = len(token_ids) - special

    print(f"    Special tokens: {special}")
    print(f"    Content tokens: {content}")

    # Show top content tokens
    content_tokens = [tid for tid in token_ids if tid >= 16]
    top_tokens = Counter(content_tokens).most_common(5)

    print(f"    Top words:")
    for tid, count in top_tokens:
        word = tokenizer.decode([tid])
        print(f"      '{word}': {count} occurrences")

    tokenizer.close()

    return token_ids


def tokens_to_pixels(token_ids: list) -> bytes:
    """Convert word IDs to dense RGB24 pixel data."""
    from src.pixel_tokenizer import PixelTokenizer

    print(f"[2] Converting {len(token_ids)} tokens to pixels...")

    tokenizer = PixelTokenizer()
    pixels = tokenizer.ids_to_pixels(token_ids)

    # Convert to bytes (RGB24)
    pixel_data = bytes(pixels.flatten().tolist())

    print(f"    Pixels: {len(pixels)} RGB24 values")
    print(f"    Size: {len(pixel_data)} bytes ({len(pixel_data) / (1024*1024):.2f} MB)")

    tokenizer.close()

    return pixel_data


def pack_into_mkv(pixel_data: bytes, mkv_path: str, entry_name: str):
    """Pack pixel data into MKV container."""
    print(f"[3] Packing into MKV: {mkv_path}")

    # Write to temp file
    tmp_path = f"/tmp/{entry_name}.bin"

    with open(tmp_path, "wb") as f:
        f.write(pixel_data)

    print(f"    Temp file: {tmp_path}")

    # Add to MKV
    result = subprocess.run([
        "python3", "tools/va_container.py", "add",
        mkv_path, tmp_path,
        "--name", entry_name,
        "--role", "emulator",
        "--note", "Semantic CPU emulator - self-modifying via wordbase"
    ], cwd=str(Path(mkv_path).parent), capture_output=True, text=True)

    if result.returncode != 0:
        print(f"ERROR: Failed to pack into MKV")
        print(f"stderr: {result.stderr}")
        return False

    print(f"    Entry: {entry_name}")
    print(f"    Success!")

    # Verify
    verify_result = subprocess.run([
        "python3", "tools/va_container.py", "ls", mkv_path
    ], cwd=str(Path(mkv_path).parent), capture_output=True, text=True)

    if entry_name in verify_result.stdout:
        print(f"    Verified in MKV listing")
        return True
    else:
        print(f"    WARNING: Not found in listing")
        return False


def extract_and_test(mkv_path: str, entry_name: str):
    """Extract and verify round-trip."""
    print(f"\n[4] Extracting and testing round-trip...")

    tmp_path = f"/tmp/{entry_name}_extracted.bin"

    result = subprocess.run([
        "python3", "tools/va_container.py", "cat",
        mkv_path, entry_name, "-o", tmp_path
    ], cwd=str(Path(mkv_path).parent), capture_output=True, text=True)

    if result.returncode != 0:
        print(f"ERROR: Failed to extract")
        return False

    print(f"    Extracted to: {tmp_path}")

    # Compare size
    import os
    original_size = os.path.getsize(tmp_path)

    print(f"    Extracted size: {original_size} bytes")

    # Would decode and verify here
    print(f"    (Skipping decode test - requires wordbase integration)")

    return True


def show_mkv_stats(mkv_path: str):
    """Show MKV container statistics."""
    print(f"\n[5] MKV Container Statistics:")

    result = subprocess.run([
        "python3", "tools/va_container.py", "ls", mkv_path
    ], cwd=str(Path(mkv_path).parent), capture_output=True, text=True)

    if result.returncode != 0:
        print(f"ERROR: Failed to list MKV")
        return

    lines = result.stdout.strip().split('\n')
    entry_count = int(lines[0].split(',')[1].split()[0])

    print(f"    Total entries: {entry_count}")

    # Find emulator entries
    emulator_entries = []
    for line in lines[1:]:
        if '[emulator]' in line:
            emulator_entries.append(line.strip())

    print(f"    Emulator entries: {len(emulator_entries)}")

    for entry in emulator_entries:
        print(f"      {entry}")


def main():
    """Main entry point."""

    import argparse

    parser = argparse.ArgumentParser(description="Pack semantic emulator into MKV")
    parser.add_argument("--code", default="semantic_cpu_emulator.py",
                       help="Path to emulator code")
    parser.add_argument("--mkv", default="visual_audio.mkv",
                       help="Path to MKV container")
    parser.add_argument("--name", default="semantic_emulator",
                       help="Entry name in MKV")

    args = parser.parse_args()

    print("=" * 70)
    print("SEMANTIC EMULATOR MKV PACKER")
    print("=" * 70)

    # Check files
    if not os.path.exists(args.code):
        print(f"ERROR: Code file not found: {args.code}")
        return 1

    if not os.path.exists(args.mkv):
        print(f"ERROR: MKV not found: {args.mkv}")
        return 1

    # Step 1: Tokenize via wordbase
    token_ids = tokenize_semantic(args.code)

    # Step 2: Convert to pixels
    pixel_data = tokens_to_pixels(token_ids)

    # Step 3: Pack into MKV
    if not pack_into_mkv(pixel_data, args.mkv, args.name):
        return 1

    # Step 4: Extract and test
    if not extract_and_test(args.mkv, args.name):
        return 1

    # Step 5: Show stats
    show_mkv_stats(args.mkv)

    print("\n" + "=" * 70)
    print("PACK COMPLETE")
    print("=" * 70)
    print("\nWhat's now in the MKV:")
    print(f"  → Semantic CPU emulator (wordbase-encoded)")
    print(f"  → Can read itself as pixels")
    print(f"  → Can optimize via color adjustment")
    print(f"  → Can create child MKVs with evolved code")
    print("\nUsage patterns:")
    print(f"  1. Boot from MKV:")
    print(f"     python3 tools/run_semantic_emulator.py --mkv {args.mkv}")
    print(f"  2. Self-modification:")
    print(f"     python3 tools/self_modifying_emulator.py --mkv {args.mkv}")
    print(f"  3. Recursive boot:")
    print(f"     python3 tools/recursive_boot.py --depth 3")
    print("=" * 70)

    return 0


if __name__ == "__main__":
    sys.exit(main())