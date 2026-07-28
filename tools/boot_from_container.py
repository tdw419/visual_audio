#!/usr/bin/env python3
"""
boot_from_container.py — Extract a bootable image from visual_audio.mkv and launch it.

Usage:
  python3 tools/boot_from_container.py alpine.qcow2
  python3 tools/boot_from_container.py alpine.qcow2 --gui
  python3 tools/boot_from_container.py alpine.qcow2 --arch riscv64 --drive fs.img

This script:
1. Extracts the named image from visual_audio.mkv to boot_images/
2. Validates the image with CRC32 + sha256
3. Launches QEMU via boot_manifest.py with safety gates

Security: Extracted files are written to the trusted boot_images/ directory,
which is already validated by boot_manifest.py against path traversal.
"""

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from tools import va_container
from tools import boot_manifest


def extract_and_boot(
    container_path: Path,
    image_name: str,
    boot_images_dir: Path,
    arch: str = "x86_64",
    gui: bool = False,
    drive: str = None,
    bios: str = "default",
) -> None:
    """Extract image from container and boot it via boot_manifest."""
    
    # Verify container integrity
    print(f"Verifying {container_path.name}...")
    va_container.verify(str(container_path))
    
    # Extract image to boot_images/
    target_path = boot_images_dir / image_name
    print(f"Extracting {image_name} to {target_path}...")
    va_container.cat(str(container_path), image_name, output=str(target_path))
    
    # Verify extraction
    if not target_path.is_file():
        raise RuntimeError(f"Extracted file not found: {target_path}")
    print(f"Extracted {target_path.stat().st_size:,} bytes")
    
    # Build boot manifest
    opts = {"bios": bios}
    if gui:
        opts["gui"] = True
    if drive:
        opts["drive"] = drive
    
    boot_op = ["boot", arch, image_name, opts]
    manifest = boot_manifest.parse_boot_op(boot_op)
    
    # Resolve paths
    image_path = boot_manifest.resolve_image(manifest, str(boot_images_dir))
    drive_path = None
    if manifest.drive:
        drive_path = (boot_images_dir / manifest.drive).resolve()
    
    # Build QEMU argv
    qemu_argv = boot_manifest.build_qemu_argv(manifest, image_path, drive_path)
    
    # Launch
    print(f"\nBooting with QEMU: {qemu_argv[0]}")
    print(f"Arch: {arch}")
    if gui:
        print(f"GUI mode: VNC on 127.0.0.1:5901 (use vncviewer localhost:1)")
    print(f"Press Ctrl+A X to quit QEMU (nographic mode)")
    print("=" * 60)
    
    os.execvp(qemu_argv[0], qemu_argv)


def main():
    parser = argparse.ArgumentParser(
        description="Extract and boot an OS image from visual_audio.mkv"
    )
    parser.add_argument(
        "image",
        help="Name of the image in the container (e.g., alpine.qcow2)"
    )
    parser.add_argument(
        "--arch",
        choices=["x86_64", "riscv64"],
        default="x86_64",
        help="QEMU architecture (default: x86_64)"
    )
    parser.add_argument(
        "--gui",
        action="store_true",
        help="Boot as GUI disk image with VNC display (x86_64 only)"
    )
    parser.add_argument(
        "--drive",
        help="Optional drive image (bare filename in boot_images/)"
    )
    parser.add_argument(
        "--bios",
        choices=["default", "none"],
        default="default",
        help="BIOS setting (default: default)"
    )
    parser.add_argument(
        "--container",
        default="visual_audio.mkv",
        help="Container path (default: visual_audio.mkv)"
    )
    parser.add_argument(
        "--boot-dir",
        default="boot_images",
        help="Boot images directory (default: boot_images)"
    )
    
    args = parser.parse_args()
    
    # Validate paths
    container_path = Path(args.container).resolve()
    if not container_path.is_file():
        parser.error(f"Container not found: {container_path}")
    
    boot_images_dir = Path(args.boot_dir).resolve()
    if not boot_images_dir.is_dir():
        parser.error(f"Boot images directory not found: {boot_images_dir}")
    
    # Validate arch/gui combination
    if args.gui and args.arch != "x86_64":
        parser.error("--gui only supported for x86_64 architecture")
    
    # Validate drive/arch combination
    if args.drive and args.arch != "riscv64":
        parser.error("--drive only supported for riscv64 architecture")
    
    try:
        extract_and_boot(
            container_path=container_path,
            image_name=args.image,
            boot_images_dir=boot_images_dir,
            arch=args.arch,
            gui=args.gui,
            drive=args.drive,
            bios=args.bios,
        )
    except (boot_manifest.BootManifestError, va_container.ContainerError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nInterrupted by user", file=sys.stderr)
        sys.exit(130)


if __name__ == "__main__":
    main()