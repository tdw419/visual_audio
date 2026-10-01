# GO-6 Layer 2 PRE-FLIGHT — kernel rebuild feasibility (2026-09-17, orchestrator cron af3e62239ce2)

Layer 2 clause: "Kernel rebuild: add CONFIG_VIRTIO_BLK (+ later VIRTIO_NET); root
stays the baked initramfs. Gate: vd0 appears from the emulated device + dd
round-trip through it." No builder attempt was spent on the build itself this
tick — this document is the measured pre-flight that decides WHICH tree the
layer must build from, and it settles the shipped-Image question by extraction.

## 1. The shipped Image is NOT rebuildable in place — config is absent

- `boot_images/rv32ima_nommu/Image` md5 `54e66d5e6634c5fcb5a9ca64b9203b0b`
  byte-identical to upstream `linux-6.1.14-rv32nommu-cnl-1.zip` (downloaded
  this tick to `/home/jericho/projects/zion/kernel-builds/`, md5 match).
- **No IKCONFIG**: `IKCFG_ST` magic absent from the binary → no embedded
  `.config` to extract.
- **No virtio_blk**: `strings` finds zero `virtio_blk`/`vd%c` markers —
  consistent with the Layer-1 receipt's strings-verified claim, re-measured.
- Toolchain: `riscv64-linux-gnu-gcc 13.3.0` compiles `-march=rv32ima
  -mabi=ilp32` fine (probe `/tmp/t.c` → RV32_OK). The 6.1.14 source itself is
  NOT in the zip (Image only) — it would need kernel.org + the cnlohr buildroot
  overlay (`cnlohr/mini-rv32ima` repo: `configs/custom_kernel_config` +
  buildroot 2023.02 uclibc toolchain). That is a full-buildroot lane, not an
  incremental rebuild.

## 2. The shipped Image's initramfs — EXTRACTED and measured (usable as-is)

The initramfs is an **uncompressed cpio baked into the Image** at offset
**1644484** through TRAILER at **3022806** (1,378,422 bytes; kernel `Image`
loader chunk handles it). Extracted this tick to
`/home/jericho/projects/zion/kernel-builds/initramfs/x/`:

- `/init` = busybox script → `mount devtmpfs` → `/sbin/init` (busybox).
- busybox is a **BFLT** executable (uclibc no-mmu userland — confirmed
  buildroot nommu). File count ≈ full rootfs (bin/sbin/etc/usr/var/lib).
- mknod of `dev/console` fails unprivileged on the host — expected; the cpio
  bytes are already correct as stored, extraction-side only.
- This directory is the "root stays the baked initramfs" material: a rebuilt
  kernel links THIS cpio (or a superset) via `CONFIG_INITRAMFS_SOURCE`.

## 3. The local `~/zion/linux-rv32` (6.10) tree is NOT a prepared L2 tree

- `# CONFIG_MMU is not set` (nommu) and `CONFIG_VIRTIO_BLK=y`,
  `CONFIG_VIRTIO_MMIO=y` present — looked promising.
- But the config is **incoherent**: `.config.old` carries
  `CONFIG_ARCH_RV64I=y` TOGETHER with `# CONFIG_64BIT is not set`, and
  `# CONFIG_NONPORTABLE is not set` with `CONFIG_RISCV_ISA_V=y` +
  `CONFIG_SOC_STARFIVE=y` — that is a 64-bit defconfig derivative, not an
  rv32ima-nommu kernel config.
- Measured twice: `make ARCH=riscv olddefconfig` **snaps 64BIT=y**
  (kconfig resolves the contradiction toward 64-bit), and `make prepare`
  then compiles `compat_vdso` (a 64-bit-only component). Neither the `.config`
  nor `.config.old` in that tree can produce the rv32ima nommu Image.
- Incidental repairs made to the tree this tick (tracked state clean, 0
  modified files after): restored 104 git-deleted files (including
  `drivers/nvme/target/Kconfig` and `drivers/target/Kconfig`, which broke
  kconfig parsing outright). `make prepare` left git-ignored generated
  headers under `include/generated`, `include/config` and a compat_vdso lds —
  deleted-untracked cleanup was blocked by the delete guard; any future build
  should `make mrproper` first. Nothing tracked changed.

## 4. Decision this pre-flight forces

Layer 2's mechanical content is: **(a)** obtain/build an rv32ima-nommu 6.x
kernel source tree whose config is coherent (6.1.14 vanilla + the cnlohr
custom_kernel_config with CONFIG_VIRTIO_BLK=y added is the minimal delta from
the proven-bootable artifact), **(b)** link the extracted §2 cpio as
INITRAMFS_SOURCE, **(c)** port the virtio-blk DATA path in
`tools/SPATIAL_RV32I.wgsl` (queue → descriptor walk → block read/write against
an emulated disk backing store — Layer 1 shipped enumeration only),
**(d)** gate: `vd0` in dmesg + dd round-trip byte-exact.

(b) and (c) are engine substrate work this repo owns. (a) is a toolchain lane
(buildroot or vanilla+config) that produces a ~3.5MB Image artifact. The
cheapest viable route for (a), pending a seat call: build vanilla 6.1.14 (or
6.10 from the local tree with a KNOWN-GOOD rv32 nommu fragment) with
`riscv64-linux-gnu-` cross tools — cnlohr's buildroot is only needed for the
uclibc/BFLT *userland*, which we already HAVE extracted (§2) and can re-bake.

## What this pre-flight did NOT do

- Did not build any kernel (attempt budget reserved; the (a) route is itself a
  seat-level choice between buildroot-faithful and vanilla-cross).
- Did not port any WGSL block-data-path code.
- Did not verify the extracted cpio boots (it is byte-identical material to
  what already boots inside the shipped Image, but no independent boot ran).
- Did not confirm 6.1.14 vanilla source availability beyond the repo-listing
  API call — no download was attempted.
