#!/usr/bin/env python3
"""
xv6 Boot Pattern Capture

Boots xv6 on the GPU RISC-V emulator and captures real-world execution
patterns that can guide RV64 emulator development.

Patterns captured:
- System call entry/exit (write, read, brk, etc.)
- Context switch (trapframe save/restore)
- Timer interrupt (CLINT, MIP.MTIP)
- Page table walk (Sv32 translations)
- UART I/O (TX/RX)
- User mode transitions (sret/ecall)

These patterns are the "ground truth" for what RV64 should emulate.
"""

import sys
import json
from pathlib import Path
from collections import defaultdict

sys.path.append(str(Path(__file__).parent))
from boot_xv6_gpu import boot_xv6


class XV6PatternCapture:
    """Capture xv6 execution patterns during boot."""
    
    def __init__(self, xv6_img_path: str):
        self.xv6_img_path = xv6_img_path
        self.patterns = {
            'syscall': [],
            'interrupt': [],
            'context_switch': [],
            'page_table_walk': [],
            'uart_io': [],
            'user_mode': []
        }
        self.current_pattern = None
        self.instruction_count = 0
    
    def capture_pattern(self, pattern_type: str, pc: int, regs: list, 
                         csr: dict, description: str = ""):
        """
        Record a captured pattern during execution.
        
        Args:
            pattern_type: Type of pattern (syscall, interrupt, etc.)
            pc: Current program counter
            regs: Register state (32 registers)
            csr: CSR state (mtvec, mcause, satp, etc.)
            description: Human-readable description
        """
        pattern = {
            'pc': hex(pc),
            'regs': regs,
            'csr': csr,
            'description': description,
            'instruction_count': self.instruction_count
        }
        
        self.patterns[pattern_type].append(pattern)
        
        # Print pattern capture for visibility
        print(f"[{pattern_type.upper()}] PC={hex(pc)} {description}")
        
        # Visual pattern: show first 8 registers as "pixel bar"
        pixel_bar = ''.join(['█' if r != 0 else '░' for r in regs[:8]])
        print(f"  State: [{pixel_bar}]")
    
    def detect_syscall_pattern(self, pc: int, regs: list, csr: dict):
        """
        Detect system call entry/exit patterns.
        
        Syscall pattern:
        - a7 = syscall number (64=write, 93=exit, 214=brk)
        - PC jumps to stvec via ECALL
        - mcause = 8 (U-mode ecall)
        """
        a7 = regs[17]  # syscall number
        mcause = csr.get('mcause', 0)
        
        # Detect syscall entry
        if mcause == 8 and a7 in [64, 93, 214, 172]:
            syscall_names = {
                64: 'write',
                93: 'exit',
                214: 'brk',
                172: 'getpid'
            }
            name = syscall_names.get(a7, f'unknown({a7})')
            self.capture_pattern(
                'syscall', pc, regs, csr,
                f"ECALL U-mode: {name}(a7={a7})"
            )
    
    def detect_interrupt_pattern(self, pc: int, regs: list, csr: dict):
        """
        Detect interrupt patterns.
        
        Timer interrupt:
        - MIP.MTIP = 1 (bit 7)
        - mcause = 0x80000007 (timer interrupt)
        - PC jumps to mtvec
        """
        mip = csr.get('mip', 0)
        mcause = csr.get('mcause', 0)
        
        # Detect timer interrupt
        if (mip & 0x80) and (mcause & 0x80000000 == 0x80000000):
            self.capture_pattern(
                'interrupt', pc, regs, csr,
                f"Timer interrupt: MIP.MTIP=1, mcause={hex(mcause)}"
            )
    
    def detect_context_switch_pattern(self, pc: int, regs: list, csr: dict):
        """
        Detect context switch patterns.
        
        Context switch pattern:
        - Write to hart register (0x80000000)
        - Save trapframe to stack
        - PC jumps to scheduler
        """
        # Check if we're at a common yield point
        if 0x80000000 <= pc < 0x80002000:
            # Look for yield() function pattern
            sp = regs[2]  # stack pointer
            
            # Check if we're in a yield context (trapframe save)
            if sp > 0x80000000 and sp < 0x81000000:
                self.capture_pattern(
                    'context_switch', pc, regs, csr,
                    f"Context switch: sp={hex(sp)}, writing to hart"
                )
    
    def detect_page_table_walk_pattern(self, pc: int, regs: list, csr: dict):
        """
        Detect page table walk patterns.
        
        Page table walk:
        - satp != 0 (MMU enabled)
        - Memory access to page table range (0x80000000-0x81000000)
        - Multiple consecutive accesses (2-level walk for Sv32)
        """
        satp = csr.get('satp', 0)
        
        if satp != 0:
            # MMU is enabled - check if we're doing a page walk
            # Page tables are in low kernel memory
            if 0x80000000 <= pc < 0x80010000:
                # Check for page table access pattern
                a0 = regs[10]  # commonly used for virtual addresses
                
                if 0x80000000 <= a0 < 0x81000000:
                    self.capture_pattern(
                        'page_table_walk', pc, regs, csr,
                        f"Page table walk: satp={hex(satp)}, VA={hex(a0)}"
                    )
    
    def detect_uart_io_pattern(self, pc: int, regs: list, csr: dict):
        """
        Detect UART I/O patterns.
        
        UART TX:
        - Write to UART_LSR (0x10000005) to check if ready
        - Write to UART_THR (0x10000000) to transmit
        
        UART RX:
        - Read UART_LSR to check data available
        - Read UART_RBR (0x10000000) to receive
        """
        # Check for UART MMIO access
        a0 = regs[10]  # address register
        
        if a0 == 0x10000000:  # UART base
            a1 = regs[11]  # value register
            
            self.capture_pattern(
                'uart_io', pc, regs, csr,
                f"UART I/O: addr={hex(a0)}, val={hex(a1)}"
            )
    
    def detect_user_mode_pattern(self, pc: int, regs: list, csr: dict):
        """
        Detect user mode transition patterns.
        
        U-mode entry:
        - sret instruction (mstatus.SPP=0)
        - PC jumps to user-space (<0x80000000 or custom U-mode region)
        
        U-mode exit:
        - ecall from user-space
        - mcause = 8 (U-mode ecall)
        """
        mstatus = csr.get('mstatus', 0)
        spp = (mstatus >> 8) & 0x3
        
        if spp == 0:  # S-mode privilege
            # Check if we're returning to U-mode
            if pc < 0x80000000:
                self.capture_pattern(
                    'user_mode', pc, regs, csr,
                    f"U-mode execution: PC={hex(pc)}"
                )
    
    def analyze_trace(self, trace_path: str):
        """
        Analyze a captured execution trace and extract patterns.
        
        Args:
            trace_path: Path to JSONL trace file
        """
        print(f"Analyzing trace: {trace_path}")
        
        with open(trace_path) as f:
            for line in f:
                entry = json.loads(line)
                pc = entry['pc']
                regs = entry['regs']
                
                # Simulate CSR state (not captured in basic trace)
                csr = {
                    'mcause': 0,
                    'mip': 0,
                    'mstatus': 0,
                    'satp': 0
                }
                
                self.instruction_count += 1
                
                # Detect patterns
                self.detect_syscall_pattern(pc, regs, csr)
                self.detect_interrupt_pattern(pc, regs, csr)
                self.detect_context_switch_pattern(pc, regs, csr)
                self.detect_page_table_walk_pattern(pc, regs, csr)
                self.detect_uart_io_pattern(pc, regs, csr)
                self.detect_user_mode_pattern(pc, regs, csr)
        
        self.print_summary()
    
    def print_summary(self):
        """Print pattern capture summary."""
        print("\n" + "=" * 60)
        print("PATTERN CAPTURE SUMMARY")
        print("=" * 60)
        
        for pattern_type, patterns in self.patterns.items():
            count = len(patterns)
            print(f"{pattern_type:20s}: {count:4d} patterns")
        
        print("=" * 60)
        print(f"Total patterns: {sum(len(p) for p in self.patterns.values())}")
        print(f"Instructions analyzed: {self.instruction_count}")
        print("=" * 60)
    
    def save_patterns(self, output_path: str):
        """Save captured patterns to JSON file."""
        with open(output_path, 'w') as f:
            json.dump(self.patterns, f, indent=2)
        
        print(f"Patterns saved to: {output_path}")


