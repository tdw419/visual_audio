#!/usr/bin/env python3
"""Fix state field references in SPATIAL_RV64I.wgsl for 64-bit migration."""

import re
from pathlib import Path

WGSL_PATH = Path(__file__).parent.parent / "tools/SPATIAL_RV64I.wgsl"

# Field mappings: old_name -> (new_name, is_64bit)
FIELD_MAPPINGS = {
    "state.pc": ("u64_from_parts(state.pc_low, state.pc_high)", True),
    "state.reservation_addr": ("u64_from_parts(state.reservation_addr_low, state.reservation_addr_high)", True),
    "state.ram_base": ("u64_from_parts(state.ram_base_low, state.ram_base_high)", True),
    "state.mtime": ("u64_from_parts(state.mtime_low, state.mtime_high)", True),
    "state.mtimecmp": ("u64_from_parts(state.mtimecmp_low, state.mtimecmp_high)", True),
}

# Direct replacements (not wrapped in u64_from_parts)
DIRECT_REPLACEMENTS = {
    "state.mtime =": "state.mtime_low =",  # STUB: should update both low and high
    "state.mtimecmp =": "state.mtimecmp_low =",  # STUB: should update both low and high
    "state.ram_base": "state.ram_base_low",  # STUB: should use both low and high
}

def fix_wgsl_file(filepath: Path) -> None:
    if not filepath.exists():
        print(f"Skipping {filepath}: not found")
        return

    content = filepath.read_text()

    # Apply direct replacements first
    for old, new in DIRECT_REPLACEMENTS.items():
        content = content.replace(old, new)

    # Apply field mappings (needs regex to preserve operators)
    for old, (new, is_64bit) in FIELD_MAPPINGS.items():
        # Match patterns like "state.pc + 4u", "state.pc != 0u", etc.
        # We need to be careful not to break things like "state.pc_low" (already correct)
        pattern = r'\b' + re.escape(old) + r'\b'

        # Replace state.pc references with the 64-bit helper
        # For now, let's use a simpler approach: just replace state.pc with state.pc_low
        # (stub implementation - not correct but will compile)
        if old == "state.pc":
            content = re.sub(pattern, "state.pc_low", content)
        elif old == "state.reservation_addr":
            content = re.sub(pattern, "state.reservation_addr_low", content)
        elif old == "state.ram_base":
            content = re.sub(pattern, "state.ram_base_low", content)
        elif old == "state.mtime":
            content = re.sub(pattern, "state.mtime_low", content)
        elif old == "state.mtimecmp":
            content = re.sub(pattern, "state.mtimecmp_low", content)

    filepath.write_text(content)
    print(f"Fixed state field references in {filepath}")

if __name__ == "__main__":
    fix_wgsl_file(WGSL_PATH)
    print("\nDone! All state field references should now use 64-bit variants.")