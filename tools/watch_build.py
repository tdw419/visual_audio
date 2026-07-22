#!/usr/bin/env python3
"""
Auto-build watcher for bare-metal RISC-V payloads.

Watches tests/bare_metal/<payload>/ for source changes and auto-rebuilds:
  .elf → .npy

Usage:
  python3 watch_build.py <payload_dir>
  python3 watch_build.py tests/bare_metal/level4b
"""

import os
import sys
import time
import subprocess
from pathlib import Path

WATCHED = frozenset({'main.c', 'entry.S', 'link.ld', 'Makefile'})

def get_mtimes(payload_dir: Path) -> dict:
    """Get mtimes of watched files."""
    mtimes = {}
    for fname in WATCHED:
        fpath = payload_dir / fname
        if fpath.exists():
            mtimes[fname] = fpath.stat().st_mtime_ns
    return mtimes

def build(payload_dir: Path) -> bool:
    """Run make and elf_to_pixel_loader.py. Returns True on success."""
    tools_dir = Path(__file__).parent

    # Step 1: make
    result = subprocess.run(
        ['make', '-C', str(payload_dir)],
        capture_output=True, text=True, timeout=30,
    )
    for line in result.stdout.splitlines():
        print(f"  make: {line}", flush=True)
    if result.returncode != 0:
        print(f"  make FAILED (exit={result.returncode})", flush=True)
        for line in result.stderr.splitlines():
            print(f"  make err: {line}", flush=True)
        return False

    # Step 2: find the .elf
    elfs = list(payload_dir.glob('*.elf'))
    if not elfs:
        print(f"  No .elf produced!", flush=True)
        return False
    elf_path = elfs[0]
    npy_path = elf_path.with_suffix('.npy')

    result = subprocess.run(
        [sys.executable, str(tools_dir / 'elf_to_pixel_loader.py'),
         str(elf_path), '-o', str(npy_path),
         '--base-addr', '2147483648'],  # 0x80000000
        capture_output=True, text=True, timeout=30,
    )
    for line in result.stdout.splitlines():
        print(f"  pixel: {line}", flush=True)
    if result.returncode != 0:
        print(f"  pixel FAILED (exit={result.returncode})", flush=True)
        for line in result.stderr.splitlines():
            print(f"  pixel err: {line}", flush=True)
        return False

    return True


def main():
    if len(sys.argv) < 2:
        payload_dir = Path('tests/bare_metal/level4b')
    else:
        payload_dir = Path(sys.argv[1])

    if not payload_dir.is_dir():
        print(f"Not a directory: {payload_dir}", flush=True)
        sys.exit(1)

    print(f"AUTO-BUILD WATCHER STARTED", flush=True)
    print(f"  Watching: {payload_dir.resolve()}", flush=True)
    print(f"  Files: {', '.join(sorted(WATCHED))}", flush=True)
    print(f"  Poll: every 2s", flush=True)
    print(flush=True)

    last_mtimes = get_mtimes(payload_dir)

    while True:
        time.sleep(2)
        current_mtimes = get_mtimes(payload_dir)

        changed = [n for n, t in current_mtimes.items()
                   if last_mtimes.get(n) != t]
        if not changed:
            continue

        ts = time.strftime('%H:%M:%S')
        print(f"\n[{ts}] Change detected: {', '.join(changed)}", flush=True)
        last_mtimes = current_mtimes

        if build(payload_dir):
            print(f"  → Build OK. elf+npy up to date.", flush=True)
        else:
            print(f"  → Build FAILED. Fix errors and save again.", flush=True)


if __name__ == '__main__':
    main()
