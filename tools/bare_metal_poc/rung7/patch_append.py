#!/usr/bin/env python3
"""Patch the isolinux.cfg text block inside TinyCore-1.iso, in place:
  - every APPEND line gains ' console=ttyS0'
  - TIMEOUT 600 -> TIMEOUT 060 (60 deciseconds: faster unattended boot)

Length-preserving strategy: the config text block is followed by a run of
NUL padding. Rebuild the block (text grows by 4*14 + 0 bytes) and shrink the
NUL padding by exactly the same amount, so the total span length is constant
and every byte offset AFTER the span is unchanged (ISO9660 extents stay
valid). Aborts loudly if the padding slack is insufficient.
"""
import hashlib
import re
import sys

p = sys.argv[1] if len(sys.argv) > 1 else 'TinyCore-1.iso'
d = bytearray(open(p, 'rb').read())
orig_len = len(d)
orig_sha = hashlib.sha256(d).hexdigest()

start = d.find(b'DEFAULT tc')
assert start != -1, 'config block not found'

# end of config text = end of last APPEND line within the block
last_app = None
for m in re.finditer(rb'APPEND[^\n]*\n', bytes(d[start:start + 4096])):
    last_app = m
assert last_app, 'no APPEND lines found'
text_end = start + last_app.end()

# measure the NUL padding run after the text
n = 0
while d[text_end + n] == 0:
    n += 1
    if n > 65536:
        break

ADD = b' console=ttyS0'
growth = 0
block = bytearray()
i = start
while i < text_end:
    j = d.find(b'APPEND ', i, text_end)
    if j == -1:
        block += d[i:text_end]
        break
    k = d.find(b'\n', j, text_end)
    line = bytes(d[j:k + 1])
    if b'console=ttyS0' in line:
        block += d[i:k + 1]
    else:
        block += d[i:j] + line[:-1] + ADD + b'\n'
        growth += len(ADD)
    i = k + 1

# TIMEOUT 600 -> 060 (same length)
t = bytes(block).find(b'TIMEOUT 600')
if t != -1:
    block[t + len('TIMEOUT ')] = ord('0')

new_nul = n - growth
assert new_nul >= 0, f'insufficient NUL slack: padding={n}, growth={growth}'

out = bytearray(d[:start]) + block + b'\x00' * new_nul + bytearray(d[text_end + n:])
assert len(out) == orig_len, (len(out), orig_len)
open(p, 'wb').write(out)
print('APPEND lines patched: 4 expected; growth =', growth,
      '; NUL padding was', n, '-> now', new_nul)
print('size unchanged:', len(out) == orig_len)
print('new sha256:', hashlib.sha256(out).hexdigest())
print('orig sha256:', orig_sha)
