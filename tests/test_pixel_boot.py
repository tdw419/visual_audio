#!/usr/bin/env python3
import os
import subprocess
import pytest
from pathlib import Path

def test_pixel_boot_pipeline(tmp_path):
    elf_path = "/tmp/test_payload.elf"
    if not os.path.exists(elf_path):
        pytest.skip(f"Test payload {elf_path} not found")
        
    png_path = tmp_path / "kernel.png"
    recovered_path = tmp_path / "recovered.elf"
    
    # Encode ELF to PNG
    subprocess.run(["python3", "tools/dense_encoder.py", "encode", elf_path, "-o", str(png_path)], check=True)
    
    # Decode PNG to ELF
    subprocess.run(["python3", "tools/dense_encoder.py", "decode", str(png_path), "-o", str(recovered_path)], check=True)
    
    # Boot in QEMU
    try:
        result = subprocess.run(
            ["qemu-system-riscv64", "-nographic", "-machine", "virt", "-kernel", str(recovered_path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=3
        )
        stdout = result.stdout
    except subprocess.TimeoutExpired as e:
        if isinstance(e.stdout, bytes):
            stdout = e.stdout.decode('utf-8', errors='ignore') if e.stdout else ""
        else:
            stdout = e.stdout if e.stdout else ""
        
    assert "*** HELLO FROM THE SPOKEN KERNEL ***" in stdout, "Kernel did not boot properly from pixel-recovered ELF"

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
