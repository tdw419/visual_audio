#!/usr/bin/env python3
"""
Debug parser - understand QEMU trace format
"""

import re

with open('/tmp/qemu_cpu_trace.log', 'r') as f:
    content = f.read()

# Split by ----------------
blocks = content.split('----------------')

print(f"Found {len(blocks)} blocks")

# Look at first complete block
for i, block in enumerate(blocks[:3]):
    lines = [l for l in block.strip().split('\n') if l.strip()]
    if len(lines) < 5:
        continue
    
    print(f"\n=== Block {i} ({len(lines)} lines) ===")
    for line in lines[:15]:
        print(repr(line))
        # Try to match disassembly
        m = re.match(r'^\s*(0x[0-9a-f]+):\s+([0-9a-f]+)\s+(.+)$', line)
        if m:
            print(f"  -> PC={m.group(1)}, bytes={m.group(2)}, instr={m.group(3)[:40]}")
            continue
        
        # Try to match register
        m2 = re.match(r'^\s*([a-z0-9_/]+)\s+(0x[0-9a-f]+)', line)
        if m2:
            print(f"  -> REG={m2.group(1).split('/')[0]} = {m2.group(2)}")