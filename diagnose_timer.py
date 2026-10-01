#!/usr/bin/env python3
"""
Timer interrupt diagnostic at stall point

Check if timer interrupts are actually firing and being delivered
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'tools'))

from spatial_rv64i_cpu import SpatialRV64ICore
from standalone_alpine_boot_quick import load_opensbi_alpine_and_dtb

print("=" * 70)
print("TIMER INTERRUPT DIAGNOSTIC AT STALL POINT")
print("=" * 70)
print()

# Initialize
print("[1] Initializing core...")
core = SpatialRV64ICore(64 * 1024 * 1024)
dtb_addr = load_opensbi_alpine_and_dtb(core)
core.write_register(10, 0)
core.write_register(11, dtb_addr)

# Run to stall point
print("[2] Running to 40M steps (after zbud loaded)...")
core.step(steps=40_000_000)

# Get initial state
state = core.get_state()

# CSR addresses
CSR_MTIMECMP = 0x13A  # Note: We use memory-mapped for M-mode
CSR_STIMECMP = 0x14D
CSR_MIP = 0x134
CSR_MIE = 0x104
CSR_SIE = 0x104
CSR_MSTATUS = 0x300
CSR_SSTATUS = 0x100
CSR_TIME = 0xC01

print()
print("[3] Timer State at Stall Point:")
print()

# Read timer CSRs
stimecmp = core.read_csr(CSR_STIMECMP)
mtime = core.read_csr(CSR_TIME)
mip = core.read_csr(CSR_MIP)
mie = core.read_csr(CSR_MIE)
mstatus = core.read_csr(CSR_MSTATUS)
sstatus = core.read_csr(CSR_SSTATUS)

print(f"  TIME (timer counter):       0x{mtime:016x} ({mtime:,})")
print(f"  STIMECMP (S-mode timer):    0x{stimecmp:016x} ({stimecmp:,})")
print(f"  MIP (interrupt pending):    0x{mip:016x}")
print(f"  MIE (interrupt enable):     0x{mie:016x}")
print(f"  MSTATUS:                    0x{mstatus:016x}")
print(f"  SSTATUS:                    0x{sstatus:016x}")
print()

# Decode MIP bits
print("  MIP bits:")
print(f"    SSIP (bit 1):  {(mip >> 1) & 1}")
print(f"    MSIP (bit 3):  {(mip >> 3) & 1}")
print(f"    STIP (bit 5):  {(mip >> 5) & 1}  <- S-mode timer pending")
print(f"    MTIP (bit 7):  {(mip >> 7) & 1}  <- M-mode timer pending")
print(f"    SEIP (bit 9):  {(mip >> 9) & 1}")
print(f"    MEIP (bit 11): {(mip >> 11) & 1}")
print()

# Decode MIE bits
print("  MIE bits:")
print(f"    SSIE (bit 1):  {(mie >> 1) & 1}")
print(f"    MSIE (bit 3):  {(mie >> 3) & 1}")
print(f"    STIE (bit 5):  {(mie >> 5) & 1}  <- S-mode timer enable")
print(f"    MTIE (bit 7):  {(mie >> 7) & 1}  <- M-mode timer enable")
print(f"    SEIE (bit 9):  {(mie >> 9) & 1}")
print(f"    MEIE (bit 11): {(mie >> 11) & 1}")
print()

# Decode MSTATUS
print("  MSTATUS interrupt enable bits:")
print(f"    MIE (bit 3):   {(mstatus >> 3) & 1}  <- M-mode global interrupt enable")
print(f"    SIE (bit 1):   {(mstatus >> 1) & 1}  <- S-mode global interrupt enable (when in M-mode)")
print(f"    Mode:          {'M' if (mstatus & 0x6000) == 0x1800 else 'S' if (mstatus & 0x6000) == 0x1000 else 'U'}")
print(f"    Previous mode: {(mstatus >> 8) & 1}  <- SPP (0=U, 1=S)")
print()

# Check if timer should fire
print("[4] Timer Interrupt Analysis:")
print()

if stimecmp == 0:
    print("  ⚠ STIMECMP is 0 - kernel has not armed S-mode timer!")
    print("    This explains the stall - kernel is waiting for timer that will never fire.")
else:
    if mtime >= stimecmp:
        print(f"  ✓ Timer SHOULD have fired: mtime (0x{mtime:x}) >= stimecmp (0x{stimecmp:x})")
        if (mip >> 5) & 1:
            print("  ✓ STIP is set in MIP - timer interrupt is pending")
        else:
            print("  ✗ STIP is NOT set in MIP - bug in timer interrupt generation!")
    else:
        print(f"  ⏳ Timer not yet due: mtime (0x{mtime:x}) < stimecmp (0x{stimecmp:x})")

print()

# Check if interrupt would be taken
stip_pending = (mip >> 5) & 1
stie_enabled = (mie >> 5) & 1
sie_enabled = (mstatus >> 1) & 1
current_mode = state['mode']

print("[5] Interrupt Delivery Path:")
print(f"  STIP pending:        {stip_pending}")
print(f"  STIE enabled:        {stie_enabled}")
print(f"  SIE (in MSTATUS):    {sie_enabled}")
print(f"  Current mode:        {current_mode} (3=M, 1=S, 0=U)")
print()

if stip_pending and stie_enabled:
    if current_mode == 1:  # S-mode
        print("  ⚠ IN S-MODE but timer interrupt can't be taken directly!")
        print("    S-mode timer (STIP) must be delegated by mideleg and handled in S-mode")
        print("    OR forwarded by M-mode (OpenSBI) to S-mode")
    elif current_mode == 3:  # M-mode
        if sie_enabled:
            print("  ✓ Interrupt SHOULD be taken to S-mode handler")
        else:
            print("  ✗ SIE not enabled - interrupt won't be taken to S-mode")

# Read mideleg
mideleg = core.read_csr(0x103)
print(f"\n  MIDELEG:             0x{mideleg:016x}")
print(f"    STIE delegated:   {(mideleg >> 5) & 1}  <- 1=STIP goes to S-mode, 0=handled in M-mode")

print()

# Check diagnostics from state
print("[6] Emulator Diagnostics:")
print(f"  Timer interrupts fired:    {state['timer_interrupts_fired']}")
print(f"  Interrupts delivered:      {state['interrupts_delivered']}")
print(f"  TLB hits:                  {state['tlb_hits']:,}")
print(f"  TLB misses:                {state['tlb_misses']:,}")
print()

# Run for 1M more steps and check if timer fires
print("[7] Running 1M steps and monitoring timer...")
initial_timer_fired = state['timer_interrupts_fired']
initial_interrupts = state['interrupts_delivered']

core.step(steps=1_000_000)

final_state = core.get_state()
delta_timer_fired = final_state['timer_interrupts_fired'] - initial_timer_fired
delta_interrupts = final_state['interrupts_delivered'] - initial_interrupts

print(f"  Timer fires in 1M steps:   {delta_timer_fired}")
print(f"  Interrupts delivered:      {delta_interrupts}")
print()

if delta_timer_fired == 0:
    print("  ✗ NO timer fires in 1M steps - kernel will hang forever!")
    if stimecmp == 0:
        print("  CAUSE: STIMECMP not set by kernel (timer never armed)")
    else:
        print("  CAUSE: Timer comparison logic not working correctly")
elif delta_interrupts == 0:
    print("  ⚠ Timer fires but NO interrupts delivered!")
    print("  CAUSE: Interrupt delivery logic issue (MIE/SIE not set, or mode issue)")

print()
print("=" * 70)
print("DIAGNOSIS COMPLETE")
print("=" * 70)