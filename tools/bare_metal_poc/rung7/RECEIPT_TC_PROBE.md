# RECEIPT — R7-TC-1: Tiny Core Linux booted from a pixel medium (shim-allowed evidence probe)

**Date:** 2026-09-18 (builder cron `af3e62239ce2`, tick started ~16:34 CDT)
**Row:** `systems/GLYPH_SELF_HOSTING_ROADMAP.md` R7-TC-1 (⏳ → ✅, evidence probe — NOT a ladder rung)
**Brief:** `.builder_queue/brief_r7tc1_tinycore_probe.md`
**Verdict: GATE GREEN — two consecutive medium-carried boots reached the `tc@box`
serial prompt; raw ISO never touched by QEMU except through PNG → nbdkit → NBD.**

## What booted

Tiny Core Linux (TinyCore-current.iso, core edition) where **every disk byte is
served by the rung-1 pixel machinery**: `tools/bare_metal_poc/pxc1_nbd_plugin.py`
under nbdkit decodes `tc_medium.png` (PXC1_BOOT_V1, one 4096×4096 RGBA plane)
on pread; QEMU attaches the NBD socket as an IDE CD-ROM (`media=cdrom`), SeaBIOS
does El Torito → isolinux → kernel+initramfs, all read from the pixel medium.

Success token (per brief): `tc@box` prompt on `console=ttyS0` serial capture.

## Hash pins

| artifact | sha256 | bytes |
|---|---|---|
| TinyCore-current.iso (final medium payload) | `c465424052643dc92e25861b8c019a38fe19bb6a1b906295f7af95a0cf3e3f88` | 28,135,424 |
| base iso (`/tmp/tc_iso_check/tc2.iso`) | `445dbb53de29b7e60660b713582bd9490370c933c2f8d2a39326ca05074de12d` | 18,874,368 |
| tc_medium.png (PXC1 payload = final iso) | `db4daa037d4233aacf663e6384d21262d75c51bb43826771eeddb425abdee69e` | — |
| iso2.norm == iso3.norm (normalized serial) | `aa44c97471c3bb0a34575ed34e5bd052830ee54b86a9496e8578ef06060043da` | 8,143 |

## Medium math

- Payload 28,135,424 B in one 4096×4096 RGBA plane (1 payload byte per byte of
  the 67,108,864-B plane, row-major, PXC1_BOOT_V1 dual-sha256 gates) → **41.9 %
  utilization**; at the stricter 3 bytes/pixel accounting that is 9,378,475 px,
  a ~3063-px square — a 4096² plane carries it either way.
- PNG wrapper retained (rung-1 pattern); raw-plane encode would be the
  fallback only if PNG scale had failed. It did not.
- **Measured nbdkit decode throughput at ISO scale: 18,525 KB/s** (full
  28,135,424 B through the NBD socket via `qemu-io -c 'read -v 0 28135424'`
  in 1.48 s; `throughput_probe.py`). Decode is not the bottleneck at this size.

## Gate evidence (brief gate clause 1–3)

1. **Receipt exists** (this file) with console log paths, sha256 pins, medium
   math, measured throughput.
2. **Two consecutive boots, byte-identical serial:**
   - boot 1: `rung7/iso2` (8,239 B), boot 2: `rung7/iso3` (8,204 B),
     both `PROMPT: tc@box seen`, QEMU rc=124 (bounded timeout, prompt-stop).
   - Normalization (PIDs in `login[NNN]:` lines and which ttys raced to print
     the login line vary boot-to-boot): strip `\r`, drop `login[..]` lines →
     `iso2.norm`/`iso3.norm`, **`cmp` rc=0, sha256 both `aa44c974…`**
     (`/tmp/r7_diff.txt` holds the raw 126-byte diff — the ONLY variation).
     Raw diff pasted:
     ```
     21,22c21
     < login[915]: root login on 'tty1'\r\r
     < login[916]: root login on 'ttyS0'\r\r
     ---
     > login[922]: root login on 'ttyS0'
     ```
