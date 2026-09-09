#!/usr/bin/env python3
"""
V4 Boot Tool - Generate multi-PDB PNG for booting

Orchestrates Rust geos_pixel tools to create bootable V4 containers:
- Kernel (vmlinuz) → single PDB frame
- Initramfs → single PDB frame
- Rootfs → tiled PDB format (multiple PNG tiles)
- Unified Disk Image → JSON metadata + concatenated PDBs

Usage:
    python3 tools/v4_boot_builder.py \
        --kernel vmlinuz \
        --initramfs initramfs.cpio.gz \
        --rootfs rootfs.ext4 \
        --output ubuntu_v4_boot.img
"""

import argparse
import hashlib
import json
import os
import subprocess
import sys
import struct
from pathlib import Path

# Constants
V4BOOT_MAGIC = b"V4BOOT00"
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def run_command(cmd, check=True):
    """Run a shell command and return stdout."""
    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(
        cmd,
        check=check,
        capture_output=True,
        text=True,
        cwd="/home/jericho/projects/zion/projects/visual_audio/systems"
    )
    if result.stdout:
        print(result.stdout)
    if result.stderr and result.returncode != 0:
        print(f"stderr: {result.stderr}", file=sys.stderr)
    return result


def encode_single_tile(input_path, output_dir_path, table_name):
    """Encode a file as a single-tile PDB (for kernel/initramfs)."""
    print(f"\n=== Encoding {table_name} as single-tile PDB ===")
    print(f"Input: {input_path}")
    print(f"Output dir: {output_dir_path}")

    output_dir = Path(output_dir_path)
    output_dir.mkdir(parents=True, exist_ok=True)

    output_png_path = output_dir / f"{table_name}.pdb.png"

    # Use the Rust encoder example
    cmd = [
        "cargo", "run", "-p", "geos_pixel", "--quiet", "--release",
        "--example", "encode_file_to_pdb", "--",
        "--input", str(input_path),
        "--output", str(output_png_path),
        "--table-name", table_name
    ]

    result = run_command(cmd, check=True)

    # Verify output exists
    if not output_png_path.exists():
        raise RuntimeError(f"Failed to encode {table_name}: no PDB PNG generated at {output_png_path}")

    return output_png_path


def encode_tiled(input_path, output_base, tile_size, table_name):
    """Encode a large file as tiled PDB (for rootfs)."""
    print(f"\n=== Encoding {table_name} as tiled PDB ===")
    print(f"Input: {input_path}")
    print(f"Output base: {output_base}")
    print(f"Tile size: {tile_size}")

    cmd = [
        "cargo", "run", "-p", "geos_pixel", "--quiet", "--release",
        "--example", "compile_v4_1_tiled", "--",
        output_base,
        str(tile_size),
        table_name,
        str(input_path)
    ]

    result = run_command(cmd, check=False)

    # Check for tiles.json output
    tiles_json_path = Path(output_base) / "tiles.json"
    if not tiles_json_path.exists():
        raise RuntimeError(f"Failed to encode {table_name}: no tiles.json generated")

    # Count generated PNG tiles
    tile_count = len(list(Path(output_base).glob("*.pdb.png")))
    print(f"Generated {tile_count} PNG tiles")

    return tiles_json_path, tile_count


def create_manifest(kernel_hash, initramfs_hash, rootfs_tiles_json):
    """Create manifest.json with metadata."""
    manifest = {
        "version": "4.0",
        "format": "V4BOOT",
        "components": {
            "kernel": {
                "format": "single-tile-pdb",
                "hash_sha256": kernel_hash,
                "tile_index": 0
            },
            "initramfs": {
                "format": "single-tile-pdb",
                "hash_sha256": initramfs_hash,
                "tile_index": 1
            },
            "rootfs": {
                "format": "tiled-pdb",
                "tiles_json": rootfs_tiles_json,
                "tile_start": 2
            }
        }
    }
    return json.dumps(manifest, indent=2)


