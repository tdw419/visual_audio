# Level 2 — zero-disk xv6 boot from pixels — RECEIPT

**Date:** 2026-08-30
**Status:** VERIFIED — xv6 boots to the interactive `$` shell prompt with the
emulator shader, the kernel ELF, and the filesystem image all sourced from
SHA-256-verified pixel frames. No boot input read from disk.

## What runs

`emulator_v2/run_checkpointed.py`:
1. `emulator_frame.png` (fmt 1) -> 141,260 bytes WGSL. Byte-identical to
   `tools/RISCV_CPU_MMU.wgsl` (verified: same SHA-256 `c8ddb261...`).
2. `kernel_frame.png` (fmt 2) -> 288,944-byte xv6 RISC-V kernel ELF.
   SHA-256 checked against the frame header before use.
3. `fs_frame.png` (fmt 3) -> 2,048,000-byte fs.img, loaded at guest PA
   0x81000000 (where the shader's virtio-blk model reads sectors from).
4. Boots on the GPU (wgpu compute), 2,000,000 instructions per dispatch,
   draining the UART ring each dispatch.

## Verified boot output (emulator_v2/v2_pixel_uart.log)

```
xv6 kernel is booting

init: starting sh
$
```

- `init: starting sh` at ~20,000,000 instructions.
- `$` prompt at ~22-24,000,000 instructions (varies slightly per run).
- Wall time: a few minutes on the host iGPU (mesa i915, "skylake derivative").
- Reproduced 3x: pixel-shader + disk kernel/fs; pixel-shader + pixel
  kernel/fs; all after a clean checkpoint wipe.

## Oracle cross-check

`qemu-system-riscv64 -machine virt -bios none -kernel <same kernel> -m 128M
-smp 3 -global virtio-mmio.force-legacy=false -drive
file=fs.img,if=none,format=raw,id=x0 -device
virtio-blk-device,drive=x0,bus=virtio-mmio-bus.0` boots the same kernel+fs
to `$` in <40s. Confirms the kernel/fs are correct and the pixel path
reproduces real behaviour.

## Corrections to the earlier (withdrawn) Level 2 receipt

The previous version of this file claimed "COMPLETE" off a run that stopped at
2,000,000 instructions showing only `xv6 kernel is booting`. That is ~10x
short of `init: starting sh` and ~12x short of `$` — it never reached a
shell. Its "N instructions" figures were the driver printing
`dispatch_count * batch_size`, not the emulator's real retired-instruction
count. `boot_from_pixels.py` also unpacked fs.img from a frame and then threw
it away (the boot function read a hardcoded `/tmp/xv6-riscv/fs.img`).

`run_checkpointed.py` is the canonical Level 2 entrypoint. It reads the real
`instr_count` from the CPU struct, sources all three inputs from frames, gates
on the actual `$` string in the UART ring, and checkpoints full emulator
state (18 MB guest RAM + CPU struct + UART ring) to `~/xv6_pixel_boot.ckpt.npz`
so a run survives this sandbox's ~1h process reaping and intermittent
GPU-dispatch hangs.

## Not yet done

- `boot_from_pixels.py` still has the fake instruction counter and the
  dis-used fs unpack; either fix it to call the `run_checkpointed` path or
  delete it. It is NOT a valid Level 2 proof as written.
- Pack the three frames into `visual_audio.mkv` (VAC1) for single-file
  distribution.
- The 2026-08-25 memory's "shell at ~1.7B instructions / 15x slow" figure
  does not match this run (~22M). Likely that run used the `boot_xv6_gpu.py`
  path (HybridKernelLoader, UEFI trampolines, blind UART monitoring that
  only prints output when `--command` is passed) rather than the lean
  `boot_xv6_gpu_v2_simple` path used here.
