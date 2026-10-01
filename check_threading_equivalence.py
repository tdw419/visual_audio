#!/usr/bin/env python3
"""Check register-state equivalence between threading ON and OFF."""

import sys
import os
sys.path.insert(0, 'tools')
sys.path.insert(0, 'tests')

from spatial_rv64i_cpu import SpatialRV64ICore
from test_alpine_opensbi_boot import load_opensbi_alpine_and_dtb, RAM_SIZE

def capture_state_at_steps(cpu, steps_list, enabled):
    """Capture full register state at specified step counts."""
    states = {}
    steps_taken = 0
    checkpoints = sorted(steps_list)
    checkpoint_idx = 0
    
    while checkpoint_idx < len(checkpoints):
        target = checkpoints[checkpoint_idx]
        
        # Run to target
        steps_needed = target - steps_taken
        if steps_needed > 0:
            cpu.step(steps_needed)
            steps_taken = target
        
        # Capture full state
        state = cpu.get_state()
        states[target] = {
            'regs': list(state['regs']),
            'pc': state['pc'],
            'mode': state['mode'],
            'halted': state['halted'],
            'steps_taken': steps_taken
        }
        print(f"[{'ON' if enabled else 'OFF'}] At {steps_taken} steps: PC={state['pc']:016x}, mode={state['mode']}, halted={state['halted']}")
        
        checkpoint_idx += 1
    
    return states

def compare_states(states_on, states_off):
    """Compare states from threading ON vs OFF."""
    all_match = True
    for step in sorted(states_on.keys()):
        on = states_on[step]
        off = states_off[step]
        
        print(f"\n=== Step {step} ===")
        
        # Compare regs
        regs_match = on['regs'] == off['regs']
        if not regs_match:
            print(f"  REGS MISMATCH")
            for i in range(32):
                if on['regs'][i] != off['regs'][i]:
                    print(f"    x{i:2d}: ON={on['regs'][i]:016x} OFF={off['regs'][i]:016x}")
            all_match = False
        else:
            print(f"  REGS: MATCH")
        
        # Compare PC, mode, halted
        pc_match = on['pc'] == off['pc']
        mode_match = on['mode'] == off['mode']
        halted_match = on['halted'] == off['halted']
        
        if pc_match and mode_match and halted_match:
            print(f"  PC={on['pc']:016x}: MATCH")
            print(f"  mode={on['mode']}: MATCH")
            print(f"  halted={on['halted']}: MATCH")
        else:
            if not pc_match:
                print(f"  PC: ON={on['pc']:016x} OFF={off['pc']:016x} MISMATCH")
            if not mode_match:
                print(f"  mode: ON={on['mode']} OFF={off['mode']} MISMATCH")
            if not halted_match:
                print(f"  halted: ON={on['halted']} OFF={off['halted']} MISMATCH")
            all_match = False
    
    return all_match

def main():
    checkpoints = [5_000_000, 15_000_000, 30_000_000]
    
    # Run with threading ON
    print("=" * 60)
    print("Running with threading ON...")
    print("=" * 60)
    cpu_on = SpatialRV64ICore(memory_size_bytes=RAM_SIZE)
    dtb_addr = load_opensbi_alpine_and_dtb(cpu_on)
    cpu_on.write_register(10, 0)
    cpu_on.write_register(11, dtb_addr)
    cpu_on.set_bb_threading(enabled=True)
    states_on = capture_state_at_steps(cpu_on, checkpoints, enabled=True)
    
    # Run with threading OFF
    print("\n" + "=" * 60)
    print("Running with threading OFF...")
    print("=" * 60)
    cpu_off = SpatialRV64ICore(memory_size_bytes=RAM_SIZE)
    dtb_addr = load_opensbi_alpine_and_dtb(cpu_off)
    cpu_off.write_register(10, 0)
    cpu_off.write_register(11, dtb_addr)
    cpu_off.set_bb_threading(enabled=False)
    states_off = capture_state_at_steps(cpu_off, checkpoints, enabled=False)
    
    # Compare
    print("\n" + "=" * 60)
    print("COMPARISON RESULTS")
    print("=" * 60)
    all_match = compare_states(states_on, states_off)
    
    if all_match:
        print("\n✓ ALL STATES MATCH - threading preserves register state")
        return 0
    else:
        print("\n✗ STATE MISMATCH DETECTED - threading changes behavior")
        return 1

if __name__ == '__main__':
    sys.exit(main())