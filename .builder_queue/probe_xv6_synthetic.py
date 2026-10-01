#!/usr/bin/env python3
"""Bounded synthetic probe for SUITE-XV6-2.

Per Determinism clause:
"Bounded synthetic probe (allowed, one short run): an infinite-loop RV64 ELF written
to tmp_path, booted with a small BOOT_TIMEOUT, must terminate with a token-bearing
non-shell verdict rather than hanging. This is the proof that L3/L4 work without
the real kernel."
"""

import os
import struct
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from tests.test_xv6_boot_regression import (
    run_xv6_boot,
    classify_boot_outcome,
    XV6_FS_COMMITTED,
)

def create_synthetic_rv64_elf(path: Path):
    """Create a minimal valid RV64 ELF executable containing an infinite loop."""
    e_ident = b"\x7fELF\x02\x01\x01\x00" + b"\x00" * 8
    e_type = struct.pack("<H", 2)       # ET_EXEC
    e_machine = struct.pack("<H", 243)  # EM_RISCV
    e_version = struct.pack("<I", 1)
    e_entry = struct.pack("<Q", 0x80000000)
    e_phoff = struct.pack("<Q", 64)
    e_shoff = struct.pack("<Q", 0)
    e_flags = struct.pack("<I", 0)      # RVC clear
    e_ehsize = struct.pack("<H", 64)
    e_phentsize = struct.pack("<H", 56)
    e_phnum = struct.pack("<H", 1)
    e_shentsize = struct.pack("<H", 64)
    e_shnum = struct.pack("<H", 0)
    e_shstrndx = struct.pack("<H", 0)
    elf_hdr = (
        e_ident + e_type + e_machine + e_version + e_entry +
        e_phoff + e_shoff + e_flags + e_ehsize + e_phentsize +
        e_phnum + e_shentsize + e_shnum + e_shstrndx
    )

    p_type = struct.pack("<I", 1)       # PT_LOAD
    p_flags = struct.pack("<I", 7)      # rwx
    p_offset = struct.pack("<Q", 0x1000)
    p_vaddr = struct.pack("<Q", 0x80000000)
    p_paddr = struct.pack("<Q", 0x80000000)
    p_filesz = struct.pack("<Q", 4)
    p_memsz = struct.pack("<Q", 4)
    p_align = struct.pack("<Q", 0x1000)
    ph_hdr = p_type + p_flags + p_offset + p_vaddr + p_paddr + p_filesz + p_memsz + p_align

    padding = b"\x00" * (0x1000 - len(elf_hdr) - len(ph_hdr))
    code = struct.pack("<I", 0x0000006f)  # j . (infinite loop)
    path.write_bytes(elf_hdr + ph_hdr + padding + code)


def main():
    print("=== SYNTHETIC RV64 NON-SHELL PROBE ===")
    start_t = time.time()
    SYNTHETIC_TIMEOUT = 10  # small bounded timeout

    with tempfile.TemporaryDirectory() as td:
        elf_path = Path(td) / "infinite_loop.elf"
        create_synthetic_rv64_elf(elf_path)
        print(f"Created synthetic infinite-loop ELF: {elf_path} ({elf_path.stat().st_size} bytes)")

        # Run boot with synthetic kernel and small timeout
        print(f"Booting synthetic kernel with timeout={SYNTHETIC_TIMEOUT}s...")
        success, stdout, stderr, metrics = run_xv6_boot(
            kernel_path=elf_path,
            fs_path=XV6_FS_COMMITTED,
            timeout=SYNTHETIC_TIMEOUT
        )
        elapsed = time.time() - start_t
        print(f"Boot finished in {elapsed:.2f}s (budget: <60s)")
        assert elapsed < 60, f"Synthetic probe exceeded 60s: {elapsed}s"

        token, fclass, desc = classify_boot_outcome(
            success, stdout, stderr, metrics, timeout_secs=SYNTHETIC_TIMEOUT
        )
        print(f"Outcome token: {token}")
        print(f"Outcome class: {fclass}")
        print(f"Outcome desc:  {desc}")

        # Assert token-bearing non-shell verdict
        assert token.startswith("NO_SHELL_"), f"Expected NO_SHELL_ token, got: {token}"
        assert fclass in ("MMU/RVC path", "kernel/toolchain"), f"Unexpected class: {fclass}"
        print("\nPROBE_VERDICT: SYNTHETIC NON-SHELL TOKEN-BEARING VERDICT VERIFIED (PASS)")


if __name__ == "__main__":
    main()
