#!/usr/bin/env python3
"""
glyph_dispatch verification gate.

Runs every oracle in the project and exits non-zero if ANY of them fails.
This is the single source of truth for "is glyph_dispatch green?" -- CI, an
autonomous loop, or a human all run exactly this and read the exit code.

Rules for this project (see ROADMAP.md):
  * every roadmap item ships its failing oracle FIRST; no oracle -> not on the
    automatable list.
  * a change may only land if `python3 verify.py` still exits 0.
  * receipts paste this command's real output; a summary line is not a receipt.

Add new oracles to ORACLES as they are written.
"""

import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent

ORACLES = [
    ("SHA-256 lockstep (FIPS + sweep vs hashlib)", "tools/sha256_lockstep_test.py"),
    ("item 1 - dispatch ABI unit suite",           "tests/test_dispatch.py"),
    ("item 2 - SHA-256 end-to-end via dispatch",    "tests/test_item2_dispatch_sha256.py"),
    ("item 3 - host MMIO dispatch bridge",           "tests/test_item3_mmio_bridge.py"),
    ("item 3b - Route B shader MMIO decode",         "tests/test_item3b_shader_mmio.py"),
]


def main() -> int:
    print("=" * 72)
    print("glyph_dispatch :: verify")
    print("=" * 72)
    results = []
    for name, rel in ORACLES:
        path = ROOT / rel
        print(f"\n>>> {name}\n    {rel}")
        if not path.exists():
            print("    MISSING")
            results.append((name, "MISSING", 0.0))
            continue
        t0 = time.time()
        proc = subprocess.run(
            [sys.executable, str(path)],
            cwd=ROOT, capture_output=True, text=True,
        )
        dt = time.time() - t0
        tail = proc.stdout.strip().splitlines()[-3:] if proc.stdout.strip() else []
        for line in tail:
            print(f"    | {line}")
        if proc.returncode != 0:
            print(f"    stderr: {proc.stderr.strip()[-500:]}")
        status = "PASS" if proc.returncode == 0 else f"FAIL(rc={proc.returncode})"
        print(f"    {status}  ({dt:.1f}s)")
        results.append((name, status, dt))

    print("\n" + "=" * 72)
    failed = [r for r in results if r[1] != "PASS"]
    for name, status, dt in results:
        print(f"  {status:<12} {name}")
    print("=" * 72)
    if failed:
        print(f"VERIFY: FAIL  ({len(failed)}/{len(results)} oracles not green)")
        return 1
    print(f"VERIFY: PASS  ({len(results)}/{len(results)} oracles green)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
