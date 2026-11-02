#!/usr/bin/env python3
"""
Debug script to check interrupt delivery state during xv6 boot.
Runs for specific instruction counts and dumps timer/CSR state.
"""

import sys
import struct
import numpy as np
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from riscv_gpu_cpu import make_cpu_state, CPU_DTYPE
from boot_xv6_gpu import ELF64Loader, create_gpu_hardware
import wgpu
import wgpu.utils


def boot_and_check(elf_path: str, max_instructions: int):
    """Boot and check interrupt state after max_instructions."""
    print(f"\n{'='*70}")
    print(f"Testing with {max_instructions:,} instructions")
    print(f"{'='*70}")

    # Load ELF
    elf = ELF64Loader(elf_path)
    
    # Setup memory
    MEMORY_SIZE_MB = 128
    MEMORY_SIZE = MEMORY_SIZE_MB * 1024 * 1024
    PHYS_START = 0x80000000
    pixel_count = MEMORY_SIZE // 4
    memory = np.zeros((pixel_count, 4), dtype=np.uint32)

    for seg in elf.get_loadable_segments():
        offset = seg['p_vaddr'] - PHYS_START
        if offset < 0 or offset + seg['p_memsz'] > MEMORY_SIZE:
            continue
        data = elf.get_segment_data(seg)
        start_pixel = offset // 4
        start_byte = offset % 4

        if start_byte == 0:
            word_count = (len(data) + 3) // 4
            byte_data = np.frombuffer(data, dtype=np.uint8)
            padded_len = word_count * 4
            if len(byte_data) < padded_len:
                padded = np.zeros(padded_len, dtype=np.uint8)
                padded[:len(byte_data)] = byte_data
                byte_data = padded
            pixel_data = byte_data.reshape(-1, 4)
            memory[start_pixel:start_pixel + word_count] = pixel_data
        else:
            for i, byte in enumerate(data):
                pixel_idx = (offset + i) // 4
                byte_idx = (offset + i) % 4
                memory[pixel_idx, byte_idx] = byte

    # Setup CPU
    cpu_state = make_cpu_state(elf.entry_point, priv_mode=3)
    harness = create_gpu_hardware(memory, cpu_state, max_instructions)
    
    # Run single dispatch
    device = harness['device']
    queue = harness['queue']
    
    encoder = device.create_command_encoder()
    pass_enc = encoder.begin_compute_pass()
    pass_enc.set_pipeline(harness['pipeline'])
    pass_enc.set_bind_group(0, harness['bind_group'])
    pass_enc.dispatch_workgroups(1)
    pass_enc.end()
    queue.submit([encoder.finish()])

    # Read back CPU state
    cpu_readback_bytes = queue.read_buffer(harness['cpu_buffer'])
    cpu_readback = np.frombuffer(cpu_readback_bytes, dtype=CPU_DTYPE)
    
    # Extract fields
    pc = (cpu_readback['pc'][0][1] << 32) | cpu_readback['pc'][0][0]
    running = int(cpu_readback['running'][0])
    instr_count = int(cpu_readback['instr_count'][0])
    priv_mode = int(cpu_readback['priv_mode'][0])
    
    mtime_low = int(cpu_readback['mtime_low'][0])
    mtime_high = int(cpu_readback['mtime_high'][0])
    mtimecmp_low = int(cpu_readback['mtimecmp_low'][0])
    mtimecmp_high = int(cpu_readback['mtimecmp_high'][0])
    timer_fired = int(cpu_readback['timer_fired'][0])
    timer_irq_count = int(cpu_readback['timer_interrupt_count'][0])
    total_irq_count = int(cpu_readback['total_interrupt_count'][0])
    
    mstatus_x = int(cpu_readback['mstatus'][0][0])
    mideleg_x = int(cpu_readback['mideleg'][0][0])
    mip_x = int(cpu_readback['mip'][0][0])
    mie_x = int(cpu_readback['mie'][0][0])
    
    stvec_low = int(cpu_readback['stvec'][0][0])
    stvec_high = int(cpu_readback['stvec'][0][1])
    mtvec_low = int(cpu_readback['mtvec'][0][0])
    mtvec_high = int(cpu_readback['mtvec'][0][1])
    
    mtime = (mtime_high << 32) | mtime_low
    mtimecmp = (mtimecmp_high << 32) | mtimecmp_low
    stvec = (stvec_high << 32) | stvec_low
    mtvec = (mtvec_high << 32) | mtvec_low
    
    # Check interrupt enable bits
    mie_enabled = (mstatus_x >> 3) & 1  # MIE (bit 3)
    sie_enabled = (mstatus_x >> 1) & 1  # SIE (bit 1)
    
    # Check pending timer bits
    mtip_pending = (mip_x >> 6) & 1  # MTIP (bit 6)
    stip_pending = (mip_x >> 5) & 1  # STIP (bit 5)
    
    # Check delegation
    timer_delegated = (mideleg_x >> 5) & 1  # Bit 5 (timer)
    
    # Check if timer would be enabled
    timer_enabled = (mtimecmp != 0)
    
    # Check if we've crossed the compare value
    timer_crossed = timer_enabled and (mtime >= mtimecmp)
    
    print(f"\nResults after {instr_count:,} instructions:")
    print(f"  PC:            0x{pc:016x}")
    print(f"  Privilege:     {'M' if priv_mode == 3 else 'S' if priv_mode == 1 else 'U'} ({priv_mode})")
    print(f"  Running:       {running}")
    
    print(f"\nTimer state:")
    print(f"  mtime:         {mtime:,} (0x{mtime:016x})")
    print(f"  mtimecmp:      {mtimecmp:,} (0x{mtimecmp:016x})")
    print(f"  timer_enabled: {timer_enabled}")
    print(f"  timer_crossed: {timer_crossed}")
    print(f"  timer_fired:   {timer_fired}")
    
    print(f"\nInterrupt delivery:")
    print(f"  timer_irq_count:   {timer_irq_count}")
    print(f"  total_irq_count:   {total_irq_count}")
    
    print(f"\nMSTATUS bits:")
    print(f"  MIE (bit 3):   {mie_enabled}")
    print(f"  SIE (bit 1):   {sie_enabled}")
    print(f"  raw mstatus.x: 0x{mstatus_x:08x}")
    
    print(f"\nMIP pending bits:")
    print(f"  MTIP (bit 6):  {mtip_pending}")
    print(f"  STIP (bit 5):  {stip_pending}")
    print(f"  raw mip.x:     0x{mip_x:08x}")
    
    print(f"\nMIE enabled bits:")
    print(f"  raw mie.x:     0x{mie_x:08x}")
    
    print(f"\nMIDELEG delegation:")
    print(f"  timer (bit 5): {timer_delegated}")
    print(f"  raw mideleg.x: 0x{mideleg_x:08x}")
    
    print(f"\nTrap vectors:")
    print(f"  stvec:         0x{stvec:016x}")
    print(f"  mtvec:         0x{mtvec:016x}")
    
    # Diagnosis
    print(f"\n{'='*70}")
    print("DIAGNOSIS:")
    print(f"{'='*70}")
    
    issues = []
    
    if not timer_enabled:
        issues.append("Timer NOT enabled (mtimecmp == 0)")
    elif not timer_crossed:
        issues.append(f"Timer not yet crossed (mtime={mtime:,} < mtimecmp={mtimecmp:,})")
    
    if priv_mode == 3 and not mie_enabled:
        issues.append("In M-mode but MIE not enabled")
    elif priv_mode == 1 and not sie_enabled:
        issues.append("In S-mode but SIE not enabled")
    
    if timer_crossed and timer_fired == 0:
        issues.append("Timer crossed but timer_fired not set - bug in edge trigger")
    
    if timer_crossed and timer_fired:
        if priv_mode == 1:
            if not stip_pending:
                issues.append("Timer crossed and fired but STIP not set - bug")
            if not timer_delegated:
                issues.append("Timer not delegated to S-mode but running in S-mode")
            if sie_enabled and stip_pending and timer_irq_count == 0:
                issues.append("All conditions met but interrupt not taken - bug in delivery")
        elif priv_mode == 3:
            if not mtip_pending:
                issues.append("Timer crossed and fired but MTIP not set - bug")
            if mie_enabled and mtip_pending and timer_irq_count == 0:
                issues.append("All conditions met but interrupt not taken - bug in delivery")
    
    if not issues:
        if timer_irq_count == 0:
            if timer_enabled and timer_crossed:
                issues.append("Timer should fire but hasn't - unknown reason")
            else:
                print("  Timer not ready yet - waiting for mtimecmp programming")
        else:
            print(f"  OK: {timer_irq_count} timer interrupts delivered")
    else:
        print("  ISSUES FOUND:")
        for i, issue in enumerate(issues, 1):
            print(f"    {i}. {issue}")
    
    print(f"{'='*70}\n")
    
    return {
        'pc': pc,
        'priv_mode': priv_mode,
        'mtime': mtime,
        'mtimecmp': mtimecmp,
        'timer_enabled': timer_enabled,
        'timer_crossed': timer_crossed,
        'timer_irq_count': timer_irq_count,
        'issues': issues,
    }


