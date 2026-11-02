#!/usr/bin/env python3
"""
Manual port: write_mem_bytes() from v1 to v2

This script ports the LUT-scatter write_mem_bytes implementation from
tools/spatial_rv64i_cpu.py to emulator/v2/spatial_rv64i_v2.py.
"""

import sys
sys.path.insert(0, 'tools')

# Read v1 to extract write_mem_bytes
with open('tools/spatial_rv64i_cpu.py', 'r') as f:
    v1_content = f.read()

# Find write_mem_bytes method
import re
match = re.search(r'def write_mem_bytes\(self, byte_addr: int, data: bytes).*?(?=\n    def |\n\nclass )', v1_content, re.DOTALL)
if not match:
    print('ERROR: Could not find write_mem_bytes in v1')
    sys.exit(1)

write_mem_bytes_code = match.group(0)
print(f'Found write_mem_bytes in v1 ({len(write_mem_bytes_code)} chars)')

# Read v2
with open('emulator/v2/spatial_rv64i_v2.py', 'r') as f:
    v2_content = f.read()

# Replace the stub write_mem_bytes with the v1 implementation
stub_pattern = r'def write_mem_bytes\(self.*?raise NotImplementedError.*?\n'
v2_updated = re.sub(stub_pattern, write_mem_bytes_code + '\n', v2_content, flags=re.DOTALL)

# Write back
with open('emulator/v2/spatial_rv64i_v2.py', 'w') as f:
    f.write(v2_updated)

print('write_mem_bytes ported to v2')

# Verify
with open('emulator/v2/spatial_rv64i_v2.py', 'r') as f:
    v2_final = f.read()

if 'raise NotImplementedError' in v2_final and 'write_mem_bytes' in v2_final:
    print('ERROR: write_mem_bytes still has stub')
    sys.exit(1)

if '_get_hilbert_lut' in v2_final or 'hilbert_lut' in v2_final:
    print('PASS: write_mem_bytes has LUT implementation')
else:
    print('ERROR: write_mem_bytes missing LUT implementation')
    sys.exit(1)