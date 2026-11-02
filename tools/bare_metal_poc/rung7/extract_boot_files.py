#!/usr/bin/env python3
"""Extract vmlinuz + core.gz from the TinyCore ISO for direct kernel boot."""
import zlib

iso = open('TinyCore-current.iso', 'rb').read()

# core.gz: the big gzip cpio stream
i = iso.find(b'\x1f\x8b', 100000)
while i != -1:
    d = zlib.decompressobj(16 + zlib.MAX_WBITS)
    try:
        out = d.decompress(iso[i:])
    except Exception:
        i = iso.find(b'\x1f\x8b', i + 1)
        continue
    if out[:6] == b'070701':
        unused = len(d.unused_data)
        end = len(iso) - unused if unused else len(iso)
        open('core.gz', 'wb').write(iso[i:end])
        print(f'core.gz: iso[{i}:{end}] = {end - i} bytes')
        break
    i = iso.find(b'\x1f\x8b', i + 1)

# vmlinuz64: find bzImage magic MZ... tinycore kernel starts with MZ header
j = iso.find(b'MZ\x91\x91')  # classic bzImage 'MZ' + hijacked chars
if j == -1:
    j = iso.find(b'MZ')
print('vmlinuz MZ at', j)
# vmlinuz64 is a file extent; find via ISO directory: search 'VMLINUZ64;1'
k = iso.find(b'VMLINUZ64;1')
print('dir record at', k, iso[k - 33:k + 12].hex() if k != -1 else '')
if k != -1:
    # ISO9660 directory record: extent LBA at rec_start+2 (4 bytes LE both
    # orders), size at +10 (8 bytes). Record start: name len byte is at
    # offset -33+... use standard layout: search backwards for length byte
    # record: [0]=len [2..5]=extent LE [10..17]=size
    rec = k - 33
    for back in range(20, 60):
        r = k - back
        ext = int.from_bytes(iso[r + 2:r + 6], 'little')
        size = int.from_bytes(iso[r + 10:r + 18], 'little')
        if 0 < ext < len(iso) // 2048 and 1000000 < size < 10000000:
            data = iso[ext * 2048:ext * 2048 + size]
            if data[:2] == b'MZ':
                open('vmlinuz64', 'wb').write(data)
                print(f'vmlinuz64: lba {ext} size {size}')
                break
