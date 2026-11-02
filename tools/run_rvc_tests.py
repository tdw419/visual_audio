#!/usr/bin/env python3
"""
Run RVC tests on GPU emulator to verify decompressor coverage.

Usage:
    python3 tools/run_rvc_tests.py                    # Run all RVC tests
    python3 tools/run_rvc_tests.py quad0              # Run specific test
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from boot_xv6_gpu import boot_xv6_on_gpu, create_gpu_hardware, make_cpu_state, ELF64Loader
import numpy as np

# Load test configuration
TEST_CONFIGS = {
    "quad0": {
        "description": "Quadrant 0: Stack-relative memory (C.ADDI4SPN, C.LW, C.LD, C.SW, C.SD)",
        "expected_output": "RVC",
    },
    "quad1": {
        "description": "Quadrant 1: Immediate ops (C.ADDI, C.LUI, C.JAL)",
        "expected_output": "RVC",
    },
    "quad2": {
        "description": "Quadrant 2: ALU ops (C.MV, C.ADD, C.SLLI, C.JR)",
        "expected_output": "RVC",
    },
    "quad3_branch": {
        "description": "Quadrant 3: Branches (C.BEQZ, C.BNEZ, C.SRLI, C.SRAI, C.ANDI)",
        "expected_output": "RVC",
    },
    "quad3_logic": {
        "description": "Quadrant 3: Logic (C.SUB, C.XOR, C.OR, C.AND)",
        "expected_output": "RVC",
    },
}

MEMORY_SIZE_MB = 128
MEMORY_SIZE = MEMORY_SIZE_MB * 1024 * 1024
PHYS_START = 0x80000000
ENTRY_POINT = 0x80000000
MAX_CYCLES = 1000000


def load_payload_from_npy(npy_path: Path) -> np.ndarray:
    """Load payload from .npy file (pixel memory format)."""
    memory = np.load(str(npy_path))
    
    # Verify format
    if memory.shape[1] != 4:
        raise ValueError(f"Expected shape (N, 4), got {memory.shape}")
    
    return memory


def run_rvc_test(test_name: str) -> dict:
    """Run a single RVC test on GPU emulator."""
    if test_name not in TEST_CONFIGS:
        raise ValueError(f"Unknown test: {test_name}")
    
    test_config = TEST_CONFIGS[test_name]
    npy_path = Path(__file__).parent.parent / f"tests/bare_metal/{test_name}/test_rvc.npy"
    
    if not npy_path.exists():
        return {"status": "error", "message": f"Test not built: {npy_path}"}
    
    print(f"Running {test_name}: {test_config['description']}")
    
    # Load payload
    memory = load_payload_from_npy(npy_path)
    
    # Create GPU hardware
    gpu_hardware = create_gpu_hardware(memory)
    
    # Create CPU state
    cpu_state = make_cpu_state(pc=ENTRY_POINT)
    
    # Boot and run
    uart_output = []
    
    try:
        for cycle in range(MAX_CYCLES):
            # Run one iteration
            uart_char = boot_xv6_on_gpu(gpu_hardware, cpu_state, max_instructions=1)
            
            if uart_char:
                uart_output.append(uart_char)
                # Print in real-time
                print(uart_char, end='', flush=True)
            
            # Check if halted
            if cpu_state['halted']:
                break
            
            # Safety: stop if we're stuck
            if cycle > 0 and cycle % 100000 == 0:
                print(f"\n[Cycle {cycle}]", end='')
        
        output_str = ''.join(uart_output)
        
        # Check for expected output
        expected = test_config['expected_output']
        if expected in output_str:
            print(f"\n✓ PASS: Test '{test_name}' completed")
            return {
                "status": "pass",
                "test": test_name,
                "cycles": cycle,
                "output": output_str,
            }
        else:
            print(f"\n✗ FAIL: Test '{test_name}' - expected '{expected}' in output")
            return {
                "status": "fail",
                "test": test_name,
                "cycles": cycle,
                "output": output_str,
            }
            
    except Exception as e:
        print(f"\n✗ ERROR: Test '{test_name}' crashed: {e}")
        return {
            "status": "error",
            "test": test_name,
            "error": str(e),
        }


def main():
    if len(sys.argv) > 1:
        tests = [sys.argv[1]]
    else:
        tests = list(TEST_CONFIGS.keys())
    
    results = []
    
    print("=" * 70)
    print("RVC Test Suite - GPU Emulator")
    print("=" * 70)
    print()
    
    for test in tests:
        result = run_rvc_test(test)
        results.append(result)
        print()
    
    # Summary
    print("=" * 70)
    print("Summary:")
    print("=" * 70)
    
    passed = sum(1 for r in results if r.get('status') == 'pass')
    failed = sum(1 for r in results if r.get('status') == 'fail')
    errors = sum(1 for r in results if r.get('status') == 'error')
    
    print(f"Passed:  {passed}/{len(results)}")
    print(f"Failed:  {failed}/{len(results)}")
    print(f"Errors:  {errors}/{len(results)}")
    
    if failed > 0 or errors > 0:
        print("\nFailed tests:")
        for r in results:
            if r.get('status') in ['fail', 'error']:
                print(f"  - {r['test']}: {r.get('message', r.get('error', 'Unknown'))}")
        return 1
    
    print("\n✓ All RVC tests passed!")
    return 0


if __name__ == "__main__":
    sys.exit(main())