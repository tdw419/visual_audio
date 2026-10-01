#!/usr/bin/env python3
"""
Process a single signed audio utterance and launch boot if authorized.
Simplified wrapper for one-shot boot operations.
"""
import sys
import json
import os
sys.path.insert(0, 'tools')

from spoken_screen import decode_data_band
import soundfile as sf
from boot_manifest import launch_boot, BootManifestError

def main():
    if len(sys.argv) < 4:
        print(f"Usage: {sys.argv[0]} <wav_file> <public_key> <boot_image_dir>", file=sys.stderr)
        sys.exit(1)

    wav_path = sys.argv[1]
    pub_key_path = sys.argv[2]
    image_dir = sys.argv[3]

    # Decode the audio
    audio, sr = sf.read(wav_path)
    if audio.ndim > 1:
        audio = audio.mean(axis=1)

    # Decode the data band with signature verification
    payload_bytes = decode_data_band(audio, sr, pub_key_path)
    ops = json.loads(payload_bytes.decode('utf-8'))

    print(f"Decoded {len(ops)} ops:")
    for op in ops:
        print(f"  {op}")

    # Process each op
    for op in ops:
        if isinstance(op, list) and len(op) > 0:
            if op[0] == "boot":
                print(f"\n[BOOT] Launching boot op: {op}")
                try:
                    argv = launch_boot(op, image_dir=image_dir, dry_run=False)
                    print(f"✓ QEMU launched: {' '.join(argv)}")
                except BootManifestError as e:
                    print(f"✗ Boot failed: {e}", file=sys.stderr)
                    sys.exit(1)
            else:
                print(f"[SKIP] Unknown op type: {op[0]}")
        else:
            print(f"[SKIP] Non-list op: {op}")

if __name__ == '__main__':
    main()