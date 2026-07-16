import os
import pytest
import numpy as np
from PIL import Image

def test_build_corpus(tmp_path):
    text_file = tmp_path / "sample.txt"
    out_npy = tmp_path / "out.npy"
    out_png = tmp_path / "out.png"
    
    text_file.write_text("Hello\nWorld")
    
    from tools.build_pixel_corpus import build_corpus
    build_corpus(str(text_file), str(out_npy), str(out_png))
    
    assert out_npy.exists()
    assert out_png.exists()
    
    arr = np.load(str(out_npy))
    assert len(arr) > 0
    
    img = Image.open(str(out_png))
    assert img.size[0] == 256
    assert img.size[1] == 2
