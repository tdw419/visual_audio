#!/usr/bin/env python3
"""
extract_and_boot_alpine.py — Extract Alpine from container and boot it

Demo: boots Alpine RISC-V from visual_audio.mkv

Usage:
  python3 tools/extract_and_boot_alpine.py --help
  python3 tools/extract_and_boot_alpine.py alpine_riscv64_raw
  python3 tools/extract_and_boot_alpine.py alpine_riscv64_qcow2
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools import va_container, boot_manifest


def extract_and_boot(
    image_name: str,
    container_path: Path = Path("visual_audio.mkv"),
    boot_images_dir: Path = Path("boot_images"),
    arch: str = "riscv64",
    bios: str = "none",
    gui: bool = False,
) -> None:
    """Extract image from container and boot it."""
    
    print(f"Extracting {image_name} from {container_path}...")
    target_path = boot_images_dir / image_name
    
    # Extract
    subprocess.run(
        ["python3", "tools/va_container.py", "cat", str(container_path), image_name, "-o", str(target_path)],
        check=True,
        capture_output=True,
    )
    
    print(f"Extracted {target_path.stat().st_size:,} bytes to {target_path}")
    
    # Build boot manifest
    manifest = boot_manifest.BootManifest(arch=arch, image=image_name, bios=bios, gui=gui)
    
    # Resolve and build QEMU argv
    image_path = boot_manifest.resolve_image(manifest, str(boot_images_dir))
    qemu_argv = boot_manifest.build_qemu_argv(manifest, image_path)
    
    # Launch
    print(f"\n{'='*60}")
    print(f"Booting Alpine RISC-V:")
    print(f"  Arch: {arch}")
    print(f"  Image: {image_name}")
    print(f"  BIOS: {bios}")
    print(f"{'='*60}")
    print(f"QEMU command: {' '.join(qemu_argv)}")
    print(f"\nPress Ctrl+A X to quit QEMU")
    print(f"{'='*60}\n")
    
    os.execvp(qemu_argv[0], qemu_argv)


def main():
    parser = argparse.ArgumentParser(
        description="Extract and boot Alpine from visual_audio.mkv"
    )
    parser.add_argument(
        "image",
        choices=["alpine_riscv64_raw", "alpine_riscv64_qcow2"],
        help="Alpine image name in container"
    )
    parser.add_argument(
        "--arch",
        default="riscv64",
        help="QEMU architecture (default: riscv64)"
    )
    parser.add_argument(
        "--bios",
        choices=["default", "none"],
        default="none",
        help="BIOS setting (default: none for Alpine)"
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
    
    try:
        extract_and_boot(
            image_name=args.image,
            container_path=Path(args.container),
            boot_images_dir=Path(args.boot_dir),
            arch=args.arch,
            bios=args.bios,
        )
    except (boot_manifest.BootManifestError, subprocess.CalledProcessError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()