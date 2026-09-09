import re

with open("ubuntu-desktop-15g.raw", "rb") as f:
    chunk = f.read(1024 * 1024 * 1024)  # 1GB
    
    # regex for exactly 3474 zeroes followed by 255, 255, 255
    pattern = b'\x00' * 3474 + b'\xff\xff\xff'
    matches = [m.start() for m in re.finditer(pattern, chunk)]
    print(matches)
