# RECEIPT — R4.2 display output (pixel-perfect frame presentation, VCC-preserving)

Rung: PRODUCT_ROADMAP.md:74 — "R4.2 Display output: pixel-perfect frame
presentation, VCC-preserving."
Builder: af3e62239ce2 (2m lane), 2026-09-21, commit (this).
Ledger updated: .builder_queue/PRODUCT_LANE_STATE.md (same commit).

## Deliverable

`.builder_queue/probe_r42_display_frame.py` — the machine's committed
RAM presented as a display frame, verified pixel-perfect:

- Runs the LANDED fleet image on the SHADER PATH (GlyphRunner.run_wgsl,
  R1.4-converged) to HALT (458 steps).
- Presents receipt["ram"] (16,384 words) as ONE 128x128 RGBA frame:
  pixel at Hilbert index d = word ram[d]; RGBA = the 4 word bytes, MSB
  in red. Curve = tools/vcc_validate.d2xy (the repo's canonical VCC
  Hilbert mapping, AGENTS.md "Hilbert Mapping Coherence"). 16384 =
  128^2, so the whole machine RAM is exactly one frame.
- Decodes the frame back and verifies WORD-EXACT against the machine's
  RAM, plus the SEMANTIC leg: frozen words read OFF THE FRAME match the
  fleet contract (0x5EED0005 @765, done=0b1011 @717, 0xFA026 @731,
  results {714:6, 728:12, 748:20, 763:30}).
- VCC leg: structural hash of the decoded payload stable across a
  re-encode/re-decode cycle.

Gate: tests/test_r42_display_frame.py — 5 legs:

1. GREEN exit contract: probe exits 0, prints DISPLAY-FRAME: MATCH.
2. RED: --corrupt-verify exits 1 (corrupted verifier REJECTS the good
   frame — verifier is load-bearing).
3. RED: --torn-frame exits 1 (a ONE-BYTE tear of ONE pixel post-encode
   is DETECTED against the word-exact contract — presentation-fault
   detection is load-bearing).
4. Curve sensitivity / non-vacuity: a LINEAR (non-Hilbert) presentation
   of the same words must NOT read back word-exact — the gate cannot
   pass on an arbitrary pixel mapping.
5. Byte-container agreement: the frame payload repacked into the repo's
   canonical vcc_validate byte-container (SPECIAL_OFFSET, alpha
   terminator) survives decode_rts_png byte-exactly.

## RED-first evidence (at landing time, true exits via file redirection)

RED leg 1 — --corrupt-verify (BEFORE any green):

```
EXIT=1
machine: halted at 458 steps (shader path)
frame[765]=0x5eed0005 frame[717]=0b1011 frame[731]=0xfa026 results={714:6,728:12,748:20,763:30}
structural hash: 0f6f2a7699f9b2fa... stable=True
R4.2 corrupt-verify RED leg: verifier REJECTED the good frame (correct discrimination)
```

RED leg 2 — --torn-frame:

```
EXIT=1
machine: halted at 458 steps (shader path)
frame[765]=0xa1ed0005 ...            <- the 0x5E->0xA1 tear, visible
structural hash: 5548d4f86cf45c58... stable=False
R4.2 torn-frame RED leg: presentation fault DETECTED (pixel tear caught against the word-exact contract)
```

GREEN:

```
EXIT=0
machine: halted at 458 steps (shader path)
frame[765]=0x5eed0005 frame[717]=0b1011 frame[731]=0xfa026 results={714:6,728:12,748:20,763:30}
structural hash: 0f6f2a7699f9b2fa... stable=True
R4.2 DISPLAY-FRAME: MATCH (16,384 words word-exact off the frame incl. frozen receipts; VCC-preserving round-trip, hash stable)
```

Gate run (RED-first, real): first run of the gate suite was 1 failed /
4 passed — leg 5 encoded 16,384 bytes into a 64x64 (4,096-byte) grid.
Fix: 128x128 grid (1 byte per pixel in the byte-container). Re-run:
5 passed. Lane regression (r41, conformance, fleet, arrive, glyph_run,
r42): 38 passed.

## What PASS does NOT prove

- No real display hardware / scanout exists. This is the
  frame-presentation + VCC-preservation contract over the substrate's
  committed RAM — a PNG frame the host can decode, not a monitor
  driver, not the virtio-pixel guest (exempt lane, GOVERNANCE_PROTOCOL
  ban respected — zero lines touched there).
- No claim that the GUEST paints its own framebuffer: the frame is the
  HOST presenting machine state. A guest-driven paint path remains
  future work.
- One image family, one host/GPU; results = {6,12,20,30} on seeds
  2/3/4/5 only.
- No rate claims → floors/check_regime N/A with that reason (one cold
  rung-shaped run per leg; quoting steps/s off it would repeat the
  R1.3 receipt-hygiene defect).

## Defects found and kept during the work

- First codec draft packed words 24-bit (BK-2 readback convention) —
  that silently drops word 765's top byte (0x5EED0005 reads as
  0x00ED0005 off the frame). Caught because the probe's own detail line
  contradicts the expected frozen value; fixed to 32-bit RGBA (word top
  byte in alpha). The BK-2 packing is a READBACK convention, not a
  presentation contract — recorded here so nobody re-derives it wrong.
- Leg 5 grid-size defect above (caught by the gate going RED).

## Exclusions

- WGSL/CPU parity NOT re-proven here (R1.4 owns that; this rung runs
  the shader path only).
- test_r41 tick-interleaving leg still owns the mailbox-path input
  story; this rung adds the output half only.
