#!/usr/bin/env python3
"""
Single consistent verification run: steps Alpine boot to 300M steps,
reporting PC + ALL interrupt/ecall counters + UART tail together at each
checkpoint, so there's one source of truth instead of stitched-together
partial runs from different sessions.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent))

from spatial_rv64i_cpu import SpatialRV64ICore
from standalone_alpine_boot import load_opensbi_alpine_and_dtb, RAM_SIZE


def main():
    print("Initializing CPU core...")
    core = SpatialRV64ICore(RAM_SIZE)

    print("Loading boot components...")
    dtb_addr = load_opensbi_alpine_and_dtb(core)

    core.write_register(10, 0)         # a0 = hartid = 0
    core.write_register(11, dtb_addr)  # a1 = DTB

    max_steps = 300_000_000
    batch_size = 5_000_000
    steps = 0
    uart_output = ""
    last_pc = None
    stuck_count = 0

    print()
    print(f"{'steps':>11} | {'PC':>18} | {'timer_fired':>11} | {'irq_delivered':>13} | "
          f"{'sbi_console':>11} | {'sbi_time':>9} | {'sbi_unknown':>11} | {'tlb_hit%':>8}")
    print("-" * 120)

    while steps < max_steps:
        core.step(steps=batch_size)
        steps += batch_size

        uart_bytes = core.read_uart_output()
        if uart_bytes:
            uart_output += uart_bytes.decode('latin-1', errors='replace')

        state = core.get_state()
        pc = state['pc']
        hits = state['tlb_hits']
        misses = state['tlb_misses']
        total = hits + misses
        hit_pct = (hits / total * 100) if total else 0.0

        print(f"{steps:11d} | 0x{pc:016x} | {state['timer_interrupts_fired']:11d} | "
              f"{state['interrupts_delivered']:13d} | {state['sbi_ecall_console']:11d} | "
              f"{state['sbi_ecall_time']:9d} | {state['sbi_ecall_unknown']:11d} | {hit_pct:7.2f}%")

        if pc == last_pc:
            stuck_count += 1
        else:
            stuck_count = 0
        last_pc = pc

        if state['halted']:
            print("\nCPU halted.")
            break

    print()
    print("=" * 70)
    print("FINAL STATE")
    print("=" * 70)
    state = core.get_state()
    print(f"  PC:                 0x{state['pc']:016x}")
    print(f"  Steps:              {steps:,}")
    print(f"  Halted:             {state['halted'] != 0}")
    print(f"  Mode:               {state['mode']}")
    print(f"  Consecutive stuck PC checkpoints: {stuck_count} (of {steps // batch_size} total checks)")
    print(f"  timer_interrupts_fired: {state['timer_interrupts_fired']}")
    print(f"  interrupts_delivered:   {state['interrupts_delivered']}")
    print(f"  sbi_ecall_console:      {state['sbi_ecall_console']}")
    print(f"  sbi_ecall_time:         {state['sbi_ecall_time']}")
    print(f"  sbi_ecall_unknown:      {state['sbi_ecall_unknown']}")
    print()
    print("UART OUTPUT (last 3000 chars):")
    print("-" * 70)
    print(uart_output[-3000:] if uart_output else "(no output)")
    print("-" * 70)
    print(f"Total UART bytes: {len(uart_output)}")


if __name__ == '__main__':
    main()
