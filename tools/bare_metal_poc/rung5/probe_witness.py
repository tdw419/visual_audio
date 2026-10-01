import json, zlib

# 1) does crc32(raw planes window of the CURRENT medium) == E9565C96?
meta = json.load(open('rung5_meta.json'))
base = meta['img2_base']
med = open('rung5_medium.raw','rb').read()
raw = med[base:base+2048]
print("crc32(raw window):", '%08X' % (zlib.crc32(raw)&0xFFFFFFFF), "(guest printed E9565C96)")
print("plain sum16(raw):", '%04X' % (sum(raw)&0xFFFF))

# 2) guest checksum function emulation: word walk, little-endian,
#    bl += low (carry->bh), bl += high (carry->bh)
def weird_sum(data):
    bl = bh = 0
    for i in range(0, len(data), 2):
        lo, hi = data[i], data[i+1]
        bl += lo
        c1 = bl >> 8; bl &= 0xFF
        bh = (bh + c1) & 0xFF
        bl += hi
        c2 = bl >> 8; bl &= 0xFF
        bh = (bh + c2) & 0xFF
    return (bh << 8) | bl

img2 = open('img2.bin','rb').read()
print("weird_sum(img2.bin):", '%04X' % weird_sum(img2), "(guest printed 4DCD in run 3)")
print("weird_sum(raw):     ", '%04X' % weird_sum(raw), "(guest printed 5490 in run 2 over :0)")

# 3) sanity: does the codec's stage2 SUM print use this same function?
s2 = open('stage2.bin','rb').read()
print("weird_sum(stage2.bin[0:2048]):", '%04X' % weird_sum(s2[:2048]), " full:", '%04X' % weird_sum(s2))
