import sys, tempfile, os
sys.path.insert(0, '/home/jericho/projects/zion/projects/visual_audio')
sys.path.insert(0, '/home/jericho/projects/zion/projects/visual_audio/tools')
from tools.glyph_gpt.atlas import build_default_atlas
from tools.glyph_gpt.baker import paged_kernel_image
from tools.glyph_gpt.runner import GlyphRunner
atlas = build_default_atlas()
out = tempfile.mktemp(suffix=".glyph")
paged_kernel_image(atlas, mode="flat64k", out_path=out)
r = GlyphRunner(out, ram_words=16384)
receipt = r.run(max_instructions=10000)
print({k: v for k, v in receipt.items() if k in ("faulted", "fault_reason", "fault_addr", "halted", "mode", "pc")})
os.unlink(out)
