#!/usr/bin/env python3
"""
run_native_boot.py — Verification script for TASK_C038
Executes the native in-hypervisor pixel boot test.
"""
import subprocess
import sys
from pathlib import Path

def main():
    root = Path(__file__).resolve().parent
    test_script = root / "tests" / "test_pixel_boot.py"
    if not test_script.exists():
        print(f"Error: {test_script} not found.")
        sys.exit(1)
        
    print("Running TASK_C038 verification: test_pixel_boot.py")
    result = subprocess.run([sys.executable, "-m", "pytest", str(test_script), "-v"])
    
    if result.returncode != 0:
        sys.exit("Native boot verification failed.")
        
    print("\n✓ Native pixel boot verified successfully.")
    
if __name__ == "__main__":
    main()
