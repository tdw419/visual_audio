#!/usr/bin/env python3
"""
Add an emulator binary to the MKV container.

Usage:
  python3 tools/add_emulator.py <emulator_name> <path_to_binary>

Examples:
  # Add Bochs (x86 emulator)
  python3 tools/add_emulator.py bochs /usr/bin/bochs

  # Add TinyEMU (RISC-V emulator)
  python3 tools/add_emulator.py tinyemu /usr/bin/temu

  # Add SIMH (classic systems)
  python3 tools/add_emulator.py simh /usr/local/bin/pdp11
"""

import subprocess
import sys
from pathlib import Path


def add_emulator(name, binary_path):
    """Add an emulator binary to the MKV."""
    binary_path = Path(binary_path)

    if not binary_path.exists():
        print(f"ERROR: Binary not found: {binary_path}")
        return 1

    print(f"Adding emulator: {name}")
    print(f"  Binary: {binary_path}")
    print(f"  Size: {binary_path.stat().st_size:,} bytes")

    # Add to MKV
    result = subprocess.run([
        "python3", "tools/va_container.py", "add",
        "visual_audio.mkv", str(binary_path),
        "--name", name,
        "--role", "emulator",
        "--note", f"CPU emulator: {name}"
    ])

    if result.returncode != 0:
        print(f"ERROR: Failed to add emulator")
        return 1

    print(f"✓ Added {name} to MKV")

    # Verify
    print(f"\nVerifying...")
    result = subprocess.run([
        "python3", "tools/va_container.py", "ls", "visual_audio.mkv"
    ], capture_output=True, text=True)

    if name in result.stdout:
        print(f"✓ {name} verified in MKV")
    else:
        print(f"WARNING: {name} not found in MKV listing")

    return 0


def main():
    if len(sys.argv) != 3:
        print(f"Usage: {sys.argv[0]} <emulator_name> <binary_path>")
        print(f"\nExamples:")
        print(f"  {sys.argv[0]} bochs /usr/bin/bochs")
        print(f"  {sys.argv[0]} tinyemu /usr/bin/temu")
        return 1

    name = sys.argv[1]
    binary_path = sys.argv[2]

    return add_emulator(name, binary_path)


if __name__ == "__main__":
    sys.exit(main())