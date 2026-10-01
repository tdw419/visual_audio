#!/usr/bin/env python3
"""
Simple CLI for signing spoken_screen utterances.
"""

import argparse
import json
import sys
import os
from pathlib import Path

sys.path.insert(0, 'tools')

from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.primitives import serialization


def generate_keys(output_dir: str = None) -> tuple[str, str]:
    """Generate Ed25519 key pair."""
    if output_dir is None:
        output_dir = str(Path.cwd() / 'keys')

    os.makedirs(output_dir, exist_ok=True)

    private_key = ed25519.Ed25519PrivateKey.generate()
    public_key = private_key.public_key()

    # Use fixed names for compatibility
    private_path = os.path.join(output_dir, 'pixel_os_private.pem')
    public_path = os.path.join(output_dir, 'pixel_os_public.pem')

    # Save private key
    with open(private_path, 'wb') as f:
        f.write(private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        ))

    # Save public key
    with open(public_path, 'wb') as f:
        f.write(public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        ))

    print(f"Generated Ed25519 key pair:")
    print(f"  Private: {private_path}")
    print(f"  Public:  {public_path}")

    return private_path, public_path


def main():
    parser = argparse.ArgumentParser(
        description="Generate Ed25519 keys for spoken_screen provenance"
    )
    parser.add_argument(
        '--key-dir',
        default=None,
        help='Directory to save keys (default: ./keys)'
    )

    args = parser.parse_args()

    try:
        priv_path, pub_path = generate_keys(args.key_dir)
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())