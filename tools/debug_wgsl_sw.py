#!/usr/bin/env python3
"""
Add debug output to WGSL to trace SW execution.
"""

import sys
from pathlib import Path

shader_path = Path('/home/jericho/projects/zion/projects/visual_audio/tools/RISCV_CPU_MMU.wgsl')
shader = shader_path.read_text()

# Add a debug counter to track SW calls
# We'll write to a specific memory address that we can check

# Find the write_phys_word function and add instrumentation
print("Current write_phys_word:")
print(shader[shader.find('fn write_phys_word'):shader.find('fn write_phys_word') + 500])
print("\nSearching for SW in execute_store...")

sw_pos = shader.find('fn execute_store')
if sw_pos >= 0:
    # Find the actual SW handling in execute_store
    sw_code = shader[sw_pos:sw_pos+2000]
    if 'SW' in sw_code:
        sw_start = sw_code.find('SW')
        sw_snippet = sw_code[max(0, sw_start-100):sw_start+300]
        print(f"\nSW handling code:\n{sw_snippet}")