#!/usr/bin/env python3
"""
Multi-tile dense encoding for large payloads.

Splits large files across multiple dense cartridges with a manifest for
reassembly. Enables encoding of files > 65KB (uint16 limit of 'UA' frame).
"""

import argparse
import hashlib
import json
import os
import sys
import zlib
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))

from dense_encoder import frame, unframe, bytes_to_pixels, pixels_to_bytes

# Manifest format constants
MANIFEST_VERSION = "MT2"  # Multi-tile v2 (extended indexing)
MAX_PAYLOAD = 65531  # Max payload per tile (uint16 limit - overhead)
MAX_TILES_V1 = 999  # Original 3-digit format (.XXX.png)
MAX_TILES_V2 = 99999  # Extended 5-digit format (.XXXXX.png)


def md5_hash(data: bytes) -> str:
    """Calculate MD5 hash as hex string."""
    return hashlib.md5(data).hexdigest()


def _get_tile_filename(base: str, index: int, version: str = MANIFEST_VERSION) -> str:
    """Generate tile filename based on version.
    
    Args:
        base: Base filename without extension
        index: Tile index (0-based)
        version: Manifest version (MT1 or MT2)
    
    Returns:
        Tile filename (e.g., 'output.000.png' or 'output.00000.png')
    """
    if version == "MT2":
        return f"{base}.{index:05d}.png"  # 5-digit format for up to 99,999 tiles
    else:  # MT1
        return f"{base}.{index:03d}.png"  # 3-digit format for up to 999 tiles


def _detect_version_from_manifest(manifest: dict) -> str:
    """Detect manifest version from manifest dict.
    
    Args:
        manifest: Parsed manifest dictionary
    
    Returns:
        Version string ('MT1' or 'MT2')
    """
    version = manifest.get("version", "MT1")
    return version


def _get_tile_path_from_manifest(path: Path, index: int, version: str) -> str:
    """Generate tile path based on manifest version.
    
    Args:
        path: Path to manifest file
        index: Tile index
        version: Manifest version
    
    Returns:
        Full path to tile file
    """
    base = str(path.with_suffix('').with_suffix(''))  # Remove .manifest.png
    return _get_tile_filename(base, index, version)


def encode_multi(payload: bytes, base_path: str, max_payload: int = MAX_PAYLOAD):
    """
    Encode large payload across multiple dense PNG tiles.

    Args:
        payload: Raw payload bytes
        base_path: Base output path (without extension or tile index)
        max_payload: Maximum bytes per tile

    Returns:
        List of created file paths
    """
    if len(payload) <= max_payload:
        # Small payload: use single-tile encoding (no manifest)
        single_path = f"{base_path}.png"
        print(f"Small payload ({len(payload)} bytes), using single-tile encoding", file=sys.stderr)
        print(f"  Output: {single_path}", file=sys.stderr)
        
        from dense_encoder import encode_dense
        encode_dense(payload, single_path)
        return [single_path]
    
    # Split into chunks
    chunks = [payload[i:i + max_payload] for i in range(0, len(payload), max_payload)]
    total_tiles = len(chunks)
    overall_hash = md5_hash(payload)
    
    print(f"Encoding {len(payload)} bytes across {total_tiles} tiles", file=sys.stderr)
    print(f"  Chunk size: {max_payload} bytes", file=sys.stderr)
    print(f"  Overall hash: {overall_hash}", file=sys.stderr)
    print(f"  Manifest version: {MANIFEST_VERSION}", file=sys.stderr)
    
    # Determine version based on tile count
    version = MANIFEST_VERSION
    if total_tiles > MAX_TILES_V1:
        # Auto-upgrade to MT2 for large payloads
        version = "MT2"
        print(f"  Auto-upgraded to MT2 for {total_tiles} tiles (> {MAX_TILES_V1})", file=sys.stderr)
    
    # Encode each chunk
    tiles = []
    for idx, chunk in enumerate(chunks):
        tile_path = _get_tile_filename(base_path, idx, version)
        tiles.append({"index": idx, "path": tile_path, "hash": md5_hash(chunk)})
        
        # Encode chunk
        from dense_encoder import encode_dense
        encode_dense(chunk, tile_path)
        
        if idx < 5 or idx >= total_tiles - 5:
            print(f"  Tile {idx}/{total_tiles-1}: {tile_path} ({len(chunk)} bytes)", file=sys.stderr)
        elif idx == 5:
            print(f"  ... ({total_tiles - 10} more tiles)", file=sys.stderr)
    
    # Create manifest tile
    manifest = {
        "version": version,
        "total_tiles": total_tiles,
        "total_bytes": len(payload),
        "overall_hash": overall_hash,
        "tiles": [{"index": t["index"], "hash": t["hash"]} for t in tiles]
    }
    
    # Compress manifest if needed
    manifest_json = json.dumps(manifest, indent=2).encode('utf-8')
    if len(manifest_json) > MAX_PAYLOAD:
        # Use compression for large manifests
        manifest_compressed = zlib.compress(manifest_json, level=zlib.Z_BEST_COMPRESSION)
        print(f"Manifest compressed: {len(manifest_json)} → {len(manifest_compressed)} bytes", file=sys.stderr)
        if len(manifest_compressed) > MAX_PAYLOAD:
            raise ValueError(f"Manifest too large even after compression: {len(manifest_compressed)} bytes")
        manifest_bytes = b"CZ" + manifest_compressed  # Add compression marker
    else:
        manifest_bytes = manifest_json
    
    manifest_path = f"{base_path}.manifest.png"
    
    from dense_encoder import encode_dense
    encode_dense(manifest_bytes, manifest_path)
    
    print(f"Manifest: {manifest_path}", file=sys.stderr)
    print(f"  Total tiles: {total_tiles}", file=sys.stderr)
    print(f"  Total bytes: {len(payload)}", file=sys.stderr)
    print(f"  Overall hash: {overall_hash}", file=sys.stderr)
    
    return [t["path"] for t in tiles] + [manifest_path]


