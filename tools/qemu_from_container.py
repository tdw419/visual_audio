#!/usr/bin/env python3
"""
qemu_from_container.py -- Launch QEMU VMs from disk images stored in Visual Audio MKV container.

This enables "any software on our map" by encoding disk images (qcow2, raw, ISO)
into the VAC1 container, then extracting and launching them via QEMU.

Usage:
    # First, encode a disk image into the container
    python3 tools/qemu_from_container.py visual_audio.mkv add boot_images/alpine_riscv64.qcow2

    # Then, launch QEMU from the container
    python3 tools/qemu_from_container.py visual_audio.mkv launch alpine_riscv64.qcow2 --arch riscv64

    # List all encoded disk images
    python3 tools/qemu_from_container.py visual_audio.mkv list

    # Show container entries
    python3 tools/qemu_from_container.py visual_audio.mkv ls
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional, List

sys.path.insert(0, str(Path(__file__).resolve().parent))

from visual_audio_container import Container


def add_disk_image(container: Container, image_path: str, name: Optional[str] = None,
                   role: str = "qemu_disk", note: Optional[str] = None) -> None:
    """Add a disk image to the VAC1 container.

    Encodes the entire disk image as pixel data in the container.
    Works with: qcow2, raw, ISO, vdi, vmdk, and any QEMU-supported format.
    """
    image_path_obj = Path(image_path)

    if not image_path_obj.exists():
        raise FileNotFoundError(f"Disk image not found: {image_path}")

    # Default name: use the filename
    if name is None:
        name = image_path_obj.name

    # Read the disk image
    print(f"Reading disk image: {image_path_obj}")
    with open(image_path_obj, "rb") as f:
        payload = f.read()

    size_mb = len(payload) / (1024 * 1024)
    print(f"  Size: {size_mb:.1f} MB ({len(payload):,} bytes)")

    # Determine format from extension
    fmt = image_path_obj.suffix.lstrip('.')
    if fmt not in ["qcow2", "raw", "iso", "vdi", "vmdk", "img"]:
        fmt = "raw"  # Default fallback

    # Add to container
    note = note or f"QEMU disk image ({fmt}, {size_mb:.1f}MB) from {image_path_obj.name}"
    container.add(name, payload, role=role, note=note)

    print(f"✓ Added {name} to container ({len(payload):,} bytes)")


def launch_qemu(container: Container, name: str, arch: str = "riscv64",
                machine: Optional[str] = None, cpu: Optional[str] = None,
                memory: str = "512M", display: str = "none",
                bios: Optional[str] = None, drive: Optional[str] = None,
                enable_kvm: bool = False, extra_args: Optional[List[str]] = None) -> int:
    """Launch QEMU VM from a disk image stored in the VAC1 container.

    Returns: QEMU process ID (or None if daemon mode)
    """
    # Extract the disk image to a temporary file
    print(f"Extracting {name} from container...")

    try:
        payload = container.read(name)
    except KeyError:
        available = [e["name"] for e in container.list() if e["role"] == "qemu_disk"]
        raise KeyError(f"{name} not found in container. Available disk images: {available}")

    # Write to temporary file
    with tempfile.NamedTemporaryFile(
        suffix=f".{name.split('.')[-1] if '.' in name else 'img'}",
        prefix="vac_qemu_",
        delete=False
    ) as tmp:
        tmp.write(payload)
        tmp_path = tmp.name

    print(f"  Extracted to: {tmp_path} ({len(payload):,} bytes)")

    # Build QEMU command
    qemu_binary = f"qemu-system-{arch}"

    cmd = [qemu_binary]

    # Machine type
    if machine:
        cmd.extend(["-M", machine])
    elif arch == "riscv64":
        cmd.extend(["-M", "virt"])  # Default for RISC-V
    elif arch == "x86_64":
        cmd.extend(["-M", "pc"])

    # CPU type
    if cpu:
        cmd.extend(["-cpu", cpu])

    # Memory
    cmd.extend(["-m", memory])

    # Display
    if display == "none":
        cmd.extend(["-nographic"])
    elif display == "vnc":
        cmd.extend(["-display", "vnc=:0"])
    elif display == "sdl":
        cmd.extend(["-display", "sdl"])
    elif display == "gtk":
        cmd.extend(["-display", "gtk"])

    # BIOS/firmware
    if bios:
        if bios == "default":
            # Use default for the architecture
            pass
        elif bios == "none":
            cmd.append("-bios none")
        else:
            cmd.extend(["-bios", bios])

    # Drive
    if drive:
        # Additional drive (e.g., fs.img for xv6)
        drive_path = None
        if drive.startswith("container:"):
            # Extract second disk from container
            drive_name = drive.split(":", 1)[1]
            try:
                drive_payload = container.read(drive_name)
                with tempfile.NamedTemporaryFile(
                    suffix=f".{drive_name.split('.')[-1] if '.' in drive_name else 'img'}",
                    prefix="vac_qemu_drive_",
                    delete=False
                ) as tmp:
                    tmp.write(drive_payload)
                    drive_path = tmp.name
            except KeyError:
                print(f"Warning: Drive {drive_name} not found, skipping")
        else:
            # Use filesystem path directly
            drive_path = drive

        if drive_path:
            cmd.extend(["-drive", f"file={drive_path},format=raw,if=none,id=x0"])
            cmd.extend(["-device", "virtio-blk-device,drive=x0"])

    # Main disk image
    drive_format = "qcow2" if name.endswith(".qcow2") else "raw"
    cmd.extend(["-drive", f"file={tmp_path},format={drive_format},if=virtio"])

    # KVM acceleration
    if enable_kvm and arch == "x86_64":
        cmd.append("-enable-kvm")

    # Extra arguments
    if extra_args:
        cmd.extend(extra_args)

    # Log the command
    print(f"\nLaunching QEMU:")
    print(f"  {' '.join(cmd)}")
    print()

    # Launch QEMU (keep the tmp file around)
    proc = subprocess.Popen(cmd)

    print(f"QEMU PID: {proc.pid}")
    print(f"Disk image: {tmp_path} (will be cleaned up when QEMU exits)")

    # Wait for QEMU to finish
    try:
        return_code = proc.wait()
        print(f"\nQEMU exited with code {return_code}")

        # Clean up temporary file
        try:
            os.unlink(tmp_path)
            print(f"Cleaned up temporary disk image: {tmp_path}")
        except:
            pass

        return return_code
    except KeyboardInterrupt:
        print("\nInterrupted by user, terminating QEMU...")
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            print("QEMU did not terminate gracefully, killing...")
            proc.kill()
            proc.wait()

        # Clean up
        try:
            os.unlink(tmp_path)
        except:
            pass

        return 130  # Standard exit code for SIGINT


def list_disk_images(container: Container, role: str = "qemu_disk") -> None:
    """List all disk images stored in the container."""
    entries = container.list(filter_role=role)

    if not entries:
        print(f"No disk images found (role={role})")
        return

    total_size = 0
    print(f"Disk images in container ({len(entries)} entries):\n")

    for e in entries:
        size_mb = e["length"] / (1024 * 1024)
        total_size += e["length"]

        print(f"  {e['name']}")
        print(f"    Size: {size_mb:.2f} MB ({e['length']:,} bytes)")
        print(f"    Note: {e['note']}")
        print()

    print(f"Total: {total_size / (1024 * 1024):.2f} MB")


def main():
    parser = argparse.ArgumentParser(
        description="Launch QEMU VMs from VAC1 container",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Add a disk image
  python3 tools/qemu_from_container.py visual_audio.mkv add boot_images/alpine_riscv64.qcow2

  # Launch RISC-V VM
  python3 tools/qemu_from_container.py visual_audio.mkv launch alpine_riscv64.qcow2 --arch riscv64 --display nographic

  # Launch with VNC display
  python3 tools/qemu_from_container.py visual_audio.mkv launch ubuntu_desktop.qcow2 --arch x86_64 --display vnc --enable-kvm

  # Launch xv6 with filesystem disk
  python3 tools/qemu_from_container.py visual_audio.mkv launch xv6.img --arch riscv64 --bios none --drive container:fs.img
        """
    )

    parser.add_argument("container", help="VAC1 container path")

    subparsers = parser.add_subparsers(dest="command", required=True)

    # Add command
    add_parser = subparsers.add_parser("add", help="Add a disk image to the container")
    add_parser.add_argument("image_path", help="Path to disk image file")
    add_parser.add_argument("--name", help="Entry name (default: filename)")
    add_parser.add_argument("--role", default="qemu_disk", help="Entry role (default: qemu_disk)")
    add_parser.add_argument("--note", help="Optional note/description")

    # Launch command
    launch_parser = subparsers.add_parser("launch", help="Launch QEMU from container disk")
    launch_parser.add_argument("name", help="Disk image entry name in container")
    launch_parser.add_argument("--arch", default="riscv64", choices=["riscv64", "x86_64", "arm", "aarch64"])
    launch_parser.add_argument("--machine", help="Machine type (default: virt for RISC-V, pc for x86_64)")
    launch_parser.add_argument("--cpu", help="CPU type")
    launch_parser.add_argument("--memory", default="512M", help="Memory size (default: 512M)")
    launch_parser.add_argument("--display", default="none", choices=["none", "nographic", "vnc", "sdl", "gtk"])
    launch_parser.add_argument("--bios", help="BIOS/firmware path or 'none' or 'default'")
    launch_parser.add_argument("--drive", help="Additional drive (path or 'container:entry_name')")
    launch_parser.add_argument("--enable-kvm", action="store_true", help="Enable KVM acceleration (x86_64 only)")
    launch_parser.add_argument("--extra", nargs="*", dest="extra_args", help="Extra QEMU arguments")

    # List command
    list_parser = subparsers.add_parser("list", help="List disk images in container")
    list_parser.add_argument("--role", default="qemu_disk", help="Filter by role (default: qemu_disk)")

    # LS command (pass through to va_container)
    ls_parser = subparsers.add_parser("ls", help="List all container entries")

    args = parser.parse_args()

    with Container(args.container) as c:
        if args.command == "add":
            add_disk_image(c, args.image_path, args.name, args.role, args.note)
        elif args.command == "launch":
            launch_qemu(
                c, args.name, args.arch, args.machine, args.cpu,
                args.memory, args.display, args.bios, args.drive,
                args.enable_kvm, args.extra_args
            )
        elif args.command == "list":
            list_disk_images(c, args.role)
        elif args.command == "ls":
            entries = c.list()
            print(f"\nContainer entries ({len(entries)}):\n")
            for e in entries:
                print(f"  [{e['role']:12}] {e['name']:40} ({e['length']:8,} bytes)")


if __name__ == "__main__":
    main()