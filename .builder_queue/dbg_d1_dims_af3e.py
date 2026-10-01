import sys
sys.path.insert(0, 'tools'); sys.path.insert(0, '.')
from tools.glyph_gpt.baker import bake_image
img = bake_image(":__entry\nHALT\n", cols_instrs=8, min_rows=16, out_path=None)
h, w, _ = img.shape
print("bake dims", w, "x", h, "=> words", w * h)
