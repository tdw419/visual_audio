#!/usr/bin/env python3
"""
Capture RV32 execution traces from xv6 boot for RV64 development.

This captures detailed execution state that can be used as ground truth
when implementing the RV64 emulator.

Usage:
    python3 tools/capture_rv32_traces.py --boot-sequence
    python3 tools/capture_rv32_traces.py --trace-execve
    python3 tools/capture_rv32_traces.py --full-boot
"""

import sys
import json
import time
import argparse
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Dict, List, Tuple, Optional

sys.path.append(str(Path(__file__).parent))
from spatial_rv32i_cpu import SpatialRV32ICore


@dataclass
class InstructionTrace:
    """Single instruction execution trace."""
    pc: int
    instruction: int
    decoded: str
    registers_before: Dict[int, int]  # x0-x31
    registers_after: Dict[int, int]
    csr_before: Dict[str, int]  # mstatus, mtvec, satp, etc.
    csr_after: Dict[str, int]
    memory_reads: List[Tuple[int, int, int]]  # (addr, size, value)
    memory_writes: List[Tuple[int, int, int]]
    privilege_before: int  # 0=U, 1=S, 3=M
    privilege_after: int
    page_table_walk: Optional[Dict]  # If memory access triggered walk

    def to_dict(self):
        return asdict(self)


@dataclass
class ExecutionTrace:
    """Complete execution trace for a phase."""
    phase_name: str
    instructions: List[InstructionTrace]
    metadata: Dict

    def to_dict(self):
        return {
            'phase_name': self.phase_name,
            'instruction_count': len(self.instructions),
            'instructions': [i.to_dict() for i in self.instructions],
            'metadata': self.metadata
        }


