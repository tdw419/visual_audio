with open("ubuntu-desktop-15g.raw", "rb") as f:
    f.seek(3474)
    b = f.read(100)
    non_zero = []
    for idx, byte in enumerate(b):
        if byte != 0:
            non_zero.append((idx + 3474, byte))
    print(non_zero[:20])
