import sys
sys.path.insert(0, "experiments"); sys.path.insert(0, "tools"); sys.path.insert(0, ".")
from experiments.glyph_l1_shell import GlyphL1Shell, L1Session
from tools.glyph_gpt.runner import GlyphRunner
import tempfile
sh = GlyphL1Shell(session=L1Session(tempfile.mkdtemp(prefix="l1wgsl_")))
r = GlyphRunner(sh.image, ram_words=16384)
rec = r.run_wgsl(max_steps=2048, input_ring=b"e hello twin")
print("error:", rec.get("error"), "| halted:", rec.get("halted"), "| steps:", rec.get("steps"))
out = bytes(w & 0xFF for w in (rec.get("output") or []) if w)
print("twin PRT:", out)
