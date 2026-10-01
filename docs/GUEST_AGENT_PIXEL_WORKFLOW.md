# Guest-Agent Pixel Workflow (hermes-in-guest ↔ host pixel substrate)

Audience: AI agents (and humans) who want to drive the pixel-booted Ubuntu guest
from the host, observe guest activity in the pixel container, and use
"guest writes → pixel moves" as a programmable interface.

Status: PROVEN n=3, 2026-09-16. Three independent cases — 17-byte marker
(byte-exact pixel hit), 108-byte random file, 160MiB 2-extent random file
crossing 3 frame boundaries — all sha256-verified guest-bytes vs
container-reconstructed-bytes, zero drift. Encoded as a tool:
`tools/pixel_container/locate_in_container.py` (locate/verify/watch).

---

## The mental model

The guest OS is a normal Ubuntu whose *entire disk* is a PXC1 pixel container
(`ubuntu_desktop_pxc1_v3_selfhost/`, 252 frames × 4096×4096 RGBA px = 64 MiB/frame,
frame 0 = metadata, rootfs starts at frame 1). A file the guest writes is bytes
on that disk is pixels in PNGs. A hermes agent installed INSIDE the guest is
therefore a programmable actuator for the pixel substrate — and the host can
compute, exactly, which pixels any guest write touches.

Three capabilities, all demonstrated:

1. **Prompt-oracle**: host prompts hermes inside the guest over ssh; guest
   executes with real tools; result files land on the host via /host_zion.
2. **Address chain**: guest file → LBA → disk byte → frame → (x, y, channel).
   Pure arithmetic — no scanning. Verified to byte-exact offset (0 drift).
3. **Watch**: the COW journal names dirty frames every 5 s writeback cycle;
   diff those PNGs to see guest writes appear in pixel space.

---

## Prerequisites

- Guest booted: `./interactive_ubuntu_pixel_pxc1.sh` (repo root). SSH on
  127.0.0.1:2222, user `jericho`, password `israel`. Writeback daemon cycles
  every 5 s; HTTP control on 127.0.0.1:8769.
- Guest agent installed (see "Reinstall after re-encode" below).

## Quick start — prompt the guest agent

```bash
sshpass -p israel ssh -o StrictHostKeyChecking=no -p 2222 jericho@127.0.0.1 \
 'export HOME=/var/tmp/hermehome PATH=/var/tmp/hermehome/.local/bin:$PATH; \
  timeout 150 hermes -z "Use the terminal tool to create /var/tmp/probe.bin \
  containing the text PIXELPROBE-4f7a21 repeated 64 times. Reply done when \
  written." --yolo -t terminal'
# rc=0 = prompt + tools + model round-trip all worked inside the VM.
```

- `-z` = one-shot, `--yolo` = autonomous tool use, `-t terminal` = tool allowlist.
- Have the guest write results under `/host_zion/...` when the host must read
  them back (9p = instant host-side); `/var/tmp` writes land in the container
  (pixel space) instead.
- Guest hermes is v0.19.0 = PyPI ceiling. Host runs a newer dev checkout;
  guest TUI sessions inside the VM are also available to humans.

## The address chain (the core trick)

Question: guest wrote `/var/tmp/probe.bin` — which pixels changed?

```bash
# 1. Guest side (no root needed): file's physical block + partition start
ssh ... 'filefrag -v /var/tmp/probe.bin | head -6'      # physical block 392214
ssh ... 'cat /sys/class/block/vda3/start'               # sector 1880192

# 2. Disk byte = (block*4096 + partition_start*512)   [verify bs=4096 via stat -f -c %S]
#    example: 392214*4096 + 1880192*512 = 2,569,033,728 (+ extent offset —
#    filefrag lists it; full chain below hit byte 19,030,016 in-frame exactly)

# 3. Container mapping (header.json): frame = 1 + byte // 67108864
#    intra = byte % 67108864; pixel = (intra % 16384) // 4 = x,
#            (intra // 16384) = y, channel = intra % 4  (RGBA, row-major)
```

