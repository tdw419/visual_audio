#!/usr/bin/env python3
"""
Final V2 completion: write_mem_bytes from v1 → v2
"""

# Read v1 write_mem_bytes implementation
with open('tools/spatial_rv64i_cpu.py', 'r') as f:
    v1_lines = f.readlines()

# Extract write_mem_bytes method (lines 560-597)
write_mem_bytes_impl = ''.join(v1_lines[559:597])

# Read v2
with open('emulator/v2/spatial_rv64i_v2.py', 'r') as f:
    v2_content = f.read()

# Replace the stub with the full implementation
stub = '''    def write_mem_bytes(self, byte_addr: int, data: bytes):
        """Write bytes to memory (same as v1, uses V2 Hilbert LUT)."""
        # TODO: Port the LUT-scatter write path from v1
        # This is the critical fix from commit 76e102b
        raise NotImplementedError("V2 needs LUT-scatter write path from v1")'''

v2_content = v2_content.replace(stub, write_mem_bytes_impl + '\n')

# Write back
with open('emulator/v2/spatial_rv64i_v2.py', 'w') as f:
    f.write(v2_content)

print("✓ write_mem_bytes ported from v1 to v2")