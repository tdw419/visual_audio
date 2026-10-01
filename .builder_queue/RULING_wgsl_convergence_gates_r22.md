# RULING_wgsl_convergence_gates_r22 — divergence is a gate, not backlog

Issued 2026-09-21 ~15:0x CDT by the observer lane on Jericho's in-channel
direction. Cites: `242c19ec` (R2.1 freeze), `68b11265` (R1.3 PASS),
`RECEIPT_R13_preference.md`, `RECEIPT_R21_box_abi.md`,
`tests/test_box_abi_conformance.py`, `PRODUCT_LANE_STATE.md`.

His call, verbatim: "don't let P2's ABI freeze (R2.1) start against a
substrate that can't yet run the whole roadmap is about. Freezing sysmap
now, on the oracle path, risks freezing an ABI shape the eventual working
shader can't actually implement — better to close divergence first (or at
minimum, get it halts at 153/zero-fleet-words) as an R1.4-equivalent gate,
then freeze the ABI against the substrate that's actually going to run it.
Direct the lane to treat WGSL convergence as a gate, not backlog it past an
ABI freeze."

## Premise updated by events, stated plainly

R2.1 landed at `242c19ec` (14:48:14), before this direction was given.
**Nothing here reverts it, and the lane did nothing dishonest about it:**
the spec was extracted from landed code, its docstring at
`tests/test_box_abi_conformance.py:32` states "What this does NOT prove:
... WGSL parity", and `RECEIPT_R21_box_abi.md:54` records "WGSL shader path
still [divergent]". The artifact is an honestly-labelled doc + test. The
directive is therefore about **rung order from here**, plus one missing leg.

## The verified substrate fact that makes the gate non-optional

The conformance suite that "GREEN 7 passed" rests on drives the oracle and
only the oracle:

- `_boot_and_run` / `_boot_baked_ram`: `cpu = runner.get_cpu()` then
  `cpu.step(runner.image)` — `runner.py:41` returns a fresh **GlyphCPUv2**.
- `grep -c run_wgsl tests/test_box_abi_conformance.py` -> **0**. The WGSL
  path (`runner.py:133`) is exercised by ~10 other test files in `tests/`,
  none of them the ABI suite.

So `BOX_ABI_v2` is currently proven conformant against the substrate whose
shape it was read off. The suite cannot fail a shader that cannot implement
the ABI — it is not a fence, it is a mirror. Meanwhile the shader's known
state is `probe_r13_wgsl_fleet.py` halting at step 153 with all fleet words
0 (`RECEIPT_R13_preference.md:97`, and halt@99/198/153 across probes at :101).
R2.2 — "one command compiles a program to a glyph/tile artifact and runs it",
per `PRODUCT_ROADMAP.md:56` — is the rung that turns this spec into a
user-facing pipeline. Building it on a mirror is how an ABI shape gets
frozen without anyone noticing the freeze was never tested.

## Directive

1. **WGSL convergence becomes the active rung (call it R1.4), ahead of
   R2.2.** Definition of done, minimum: `probe_r13_wgsl_fleet.py` runs the
   4-tenant fleet to completion on the shader path with the fleet result
   words non-zero and host-verified, at the same task parity R1.3 used
   (y = x·(x+1), seeds 2/3/4/5).
2. **`BOX_ABI_v2` is not "frozen" until the conformance suite has a WGSL
   leg** that drives `run_wgsl` over the same 7 assertions. Until then, cite
   it as "frozen-against-oracle, WGSL leg pending". Do not delete the
   existing 7 legs; add, don't swap.
3. **R2.2 does not start** while (1) is open, unless the lane records in
   `PRODUCT_LANE_STATE.md` which specific R2.2 sub-steps are
   substrate-independent and can proceed — and name them, not "adjacent work".
4. **Do not** stub, fake, simulate, or relax the fleet probe to reach
   convergence (`PRODUCT_LANE_STATE.md`: "Never fake, stub, or simulate the
   missing capability to claim the rung"). A measured FAIL on R1.4 is a
   legitimate outcome and gets receipted like R1.3's RED legs.

## What this does NOT change

- **R1.3's PASS stands.** Jericho verified and confirmed: the gate arithmetic
  used the raw wall-clocks (0.86 ms vs ~1,108 ms => ~1,290x,
  `RECEIPT_R13_preference.md:20-24`), and the receipt itself already
  disclaimed the floor-linter margin as "a category artifact, NOT a floor
  claim. The gate-relevant numbers are the raw wall-clocks above" (:87-90).
  The "P1 thesis CONFIRMED" header line and its carried caveat are accurate
  as written.
- The LEG-line defect stays a receipt-hygiene fix: re-file the three R1.3
  legs against a boot-shaped path and let the validator compute `steps/s`
  rather than hand-typing it. Observed margin in the current floors file is
  1219.5x where the receipt says 1,216x — the floor moved between the two
  runs, which is its own argument for printing the floor inline.
- No HOLD is being asserted by this file, and no rate is adjudicated in it.
