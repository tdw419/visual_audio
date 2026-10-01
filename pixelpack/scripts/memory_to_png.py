#!/usr/bin/env python3
"""
memory_to_png.py — Memory Palace to PNG conversion bridge.

This script converts memory/knowledge data (JSON) into dense PNG tiles using
the dense encoder for Visual Audio Memory Palace (VAMP) integration.

Usage:
    python3 pixelpack/scripts/memory_to_png.py <knowledge.json> -o output.png

Features:
    - Uses tools/dense_encoder.py for encoding (3 bytes/pixel density)
    - Supports JSON memory/knowledge structures
    - Verifies CRC on all generated tiles
    - Backward-compatible with existing Memory Palace building workflows
"""

import argparse
import json
import os
import sys

# Add parent directory to path for importing dense_encoder
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'tools'))

from dense_encoder import encode_dense, decode_dense


def load_knowledge(path: str) -> dict:
    """
    Load knowledge/memory data from JSON file.

    Args:
        path: Path to JSON file

    Returns:
        Parsed JSON dictionary
    """
    with open(path, 'r') as f:
        return json.load(f)


def memory_to_png(knowledge: dict, output_path: str, verify: bool = True) -> str:
    """
    Convert memory/knowledge data to dense PNG using dense_encoder.

    Args:
        knowledge: Dictionary containing memory/knowledge data
        output_path: Output PNG path
        verify: If True, verify round-trip after encoding

    Returns:
        Path to generated PNG file
    """
    # Serialize knowledge to compact JSON
    payload = json.dumps(knowledge, separators=(',', ':')).encode('utf-8')

    # Encode using dense_encoder.py (3 bytes/pixel, CRC-verified)
    encode_dense(payload, output_path, square=True)

    # Verify round-trip if requested
    if verify:
        recovered = decode_dense(output_path)
        recovered_knowledge = json.loads(recovered)

        if recovered_knowledge != knowledge:
            raise ValueError("Round-trip verification failed: recovered data differs from original")

        print(f"✓ Verified: round-trip successful for {len(payload)} bytes")

    return output_path


def main():
    parser = argparse.ArgumentParser(
        description="Convert Memory Palace knowledge to dense PNG tiles",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Encode knowledge JSON to PNG
    python3 pixelpack/scripts/memory_to_png.py knowledge.json -o memory.png

    # Encode without verification (faster)
    python3 pixelpack/scripts/memory_to_png.py knowledge.json -o memory.png --no-verify

    # Decode PNG back to knowledge
    python3 pixelpack/scripts/memory_to_png.py memory.png -d -o recovered.json
        """
    )

    parser.add_argument('input', help='Input JSON file or PNG file (if --decode)')
    parser.add_argument('-o', '--output', required=True, help='Output PNG or JSON file')
    parser.add_argument('-d', '--decode', action='store_true', help='Decode PNG to JSON')
    parser.add_argument('--no-verify', action='store_true', help='Skip round-trip verification')

    args = parser.parse_args()

    if args.decode:
        # Decode PNG back to JSON
        recovered_bytes = decode_dense(args.input)
        recovered_knowledge = json.loads(recovered_bytes)

        with open(args.output, 'w') as f:
            json.dump(recovered_knowledge, f, indent=2)

        print(f"Decoded PNG → JSON: {args.output}")
        print(f"  Facts/memories recovered: {len(recovered_knowledge) if isinstance(recovered_knowledge, list) else 'dict'}")

    else:
        # Encode JSON to PNG
        knowledge = load_knowledge(args.input)
        memory_to_png(knowledge, args.output, verify=not args.no_verify)
        print(f"Encoded JSON → PNG: {args.output}")


if __name__ == '__main__':
    main()