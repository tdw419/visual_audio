"""dbg_d31c_trace_diff_af3e.py — falsifier 1 (ledger 2026-09-25 ~10:2x).

Catch the SpatialMisalignmentFault inside GlyphCPUv2 at the moment the PC
delegates to a bad x, and dump:
  - the last N glyph lines executed (via _pcmap from the glyph source)
  - the glyph registers r26..r30 at fault time
  - the same program's glyph source around the last executed line

Run: .venv/bin/python .builder_queue/dbg_d31c_trace_diff_af3e.py <scenario>
"""
import sys, tempfile, traceback
from pathlib import Path

VA = Path('/home/jericho/projects/zion/projects/visual_audio')
for p in (str(VA / 'tools'), str(VA), str(VA / 'tests')):
    if p not in sys.path:
        sys.path.insert(0, p)

import tools.rv64i_to_glyph as t2g  # noqa: E402
from tools.rv64i_to_glyph import transpile_elf_to_glyph  # noqa: E402
from tools.glyph_isa_v2 import GlyphCPUv2, OpcodeMapV2, SpatialMisalignmentFault  # noqa: E402
import test_rv64i_to_glyph_xv6_nano as T  # noqa: E402
from tools.rv64i_to_glyph import assemble_glyph_to_pixels  # noqa: E402

SCENARIO = int(sys.argv[1]) if len(sys.argv) > 1 else 6


def pcmap_from_source(src):
    """Line-number -> pixel word (col,row) map: mirrors the test helper."""
    # reuse the test's helper if importable
    return T._pcmap_from_source(src)


def run_with_trace(elf_bytes, **kw):
    glyph_source = transpile_elf_to_glyph(
        elf_bytes, entry_symbol="_start", byte_to_word_mem=True,
        ptr_table_base=kw.get('ptr_table_base'))
    cpu = GlyphCPUv2(OpcodeMapV2(), cols_instrs=64)
    pixels, coords = assemble_glyph_to_pixels(glyph_source, cols_instrs=64, min_rows=32)
    cpu.memory = [0] * 16384
    for vaddr, blob in T.parse_elf_data_sections(elf_bytes):
        for i, byte in enumerate(blob):
            a = vaddr + i
            w = a >> 2
            sh = (a & 3) * 8
            cpu.memory[w] = (cpu.memory[w] & ~(0xFF << sh)) | (byte << sh)
    tv, tb, _ = T.parse_elf(elf_bytes)
    base = kw.get('ptr_table_base', T.PTR_TABLE_BASE)
    for wi, packed in T.build_pointer_table(tb, tv, coords).items():
        idx = (base >> 2) + wi
        if 0 <= idx < len(cpu.memory):
            cpu.memory[idx] = packed
    if kw.get('kfault_rv_addr') is not None:
        from tools.glyph_isa_v2 import KFAULT_PC_ADDR
        col, row = coords[f":pc_{kw['kfault_rv_addr']:08x}"]
        cpu.memory[KFAULT_PC_ADDR >> 2] = ((row & 0xFFFF) << 16) | (col & 0xFFFF)
    if kw.get('ksys_rv_addr') is not None:
        from tools.glyph_isa_v2 import KSYS_PC_ADDR
        col, row = coords[f":pc_{kw['ksys_rv_addr']:08x}"]
        cpu.memory[KSYS_PC_ADDR >> 2] = ((row & 0xFFFF) << 16) | (col & 0xFFFF)

    # word -> glyph line map: assemble with per-line source markers is not
    # available, so instead we map pixel word back to instr index:
    # pixels are scanline: word w = row*64+col holds instr w of the program
    # (assemble_glyph_to_pixels packs instrs linearly with cols_instrs=64).
    lines = [ln for ln in glyph_source.splitlines() if ln.strip()]
    w2line = {i: ln for i, ln in enumerate(lines)}

    history = []

    class Tracer:
        def step(self, pixels):
            w = cpu.pc[1] * 64 + cpu.pc[0]
            history.append((w, w2line.get(w, f'<word {w}>')))
            return cpu.step(pixels)

    # monkey-patch: we cannot easily wrap step, so run manually
    cpu.pc = (0, 0)
    cpu.running = True
    fault = None
    try:
        for _ in range(3_000_000):
            w = cpu.pc[1] * 64 + cpu.pc[0]
            history.append((w, w2line.get(w, f'<word {w}>')))
            if not cpu.step(pixels):
                break
    except SpatialMisalignmentFault as e:
        fault = e
    except Exception as e:
        fault = e
    return cpu, history, fault, glyph_source


def main():
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        elf_bytes, bin_data, objdump = T._build(SCENARIO, tmp)
        want = {"g_console", "g_clen", "g_fault_pid", "g_fault_addr", "proc",
                "g_arena", "fault_handler", "switch_to"}
        sym = T._read_syms(elf_bytes, tmp, want)
        cpu, history, fault, src = run_with_trace(
            elf_bytes,
            kfault_rv_addr=sym["fault_handler"],
            ksys_rv_addr=(sym["syscall_dispatch"] if SCENARIO == 7 else None),
        )
        print(f"scenario {SCENARIO}: steps={len(history)} fault={fault!r}")
        if fault is None:
            return
        print("\n--- last 30 executed glyph lines ---")
        for w, ln in history[-30:]:
            print(f"  w={w:5d}  {ln}")
        print("\n--- registers r0..r31 at fault ---")
        for i in range(0, 32, 4):
            print("  " + "  ".join(
                f"r{i+j}={cpu.registers[i+j]:#010x}" if hasattr(cpu, 'registers') else f"r{i+j}=?"
                for j in range(4)))


if __name__ == '__main__':
    main()
