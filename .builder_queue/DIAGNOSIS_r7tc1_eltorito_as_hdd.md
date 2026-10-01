# DIAGNOSIS — R7-TC-1: El Torito image presented as hard disk (measured RED, pixel layer exonerated)

> **SUPERSEDED 2026-09-18 ~17:00 — see `tools/bare_metal_poc/rung7/RECEIPT_TC_PROBE.md`.**
> The row CLOSED GREEN without this file's fix plan: the dead legs were an
> in-place core.gz repack spilling 128,775 B over vmlinuz64's extent head
> (corrupt kernel head — `il` where `MZ` belongs), and the boot that went
> green used `media=cdrom` presentation (El Torito), dissolving the
> hdd-presentation question entirely. Option A/B below were never needed:
> the host sector-0 check had already shown the ISO isohybrid-complete.
> The serial recipe in the 16:35 update (item 3) IS what the fix used.
> Items 3–4 of the update are superseded by the receipt's root cause.

**Status:** diagnosis staged 2026-09-18 ~15:57, mid-tick (started 15:53:40).
Written by host Hermes from the tick's own artifacts; the live tick owns the
scratch tree — this file is context for whoever closes the row.

## Measured observations (all from tools/bare_metal_poc/rung7/)

1. **Pixel decode path fully functional at 18 MiB scale.** SeaBIOS via
   nbdkit+plugin reports `drive 0x000f5200: PCHS=36/16/63 ... s=36864`
   (debugcon.log) = 36864×512 = 18,874,368 B = the ISO's exact size, seen
   through PNG→pixels→NBD. Geometry falsifiably matches; the medium holds.
2. **NBD boot leg:** SeaBIOS `Booting from Hard Disk...` →
   `Booting from 0000:7c00` (debugcon.log tail), then silence — correct:
   LBA0 of the medium is a raw copy of the ISO's sector 0 (`33 ed 90 90...`,
   55AA present per dd), which is isolinux's CD-entry code, not an MBR that
   can find a hard-disk volume. Execution of it as an MBR goes nowhere
   observable. All serial logs (serial_tc1/tc2/iso_direct) are 0 bytes.
3. **Direct-ISO control leg fails the same way, different reason:**
   `Boot failed: could not read the boot disk` → `Booting from DVD/CD...`
   (debugcon_iso.log tail). Control leg confirms the failure is image-format
   presentation, not decode.
4. Medium math: 18,874,368 B payload in one 4096×4096 RGBA plane-set
   (64 MiB capacity, 1B/medium-byte packing) — ~29% utilization. Headroom
   is not the constraint.

## Diagnosis

Plain El Torito ISO ≠ bootable hard disk. This is the classical failure any
raw-ISO-as-hdd setup hits, independent of pixels. Not a decode defect, not a
plugin defect, not a gate failure.

## Fix (classical, ~30 lines in mk_medium.py)

- Option A (isohybrid-style): write an isolinux hybrid MBR into LBA0 of the
  MEDIUM (do not mutate the archived ISO), with the ISO payload at its
  existing offset (likely 0 — the ISO's own sector 0 already carries the
  hybrid code; verify the Syslinux version's hybrid layout before assuming
  the isohdpfx bytes are present and complete).
- Option B (max control): fresh MBR + single partition entry (type 0x0B/0x83,
  bootable) pointing at the ISO payload placed at a sector-aligned offset
  (e.g. LBA 63), stage1 reads the partition table... — only if A fails;
  A is the minimal delta.

## The trap to watch (sector-boundary discipline)

Hybrid layouts care where partition boundaries land relative to the El
Torito catalog and the ISO9660 volume descriptors (first 32 KiB of the
image, including the primary VD at sector 16). Off-by-one-sector symptoms
look like PROGRESS — SeaBIOS finds an MBR and jumps — but isolinux then
can't locate its own volume: a NEW silence, not the OLD silence. Distinguish
legs by debugcon, not serial presence alone. The brief's two-consecutive-
byte-identical-boots gate is the right green bar.

## Pointer for the NEXT rung (record now, brief later)

Before writing any stage2→kernel handoff code (BM-504 or successor to
BM-503D): build the oracle FIRST. Conventional QEMU + real Linux boot, dump
the real firmware/chainloader's `boot_params` + cmdline, and diff the
emulator-constructed tables field-by-field against that dump. The failure
mode of a wrong boot_params is a silent hang or triple-fault with no
diagnostic — mismatches must surface as diffs, not hangs. (Same discipline
as the rung2 CMP/JZ gate and today's corruption tests: assert the expected
mechanism.)

## Scope note

rung7/ is currently UNCOMMITTED (?? in git status) per the BM001 hold on
landing bare_metal_poc — closing the row means landing the RECEIPT + roadmap
cell per the amended brief, not committing the scratch tree.

## Measured update — host observation 2026-09-18 16:35 (post 15:53→16:34 tick)

Written by host Hermes from the tick's own artifacts; the tick owns the row.

1. **The classical blocker is DEAD — superseded by measurement.** At
   16:07:57 the medium-carried boot ran FULLY through the pixel decode
   path: isolinux loaded the kernel + initramfs off the hdd-presented
   medium, TinyCore userspace came up end-to-end (serial_tc1.log 840 B:
   kernel banner, udev, extensions, `root login on 'tty1'`). "isolinux
   can't locate its volume when presented as hdd" did not happen. The
   remaining gap is NOT booting — it is a deterministic serial receipt
   channel (the 16:07 console was split tty1/ttyS0; green bar needs ×2
   byte-identical serial).
2. **Sector-0 sanity check done (16:15, host):** TinyCore ISO LBA0 is
   already a complete isohybrid layout — `33 ed` code start, 55AA,
   entry1 = 0x80/0x17, start_lba=0, count=36864 (exact image size),
   entries 2-4 zero, PVD intact at sector 16. Option A's MBR injection
   is NOT needed; don't spend a leg on it.
3. **Serial-determinism attempts so far (all 0 B serial):** inittab/getty
   patch leg 16:14 (died pre-kernel output — real-mode death in int log;
   the core.gz repack is the suspect — validate with `cpio -t` before
   the next repack leg), direct/-kernel legs 16:24-16:30, extracted
   vmlinuz+core.gz pivot 16:33 (serial_kernel.log empty, tick ended).
   Recipe that should close it on TinyCore 10.1: isolinux.cfg first
   line `SERIAL 0 115200`; APPEND `console=ttyS0,115200 console=tty0`
   (LAST console= gets /dev/console); inittab add
   `ttyS0::respawn:/sbin/getty -L ttyS0 115200 vt100`.
4. **Boundary for the gate:** the extract-kernel/-append legs are
   DIAGNOSTIC ONLY (isolate serial config from medium decode). Gate legs
   must remain medium-carried end-to-end: nbdkit+plugin as the only
   disk, isolinux from the medium, ×2 byte-identical serial.
