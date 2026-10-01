# RECEIPT — CLAIM QUEUE item 35: reactive agent state machine runtime (GlyphReactive)

**Builder:** af3e62239ce2 (GLM cron lane) · **Date:** 2026-09-26 ~16:3x CDT
**Landed commit:** 86be9194
**Claim basis:** Phase-1b, QUEUE_STATE.json item-35 (`blocks_on: [item-34]`, landed `ad9edcf9`). Mailbox rule clean: newest RULING mtime 1790127513 < HEAD epoch 1790449823 at claim time.
**Provenance:** resumed a staged tree left by a cut-off prior tick (A: tests/test_item35_reactive.py + tools/glyph_reactive.py, exactly 2 files). Provenance re-verified against HEAD e5f076d4 and QUEUE_STATE before gating; monitor delta CLAIM_PENDING→DIRTY_ACTIVE explained by the staged files.

## What landed (commit <this>)

- `tools/glyph_reactive.py` — ReactiveRuntime: host-side kernel-class driver for a guest reactive agent. Read (guest LDs of a 6-word contract row at wire offsets 35..40 — no overlap with the item-34 channel wire [0,35)); Evaluate (FSM entirely in guest instructions: event-dominance check, p0 jump dispatch, state-dependent re-arm); Act (guest ST of the resolved state to the act slot); Paint (fenced in-tile color via the documented masked path). Each tick commits the action word over the GlyphChannel (item-34 wire, seq/CRC/ack) and appends to the transitions ledger.
- `tests/test_item35_reactive.py` — the gate: R1-R7 + N1-N3 (10 legs). N1 = engine-byte guard (glyph_isa_v2.py byte-identical to HEAD); N2 = non-vacuity (garbage quiet percept must STAY, not default); N3 = fence containment (rogue cross-fence ST reaped EXIT_FAULT); R7 = migration (item-34 gate re-runs GREEN in subprocess).

## Gate evidence (RED first, then GREEN — both on this exact tree)

RED run 1 (`output/item35_gate_af3e_full.txt`): **5 failed, 5 passed in 418.12s.**
Root cause (two defects in the cut-off staged FSM):
1. `:commit` block inverted: `CMP r18 r17; JNZ :store; LDI r18 -1` stored the stay marker (0xFFFFFFFF) exactly when the computed state EQUALED the current state (CMP sets r0 on equality; JNZ jumps when r0 clear). Fix: test r18 against the marker itself (`LDI r13 -1; CMP r18 r13; JNZ :store`), and resolve a stay by RELOADING the current state from the act slot (still pre-store) — no MOV in the ISA, the reload is the register move.
2. `:k0` arm hardcoded `p0=NONE → scan` regardless of current state, breaking the locked transition "approach + quiet → stay" (R6). Fix: k0 is state-dependent (`CMP r17 STATE_APPROACH; JZ :k0_stay`), matching the claim supply's transition table.

RED run 2 (`output/item35_gate_af3e_green.txt`): **1 failed, 9 passed in 417.63s** — R5 composite assert unpacked RGB in the opposite byte order from the LOCKED item-31 composite encoding (glyph_stratum.py:251 renders `(R<<16)|(G<<8)|B`; gate expected low-byte-red). Implementation matched the landed ABI; fixed the gate's unpack order with a comment citing glyph_stratum.py:251. This is a byte-order correction against a locked interface, NOT a guard weakening — the leg still fails if the composite lacks the agent's painted color.

GREEN (`output/item35_gate_af3e_green2.txt`): **10 passed in 415.54s** (full, incl. subprocess R7 migration leg running the item-34 gate).

## What the PASS does NOT prove

- No GPU/WGSL execution — host CPU engine, Phase-2 doctrine (N1 pins the engine bytes to prove it).
- Perception is a contract-row read, NOT a composite readback; cross-window SENSE is structurally impossible (private RAM copies) and never claimed.
- Cooperative seed-then-run only; no preemption. Fresh agent task per tick.
- The FSM is fixed at assemble time — a real FSM, not a learned policy.
- No rates/latencies asserted (rule-1 floors do not attach; no floors citation needed).
- Stay-marker COLOR resolves through the masked path to the flee band; stay color is not a contract (gate asserts action words for stay legs).

## Scope

Tracked changes: exactly `tools/glyph_reactive.py`, `tests/test_item35_reactive.py` (+ this receipt, ledger, QUEUE_STATE). Engine, stratum, channel, shell untouched (N1 asserts byte-identity of the engine).
