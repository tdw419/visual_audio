# V5 VM Dev Environment

How the V5 VM is set up, how it differs from V4, and how to work inside it —
including running a second Claude Code instance natively inside the guest.

## What V4 and V5 actually are

Both are the same underlying disk image lineage, booted separately:

| | V4 | V5 |
|---|---|---|
| Disk | `ubuntu-desktop-15g.raw` | `ubuntu-desktop-v5.raw` (a `cp --reflink=auto` copy of V4's disk, made 2026-08-24) |
| Boot script | ad-hoc (see below) | `boot_v5_vm.sh` |
| SSH port | 2222 | 2224 |
| Monitor socket | `/tmp/qemu_monitor_interactive.sock` | `/tmp/qemu_monitor_v5vm.sock` |
| Login | `jericho` / `israel` | `jericho` / `israel` (same, copied disk) |

They're independent VMs that can run simultaneously — separate ports, separate
monitor sockets, separate disk files. Editing one does not affect the other.

Both boot via the **same shared chainloader**: `/tmp/ubuntu_v4_efi.img`, built
from `systems/v4_bootloader_x86`. This is a custom UEFI bootloader (not GRUB)
that hardcodes its kernel command line in
`systems/v4_bootloader_x86/src/bootloader_uefi.rs`. Anything changed there
affects both V4 and V5's next boot — treat it as shared infrastructure.

There's also a separate, unrelated qcow2 (`/home/jericho/zion/apps/linux/ubuntu/ubuntu-24.04-desktop.qcow2`,
an "osboxes" prebuilt image) that was explored once as an alternative — it
uses legacy BIOS boot (GPT + BIOS-boot partition, no ESP), not UEFI, so it
needs SeaBIOS, not OVMF. It's not part of the V4/V5 lineage; mentioned here
only so a future session doesn't re-diagnose the boot failure from scratch if
someone tries to OVMF-boot it again.

## Booting V5

```bash
./boot_v5_vm.sh
```

Boots detached, prints its PID. SSH becomes reachable within ~10s:

```bash
ssh -p 2224 jericho@127.0.0.1   # password: israel
```

**Always shut down gracefully** before stopping it —
`sudo shutdown -h now` over SSH, or `system_powerdown` via the monitor socket.
This disk has been corrupted by hard `kill -9` twice this session (real ext4
corruption: freed-block-double-free, orphaned inodes) — recoverable with
`e2fsck -f -y` on the partition via a loop device, but avoidable entirely by
shutting down cleanly. Only hard-kill if the guest is genuinely wedged (e.g.
OOM-thrashing so badly SSH can't even complete a banner exchange), and run
`e2fsck` on the disk before the next boot if you do.

Memory: currently `-m 16G`. It was originally 2G and OOM-thrashed itself into
an apparent "lockup" the moment a real desktop session (Firefox + Chromium
simultaneously) was actually used — 16G was tested clean under the same load.

## The `zion` shared folder (virtio-9p)

`boot_v5_vm.sh` shares the host's `~/zion` (`/home/jericho/projects/zion`,
`/home/jericho/zion` is a symlink to the same place) into the guest via
`virtio-9p`:

```
-fsdev local,id=zionfs,path=/home/jericho/projects/zion,security_model=mapped-xattr
-device virtio-9p-pci,fsdev=zionfs,mount_tag=zion
```

Inside the guest it's mounted at `/mnt/zion`, read-write, and persisted in
`/etc/fstab`:

```
zion /mnt/zion 9p trans=virtio,version=9p2000.L,msize=104857600,rw,_netdev,nofail 0 0
```

`nofail` means a boot without the 9p device attached (e.g. if some other
script boots this disk without the `-fsdev`/`-device` flags) won't hang on
the missing mount — it just won't be there.

This means: **files written by a process on the host and files written
inside the VM at `/mnt/zion` are the same files**, immediately, no sync step.
`systems/geos_pixel_v5/` on the host is `/mnt/zion/projects/visual_audio/systems/geos_pixel_v5/`
inside V5.

## Chromium / snap apps need a manual step after every boot

Ubuntu 24.04.4 LTS Cloud image ships with a permanently kernel-cmdline-masked
`snapd.service` (see `bootloader_uefi.rs`'s `systemd.mask=snapd.service`,
added to speed up boot). This means Chromium, Firefox, and anything else
delivered as a snap **will not launch** until `snapd` is started manually —
the mask can't be undone at runtime (`systemctl unmask` fails: "masked via a
generator"), only worked around per-boot:

```bash
sudo bash -c "nohup /usr/lib/snapd/snapd > /tmp/snapd_manual.log 2>&1 & disown"
```

