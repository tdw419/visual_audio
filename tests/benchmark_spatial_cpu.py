import time
import numpy as np
import sys
import argparse
from pathlib import Path

# Add tools directory to path
sys.path.append(str(Path(__file__).parent.parent / "tools"))
from spatial_rv32i_cpu import SpatialRV32ICore

def compile_fibonacci_loop(iterations):
    """
    Returns RV32I machine code for calculating fibonacci numbers.
    x1 = 0
    x2 = 1
    x3 = iterations
    
    loop:
        beq x3, x0, done
        add x4, x1, x2
        addi x1, x2, 0
        addi x2, x4, 0
        addi x3, x3, -1
        jal x0, loop
    done:
        halt / infinite loop
    """
    
    # 0: addi x1, x0, 0
    # 4: addi x2, x0, 1
    # 8: lui x3, (iterations >> 12) & 0xFFFFF
    # 12: addi x3, x3, iterations & 0xFFF
    # loop (16):
    # 16: beq x3, x0, done (offset +24 -> 40)
    # 20: add x4, x1, x2
    # 24: addi x1, x2, 0
    # 28: addi x2, x4, 0
    # 32: addi x3, x3, -1
    # 36: jal x0, loop (offset -20 -> 16)
    # done (40):
    # 40: jal x0, done (offset 0 -> 40)
    
    # Helper to build B-type immediate
    def b_imm(offset):
        imm12 = (offset >> 12) & 0x1
        imm11 = (offset >> 11) & 0x1
        imm10_5 = (offset >> 5) & 0x3F
        imm4_1 = (offset >> 1) & 0xF
        return (imm12 << 31) | (imm10_5 << 25) | (imm4_1 << 8) | (imm11 << 7)
        
    # Helper to build J-type immediate
    def j_imm(offset):
        imm20 = (offset >> 20) & 0x1
        imm19_12 = (offset >> 12) & 0xFF
        imm11 = (offset >> 11) & 0x1
        imm10_1 = (offset >> 1) & 0x3FF
        return (imm20 << 31) | (imm10_1 << 21) | (imm11 << 20) | (imm19_12 << 12)

    upper_iter = (iterations >> 12) & 0xFFFFF
    lower_iter = iterations & 0xFFF
    
    # Manual sign extension for lower 12 bits of auipc/addi
    if lower_iter & 0x800:
        upper_iter = (upper_iter + 1) & 0xFFFFF

    instrs = np.array([
        (0 << 20) | (0 << 15) | (0 << 12) | (1 << 7) | 0x13,
        (1 << 20) | (0 << 15) | (0 << 12) | (2 << 7) | 0x13,
        (upper_iter << 12) | (3 << 7) | 0x37,
        (lower_iter << 20) | (3 << 15) | (0 << 12) | (3 << 7) | 0x13,
        
        # loop:
        b_imm(24) | (0 << 20) | (3 << 15) | (0 << 12) | 0x63, # beq x3, x0, done
        (0 << 25) | (2 << 20) | (1 << 15) | (0 << 12) | (4 << 7) | 0x33, # add x4, x1, x2
        (0 << 20) | (2 << 15) | (0 << 12) | (1 << 7) | 0x13, # addi x1, x2, 0
        (0 << 20) | (4 << 15) | (0 << 12) | (2 << 7) | 0x13, # addi x2, x4, 0
        (0xFFF << 20) | (3 << 15) | (0 << 12) | (3 << 7) | 0x13, # addi x3, x3, -1
        j_imm(-20 & 0x1FFFFF) | (0 << 7) | 0x6F, # jal x0, loop
        
        # done:
        j_imm(0) | (0 << 7) | 0x6F, # jal x0, done
    ], dtype=np.uint32)
    
    return instrs.tobytes()

def run_benchmark():
    print("=" * 60)
    print("Benchmarking SpatialRV32ICore (Hilbert Curve GPU Execution)")
    print("=" * 60)
    
    # We will do 100,000 iterations of the loop.
    # Each loop iteration executes 6 instructions.
    # 4 setup instructions.
    # Total instructions ~ 600,004
    iterations = 100000
    program = compile_fibonacci_loop(iterations)
    
    core = SpatialRV32ICore(1024 * 1024)
    core.load_program(program)
    
    expected_instructions = 4 + (iterations * 6) + 1
    
    start_time = time.perf_counter()
    
    # Currently step() executes one instruction at a time via a single WGSL dispatch.
    # Execute all instructions in batches (since WGSL caps at 65535 per dispatch)
    remaining = expected_instructions
    while remaining > 0:
        batch = min(remaining, 65535)
        core.step(batch)
        remaining -= batch
        
    end_time = time.perf_counter()
    
    state = core.get_state()
    total_time = end_time - start_time
    instr_per_sec = expected_instructions / total_time
    
    print(f"Executed {expected_instructions:,} instructions.")
    print(f"Total time: {total_time:.4f} seconds")
    print(f"Throughput: {instr_per_sec:,.2f} instructions/sec")
    print(f"Final PC: {state['pc']}")
    print(f"Final Loop Counter (x3): {state['regs'][3]}")
    
    # Validation: fib(100000) will heavily overflow 32-bit registers, 
    # but the loop counter should be 0.
    if state['regs'][3] != 0:
        print("❌ ERROR: Loop counter did not reach 0!")
        sys.exit(1)
        
    print("✓ Benchmark completed successfully")

if __name__ == "__main__":
    run_benchmark()
