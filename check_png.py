import glob
from PIL import Image

for path in glob.glob("tmp_tiles/*.pdb.png"):
    try:
        Image.open(path).load()
    except Exception as e:
        print(f"{path}: {e}")
