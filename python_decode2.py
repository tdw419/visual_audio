from PIL import Image

img = Image.open("tmp_tiles/rootfs.0.0.pdb.png")
pixels = img.load()
width = 4096
grid_size = 4096

def d2xy(n, d):
    t = d
    x, y = 0, 0
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

out = bytearray()
for i in range((512+2)//3):
    x, y = d2xy(grid_size, i)
    out.extend(pixels[x, 128 + y][:3])

print("MBR signature at 510:", hex(out[510]), hex(out[511]))
