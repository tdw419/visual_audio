#!/usr/bin/env python3
"""
Advanced Memory Access Diagnostic for Alpine Boot

Captures detailed memory access patterns at the stall point
to identify why the SUM fix didn't resolve the store fault.
"""

import subprocess
import json
import re
from pathlib import Path

PROJECT_ROOT = Path("/home/jericho/projects/zion/projects/visual_audio")

def analyze_memory_regions():
    """Analyze what memory regions exist and their properties"""
    
    print("🔬 MEMORY REGION ANALYSIS")
    print("=" * 70)
    
    # Look for kernel ELF file to understand memory layout
    kernel_files = list(PROJECT_ROOT.glob("**/alpine*kernel*elf*")) + list(PROJECT_ROOT.glob("**/Image*"))
    
    if kernel_files:
        print(f"✓ Found kernel image: {kernel_files[0]}")
        
        # Use readelf to analyze memory sections
        try:
            result = subprocess.run(
                ['readelf', '-l', '-S', str(kernel_files[0])],
                capture_output=True, text=True, timeout=30
            )
            
            print(f"\n📊 Memory Layout from ELF:")
            print("-" * 70)
            
            in_sections = False
            in_program_headers = False
            
            for line in result.stdout.split('\n'):
                if 'Program Headers:' in line:
                    in_program_headers = True
                    in_sections = False
                elif 'Section Headers:' in line:
                    in_sections = True
                    in_program_headers = False
                elif in_program_headers and ('LOAD' in line or line.strip().startswith('0x')):
                    print(f"  {line}")
                elif in_sections and any(sec in line for sec in ['.text', '.data', '.bss', '.rodata']):
                    print(f"  {line}")
                    
        except Exception as e:
            print(f"⚠️  Could not analyze ELF: {e}")
    
    else:
        print("⚠️  No kernel image found for analysis")

def examine_wgsl_memory_handling():
    """Examine how the WGSL shader handles memory operations"""
    
    wgsl_path = PROJECT_ROOT / "tools" / "SPATIAL_RV64I.wgsl"
    
    if not wgsl_path.exists():
        print(f"ERROR: WGSL shader not found")
        return
    
    with open(wgsl_path) as f:
        content = f.read()
    
    print(f"\n🔬 WGSL MEMORY HANDLING ANALYSIS")
    print("=" * 70)
    
    # Check for permission checking in different paths
    check_perm_calls = content.count('check_perm(')
    print(f"✓ check_perm() calls: {check_perm_calls}")
    
    # Find all places where need_write is used
    need_write_contexts = []
    lines = content.split('\n')
    
    for i, line in enumerate(lines):
        if 'need_write' in line and '//' not in line:
            context = lines[max(0, i-2):i+3]
            need_write_contexts.append((i+1, ''.join(context)))
    
    print(f"\n📝 need_write usage (found {len(need_write_contexts)} places):")
    
    for line_num, context in need_write_contexts[:5]:  # Show first 5
        print(f"  Line {line_num}:")
        for ctx_line in context.split('\n'):
            print(f"    {ctx_line}")
        print()
    
    # Check for store operation handlers
    store_patterns = [
        'STORE_BYTE',
        'STORE_HALF',
        'STORE_WORD', 
        'STORE_DWORD',
        'AMO',
        'LR',
        'SC'
    ]
    
    found_stores = []
    for pattern in store_patterns:
        if pattern in content:
            found_stores.append(pattern)
    
    print(f"📦 Store operation patterns found: {found_stores}")
    
    # Check for MMU store path
    mmu_store_paths = [
        'case 0x23:',  # SB
        'case 0x27:',  # SH  
        'case 0x2B:',  # SW
        'case 0x2F:',  # SD
        'case 0x2F:',  # Alternative SD
    ]
    
    print(f"\n🔍 Looking for store instruction cases...")
    
    for case_pattern in mmu_store_paths:
        pattern_matches = re.findall(case_pattern.replace(':', r':.*?(?=case 0x|fn |$)'), content, re.DOTALL)
        if pattern_matches:
            print(f"  ✓ Found: {case_pattern}")
            # Show first part of the handler
            first_line = pattern_matches[0][:200].replace('\n', ' ')
            print(f"    {first_line}...")
        else:
            print(f"  ⚠️  Not found: {case_pattern}")

def check_instruction_decode():
    """Check how instructions are decoded and executed"""
    
    wgsl_path = PROJECT_ROOT / "tools" / "SPATIAL_RV64I.wgsl"
    
    if not wgsl_path.exists():
        return
    
    with open(wgsl_path) as f:
        content = f.read()
    
    print(f"\n🔬 INSTRUCTION DECODE ANALYSIS")
    print("=" * 70)
    
    # Find the main decode function
    decode_func = re.search(r'fn decode_and_execute[^}]+\}', content, re.DOTALL)
    
    if decode_func:
        func_content = decode_func.group(0)
        print(f"✓ Found decode function ({len(func_content)} chars)")
        
        # Check for instruction type handling
        opcode_switches = func_content.count('switch (opcode)')
        print(f"✓ Opcode switches: {opcode_switches}")
        
        # Check for store instruction paths
        store_branches = func_content.count('case 0x2') + func_content.count('case 0x3')
        print(f"✓ Store instruction branches: {store_branches}")
        
    # Look for memory operation handling
    mem_ops = content.count('translate_address')
    print(f"✓ translate_address() calls: {mem_ops}")
    
    # Check for permission checking frequency
    perm_checks = content.count('check_perm')
    print(f"✓ Permission checks: {perm_checks}")

def diagnose_stall_address():
    """Try to identify what address is causing the stall"""
    
    state_file = PROJECT_ROOT / "alpine_boot_state.json"
    
    if not state_file.exists():
        print("⚠️  No state file available")
        return
    
    with open(state_file) as f:
        state = json.load(f)
    
    print(f"\n🎯 STALL ADDRESS DIAGNOSIS")
    print("=" * 70)
    
    stall_step = state['state']['stall_step']
    csr_state = state['state']['csr_state']
    
    print(f"Stall occurs at: {stall_step:,} steps")
    print(f"SATP: {csr_state['satp']}")
    print(f"Mode: M={csr_state['mcause']}, S={csr_state['scause']}")
    
    # Decode SATP to get page table base
    try:
        satp_value = int(csr_state['satp'], 16)
        ppn = satp_value & 0x003FFFFF
        
        print(f"\n🗂️  Page table base: 0x{ppn:08x}")
        print(f"  Physical address: 0x{ppn * 4096:010x}")
        
        # This is where the page table starts in physical memory
        # The fault is likely in accessing this page table or the pages it points to
        
        print(f"\n💡 Hypothesis:")
        print(f"  The fault may be in accessing the page table itself")
        print(f"  Check if page table memory is properly mapped")
        print(f"  Verify PTE chains don't point to invalid pages")
        
    except Exception as e:
        print(f"⚠️  Could not decode SATP: {e}")

def main():
    """Run comprehensive diagnostic"""
    
    analyze_memory_regions()
    examine_wgsl_memory_handling()
    check_instruction_decode()
    diagnose_stall_address()
    
    print(f"\n" + "=" * 70)
    print(f"📋 COMPREHENSIVE DIAGNOSTIC COMPLETE")
    print(f"=" * 70)
    
    print(f"\n🎯 Next Steps:")
    print(f"  1. Verify page table memory is accessible")
    print(f"  2. Check PTE chain validity at fault point")
    print(f"  3. Test if removing SUM check helps diagnose the issue")
    print(f"  4. Consider adding debug output for faulting addresses")

if __name__ == "__main__":
    main()