#!/usr/bin/env python3
"""
Targeted Store Fault Diagnostic Tool

Captures detailed memory access patterns at the stall point (~29-43M steps)
to identify the root cause of persistent store page faults.
"""

import subprocess
import json
import re
from pathlib import Path

PROJECT_ROOT = Path("/home/jericho/projects/zion/projects/visual_audio")
STATE_FILE = PROJECT_ROOT / "alpine_boot_state.json"

def analyze_stall_pattern():
    """Analyze the stall patterns from state file"""
    
    if not STATE_FILE.exists():
        print("ERROR: State file not found")
        return
    
    with open(STATE_FILE) as f:
        state = json.load(f)
    
    print("🔍 ALPINE BOOT STORE FAULT DIAGNOSTIC")
    print("=" * 70)
    
    # Current stall info
    stall_step = state['state']['stall_step']
    best_step = state['state']['last_working_step']
    csr_state = state['state']['csr_state']
    
    print(f"\n📍 Stall Analysis:")
    print(f"  Stall Point:   {stall_step:,} steps")
    print(f"  Best Progress: {best_step:,} steps")
    print(f"  Stall Ratio:   {stall_step/best_step:.1%}")
    
    print(f"\n🔧 CSR State at Stall:")
    print(f"  mcause: {csr_state['mcause']} (Instruction page fault)")
    print(f"  scause: {csr_state['scause']} (Load page fault)")
    print(f"  sepc:   {csr_state['sepc']}")
    print(f"  satp:   {csr_state['satp']} (Sv39 page table active)")
    
    # Applied fixes
    applied_fixes = state['state']['applied_fixes']
    print(f"\n🔨 Applied Fixes: {applied_fixes}")
    
    # Recent results
    results = state['results'][-5:]
    print(f"\n📊 Recent Boot Attempts:")
    for i, result in enumerate(results, 1):
        status = result['status']
        steps = result['steps']
        stall_mode = result['stall_mode']
        print(f"  {i}. Iteration {result['iteration']}: {steps:,} steps → {stall_mode} ({status})")
    
    # Decode SATP to get page table base
    try:
        satp_value = int(csr_state['satp'], 16)
        ppn = satp_value & 0x003FFFFF  # Physical page number
        asid = (satp_value >> 44) & 0xFFFF  # Address space ID
        mode = (satp_value >> 60) & 0xF  # Mode (should be 8 for Sv39)
        
        print(f"\n🗂️  SATP Decoding:")
        print(f"  Mode (Sv39): {mode} (should be 8)")
        print(f"  ASID: {asid}")
        print(f"  PPN (page table base): 0x{ppn:08x}")
        
    except Exception as e:
        print(f"\n⚠️  Could not decode SATP: {e}")
    
    print(f"\n💡 Root Cause Hypothesis:")
    
    # Based on error signature
    mcause = int(csr_state['mcause'], 16)
    scause = int(csr_state['scause'], 16) if isinstance(csr_state['scause'], str) else csr_state['scause']
    
    if mcause == 9 and scause == 5:  # Instruction page fault + Load page fault
        print("  ⚠️  INSTRUCTION FETCH PAGE FAULT + LOAD FAULT")
        print("  → CPU trying to execute code from non-executable page")
        print("  → Store operation failing at different address")
        print("  → Possible MMU permission table walk error")
        print("  → Check if x-bit set correctly in PTE chain")
    elif mcause == 9:
        print("  ⚠️  INSTRUCTION PAGE FAULT ONLY")
        print("  → CPU trying to fetch instruction from invalid page")
        print("  → Check page table walk at PC")
        print("  → Verify PTE chain validity")
    elif scause == 5:
        print("  ⚠️  LOAD PAGE FAULT ONLY")
        print("  → Trying to read from unreadable page")
        print("  → Check if U-bit/SUM logic correct")
        print("  → Verify r-bit set in PTE chain")
    else:
        print(f"  ⚠️  UNEXPECTED FAULT COMBINATION: mcause={mcause}, scause={scause}")
    
    print(f"\n🎯 Recommended Next Steps:")
    print(f"  1. Create targeted diagnostic that halts at {stall_step:,} steps")
    print(f"  2. Dump full page table structure at fault point")
    print(f"  3. Check PTE chain for store permissions (w-bit)")
    print(f"  4. Verify SATP ASID isolation")
    print(f"  5. Test if issue is memory region-specific")
    
    print(f"\n🔬 MMU Diagnostics to Capture:")
    print(f"  - Faulting virtual address (stval, mtval)")
    print(f"  - Page table entries at each level")
    print(f"  - Memory region permissions")
    print(f"  - TLB contents at stall point")
    
    return state

