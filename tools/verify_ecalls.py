#!/usr/bin/env python3
import sys
import numpy as np
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / 'tools'))

from spatial_rv64i_cpu import SpatialRV64ICore
from standalone_alpine_boot import load_opensbi_alpine_and_dtb, RAM_SIZE

def main():
    print("Initializing CPU core...")
    core = SpatialRV64ICore(RAM_SIZE)
    
    print("Loading boot components...")
    dtb_addr = load_opensbi_alpine_and_dtb(core)
    
    # Set registers
    core.write_register(10, 0)         # a0 = hartid = 0
    core.write_register(11, dtb_addr)  # a1 = DTB
    
    # Run to 5M steps
    print("Stepping 5,000,000 steps...")
    core.step(5_000_000)
    state = core.get_state()
    print(f"At 5M steps:")
    print(f"  PC: {hex(state['pc'])}")
    print(f"  Timer Interrupts Fired (SBI TIME): {state['timer_interrupts_fired']}")
    
    # Run to 15M steps
    print("Stepping another 10,000,000 steps (total 15M)...")
    core.step(10_000_000)
    state = core.get_state()
    print(f"At 15M steps:")
    print(f"  PC: {hex(state['pc'])}")
    print(f"  Timer Interrupts Fired (SBI TIME): {state['timer_interrupts_fired']}")
    print(f"  Interrupts Delivered: {state['interrupts_delivered']}")
    
    # Read UART
    uart_bytes = core.read_uart_output()
    uart_text = uart_bytes.decode('utf-8', errors='ignore')
    print("Does UART contain 'E:'?")
    has_e = "E:" in uart_text
    print(f"  'E:' present: {has_e}")
    if has_e:
        # Print lines containing E:
        lines = [line for line in uart_text.split('\n') if "E:" in line]
        print(f"  Sample E: lines (up to 5): {lines[:5]}")

if __name__ == '__main__':
    main()
