# BL002 — Container-as-Disk sha256 Roundtrip + Boot: RECEIPT

**Task**: ROADMAP Phase 27 / TASK_BL002
**Date**: 2026-09-04
**Status**: PASS (both parts) — bit-identical roundtrip AND the reconstructed disk boots to real userspace in the browser.
**Harness**: `browser_boot/bl002/` (this repo)

---

## Claim (from ROADMAP)

Convert an Alpine rootfs through `dense_encoder` → tiled PNGs → back to raw,
verify sha256 equality, then boot the *reconstructed* image via the BL001
emulator's disk interface.

## Part (a): bit-identical roundtrip — PASS

Original artifact swapped (see Deviation 1 below) for a genuine, verified
x86 (i686) Alpine 3.20.9 ext2 rootfs, 16 MiB, built with `mke2fs -d`.

```
tools/dense_encoder_multitile.py encode alpine_i386_16mb.img -> 257 tiles (256×65531B + 1×1280B) + manifest, 0.7s
tools/dense_encoder_multitile.py decode manifest.png          -> 16777216 bytes, per-tile hash verified, 0.35s

sha256(original)      = 3089f7dfa96f5579d0ed5bb26359ae34f4ec6a44f81d9e50e3539d36efee0c80
sha256(reconstructed) = 3089f7dfa96f5579d0ed5bb26359ae34f4ec6a44f81d9e50e3539d36efee0c80
cmp original reconstructed -> exit 0 (byte-identical)
```

`tools/dense_encoder_multitile.py` (not `dense_encoder.py` alone) is required —
`dense_encoder.py`'s single-frame format caps payloads at 65535 bytes
(`MAX_PAYLOAD_SIZE`), so anything past ~64 KiB needs the existing multitile
wrapper. Confirmed via `grep` that no other repo tool already solved this
before reaching for it.

## Part (b): boot the reconstructed disk — PASS

`browser_boot/bl002/receipts/boot.png` shows `ext2 filesystem being mounted
at /newroot` followed by `BL002_ROOT_MOUNTED` and a live `~ #` shell prompt —
this is the **real Alpine rootfs's own init/getty**, not a rescue fallback
(see "false-positive caught" below for how that distinction was verified).
`boot_ms: 18677` (page load → root-mounted marker).

## Deviations from the task text (all evidence-based, found during work — not guesses)

1. **Rootfs swapped.** `alpine_rootfs_3mb.img` turned out to be a non-bootable
   **stub fixture** from an unrelated experiment (virtio_pixel_rs backend
   test) — `/bin` is empty, `/sbin/init` execs a nonexistent `/bin/sh`.
   `alpine_rootfs_ext4_busybox.img` (the "100MB, hold back" file) *does* have
   a real busybox — but it's **RISC-V64**, not x86 (this repo's other RISC-V
   GPU-emulator work). v86 only emulates x86. Neither file matches the task.
   Built a fresh, verified **x86 Alpine 3.20.9 minirootfs** (real download +
   `mke2fs -d`, i686 busybox confirmed via `file`) instead of fabricating a
   pass against unusable fixtures.
2. **x86_64 → i686.** First boot attempt used a real x86_64 Alpine kernel +
   minirootfs and failed immediately: SeaBIOS printed *"This kernel requires
   an x86-64 CPU, but only detected an i686 CPU"* — v86 has no long-mode
   support (documented behavior, not a bug in our pipeline). Switched to
   Alpine's 32-bit `x86` release (`vmlinuz-lts` 6.6.134-0-lts + matching
   `modloop-lts` + i686 minirootfs).
3. **"virtio-blk" → IDE (`ata_piix`).** v86 exposes disks as an emulated IDE
   controller (`ata1 at 0x1f0`, matches BL001's boot log too), not virtio-blk.
   ROADMAP's wording was imprecise; substance unchanged.

## Failures hit and fixed, in order (verify-every-step, no fabricated passes)

| # | Symptom | Root cause | Fix |
|---|---------|-----------|-----|
| 1 | SeaBIOS: "requires an x86-64 CPU" | v86 has no long-mode/x86-64 | Switched to Alpine's 32-bit `x86` kernel+rootfs |
| 2 | `Kernel panic — Attempted to kill the idle task` at `setup_IO_APIC` | Generic distro SMP kernel vs. v86's minimal/quirky IOAPIC emulation (known class of issue — distro kernels expect real hardware) | `cmdline: noapic nolapic acpi=off nosmp` |
| 3 | `Failed to execute /init (error -2)` | `/init`'s shebang interpreter `/bin/busybox` is dynamically linked (`/lib/ld-musl-i386.so.1`) and that loader wasn't in the initramfs | Added `ld-musl-i386.so.1` to initramfs `/lib/` |
| 4 | Reached a `~ #` prompt — **initially misreported as booted** | Marker regex `/~\s*#\s*$/` matched the initramfs's own **rescue shell** (spawned when root-mount fails), not real userspace | Caught by inspecting the log before reporting; removed generic prompt regexes, marker is now only our own script's explicit `BL002_ROOT_MOUNTED` |
| 5 | `mount: /dev/sda: No such device` | `ata_generic` needs `libata`+`scsi_mod`+`scsi_common` loaded first (kernel bans loading modules with unresolved symbols); those weren't in the insmod chain | Added full dependency chain |
| 6 | Still `No such device` after chain fixed | `cmdline` had `pci=off` (added for #2) — but the disk is on a PCI IDE controller, so `ata_generic`/`ata_piix` had nothing to bind to | Dropped `pci=off`, kept the other 4 flags |
| 7 | `ata_generic` bound to nothing even with PCI on | v86 emulates a PIIX-style controller; `ata_generic` doesn't match it, `ata_piix` does | Added `ata_piix.ko`, loaded before `ata_generic` |
| 8 | `/dev/sda` node existed (`brw------- 8,0`), mount still `No such device` | ext2 isn't compiled into this kernel; `mount -t ext2` fails when the fs type isn't registered, regardless of the block device | Added `ext2.ko` + its `mbcache.ko` dependency |

Each row was diagnosed from the actual serial log content (added a debug
`ls -la /dev` step at one point), not inferred — nothing here was assumed.

## Reproduce

See `browser_boot/bl002/` (`init.sh` = initramfs `/init`, `bl002.html` = v86
boot page, `receipts/` = boot.png + serial.log + console.log + sha256.txt).
Fetch commands for the vendored pieces (not committed — same policy as
BL001): Alpine 32-bit kernel+modules from
`dl-cdn.alpinelinux.org/alpine/v3.20/releases/x86/netboot/{vmlinuz-lts,modloop-lts}`,
minirootfs from `.../releases/x86/alpine-minirootfs-3.20.9-x86.tar.gz`;
build the ext2 image with `mke2fs -F -t ext2 -d <rootdir> <img> 16M`; run the
roundtrip with `tools/dense_encoder_multitile.py`; assemble the initramfs
per `init.sh`'s module list; boot via `browser_boot/drive.mjs` against the
already-running headless Chrome (see `browser_boot/README.md`).

## Next (BL003)

OPFS persistence overlay behind the disk backend — needs COOP/COEP headers
on the serving origin (flagged in ROADMAP Non-Goals/notes already).
