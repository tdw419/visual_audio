# boot_images/

Bootable images for the signed boot manifest (see `tools/boot_manifest.py`,
TASK_C033). A signed `["boot", arch, image, {opts}]` op decoded from audio
launches QEMU with the named image from this directory.

## Committed demo kernels (built from `src/`)

Build with `make -C boot_images/src` (needs `riscv64-unknown-elf-gcc`):

- **hello.img** — S-mode kernel loaded by OpenSBI at `0x80200000`, prints via
  SBI. Boot with the default firmware:
  `["boot", "riscv64", "hello.img"]`
- **bare.img** — M-mode kernel at `0x80000000` that prints via the raw NS16550
  UART, for the `-bios none` path:
  `["boot", "riscv64", "bare.img", {"bios": "none"}]`

## Real xv6 (not committed — build it yourself)

xv6-riscv is third-party (MIT PDOS). It is git-ignored here; build and drop it in:

```sh
git clone --depth 1 https://github.com/mit-pdos/xv6-riscv /tmp/xv6
make -C /tmp/xv6 TOOLPREFIX=riscv64-unknown-elf- kernel/kernel fs.img
cp /tmp/xv6/kernel/kernel boot_images/xv6.img
cp /tmp/xv6/fs.img        boot_images/fs.img
```

xv6 carries its own machine-mode boot code and needs its filesystem disk, so it
boots to a shell via the `bios` + `drive` options:

```
["boot", "riscv64", "xv6.img", {"bios": "none", "drive": "fs.img"}]
```

Verified end-to-end: a signed spoken "boot xv6" command boots to
`init: starting sh` and the `$` prompt.
