#!/usr/bin/env python3
"""
Minimal boot script to catch EFAULT fault state.
Steps through execve path with CSR logging.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'tools'))

from spatial_rv64i_cpu import SpatialRV64ICore

print("Booting to catch execve fault...")
core = SpatialRV64ICore()

target = "Starting init"
max_steps = 1_000_000_000
check_interval = 100_000

print(f"Looking for: '{target}'")
print(f"Will monitor CSRs after...")

steps = 0
in_execve_region = False

while steps < max_steps:
    core.step()
    steps += 1

    if steps % check_interval == 0:
        uart = core.read_uart()
        if uart:
            uart_str = uart.decode('utf-8', errors='ignore')

            if target in uart_str and "couldn't execute it" not in uart_str:
                print(f"\n*** Found '{target}' at step {steps} ***")
                in_execve_region = True

            if in_execve_region and "couldn't execute it" in uart_str:
                print(f"\n*** EFAULT at step {steps} ***")
                print(f"UART (last 200 chars): {uart_str[-200:]}")

                # Capture current CSR state
                scause = core.read_csr(0x142)
                stval = core.read_csr(0x143)
                sepc = core.read_csr(0x141)
                state = core.get_state()

                print(f"\nFault state:")
                print(f"  PC:     0x{state['pc']:016x}")
                print(f"  Mode:   {state['mode']}")
                print(f"  scause: 0x{scause:016x}")
                print(f"  stval:  0x{stval:016x}")
                print(f"  sepc:   0x{sepc:016x}")

                # Decode scause
                is_interrupt = (scause >> 63) & 1
                exception_code = scause & 0xFF
                print(f"\n  Interrupt: {is_interrupt}")
                print(f"  Exception code: {exception_code}")
                if is_interrupt:
                    print("  -> Timer interrupt (normal)")
                elif exception_code == 13:
                    print("  -> Load page fault")
                elif exception_code == 15:
                    print("  -> Store page fault")
                elif exception_code == 12:
                    print("  -> Instruction page fault")

                sys.exit(0)

        if steps % 1_000_000 == 0:
            print(f"Progress: {steps} steps")

print("\nFailed to reach EFAULT")