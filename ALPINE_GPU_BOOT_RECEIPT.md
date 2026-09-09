# Alpine Linux boots on the GPU RV64 core — 2026-08-29

## Result

`tools/SPATIAL_RV64I.wgsl` (via `SpatialRV64ICore`) boots the Alpine RISC-V
kernel from the OpenSBI handoff through **full kernel init** to the VFS
root-mount panic — i.e. everything up to the point a block device is needed.

Reproduce (host, real GPU adapter — not llvmpipe):

```bash
python3 tools/boot_alpine_gpu_fixed.py --max-steps 1400000000 --batch 5000000
```

Milestones (`receipts/alpine_gpu_boot_2026-08-29.log`):

```
[    0.000000] Linux version 6.12.31-0-lts ... #1-Alpine SMP PREEMPT_DYNAMIC
[    0.000000] Machine model: visual-audio,gpu-riscv-pixel-machine
[    0.000000] SBI specification v3.0 detected
[    0.000000] earlycon: uart8250 at MMIO 0x0000000010000000
[    0.262132] smp: Brought up 1 node, 1 CPU
[    0.269785] Memory: 28940K/65536K available (8169K kernel code, ...)
[    2.118197] Unpacking initramfs...
[   33.608146] Freeing initrd memory: 5164K
[   47.504240] riscv-pmu-sbi: 16 firmware and 31 hardware counters
[   53.724800] Loaded X.509 cert 'alpinelinux.org: Alpine Linux kernel key: ...'
[   55.128189] Kernel panic - not syncing: VFS: Unable to mount root fs on unknown-block(0,0)
```

QEMU boots the same kernel image (`/tmp/p1/kpe.bin`, extracted from
`boot_images/alpine_riscv64.lnx.bin`) with the same OpenSBI `fw_jump.bin`;
the GPU core now matches it through kernel init.

## What was broken (both GPU-side, not kernel bugs)

### 1. `write_mem_bytes` large-write corruption — `tools/spatial_rv64i_cpu.py`

The chunked copy-shader (`dest[hilbert_idx] = src[i]`, inline `d2xy`) scrambled
writes larger than 64 KB: sparse, word-level. On the 20 MB Alpine kernel image
roughly one word in four came back **zeroed or shifted to a neighbouring
cell**. The kernel's `head.S` (BSS clear, boot-arg save around `0x802010f2`)
fetched a zeroed word, took an illegal-instruction trap (`mcause=2`), and —
since `medeleg` doesn't delegate illegal-instruction — bounced into OpenSBI's
M-mode handler forever. Zero kernel output.

Fix: scatter linear words into their Hilbert cells through `hilbert_lut_np`
(the exact LUT the shader reads memory back through) and upload the whole
buffer once. ~3 s per large write; a boot does three (kernel / initrd / DTB).
Commit `76e102b`.

### 2. DTB placement — `tools/boot_alpine_gpu_fixed.py` (new)

OpenSBI's `fw_jump` hands the kernel `a1 = 0x82200000` (its compiled-in
`FW_JUMP_FDT_ADDR`, printed as `Domain0 Next Arg1`). The existing boot scripts
wrote the DTB at end-of-RAM (`RAM_BASE + RAM_SIZE - len(dtb)`), so the kernel
parsed garbage as its device tree. `boot_alpine_gpu_fixed.py` writes the DTB at
`0x82200000` — free space between the kernel (ends `0x815e3000`) and the initrd
(`0x82800000`) — and sets `a0 = 0`, `a1 = 0x82200000` for OpenSBI's own entry.

## Diagnosis path

1. UART showed the full OpenSBI banner, then nothing; PC oscillated in the
   OpenSBI text region (`0x80008xxx`).
2. Fine single-stepping across the handoff: fetched instruction at
   `0x802010f2` read as `0x00000000` — but QEMU's `-d in_asm` had
   `013e1717 auipc a4` there.
3. Bulk readback + numpy diff of GPU RAM vs the kernel file: sparse word
   mismatches near `0x802010f0` (zeroes / neighbour-shifts), pages at 4 KB
   boundaries clean → large-write path.
4. `_d2xy` and `hilbert_lut_np` agreed perfectly → the bug was the chunk
   copy-shader itself, not the mapping. Bypassed it.

## Still open (Route B Phase 3 → shell)

The panic is the "needs a block device" state Route B's host-served virtio-blk
is for. `tools/boot_offload_alpine.py` now uses the fixed loader plus
`root=/dev/vda rootwait` and `run_with_offload` (no longer capped at 250 M
steps). Outstanding:
- confirm `virtio_mmio` / `virtio_blk` actually probe the DTB
  `virtio_mmio@10001000` node (the plain boot shows zero virtio log lines).
- `run_with_offload`'s loop is slow — `read_uart_output()` does per-byte GPU
  readbacks; needs a bulk drain before long boots are practical.