class RV32TraceCapture:
    """Capture detailed execution traces from RV32 emulator."""

    def __init__(self):
        self.core = None  # type: Optional[SpatialRV32ICore]
        self.traces: List[ExecutionTrace] = []
        self.trace_file: str = "tools/rv32_execution_traces.json"

    def load_kernel(self, kernel_path: str, dtb_path: str = None):
        """Load xv6 kernel into emulator."""
        print(f"Loading kernel: {kernel_path}")

        with open(kernel_path, 'rb') as f:
            kernel = f.read()

        self.core = SpatialRV32ICore(memory_size_bytes=64 * 1024 * 1024)
        RAM_BASE = 0x80000000
        self.core.load_program(kernel, entry_point=RAM_BASE, ram_base=RAM_BASE)

        if dtb_path and Path(dtb_path).exists():
            with open(dtb_path, 'rb') as f:
                dtb = f.read()
            self.core.write_mem_bytes(0x00400000, dtb)
            self.core.write_register(10, 0)
            self.core.write_register(11, RAM_BASE + 0x00400000)

        print("✓ Kernel loaded")

    def capture_instruction_trace(self, steps: int = 1) -> InstructionTrace:
        """Execute instructions and capture detailed trace."""
        state_before = self.core.get_state()

        # Extract registers before
        regs_before = {f"x{i}": state_before.get('registers', {}).get(i, 0)
                      for i in range(32)}

        # Extract CSRs before
        csr_before = {
            'mstatus': state_before.get('mstatus', 0),
            'mtvec': state_before.get('mtvec', 0),
            'satp': state_before.get('satp', 0),
            'mepc': state_before.get('mepc', 0),
            'mcause': state_before.get('mcause', 0),
        }

        # Execute
        self.core.step(steps=steps)

        state_after = self.core.get_state()

        # Extract registers after
        regs_after = {f"x{i}": state_after.get('registers', {}).get(i, 0)
                     for i in range(32)}

        # Extract CSRs after
        csr_after = {
            'mstatus': state_after.get('mstatus', 0),
            'mtvec': state_after.get('mtvec', 0),
            'satp': state_after.get('satp', 0),
            'mepc': state_after.get('mepc', 0),
            'mcause': state_after.get('mcause', 0),
        }

        # Decode instruction
        pc = state_before.get('pc', 0)
        instr = self.core.read_mem_word(pc)
        decoded = self._decode_instruction(instr)

        trace = InstructionTrace(
            pc=pc,
            instruction=instr,
            decoded=decoded,
            registers_before=regs_before,
            registers_after=regs_after,
            csr_before=csr_before,
            csr_after=csr_after,
            memory_reads=[],  # Would need memory access tracking
            memory_writes=[],
            privilege_before=state_before.get('privilege', 3),
            privilege_after=state_after.get('privilege', 3),
            page_table_walk=None  # Would need MMU tracing
        )

        return trace

    def capture_boot_sequence(self, max_instructions: int = 10000):
        """Capture trace from kernel entry through early boot."""
        print("=" * 70)
        print("CAPTURING BOOT SEQUENCE TRACE")
        print("=" * 70)

        traces = []
        start_time = time.time()

        for i in range(max_instructions):
            trace = self.capture_instruction_trace()
            traces.append(trace)

            # Check for significant events
            if i % 1000 == 0:
                print(f"  Captured {i}/{max_instructions} instructions")

            # Stop at shell prompt (look for UART output pattern)
            uart = self.core.read_uart_output()
            if b'$' in uart or b'#' in uart:
                print(f"✓ Shell prompt reached at instruction {i}")
                break

        duration = time.time() - start_time

        exec_trace = ExecutionTrace(
            phase_name="boot_sequence",
            instructions=traces,
            metadata={
                'capture_time': time.time(),
                'duration_ms': duration * 1000,
                'instructions_captured': len(traces),
                'uart_output': uart.decode(errors='ignore')[-500:],
            }
        )

        self.traces.append(exec_trace)
        print(f"✓ Captured {len(traces)} instructions ({duration:.2f}s)")

        return exec_trace

    def capture_page_table_walks(self, max_instructions: int = 5000):
        """Focus on capturing page table walk patterns."""
        print("=" * 70)
        print("CAPTURING PAGE TABLE WALK PATTERNS")
        print("=" * 70)

        # This would need MMU instrumentation in the emulator
        # For now, capture traces around known MMU-heavy operations

        traces = []
        pc_start = self.core.get_state().get('pc', 0)

        for i in range(max_instructions):
            trace = self.capture_instruction_trace()

            # Check if this is a memory access instruction
            if 'lw' in trace.decoded or 'sw' in trace.decoded or 'lb' in trace.decoded:
                traces.append(trace)

            if len(traces) >= 100:  # Capture 100 memory accesses
                break

        exec_trace = ExecutionTrace(
            phase_name="page_table_walks",
            instructions=traces,
            metadata={
                'capture_time': time.time(),
                'memory_accesses_captured': len(traces),
            }
        )

        self.traces.append(exec_trace)
        print(f"✓ Captured {len(traces)} memory access traces")

        return exec_trace

    def _decode_instruction(self, instr: int) -> str:
        """Simple RISC-V instruction decoder."""
        opcode = instr & 0x7F
        rd = (instr >> 7) & 0x1F
        funct3 = (instr >> 12) & 0x7
        rs1 = (instr >> 15) & 0x1F
        rs2 = (instr >> 20) & 0x1F
        funct7 = (instr >> 25) & 0x7F

        if opcode == 0x33:  # R-type
            if funct7 == 0x00 and funct3 == 0x00:
                return f"add x{rd}, x{rs1}, x{rs2}"
            elif funct7 == 0x00 and funct3 == 0x07:
                return f"and x{rd}, x{rs1}, x{rs2}"
            elif funct7 == 0x20 and funct3 == 0x00:
                return f"sub x{rd}, x{rs1}, x{rs2}"
        elif opcode == 0x13:  # I-type
            imm = instr >> 20
            imm = imm if imm < 0x800 else imm - 0x1000
            if funct3 == 0x00:
                return f"addi x{rd}, x{rs1}, {imm}"
        elif opcode == 0x63:  # B-type
            return f"beq x{rs1}, x{rs2}, pc+??"
        elif opcode == 0x23:  # S-type
            return f"sw x{rs2}, ??(x{rs1})"
        elif opcode == 0x03:  # Load
            if funct3 == 0x02:
                return f"lw x{rd}, ??(x{rs1})"
        elif opcode == 0x6F:  # JAL
            return f"jal x{rd}, ??"
        elif opcode == 0x73:  # SYSTEM
            if funct3 == 0x000:
                return f"ecall"
            elif funct3 == 0x001:
                return f"csrrw x{rd}, csr, x{rs1}"

        return f"unknown_{hex(instr)}"

    def save_traces(self, output_path: str = None):
        """Save captured traces to JSON."""
        if output_path is None:
            output_path = self.trace_file

        data = {
            'capture_timestamp': time.time(),
            'total_phases': len(self.traces),
            'phases': [t.to_dict() for t in self.traces],
            'metadata': {
                'kernel': 'xv6-riscv',
                'isa': 'RV32IMAC',
                'purpose': 'RV64 development ground truth'
            }
        }

        with open(output_path, 'w') as f:
            json.dump(data, f, indent=2)

        print(f"✓ Saved traces to: {output_path}")
        print(f"  Phases: {len(self.traces)}")
        print(f"  Total instructions: {sum(len(t.instructions) for t in self.traces):,}")

    def load_traces(self, trace_path: str):
        """Load traces from JSON for comparison."""
        with open(trace_path) as f:
            data = json.load(f)

        print(f"✓ Loaded {len(data['phases'])} trace phases")
        return data


