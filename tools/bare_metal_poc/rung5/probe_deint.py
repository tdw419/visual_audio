import json, zlib
meta = json.load(open('rung5_meta.json'))
base = meta['img2_base']
img2 = open('img2.bin','rb').read()
print("meta img2_crc32:", meta['img2_crc32'])
print("crc32(img2.bin):", '%08X' % (zlib.crc32(img2)&0xFFFFFFFF))
print("img2_base:", base, "img2_len:", meta['img2_len'])
med = open('rung5_medium.raw','rb').read()
planes = med[base:base+2048]
# hypothesis A (current asm deint): dst[4k+p] = src[p*512+k]
A = bytes(planes[p*512+k] for k in range(512) for p in range(4))
print("guest-deint (asm current):", '%08X' % (zlib.crc32(A)&0xFFFFFFFF))
# hypothesis B (per codec contract): out[p::4] = plane p
B = bytearray(2048)
for p in range(4):
    B[p::4] = planes[p*512:(p+1)*512]
print("codec deint (B):        ", '%08X' % (zlib.crc32(bytes(B))&0xFFFFFFFF))
print("A head:", A[:24])
print("B head:", bytes(B[:24]))
print("img2 head:", img2[:24])
print("crc raw window:        ", '%08X' % (zlib.crc32(planes)&0xFFFFFFFF))
