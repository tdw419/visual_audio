# QEMU Golden Reference Test Workflow

## Quick Test

Trace a simple kernel and verify the parser works:

```bash
# 1. Build simple test kernel
make -f Makefile.test_simple

# 2. Generate QEMU trace (bounded to 50 instructions)
python3 tools/qemu_cpu_trace.py test_simple_qemu.elf --max-instructions 50

# 3. Parse and verify
python3 tools/qemu_cpu_trace.py test_simple_qemu.elf --parse-only
```

Expected output:
- QEMU starts at 0x1000 (virt machine reset vector)
- Traces ~50 instructions
- Parser correctly extracts PC and register values

## Next: GPU Emulator Trace Capture

Need to add trace output to our GPU emulator. Currently it doesn't dump per-instruction state. Options:

1. Add JSONL trace output to `riscv_gpu_cpu.py` with `max_instructions=1`
2. Parse the CPU struct after each dispatch and dump to JSONL

## Diff Workflow

```bash
# 1. Capture QEMU trace at target PC
python3 tools/qemu_cpu_trace.py kernel.elf --max-instructions 5000 --target-pc 0x8000103c

# 2. Capture GPU trace (needs implementation)

# 3. Compare
python3 tools/diff_qemu_gpu_traces.py --qemu-trace /tmp/qemu_trace.jsonl \
                                     --gpu-trace /tmp/gpu_trace.jsonl \
                                     --start-pc 0x8000103c
```

## Notes

- QEMU's virt machine always starts at 0x1000 even with `-bios none`
- GPU emulator boots directly to kernel entry point (0x80000000)
- Need to align traces by PC, not instruction count
- Register names may differ (e.g., x0/zero vs x0)
- CSRs like mhartid may differ legitimately and should be ignored in diff