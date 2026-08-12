#!/usr/bin/env python3
"""
speak_glyph.py — Speak a .glyph spatial program into existence via signed dual-band audio.

This is the encoder side for .glyph programs:
    .glyph source  ->  speak_glyph.py  ->  dual-band WAV
        ->  [ acoustic channel ]  ->  pixel_os_listener (provenance gate)
        ->  write .glyph file to disk  ->  execute via wgsl_glyph_full_execute.py

Usage:
    python tools/speak_glyph.py program.glyph --output glyph_speech.wav \\
        --narration "Installing spatial program" --private-key keys/pixel_os_private.pem

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
import struct
import binascii
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# pixel_screen.utter() already implements the verified dual-band mix
# (narration low-band + synth_data_band high-band) that pixel_os_listener.py's
# decode_data_band() expects. Reuse it instead of driving the raw Phy16Tone
# modem directly -- the two encodings are not interchangeable.
from pixel_screen import utter as pixel_screen_utter


def encode_glyph(source_path: str, script_name: str = None) -> list:
    """
    Encode .glyph source into write+run ops.

    Args:
        source_path: Path to .glyph source file
        script_name: Name to use when writing the .glyph (default: basename)

    Returns:
        List of ops: [["write", script_name, source_content], ["run", script_name]]
    """
    if script_name is None:
        script_name = os.path.basename(source_path)

    # Read .glyph source
    with open(source_path, 'r', encoding='utf-8') as f:
        source_content = f.read()

    # Build ops
    ops = [
        ["write", script_name, source_content],
        ["run", script_name]
    ]

    return ops


def encode_ops_to_audio(ops: list, private_key_path: str, narration: str, wav_path: str):
    """
    Encode ops to a signed dual-band WAV via pixel_screen.utter(), the same
    path pixel_os_listener.py's decode_data_band() actually understands.

    Args:
        ops: List of ops to encode
        private_key_path: Path to Ed25519 private key (PEM/PKCS8)
        narration: Spoken narration text for the low band
        wav_path: Output WAV path
    """
    return pixel_screen_utter(narration, ops, wav_path, private_key_path)


def main():
    parser = argparse.ArgumentParser(
        description="Speak a .glyph spatial program into existence via signed dual-band audio",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    parser.add_argument(
        'glyph_source',
        help="Path to .glyph source file to encode"
    )

    parser.add_argument(
        '--output', '-o',
        default='glyph_speech.wav',
        help="Output WAV file path (default: glyph_speech.wav)"
    )

    parser.add_argument(
        '--script-name',
        help="Name to use when writing the .glyph (default: basename of source)"
    )

    parser.add_argument(
        '--private-key',
        default='keys/pixel_os_private.pem',
        help="Path to Ed25519 private key for signing (default: keys/pixel_os_private.pem)"
    )

    parser.add_argument(
        '--narration',
        default=None,
        help="Spoken narration text for the low band (default: derived from script name)"
    )

    parser.add_argument(
        '--dry-run',
        action='store_true',
        help="Encode and print ops without writing WAV file"
    )

    args = parser.parse_args()

    # Validate input
    if not os.path.exists(args.glyph_source):
        print(f"Error: .glyph source file not found: {args.glyph_source}", file=sys.stderr)
        return 1

    if not os.path.exists(args.private_key):
        print(f"Error: private key not found: {args.private_key}", file=sys.stderr)
        print("Run 'python gen_provenance_keys.py' to generate key pair.", file=sys.stderr)
        return 1

    # Generate ops
    ops = encode_glyph(args.glyph_source, args.script_name)

    # Print what we're encoding
    print(f"Encoding .glyph program: {args.glyph_source}")
    print(f"  Script name: {ops[0][1]}")
    print(f"  Source size: {len(ops[0][2])} bytes")
    print(f"  Ops: {ops}")

    if args.dry_run:
        print("\n[DRY RUN] Would encode to:", args.output)
        return 0

    # Create audio with provenance
    print(f"\nEncoding signed audio to {args.output}...")
    try:
        narration = args.narration or f"Installing spatial program {ops[0][1]}"
        from speak import SAMPLE_RATE
        audio = encode_ops_to_audio(ops, args.private_key, narration, args.output)
        duration = len(audio) / SAMPLE_RATE
        print(f"  ✓ Success: {duration:.1f}s of audio")
        print(f"  ✓ Signed with Ed25519 (64-byte signature + timestamp)")
        print(f"\nTo execute this .glyph program via the listener:")
        print(f"  python tools/pixel_os_listener.py \\")
        print(f"    --fb /tmp/framebuffer.png \\")
        print(f"    --provenance \\")
        print(f"    --enable-driver-ops \\")
        print(f"    --driver-output-dir /tmp/drivers \\")
        print(f"    --public-key keys/pixel_os_public.pem \\")
        print(f"    --mode queue --watch-dir ./")
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