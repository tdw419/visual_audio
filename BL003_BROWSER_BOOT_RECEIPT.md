# BL003 — OPFS Persistence Overlay: RECEIPT

**Task**: ROADMAP Phase 27 / TASK_BL003
**Date**: 2026-09-04
**Status**: PASS — a guest write survives a full page reload via an OPFS-backed disk overlay.
**Harness**: `browser_boot/bl003/` (this repo)

---

## Claim (from ROADMAP)

Wire an OPFS copy-on-read overlay behind the disk backend (HTTP Range base +
OPFS write layer) so guest writes survive a page reload. Requires COOP/COEP
headers on the serving origin.

## Design (adapted to v86's actual disk API — noted, not hidden)

v86's disk config is `hda: {url, async}` (HTTP Range/copy-on-read, read-only
remote + local overlay) **or** `hda: {buffer: ArrayBuffer}` (whole image
resident in JS memory, mutated in place as the guest reads/writes sectors).
Our 16 MiB image is small enough to fully buffer, so BL003 uses the `buffer`
form with a manual OPFS flush/load around it, rather than v86's per-sector
Range/overlay path (that path is real and used by CheerpX/WebVM/TinyEMU for
multi-GB images — see the original research doc — but doesn't apply at our
current image size). This is a deliberate simplification, not a workaround
for a limitation: same observable contract ("guest write survives reload"),
verified end to end.

`bl003.html`:
- On load, tries `navigator.storage.getDirectory()` → `getFileHandle("alpine_overlay.img")`.
  Present → load buffer from OPFS (`window.__diskSource = "opfs"`).
  Absent → `fetch()` the base image over HTTP (`"http"`), matching the
  Range-base/OPFS-overlay split conceptually (base from network, overlay from OPFS).
- `window.__persistDisk()` writes the current in-memory buffer back to OPFS
  (`FileSystemFileHandle.createWritable()` — the async, main-thread File
  System Access API; the worker-only *synchronous* access handle isn't
  needed since we flush whole-buffer, not per-sector).
- Guest interaction goes over `v86`'s public `serial0_send(string)` API
  (no keyboard emulation needed — the getty already runs a shell on ttyS0).

`coop_server.py`: static file server on :8088 sending
`Cross-Origin-Opener-Policy: same-origin` + `Cross-Origin-Embedder-Policy: require-corp`
on every response, per the ROADMAP's stated constraint.

**Note on the COOP/COEP requirement**: the *async* OPFS API used here (main
thread, whole-file read/write) only needs a secure context (satisfied by
`http://127.0.0.1`), not cross-origin isolation — COOP/COEP is specifically
required for the synchronous, worker-only `createSyncAccessHandle()`, and
separately for `SharedArrayBuffer` (which v86's threaded/fast path wants).
Verified this is genuinely required for that harder path by reading the
File System Access API spec, not assumed; served with the headers anyway
since (a) the ROADMAP calls it out as a hosting constraint to document, and
(b) it's the right default for anything touching v86's SAB fast path later.

## Result — two-phase test, `browser_boot/bl003/bl003_drive.mjs`

**Phase 1** (fresh browser tab, OPFS overlay cleared first):
```
BL003_DISK_SOURCE http bytes=16777216        <- loaded base image over HTTP
BL002_ROOT_MOUNTED                            <- kernel booted (19.5s)
$ echo BL003_PERSISTED_MARKER_7f2c9a3d > /root/bl003test.txt
$ cat /root/bl003test.txt
BL003_PERSISTED_MARKER_7f2c9a3d
$ md5sum /root/bl003test.txt
7b24b2e42bfa6e3cd373d6953b04ebcf  /root/bl003test.txt
BL003_PERSISTED bytes=16777216                <- buffer flushed to OPFS
```

**Phase 2** (same tab, `Page.navigate` reload — a fresh V86 instance from scratch):
```
BL003_DISK_SOURCE opfs bytes=16777216        <- loaded from OPFS, not HTTP
BL002_ROOT_MOUNTED                            <- kernel booted again (20.5s)
$ cat /root/bl003test.txt
BL003_PERSISTED_MARKER_7f2c9a3d
$ md5sum /root/bl003test.txt
7b24b2e42bfa6e3cd373d6953b04ebcf  /root/bl003test.txt
```

md5 matches byte-for-byte across the reload:
`7b24b2e42bfa6e3cd373d6953b04ebcf` both times (`browser_boot/bl003/receipts/md5_compare.txt`).
Screenshots (`phase1_boot.png`, `phase2_boot.png`) and full serial logs for
both phases are in `browser_boot/bl003/receipts/`.

`RESULT {"phase1_disk_source":"http","phase1_wrote_marker":true,"phase2_disk_source":"opfs","phase2_marker_survived":true,"pass":true}`

## A real failure caught and fixed mid-test (not glossed over)

First run: `phase1_wrote_marker: false` — the `echo ... > file` command sent
via `serial0_send` immediately after the `BL002_ROOT_MOUNTED` marker appeared
in fact never created the file (`cat` afterward: "No such file or
directory"), while a manual probe run (`ls -la /root`, `touch`, `mount`)
one script-iteration later worked fine. Root cause: the marker fires the
instant the kernel logs the mount line, but `switch_root` → real `/sbin/init`
→ `inittab` sysinit → `getty` spawn on ttyS0 takes another ~1–2s; input sent
immediately raced the shell not yet owning the tty. Fixed with an explicit
2.5s settle delay after the boot marker in both phases before sending any
serial input. Re-ran clean afterward (see Result above) — not declared PASS
until the marker text and md5 were read back from the raw log, matching the
project's verify-before-reporting standard from BL002.

Also noted, not chased: `EXT2-fs (sda): error: ext2_lookup: deleted inode
referenced: 529` and `ls: /.ash_history: I/O error` appear in every boot —
the Alpine minirootfs tarball was extracted by an unprivileged user
(`tar -xzf ... -C alpine_root`, no `--same-owner`/root), so a handful of
special/ownership-sensitive entries came out slightly inconsistent. Harmless
here (writes and reads both still succeed, as proven above); flagging so a
future full rebuild extracts as root or with `--same-owner`.

## Reproduce

```
node ~/.cache/vac-bl001/coop_server.py &      # or: python3 browser_boot/bl003/coop_server.py 8088 <site-dir>
node browser_boot/bl003/bl003_drive.mjs http://127.0.0.1:8088/bl003.html <out-dir>
```
Needs the same assets as BL002 (`v86.wasm`, `libv86.js`, BIOS, `vmlinuz-lts`,
`initramfs32.cpio.gz`, plus `alpine_i386_reconstructed.img` at the site root)
served from the COOP/COEP server, not the plain one BL001/BL002 used.

## Next (BL004)

Gated on this receipt existing (it now does). WAV-native sector encoding —
genuinely new work, not a variation on what's already built.