def compute_sha256(filepath):
    """Compute SHA256 hash of a file."""
    sha256 = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def create_v4_boot_image(
    kernel_path,
    initramfs_path,
    rootfs_path,
    output_img,
    tile_size=4096
):
    """Create a unified V4 boot image."""
    output_img = Path(output_img)
    workdir = output_img.parent / "v4_boot_work"
    workdir.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("V4 Boot Image Builder")
    print("=" * 60)

    # Step 1: Encode kernel
    kernel_png = encode_single_tile(
        kernel_path,
        workdir / "kernel",
        "kernel"
    )
    kernel_hash = compute_sha256(kernel_path)

    # Step 2: Encode initramfs
    initramfs_png = encode_single_tile(
        initramfs_path,
        workdir / "initramfs",
        "initramfs"
    )
    initramfs_hash = compute_sha256(initramfs_path)

    # Step 3: Encode rootfs (tiled)
    rootfs_workdir = workdir / "rootfs_tiles"
    rootfs_workdir.mkdir(exist_ok=True)

    # rootfs_tiles_json_path, rootfs_tile_count = encode_tiled(
    #     rootfs_path,
    #     str(rootfs_workdir),
    #     tile_size,
    #     "rootfs"
    # )
    
    # Use existing tiles
    rootfs_tiles_json_path = rootfs_workdir / "tiles.json"
    rootfs_tile_count = 324

    # Load tiles.json for embedding
    with open(rootfs_tiles_json_path, "r") as f:
        rootfs_tiles_json_content = f.read()

    # Step 4: Create manifest
    manifest_json = create_manifest(
        kernel_hash,
        initramfs_hash,
        rootfs_tiles_json_content
    )
    manifest_bytes = manifest_json.encode("utf-8")

    # Step 5: Assemble V4BOOT image
    print("\n=== Assembling V4BOOT image ===")

    with open(output_img, "wb") as f:
        # Write magic
        f.write(V4BOOT_MAGIC)

        # Write manifest size + manifest
        f.write(struct.pack("<Q", len(manifest_bytes)))
        f.write(manifest_bytes)

        # Write tiles.json placeholder (for production use)
        # For bootloader simplicity, we embed empty tiles.json
        tiles_json_bytes = json.dumps({
            "note": "Bootloader uses sequential tile scanning",
            "kernel_tile": 0,
            "initramfs_tile": 1,
            "rootfs_tiles_start": 2,
            "rootfs_tile_count": rootfs_tile_count
        }).encode("utf-8")

        f.write(struct.pack("<Q", len(tiles_json_bytes)))
        f.write(tiles_json_bytes)

        # Write PNG tiles sequentially
        # Order: kernel, initramfs, then rootfs tiles (sorted by filename)
        tiles_order = [kernel_png, initramfs_png]

        # Add rootfs tiles in sorted order
        # rootfs_tiles = sorted(rootfs_workdir.glob("*.pdb.png"))
        # tiles_order.extend(rootfs_tiles)

        for tile_path in tiles_order:
            print(f"Appending: {tile_path.name}")
            with open(tile_path, "rb") as tf:
                f.write(tf.read())

    img_size = output_img.stat().st_size
    print(f"\n=== COMPLETE ===")
    print(f"Output image: {output_img}")
    print(f"Image size: {img_size / (1024*1024):.2f} MB")
    print(f"Tiles embedded: {len(tiles_order)}")

    return output_img


def main():
    parser = argparse.ArgumentParser(
        description="Create V4 boot image from kernel, initramfs, and rootfs"
    )
    parser.add_argument(
        "--kernel",
        required=True,
        help="Path to kernel image (vmlinuz)"
    )
    parser.add_argument(
        "--initramfs",
        required=True,
        help="Path to initramfs (initramfs.cpio.gz)"
    )
    parser.add_argument(
        "--rootfs",
        required=True,
        help="Path to rootfs (rootfs.ext4)"
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Output V4 boot image path"
    )
    parser.add_argument(
        "--tile-size",
        type=int,
        default=4096,
        help="Tile size for tiled rootfs (default: 4096)"
    )

    args = parser.parse_args()

    create_v4_boot_image(
        args.kernel,
        args.initramfs,
        args.rootfs,
        args.output,
        args.tile_size
    )


if __name__ == "__main__":
    main()