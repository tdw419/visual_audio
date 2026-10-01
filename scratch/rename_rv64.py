#!/usr/bin/env python3
"""Bulk rename RV32I -> RV64I identifiers in the forked RV64 files."""

import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
RV64_FILES = [
    PROJECT_ROOT / "tools/SPATIAL_RV64I.wgsl",
    PROJECT_ROOT / "tools/spatial_rv64i_cpu.py",
    PROJECT_ROOT / "tools/rv64i_asm.py",
    PROJECT_ROOT / "tests/test_spatial_rv64i_cpu.py",
]

REPLACEMENTS = [
    (r"RV32I", "RV64I"),
    (r"rv32i", "rv64i"),
    (r"RV32", "RV64"),
    (r"rv32", "rv64"),
    (r"SpatialRV32ICore", "SpatialRV64ICore"),
    (r"test_spatial_rv32i_cpu", "test_spatial_rv64i_cpu"),
    (r"SPATIAL_RV32I", "SPATIAL_RV64I"),
    (r"# 32-bit", "# 64-bit"),
    (r"32 x 32-bit", "32 x 64-bit"),
]

def rename_file(filepath: Path) -> None:
    if not filepath.exists():
        print(f"Skipping {filepath}: not found")
        return

    content = filepath.read_text()

    for pattern, replacement in REPLACEMENTS:
        content = re.sub(pattern, replacement, content)

    filepath.write_text(content)
    print(f"Renamed {filepath}")

if __name__ == "__main__":
    for f in RV64_FILES:
        rename_file(f)

    print("\nDone! Core files have been renamed to RV64I variants.")
    print("Now the actual 64-bit implementation can begin.")