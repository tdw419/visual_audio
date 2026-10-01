#!/usr/bin/env python3
"""Quick inspect: bytes following each APPEND line in the ISO."""
import re

d = open('TinyCore-current.iso', 'rb').read()
for m in re.finditer(rb'APPEND[^\n]*\n', d):
    j = m.end()
    print(len(m.group()), repr(m.group()), '->', repr(d[j:j + 14]))
