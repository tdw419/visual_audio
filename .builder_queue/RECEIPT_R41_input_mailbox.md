# R4.1 Keyboard/Mouse Input into the Mailbox Path — Receipt (2026-09-21)

## Rung

PRODUCT_ROADMAP.md:73 (R4.1): "Keyboard/mouse input into the mailbox
path (BM905 lineage)."

## What landed

- `.builder_queue/probe_r41_input_devices.py` — the input-device seat:
  keyboard + mouse event records delivered to the machine through the
  mailbox ABI (host RAM writes between step() calls — the exact
  mechanism the R1.1 arrive leg froze: flag@742 + payload@760).
  Zero production lines changed.
- `tests/test_r41_input_mailbox.py` — the gate (4 legs, below).

## Mechanism (all over LANDED channels)

- **Device record** (4 words, probe-private RAM map @3040..3043):
  marker (ordinal+1, 0 = empty), type (1=KEY, 2=MOUSE), code (scancode
  / button mask), aux (modifiers / packed dx,dy).
- **Guest daemon** (GlyphAssemblerV2 program, 45 instrs): bounded
  poll loop (budget 3500 polls ≈ 42k steps, halting cleanly so a
  starved stream is verifiable) that claims each event (marker = 0,
  its own store), packs it to one word `(type<<16)|(code<<8)|(aux&0xFF)`,
  appends to the event log @3016, maintains the count word @3000, and
  HALTs at 8 events. The 0xAA sentinel @3032 guards overrun.
- **Host verify**: log read back word-by-word against the full
  8-event contract (4 KEY with scancodes/modifiers, 4 MOUSE with
  button/dy bytes), sentinel intact.

## Gate result (measured, this session)

GREEN (exit 0):
```
R4.1 seat posted 8 events in 441 steps; halted=True
R4.1 INPUT-MAILBOX: MATCH (8 events logged, sentinel intact) — keyboard+mouse events delivered through the mailbox path, host-verified
```

RED legs at landing (each exit 1, shown before green):

1. `--corrupt-verify` (verifier discrimination; exit 1 measured):
```
R4.1 corrupt-verify RED leg: verifier REJECTED the good log under wrong expectations (correct discrimination): log[0] 0x00011e00 != corrupted 0x5a5b445a
```
2. `--drop-event` (event-loss detection; exit 1 measured):
```
R4.1 drop-event RED leg: the 7-event log REJECTED against the 8-event contract (event loss detected): log count 7 != 8 (expected clean 8)
```

Regression: `tests/test_r41_input_mailbox.py` 4 passed; lane suites
(conformance + glyph_run + fleet + arrive + glyph_cc) 36 passed.

## Defects found and fixed during implementation (all in-probe; zero
## production lines changed)

1. **Zero-constant register held an address** (`LDI r6 3000` then used
   as zero for CMP/claim-stores): the daemon stored 3000 into the slot
   marker on claim, so the seat's next post read marker=3000 ≠ 0 and
   the daemon double-claimed garbage. Fix: `LDI r6 0`.
2. **Budget decrement only on the claim path**: a starved stream never
   decremented, so `--drop-event` spun to the 60k-step cap instead of
   halting with a 7-event log. Fix: `:tick` decrement on the empty-slot
   path too. Then the budget (5000) was still too big once BOTH paths
   decremented (~12 steps/poll measured → 60k steps) — sized to 3500
   (~42k steps, under the cap).
3. **Vacuously-green drop leg**: `_expected_events()` trimmed the
   expectation list under `--drop-event`, so the leg verified a 7-event
   run against a 7-event contract — it detected nothing. This is
   exactly B3's "prediction written before the measurement" trap: the
   RED leg passed trivially until caught. Fix: the verifier ALWAYS
   holds the full 8-event contract; only the seat's device stream
   drops.

## What this PASS does NOT prove

- **No WGSL shader-path leg.** `run_wgsl` executes to HALT in ONE call
  with no per-step host hook, so a post-boot event stream cannot be
  expressed on the shader path; pre-posting all events before the run
  would not exercise the mailbox path (it would drain a pre-seeded
  queue). The guest source assembles unchanged for a future hooked
  runner. Recorded as the open substrate gap, not faked.
- **No real device hardware.** This is the mailbox-path EVENT channel
  (BM905 lineage: input drives work), not a PS/2/USB driver. There is
  no device emulator, no scan-code translation table beyond the
  probe's 8-event script.
- **No interrupt-driven delivery.** The daemon polls a rotating slot
  within a bounded budget; the GH-16 timer is orthogonal. The gate's
  leg 4 host-simulates the tick cadence — the real in-guest tick
  handler is exercised by the R1.1/R1.2 suites, not here.
- **No rate/floor claims** (floors authority not engaged).
- The event-record layout (4-word record, packing) is a PROBE contract,
  not part of the frozen BOX_ABI_v2 surface; promoting it into the ABI
  would need a minor-version bump per the freeze's change policy.

## Verdict

Keyboard and mouse events flow from the host seat into the machine
through the mailbox path, are drained in-guest under a bounded poll,
and are host-verified word-by-word — with both RED legs demonstrably
able to fail. R4.1 (mailbox-path leg): PASS. Device-driver and
shader-path legs: not claimed (blockage recorded above).
