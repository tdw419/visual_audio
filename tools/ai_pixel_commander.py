#!/usr/bin/env python3
"""
ai_pixel_commander.py — Bridge AI output to Geometry OS framebuffer via audio.

Takes AI output as JSON { "speech": "...", "ops": [...] } and:
  1. Utters the speech+ops into signed dual-band audio
  2. Listens to the audio, decodes ops, applies to framebuffer.png

This is the AI's "hands" — speaking commands that physically change pixels.

Usage:
  echo '{"speech": "Drawing a window", "ops": [["rect", 50, 50, 200, 150, "#333333"]]}' | python tools/ai_pixel_commander.py

  # With provenance (gated execution)
  python tools/ai_pixel_commander.py --private-key keys/pixel_os_private.pem --public-key keys/pixel_os_public.pem

Input format (stdin JSON):
  {
    "speech": "What to say aloud (human band)",
    "ops": [["rect", x, y, w, h, "#color"], ...]  // What to do (machine band)
  }
"""

import argparse
import json
import sys
import os
import subprocess
import tempfile
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(
        description="Bridge AI output to Geometry OS framebuffer via audio",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    parser.add_argument(
        '--fb', '-f',
        default='framebuffer.png',
        help='Framebuffer image path (default: framebuffer.png)'
    )

    parser.add_argument(
        '--private-key',
        help='Ed25519 private key for signing (gated execution)'
    )

    parser.add_argument(
        '--public-key',
        help='Ed25519 public key for verification (required if using signed audio)'
    )

    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Generate audio but do not apply to framebuffer'
    )

    args = parser.parse_args()

    # Read JSON from stdin
    try:
        input_data = json.loads(sys.stdin.read())
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON input: {e}", file=sys.stderr)
        return 1

    # Validate input structure
    if not isinstance(input_data, dict):
        print("Error: Input must be a JSON object", file=sys.stderr)
        return 1

    if 'ops' not in input_data:
        print("Error: Input must contain 'ops' array", file=sys.stderr)
        return 1

    speech = input_data.get('speech', '')
    ops = input_data['ops']

    if not isinstance(ops, list):
        print("Error: 'ops' must be an array", file=sys.stderr)
        return 1

    # Path to pixel_screen.py
    pixel_screen = Path(__file__).parent / 'pixel_screen.py'

    # Generate audio via utter subcommand
    with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as wav_file:
        wav_path = wav_file.name

    cmd_utter = [
        sys.executable, str(pixel_screen), 'utter',
        speech,
        '--ops', json.dumps(ops),
        '-o', wav_path
    ]

    if args.private_key:
        cmd_utter.extend(['--private-key', args.private_key])

    print(f"Uttering: {speech[:80]}{'...' if len(speech) > 80 else ''}")
    try:
        result = subprocess.run(cmd_utter, check=True, capture_output=True, text=True)
        print(result.stdout.strip())
    except subprocess.CalledProcessError as e:
        print(f"Error uttering audio: {e.stderr}", file=sys.stderr)
        return 1

    # Apply to framebuffer via listen subcommand
    if args.dry_run:
        print(f"[DRY RUN] Would apply {len(ops)} ops to {args.fb}")
        print(f"  Audio saved to: {wav_path}")
    else:
        print(f"Applying {len(ops)} ops to {args.fb}...")

        cmd_listen = [
            sys.executable, str(pixel_screen), 'listen',
            wav_path,
            '--fb', args.fb
        ]

        if args.public_key:
            cmd_listen.extend(['--public-key', args.public_key])

        try:
            result = subprocess.run(cmd_listen, check=True, capture_output=True, text=True)
            print(result.stdout.strip())
        except subprocess.CalledProcessError as e:
            print(f"Error listening to audio: {e.stderr}", file=sys.stderr)
            return 1

        # Show result
        cmd_show = [sys.executable, str(pixel_screen), 'show', '--fb', args.fb]
        try:
            result = subprocess.run(cmd_show, check=True, capture_output=True, text=True)
            print(f"  {result.stdout.strip()}")
        except subprocess.CalledProcessError as e:
            print(f"Error showing framebuffer: {e.stderr}", file=sys.stderr)

    return 0


if __name__ == '__main__':
    sys.exit(main())