def analyze_for_rv64_development(trace_data: dict):
    """Analyze traces to extract RV64-relevant patterns."""
    print("\n" + "=" * 70)
    print("RV64 DEVELOPMENT ANALYSIS")
    print("=" * 70)

    for phase in trace_data['phases']:
        print(f"\nPhase: {phase['phase_name']}")
        print(f"  Instructions: {phase['instruction_count']:,}")

        instructions = phase['instructions']

        if not instructions:
            continue

        # Find patterns useful for RV64
        print("\n  Key patterns for RV64:")

        # 1. Arithmetic operations (verify low-32-bit behavior)
        arith = [i for i in instructions if any(op in i['decoded'] for op in ['add', 'sub', 'and', 'or'])]
        if arith:
            print(f"    Arithmetic operations: {len(arith)}")
            print(f"      Sample: {arith[0]['decoded']}")
            print(f"        Before: x{arith[0]['registers_before']}")

        # 2. Memory operations (verify Sv39 page table walks)
        mem_ops = [i for i in instructions if any(op in i['decoded'] for op in ['lw', 'sw', 'lb', 'sb'])]
        if mem_ops:
            print(f"    Memory operations: {len(mem_ops)}")
            print(f"      Sample: {mem_ops[0]['decoded']}")

        # 3. CSR operations (verify privilege handling)
        csr_ops = [i for i in instructions if 'csr' in i['decoded'] or 'ecall' in i['decoded']]
        if csr_ops:
            print(f"    CSR operations: {len(csr_ops)}")
            print(f"      Sample: {csr_ops[0]['decoded']}")
            if csr_ops[0]['csr_before']:
                print(f"        SATP before: {hex(csr_ops[0]['csr_before'].get('satp', 0))}")
                print(f"        SATP after:  {hex(csr_ops[0]['csr_after'].get('satp', 0))}")

        # 4. Privilege transitions
        priv_changes = [i for i in instructions if i['privilege_before'] != i['privilege_after']]
        if priv_changes:
            print(f"    Privilege transitions: {len(priv_changes)}")
            print(f"      Sample: {priv_changes[0]['privilege_before']} → {priv_changes[0]['privilege_after']}")

        print(f"\n  Metadata:")
        for key, value in phase['metadata'].items():
            print(f"    {key}: {value}")


def main():
    parser = argparse.ArgumentParser(description="Capture RV32 execution traces for RV64 development")
    parser.add_argument('--kernel', default="boot_images/xv6.img", help="Kernel image path")
    parser.add_argument('--dtb', help="Device tree blob path")
    parser.add_argument('--boot-sequence', action='store_true', help="Capture boot sequence")
    parser.add_argument('--trace-execve', action='store_true', help="Capture execve execution")
    parser.add_argument('--full-boot', action='store_true', help="Capture full boot to shell")
    parser.add_argument('--analyze', help="Analyze existing trace file")
    parser.add_argument('--output', '-o', help="Output JSON path")

    args = parser.parse_args()

    if args.analyze:
        # Analyze existing traces
        capturer = RV32TraceCapture()
        trace_data = capturer.load_traces(args.analyze)
        analyze_for_rv64_development(trace_data)
        return

    # Capture new traces
    capturer = RV32TraceCapture()
    capturer.load_kernel(args.kernel, args.dtb)

    if args.boot_sequence or args.full_boot:
        capturer.capture_boot_sequence(max_instructions=10000)

    if args.trace_execve:
        capturer.capture_page_table_walks()

    capturer.save_traces(args.output)

    print("\n" + "=" * 70)
    print("CAPTURE COMPLETE")
    print("=" * 70)
    print("\nHow to use these traces for RV64 development:")
    print("  1. Load trace: data = json.load('tools/rv32_execution_traces.json')")
    print("  2. For each instruction, verify RV64 produces same low-32-bit result")
    print("  3. Compare page table walks: RV64 Sv39 must match RV32 Sv32")
    print("  4. Verify CSR behavior: privilege transitions must be identical")


if __name__ == "__main__":
    main()