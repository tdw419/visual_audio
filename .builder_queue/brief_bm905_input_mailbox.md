# BRIEF — TASK_BM905: Input mailbox over the pixel medium (host paints events, guest testifies keycodes)

**Row:** `tools/bare_metal_poc/ROADMAP.md` Rung 9 (after BM904, which landed GATE PASS ×3 2026-09-19; commit 450a314a)
**Provenance:** Jericho ruling 2026-09-19 ~11:10 — of the two candidate briefs
(input mailbox vs mind-state/KV-cache probe), **input mailbox first**. The
mailbox is the one item this ladder designed but never briefed; the idea is
Jericho's and the queue gate is his. BM904's filed backlog note (this brief's
predecessor, ac1ce868) shelved it as replacement-scaffold work — this ruling
un-shelves it deliberately, shim-era, because its verification reuses BM904's
fresh gate exactly (paint → diff → prove pixel landing → guest testifies).
**HARD scope:** read-mostly guest discipline: guest touches only the reserved
window (read-only raw dd), `/dev/uinput`, and its own `/var/tmp` daemon files
(rm'd at cleanup). No backend rebuild/restart. No edits under
`systems/virtio_pixel_rs/` (parallel-session WIP — see
RULING_20260919_monitor_newest_mtime_epoch.md). Lands only: gate scripts +
receipt + roadmap cell. Reuse `tools/pixel_container/locate_in_container.py`
as a library for the disk-byte→pixel chain (import; do not fork the address
math). **Interfaces are LOCKED.**

## Scope (files this brief may change)

**Files in scope:**
- `tools/bare_metal_poc/rung9/bm905_mailbox_packet.py` — packet codec (new; shared by host + gate)
- `tools/bare_metal_poc/rung9/bm905_host_paint.py` — window preflight + host-side paint (new)
- `tools/bare_metal_poc/rung9/bm905_guest_listener.py` — guest daemon (new; deployed to guest `/var/tmp`, rm'd at cleanup)
- `tools/bare_metal_poc/rung9/bm905_mailbox_gate.py` — the gate script (new)
- `tools/bare_metal_poc/rung9/RECEIPT_BM905_INPUT_MAILBOX.md` — the gate receipt (new)
- `tools/bare_metal_poc/ROADMAP.md` — the Rung 9 BM905 cell only

**Do NOT** touch `systems/virtio_pixel_rs/`, the backend restart path, or the
disk image outside the reserved window's paint mechanism. If a signature in
`locate_in_container.py` looks wrong, STOP and report — never weaken a live
guard to make a step pass.

## Why (build-on from BM903/BM904)

BM903 proved the READ direction (pixels → guest bytes) and BM904 the WRITE
direction (guest bytes → exact pixel set). Both are about *storage*. BM905
makes the medium carry something it has never carried in this project: an
**event that becomes real inside the guest** — a synthesized keypress on a
kernel-created input device. The medium's frames are the DISK, not the screen
(design note, shim-oracle-and-input-mailbox.md: a keystroke changes the
framebuffer, never the container frames), so input over the medium MUST go
through a disk window: there is no pixel path to the display device today.
That asymmetry is the gate's whole point: prove the path that exists, don't
photograph the screen.

## Endgoal alignment (these tests scaffold the shim's replacement)

Judge every leg on whether it survives the shim's deletion:

- **SURVIVES (the deliverable):** the packet protocol `[seq, type, code,
  value]` + CRC + monotonic-seq dedup semantics; the reserved-window-outside-
  FS placement method; the verify pattern paint → diff → prove landing →
  guest testifies (TC-1/oracle-first shape). At Rung 8 the writer's address
  changes from a livemap paint call to a USB plug (HID-injector dongle =
  hands) — the protocol and the proof shape carry unchanged.
- **DIES WITH THE SHIM:** the livemap paint call and `POST /writeback`
  barrier themselves — they are the QEMU-era painter, and bare metal freezes
  the medium at dd time (live writes are categorically harder closer to the
  metal; that is why Rung 8 is transport-only). Record shim-specific latency
  numbers as shim-era facts, not contract targets.

## Method

0. **Prereq probe (measure, then proceed or STOP-and-ticket):**
   - Guest: `/dev/uinput` present or creatable (`modprobe uinput`; as root,
     `mknod /dev/uinput c 10 223` if the node is absent but the misc device
     exists in `/proc/devices`); python `evdev` importable or pip-installable
     over slirp. If uinput cannot be made to work IN GUEST, STOP and file
     REPAIR_PENDING with the measurements — do NOT fall back to a plain
     read-the-window testify leg: byte arrival on the guest disk is already
     proven (BM903); only event synthesis is new, and dropping it drops the
     claim.
   - Window placement: read the guest disk's partition table; choose a
     ≥64 KiB LBA range outside every partition and outside the protective/hybrid
     MBR areas (disk tail is the default candidate). Record start LBA, size,
     and the proof-of-outside (parted/fdisk output quoted in the receipt).
     The window must survive: no FS, no journal, no swap claims it.
1. **Packet format (fixed 16 B slots, little-endian, ring of ≥256 slots in
   the window):** `magic u16 (0x0DB5) | seq u32 | type u8 | code u16 |
   value u16 | crc16 (over first 14 bytes)`. Types: 1=EV_KEY press
   (`value`=keycode, daemon auto-synthesizes the matching release so
   key-press+release pairs are one packet), 2=EV_KEY release (explicit),
   3=EV_SYN noop (heartbeat/latency probe). Malformed magic or CRC ⇒ daemon
   skips and counts (never injects).
2. **Guest daemon** (`bm905_guest_listener.py`, runs backgrounded in guest
   with a bounded lifetime): polls its own `/dev/vdX` at the window via
   `dd bs=16 count=256 skip=<window-lba> iflag=direct` (if direct unsupported,
   drop-caches discipline + document), tracks `last_seq`, injects strictly
   newer valid packets via uinput on a registered device
   (`BM905-Mailbox-Keyboard`), and appends JSONL testimony
   `/var/tmp/bm905_testify.jsonl`: `{seq, type, code, mono_ts}`.
3. **Leg A — pixel-landing proof (BM904 primitive, host-paint source):**
   host paints packet(s) with seq N, N+1 into the window's mapped pixels
   (chain: disk byte → frame/x/y/channel — same math as BM904, inverted
   writer), `POST /writeback`, re-decode: changed-pixel set must EQUAL the
   predicted set (control noise on the affected frames must be measured
   first; exact equality only when it is zero, else the ⊆-union form).
   ×2 runs, different keycodes/seq values, at least one packet straddling a
   slot/frame boundary.
4. **Leg B — keycode arrival (the new claim):** within a bounded latency
   budget (daemon poll ≤200 ms; gate asserts testimony ≤5 s per packet), the
   guest's own evdev reader testifies EV_KEY `<keycode>` value=1 then value=0
   on device `BM905-Mailbox-Keyboard`. Quote the testimony lines in the
   receipt. Also record the honest ordering fact: the guest may observe bytes
   via the backend overlay BEFORE writeback makes them pixel-visible (BM904
   R1 peek-leads-PNG) — guest read is the arrival authority; the pixel diff
   is the host-side corroboration of the mapping. Measure which leads,
   record, do not tune.
5. **Leg C — dedup negative:** replay an OLD seq (re-paint a already-consumed
   slot, or paint seq < last_seq): daemon testimony count must NOT increase
   for it. This is the RED leg proving seq is load-bearing, not decorative.
6. **Leg D — comparator mutant:** `--mutant` flag shifts the window base by
   one sector in the prediction only; Leg A must go RED (extra/missing > 0,
   exit 1). Paste the RED tail.
7. **Cleanup:** kill daemon, rm `/var/tmp/bm905_*` + sync (verify GONE);
   zero-fill the window via host paint + writeback (or guest dd if simpler),
   re-verify window reads zero. Container state net unchanged modulo the
   window bytes, which were chosen to be FS-dead-space.

## Verification (row gate)

- [ ] Leg 0 measurements in receipt: uinput path used, partition table proof
      that the window is outside all FS-owned ranges.
- [ ] Leg A exact-equality (or noise-attributed) pixel diff ×2 runs, fresh
      seqs, one straddle case.
- [ ] Leg B: ≥3 distinct keycodes testified press+release in guest evdev
      output, latency budget met, quoted in receipt.
- [ ] Leg C: replayed old seq NOT re-injected (testimony count pinned).
- [ ] Leg D: mutant comparator → gate RED, exit 1, tail pasted.
- [ ] Malformed-packet leg: CRC-corrupted slot skipped + counted (cheap host
      side: paint one bit flip, assert daemon skip counter moves, testimony
      does not).
- [ ] Receipt `rung9/RECEIPT_BM905_INPUT_MAILBOX.md` + roadmap cell; guest
      prompts bounded (<300 s, quoted-output style) per BM903 capability map;
      cleanup verified GONE.

## Honest boundaries this gate must state (not hide)

Poll-loop daemon, not an interrupt path; single guest session; shim-era painter
(livemap+writeback) — the bare-metal analogue replaces it with a physical HID
dongle, and NOTHING in the protocol depends on QEMU except latency numbers.
The gate proves event synthesis inside the guest from host-writable bytes; it
does NOT prove the medium can deliver input to a machine whose disk the host
cannot write (that is Rung 8 territory and uses a different writer entirely).

## Follow-on ladder (do NOT build now — file as backlog rows)

Mouse/multi-event packets (usb-tablet absolute = 6 B), the guest→host ACK
leg over BM903 read-direction (window ack slot, host reconstructs ack from
pixels — closes full duplex over the medium), mind-state probe (KV
save_state → pixel diff → host reload; ranked below this mailbox by Jericho's
2026-09-19 ruling, re-briefable as BM906), crash-consistency legs from the
BM904 follow-on list.
