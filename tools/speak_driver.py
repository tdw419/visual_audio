#!/usr/bin/env python3
"""
speak_driver.py — Speak a driver into existence via signed dual-band audio.

This is the encoder side of "speak a driver into existence":

    LLM/generate_driver.py  ->  speak_driver.py  ->  dual-band WAV
        ->  [ acoustic channel ]  ->  pixel_os_listener (provenance gate)
        ->  write Python script to disk  ->  RUN it

Usage:
    python tools/speak_driver.py driver.py --output driver_speech.wav \\
        --narration "Installing network driver" --private-key keys/pixel_os_private.pem

The dual-band WAV contains:
  • Low band (<3.5 kHz): Human-readable narration (what the operator hears)
  • High band (4.2-7.5 kHz): Signed write+run ops (what the machine obeys)

Security:
  • Ops are signed with Ed25519 before encoding
  • Listener only honors write/run ops when:
    - Provenance is required (--provenance flag on listener)
    - Signature verifies against public key
    - Driver ops are explicitly enabled (--enable-driver-ops)
    - Output path is confined to driver_output_dir
"""

import argparse
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from spoken_screen import utter, SAMPLE_RATE


def encode_driver(source_path: str, script_name: str = None,
                   narration: str = None) -> list:
    """
    Encode driver source into write+run ops.

    Args:
        source_path: Path to Python driver source file
        script_name: Name to use when writing the driver (default: basename)
        narration: Human narration to speak (default: "Installing {script_name}")

    Returns:
        List of ops: [["write", script_name, source_content], ["run", script_name]]
    """
    if script_name is None:
        script_name = os.path.basename(source_path)

    # Read driver source
    with open(source_path, 'r', encoding='utf-8') as f:
        source_content = f.read()

    # Build ops
    ops = [
        ["write", script_name, source_content],
        ["run", script_name]
    ]

    return ops


def main():
    parser = argparse.ArgumentParser(
        description="Speak a driver into existence via signed dual-band audio",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    parser.add_argument(
        'driver_source',
        help="Path to Python driver source file to encode"
    )

    parser.add_argument(
        '--output', '-o',
        default='driver_speech.wav',
        help="Output WAV file path (default: driver_speech.wav)"
    )

    parser.add_argument(
        '--script-name',
        help="Name to use when writing the driver (default: basename of source)"
    )

    parser.add_argument(
        '--narration',
        default=None,
        help="Human narration to speak in the low band "
             "(default: 'Installing {script_name}')"
    )

    parser.add_argument(
        '--private-key',
        default='keys/pixel_os_private.pem',
        help="Path to Ed25519 private key for signing (default: keys/pixel_os_private.pem)"
    )

    parser.add_argument(
        '--dry-run',
        action='store_true',
        help="Encode and print ops without writing WAV file"
    )

    args = parser.parse_args()

    # Validate input
    if not os.path.exists(args.driver_source):
        print(f"Error: driver source file not found: {args.driver_source}", file=sys.stderr)
        return 1

    if not os.path.exists(args.private_key):
        print(f"Error: private key not found: {args.private_key}", file=sys.stderr)
        print("Run 'python gen_provenance_keys.py' to generate key pair.", file=sys.stderr)
        return 1

    # Generate ops
    ops = encode_driver(args.driver_source, args.script_name)

    # Generate default narration if not provided
    if args.narration is None:
        script_name = args.script_name or os.path.basename(args.driver_source)
        args.narration = f"Installing {script_name}"

    # Print what we're encoding
    print(f"Encoding driver: {args.driver_source}")
    print(f"  Script name: {ops[0][1]}")
    print(f"  Source size: {len(ops[0][2])} bytes")
    print(f"  Narration: {args.narration!r}")
    print(f"  Ops: {ops}")

    if args.dry_run:
        print("\n[DRY RUN] Would encode to:", args.output)
        return 0

    # Create dual-band WAV with provenance
    print(f"\nEncoding signed dual-band audio to {args.output}...")
    try:
        audio = utter(args.narration, ops, args.output,
                     private_key_path=args.private_key)
        duration = len(audio) / SAMPLE_RATE
        print(f"  ✓ Success: {duration:.1f}s of audio")
        print(f"  ✓ Signed with Ed25519 (64-byte signature + timestamp)")
        print(f"\nTo execute this driver via the listener:")
        print(f"  python tools/pixel_os_listener.py \\\\")
        print(f"    --fb /tmp/framebuffer.png \\\\")
        print(f"    --provenance \\\\")
        print(f"    --enable-driver-ops \\\\")
        print(f"    --driver-output-dir /tmp/drivers \\\\")
        print(f"    --public-key keys/pixel_os_public.pem \\\\")
        print(f"    --queue-mode --watch-dir ./")
        print(f"\nThen play the WAV:")
        print(f"  aplay {args.output}")
        return 0

    except Exception as e:
        print(f"\nError encoding audio: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main())