#!/usr/bin/env python3
"""
Trace Level 5c on QEMU for first 10K instructions to see expected PC.
"""

import subprocess
import struct
import re
from pathlib import Path

LEVEL5C_ELF = Path('tests/bare_metal/level5c/level5c.elf')

def main():
    print("Running Level 5c on QEMU with trace...")
    # Use QEMU's trace to see execution progress
    # Focus on PC after some steps - we can use GDB for this

    # Simpler: run with timeout and capture output to understand flow
    result = subprocess.run(
        ['qemu-system-riscv64', '-nographic', '-machine', 'virt',
         '-bios', 'none', '-kernel', str(LEVEL5C_ELF), '-m', '64M'],
        timeout=5,
        capture_output=True,
        text=True
    )

    print("QEMU output:")
    print(result.stdout)

if __name__ == '__main__':
    main()