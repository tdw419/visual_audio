# RV64I GPU-Native Emulator Harness Guide

**Date**: 2026-08-25
**Status**: Active

## Overview

The RV64I harness is a GPU-native RISC-V emulator that executes code directly on the GPU via WebGPU compute shaders. It's designed to boot real operating systems (xv6, Alpine Linux) for research into spatial computing and pixel-native execution.

### Key Characteristics

- **GPU-native**: All instruction execution happens on the GPU (WGSL compute shader)
- **Hilbert-mapped memory**: Physical memory is stored in Hilbert curve order to preserve spatial locality
- **RISC-V RV64I**: Implements the base integer instruction set (64-bit)
- **Real boots**: xv6 and Alpine Linux have been verified to boot to shell/login
- **Monitoring**: Live state inspection, UART capture, memory dumps at arbitrary points
- **Performance**: ~1.7M instructions/second on RTX 5090 (2-3 orders slower than CPU, but GPU-parallelizable)

---

## Architecture

### Components

```
┌─────────────────────────────────────────────────────────────┐
│                    Python Harness Layer                     │
│  SpatialRV64ICore (tools/spatial_rv64i_cpu.py)             │
│  - Memory/CSR/UART buffer management                        │
│  - Hilbert LUT cache & mapping                              │
│  - Basic-block threading pre-decoder                        │
│  - WGSL pipeline binding                                    │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                   WGSL Compute Shader                        │
│  (tools/SPATIAL_RV64I.wgsl - loaded by Python)              │
│  - CPU state: PC, registers, mode, halted flag              │
│  - Fetch-decode-execute loop (RV64I ISA)                    │
│  - Sv39 MMU + 256-entry direct-mapped TLB                   │
│  - UART TX/RX emulation (16550-style)                       │
│  - Timer (mtime/mtimecmp) + interrupt handling              │
│  - Basic-block threading (pre-decoded ops)                  │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                 GPU Memory (WebGPU Storage)                  │
│  Binding 0: Memory buffer (Hilbert-mapped, e.g., 64MB)      │
│  Binding 1: Registers (32 x 64-bit = 256 bytes)            │
│  Binding 2: State (120 bytes: PC, mode, halted, etc.)       │
│  Binding 3: CSRs (4096 x 64-bit = 32KB)                    │
│  Binding 4: UART buffer (4096 bytes ring buffer)            │
│  Binding 5: Hilbert LUT (read-only, precomputed)            │
│  Binding 6: Decoded ops (pre-decoded instruction metadata)  │
│  Binding 7: TLB (256 entries x 16 bytes)                    │
└─────────────────────────────────────────────────────────────┘
```

### Memory Layout: Hilbert Curve Mapping

Physical memory is not stored linearly. Instead, it's mapped to a 2D grid using a Hilbert space-filling curve, then flattened to 1D storage. This preserves **spatial locality** — nearby physical addresses map to nearby storage indices.

**Why Hilbert?**  
- Better cache locality than row-major or Z-order for sequential access patterns
- Critical for GPU memory access patterns (coalesced reads)
- Required for VCC (Visual Consistency Contract) compliance in spatial systems

**Mapping:**
```python
# Linear guest address d → Hilbert spatial index
spatial_idx = hilbert_d2xy(N, d)  # Returns (x, y)
storage_idx = y * N + x           # Flatten to 1D
```

The Hilbert LUT is precomputed once on the host (vectorized NumPy) and cached to disk (`~/.cache/visual_audio/hilbert_lut_*.npy`). The GPU does O(1) lookups into this read-only buffer instead of recomputing the curve per access.

### CPU State (WGSL `CPUState` struct)

```wgsl
struct CPUState {
    pc_low, pc_high: u32,              // Program counter (64-bit split)
    halted: u32,                       // Core halted flag
    steps_remaining: u32,              // How many more instructions to execute
    mode: u32,                         // Privilege mode: 0=U, 1=S, 3=M
    trap_pending: u32,                 // Trap pending flag
    reservation_valid: u32,            // LR/SC reservation flag
    reservation_addr_low, reservation_addr_high: u32,
    uart_tx_len: u32,                  // UART TX ring buffer length
    mtime_low, mtime_high: u32,        // Timer value (64-bit)
    mtimecmp_low, mtimecmp_high: u32,  // Timer compare (interrupt threshold)
    ram_base_low, ram_base_high: u32,  // Guest physical base for word 0
    uart_rx_data_pending: u32,         // UART RX byte available
    uart_rx_byte: u32,                 // UART RX byte value
    instr_len: u32,                    // Last instruction length (2 or 4 bytes)
    last_d2idx_d, last_d2idx_result: u32,  // Hilbert cache
    _pad: array<u32, 2>,
    // Basic-block threading counters
    bb_total_insts: u32,
    bb_ctl_insts: u32,
    bb_fallback_insts: u32,
    bb_threaded_insts: u32,
    bb_threading_enabled: u32,
}
```

