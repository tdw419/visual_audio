#!/usr/bin/env python3
"""
Summarize findings
"""

print("=" * 70)
print("RCU STALL ROOT CAUSE ANALYSIS")
print("=" * 70)
print()

print("OBSERVED SYMPTOM:")
print("  - Alpine boots but then stalls with RCU watchdog")
print("  - Timer fires 11.9M times but only 28.6K delivered (0.24%)")
print("  - SIE=0 (S-mode interrupts globally disabled)")
print()

print("ROOT CAUSE:")
print("  - Kernel is stuck in a store/AMO access fault loop")
print("  - Faulting address: 0xffffffc4febfe000 (vmalloc area)")
print("  - Level 2 PTE at 0x00080c06238 is ZERO")
print("  - Kernel's page table doesn't map this virtual address")
print()

print("WHY THE FAULT OCCURS:")
print("  - The kernel makes it past early boot (UART shows progress)")
print("  - It then tries to vmalloc() memory for kernel structures")
print("  - vmalloc() returns virtual addresses in 0xffffffc000000000+ range")
print("  - These addresses need page table mappings")
print("  - With only 64MB physical RAM, the kernel can't satisfy")
print("    the allocation OR can't expand the page table")
print()

print("WHY TIMER INTERRUPTS FAIL:")
print("  - Timer interrupts ARE being armed (57K SBI TIME ecalls)")
print("  - Timer DOES fire (11.9M fires)")
print("  - But SIE=0 prevents delivery")
print("  - SIE is disabled because the kernel is stuck in")
print("    the fault handler and never returns to sret")
print()

print("CONCLUSION:")
print("  The interrupt throttling is a SYMPTOM, not the cause.")
print("  The real issue: 64MB RAM is insufficient for Alpine.")
print()
print("  The kernel boots but hits memory constraints.")
print("  Once it faults, it never recovers, so interrupts")
print("  are never delivered (SIE never re-enabled).")
print()

print("FIX OPTIONS:")
print("  1. Increase RAM_SIZE in boot scripts (GPU buffer limit may require")
print("     indirect MMIO for large RAM regions)")
print("  2. Configure kernel to use less memory (bootargs mem=...)")
print("  3. Use a smaller kernel config (busybox-based distro)")
print()

print("=" * 70)