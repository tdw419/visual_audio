#!/usr/bin/env python3
"""Build a SQLite companion index (kernel_symbols table) mapping kernel virtual
addresses to symbol names, per docs/../PDB_COMPANION_INDEX_PATTERN.md.

Extracts the embedded RISC-V kernel PE image from an Alpine boot payload
(boot_images/alpine_riscv64.lnx.bin), reconstructs an ELF via vmlinux-to-elf
(which recovers the kernel's own kallsyms table), and loads its symbol table
into <basename>_semantic.db so trace PCs (0xffffffff...) can be resolved to
function names with a single indexed query instead of redoing the ELF
reconstruction by hand every debugging session.

Usage:
    python3 tools/build_kernel_symbol_index.py [boot_images/alpine_riscv64.lnx.bin]

Query:
    sqlite3 boot_images/alpine_riscv64_semantic.db \\
      "SELECT name, addr FROM kernel_symbols WHERE addr <= 0x807e7b88 \\
       ORDER BY addr DESC LIMIT 1"
"""
import sqlite3
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _to_signed64(addr: int) -> int:
    return addr - (1 << 64) if addr >= (1 << 63) else addr


def _from_signed64(addr: int) -> int:
    return addr + (1 << 64) if addr < 0 else addr


def extract_kernel_pe(boot_bin: Path) -> bytes:
    data = boot_bin.read_bytes()
    kernel_offset = struct.unpack('<I', data[4:8])[0]
    kernel_size = struct.unpack('<I', data[8:12])[0]
    return data[kernel_offset:kernel_offset + kernel_size]


def reconstruct_elf(kernel_pe: bytes, out_elf: Path):
    with tempfile.NamedTemporaryFile(suffix='.bin', delete=False) as f:
        f.write(kernel_pe)
        raw_path = Path(f.name)
    try:
        subprocess.run(
            ['vmlinux-to-elf', str(raw_path), str(out_elf),
             '--e-machine=243', '--bit-size=64'],
            check=True, capture_output=True, text=True,
        )
    finally:
        raw_path.unlink(missing_ok=True)


def load_symbols(elf_path: Path):
    proc = subprocess.run(['nm', '-n', str(elf_path)], check=True,
                           capture_output=True, text=True)
    for line in proc.stdout.splitlines():
        parts = line.split(maxsplit=2)
        if len(parts) != 3:
            continue
        addr_hex, sym_type, name = parts
        try:
            addr = int(addr_hex, 16)
        except ValueError:
            continue
        yield addr, sym_type, name


def build_index(boot_bin: Path, db_path: Path):
    print(f"[1/3] Extracting kernel PE from {boot_bin} ...")
    kernel_pe = extract_kernel_pe(boot_bin)
    print(f"      {len(kernel_pe):,} bytes")

    with tempfile.TemporaryDirectory() as tmpdir:
        elf_path = Path(tmpdir) / 'kernel.elf'
        print("[2/3] Reconstructing ELF via vmlinux-to-elf (recovers kallsyms) ...")
        reconstruct_elf(kernel_pe, elf_path)

        print(f"[3/3] Loading symbol table into {db_path} ...")
        db_path.unlink(missing_ok=True)
        conn = sqlite3.connect(db_path)
        conn.execute("""
            CREATE TABLE kernel_symbols (
                addr INTEGER NOT NULL,
                sym_type TEXT NOT NULL,
                name TEXT NOT NULL
            )
        """)
        # SQLite INTEGER is signed 64-bit; kernel addresses (0xffffffff8...) exceed
        # int64 max, so store the two's-complement signed representation and convert
        # back on read (see _to_signed64 / _from_signed64).
        rows = [(_to_signed64(addr), t, n) for addr, t, n in load_symbols(elf_path)]
        conn.executemany("INSERT INTO kernel_symbols (addr, sym_type, name) VALUES (?, ?, ?)", rows)
        conn.execute("CREATE INDEX idx_kernel_symbols_addr ON kernel_symbols(addr)")
        conn.commit()
        conn.close()
        print(f"      {len(rows):,} symbols indexed")


def symbol_at(db_path: Path, addr: int) -> str:
    """Nearest symbol at or below addr — the companion-index equivalent of
    manually bisecting an nm dump, used by trace tooling to resolve a PC."""
    conn = sqlite3.connect(db_path)
    row = conn.execute(
        "SELECT name, addr FROM kernel_symbols WHERE addr <= ? ORDER BY addr DESC LIMIT 1",
        (_to_signed64(addr),),
    ).fetchone()
    conn.close()
    if row is None:
        return f"0x{addr:x} (no symbol)"
    name, sym_addr = row
    offset = addr - _from_signed64(sym_addr)
    return f"{name}+0x{offset:x}" if offset else name


DEFAULT_BOOT_BIN = REPO_ROOT / 'boot_images' / 'alpine_riscv64.lnx.bin'


def default_db_for(boot_bin: Path) -> Path:
    return boot_bin.parent / f"{boot_bin.stem.replace('.lnx', '')}_semantic.db"


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == 'resolve':
        # tools/build_kernel_symbol_index.py resolve 0xffffffff807e7b88 [0xother ...]
        db_path = default_db_for(DEFAULT_BOOT_BIN)
        for arg in sys.argv[2:]:
            addr = int(arg, 16)
            print(f"  {arg} -> {symbol_at(db_path, addr)}")
        sys.exit(0)

    boot_bin = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_BOOT_BIN
    db_path = default_db_for(boot_bin)
    build_index(boot_bin, db_path)

    # Smoke-test against the addresses resolved by hand earlier this session.
    for addr in (0xffffffff807e7b88, 0xffffffff807e7840, 0xffffffff8032c908):
        print(f"  0x{addr:x} -> {symbol_at(db_path, addr)}")
