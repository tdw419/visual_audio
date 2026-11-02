import sys, time
sys.path.insert(0, '.')
from experiments.glyph_l1_shell import GlyphL1Shell

sh = GlyphL1Shell()
sh.turn("write sample.txt hello world record2 payload")
t0 = time.perf_counter(); sh.turn("grep record2 sample.txt"); t1 = time.perf_counter()
print(f"native grep hit: {(t1-t0)*1000:.1f}ms")

# host-arm grep for comparison
sh._SHELL_NATIVE = False
t0 = time.perf_counter(); r = sh.turn("grep record2 sample.txt"); t1 = time.perf_counter()
print(f"host grep hit: {(t1-t0)*1000:.1f}ms -> {r!r}")

import subprocess
t0 = time.perf_counter()
subprocess.run(["riscv64-unknown-elf-gcc", "--version"], capture_output=True)
t1 = time.perf_counter()
print(f"gcc --version alone: {(t1-t0)*1000:.1f}ms")
