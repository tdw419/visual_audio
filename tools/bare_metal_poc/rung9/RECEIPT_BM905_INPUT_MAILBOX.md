# RECEIPT — TASK_BM905: input mailbox over the pixel medium

**Verdict: GATE PASS** (exit 0) — `output/bm905_n4_gate_full_v4.log`,
`output/bm905_gate_result.json`, `output/bm905_testify_evidence.jsonl`.
Lane: Qoder manual lane (`.builder_queue/BM905_MANUAL_LANE_STATE.md`),
branch `glyph-transpiler-autoloop`, 2026-09-19. Brief:
`.builder_queue/brief_bm905_input_mailbox.md`.

## Files landed

- `bm905_mailbox_packet.py` — 16 B slot codec, LOCKED layout
  (`<HIBBHHH` body + CRC-16/ARC over [0,14)), ring of 256 slots.
- `bm905_host_paint.py` — window geometry + host-side PNG paint path.
- `bm905_guest_listener.py` — guest daemon (dd poll, uinput inject, testimony).
- `bm905_mailbox_gate.py` — Legs A–E + `--mutant` + `--skip-guest` + cleanup.
- `bm905_sudo_drive.py` — pty sudo-answerer. NOT in the brief's file list but
  a hard dependency: the gate imports `load_password()` from it. Contains
  zero credential literals — the guest password lives only in gitignored
  `.env` (`SUDO_PASSWORD`).
- This receipt + the ROADMAP Rung-9 cell. Nothing else in the repo touched.

## Step 0: window placement and the uinput path

**uinput:** raw-ABI `UI_DEV_CREATE` of `BM905-Mailbox-Keyboard` in-guest
(guest has no pip/gcc/evdev — structs packed by hand); EV_KEY 30
press+release read back from `/dev/input/event5`. Measured GREEN leg-0.

**Proof-of-outside** (`sudo fdisk -l /dev/vda` in-guest, 2026-09-19,
`output/bm905_n5_partition_proof.log`):

```
Disk /dev/vda: 15.67 GiB, 16828528128 bytes, 32868219 sectors
Disklabel type: gpt
Device       Start      End  Sectors  Size Type
/dev/vda1     2048    10239     8192    4M BIOS boot
/dev/vda2    10240  1880064  1869825  913M Linux extended boot
/dev/vda3  1880192 31454847 29574656 14.1G Linux filesystem
```

The mailbox window is vda LBAs **[256, 512)** — past the GPT header+entries
(LBA 1..~33), entirely before vda1@2048. No FS, journal, or swap claims it.
Window = 256 sectors = **128 KiB**, bytes [131072, 262144), verified
all-zero via both the pixel path and `/peek`. (The brief's "64 KiB" label
and byte range [131072, 196608) were WRONG; corrected by measurement — the
4 KiB packet ring sits at the window head, the rest stays zero.)
The brief's disk-tail candidate was REJECTED by measurement: the tail
carries the container's initramfs+gguf payload sections (header.json
sections end at byte 16828528128 = disk size) — hash-tracked payload, not
dead space.

## Codec self-test (pinned)

Roundtrip ×500 random packets; 200 single-bit corruptions, CRC-field
corruption, and foreign-magic (valid CRC) all REFUSED; seq+256 slot-sharing
decodes distinctly; ring collision = last-write-wins; pin vector
`b50d0100000001001e00010000009975` byte-stable.
`output/bm905_n1_codec.log` → GATE PASS.

## Guest raw-dd read proof + the ordering fact

Painted seq-7777 packet (`b50d611e000001001e000100000079dd`) into a clean
window; guest `dd if=/dev/vda` md5 hit the full-window expectation
`6df4a82772818640c3b173523fc26cc5` at **+62.0 s** after paint (first guest
read); `/peek` saw the painted byte at **+38.2 s** — **peek LEADS guest dd**
(BM904 R1 shape, now measured on the input path too). Guest dd is the
arrival authority; the pixel diff is host-side corroboration. Zero-state
pins: guest-window-zero md5 = `0dfbe8aa4c20b52e1b8bf3cb6cbdf193`.
`output/bm905_n2_guest_dd_proof_v2.log` → GATE PASS.

## Leg A — pixel-landing exactness (×2 runs)

- run1 seqs [1000–1003] (keys A,B,C + SYN): `pred=15 changed=15 extra=0
  missing=0 control_noise=0` → EXACT.
- run2 seqs [2000–2002] (keys D,E + SYN): `11/11/0/0/0` → EXACT.
- Prediction derived from the ACTUAL pre-paint window bytes (residue-robust),
  not the nominal image.
