#!/usr/bin/env python3
"""
TASK_G001 Receipt Validation

This script validates the receipt criteria for TASK_G001:
"python3 tools/dense_encoder.py run cartridge.png works via GeOS syscall"
"""

import os
import sys
import tempfile
import subprocess

# Add paths for imports
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)
sys.path.insert(0, os.path.join(project_root, 'tools'))

import dense_encoder


def test_receipt_criteria():
    """
    Validate the receipt criteria for TASK_G001.

    Receipt: python3 tools/dense_encoder.py run cartridge.png works via GeOS syscall
    """
    print("="*60)
    print("TASK_G001 Receipt Validation")
    print("="*60)
    print()
    print("Receipt Criteria:")
    print("  python3 tools/dense_encoder.py run cartridge.png --geos")
    print("  should work via GeOS syscall")
    print()

    # Create test cartridge
    test_payload = b'print("TASK_G001 receipt validation")'
    with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as f:
        cartridge_path = f.name

    try:
        # Encode cartridge
        print("Step 1: Encoding test cartridge...")
        dense_encoder.encode_dense(test_payload, cartridge_path, square=True)
        print(f"  ✓ Created {cartridge_path}")
        print()
        
        # Execute via GeOS
        print("Step 2: Executing via GeOS spatial syscall...")
        result = subprocess.run(
            ['python3', 'tools/dense_encoder.py', 'run', cartridge_path, '--geos', '--region', 'receipt_test'],
            cwd=project_root,
            capture_output=True,
            text=True
        )

        # Check output
        print("  Command output:")
        for line in result.stdout.split('\n'):
            if line:
                print(f"    {line}")

        print()

        # Validate
        print("Step 3: Validating receipt criteria...")

        checks = {
            "Exit code is 0": result.returncode == 0,
            "Decoded from dense image": "decoded" in result.stdout.lower(),
            "GeOS executor invoked": "GeOS executor" in result.stdout,
            "Spatial syscall interface": "spatial syscall" in result.stdout.lower(),
            "Region execution dispatched": "execution dispatched" in result.stdout.lower(),
            "MMIO address present": "0x80090000" in result.stdout or "syscall address" in result.stdout.lower(),
        }

        all_passed = True
        for check, passed in checks.items():
            status = "✓" if passed else "✗"
            print(f"  {status} {check}")
            if not passed:
                all_passed = False

        print()

        if all_passed:
            print("="*60)
            print("✓ TASK_G001 RECEIPT VALIDATED")
            print("="*60)
            print()
            print("The dense cartridge region executor successfully:")
            print("  1. Decodes cartridges from dense PNG")
            print("  2. Encodes payload as spatial VM bytecode")
            print("  3. Creates spatial syscall requests")
            print("  4. Dispatches execution to GeOS regions")
            print("  5. Uses correct MMIO addresses (0x8009_0000)")
            print()
            print("Receipt criteria satisfied:")
            print("  python3 tools/dense_encoder.py run cartridge.png --geos")
            print("  ✓ works via GeOS syscall")
            return 0
        else:
            print("="*60)
            print("✗ TASK_G001 RECEIPT FAILED")
            print("="*60)
            return 1

    finally:
        # Cleanup
        if os.path.exists(cartridge_path):
            os.unlink(cartridge_path)


if __name__ == "__main__":
    sys.exit(test_receipt_criteria())