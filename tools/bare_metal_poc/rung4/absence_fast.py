"""Fast absence probe: instead of 65520 x bytes.find over a 64KB region
(O(N*M) ~ 4G byte comparisons, minutes), note that a 16-byte window of
s2 can only appear contiguously in the medium if the de-interleave maps
16 CONSECUTIVE payload bytes to 16 consecutive medium bytes. Under the
documented layout (byte i -> 512 + (i%4)*PLANE + i//4), consecutive
payload bytes i, i+1 map to medium positions differing by PLANE except
every 4th step (-3*PLANE+1). So a contiguous 16-byte run can only occur
across a plane boundary, i.e. it must consist of the LAST j bytes of one
plane's slot range + first 16-j of the next. Exhaustive but O(64KB) check:
directly test the only 16-byte medium-aligned candidates is wrong; instead
just verify: for the contiguous claim to be FALSE we need no 16-byte
payload window == any 16-byte medium window. Equivalent fast formulation:
build the set of 16-grams of the region ONCE via a rolling hash
(Python bytes.find per window is the slow part), then check membership.
Use a dict of 8-gram -> positions? Memory heavy. Simpler: the region is
only 64KB: 65536-15 = 65521 medium windows. Payload has 65521 windows.
Exact all-pairs = 4G comparisons. Use bytes.find but with a FIRST-Byte
pre-filter table: count region byte frequencies; still O(N*M).
Practical fast approach: use hashlib + set of md5 of medium windows
(65521 hashes, ~0.2s), then for each payload window compute md5 and
check membership (65521 hashes). Exact (collision negligible but assert
by byte compare on hit).
"""
import hashlib, time
t0 = time.time()
med = open("rung4_medium.raw", "rb").read(512 + 65536)
s2 = open("payload_host.bin", "rb").read()
region = med[512:512 + 65536]
mw = {}
for i in range(len(region) - 15):
    w = region[i:i+16]
    mw.setdefault(hashlib.md5(w).digest(), []).append(i)
print("medium windows indexed: %d in %.1fs" % (sum(len(v) for v in mw.values()), time.time()-t0))
leaks = []
for i in range(len(s2) - 15):
    w = s2[i:i+16]
    hits = mw.get(hashlib.md5(w).digest())
    if hits:
        for h in hits:
            if region[h:h+16] == w:
                leaks.append((i, h))
print("leaks:", leaks[:5], "count", len(leaks), "elapsed %.1fs" % (time.time()-t0))
