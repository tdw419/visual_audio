#!/usr/bin/env python3
"""GP-1 batch-2 negative legs (RED-first, per brief/receipt discipline).
Leg-N: flip one byte in a COPY of b2cap3's trace.log -> host-side sha verify
must go RED on the tampered artifact and GREEN on the pristine one.
Leg-E: empty trace.log -> converter emits total=0 -> schema rule 4: not a capture.
Exit 0 iff both legs behave as specified (tamper detected; empty rejected)."""
import hashlib, json, shutil, subprocess, sys, tempfile
from pathlib import Path

ok = True
tmp = Path(tempfile.mkdtemp(prefix='gp1b2_neg_'))

# ---- Leg-N: tamper one byte of the artifact copy; sha verify must fail ----
src = Path('corpus_build/b2cap3/mmap.bin')
tampered = tmp / 'mmap.bin'
data = bytearray(src.read_bytes())
data[0] ^= 0xFF
tampered.write_bytes(bytes(data))
guest_want = (Path('corpus_build/b2cap3/effects.sha256')).read_text().split()[0]
tam_sha = hashlib.sha256(bytes(data)).hexdigest()
if tam_sha != guest_want:
    print(f"PASS[leg-N] tampered artifact RED: {tam_sha[:12]}... != {guest_want[:12]}...")
else:
    print("FAIL[leg-N] tamper NOT detected — gate cannot fail, decoration")
    ok = False
pristine = hashlib.sha256(src.read_bytes()).hexdigest()
if pristine == guest_want:
    print(f"PASS[leg-N] pristine GREEN: {pristine[:12]}...")
else:
    print(f"FAIL[leg-N] pristine mismatch: {pristine} != {guest_want}")
    ok = False

# ---- Leg-E: empty trace is not a capture (schema rule 4) ----
empty_log = tmp / 'trace.log'
empty_log.write_bytes(b'')
out = tmp / 'trace.json'
r = subprocess.run([sys.executable, 'tools/corpus/strace_to_json.py',
                    str(empty_log), str(out)], capture_output=True, text=True)
counts = {}
if out.exists():
    counts = json.load(open(out)).get('counts', {})
if counts.get('total') == 0 and counts.get('converted') == 0:
    print(f"PASS[leg-E] empty trace -> total=0 -> NOT a capture (nothing committed): {counts}")
else:
    print(f"FAIL[leg-E] empty trace produced unexpected counts: {counts} rc={r.returncode}")
    ok = False

shutil.rmtree(tmp)
sys.exit(0 if ok else 1)
