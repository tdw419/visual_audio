# RULING — WF-1 (GPU tick semantics)

**Date:** 2026-09-12 · **Seat:** orchestrator (Jericho's standing "you lead")

## Context

WF-1 is the last open engineering gap. It appears in three places as an unverified
residual, not as a roadmap row:

- `systems/GLYPH_SELF_HOSTING_ROADMAP.md` NOT-verified list: "GPU tick parity (the WGSL engine has no tick delivery at all — no KTICK word)"
- `systems/RECEIPT_ARC_VERIFY_3e2bd8e.md`: "GPU tick parity is not testable"
- `systems/RECEIPT_DEFECT18_ENGINE_TICK_REGISTERS.md`: "there is no KTICK word and no timer countdown. So 'CPU ≡ GPU' [cannot be claimed] for tick semantics"

DEFECT-18 option (a) landed (`11fe1ac`): the CPU engine snapshots/restores the USER regfile on tick.
The claim that ticks are correct is therefore CPU-only, and nothing enforces that bound.

## Decision

**Option (ii) now, option (i) when a consumer exists.**

1. **Bound the claim now (land as a row).** Add a gate asserting the bound, not the capability:
   tick semantics are CPU-only today. The gate must fail if a parity claim is made for the GPU
   path while WGSL has no tick delivery. This is a real failure mode, not ceremony: the DEFECT-18
   receipt already had to add a caveat precisely because no such guard exists. Cheap — a static
   assertion over the engine sources plus one leg that asserts the CPU tick legs exist and pass.

2. **Do NOT build WGSL tick delivery now.** There is no consumer: no landed row needs GPU ticks,
   and the residency tier (the only tier that presumes preemption on the path where the substrate
   actually runs) is unbuilt. Building it now would be instrumentation with no verification value —
   the same criterion applied to (a) the local digest clause and (b) substrate witnesses.

3. **Pre-register the delivery row's acceptance criteria** so it becomes mechanical when a consumer
   appears (first residency-class task). Mirror DEFECT-18's definition of done on the GPU path:
   - a KTICK word exists and delivers a tick the engine acts on (not a baked constant);
   - a program holding live values across a tick gives byte-identical results with preemption on
     and off, measured on the GPU engine;
   - parity leg: the same program's tick-observable state matches the CPU reference engine;
   - the bound gate from (1) is deleted in the same commit that makes it false.

## Not claimed

- That GPU ticks are implementable cheaply — unmeasured.
- That CPU tick parity generalises to the GPU path — explicitly the thing bounded by (1).

## Consequence for the loop

WF-1 item (1) is promotable as a row when the roadmap has no other eligible item. Items (2)/(3)
stay parked until a residency-class task exists.
