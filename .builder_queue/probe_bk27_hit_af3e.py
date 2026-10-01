"""BK-27 receipt probe: measured fresh-bake vs cache-hit turn cost."""
import sys, time
sys.path.insert(0, "/home/jericho/projects/zion/projects/visual_audio")
from experiments.glyph_l1_shell import GlyphL1Shell

sh = GlyphL1Shell()
sh.turn("echo alpha record1 > probe27.txt")
sh.turn("echo beta record2 >> probe27.txt")

t0 = time.perf_counter(); a = sh.turn("grep record1 probe27.txt"); t1 = time.perf_counter()
b = sh.turn("grep record1 probe27.txt"); t2 = time.perf_counter()
assert a == b and a, (a, b)
fresh_ms = (t1 - t0) * 1000
hit_ms = (t2 - t1) * 1000
print(f"fresh bake turn: {fresh_ms:.1f} ms")
print(f"cache-hit turn:  {hit_ms:.1f} ms")
print(f"speedup:         {fresh_ms / hit_ms:.1f}x")
print(f"cache entries:   {len(sh._bake_cache)}")