First launch of any snap app after this will pause for ~20s (AppArmor
compiling profiles from scratch, no cache survives snapd not having run) —
this is normal, not a hang. Chromium was installed via `sudo snap install
chromium` and works once `snapd` is running.

This doesn't survive a VM restart. A permanent fix (removing the mask from
`bootloader_uefi.rs` and rebuilding the bootloader) is possible but affects
V4 too — hasn't been done, ask before doing it.

## Claude Code CLI running inside the guest

Installed via Node 22 (NodeSource) + `npm install -g @anthropic-ai/claude-code`.
Confirmed authenticated and working — `claude --version` reports 2.1.241.

This is a **separate, independent Claude Code session** from the one
orchestrating the host side of things — its own context, its own permission
prompts, no shared state. What makes it useful is that it runs *inside* the
guest: it has direct, local access to `/dev/dri`, `/dev/input`, guest
processes, guest logs — the things a host-side session can only reach
indirectly through SSH one command at a time.

Two ways to drive it:

**Non-interactive, one-shot** (good for delegating a bounded task and getting
the result back over the same SSH channel used for everything else):

```bash
ssh -p 2224 jericho@127.0.0.1 'claude -p "<prompt>"'
```

Expect this to take longer than a normal SSH command — it's a full LLM
round-trip through the guest's NAT'd network, not an instant shell command.

**Interactive**: SSH in and just run `claude`, the same as using it anywhere
else — useful when a human wants to watch or steer it directly rather than
delegate a single bounded task.

Because `/mnt/zion` is the same files as the host, a Claude instance running
in the guest can read and edit `systems/geos_pixel_v5/` (or anything else in
the repo) and the changes are immediately visible on the host, and vice
versa — no deploy step needed for source edits, only for rebuilt binaries
that need to run against the guest's actual `/dev/dri`/`/dev/input`.

## Switching to raw-KMS "pixel Linux" mode (and back)

`systems/geos_pixel_v5/examples/v5_interactive.rs` can render and take mouse
input with no X11/Wayland/compositor at all — it opens `/dev/dri/card1`
directly and does its own DRM mode-set, and reads `/dev/input/event2`
(the QEMU absolute-mode `VirtualPS/2 VMware VMMouse`, **not** `event0`,
which is the power button — the code's `V5_DRI_CARD`/`V5_INPUT_DEVICE`
defaults, `card0`/`event0`, are both wrong on this VM and must be
overridden) via an exclusive `grab()`.

DRM only allows one mode-setting master at a time, and normally that's
`gnome-shell` (via `gdm.service` → `graphical.target`). So running
`v5_interactive` while the desktop is up fails with
`set_crtc: Permission denied` — being root isn't enough, gdm has to
actually stop first.

Two scripts at the repo root do this reversibly, without any persistent
boot-config change (`systemctl set-default` stays `graphical.target`):

```bash
./pixel_linux_enter.sh   # stops gdm, launches v5_interactive with the
                          # correct env vars, logs to /tmp/pixel_linux.log
./pixel_linux_exit.sh    # kills v5_interactive, restarts gdm
```

**This is genuinely disruptive, not a clean background switch**: stopping
gdm ends the live desktop session outright — the screen goes black and,
after `pixel_linux_exit.sh` restarts gdm, you'll land back at a fresh GDM
login prompt (a new session, not the old one resumed). That's expected
behavior of DRM's single-master model, not a bug to fix here. If you want
to avoid this cost entirely, the only way is `docs/V5_ROADMAP.md`'s Phase 6
(replace Ubuntu with a minimal kernel where nothing else ever holds DRM
master) — a much bigger, currently out-of-scope undertaking; see that doc's
addendum note.

Both scripts run as root via `sudo` (interactive password prompt, matching
the existing `launch_v5_event2.sh`/`run_v5_instrumented.sh` convention) —
no udev rule grants `/dev/dri`/`/dev/input` access to a normal user in this
repo today.

## Quick reference

| Thing | Value |
|---|---|
| Boot | `./boot_v5_vm.sh` |
| SSH | `ssh -p 2224 jericho@127.0.0.1` (password `israel`) |
| Shared folder (host) | `/home/jericho/projects/zion` |
| Shared folder (guest) | `/mnt/zion` |
| Monitor socket | `/tmp/qemu_monitor_v5vm.sock` |
| Serial log | `/tmp/qemu_serial_v5vm.log` |
| RAM | 16G |
| Start snapd (after every boot, before using Chromium/Firefox) | `sudo bash -c "nohup /usr/lib/snapd/snapd > /tmp/snapd_manual.log 2>&1 & disown"` |
| Claude CLI in-guest | `claude -p "<prompt>"` or interactive `claude` |
