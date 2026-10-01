#!/usr/bin/env python3
"""
Level 5c QEMU test - verify the same ELF boots on QEMU.
Run: python3 tests/level5c_qemu_test.py
"""

import sys
import os
import subprocess
import time
from pathlib import Path

ELF_PATH = Path(__file__).parent / 'bare_metal' / 'level5c' / 'level5c.elf'
QEMU = 'qemu-system-riscv64'

def main():
    if not ELF_PATH.exists():
        print(f"ERROR: {ELF_PATH} not found")
        return 1

    # Check if QEMU is available
    try:
        subprocess.run([QEMU, '--version'], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        print(f"ERROR: {QEMU} not found")
        print("Install with: apt install qemu-system-riscv64")
        return 1

    print("Running Level 5c on QEMU RISC-V...")
    print()

    # Run QEMU and capture output
    process = subprocess.Popen(
        [
            QEMU,
            '-machine', 'virt',
            '-nographic',
            '-bios', 'none',
            '-kernel', str(ELF_PATH),
            '-m', '64M'
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True
    )

    output = ""
    start_time = time.time()
    timeout = 5  # seconds

    while True:
        try:
            line = process.stdout.readline()
            if line:
                output += line
                # Check if we got the success marker
                if "Level 5c Complete." in line:
                    process.terminate()
                    process.wait(timeout=2)
                    break
            elif process.poll() is not None:
                break  # Process exited
            elif time.time() - start_time > timeout:
                process.terminate()
                process.wait(timeout=2)
                break
        except KeyboardInterrupt:
            process.terminate()
            process.wait()
            break

    # Check for expected output
    success = True

    if "Level 5c: Non-Identity SV39 Mapping" in output:
        print("✓ Initial banner")
    else:
        print("✗ Missing initial banner")
        success = False

    if "Page table built" in output:
        print("✓ Page table built")
    else:
        print("✗ Page table not built")
        success = False

    if "supervisor_main reached" in output:
        print("✓ Supervisor main reached (non-identity VA fetch)")
    else:
        print("✗ Supervisor main not reached")
        success = False

    if "UART write via non-identity VA" in output:
        print("✓ Non-identity UART write")
    else:
        print("✗ Non-identity UART write failed")
        success = False

    if "Level 5c Complete." in output:
        print("✓ Level 5c Complete")
    else:
        print("✗ Level 5c not complete")
        success = False

    if not success:
        print()
        print("QEMU output:")
        print(output)
        return 1

    print()
    print("SUCCESS: Level 5c boots correctly on QEMU")
    return 0


if __name__ == '__main__':
    sys.exit(main())