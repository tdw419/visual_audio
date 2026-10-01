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

## GUI desktop boot (TASK_C041 — audio → VNC-reachable desktop)

The `gui` boot option (x86_64 only) boots `image` itself as a qcow2 disk with
a VNC display (`:1`, i.e. `127.0.0.1:5901`) instead of direct-kernel-booting
it. `snapshot=on` is always forced for gui boots, so a signed manifest can
never persist changes to the trusted disk image on disk.

```
["boot", "x86_64", "arch_desktop.qcow2", {"gui": true}]
```

- **arch_desktop.qcow2** (not committed — third-party, git-ignored like
  xv6.img/fs.img) — a pre-built Arch Linux x86_64 image with a full desktop
  environment and display manager already installed. Substituted for the
  original "Ubuntu Desktop" wording: a genuine riscv64 Ubuntu desktop image
  wasn't available/buildable in this environment (only a corrupt 0-byte
  placeholder existed), and root disk space was too constrained (3.5G free)
  for a multi-GB build; an existing, valid x86_64 image with a desktop
  already installed was substituted instead. Place your own qcow2 disk image
  (any x86_64 Linux with a display manager) at this path to reproduce.

Reproduction steps:
1. Place a bootable x86_64 qcow2 disk image with a desktop environment at
   `boot_images/arch_desktop.qcow2`.
2. Send (or directly call) the boot op above through the signed-audio
   listener path, or directly via `tools/boot_manifest.py`'s `launch_boot()`.
3. Connect a VNC client to `127.0.0.1:5901` (e.g. `vncviewer localhost:1` or
   `vncdotool -s localhost:1 capture screenshot.png`) once the guest has
   booted (~30-60s to a login screen on modest hardware).

Verified end-to-end: `launch_boot(["boot", "x86_64", "arch_desktop.qcow2",
{"gui": true}], image_dir="boot_images")` launches real QEMU, VNC is
reachable at `127.0.0.1:5901`, and a full graphical desktop (taskbar,
applications menu, file manager) is visible after login. Receipt screenshot:
`docs/receipts/task_c041_desktop_vnc.png`.