Real verified examples (n=3):

1. marker (17B ASCII): block 392214, vda3 start 1880192 → disk byte 2,569,166,848 →
   frame 39, intra 19,030,016 → pixel (2048, 1161), channel R — found at exactly
   that offset, 64/64 reps.
2. case2_rand.bin (108B random): single extent, frame 129 — sha256 match.
3. case3_big.bin (160MiB random): 2 non-contiguous extents (16MiB ext4 allocation
   gap between them — correctly skipped; contiguous assumption fails here),
   crossing 3 frame boundaries mid-extent (blocks 1927664→133, 1944048→134,
   1960432→135) with byte-continuous reconstruction — sha256 match.

## The tool (use this, not hand-rolled scans)

```bash
$T locate /var/tmp/probe.bin            # extent map: frames + pixel spans (JSON)
$T verify /var/tmp/probe.bin <sha256>   # reconstruct from PNGs alone, compare
$T verify /var/tmp/big.bin file:sha256s.txt   # '<hash> <name>' lines, matched by basename
$T watch                                # dirty frames pending writeback right now
```

- `verify` takes the writeback barrier automatically (see trap below); exit 0
  iff the container's bytes hash to the expected value. Negative control: a
  wrong sha must exit 1 — a verification that cannot fail is not a verification.
- `verify --no-barrier` skips the barrier (faster, may read stale frames).

## Source-level attribution: addr2line overlay (no font rendering)

"See the source code being used" is achieved with DWARF, not rasterized text.
Three kernels, three states (measured 2026-09-16):

| Kernel | DWARF | addr2line |
|---|---|---|
| `~/zion/projects/xv6-riscv/kernel/kernel` | full | `copyout` → `vm.c:350` |
| `~/zion/linux-rv64-test/vmlinux` | none (`DEBUG_INFO_NONE`) | `??:0` |
| `~/zion/linux-rv64-test/vmlinux.dwarf4` | DWARF4+REDUCED | `__riscv_sys_write` → `fs/read_write.c:652` |

`vmlinux.dwarf4` was built 2026-09-16 in a throwaway git worktree (source
tree untouched) with `CONFIG_DEBUG_INFO_DWARF4=y` +
`CONFIG_DEBUG_INFO_REDUCED=y`, copied out, then the worktree deleted.
REDUCED keeps exactly the file/line/function tables addr2line needs at a
third of the disk footprint of full DWARF — decisive on /home, which peaked
at 34MB free during the first full-DWARF attempt and ENOSPC'd at the final
link. Rebuild recipe:

```
git -C ~/zion/linux-rv64-test worktree add ../linux-rv64-dwarf4 HEAD
cd ../linux-rv64-dwarf4
cp ../linux-rv64-test/.config .config
../linux-rv64-test/scripts/config --file .config \
    -d DEBUG_INFO_NONE -e DEBUG_INFO_DWARF4 -e DEBUG_INFO_REDUCED
make ARCH=riscv CROSS_COMPILE=riscv64-linux-gnu- olddefconfig
make -j24 ARCH=riscv CROSS_COMPILE=riscv64-linux-gnu- all
cp vmlinux ../linux-rv64-test/vmlinux.dwarf4
git -C ~/zion/linux-rv64-test worktree remove --force ../linux-rv64-dwarf4
```

Debug chain: lockstep divergence at PC → addr2line (DWARF kernel) →
file:line → locate_in_container.py → pixel coordinate.

## Watch mode (dirty-frame diffing)

```bash
ls -lt /tmp/pxc1_cow_journal/          # frame_*.png = frames dirty since last cycle
# backend folds them into the container every 5 s and clears the journal —
# either scan fast, or diff the container frames named in the journal
```

A watcher diffs region (2048,1161)±N of frame 39 across cycles → sees agent
writes land in near-real-time; a VLM can be pointed at exactly that region.

## Traps (each one produced a real wrong result in this session)