- Straddle geometry (recorded honestly): 16 B slots are 512-aligned ⇒
  sector straddle is mathematically impossible (`crosses_512=False`); the
  128 KiB window lies wholly inside frame 1 ⇒ frame straddle structurally
  impossible. The dd bs=512 reads span slots per layout on the guest side.

## Leg B — keycodes become real inside the guest

From guest-VISIBLE anchor (the moment `dd` md5 matches the painted window),
budget 5.0 s daemon-side + 8 s detect slack. Guest-visible latencies:
**+26.8 s** (run1), **+13.5 s** (run2) after paint+barrier — fold-queue
lag, budgeted as a medium property, never tuned away.

Testimony (first lines of `/var/tmp/bm905_testify.jsonl`, archived):

```
{"seq": 1000, "type": 1, "code": 30, "mono_ts": 195826.355104116}
{"seq": 1001, "type": 1, "code": 31, "mono_ts": 195826.355199077}
{"seq": 1002, "type": 1, "code": 32, "mono_ts": 195826.355235081}
{"seq": 1003, "type": 3, "code": 0,  "mono_ts": 195826.355250823}
```

5 distinct keycodes attested across runs: {30,31,32} then {33,34}; each
type-1 packet synthesizes a press+release PAIR (daemon auto-release; the
pair + EV_SYN read back from `/dev/input/event5` in leg 0). Both runs
PASS within budget.

## Leg C — dedup negative (seq is load-bearing)

After zero-visibility, re-painted already-consumed seqs 1000/2000, proved
them guest-visible, waited daemon poll cycles: testimony count pinned
**7 → 7**. Replayed packets re-inject nothing.

## Leg D — comparator mutant goes RED

`--mutant` shifts the prediction one sector: `legA run1: pred=15
changed=15 extra=15 missing=15 → FAIL / GATE FAIL (expected under
--mutant)`, exit 1. `output/bm905_n3_gate_mutant.log`. The exactness of
A/B is not slack.

## Malformed leg (E) — skip and count, never inject

Good seq 3000 (slot 88) + CRC-corrupted seq 3001 (slot 89, value byte
bit-flipped). Result: `skipped=11 seq3000=True seq3001_injected=False →
PASS` — daemon skip counter moved every poll over the bad slot, the good
key pressed, the malformed one never became an event.

## Cleanup

Daemon stopped; all `/var/tmp/bm905_*` removed and verified GONE (incl.
leg-0-era root-owned files); window zero-filled and re-verified through
the GUEST dd plane with a quiescence double-check (two zero confirmations
15 s apart). Post-run check: `NO-DAEMON`, `GUEST-CLEAN`. Container state
net-unchanged modulo FS-dead window bytes, which read zero.

## Honest boundaries

Poll-loop daemon (200 ms), not an interrupt path. Single guest session.
Shim-era painter (livemap + `/writeback` barrier) — the bare-metal
analogue replaces it with a physical HID dongle; NOTHING in the protocol
depends on QEMU except latency numbers. This gate proves event synthesis
inside the guest from host-writable bytes; it does NOT prove input
delivery to a machine whose disk the host cannot write (Rung 8, different
writer). Measurement traps documented for successors: `Container.read`
caches decoded frames per instance (clear or fresh-instance before
re-read); journal folds serialize ~34 s and can land late — always
heal+verify zero immediately before a paint leg (`output/bm905_heal_window.py`).

## RED history (process honesty)

Gate v1–v3 REDs were fully attributable, none to the medium: probe-side
window-size/frame-cache bugs (N2 v1), daemon dedup vs SYN slot-order and
dd-timeout death (v1/v2), and a JSON serialization crash (v2). v3's legE
RED was a RACE WITH OUR OWN LANE: a second, insufficiently-killed gate
instance ran concurrently and re-painted/zeroed the window mid-run plus
stole the testimony archives at its cleanup (proof: stale
`bm905_gate_result.json` with numbers absent from v3's log; empty testify
archive despite legB PASS lines). v4 ran as a verified single instance
(ps) with quiescence double-checks and PASSED every leg. Credentials: the
two plaintext password lines found during the lane are gone; zero
`<SUDO_PASSWORD from .env>` literals remain in any `bm905_*.py`.

## Follow-on ladder (filed, NOT built)

Mouse/multi-event packets (usb-tablet absolute = 6 B); guest→host ACK leg
over BM903 read-direction (closes full duplex over the medium); mind-state
probe (ranked BELOW this mailbox by Jericho's 2026-09-19 ruling;
re-briefable as BM906); crash-consistency legs from BM904's follow-on list.
