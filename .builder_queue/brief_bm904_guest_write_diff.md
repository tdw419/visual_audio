# BRIEF — TASK_BM904: Guest write-side pixel diff (inverse provenance gate)

**Row:** proposed → `tools/bare_metal_poc/ROADMAP.md` Rung 9 (after BM903, which landed GATE PASS 2026-09-18 22:14)
**Provenance:** Jericho 2026-09-19 ~07:4x — "what if you told hermes the path to
the container then it could make a change and potentially see what change was
made in the container… how can we build on this idea?"
**HARD scope:** read-only guest discipline except the probe file. No backend
rebuild/restart. No edits under `systems/virtio_pixel_rs/` (parallel-session
WIP lives there — see RULING_20260919_monitor_newest_mtime_epoch.md). Lands
only: this gate's script + receipt + roadmap cell. Reuse
`tools/pixel_container/locate_in_container.py` as a library (import the chain
functions; do not fork the address math).

## Scope (files this brief may change)

**Files in scope:**
- `tools/bare_metal_poc/rung9/bm904_write_diff_probe.py` — the gate script (new file)
- `tools/bare_metal_poc/rung9/RECEIPT_BM904_WRITE_DIFF.md` — the gate receipt (new file)
- `tools/bare_metal_poc/ROADMAP.md` — the Rung 9 row/cell only

**Do NOT** touch `systems/virtio_pixel_rs/` (parallel-session WIP — see
RULING_20260919_monitor_newest_mtime_epoch.md) or the backend restart path.
**Interfaces are LOCKED.** If a signature in
`tools/pixel_container/locate_in_container.py` looks wrong, STOP and report —
never weaken a live guard to make a step pass.

## Why (build-on from BM903)

BM903 proved the read direction: host reconstructs bytes from pixels ≡ guest
file ≡ /peek. BM904 closes the WRITE direction: the guest writes random bytes,
and the host must find **exactly** which pixels changed — turning the
correctness check (yes/no) into a live FS-block→pixel mapping tool (where).

## Endgoal alignment (Jericho, 2026-09-19: these tests scaffold the shim's replacement)

The endgame for this line is a bare-metal boot path that REPLACES
`systems/virtio_pixel_rs` — the shim era is the oracle era. Judge every part
of this gate on whether it survives the shim's deletion:

- **SURVIVES (the deliverable):** the address chain (medium layout is
  decoder-independent), the decoded-pixel diff primitive, the control-leg
  noise-floor method. Together these are the verified medium contract any
  replacement decoder must honor — oracle-first, TC-1 pattern.
- **DIES WITH THE SHIM:** R1 (peek/PNG asymmetry) is shim-forensics.
  Measure it, record it, do not deepen shim internals beyond R1.

## Method

1. **Preallocate before writing** (kills the ext4 delayed-alloc chicken-and-egg):
   guest runs `fallocate -l 64K /var/tmp/bm904_probe.bin && sync`, then
   `filefrag -v` — extents are now known BEFORE any data exists.
2. **Snapshot:** host decodes the affected frame(s) to pixel arrays (RGBA,
   decoded level — never diff PNG bytes; re-encode is non-locally different,
   decoded pixels are lossless).
3. **Write:** guest writes 256 random bytes (from /dev/urandom, saved
   guest-side for the assertion) at a known intra-file offset via
   `dd conv=notrunc`, then `sync`.
4. **Barrier:** host `POST /writeback`, verify `ok:true`
   (locate_in_container already asserts this pattern); `watch` shows no dirty
   frames pending.
5. **Diff + assert:** re-decode frames; the changed-pixel set must EQUAL the
   expected set = bytes of the random write mapped through the chain
   (extent lba → disk byte = block*4096 + vda3_start*512 → frame/intra →
   x,y,channel). Pixel granularity: a pixel is in the set if ANY of its 4
   channels is covered.
6. **Control leg (noise floor):** repeat steps 2–5 with NO guest write; the
   changed set on a live guest is nonzero background (jbd2 journal commits,
   syslog). Assertion form: treatment changed set ⊆ expected ∪ control-noise,
   and |changed ∩ outside-expected| ≤ |control-noise| on the same frames.
   If control noise on the affected frames is zero, assert exact equality.
7. **RED legs:**
   - **R1 durability boundary (expected, not forced):** AFTER step 3 but
     BEFORE writeback, `/peek` at the first written disk byte should already
     serve the new byte (overlay plane) while the disk PNGs still decode the
     old byte. Measure it. If peek does NOT lead the PNGs, that is a finding
     about the peek plane's overlay awareness — record it, do not tune the
     backend.
   - **R2 diff sensitivity:** host paints one byte of the written region back
     to a different value, re-decode, assert the diff catches exactly that
     channel. Restore, re-verify. (livemap_probe conventions: full revert,
     re-verify.)
8. **Cleanup:** guest `rm + sync` the probe file; container byte state net
   unchanged modulo PNG re-encode.

## Verification (row gate)

- [ ] Changed-pixel set equality (or noise-floor attribution) measured on
      ≥2 runs, different random bytes, at least one write crossing a
      frame boundary (offset chosen near the 64MiB edge).
- [ ] R1 asymmetry measured and recorded either way.
- [ ] R2 sensitivity demonstrated (1-byte catch) + restore re-verified.
- [ ] Control-leg noise floor quantified (pixels/frame/window).
- [ ] Receipt `rung9/RECEIPT_BM904_WRITE_DIFF.md` + roadmap cell; guest-Hermes
      prompts bounded (<300s, quoted-output style) per BM903 capability map.

## Follow-on ladder (do NOT build now — file as backlog rows)

The write-diff primitive unlocks, in order: crash-consistency legs (kill -9
guest between write and writeback → assert journal recovery on reboot);
block-level guest-state snapshot to pixels (VAMP-adjacent); diff-summary
uplink over the dual-band audio channel.

Backlog note (Jericho 2026-09-19): the input-mailbox idea (host paints
[seq,type,code,value] packets into a reserved LBA window; guest daemon polls
its own /dev/vdX and injects via uinput) is shelved as a REPLACEMENT-scaffold
deliverable, not a shim-era feature — it only makes sense once the decoder
running the guest is the one being tested. Its verification design reuses
BM904 (paint → diff → prove pixel landing → guest testifies receipt).
Bare-metal endgame of the same idea = HID-injector dongle (hands) + HDMI
capture (eyes); design carries, writer address changes from livemap paint
to USB plug.