| Trap | Symptom | Rule |
|---|---|---|
| RGB vs RGBA | scan finds NOTHING, even for strings that must exist (control test!) | PNG is RGBA; `convert("RGB")` deletes every 4th byte, ~24% marker survival per rep. Always scan the raw RGBA stream. |
| Hilbert assumption | wrong mapping everywhere | PXC1 v1 is ROW-MAJOR by design (forensic invertibility). No curve. |
| Frame 0 | control string never found anywhere | Frame 0 is metadata; disk byte 0 = frame 1 pixel 0. Sections concatenate; rootfs starts at frame 1. |
| dd /dev/vda as jericho | empty reads | Guest user is unprivileged on the raw device. Use filefrag + /sys/block/*/start instead. |
| stale backend socket | relaunch dies: "connect to /tmp/virtio-pixel-interactive.sock failed" | Backend daemon outlives qemu BY DESIGN. If port 8769 answers after qemu death, kill the old backend before relaunch. |
| pkill/pgrep -f self-match | your own shell SIGTERMed (twice in one day) | `ps -eo pid,comm | grep -i NAME` or full-cmdline check excluding $$ before killing. |
| guest $HOME | hermes config invisible, pip EPERM | /home/jericho is root-owned in guest: export HOME=/var/tmp/hermehome. Config symlinks → /host_zion. |
| guest-local installs | vanished after old image died | Everything under /var/tmp is container-state (survives compact+reboot, dies on re-encode). Identity lives on /host_zion. |
| stale PNG read (race) | reconstruct matched by hand once, then failed via tool | The 5s writeback daemon rewrites frames under you. Always take the /writeback barrier and confirm frame mtimes BEFORE reading — `verify` does this unless --no-barrier. |
| filefrag dialect | extents attributed to the WRONG file | "File size of X is N" header PRECEDES its extent lines; the "N extents found" trailer FOLLOWS them. Anchor parsers on the header. |
| whole-block hashing | small files "fail" verification | ext4 allocates whole blocks: a 108-byte file owns 4096 container bytes. Hash truncated to file size, never the block. |
| reorder vs index | — | Do NOT rearrange container layout to "organize" it — that breaks stock-guest compatibility and risks the journal-poisoning class of corruption. Build the semantic index (guest path → pixel regions) as a read-only overlay instead; same understanding, zero disk writes. |

## Shutdown / reboot / reinstall

```bash
curl -s -X POST http://127.0.0.1:8769/writeback        # flush dirty frames
curl -s -X POST http://127.0.0.1:8769/compact_journal  # expect {"ok":true,...}
kill <qemu-pid>                                        # graceful stop
# reboot: relaunch launcher; installs SURVIVE (proven: hermes intact + live
# probe after compact→kill→boot cycle)
# re-encode from base = fresh disk: guest packages are gone, identity is not
bash /host_zion/guest_hermes_home/bootstrap.sh   # from host; ~2 min; see file
```

Identity note: guest config/auth live at
`/host_zion/guest_hermes_home/.hermes/{config.yaml,auth.json}` (host disk,
outside this repo — never inside a git tree), symlinked from guest
`/var/tmp/hermehome/.hermes/`. chmod 600/700; treat as secrets.

## Why this matters for pixel programming

- Pixel space is *addressable* like memory: any guest allocation maps
  deterministically to (frame, x, y, channel). A debugger's view of a disk.
- Agent intent → pixel movement is now a *callable* interface, not a metaphor:
  prompt changes pixels at computed coordinates; the delta is observable.
- Failure taxonomy is spec'd (RGB/RGBA, section offsets) and documented in the
  PXC1 skill; the control-string test above is the cheap falsifier — run it
  before trusting any negative scan.

## Related

- `docs/SYSCALL_ABI_SPEC.md` — Pillar 2.1 syscall ABI (the other half: what
  syscalls guest programs make; corpus at `tools/syscall_corpus/`)
- skills: `pixel-container-pxc1`, `pixel-booted-agent-workflows`,
  `syscall-corpus-capture`
- 2026-08-29 receipt: earlier hermes-on-guest attempt (died with old image —
  the persistence lesson that motivated /host_zion identity storage)