Total: 30 u32 fields = 120 bytes

---

## Using the Harness

### 1. Quick Start: Boot xv6

```bash
# Minimal xv6 boot (already has a wrapper script)
python3 tools/boot_xv6_gpu.py --steps 100000000
```

This boots the xv6 RISC-V kernel on the GPU emulator and runs until ~100M instructions or halt.

### 2. Alpine Linux Boot with Live Monitoring

```bash
# Monitor Alpine boot in real-time
python3 tools/monitor_rv64i.py --program alpine \
    --steps-per-tick 200000 \
    --max-steps 500000000 \
    --out /tmp/rv64i_state.jsonl
```

**What this does:**
- Loads OpenSBI firmware → Alpine Linux kernel → DTB into GPU memory
- Runs in batches of 200K instructions per "tick"
- Prints live state: steps, steps/s, PC, mode, halted, trap, TLB stats, UART bytes
- Writes structured JSONL trace to `/tmp/rv64i_state.jsonl` for later analysis
- Warns on stalls (PC stuck with no UART output for 5+ ticks)

**Output format:**
```
     steps    steps/s                pc       mode halted trap    mcause    scause uart+ tlbH%      tlbH      tlbM
        200000    600000 0x800000000050         M     0    0       0x0       0x0   240 100.0        0         0
        400000    650000 0x800000000054         M     0    0       0x0       0x0   288 100.0        0         0
```

### 3. Stop on UART Message & Dump Memory

The most powerful debugging pattern: capture full guest memory at the exact moment a kernel error appears.

```bash
python3 tools/monitor_rv64i.py --program alpine \
    --stop-on-uart "broken padding" \
    --dump-mem /tmp/initrd_at_error.mem \
    --max-steps 700000000 \
    --steps-per-tick 1000000
```

**What happens:**
1. GPU emulator runs normally
2. UART output is accumulated on the host
3. When the substring `"broken padding"` appears in UART:
   - Execution halts immediately
   - Full guest memory is dumped to `/tmp/initrd_at_error.mem` (linear physical memory, 64MB)
   - Process exits with a status summary

**Analyzing the dump:**
```bash
# Extract initrd region (physical 0x82000000-0x8250b5e1)
dd if=/tmp/initrd_at_error.mem of=/tmp/initrd_dumped.bin \
    bs=1 skip=$((0x82000000)) count=$((0x50b5e2))

# Compare against source initrd
cmp -l /tmp/initrd_dumped.bin rv64_inflate_probe/initrd.gz.bin
```

### 4. Probe Isolation (Minimal Reproductions)

The `rv64_inflate_probe/` directory contains minimal ELF programs that exercise specific kernel code paths in isolation:

- **probe.elf**: Tests zlib inflate on the full real initrd
- **probe_cpio.elf**: Tests the CPIO parser on the decompressed output

```bash
# Run the inflate probe on GPU (should match QEMU golden)
cd rv64_inflate_probe
python3 run_probe_gpu.py --max-steps 200000000

# Expected output:
#   total_out: 11600900
#   out fnv1a: 0x8467f515c0c44ada
#   TRAILER!!!
#   PROBE DONE
#   RESULT: MATCHES QEMU GOLDEN
```

If a probe diverges, you have a tiny repro that runs in ~400M steps instead of a full boot's ~700M+ steps.

---

## Debugging Workflow

### Step 1: Monitor for UART Progress

```bash
python3 tools/monitor_rv64i.py --program alpine --out /tmp/alpine_boot.jsonl
```

