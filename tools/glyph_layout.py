"""Glyph OS Memory and Pixel Region Classifier & Conflict Scanner.

Imports canonical constants directly from baker.py to ensure zero drift.
Classifies word addresses, verifies spatial region disjointness
(code ∩ table ∩ mailbox = ∅), and scans bus-lane assignments in words 700..767.
"""

import os
import sys
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

# Ensure tools/ and repo root are in sys.path
_TOOLS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _TOOLS_DIR.parent
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from glyph_gpt import baker  # type: ignore
from glyph_gpt import libc_runtime  # type: ignore
from rv64i_to_glyph import PTR_TABLE_BASE  # type: ignore  # word 0x2000 (byte) — canonical


class Region:
    def __init__(self, name: str, start: int, end: int, description: str):
        self.name = name
        self.start = start  # inclusive
        self.end = end      # exclusive
        self.description = description

    def contains(self, word: int) -> bool:
        return self.start <= word < self.end

    def overlap(self, other: "Region") -> Optional[Tuple[int, int]]:
        s = max(self.start, other.start)
        e = min(self.end, other.end)
        if s < e:
            return (s, e)
        return None


def get_canonical_regions() -> List[Region]:
    """Derive canonical regions directly from committed engine constants.

    HARD attribute access — a missing constant is an error, never a guessed
    default (the silent-fallback pattern delivered confident wrong answers).
    """
    ptr_table_base = PTR_TABLE_BASE >> 2  # byte addr -> word addr (0x2000 -> 2048)
    ptr_table_end = ptr_table_base + 321  # 2369 words for indirect call table
    heap_base = libc_runtime.GH23_HEAP_BASE  # 2560, word addr

    return [
        Region("KERNEL_TEXT", 0, 700, "Kernel boot, interrupt vector, tick handler"),
        Region("KERNEL_BUS_MMIO", 700, 768, "Kernel dispatch, task status, MMIO mailboxes"),
        Region("KERNEL_STATE", 768, 1024, "Kernel internal state, page tables, ABI status"),
        Region("FS_PIXEL_WINDOW", baker.GH8_FSTAB_WORD, baker.GH8_FSTAB_WORD + 256, "Pixel-aliased FS window (vpn 4, words 1024..1279)"),
        Region("TABLE_PIX_WINDOW", baker.GH18_TABLE_PIX_WORD, baker.GH18_TABLE_PIX_WORD + 256, "Pixel-mapped syscall table window (vpn 5, words 1312..1567)"),
        Region("SYSCALL_TABLE", baker.GH18_TABLE_WORD, baker.GH18_TABLE_WORD + 16, "Syscall vector table (words 1568..1583)"),
        Region("SYSCALL_TILE_RECT", baker.GH18_TILE_WORD, baker.GH18_TILE_WORD + 96, "Syscall tile execution rect (words 1600..1695)"),
        Region("PTR_TABLE", ptr_table_base, ptr_table_end, "Transpiler indirect call pointer table (words 2048..2369)"),
        Region("C_HEAP", heap_base, heap_base + 1024, "Picolibc malloc heap (words 2560..3583)"),
    ]


def classify_word(word: int) -> str:
    """Classify a 32-bit word address into its canonical region."""
    for reg in get_canonical_regions():
        if reg.contains(word):
            return f"{reg.name} ({reg.description})"
    if word < 1024:
        return f"PAGE_0_LOW_RAM (word {word})"
    vpn = word >> 8
    offset = word & 0xFF
    return f"PAGE_{vpn}_EXT (word {word}, vpn {vpn}, offset {offset})"


def assert_disjoint_regions() -> List[str]:
    """Verify that no critical regions overlap. Returns error strings if any."""
    regions = get_canonical_regions()
    errors = []
    for i, r1 in enumerate(regions):
        for r2 in regions[i + 1:]:
            ov = r1.overlap(r2)
            if ov:
                errors.append(
                    f"COLLISION: {r1.name} [{r1.start}..{r1.end}) overlaps with "
                    f"{r2.name} [{r2.start}..{r2.end}) at words [{ov[0]}..{ov[1]})"
                )
    return errors


def scan_bus_assignments() -> Dict[int, List[str]]:
    """Scan all named bus word constants in baker.py between 700 and 767."""
    bus_words: Dict[int, List[str]] = {}
    for attr in dir(baker):
        if attr.endswith("_WORD"):
            val = getattr(baker, attr)
            if isinstance(val, int) and 700 <= val < 768:
                bus_words.setdefault(val, []).append(attr)
    return dict(sorted(bus_words.items()))


def format_report() -> str:
    lines = []
    lines.append("=== Glyph OS Canonical Memory Layout & Bus Map ===")
    lines.append("")
    lines.append("Canonical Regions:")
    for reg in get_canonical_regions():
        lines.append(f"  [{reg.start:4d} .. {reg.end:4d}) (0x{reg.start*4:04x}..0x{reg.end*4:04x}): {reg.name:<18} — {reg.description}")
    
    lines.append("")
    lines.append("Region Disjointness:")
    collisions = assert_disjoint_regions()
    if not collisions:
        lines.append("  PASS: All critical spatial regions are strictly disjoint (code ∩ table ∩ mailbox = ∅).")
    else:
        for c in collisions:
            lines.append(f"  FAIL: {c}")

    lines.append("")
    lines.append("Bus Lane Word Assignments (700..767):")
    bus = scan_bus_assignments()
    for w, names in bus.items():
        lines.append(f"  Word {w:3d} (0x{w*4:04x}): {', '.join(names)}")
    
    return "\n".join(lines)


if __name__ == "__main__":
    rep = format_report()
    print(rep)
    collisions = assert_disjoint_regions()
    if collisions:
        sys.exit(1)
