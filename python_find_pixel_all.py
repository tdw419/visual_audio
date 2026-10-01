from PIL import Image

img = Image.open("tmp_tiles/rootfs.0.0.pdb.png")
pixels = img.load()
for y in range(4096):
    for x in range(4096):
        if pixels[x, y] == (235, 99, 144):
            print(f"Found it at ({x}, {y})!")
