# BRIEF — R3.1 cold boot to agent-fleet-ready <60s, measured

## Spec pointer (READ FIRST)

- `PRODUCT_ROADMAP.md` (RATIFIED 1827f6cb) lines 64-65 — R3.1: "Cold boot
  to agent-fleet-ready <60s on this hardware, measured, receipts with
  floors attached (policy rule 1)."
- `.builder_queue/PRODUCT_LANE_STATE.md` — STATUS: ACTIVE; R1.4 LANDED
  (cee0d963); P2 (R2.1/R2.2/R2.3) fully landed at HEAD → P3 R3.1 is the
  next eligible rung.
- `.builder_queue/POLICY_standing_decision_delegation.md` rules 1-4;
  floors authority: `.builder_queue/floors_authoritative.json` (ONLY
  citable file, 12h window) + `RECEIPT_floors_glyphrunner_extension.md`
  (GlyphRunner WGSL floors).
- R1.3 receipt-hygiene lesson (`RECEIPT_R13_preference.md:20-24,87-90`):
  LEG lines must be re-filed against a boot-shaped path — steps/s
  computed from the boot leg's own measured wall-clock and step count,
  validated by `.builder_queue/check_regime.py`, never raw wall-clocks
  posed as rates.

## Scope

MAY change (all additive):
- `.builder_queue/probe_r31_coldboot.py` — new probe (the gate).
- `.builder_queue/brief_r31_coldboot.md` — this brief.
- `.builder_queue/RECEIPT_R31_coldboot.md` — receipt.
- `.builder_queue/PRODUCT_LANE_STATE.md` — ledger update at session end.

MUST NOT change:
- `tools/glyph_gpt/agent_resident.py`, `tools/glyph_gpt/runner.py`,
  `tools/glyph_gpt/baker.py`, `tools/glyph_gpt/atlas.py`,
  `tools/wgsl_glyph_isa_v2.py`, `glyph_dispatch/**` — the measurement
  runs the LANDED artifacts unmodified (same rule as R1.3).
- `.builder_queue/floors_authoritative.json` and the calibrator — read
  only; if stale (>12h), regenerate via
  `calibrate_floors_authoritative.py` in its OWN process per the floors
  authority, never edit numbers by hand.
- Protected assets per AGENTS.md; other RULING/RECEIPT files.

## Gate command

```
python3 .builder_queue/probe_r31_coldboot.py                 # exit 0 (GREEN)
python3 .builder_queue/probe_r31_coldboot.py --budget-ms 500 # exit 1 (RED: budget)
python3 .builder_queue/probe_r31_coldboot.py --corrupt-verify # exit 1 (RED: verifier)
```

## Gate clause

- GREEN: 3 reps of the full cold chain (atlas → resident_image(fleet)
  bake → GlyphRunner init → run_wgsl to halt) complete with the fleet
  receipt host-verified each rep (ram[765]==0x5EED0005, ram[717]==0b1011,
  results == RES_FLEET_EXPECT); COLD total (rep 1, includes wgpu shader
  pipeline creation) < 60,000 ms; probe prints the LEG line computed from
  the boot leg's own steps and wall-clock and exits 0.
- DISCRIMINATING: `--budget-ms 500` MUST exit 1 (a sub-second budget is
  genuinely missed — proves the gate measures and enforces the threshold,
  not a constant); `--corrupt-verify` MUST exit 1 (fleet-ready is
  verified against the frozen words — a corrupted verifier must reject a
  GOOD boot, proving the readiness check is load-bearing).
- Receipt discipline: floors line cites floors_authoritative.json age
  (12h window); `python3 .builder_queue/check_regime.py
  .builder_queue/RECEIPT_R31_coldboot.md` exit 0.

## Failure evidence (the gate must be shown able to FAIL)

RED-first at landing: both RED legs above run BEFORE the green is
trusted, tails pasted in the receipt. Budget leg shows a real threshold
violation; corrupt-verify leg shows the verifier rejecting a measuredly
successful boot. If either RED exits 0, the gate is decoration — fix the
probe, not the ledger.

## Interfaces LOCKED

resident_image(mode="fleet", timer_quantum=6), GlyphRunner(img,
ram_words=16384).run_wgsl(max_steps=5000), RES_* word constants — all
LOCKED at HEAD cee0d963. Any mismatch = stop-and-ticket, not a signature
change.

## Definition of done

Probe GREEN exit 0 + both RED legs exit 1 + receipt with LEG lines +
check_regime PASS + ledger updated. What the PASS does NOT prove is
stated in the receipt (single image family; host-side bake included;
"warm" pipeline-reuse numbers reported but not gated; no claim about
booting a KERNEL image or the virtio-pixel guest path — this is the
GlyphRunner substrate's cold boot, measured on this hardware).
