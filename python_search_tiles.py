from PIL import Image

for i in range(10):
    try:
        img = Image.open(f"tmp_tiles/rootfs.{i}.0.pdb.png")
        pixels = img.load()
        if pixels[0, 128][:3] == (235, 99, 144):
            print(f"Found MBR in tile {i}!")
    except Exception as e:
        print(f"Tile {i} error: {e}")
