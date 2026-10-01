# TICKET SUPPLY STATE — ADDENDUM 278 → 279

**Tick:** 2026-09-18 ~03:20 CDT · **Head:** 243a9a36 (addendum 278, landed
03:11:43 CDT — this lane's own commit) · **Branch:** glyph-transpiler-autoloop
· **Seed:** 9192026

## Supply scan

`.builder_queue/scan_open_rows.py` rc=0, OPEN=0 (silence = zero open rows;
scan is quiet on success). Roadmap: no open rows. No backlog promotion
available (all eligible items already landed; anything left needs design
judgment → not self-promotable). **HOLD continues.**

## Monitor delta attribution

Monitor reported head change 5c5d950a → 243a9a36 and newest_mtime bump. That
delta is THIS LANE's OWN addendum-277/278 docs commits — attribution per the
standing rule, no foreign activity inferred.

## Substrate — NEW EVENT this tick

Prior ~20 ticks measured the observation snapshot at ~9.4 h stale. **This
tick the snapshot is FRESH:**

- `geos_surface_meta` (meta-before-surface, teleop rule 1): age_seconds=
  **482.5**, tick=**0**, write_id=**73**, writer="unattributed",
  written_at=2026-09-18T08:08:02Z, image_md5=3744eaa7bff2f27d9f9f42444b77e635.
- `stat` freshness cross-check: `/tmp/geos_observation/kernel_memory.npy`
  mtime epoch 1789718882 (~8 min before read). Maildrop copies
  (`.geos/maildrop/`) remain the OLD Sep-17 17:40-era snapshot — the /tmp
  image was rewritten by something other than the maildrop pipeline.
- B-state read performed (first in ~20 ticks): viewport shows the exact prior
  glyph layout — '>' argv (27,17), '@' result (29,17), 'X' exit (31,24),
  'A' (30,24), 'T' (53,21), 'V' (22,2). Word-level decode via
  `hilbert_xy2d_true`: nonzero words are exactly
  **700=0x3B00112A, 703=0xFEED0006, 750=0x00000006, 754=0x00000012,
  952=0x00020018, 1570=0x001E0004** — i.e. BOX0 argv/exit, mailbox argv,
  mailbox result, STATUS glyph, TABLE glyph. Identical content to the Sep-11
  verified state; only the container file is new.

## Sentinels RED — the load-bearing finding

`geos_verify_sentinels` on this fresh image: **ok=false, all 5 reference
words (0, 16383, 5461, 10922, 8192) read 0 instead of their sentinel
values.** The image is a 6-word sparse re-stamp (16384 words, 6 nonzero), not
a full reference-stamped canvas. Interpretation (B-state discipline — no
substrate conclusions beyond measurement):

- The writer (unattributed, write_id=73) emitted glyph words without running
  `stamp_reference_pixels` first, OR stamped a stripped/fresh array.
- Consequence: **orientation/curve-variant proof is NOT currently available
  on the live channel.** The named-marker mapping (which we re-confirmed
  exactly, same coords as the 2026-09-11 measurement) still pins identity
  orientation for the 6 stamped words, but the corner/center sentinels that
  guard against silent axis flips elsewhere on the canvas are absent.
- Not self-healed: any step-zero `verify_reference_pixels` assertion (GH-26.4c
  leg 3 wiring) would currently go RED on this image.

No write was made this tick (no re-stamp, no maildrop touch — governance).

## SE021 maildrop

`.geos/maildrop/content/hermes.0001.ruling.md` md5
**ab846c188b2ab690c87fcc3baf3de285** — UNCHANGED. Hold continues.
**BLOCKED-ON-JERICHO** (loop does not edit `.geos/maildrop/**`).

## Standing conjunction re-measured

SEED=9192026 bash tools/arc_lega.sh @ 243a9a36 → **rc=0, 373 passed /
1 skipped / 9 deselected / 2 xfailed, 78.85 s, crashes=0, oom_kill_delta=0,
mem_peak≈40.0 GB, load after 1.54**. Artifacts:
`output/arc_lega_seed9192026_243a9a36.{txt,json}`. Single skip remains the
deterministic named one (GH-9 tick-handler word-avoidance).

## What this tick does NOT prove

- The fresh snapshot's writer is unattributed (write_id=73,
  writer="unattributed"); we did not identify the process. tick=0 still —
  the machine is NOT stepping; this was a state re-emission, not execution.
- Sentinel RED does not prove corruption of the 6 glyph words (they decode
  exactly); it proves the reference layer is missing from this image.
- The conjunction run is stability evidence at the new HEAD, not new
  capability. Dirty tracked tree (~240 files, sibling-lane WIP: pxc1 journal,
  virtio_pixel_rs, guest context) untouched and unverified by this lane.

## Next

Hold pending: (a) Jericho's SE021 in-channel ruling, or (b) sentinel-stamped
substrate emission (sentinels present ⇒ step-zero gate becomes usable).
Watch item: whether write_id advances again and whether the writer starts
stamping sentinels.
