# RECEIPT — BM903 guest-side handoff provenance gate

**Date:** 2026-09-19 (builder cron af3e62239ce2)
**Brief:** `.builder_queue/brief_bm903_guest_hermes.md` (contract-complete,
committed 5679b189/e69a6e84)
**Gate:** `python3 tools/bare_metal_poc/rung9/guest_provenance_gate.py` —
**GATE PASS, exit 0** (`output/bm903_gate_run5.log`; RED-first defect tail in
`output/bm903_gate_run1.log`)

## Question answered

Does the guest's own read path serve exactly the bytes our chain writes —
verified FILE-level from inside the running pixel-booted VM, not just
byte-level from the host? Measured: **yes**, with a three-way agreement.

## Gate legs (run5, 2026-09-19 ~02:5x)

- **Leg 1 (chain A, guest):** guest Hermes v0.19.0 (via
  `guest_bridge.py hermes_run`, bounded, 24 s) wrote
  `/var/tmp/bm903_probe.bin` (2400 B) itself and quoted back
  `sha256sum` + `od -A d -t x1 -N 16`. Guest sha == expected
  (`486faab1b518d5ad…`). `filefrag -v`: **1 extent**, first disk byte
  12,990,693,376 (frame 194).
- **Leg 2 (chain B, pixels):** `locate_in_container.py verify` reconstructed
  the 2400 B from container PNGs alone: `recon_sha256 == expected_sha256`,
  rc=0 (`output/bm903_gate_verify.json`).
- **Leg 3 (chain C, guest-equivalent disk):** after
  `livemap_probe.evict` (>16 cold frame decodes), backend `/peek` at the
  first disk byte returned `0x42` == payload byte 0 == the byte guest
  Hermes quoted from `od`. Three-way agreement measured.
- **Leg 4 (RED, discriminating):** guest Hermes `rm + sync`; `test -e`
  → rc=1 (file gone); `verify` now **RED** (rc=1,
  `TRANSIENT-EXHAUSTED: guest command failed after 3 attempts …
  'filefrag -v /var/tmp/bm903_probe.bin'` — no subject to map).
  Measured honestly: `/peek` after rm STILL returns `0x42` — stale pixels
  persist until overwritten (a plain rm does not journal-fold); the RED is
  the guest-half of the chain, and the peek persistence is recorded, not
  hidden. Artifacts: `output/bm903_gate_red.json`.

## Defect found and fixed during bring-up (RED first)

**Run1** (`output/bm903_gate_run1.log`): payload embedded in the Hermes
prompt (`printf '%s' '<2400 B>'`) is NOT byte-faithful — the LLM rewrote
the repeat count (2400 B → 2750 B, guest sha `585d5fa5…` ≠ expected
`8cd8e698…`). **Fix:** payload travels via the shared 9p mount
(`.hermes_guest_context/bm903_seed.bin`, host-written) and Hermes' single
bounded action is `cp seed probe` — the guest-side write is still performed
by guest Hermes, but no bytes pass through the prompt (run2: 20 s, sha
match).

## Scope

`rung9/guest_provenance_gate.py` (new), `rung9/RECEIPT_BM903_GUEST_PROVENANCE.md`
(this file), ROADMAP.md TASK_BM903 sub-row, `output/bm903_gate_*` artifacts.
Guest writes limited to the probe file (rm'd + sync'd in-leg, verified gone);
no sudo, no guest service restarts, no compaction calls; rung1-7 + oracle
dumps untouched.

## What this PASS does NOT prove

- **Not the BM903 e2e boot** (`brief_bm903_e2e_pixel_boot.md` — brief
  `7f413004`): no 16-bit stage2 was executed; this gate closes the
  *provenance* question only (guest logical file == pixels ==
  guest-equivalent disk bytes).
- **n=1 file, 1 extent**: a 2400 B single-extent file; multi-extent/
  frame-crossing behavior was proven separately by locate_in_container's
  n=4 (160 MiB, 3 frame boundaries) and is not re-measured here.
- **Leg-4 peek persistence is a property of this container state** (no
  concurrent overwriter of LBA-adjacent blocks during the ~seconds
  window); it is not a guarantee.
- `hermes_run` prompts were bounded and quoted-output style (2 prompts,
  24 s each), but the guest model remains LLM-mediated: the byte-faithful
  path is the 9p seed file, not the prompt.
- The 300 s hermes_run cap was not approached (24 s); behavior near the
  cap untested.