3. **Gate can fail (measured):** every leg between 16:14 and 16:33 in the
   previous tick produced 0-byte serials (dead legs, `serial_tc1.log` …
   `serial_kernel.log` all 0 B) because the then-current ISO's vmlinuz64 was
   corrupt — see root cause below. That is the RED the green is measured
   against: same pipeline, corrupt kernel → silence; fixed kernel → prompt.

## Root cause found this tick (supersedes DIAGNOSIS items 3–4)

`patch_serial_console.py` (16:13) computed the core.gz rewrite region with a
decompress loop that checked `eof` AFTER advancing its position, so it measured
the gzip member as 9,437,184 B (the 2048-rounded *decompressed-consumption*
window) instead of the true 9,131,528 B member + pad ending exactly at
vmlinuz64's extent start (byte 9,248,768). The level-9 re-compressed stream
(9,260,807 B — TinyCore's original stream is not zlib-9, so the grown inittab
could not fit in place; measured floor across levels 6–9) **spilled 128,775
bytes over vmlinuz64's head**, leaving `il…` where `MZ` belongs. isolinux then
loaded a corrupt kernel: every post-16:13 medium boot died pre-output with 0
serial bytes. Pixel layer fully exonerated (DIAGNOSIS item 1 stands).

Fix (`repack_v3.py`, asserts vmlinuz head MZ, member round-trip, cfg round-trip,
extent disjointness):
- base = pristine-layout iso `445dbb53…` (initramfs unpadded, kernel intact);
- new gzip stream with the `ttyS0::respawn:…getty` line **appended at the END
  of the image** (new extent 9216), only the `CORE.GZ;1` directory record
  extent/size patched — one record, old region zeroed;
- `isolinux.cfg` patched in its extent: `SERIAL 0 115200` first line,
  `console=ttyS0,115200` appended to APPEND lines lacking it (1,445 → 1,546 B,
  dir size updated).

## HONEST BOUNDARY

- **Shim-allowed, labeled as evidence, exactly as the row requires:** disk
  reads flow PNG → nbdkit → NBD. The kernel+initramfs are loaded by isolinux
  FROM that disk, so the boot media path is pixel-served; but the decode is a
  HOST process (nbdkit + Python plugin), not loader-side decode. This advances
  the evidence case (a real OS runs with pixels as its only disk) — it does
  NOT advance the loader-side-decode thesis (that is rung 8 / Path-A-at-scale).
- Normalization for the byte-identical bar drops `login[..]` lines: busybox
  login embeds its PID and the tty that won the race — runtime scheduler
  output, not medium or decode nondeterminism. Everything else (kernel banner
  through prompt) is byte-identical across boots from the same medium.
- `boot_probe.sh` runs QEMU under `timeout` (90 s default) and the boot
  self-terminates at the prompt only via grep-after-the-fact; rc=124 is the
  bounded-timeout signature, the serial log is the verdict channel.
- Not done: ECC, hardware, loader-side decode of multi-MB payloads, extension
  boot (tcz) beyond what rcS did automatically, `waitusb` variants.
- The in-ISO core.gz in TinyCore overlaps nothing after repack_v3; the corrupt
  iso (`0a3494de…`) was overwritten on disk by the fixed one (`c4654240…`) —
  the corrupt bytes are reproducible from `repack_v2.py`-class in-place splicing
  if anyone needs the RED artifact again.
- Throughput measured with qemu-io (1.48 s wall for the full medium) —
  plugin-level decode dominates; a per-request latency profile was not taken.

## Files (rung7/ — uncommitted per TASK_BM001 hold)

New this tick: `repack_v3.py`, `validate_repack.py`, `throughput_probe.py`,
`iso2`, `iso3`, `iso2.norm`, `iso3.norm`, refreshed `TinyCore-current.iso`,
`tc_medium.png`. Roadmap R7-TC-1 status cell updated by the orchestrator.