Watch for:
- Kernel messages (`"Linux version"`, `"Unpacking initramfs"`)
- Errors (`"broken padding"`, `"write error"`, panic messages)
- Stalls (stop prints "!! STALL" if PC doesn't move for 5+ ticks with no UART)

### Step 2: Capture State at Failure Point

Once you identify where the boot fails, use `--stop-on-uart` + `--dump-mem`:

```bash
python3 tools/monitor_rv64i.py --program alpine \
    --stop-on-uart "broken padding" \
    --dump-mem /tmp/mem_at_failure.bin
```

### Step 3: Analyze Memory Dump

```bash
# Use the analysis script to find corruption
python3 tools/analyze_mem_dump.py /tmp/mem_at_failure.bin

# Or manually extract specific regions
dd if=/tmp/mem_at_failure.bin of=region.bin bs=1 skip=<offset> count=<size>
```

### Step 4: Compare Against Golden (QEMU)

Run the same boot pattern on QEMU and compare:

```bash
# QEMU boot (golden reference)
qemu-system-riscv64 -M virt -m 64M -nographic \
  -kernel /tmp/alpine_kernel.bin \
  -initrd /tmp/alpine_initrd.bin \
  -append "console=ttyS0" 2>&1 | tee /tmp/qemu_boot.log

# Compare UART output
diff -u <(grep -E "Unpacking|broken|panic" /tmp/qemu_boot.log) \
        <(grep -E "Unpacking|broken|panic" /tmp/gpu_boot.log)
```

### Step 5: Isolate with Probes

If the bug is in a specific code path (e.g., zlib inflate), build a minimal probe:

```bash
cd rv64_inflate_probe
./build.sh  # Builds probe.elf and probe_cpio.elf

# Run probe on both QEMU and GPU
qemu-system-riscv64 -M virt -nographic -kernel probe.elf | tee qemu_probe.log
python3 run_probe_gpu.py --max-steps 200000000 | tee gpu_probe.log

# Compare output
diff qemu_probe.log gpu_probe.log
```

---

## Advanced Features

### Basic-Block Threading

The emulator pre-decodes instructions on the host and uploads decoded metadata to the GPU, allowing the shader to execute pre-decoded ops instead of re-parsing bitfields every step.

**Status:** Enabled by default (`bb_threading_enabled = 1` in state init).

**Performance:** ~2.25x speedup on Alpine boot (1.58M vs 704K steps/s)

**To disable (for A/B control):**

```bash
python3 tools/monitor_rv64i.py --program alpine --no-threading
```

### TLB Instrumentation

The Sv39 TLB is instrumented with hit/miss counters in the shader:

```bash
python3 tools/monitor_rv64i.py --program alpine

# Output includes:
# tlbH%  (per-tick TLB hit rate)
# tlbH    (cumulative TLB hits)
# tlbM    (cumulative TLB misses)
```

**Baseline (Alpine boot, 120M steps):** 99.9% hit rate (39M hits / 33K misses)

### Custom ELF Loading

For bare-metal tests that aren't Alpine:

```bash
python3 tools/monitor_rv64i.py --program elf \
    --elf-path /path/to/your_program.elf \
    --ram-base 0x80000000 \
    --mem-size 16777216  # 16MB
```

### Trace Files for Diffing

```bash
python3 tools/monitor_rv64i.py --program alpine --trace-file /tmp/rv64i_trace.jsonl

# Later, diff against a QEMU trace:
diff_qemu_gpu_traces.py /tmp/qemu_trace.jsonl /tmp/rv64i_trace.jsonl
```

---

## Performance Characteristics

### Measured Performance (RTX 5090, Vulkan backend)

| Workload | Steps/s | Notes |
|----------|---------|-------|
| Alpine boot (threading ON) | 1.58M | 92.0% threaded, avg block 12.8 insts |
| Alpine boot (threading OFF) | 704K | Basic-block threading disabled |
| xv6 boot | ~1.0M | To shell prompt |
| Bare-metal inflate probe | ~400K | 5.29MB → 11.6MB decompression |

### Performance Milestones

| Commit | Change | Effect |
|--------|--------|--------|
| 2aee769 | Precomputed Hilbert LUT | 3.3x (181k → 600k) |
| 39ec634 | Sv39 TLB + sfence.vma fix | 1.33x; fixed deep-boot freeze |
| f0598eb | Basic-block threading | 2.25x (704k → 1.58M) |

### Bottlenecks

- **Host-GPU sync**: `get_state()` triggers a buffer read, which forces GPU dispatch completion. This is intentional for accurate timing.
- **State serialization**: Per-step writes to state buffer (PC, counters) hammer the same cache line.
- **GPU single-core**: The emulator is single-threaded on one GPU core; parallel lanes require divergent kernel design (future work).

---

## Known Issues & Limitations

1. **No FPU**: Only RV64I base integer set (no F/D extensions)
2. **No atomic ordering beyond LR/SC**: No full memory model for atomics
3. **Single-core**: Only one hart (no SMP)
4. **Timer only**: PLIC (interrupt controller) is minimal; timer interrupts work, external I/O interrupts are partial
5. **Performance**: ~1-2M steps/s vs ~100M+ steps/s for CPU QEMU — GPU is not faster for serial emulation, but is research platform for spatial/parallel designs

---

## File Reference

### Core Harness Files

| File | Purpose |
|------|---------|
| `tools/spatial_rv64i_cpu.py` | Python GPU interface (SpatialRV64ICore class) |
| `tools/monitor_rv64i.py` | Live state monitor + UART stop + memory dump |
| `tools/SPATIAL_RV64I.wgsl` | WGSL compute shader (fetch-decode-execute loop) |
| `pixel_emulator/src/hilbert.rs` | Hilbert curve d2xy implementation (Rust, for validation) |

### Probe Files (rv64_inflate_probe/)

| File | Purpose |
|------|---------|
| `probe.elf` | Bare-metal zlib inflate test |
| `probe_cpio.elf` | Bare-metal CPIO parser test |
| `run_probe_gpu.py` | Run probes on GPU |
| `initrd.gz.bin` | Real Alpine initrd (5.29MB) |
| `small.gz.bin` | Small test payload (342B) |

### Boot Scripts

| File | Purpose |
|------|---------|
| `tools/boot_xv6_gpu.py` | xv6 boot wrapper |
| `tests/standalone_alpine_boot.py` | Alpine boot loader (used by monitor) |

### Debugging/Analysis

| File | Purpose |
|------|---------|
| `tools/analyze_mem_dump.py` | Analyze memory dump for corruption |
| `tools/analyze_mem_dump_pages.py` | Page-by-page dump analysis |

---

## Example Debugging Session: Initramfs "Broken Padding"

This is a real case study from August 2026 (see `STATUS_RV64I_INITRD_PROBE.md`).

### Problem

Alpine Linux boot on GPU emulator failed with:
```
[    X.XXXXXX] Unpacking initramfs...
[    X.XXXXXX] Initramfs unpacking failed: broken padding
```

Same boot on QEMU succeeded without error.

### Hypothesis

Either:
1. GPU memory corruption (wrong bytes written/read)
2. Mis-executed instruction in zlib inflate
3. CPIO parser bug
4. MMU/TLB mapping divergence (kernel reads different bytes than written)
5. Memory overwrite of initrd region during early boot

### Debugging Steps

**Step 1: Isolate inflate with probe**

```bash
cd rv64_inflate_probe
./build.sh
python3 run_probe_gpu.py --max-steps 200000000
```

**Result:** MATCHES QEMU GOLDEN — inflate is correct, not the bug.

**Step 2: Isolate CPIO parser with probe**

```bash
python3 run_probe_gpu2.py probe_cpio.elf --max-steps 200000000
```

**Result:** CPIO RESULT: CLEAN — parser is correct, not the bug.

**Step 3: Capture memory at failure**

```bash
python3 tools/monitor_rv64i.py --program alpine \
    --stop-on-uart "broken padding" \
    --dump-mem /tmp/initrd_at_error.mem \
    --max-steps 700000000
```

**Step 4: Compare initrd region against source**

```python
import struct
from pathlib import Path

# Load dump
dump = Path('/tmp/initrd_at_error.mem').read_bytes()
# Extract initrd region (physical 0x82000000)
dump_initrd = dump[0x82000000:0x8250b5e2]

# Load source
source = Path('rv64_inflate_probe/initrd.gz.bin').read_bytes()

if dump_initrd == source:
    print("✓ Initrd bytes match source — GPU memory write path OK")
else:
    print("✗ Divergence — corruption detected")
```

**Result:** (As of STATUS doc: next step — awaiting memory dump)

### Conclusion (Status as of Aug 25, 2026)

Based on probe results, the bug is NOT in inflate or CPIO parsing. The kernel must be reading different bytes than we wrote — either an MMU/TLB translation divergence (VA → PA mapping mismatch) or an overwrite of 0x82000000 during early boot.

---

## Quick Reference: Common Commands

```bash
# Monitor Alpine boot
python3 tools/monitor_rv64i.py --program alpine --max-steps 500000000

# Stop on UART error and dump memory
python3 tools/monitor_rv64i.py --program alpine \
    --stop-on-uart "broken padding" \
    --dump-mem /tmp/mem.bin

# Disable threading (A/B control)
python3 tools/monitor_rv64i.py --program alpine --no-threading

# Run inflate probe
cd rv64_inflate_probe && python3 run_probe_gpu.py --max-steps 200000000

# Custom ELF
python3 tools/monitor_rv64i.py --program elf --elf-path test.elf

# Analyze memory dump
python3 tools/analyze_mem_dump.py /tmp/mem.bin
```

---

## Further Reading

- `PIXEL_GPU_COMPUTE_RECEIPT.md` — GPU compute architecture + xv6 boot verification
- `RV64I_STATUS.md` — Performance milestones + TLB analysis
- `STATUS_RV64I_INITRD_PROBE.md` — Current initramfs debugging session
- `STATUS_RV64I_LOOP.md` — Alpine boot stall investigation history
- `TLB_RECEIPT.md` — TLB implementation verification

---

**Last Updated**: 2026-08-25