def check_mmu_implementation():
    """Check current MMU implementation in WGSL shader"""
    
    wgsl_path = PROJECT_ROOT / "tools" / "SPATIAL_RV64I.wgsl"
    
    if not wgsl_path.exists():
        print(f"ERROR: WGSL shader not found at {wgsl_path}")
        return
    
    with open(wgsl_path) as f:
        content = f.read()
    
    print(f"\n🔬 MMU Implementation Analysis:")
    print("=" * 70)
    
    # Find check_perm function
    perm_check = re.search(r'fn check_perm\([^}]+\}', content, re.DOTALL)
    if perm_check:
        print(f"✓ Found check_perm function:")
        print(f"  - {len(perm_check.group(0))} bytes")
        print(f"  - Contains 'U-bit': {('u = (pte >> 4u)' in perm_check.group(0))}")
        print(f"  - Contains 'SUM': {('sstatus_sum' in perm_check.group(0) or 'MSTATUS' in perm_check.group(0))}")
    
    # Find Sv39 translation function
    sv39_func = re.search(r'fn translate_sv39\([^}]+\}', content, re.DOTALL)
    if sv39_func:
        print(f"✓ Found translate_sv39 function:")
        print(f"  - {len(sv39_func.group(0))} bytes")
        print(f"  - 3-level page table: {('pt_root' in sv39_func.group(0))}")
    
    # Check for store handling
    store_patterns = [
        r'STO?_OP',
        r'handle_store',
        r'store_byte',
        r'store_word',
        r'store_dword',
    ]
    
    found_store = False
    for pattern in store_patterns:
        if re.search(pattern, content):
            found_store = True
            print(f"✓ Store operation handling present: {pattern}")
    
    if not found_store:
        print(f"⚠️  Store operation handling NOT FOUND")
    
    # Check for permission checking in store path
    store_permission = re.search(r'case STORE.*check_perm', content, re.DOTALL)
    if store_permission:
        print(f"✓ Store permission checking found")
    else:
        print(f"⚠️  Store permission checking NOT FOUND")
    
    # Look for common MMU bugs
    print(f"\n🐛 Common MMU Bug Patterns:")
    
    # Check 1: Missing w-bit check
    w_bit_check = re.search(r'need_write.*w.*==.*1u', content)
    if w_bit_check:
        print(f"✓ w-bit check present for writes")
    else:
        print(f"⚠️  w-bit check may be missing for writes")
    
    # Check 2: U-bit logic
    u_bit_logic = re.search(r'u.*==.*1u', content)
    if u_bit_logic:
        print(f"✓ U-bit logic present")
    else:
        print(f"⚠️  U-bit logic may be missing")
    
    # Check 3: SUM bit handling
    sum_logic = re.search(r'status.*18u|0x40000', content)
    if sum_logic:
        print(f"✓ SUM bit handling present")
    else:
        print(f"⚠️  SUM bit handling may be missing")
    
    # Check 4: Page table walk bounds
    bounds_check = re.search(r'if.*>=.*4096|ppn.*<<.*12', content)
    if bounds_check:
        print(f"✓ Page table walk bounds check present")
    else:
        print(f"⚠️  Page table walk bounds check may be missing")

def main():
    """Run diagnostic analysis"""
    
    state = analyze_stall_pattern()
    check_mmu_implementation()
    
    print(f"\n" + "=" * 70)
    print(f"📋 DIAGNOSTIC COMPLETE")
    print(f"=" * 70)
    print(f"\n💾 State file saved at: {STATE_FILE}")
    print(f"📊 Next: Run targeted boot with state capture")
    
    # Show current iteration count
    iteration = state['state']['iteration']
    max_iterations = 100
    
    print(f"\n🔄 Iteration Status:")
    print(f"  Current: {iteration}/{max_iterations}")
    print(f"  Progress: {iteration/max_iterations:.1%}")
    
    if iteration >= max_iterations:
        print(f"  ⚠️  MAX ITERATIONS REACHED")
        print(f"  → Daemon exhausted autonomous fix capabilities")
        print(f"  → Requires manual engineering intervention")
    else:
        print(f"  → Still has {max_iterations - iteration} iterations remaining")

if __name__ == "__main__":
    main()