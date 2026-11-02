# Where this is going: one GPU serving desktops the way a game server serves players

## The honest starting point

Today's artifact boots Linux in ~75 minutes; QEMU does it in 5 seconds.
It is single-user and single-hart. We are not claiming a faster VM —
on raw boot speed we lose, and the demo does not pretend otherwise.

The contribution is the substrate, and every claim below is a committed
receipt: a full Linux kernel and an interactive userspace shell running
*inside* the GPU's compute shaders (WGSL, no CPU in the guest's path),
with image I/O working in both directions — reading structure out of
pixels (md5-verified decode) and writing machine code *into* images
(Muse authoring to verified bytecode).

## Why the boot is the load-bearing proof

A multi-user gaming system is three things: one server owning world
state, N players sending input, N views going out. Served desktops are
the same shape, except each player's "character" is a full OS session.
So the first question is not "can we multiplex N" — it is "can one
session run where the rendering happens?" The boot answers yes, and
contributes each mechanic the game-server model needs:

1. **The session runs in server memory.** The OS, its ramdisk, and its
   processes live in the same GPU memory the compositor will read.
   Serving a view is a memory read of one rectangle — a VM must copy
   every frame across PCIe; per-user cost collapses from "a machine"
   to "a slice of one frame."
2. **One session = one sealed spatial region = one player slot.** N
   users becomes N regions plus N hart contexts; the DTB/OpenSBI boot
   path is already multi-hart-shaped, and multiplexing is the game
   tick: hart time slices instead of player time slices.
3. **The input wire is per-session.** The interactive shell proved
   keystrokes in, answers out, nothing shared between sessions — the
   per-player input stream, with the image/audio command paths showing
   it generalizes to media.
4. **Determinism is the netcode.** Identical serial hashes on every
   boot mean checkpoint, restore, replay, and migrate are all exact:
   the save-state machinery games already ship, applied to OS sessions.
   A game server doesn't boot a physics world from scratch for every
   player who joins — it initializes the world once, snapshots/forks
   memory slots, and streams views. The machine-state snapshot proves an
   OS desktop on a GPU works the same way: the whole machine is six GPU
   buffers, saving them at the prompt gives instant resume (68 min full
   boot → 124s), and byte-identical hashes across adapters make spinning
   up a new user slot a memory blit rather than an OS installation.
   (Measured + receipted: `SPEED_UP_RECEIPT_2026-11-02.md`.)
5. **The boot is the seat at the table.** You cannot serve N players
   until one world-sim runs correctly. One unmodified real kernel, a
   live shell, file I/O — step zero is done, and everything after is
   multiplexing on top of a working single seat.

## Post-deadline horizon (staked, not claimed)

**Measured since submission (2026-11-02):** fork-on-restore at N=2 — two
concurrent Linux seats restored from one master snapshot on one RTX 5090,
zero state leakage, ~83M steps/seat — `MULTI_SEAT_RECEIPT.md`.

1. **VRAM-side snapshot restore** — `copy_buffer_to_buffer` clones of the
   six buffers stay on-device; restore drops from seconds to sub-millisecond,
   so a dirty session resets inside one display frame.
2. **Checkpoint ladder** — milestone snapshots (OpenSBI-ready, MMU-active,
   at-prompt) turn kernel debugging into revert-and-step instead of reboot.
3. **Toolchain snapshot as a build farm** — snapshot Alpine with a compiler
   seeded once; every later compile session forks from warm state in seconds.
4. **Glyph-lane bridge** — spatial memory regions as autonomous `.glyph`
   execution planes (separate lane; both ISAs' real grammar respected).

## The destination

A multi-user desktop system served by one GPU the way a game server
serves players:

- N users, one machine. The server owns the world state; each user
  sends input and receives a view.
- Desktops are exactly that problem: the session is the state, the
  keyboard is the input, the screen is the view.
- The view is an *image* — which means any device that can display a
  picture can sit at the desktop. No client install, no hypervisor, no
  drivers. A browser tab is a thin enough client (this project has
  already driven a browser-composited window as a substrate surface).

## How today's work leads there

1. **The server engine exists.** A real kernel (Alpine 6.12.31-lts,
   riscv64) executing on the GPU core with a live shell is proof that
   the substrate runs unmodified real workloads — the prerequisite for
   serving real users. Receipt:
   `gpu_shell_live_interactive_2026-11-01.log`.

2. **The I/O protocol is already images, both ways.** Reading: the
   decoder turns pixels into bytes and boots code from them. Writing:
   the authoring path turns intent into machine code inside an image.
   For a served desktop, the screen wire format and the software
   distribution format are the same thing — pictures.

3. **The memory model is spatial, not flat.** The GPU's memory is
   addressed as a 2D Hilbert surface. Multi-tenant isolation falls out
   of geometry: each user's session is a region of the surface, and
   the compositor is a traversal of it. (The emulator's loader and
   mem-dump tooling already walk this layout.)

4. **Determinism is the netcode.** Boots produce byte-identical serial
   hashes (`serial_sha256` in the E2E output is the same on every run).
   Identical-input-identical-state means sessions can be checkpointed,
   restored, replayed, migrated to another GPU, and served to a second
   user bit-for-bit. That is the save-state and replay mechanic every
   multiplayer game already ships — applied to OS sessions.

## The build order (each step lands on committed ground)

1. **Root on virtio disk** — persist desktops across boots. The
   initramfs ships without `virtio_mmio.ko`/`virtio_blk.ko`; injecting
   the two modules plus a real rootfs through the existing overlay
   mechanism (`tools/build_gpu_shell_blob.py`) gives every user a
   persistent machine. Named in `SHELL_QUICKSTART.md` today.
2. **N harts** — the boot already goes through OpenSBI + DTB; extend
   the emulator to N hart contexts and one GPU runs N concurrent OS
   instances. N instances = N users; the GPU multiplexes them the way
   a game tick multiplexes players.
3. **Framebuffer as image** — the initramfs already carries
   `virtio_gpu`. Route desktop pixels into the image pipeline and a
   session becomes a streamable picture: viewable in a browser, on a
   phone, on a projector — or composed into a larger image that holds
   many users' screens at once.
4. **The compositor is the game loop** — windows as glyphs on the
   spatial surface; user sessions multiplexed on hart time slices;
   input arriving as media (the project's audio-pixel command path
   already demonstrated command-carrying media as a control channel).
5. **Deterministic migration** — snapshot a session (mem-dump tooling
   exists), restore it on another GPU, hand the same desktop to the
   same user from a different machine. State verification is the md5
   gate the project already runs everywhere.

## Why GPU-native instead of "just use a VM"

- **Density**: a VM gives each user a fake computer; a game server
  gives each player a view. Per-user cost collapses from "a machine"
  to "a slice of one frame." Thousands of players per box is normal
  for games; we want that math for desktops.
- **Zero-copy**: compute, render, and I/O share one memory. A VM must
  copy every frame out of the GPU; here the frame *is* the memory.
- **Access**: the client protocol is a picture. Anything that can
  show an image can be the desk.
- **Verifiability**: same input, same hash, every run — the md5 gates
  in this repo are a forensic audit trail for the whole machine, which
  shared VM hosts cannot offer.

## What we will honestly say we cannot do yet

Multi-hart scheduling, persistent root disks, and the served-image
compositor are not in this submission — they are the next lane, and
the blockers are documented, not hidden (missing virtio modules, single
hart context in the emulator, no modloop in the shipped image). What
this submission proves is that the hard, load-bearing piece — a real
operating system executing inside GPU compute, with an image-native
I/O protocol in both directions — is real, reproducible, and receipted.
