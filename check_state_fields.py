#!/usr/bin/env python3
"""
Quick check of available state fields
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'tools'))

from spatial_rv64i_cpu import SpatialRV64ICore
from standalone_alpine_boot_quick import load_opensbi_alpine_and_dtb

print("Initializing core...")
core = SpatialRV64ICore(64 * 1024 * 1024)
dtb_addr = load_opensbi_alpine_and_dtb(core)
core.write_register(10, 0)
core.write_register(11, dtb_addr)

print("Running 1000 steps...")
core.step(steps=1000)

state = core.get_state()
print("\nState fields:")
for key in sorted(state.keys()):
    print(f"  {key}: {state[key]}")