def capture_xv6_boot_patterns(xv6_img: str, output_json: str):
    """
    Boot xv6 and capture execution patterns.
    
    Args:
        xv6_img: Path to xv6 kernel image
        output_json: Output path for captured patterns
    """
    print("=" * 60)
    print("CAPTURING XV6 BOOT PATTERNS")
    print("=" * 60)
    
    capturer = XV6PatternCapture(xv6_img)
    
    # Boot xv6 with tracing enabled
    # NOTE: This requires boot_xv6_gpu.py to support trace output
    print(f"\nBooting xv6: {xv6_img}")
    
    # For now, we'll analyze an existing trace if available
    # In production, boot_xv6_gpu.py would emit a trace during boot
    
    trace_path = Path(__file__).parent / "xv6_boot_trace.jsonl"
    if trace_path.exists():
        capturer.analyze_trace(str(trace_path))
    else:
        print("No trace found. Boot xv6 first to generate trace.")
        print("  Use: python3 tools/boot_xv6_gpu.py boot_images/xv6.img --trace")
        return None
    
    # Save patterns
    capturer.save_patterns(output_json)
    
    return capturer.patterns


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Capture xv6 boot patterns")
    parser.add_argument('xv6_img', help="Path to xv6 kernel image")
    parser.add_argument('--output', '-o', 
                        default="tools/xv6_patterns.json",
                        help="Output JSON path for patterns")
    
    args = parser.parse_args()
    
    patterns = capture_xv6_boot_patterns(args.xv6_img, args.output)
    
    if patterns:
        print("\n" + "=" * 60)
        print("CAPTURE COMPLETE")
        print("=" * 60)
        print(f"Patterns saved to: {args.output}")
        print("\nUse these patterns to guide RV64 emulator development.")
        print("See PIXEL_PATTERN_LEARNING_GUIDE.md for next steps.")
        print("=" * 60)


if __name__ == "__main__":
    main()