if __name__ == '__main__':
    kernel_path = '/tmp/xv6-riscv/kernel/kernel'
    
    if not Path(kernel_path).exists():
        print(f"ERROR: Kernel not found at {kernel_path}")
        print("Run vendor/xv6-riscv/build.sh first")
        sys.exit(1)
    
    # Test at progressively deeper instruction counts
    test_points = [
        10_000,      # Early boot
        100_000,     # Still early
        1_000_000,   # Mid boot
        10_000_000,  # Should be into userland
        50_000_000,  # Deeper
        100_000_000, # 100M
    ]
    
    results = []
    for max_instr in test_points:
        try:
            result = boot_and_check(kernel_path, max_instr)
            results.append((max_instr, result))
        except KeyboardInterrupt:
            print("\nInterrupted by user")
            break
        except Exception as e:
            print(f"ERROR at {max_instr}: {e}")
            import traceback
            traceback.print_exc()
    
    # Summary
    print(f"\n{'='*70}")
    print("SUMMARY")
    print(f"{'='*70}")
    for max_instr, result in results:
        print(f"\n{max_instr:,} instructions:")
        print(f"  Timer enabled: {result['timer_enabled']}")
        print(f"  Timer crossed: {result['timer_crossed']}")
        print(f"  Timer IRQs:    {result['timer_irq_count']}")
        print(f"  Priv mode:     {'M' if result['priv_mode'] == 3 else 'S' if result['priv_mode'] == 1 else 'U'}")
        if result['issues']:
            print(f"  Issues:       {', '.join(result['issues'][:3])}")
    print(f"\n{'='*70}")