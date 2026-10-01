"""BM902 scratch probe 3: verify kernel-baked byte identity.

Splits the zeropage into the regions that matter for stage2 construction:
  [0x1f1, 0x268) — protocol header fields: zp should be file-identical
                   EXCEPT loader-owned offsets (0x1ef/0x1f0 suffix bytes,
                   loader fields 0x210/0x211/0x224/0x228ff/ramdisk) and
                   root_dev 0x1fc/0x1fd (file 0, loader set 0x0200).
  [0x268, 0x2d0) — the file's real-mode setup CODE bytes (copied to
                   0x10000-ish by the loader); zeropage region is zero.
"""
import struct

zp = open('oracle_zp_leg0.bin', 'rb').read()
img = open('vmlinuz64.extracted', 'rb').read()

LOADER_OWNED = set()
for lo, hi in [(0x1ef, 0x1f1), (0x1fc, 0x1fe), (0x210, 0x212),
               (0x218, 0x220), (0x224, 0x226), (0x228, 0x22c)]:
    LOADER_OWNED.update(range(lo, hi))

band = range(0x1f1, 0x268)
diffs = [i for i in band if zp[i] != img[i]]
unexcused = [i for i in diffs if i not in LOADER_OWNED]
print('header band [0x1f1,0x268):', len(band), 'bytes;',
      len(diffs), 'diff, unexcused:', [hex(i) for i in unexcused])
assert not unexcused, 'kernel-baked region NOT byte-identical to file!'

tail = range(0x268, 0x2d0)
nz = [i for i in tail if zp[i]]
print('tail band [0x268,0x2d0): nonzero zp bytes:',
      [hex(i) for i in nz[:10]] if nz else 'none (file setup code not in zp)')
