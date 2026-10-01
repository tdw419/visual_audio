from PIL import Image

img = Image.open("tmp_tiles/rootfs.0.0.pdb.png")
pixels = img.load()
non_zero = 0
for y in range(4096):
    for x in range(4096):
        if pixels[x, y] != (0, 0, 0):
            non_zero += 1
print("Non-zero pixels:", non_zero)
