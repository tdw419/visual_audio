#!/usr/bin/env python3
"""
PDB Semantic Layer: PC → Symbol → Pixel Region Mapping

Creates spatial tables in SQLite where:
- kernel_symbols table maps PC ranges to symbol names
- fault_frequency table maps PCs to how often they fault
- Combined spatial index can be rendered as a heat map

Usage:
    python pdb_semantic_layer.py /tmp/rv64i_boot_push.jsonl rv64i_semantic.db
"""

import json
import sqlite3
import struct
import sys
from pathlib import Path
from typing import Dict, List, Tuple
from collections import Counter


# Kernel text region (from trace: 0xffffffff80000000 - 0xffffffff807f...)
KERNEL_TEXT_BASE = 0xffffffff80000000
KERNEL_TEXT_SIZE = 0x01000000  # 16MB approximate


def pc_to_signed(pc: int) -> int:
    """
    Convert a potentially-unsigned 64-bit PC to signed 64-bit for SQLite.
    Python's int can exceed 64-bit signed range; convert to two's complement.
    """
    # Mask to 64 bits
    pc_masked = pc & 0xffffffffffffffff
    # If high bit set, convert to negative
    if pc_masked >= 0x8000000000000000:
        return pc_masked - 0x10000000000000000
    return pc_masked


def signed_to_pc(signed: int) -> int:
    """
    Convert signed 64-bit back to PC format (for display).
    """
    if signed < 0:
        return signed + 0x10000000000000000
    return signed


def create_schema(db: sqlite3.Connection):
    """
    Create semantic tables.
    """
    # Symbol mapping table (loaded from kernel binary later)
    db.execute("""
        CREATE TABLE IF NOT EXISTS kernel_symbols (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            start_addr INTEGER NOT NULL UNIQUE,
            end_addr INTEGER NOT NULL,
            size INTEGER NOT NULL
        )
    """)

    # Fault frequency table
    db.execute("""
        CREATE TABLE IF NOT EXISTS fault_frequency (
            pc INTEGER PRIMARY KEY,
            fault_count INTEGER NOT NULL,
            trap_type TEXT NOT NULL,
            first_seen_step INTEGER,
            last_seen_step INTEGER,
            uart_bytes_at_fault INTEGER DEFAULT 0
        )
    """)

    # Pixel region mapping (connects to PDB)
    db.execute("""
        CREATE TABLE IF NOT EXISTS pixel_regions (
            region_id INTEGER PRIMARY KEY AUTOINCREMENT,
            pc_start INTEGER NOT NULL,
            pc_end INTEGER NOT NULL,
            tile_x INTEGER NOT NULL,
            tile_y INTEGER NOT NULL,
            fault_count INTEGER NOT NULL,
            avg_frequency REAL NOT NULL,
            UNIQUE(tile_x, tile_y)
        )
    """)

    # Create indexes for queries
    db.execute("CREATE INDEX IF NOT EXISTS idx_fault_freq ON fault_frequency(fault_count DESC)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_symbol_range ON kernel_symbols(start_addr, end_addr)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_pixel_region ON pixel_regions(pc_start, pc_end)")

    db.commit()


def load_fault_trace(trace_file: str, db: sqlite3.Connection):
    """
    Load trace events into fault_frequency table.
    """
    with open(trace_file) as f:
        events = [json.loads(line) for line in f]

    # Count faults per PC
    fault_counts = Counter()
    fault_types = {}
    first_seen = {}
    last_seen = {}
    uart_at_fault = {}

    for evt in events:
        pc = evt.get("pc", 0)
        steps = evt.get("steps", 0)
        mcause = evt.get("mcause", 0)
        scause = evt.get("scause", 0)
        uart_bytes = evt.get("uart_new_bytes", 0)

        # Combine mcause/scause into trap type
        trap_type = f"m{mcause:x}/s{scause:x}"

        fault_counts[pc] += 1
        fault_types[pc] = trap_type

        if pc not in first_seen:
            first_seen[pc] = steps
        last_seen[pc] = steps
        uart_at_fault[pc] = uart_bytes

    # Insert into database (convert PCs to signed 64-bit)
    for pc, count in fault_counts.items():
        pc_signed = pc_to_signed(pc)
        db.execute("""
            INSERT OR REPLACE INTO fault_frequency
            (pc, fault_count, trap_type, first_seen_step, last_seen_step, uart_bytes_at_fault)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (pc_signed, count, fault_types[pc], first_seen[pc], last_seen[pc], uart_at_fault[pc]))

    db.commit()
    print(f"Loaded {len(fault_counts)} unique fault PCs")


def map_to_pixel_regions(db: sqlite3.Connection, pc_range_start: int, pc_range_end: int, tiles_per_row: int = 32):
    """
    Map PC ranges to pixel tiles (spatial coordinates).
    Uses Hilbert-like 2D mapping for locality preservation.
    """
    pc_range_size = pc_range_end - pc_range_start
    total_faults = db.execute("SELECT SUM(fault_count) FROM fault_frequency WHERE pc >= ? AND pc <= ?",
                              (pc_to_signed(pc_range_start), pc_to_signed(pc_range_end))).fetchone()[0] or 0

    if total_faults == 0:
        print("No faults in PC range")
        return

    # Calculate tile size (each tile covers a PC range)
    tile_size = pc_range_size // (tiles_per_row * tiles_per_row)

    # Clear existing pixel regions
    db.execute("DELETE FROM pixel_regions")

    # Map each faulting PC to a tile
    for row in db.execute("SELECT pc, fault_count FROM fault_frequency WHERE pc >= ? AND pc <= ?",
                          (pc_to_signed(pc_range_start), pc_to_signed(pc_range_end))):
        pc_signed, count = row
        pc = signed_to_pc(pc_signed)

        # Calculate tile coordinates (row-major for now, could be Hilbert)
        offset = pc - pc_range_start
        tile_idx = offset // tile_size
        tile_x = tile_idx % tiles_per_row
        tile_y = tile_idx // tiles_per_row

        # Calculate tile's PC range
        tile_pc_start = pc_range_start + tile_idx * tile_size
        tile_pc_end = min(tile_pc_start + tile_size, pc_range_end)

        # Insert or accumulate
        existing = db.execute(
            "SELECT fault_count FROM pixel_regions WHERE tile_x = ? AND tile_y = ?",
            (tile_x, tile_y)).fetchone()

        if existing:
            # Update existing tile
            existing_count = existing[0]
            new_count = existing_count + count
            new_freq = new_count / total_faults
            db.execute("""
                UPDATE pixel_regions
                SET fault_count = ?, avg_frequency = ?
                WHERE tile_x = ? AND tile_y = ?
            """, (new_count, new_freq, tile_x, tile_y))
        else:
            # Insert new tile
            db.execute("""
                INSERT INTO pixel_regions
                (pc_start, pc_end, tile_x, tile_y, fault_count, avg_frequency)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (tile_pc_start, tile_pc_end, tile_x, tile_y, count, count / total_faults))

    db.commit()
    print(f"Mapped to {tiles_per_row}x{tiles_per_row} pixel grid")


