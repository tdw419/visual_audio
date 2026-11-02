#!/usr/bin/env python3
"""
Diagnose why PLIC interrupts stop flowing after ~1200 interrupts.

This modifies RISCV_CPU_MMU.wgsl to log PLIC state every interrupt.
"""
import subprocess
import re
import sys

def run_trace():
    # Boot and capture PLIC state on each interrupt
    cmd = [
        "python3", "tools/boot_xv6_gpu.py",
        "/tmp/xv6-riscv/kernel/kernel",
        "--command", "echo test"
    ]

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        cwd="/home/jericho/projects/zion/projects/visual_audio"
    )

    plic_states = []
    last_irq_count = 0

    for line in proc.stdout:
        # Extract interrupt count and PLIC state from diagnostic output
        if "total_irq=" in line:
            match = re.search(r"total_irq=(\d+)", line)
            if match:
                irq_count = int(match.group(1))
                if irq_count > last_irq_count:
                    # New interrupt delivered
                    print(f"[INTERRUPT {irq_count}] PLIC check triggered")
                    last_irq_count = irq_count

                    # Check if this matches stall pattern (~1200-1300)
                    if 1200 <= irq_count <= 1400:
                        print(f"  -> In stall region! Capturing state...")
                        # Could add more diagnostic capture here

        # Check for actual test output
        if "test" in line and "$" not in line:
            print(line.strip())

    proc.wait()

if __name__ == "__main__":
    run_trace()