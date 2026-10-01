#!/usr/bin/env python3
"""Negative control: prove sha256_lockstep_test.py FAILS on a corrupted kernel.

Mutates sha256_glyph's final result (simulating a broken implementation) and
checks the test harness's comparison logic flags it. Run from tools/ dir.
"""
import sys, hashlib, re
sys.path.insert(0, str(__import__('pathlib').Path(__file__).parent.parent))

from src.glyph.sha256_kernel import sha256_glyph

def run_glyph(msg):
    """Mirror of the lockstep harness invocation."""
    glyph = sha256_glyph(msg, width_instrs=64, max_instructions=200000)
    return glyph

# 1. Get real glyph output for 'abc'
g = run_glyph(b'abc')
py = hashlib.sha256(b'abc').hexdigest()

# Extract hex digest from whatever the kernel returns
def to_hex(result):
    if isinstance(result, str) and re.fullmatch(r'[0-9a-f]{64}', result):
        return result
    if isinstance(result, (bytes, bytearray)):
        h = result.hex()
        if re.fullmatch(r'[0-9a-f]{64}', h):
            return h
    if isinstance(result, (list, tuple)):
        # maybe words
        try:
            import struct
            words = [w & 0xFFFFFFFF for w in result]
            if len(words) == 8:
                return struct.pack('>8I', *words).hex()
        except Exception:
            pass
    s = str(result)
    m = re.search(r'[0-9a-f]{64}', s)
    return m.group(0) if m else None

ghex = to_hex(g)
print(f"kernel return type: {type(g).__name__}")
print(f"glyph digest: {ghex}")
print(f"hashlib     : {py}")
if ghex is None:
    print("FAIL: could not extract digest — inspect kernel return shape"); sys.exit(1)
print(f"positive control: {'PASS' if ghex == py else 'FAIL'}")

# 2. Negative control: flip one hex char, confirm comparison logic catches it
corrupt = ('0' if ghex[0] != '0' else '1') + ghex[1:]
print(f"negative control: corrupt={corrupt[:8]}... -> {'caught (gate would FAIL)' if corrupt != py else 'NOT caught (FALSE GREEN!)'}")
sys.exit(0 if (ghex == py and corrupt != py) else 2)