def generate_symbol_guesses(db: sqlite3.Connection):
    """
    Generate synthetic symbol names based on PC ranges (for visualization).
    Real kernel binary would use nm/readelf.
    """
    # Group PCs into regions (64KB each)
    region_size = 0x10000  # 64KB

    regions = db.execute("""
        SELECT (pc / ?) as region_idx, MIN(pc) as pc_start, MAX(pc) as pc_end,
               SUM(fault_count) as total_faults
        FROM fault_frequency
        GROUP BY region_idx
        ORDER BY total_faults DESC
        LIMIT 20
    """, (pc_to_signed(region_size),)).fetchall()

    print("\n=== Top Faulting Regions (synthetic symbols) ===")
    for region_idx, pc_start_signed, pc_end_signed, total_faults in regions:
        pc_start = signed_to_pc(pc_start_signed)
        pc_end = signed_to_pc(pc_end_signed)
        offset = pc_start - KERNEL_TEXT_BASE
        # Generate synthetic symbol name
        symbol = f"kernel_text_{offset:06x}"
        print(f"{symbol}: 0x{pc_start:016x} - 0x{pc_end:016x} ({total_faults} faults)")

        # Insert into kernel_symbols table
        db.execute("""
            INSERT OR REPLACE INTO kernel_symbols
            (name, start_addr, end_addr, size)
            VALUES (?, ?, ?, ?)
        """, (symbol, pc_to_signed(pc_start), pc_to_signed(pc_end), pc_end - pc_start))

    db.commit()


def print_summary(db: sqlite3.Connection):
    """
    Print database summary.
    """
    print("\n=== PDB Semantic Layer Summary ===")

    # Total faults
    total_faults = db.execute("SELECT SUM(fault_count) FROM fault_frequency").fetchone()[0]
    print(f"Total fault events: {total_faults}")

    # Top faulting PCs
    print("\nTop 10 faulting PCs:")
    for row in db.execute("SELECT * FROM fault_frequency ORDER BY fault_count DESC LIMIT 10"):
        pc_signed, count, trap, first, last, uart = row
        pc = signed_to_pc(pc_signed)
        print(f"  0x{pc:016x}: {count:2d} faults, trap={trap}, uart={uart}")

    # Stall detection (PCs with zero UART)
    stall_pcs = db.execute("SELECT COUNT(*) FROM fault_frequency WHERE uart_bytes_at_fault = 0").fetchone()[0]
    print(f"\nPCs with zero UART output: {stall_pcs}")

    # Pixel region summary
    regions = db.execute("SELECT COUNT(*) FROM pixel_regions").fetchone()[0]
    print(f"Active pixel regions: {regions}")


def main():
    if len(sys.argv) < 2:
        print("Usage: pdb_semantic_layer.py <trace.jsonl> [output.db]")
        sys.exit(1)

    trace_file = Path(sys.argv[1])
    db_path = sys.argv[2] if len(sys.argv) > 2 else trace_file.stem + "_semantic.db"

    # Create database
    db = sqlite3.connect(db_path)
    create_schema(db)

    # Load trace data
    print(f"Loading trace from {trace_file}...")
    load_fault_trace(str(trace_file), db)

    # Map to pixel regions (kernel text range)
    map_to_pixel_regions(db, KERNEL_TEXT_BASE, KERNEL_TEXT_BASE + KERNEL_TEXT_SIZE)

    # Generate synthetic symbols
    generate_symbol_guesses(db)

    # Print summary
    print_summary(db)

    print(f"\nSemantic database saved to {db_path}")
    print("\nExample queries:")
    print(f"  sqlite3 {db_path} 'SELECT * FROM fault_frequency ORDER BY fault_count DESC LIMIT 5'")
    print(f"  sqlite3 {db_path} 'SELECT tile_x, tile_y, fault_count FROM pixel_regions ORDER BY fault_count DESC LIMIT 10'")


if __name__ == "__main__":
    main()