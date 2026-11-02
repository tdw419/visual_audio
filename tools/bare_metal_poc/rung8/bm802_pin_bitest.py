#!/usr/bin/env python3
"""Does BM802's new stage1 pin actually bite?

The selftest going green proves the assembled stage1 matches the pin; it does
not prove the assert would fire if the bytes moved. So: build once for real,
then re-run the same build with the pin replaced by a wrong value. If nothing
raises, the check is decoration and this file says so.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bm802_fixture as fx  # noqa: E402

rig = fx.Rig()
rig.build(None, '/tmp/bm802_rig/bitest.raw')
print(f'  clean build ok against the pin {fx.STAGE1_SHA[:16]}...')

real = fx.STAGE1_SHA
fx.STAGE1_SHA = 'aa' * 32
try:
    rig.build(None, '/tmp/bm802_rig/bitest.raw')
except AssertionError as e:
    print(f'  [BITES] moved pin -> AssertionError: {e}')
    sys.exit(0)
print('  [NO CHECK] a wrong pin passed the build: the assert is decoration')
sys.exit(1)
