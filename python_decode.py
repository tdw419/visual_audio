from PIL import Image
import math

img = Image.open("tmp_tiles/rootfs.0.0.pdb.png")
pixels = img.load()

# bbox.y_min = 128
width = 4096
height = 3968 # 4096 - 128
grid_size = 4096

def d2xy(n, d):
    t = d
    x = 0
    y = 0
    s = 1
    while s < n:
        rx = 1 & (t // 2)
        ry = 1 & (t ^ rx)
        if ry == 0:
            if rx == 1:
                x = s - 1 - x
                y = s - 1 - y
            x, y = y, x
        x += s * rx
        y += s * ry
        t //= 4
        s *= 2
    return x, y

out = []
for i in range(16):
    x, y = d2xy(grid_size, i)
    abs_x = x
    abs_y = 128 + y
    out.extend(pixels[abs_x, abs_y][:3])

print(out)
