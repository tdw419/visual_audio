import json
meta = json.load(open('dbg_meta.json'))
base = meta['img2_base']
med = open('dbg_medium.raw','rb').read()
win = med[base:base+16]
print("medium[base:base+16]:", ' '.join('%02X'%b for b in win))
img2 = open('img2.bin','rb').read()
print("img2[0:16]:          ", ' '.join('%02X'%b for b in img2[:16]))
# observed from serial_dbg3.log
obs = bytes.fromhex('5235522D472EF92FBBBB6C3DCB4BD3CA')
print("observed :0:         ", ' '.join('%02X'%b for b in obs))
# candidate: guest read is fine but from a DIFFERENT base?
# search the medium for the observed byte string
idx = med.find(obs)
print("observed string found at medium offset:", idx, "(LBA", idx//512, ") expected base:", base)
# also: what arrangement is it? print medium around any hit
if idx >= 0:
    print("context:", ' '.join('%02X'%b for b in med[idx-8:idx+24]))
# candidate 2: stride-4 groups of 2
c2 = bytearray()
for k in range(8):
    c2 += med[base+4*k:base+4*k+2]
print("stride-4x2 candidate:", ' '.join('%02X'%b for b in c2))
# what is at LBA 129 in various encodings — check png-based re-derivation not needed
