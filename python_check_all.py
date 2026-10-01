with open("tmp_tiles/rootfs.0.0.pdb.png", "rb") as f:
    import hashlib
    b = f.read()
    print("Tile 0 Hash:", hashlib.md5(b).hexdigest())

with open("ubuntu-desktop-15g.raw", "rb") as f:
    import hashlib
    b = f.read(16106127360)
    print("Raw Hash:", hashlib.md5(b).hexdigest())
