#!/usr/bin/env python3
"""probe_bk24_deltastep.py — round-7c: is the packing self-consistent under row crosses?

Round 7b found: every shared entry's packed seed IS exactly packed(cell)
(0 inconsistencies), and the spliced-cell DELTA between GREEN and RED
varies (238..313, 72 distinct values) — entries don't shift uniformly,
which is EXPECTED because the two builds assemble to different row counts
per entry (5-instr form). The packed field keeps row<<16|col, rows up to
255 OK. BUT: the deltas differ per entry by row-quantization — when the
R build's extra text pushes an entry across a CELL-PER-ROW boundary, its
(row, col) repacking changes shape but the FLAT cell stays correct...

unless a row crosses 255 (DEFECT-7's 8-bit row field). Check: what is
the max spliced row in R vs G? If RED pushes entries past row 255, the
packed row field TRUNCATES and the RET lands wrong — matching the
measured symptom (stale PC pops).
"""
import importlib.util
import sys
from pathlib import Path

_REPO = Path("/home/jericho/projects/zion/projects/visual_audio")
for _p in (str(_REPO), str(_REPO / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

spec = importlib.util.spec_from_file_location(
    "p_r7", _REPO / ".builder_queue" / "probe_bk24_packed_cells.py")
p7 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p7)

spec1 = importlib.util.spec_from_file_location(
    "p_r1", _REPO / ".builder_queue" / "probe_bk24_wrapper_falsifier.py")
p1 = importlib.util.module_from_spec(spec1)
spec1.loader.exec_module(p1)

CELLS_PER_ROW = 16


def main() -> int:
    g_cells, g_seeds = p7.collect_packed(p1.VARIANTS["V_trivial_write"], "G")
    r_cells, r_seeds = p7.collect_packed(p1.VARIANTS["V_new_control"], "R")
    g_rows = [c // CELLS_PER_ROW for c in g_cells.values()]
    r_rows = [c // CELLS_PER_ROW for c in r_cells.values()]
    print(f"GREEN: max cell {max(g_cells.values())} = row {max(g_rows)}")
    print(f"RED  : max cell {max(r_cells.values())} = row {max(r_rows)}")
    over_g = [rv for rv, c in g_cells.items() if c // CELLS_PER_ROW > 255]
    over_r = [rv for rv, c in r_cells.items() if c // CELLS_PER_ROW > 255]
    print("G entries with row > 255:", len(over_g), [hex(v) for v in over_g[:8]])
    print("R entries with row > 255:", len(over_r), [hex(v) for v in over_r[:8]])
    # seeds actually stored (post-truncation) vs true cell:
    import rv64i_to_glyph as r2g
    bad_r = []
    for rv, packed in r_seeds.items():
        stored_row = (packed >> 16) & 0xFFFF
        true_row = r_cells[rv] // CELLS_PER_ROW
        if stored_row != true_row:
            bad_r.append((rv, true_row, stored_row))
    print("RED entries where packed row != true row (truncation):",
          len(bad_r), bad_r[:8])
    return 0


if __name__ == "__main__":
    sys.exit(main())
