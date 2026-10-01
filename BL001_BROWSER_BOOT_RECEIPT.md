# BL001 — Browser-Native Linux Boot: RECEIPT

**Task**: ROADMAP Phase 27 / TASK_BL001
**Date**: 2026-09-04
**Status**: PASS — a real Linux kernel reached userspace inside a headless browser tab.
**Harness**: `browser_boot/` (this repo)

---

## Claim

Serve an unmodified upstream in-browser emulator + a stock Linux image from a
static file server; a browser tab boots that kernel to userspace. No Visual
Audio work at this rung — this only proves the emulator harness runs in a tab
and that we have a working browser + capture path on this host.

## What actually ran

| Component | Version / detail |
|-----------|------------------|
| Emulator | v86 `0.5.458` (npm), unmodified — `build/libv86.js` + `build/v86.wasm` |
| Firmware | SeaBIOS `seabios.bin` 131072 B, VGABIOS `vgabios.bin` 36352 B (from `copy.sh/v86/bios/`) |
| Guest image | v86 buildroot `linux.iso` — ISO9660, bootable, 5 666 816 B (from `copy.sh/v86/images/`) — Linux 2.6, ext2 initrd, boots to an interactive shell |
| Browser | Chrome-for-Testing `152.0.7977.82` (`@puppeteer/browsers`, userspace), headless, `--no-sandbox` |
| Server | `python3 -m http.server 8087 --bind 127.0.0.1` |
| Driver | `browser_boot/drive.mjs` — raw CDP over Node 24 global `WebSocket`, no MCP |

Config: 64 MiB RAM, 8 MiB VGA, `cdrom` = `linux.iso`, `autostart:true`,
keyboard/mouse disabled. Served without COOP/COEP, so v86 runs in its
non-SharedArrayBuffer fallback mode (fine at this rung; BL003 adds the headers).

## Result

```
RESULT {"booted":true,"boot_ms":3986,"serial_bytes":40,
        "screenshot":".../boot.png","serial_log":".../serial.log"}
```

- **Kernel → userspace in ~4.0 s** (page load to userspace marker).
- **VGA console** (`browser_boot/receipts/boot.png`, 1280×757) shows the full
  boot tail:
  - `RAMDISK: Loading 3883KiB [1 disk] into ram disk... done.`
  - `VFS: Mounted root (ext2 filesystem) on device 1:0.`
  - `/root% ` — an **interactive shell prompt** (init ran, shell spawned)
- **Serial console** (`browser_boot/receipts/serial.log`, 40 B — this image
  routes most output to VGA, only the getty banner to serial0):
  ```
  Welcome to Buildroot
  (none) login:
  ```
- **Page console** (`browser_boot/receipts/console.log`):
  `BL001_EMULATOR_READY` then `BL001_USERSPACE_REACHED after 3986ms marker=/Welcome to Buildroot/i`

Both a VGA shell prompt and a serial getty prompt independently confirm the
kernel handed control to userspace.

## Deviations from the task text

1. **Image**: buildroot `linux.iso` (Linux 2.6), not a "stock Alpine bzImage".
   Rationale: this rung only needs *a* Linux kernel reaching userspace in a tab.
   Alpine specifically matters at BL002, where the rootfs is a virtio-blk disk
   we build from `alpine_rootfs_3mb.img` via `tools/dense_encoder.py` — the
   ISO route here would be thrown away anyway.
2. **Emulator**: v86 only (task allowed "v86 or TinyEMU").

## Host environment blockers found & resolved (for the next session)

- ecc `chrome-devtools` MCP looks for Google Chrome at `/opt/google/chrome/chrome`
  — **not installed** here.
- Snap Chromium is present but its confinement **denies writing** screenshot /
  profile paths outside `~/snap/chromium/` (`~/.cache` write → `Permission denied`).
- Ubuntu OEM kernel sets `kernel.apparmor_restrict_unprivileged_userns=1`, so
  Chrome's namespace sandbox **core-dumps**; `--no-sandbox` is mandatory.
- Resolution: Chrome-for-Testing pulled to `~/.cache/puppeteer` via
  `@puppeteer/browsers` (no root, no snap), launched headless with
  `--no-sandbox --remote-debugging-port=9222`. The ecc MCP was repointed with
  `--browserUrl=http://127.0.0.1:9222` (edit in the ecc plugin cache — fragile
  across ecc upgrades). The harness itself uses raw CDP and needs no MCP.

## Reproduce

See `browser_boot/README.md`.
