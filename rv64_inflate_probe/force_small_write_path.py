#!/usr/bin/env python3
"""
Temporary workaround: force write_mem_bytes to use small-write path.
This avoids the synchronization bug in the chunked path.

After applying this patch, all writes will use write_mem_word in a loop,
which is slower but correct.
"""

# Read the original file
with open('/home/jericho/projects/zion/projects/visual_audio/.worktrees/rv64i-finish-1787713474/tools/spatial_rv64i_cpu.py', 'r') as f:
    content = f.read()

# The line to change: 16384 (64KB threshold) → 0xFFFFFFFF (force small path)
old_line = "        if len(words) < 16384:  # 64KB"
new_line = "        if len(words) < 0xFFFFFFFF:  # TEMP WORKAROUND: force small-write path (see CORRUPTION_FIX_SPEC.md)"

if old_line in content:
    patched = content.replace(old_line, new_line)

    # Write patched version
    with open('/home/jericho/projects/zion/projects/visual_audio/.worktrees/rv64i-finish-1787713474/tools/spatial_rv64i_cpu.py', 'w') as f:
        f.write(patched)

    print("✓ Patched write_mem_bytes to force small-write path")
    print("  Changed threshold from 16384 to 0xFFFFFFFF")
    print("  This is slow but correct. Apply proper sync fence for permanent fix.")
else:
    print("✗ Line not found - already patched or code changed")
    print(f"  Looking for: {old_line}")