#!/usr/bin/env python3
"""
Step-by-step diagnostic to locate where SP is corrupted (zeroed).
"""

import sys
import struct
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / 'tools'))
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from spatial_rv64i_cpu import SpatialRV64ICore
from standalone_alpine_boot import load_opensbi_alpine_and_dtb, RAM_SIZE, RAM_BASE

def main():
    print("Initializing CPU core...")
    core = SpatialRV64ICore(RAM_SIZE)
    
    print("Loading boot components...")
    dtb_addr = load_opensbi_alpine_and_dtb(core)
    
    core.write_register(10, 0)
    core.write_register(11, dtb_addr)
    
    # Fast forward to 11,224,900 steps
    print("Fast forwarding to 11,224,900 steps...")
    core.step(11_224_900)
    
    state = core.get_state()
    # Consume existing UART output
    core.read_uart_output()
    sp = state['regs'][2][0] | (state['regs'][2][1] << 32)
    print(f"Step 11.2249M: PC=0x{state['pc']:016x}, SP=0x{sp:016x}")
    
    # Run instruction by instruction
    for batch in range(200):
        core.step(1)
        state = core.get_state()
        sp = state['regs'][2][0] | (state['regs'][2][1] << 32)
        pc = state['pc']
        
        print(f"S {11_224_900 + batch + 1:d}: PC=0x{pc:016x} SP=0x{sp:016x} mode={state['mode']} trap_pending={state['trap_pending']}")
        if sp == 0:
            print("SP became zero!")
            break
            
if __name__ == '__main__':
    main()
