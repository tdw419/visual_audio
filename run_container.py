#!/usr/bin/env python3
"""
run_container.py — Verification script for TASK_VAC001-007
Validates the container architecture by extracting and verifying the self-hosted MKV.
"""
import subprocess
import sys
from pathlib import Path

def main():
    root = Path(__file__).resolve().parent
    mkv_path = root / "visual_audio.mkv"
    if not mkv_path.exists():
        print(f"Error: {mkv_path.name} not found in repository root.")
        sys.exit(1)
        
    print(f"Verifying {mkv_path.name}...")
    result = subprocess.run([sys.executable, str(root / "tools" / "va_container.py"), "verify", str(mkv_path)])
    
    if result.returncode != 0:
        sys.exit("Container verification failed.")
        
    print("\n✓ Container verified successfully.")
    
if __name__ == "__main__":
    main()
