# rv32ima_nommu boot image

Prebuilt Linux 6.1.14 kernel for RV32IMA (NOMMU), from
[cnlohr/mini-rv32ima-images](https://github.com/cnlohr/mini-rv32ima-images)
(`linux-6.1.14-rv32nommu-cnl-1.zip`), with the matching device tree from
[cnlohr/mini-rv32ima](https://github.com/cnlohr/mini-rv32ima)
(`mini-rv32ima/sixtyfourmb.dtb`).

- `Image` — raw kernel image with an initramfs rootfs baked in. No separate rootfs
  file is needed.
- `sixtyfourmb.dtb` — device tree describing the `riscv-minimal-nommu,qemu` machine:
  64MiB RAM at `0x80000000`, a 16550 UART at `0x10000000`, and a `sifive,clint0` at
  `0x11000000`.

This is a **NOMMU** build — `satp`/Sv32 paging never engages, which is why it's a good
first real-world target for `SpatialRV32ICore`: booting it only exercises privilege
modes, CSRs, trap/interrupt handling, the CLINT timer, the 16550 UART, and native SBI
ecalls (see `tools/SPATIAL_RV32I.wgsl`), not the MMU.

Boot it with `python3 tools/boot_rv32ima_linux.py`. As of the last verified run, this
kernel boots all the way to `Run /init as init process` (mounts its own rootfs, brings
up the console) on the GPU-native emulator — userspace/`/init` execution itself is the
next thing to verify.
