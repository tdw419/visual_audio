"""dbg C: verify the BK-41 L5 neuter shape — empty _BK41_LOCKED_WORDS in a
TEMP-COPY module must let the C6 sentinel LAND at TIMER_COUNT clean."""
import sys, tempfile, io, contextlib
from pathlib import Path
sys.path.insert(0, "."); sys.path.insert(0, "tools")
import numpy as np
import importlib.util

real = Path("tools/glyph_isa_v2.py")
src = real.read_text()
marker = "_BK41_LOCKED_WORDS = frozenset({"
assert marker in src, "marker missing"
end = src.index("})", src.index(marker)) + 2
neutered = src[:src.index(marker)] + "_BK41_LOCKED_WORDS = frozenset()" + src[end:]
assert neutered != src

with tempfile.TemporaryDirectory() as td:
    tmp = Path(td) / "neut.py"
    tmp.write_text(neutered)
    spec = importlib.util.spec_from_file_location("bk41_neut_dbgB", tmp)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    om = mod.OpcodeMapV2(wordbase_path=Path("db/wordbase.db"))
    cpu = mod.GlyphCPUv2(om, cols_instrs=8)
    cpu.memory = [0] * 16384
    from tools.glyph_containment import arm_tile
    arm_tile(cpu, (5, 0, 8, 8))
    cpu._tile_confinement = True
    cpu.memory[8194] = (6 << 16) | 0
    cpu.memory[8193] = 30 << 16
    cpu.running = True
    gadget = mod.GlyphAssemblerV2(om).assemble(
        ["LDI r2 8208", "LDI r3 4242", "ST r2 r3", "HALT"], width_instrs=8)
    canvas = np.zeros((32, 32, 3), dtype=np.uint8)
    canvas[0:2] = mod.GlyphAssemblerV2(om).assemble(
        ["LDI r17 2", "SYSCALL r10 2", "HALT"], width_instrs=8)[0:2]
    canvas[6:6 + gadget.shape[0]] = gadget
    n = 0
    with contextlib.redirect_stdout(io.StringIO()):
        while cpu.running and n < 500:
            cpu.step(canvas)
            n += 1
    print("steps", n, "faulted", cpu.faulted, (cpu.fault_reason or "")[:60])
    print("tcount", cpu.memory[8208])
