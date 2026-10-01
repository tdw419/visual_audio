# RECEIPT_R51_installer.md — R5.1 installer/launcher artifact (P5)

**Rung:** PRODUCT_ROADMAP.md P5 R5.1 — "An installer/launcher artifact:
one file, boots on Jericho's machine."
**Landed:** 2026-09-21 ~18:3x CDT, builder af3e62239ce2, HEAD 7c5b2a7b + this commit.
**Artifact:** `glyphos_installer.py` (6.2 MB, sha256
86b4865211dc09b463e6ef59491f3f37657411db886409d3d393fa751efe3e7f) at the
repo root. ONE file: stdlib launcher head + base64 gzipped payload
(4.86 MB tar.gz: 20 boot-chain modules + `db/wordbase.db`) + sha256
manifest. Rebuild: `.builder_queue/embed_r51.py` (after
`.builder_queue/build_r51_payload.py`).

## What "boots" means here (the honest chain)

The installer boots the **GlyphRunner substrate's agent fleet to
fleet-ready** — the exact chain R3.1 gated (atlas → fleet bake →
GlyphRunner → run_wgsl to halt), then host-verifies the frozen fleet
words from `receipt["ram"]`:

- receipt word `0x5EED0005` @765, done bits `0b1011` @717
- results `{714: 6, 728: 12, 748: 20, 763: 30}` = y=x·(x+1) on seeds
  2/3/4/5 (R1.3 task parity), measured GREEN exit 0 in 4.6s of gate
  wall-clock (cold run inside the temp tree: imports 0.73s + atlas
  0.03s + bake 0.006s + run_wgsl 0.75s; 458 steps, halt).

Measured GREEN run (twice, deterministic; `/tmp/r51_green.log`,
`/tmp/r51_green2.log`):

```
Glyph OS boot receipt
  status      : fleet_ready_verified
  halted      : True  steps: 458
  timings_s   : {'imports': 0.726, 'atlas': 0.031, 'bake': 0.006, 'run_wgsl': 0.747}
  receipt word: 0x5eed0005
  done bits   : 0b1011
  result[714]  : 6
  result[728]  : 12
  result[748]  : 20
  result[763]  : 30
```

## RED legs at landing (shown before/alongside the green)

1. **Corrupted manifest** (`--corrupt-verify`): the installer corrupts
   the fleet-image module's manifest entry itself; the GOOD payload must
   be REJECTED before any boot.
   ```
   exit=1
   installer: PAYLOAD REJECTED (1 bad, 0 missing)
     tools/glyph_gpt/agent_resident.py: sha256 mismatch
   ```
2. **Torn payload** (`.builder_queue/probe_r51_torn_payload.py`, gate
   leg L5): one flipped bit in the EMBEDDED PAYLOAD bytes (not the
   manifest) → exit 1 + `PAYLOAD REJECTED` + NO boot
   (`fleet_ready_verified` absent). Discriminating: a broken integrity
   gate would boot the torn payload and exit 0.
   ```
   installer: PAYLOAD REJECTED (1 bad, 0 missing)
     db/wordbase.db: sha256 mismatch
   RED-leg(payload tear): exit=1 rejected=True no_boot=True => PASS
   ```
   (Landing note: the flipped byte landed in `db/wordbase.db` — the
   manifest catches a tear of the data payload as readily as a code
   module.)

## Gate

`tests/test_r51_installer.py` (force-added past `.gitignore`'s
`test_*.py` rule), 5 legs, **5 passed in 4.62s**:

- L1 GREEN `--skip-boot` verifies payload (exit 0, 21 members, ~110 ms)
- L2 RED corrupted manifest rejected (exit 1)
- L3 GREEN full boot → fleet_ready_verified + frozen words (skipped
  wgpu-free)
- L4 GREEN `--json` machine-readable receipt parses, words exact
- L5 RED torn payload rejected, no boot

Lane regression: `test_r41/test_r42/test_r43/conformance/glyph_run/gh26_fleet`
**38 passed** — zero production lines touched.

## Scope

New files only: `glyphos_installer.py`,
`tests/test_r51_installer.py` (force-add),
`.builder_queue/{build_r51_payload.py, embed_r51.py,
probe_r51_torn_payload.py, payload_r51.tar.gz,
payload_r51_manifest.json (force-add: `*_manifest.json` ignored)},
`RECEIPT_R51_installer.md`, plus the ledger update. The two pre-existing
dirty files (`.hermes_guest_context/guest_state.json`,
`ubuntu_desktop_pxc1_v3_selfhost/frame_00230.png`, last touched by other
sessions at 3418a564-era state) are NOT mine and NOT committed.

## Honesty — what this PASS does NOT prove

- **Not a kernel-image boot.** No virtio-pixel guest, no Alpine Linux,
  no boot sector. The substrate booted is the GlyphRunner WGSL machine
  (same honesty note as R3.1/R3.2).
- **Not a second-machine claim.** R5.1 says "boots on Jericho's machine
  (and a second machine, if one exists)". This receipt covers THIS
  machine only (RTX 5090, wgpu 0.32.0, python 3.x + numpy 2.4.6 + PIL).
  The installer carries no compiled artifacts and needs only
  python3/numpy/wgpu/Pillow, but no other machine was tested.
- **Payload scope is the boot chain, not the whole repo.** 20 modules +
  wordbase.db, chosen because `build_default_atlas → resident_image →
  GlyphRunner.run_wgsl` transitively imports them (wordbase.db ships
  because OpcodeMapV2 colors are wordbase-derived — cross-machine bake
  determinism). tools outside that graph (e.g. glyph_run.py, glyph_cc.py)
  are not in the artifact.
- **Extraction model:** the installer extracts to a fresh `tempfile.mkdtemp`
  per run and removes it at exit; nothing is installed persistently. A
  true "install to a location and re-run" story (PATH shim, desktop
  entry) is NOT built — R5.1's wording ("installer/launcher artifact")
  is satisfied by the launcher; the install-side UX is future work.
- **No rate claims** → floors/check_regime N/A (no performance numbers
  quoted; the timings line above is descriptive context, not a gate).
- **Determinism caveat:** boot is deterministic across re-runs on this
  host (frozen words identical, 458 steps twice); cross-GPU determinism
  of the shader path is NOT established.

## Next rung

R5.2 (stranger documentation) or, if Jericho rules R2.3
LANDED-PENDING-REVIEW resolved, that ruling's scoping. Re-verify HEAD
first — parallel sessions land rungs mid-flight.
