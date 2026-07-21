# GPU RISC-V Emulator — xv6 Boot Receipt

**Date**: 2026-07-20
**Status**: ✅ COMPLETE
**Milestone**: xv6-riscv boots to shell prompt on GPU (WebGPU compute shader)

---

## What Was Achieved

The GPU-native RISC-V emulator (`tools/RISCV_CPU_MMU.wgsl`) successfully boots a complete operating system kernel:

- xv6-riscv (MIT educational OS)
- Executes 100M instructions in WGSL compute shader
- UART console output: "init: starting sh" followed by interactive `$` shell prompt
- All OS functionality working: disk I/O, process scheduling, interrupts

---

## Boot Output

```
======================================================================
UART CONSOLE OUTPUT
======================================================================

xv6 kernel is booting

init: starting sh
$
======================================================================
Final PC: 0x0000000080001080
Instructions executed: 99999934
CPU running: 1
======================================================================
```

---

## Critical Bug Fix: UART Interrupt Injection

**Problem**: init process hung forever waiting for UART transmit interrupt

The kernel's `uartwrite()` function:
1. Writes character to THR (Transmit Holding Register)
2. Sets `tx_busy = 1`
3. Calls `sleep()` waiting for UART IRQ
4. Never woke up because emulator never fired the interrupt

**Root Cause**: GPU emulator lacked UART0_IRQ (Interrupt 10) injection

**Fix** (in `tools/RISCV_CPU_MMU.wgsl`):
1. Added `uart_irq_delay: u32` field to RiscvCPU struct
2. On UART_THR write: capture character to output buffer, set delay = 5000 cycles
3. Main loop decrements delay, fires PLIC IRQ 10 when hits 0

**Result**: init wakes up, loads from disk, spawns shell, reaches interactive prompt

---

## Vendor xv6-riscv Customizations

The xv6 source requires patches for GPU execution:

1. **Remove C extension** (Makefile line 95)
   - Change: `-march=rv64gc` → `-march=rv64ima_zicsr_zifencei`
   - Why: WGSL emulator implements RV64I + M only, no compressed instructions

2. **Reduce memory to 16MB** (kernel/memlayout.h line 40)
   - Change: `PHYSTOP (KERNBASE + 128MB)` → `PHYSTOP (KERNBASE + 16MB)`
   - Why: Boot harness uses fixed memory buffer

**Location**: `vendor/xv6-riscv/patches/`

---

## Verification Command

```bash
cd /home/jericho/projects/zion/projects/visual_audio
python3 tools/boot_xv6_gpu.py /tmp/xv6-riscv/kernel/kernel
```

Expected output: xv6 boot sequence ending with `$` shell prompt

---

## Architecture

### GPU Memory Layout
- Host allocates a 128MB physical address window (33554432 4-byte words,
  536MB of actual VRAM since each byte-channel is stored as its own u32)
- The xv6 kernel itself is patched to PHYSTOP=16MB (see Vendor
  Customizations below) - the rest of the 128MB window is allocated but
  unused headroom, not a hard requirement
- Physical base: 0x80000000 → word index 0
- fs.img loaded at 0x81000000 (16MB offset, just past PHYSTOP)

### CPU State (WGSL struct)
- 64-bit PC and registers (vec2<u32>: low, high)
- RV64I + M extension integer instructions
- SV39 MMU (3-level page table walk)
- PLIC interrupt controller (IRQ 0-31)
- VirtIO block device (IRQ 1)
- UART with delayed interrupt (IRQ 10)

### Instruction Set Implemented
- Base: RV64I (load/store, arithmetic, branches, JAL/JALR)
- Extension: RV64M (MULH, MULHSU, MULHU, DIV, DIVU, REM, REMU)
- CSR access (CSRRW, CSRRS, CSRRC)
- System instructions (ECALL, SRET, WFI)
- A-extension: LR/SC (Load-Reserved/Store-Conditional)

---

## Performance

- 100M instructions executed in ~10 seconds (10 MIPS)
- GPU: NVIDIA GeForce RTX 5090 Laptop GPU
- Compute shader: single workgroup (1 thread)
- Memory: 512MB VRAM for 128MB physical memory

---

## Test Suite

**Status**: All regression tests passing (verified 2026-07-20)

These are standalone GPU harness scripts, not pytest-discoverable (each
creates its own WebGPU device and runs to completion) - run each directly:
```bash
python3 tests/test_csr_m_extension.py   # M/CSR register operations, traps
python3 tests/test_a_extension.py       # A-extension atomics (LR/SC, AMOs)
python3 tests/test_smode_sbi.py         # S-mode/SBI trap + delegation handling
python3 tools/test_mmu_gpu.py           # SV39 page table walk
```

---

## Dependencies

- wgpu (WebGPU Python bindings)
- numpy (for memory pixel encoding)
- A riscv64 cross-compiler (verified with `riscv64-linux-gnu-gcc`; pass
  `TOOLPREFIX=riscv64-unknown-elf-` to `vendor/xv6-riscv/build.sh` if
  using that toolchain instead)

---

## Next Steps

This milestone enables:
1. Full OS boot testing on GPU
2. Geometry OS hypervisor integration (spatial RISC-V)
3. GPU-native OS kernels without host dependency
4. Spatial security research (guest isolation via GPU)

---

**Commit**: 18e6d83 (fix(gpu-riscv): PLIC/VirtIO interrupt injection)
**Commit**: 650ff17 (feat(vendor): Add xv6-riscv patches and build script)
**Commit**: 7172eda (fix(vendor): make build.sh actually reproduce the verified boot -
the original script crashed immediately on a clean run and its C-extension
patch didn't apply; regenerated both patches from a real diff and verified
end to end against a fully clean checkout)