#!/bin/bash
# Test the QEMU golden reference workflow end-to-end

set -e

echo "=== QEMU Golden Reference Workflow Test ==="
echo

echo "[1] Building simple test kernel..."
make -f Makefile.test_simple

echo
echo "[2] Generating QEMU trace (50 instructions)..."
python3 tools/qemu_cpu_trace.py test_simple_qemu.elf --max-instructions 50

echo
echo "[3] Parsing trace output..."
python3 tools/qemu_cpu_trace.py test_simple_qemu.elf --parse-only

echo
echo "[4] Checking trace file size..."
ls -lh /tmp/qemu_cpu_trace.log

echo
echo "[5] Displaying first 10 instructions of trace..."
head -50 /tmp/qemu_cpu_trace.log | grep "^0x" | head -10

echo
echo "=== Workflow test complete! ==="
echo
echo "Next steps:"
echo "1. Run QEMU trace on real kernel: python3 tools/qemu_cpu_trace.py kernel.elf --max-instructions 1000 --target-pc 0x8000103c"
echo "2. Capture GPU trace (needs per-instruction mode in GPU emulator)"
echo "3. Diff the traces: python3 tools/diff_qemu_gpu_traces.py --qemu-trace qemu_trace.jsonl --gpu-trace gpu_trace.jsonl"