def decode_multi(png_path: str) -> bytes:
    """
    Decode multi-tile encoding (auto-detects single vs multi-tile).

    Args:
        png_path: Path to manifest tile (for multi-tile) or single tile

    Returns:
        Reassembled payload bytes
    """
    path = Path(png_path)
    
    # Check if this is a manifest tile
    if not png_path.endswith('.manifest.png'):
        # Single-tile encoding
        print(f"Single-tile encoding detected", file=sys.stderr)
        from dense_encoder import decode_dense
        return decode_dense(png_path)
    
    print(f"Multi-tile encoding detected", file=sys.stderr)
    
    # Decode manifest
    from dense_encoder import decode_dense
    manifest_bytes = decode_dense(png_path)
    
    # Handle compressed manifests
    if manifest_bytes.startswith(b"CZ"):
        print(f"Manifest is compressed, decompressing...", file=sys.stderr)
        manifest_bytes = zlib.decompress(manifest_bytes[2:])
    
    manifest = json.loads(manifest_bytes)
    
    version = _detect_version_from_manifest(manifest)
    print(f"Manifest version: {version}", file=sys.stderr)
    
    if version not in ["MT1", "MT2"]:
        raise ValueError(f"Unsupported manifest version: {version}")
    
    total_tiles = manifest["total_tiles"]
    total_bytes = manifest["total_bytes"]
    overall_hash = manifest["overall_hash"]
    tiles = manifest["tiles"]
    
    print(f"  Total tiles: {total_tiles}", file=sys.stderr)
    print(f"  Total bytes: {total_bytes}", file=sys.stderr)
    print(f"  Overall hash: {overall_hash}", file=sys.stderr)
    
    # Decode each tile and verify
    chunks = []
    for tile_info in tiles:
        idx = tile_info["index"]
        expected_hash = tile_info["hash"]
        
        # Use version-aware path generation
        tile_path = _get_tile_path_from_manifest(path, idx, version)
        
        if not os.path.exists(tile_path):
            raise FileNotFoundError(f"Tile {idx} not found: {tile_path}")
        
        chunk = decode_dense(tile_path)
        actual_hash = md5_hash(chunk)
        
        if actual_hash != expected_hash:
            raise ValueError(f"Tile {idx} hash mismatch: expected {expected_hash}, got {actual_hash}")
        
        chunks.append((idx, chunk))
        
        # Limit output for large tile sets
        if total_tiles <= 20 or idx < 3 or idx >= total_tiles - 3:
            print(f"  Tile {idx}/{total_tiles-1}: verified (hash {actual_hash})", file=sys.stderr)
        elif idx == 3:
            print(f"  ... ({total_tiles - 6} more tiles)", file=sys.stderr)
    
    # Sort by index and concatenate
    chunks.sort(key=lambda x: x[0])
    payload = b''.join(chunk for _, chunk in chunks)
    
    # Verify overall hash
    actual_overall_hash = md5_hash(payload)
    if actual_overall_hash != overall_hash:
        raise ValueError(f"Overall hash mismatch: expected {overall_hash}, got {actual_overall_hash}")
    
    print(f"Reassembly complete: {len(payload)} bytes (hash verified)", file=sys.stderr)
    
    return payload


def main():
    parser = argparse.ArgumentParser(description="Multi-tile dense encoding for large payloads")
    sub = parser.add_subparsers(dest='cmd', required=True)
    
    p_enc = sub.add_parser('encode', help='encode payload as multi-tile dense PNG')
    p_enc.add_argument('input', help='input file')
    p_enc.add_argument('-o', '--output', default='payload', help='base output path (without extension)')
    
    p_dec = sub.add_parser('decode', help='decode multi-tile dense PNG')
    p_dec.add_argument('png', help='manifest PNG or single tile')
    p_dec.add_argument('-o', '--output', help='output file')
    
    p_run = sub.add_parser('run', help='decode and execute multi-tile dense PNG')
    p_run.add_argument('png', help='manifest PNG or single tile')
    p_run.add_argument('--geos', action='store_true', help='execute via GeOS spatial syscall')
    p_run.add_argument('--region', default='default', help='GeOS region identifier (default: default)')
    
    args = parser.parse_args()
    
    if args.cmd == 'encode':
        with open(args.input, 'rb') as f:
            payload = f.read()
        encode_multi(payload, args.output)
    
    elif args.cmd == 'decode':
        payload = decode_multi(args.png)
        if args.output:
            with open(args.output, 'wb') as f:
                f.write(payload)
            print(f"Wrote {len(payload)} bytes to {args.output}")
        else:
            # Write to stdout when no output file specified
            sys.stdout.buffer.write(payload)
    
    elif args.cmd == 'run':
        # GeOS execution not supported for multi-tile (yet)
        if args.geos:
            print("GeOS execution not yet supported for multi-tile payloads")
            print("Reassemble first: dense_encoder_multitile.py decode <manifest.png> -o reassembled.bin")
            sys.exit(1)
        
        payload = decode_multi(args.png)
        
        print(f"pixel executor: {len(payload)} bytes decoded, executing (sandboxed)\n---")
        from executor.sandbox import execute_cartridge
        result = execute_cartridge(payload.decode('utf-8'))
        if result.stdout:
            print(result.stdout, end='')
        if not result.success:
            print(f"[sandbox] execution failed: {result.error_message or result.stderr}")


if __name__ == '__main__':
    main()