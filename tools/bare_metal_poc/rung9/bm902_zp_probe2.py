"""BM902 scratch probe 2: kernel-baked fields — zeropage vs bzImage bytes.

Checks that the oracle zeropage's protocol fields (0x1f1..0x270) match the
bzImage file's own header bytes, so stage2 knows which fields it must copy
from the image vs set itself.
"""
import struct

zp = open('oracle_zp_leg0.bin', 'rb').read()
img = open('vmlinuz64.extracted', 'rb').read()
print('img size', len(img), 'setup_sects in img', img[0x1f1])
print('file header', img[0x202:0x206])
match = sum(1 for i in range(0x1f1, 0x270) if zp[i] == img[i])
print('zp vs file bytes equal in [0x1f1,0x270):', match, 'of', 0x270 - 0x1f1)
diffs = [(hex(i), hex(zp[i]), hex(img[i]))
         for i in range(0x1f1, 0x270) if zp[i] != img[i]]
print('diffs:', diffs[:40])
syssize = struct.unpack_from('<I', zp, 0x1f4)[0]
print('syssize paras', hex(syssize), 'bytes', syssize * 16, 'img', len(img))
# does file syssize field agree?
print('file syssize', hex(struct.unpack_from('<I', img, 0x1f4)[0]))
