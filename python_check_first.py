from PIL import Image

img = Image.open("tmp_tiles/rootfs.0.0.pdb.png")
pixels = img.load()
print(pixels[0, 128])
