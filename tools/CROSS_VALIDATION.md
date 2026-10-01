# GPU RISC-V Emulator — Cross-Validation Guide

This directory contains the complete toolchain for cross-validating the GPU-native RV32I emulator against QEMU (or QEMU-like reference implementations).

## Components

### Core Files

- **`spatial_rv32i_cpu.py`** — GPU-native RV32I+M core execution
  - Supports optional `trace_file` parameter for execution traces
  - Traces in JSONL format compatible with `diff_qemu_gpu_traces.py`

- **`rv32i_asm.py`** — RV32I+M assembler
  - Supports labels, pseudo-instructions, ABI register names
  - Generates binary compatible with both emulators

- **`spatial_disassembler.py`** — RV32I+M disassembler
  - Decodes binaries back to assembly with branch/jump targets
  - Useful for inspecting GPU memory when debugging

- **`diff_qemu_gpu_traces.py`** — Trace comparison tool
  - Accepts JSONL trace files from QEMU and GPU emulator
  - Reports first mismatching instruction with register differences

### Demo & Tests

- **`demo_qemu_gpu_diff.py`** — End-to-end cross-validation demo
  - Compiles test program (Fibonacci loop)
  - Runs on both GPU and Python (QEMU-like) emulators
  - Generates traces and runs diff tool
  - Reports PASS/FAIL with detailed output

- **`tests/benchmark_spatial_cpu.py`** — Performance benchmark
  - Measures GPU throughput (instructions/sec)
  - Validates correct execution (loop counter reaches zero)

## Usage

### Quick Cross-Validation Demo

Run the full cross-validation pipeline:

```bash
python3 tools/demo_qemu_gpu_diff.py
```

Expected output:

```
============================================================
GPU Emulator Cross-Validation Demo
============================================================

1. Compiling Fibonacci loop program...
   Expected 65 instructions

2. Running on GPU emulator (WGSL)...
   Final PC: 0x00000028
   Final x1: 55, x2: 89, x3: 0
   Trace: 66 entries

3. Running on Python emulator (QEMU-like)...
   Final PC: 0x00000028
   Final x1: 55, x2: 89, x3: 0
   Trace: 66 entries

4. Comparing traces with diff_qemu_gpu_traces.py...

✓ Compared 65 instructions - all matched!

============================================================
✓ CROSS-VALIDATION PASSED
  GPU emulator produces identical results to QEMU-like reference
============================================================
```

### Manual Trace Generation

Generate a GPU trace for manual inspection:

```python
import sys
sys.path.append('tests')
from benchmark_spatial_cpu import compile_fibonacci_loop, SpatialRV32ICore

program = compile_fibonacci_loop(10)
core = SpatialRV32ICore(1024 * 1024, trace_file='/tmp/my_trace.jsonl')
core.load_program(program)

# Execute with tracing
expected = 4 + (10 * 6) + 1
for _ in range(expected):
    core.step(1)
```

Then inspect the trace:

```bash
head /tmp/my_trace.jsonl
# {"pc": 0, "regs": {"x0": 0, "x1": 0, ..., "x31": 0}}
# {"pc": 4, "regs": {"x0": 0, "x1": 0, ..., "x31": 0}}
# ...
```

### Disassembling GPU Memory

If you need to inspect what's actually in GPU memory:

```bash
# Dump GPU memory to binary, then disassemble
python3 -c "
import sys
sys.path.append('tests')
from benchmark_spatial_cpu import compile_fibonacci_loop, SpatialRV32ICore
program = compile_fibonacci_loop(10)
with open('/tmp/fib.bin', 'wb') as f:
    f.write(program)
"

python3 tools/spatial_disassembler.py /tmp/fib.bin --base 0x80000000
```

### Cross-Validation with Real QEMU

To validate against actual QEMU instead of the Python reference emulator:

1. Compile your test program to ELF using `riscv64-unknown-elf-gcc` or your RV32I toolchain
2. Run QEMU with tracing: see `tools/qemu_cpu_trace.py` for QEMU invocation patterns
3. Generate GPU trace using `SpatialRV32ICore(trace_file='...')`
4. Run `diff_qemu_gpu_traces.py` with both trace files:

```bash
python3 tools/diff_qemu_gpu_traces.py \
    --qemu-trace /tmp/qemu_trace.jsonl \
    --gpu-trace /tmp/gpu_trace.jsonl \
    --max-instructions 1000
```

## Trace Format

Both QEMU and GPU traces use JSONL (one JSON object per line):

```json
{"pc": 123456, "regs": {"x0": 0, "x1": 10, "x2": 20, ..., "x31": 0}}
{"pc": 123460, "regs": {"x0": 0, "x1": 10, "x2": 30, ..., "x31": 0}}
...
```

The diff tool aligns traces by PC and compares register states.

## Performance Baseline

Current GPU emulator performance (WGSL compute shader):

- **Throughput**: ~1.34 million instructions/second
- **Batching**: Up to 65,535 instructions per GPU dispatch
- **Tracing overhead**: Minimal when disabled; adds ~10% when enabled

## Verification Status

- ✅ RV32I base instructions (all opcodes)
- ✅ M extension (mul, mulh, mulhu, div, divu, rem, remu)
- ✅ Control flow (beq, bne, blt, bge, jal, jalr)
- ✅ CSR operations (csrrw, csrrs, csrrc, csrrwi, csrrsi, csrrci)
- ✅ Cross-validation against QEMU-like emulator (100% match)
- ⏳ Real QEMU validation (needs real QEMU environment setup)

## Extending the Toolchain

To add more complex test programs:

1. Write RV32I assembly using `rv32i_asm.py` syntax
2. Compile to binary: `from rv32i_asm import assemble; binary = assemble(source)`
3. Run on both emulators with trace generation
4. Run diff tool to verify

Example test program:

```python
from rv32i_asm import assemble

test_program = """
    addi x1, x0, 5
    addi x2, x0, 3
    mul  x3, x1, x2
    add  x4, x3, x3
    halt
"""

binary = assemble(test_program)
```

## Troubleshooting

**"Unable to find extension: VK_EXT_physical_device_drm"**
- Non-critical warning about Vulkan extensions
- Does not affect functionality

**Trace file is empty or has fewer entries than expected**
- Ensure you're calling `step()` for each instruction
- Batching (e.g., `step(100)`) only traces the final state, not intermediate steps

**diff tool reports mismatches**
- Check instruction counts: both traces should have similar lengths
- Verify both emulators started from the same initial state (PC, registers)
- For batched execution, the GPU trace may have fewer entries than expected

**GPU emulator hangs or never halts**
- Check for infinite loops in your program
- Use `run_until_halt(max_cycles=10000)` to add a safety timeout
- Disassemble the binary to verify jump targets are correct