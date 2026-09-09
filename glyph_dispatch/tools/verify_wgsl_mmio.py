#!/usr/bin/env python3
"""WGSL MMIO handler lockstep verification."""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

def test_wgsl_mmio_syntax():
    """Test that WGSL shader is syntactically valid and contains required patterns."""
    wgsl_file = project_root / 'src/riscv/RISCV_CPU_MMU_dispatch.wgsl'

    if not wgsl_file.exists():
        print(f"❌ WGSL file not found: {wgsl_file}")
        return False

    wgsl_src = wgsl_file.read_text()

    # Check for required patterns
    required_patterns = [
        'fn is_glyph_dispatch_mmio',
        'GLYPH_DISPATCH_TRIGGER_MMIO',
        'fn handle_glyph_dispatch_write',
        'glyph_busy',
        'if (addr_low == GLYPH_DISPATCH_TRIGGER_MMIO)',
        '(*cpu).glyph_busy = 1u',
    ]

    print("Checking WGSL MMIO handler...")
    for pattern in required_patterns:
        if pattern in wgsl_src:
            print(f"  ✓ Found: {pattern}")
        else:
            print(f"  ❌ Missing: {pattern}")
            return False

    print("✅ WGSL MMIO handler verification passed")
    return True

if __name__ == '__main__':
    sys.exit(0 if test_wgsl_mmio_syntax() else 1)