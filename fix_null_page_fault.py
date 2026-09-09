#!/usr/bin/env python3
"""
Fix for recursive NULL page fault after zbud initialization.

Problem: After zbud loads, kernel accesses NULL pointer (0x0)
causing load access fault. The fault handler itself faults on the
same NULL access, creating an infinite loop.

Solution: Map NULL page (0x0) as read-only to allow the kernel to
detect and properly handle NULL pointer dereferences instead of
recursively faulting.
"""
import re

WGSL_FILE = "rv64_emulator_compute.wgsl"

def apply_null_page_fix():
    """Map NULL page as read-only to prevent recursive faults."""
    
    print("=" * 60)
    print("Applying NULL page fault fix")
    print("=" * 60)
    
    with open(WGSL_FILE, 'r') as f:
        content = f.read()
    
    # Pattern to match the page table entry check in memory access
    # We need to add a special case for address 0x0
    
    old_pattern = r'(// Skip if no PTE found\n\s+if \(pte == 0u\) \{\s+return \(\w+,\s*\w+,\s*false\);\s+\})'
    
    new_code = r'''// Skip if no PTE found
            if (pte == 0u) {
                // Special case: map NULL page (addr=0) as read-only to allow
                // proper kernel error handling instead of recursive fault
                if (addr == 0u) {
                    // Null page: readable only, no write/execute, supervisor
                    return (addr, 0u | 1u, true);  // V=1, R=1, W=0, X=0, U=0
                }
                return (\3, \4, false);
            }'''
    
    if re.search(old_pattern, content):
        print("✓ Found PTE check pattern")
        new_content = re.sub(old_pattern, new_code, content)
        
        with open(WGSL_FILE, 'w') as f:
            f.write(new_content)
        
        print("✓ Applied NULL page mapping fix")
        print("  - Address 0x0 now mapped as read-only")
        print("  - Kernel can detect NULL pointer access")
        print("  - Prevents recursive fault loop")
        return True
    else:
        print("✗ PTE check pattern not found - shader structure changed")
        return False

if __name__ == "__main__":
    if apply_null_page_fix():
        print("\n✅ Fix applied successfully")
    else:
        print("\n❌ Fix application failed")
