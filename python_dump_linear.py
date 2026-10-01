from PIL import Image

img = Image.open("tmp_tiles/rootfs.0.0.pdb.png")
pixels = img.load()
for x in range(20):
    print(f"({x}, 128):", pixels[x, 128])
