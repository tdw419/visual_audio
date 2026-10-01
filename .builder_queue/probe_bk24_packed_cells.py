#!/usr/bin/env python3
"""probe_bk24_packed_cells.py — round-7b: dump the PACKED seed values per :pc_ entry.

Round 7: RED build has 44 MORE :pc_ entries (0x4fc..0x5a8 contiguous) than
GREEN; all shared entries' labels are byte-identical in the text. The
:pc_ label LINES carry no packed value (the loader packs them during the
fixed-point). To see the actual seeded VALUES we must replicate the
loader's fixed-point packing here — i.e. run the same assemble passes and
print packed per entry. If any shared entry's packed value differs between
G and R beyond the pure splice shift, the seeds are wrong under the new
layout; if they're consistently +delta, the seeding is consistent and the
defect is elsewhere (bake stamping).
"""
import importlib.util
import sys
import tempfile
from pathlib import Path

_REPO = Path("/home/jericho/projects/zion/projects/visual_audio")
for _p in (str(_REPO), str(_REPO / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

spec = importlib.util.spec_from_file_location(
    "t_gh23", _REPO / "tests" / "test_gh23_libc_runtime.py")
t = importlib.util.module_from_spec(spec)
spec.loader.exec_module(t)

spec2 = importlib.util.spec_from_file_location(
    "p_r1", _REPO / ".builder_queue" / "probe_bk24_wrapper_falsifier.py")
p1 = importlib.util.module_from_spec(spec2)
spec2.loader.exec_module(p1)

import rv64i_to_glyph as r2g

CELLS_PER_ROW = 16
SPLICE_OFFSET_CELLS = 384


def collect_packed(libc_text: str, tag: str) -> dict[int, int]:
    """Replicate the loader's fixed-point (copy of _load_posix_program's
    core) and return {rv_byte: spliced_cell} for every :pc_ entry."""
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        elf = t._compile_elf(tmp, p1.QSORT_ONLY_C, libc_text=libc_text)
        base, text, symbols = r2g.parse_elf(elf)
        gp_addr = next((a for a, n in r2g.parse_elf(elf)[2].items()
                        if n == "__global_pointer$"), None)
        symbols = {a: n for a, n in symbols.items()
                   if not n.startswith("$") and n not in t.LINKER_JUNK}
        lines = r2g.transpile_rv32i_to_glyph(
            text_bytes=text, symbols=symbols, base_addr=base,
            entry_symbol="_start", use_ir=True,
            cols_instrs=16).splitlines()

        out: list[str] = []
        prev = ""
        for ln in lines:
            s = ln.split(";")[0].strip()
            if not s or s.startswith(":"):
                out.append(ln)
                continue
            if s == "HALT" and prev.startswith("LDI r17 "):
                out.append("SYSCALL r10")
                prev = "SYSCALL r10"
                continue
            out.append(ln)
            prev = s

        def _final_text(pc_seed_packed=None):
            init: list[str] = []
            for vaddr, blob in r2g.parse_elf_data_sections(elf):
                for wi in range(0, len(blob), 4):
                    word = int.from_bytes(
                        blob[wi:wi + 4].ljust(4, b"\0"), "little")
                    w = (vaddr + wi) >> 2
                    init.append(f"LDI r20 {word & 0xFFFF}")
                    hi = (word >> 16) & 0xFFFF
                    if hi:
                        init.extend(["LDI r21 {0}".format(hi),
                                     "LDI r22 16", "SHL r21 r22",
                                     "OR r20 r21"])
                    init.append(f"LDI r15 {w}")
                    init.append("ST r15 r20")
            for rv_byte, packed in (pc_seed_packed or {}).items():
                word = (r2g.PTR_TABLE_BASE + rv_byte) >> 2
                init.extend([
                    f"LDI r20 {packed & 0xFFFF}",
                    f"LDI r21 {(packed >> 16) & 0xFFFF}",
                    "LDI r22 16", "SHL r21 r22", "OR r20 r21",
                ])
                init.append(f"LDI r15 {word}")
                init.append("ST r15 r20")
            idx = next(i for i, ln in enumerate(out)
                       if ln.split(";")[0].strip().startswith("LDI r31"))
            jmp_idx = next(i for i in range(idx + 1, len(out))
                           if out[i].startswith("JMP "))
            seeded = (out[:idx + 1]
                      + ["LDI r2 1023"]
                      + ([f"LDI r3 {gp_addr}"] if gp_addr is not None else [])
                      + init
                      + out[jmp_idx:])
            return "\n".join(seeded) + "\n"

        shape_txt = _final_text()
        _, pc_coords = r2g.assemble_glyph_to_pixels(
            shape_txt, cols_instrs=CELLS_PER_ROW, min_rows=34)
        seeds: dict[int, int] = {}
        cells: dict[int, int] = {}
        for _it in range(5):
            new_seeds: dict[int, int] = {}
            new_cells: dict[int, int] = {}
            for lbl, (col, row) in pc_coords.items():
                if not lbl.startswith(":pc_"):
                    continue
                rv_byte = int(lbl[4:], 16)
                flat_cell = row * CELLS_PER_ROW + col
                spliced_cell = flat_cell + SPLICE_OFFSET_CELLS
                packed = (((spliced_cell // CELLS_PER_ROW) & 0xFFFF) << 16) \
                    | ((spliced_cell % CELLS_PER_ROW) & 0xFFFF)
                new_seeds[rv_byte] = packed
                new_cells[rv_byte] = spliced_cell
            if new_seeds == seeds:
                break
            seeds = new_seeds
            cells = new_cells
            _, pc_coords = r2g.assemble_glyph_to_pixels(
                _final_text(seeds), cols_instrs=CELLS_PER_ROW, min_rows=34)
        else:
            raise AssertionError("no convergence")
        return cells, seeds


def main() -> int:
    g_cells, g_seeds = collect_packed(p1.VARIANTS["V_trivial_write"],
                                      "GREEN")
    r_cells, r_seeds = collect_packed(p1.VARIANTS["V_new_control"], "RED")
    shared = sorted(set(g_cells) & set(r_cells))
    print(f"shared entries: {len(shared)}; G-only: "
          f"{len(set(g_cells)-set(r_cells))}; R-only: "
          f"{len(set(r_cells)-set(g_cells))}")
    deltas = {rv: r_cells[rv] - g_cells[rv] for rv in shared}
    uniq = sorted(set(deltas.values()))
    print("cell delta (R-G) distribution:", uniq[:10],
          f"({len(uniq)} distinct)")
    # find where the delta changes (a step in the shift = the insertion point)
    prev = None
    for rv in shared:
        if prev is not None and deltas[rv] != prev:
            print(f"delta changes at :pc_{rv:02x}: {prev} -> {deltas[rv]}")
        prev = deltas[rv]
    # consistency: is each packed seed exactly the packed form of its cell?
    bad = [rv for rv in shared
           if r_seeds[rv] != (((r_cells[rv] // CELLS_PER_ROW) & 0xFFFF) << 16)
           | (r_cells[rv] % CELLS_PER_ROW)]
    print("RED entries whose packed seed != packed(cell):", bad[:10],
          f"({len(bad)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
