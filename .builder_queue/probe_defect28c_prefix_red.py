#!/usr/bin/env python3
"""DEFECT-28 file (2) — orchestrator's own prefix-RED probe.

Loads the PRE-FIX decoder (git HEAD:tools/vcc_validate.py) as module `vcc_validate`
and shows the original substantive failure: a container written by the live
converter (3 bytes/pixel) cannot be decoded by the VCC decoder.
"""
import importlib.util, os, subprocess, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'tools'))
root = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
prefix_py = os.path.join(root, 'output', 'DEFECT28C_prefix_vcc_validate.py')
blob = subprocess.run(['git', 'show', 'HEAD:tools/vcc_validate.py'], cwd=root,
                      capture_output=True, text=True, check=True).stdout
open(prefix_py, 'w').write(blob)
print('prefix decoder written to', prefix_py, 'sha256', __import__('hashlib').sha256(blob.encode()).hexdigest()[:16])

spec = importlib.util.spec_from_file_location('vcc_validate_prefix', prefix_py)
pre = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pre)
print('prefix module has encode_rts_png:', hasattr(pre, 'encode_rts_png'))

import pixelrts_v2_converter as conv
data = bytes(range(256))
with tempfile.NamedTemporaryFile(mode='wb', delete=False) as t:
    t.write(data); t.flush(); inp = t.name
outp = inp + '.rts.png'
conv.convert_to_rts_png(inp, outp, grid_size=256)
try:
    got = pre.decode_rts_png(outp, grid_size=256)
    print('PREFIX DECODE RETURNED len=%d -> NOT RED' % len(got))
except Exception as e:
    print('PREFIX RED: %s: %s' % (type(e).__name__, e))
os.unlink(inp); os.unlink(outp)
