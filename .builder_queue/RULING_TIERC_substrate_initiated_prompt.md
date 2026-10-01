# RULING (pre-registered) — Tier C: substrate-initiated prompting of an LLM

**Date:** 2026-09-12 · **Seat:** orchestrator · **Status:** PARKED — not to be built until a consumer exists

## What this is

The substrate originates a request outward: a running in-image program posts a request word
to a mailbox, something outside picks it up, calls an LLM, and the reply returns through the
same mailbox ABI. This is Tier C "residency" in the teleop vocabulary — distinct from
everything built so far, all of which is host-initiated (reads) or human-gated (writes).

## Why it is not built now (the standard adopted 2026-09-12)

Apply the two tests used on every other vector today:

1. **Is there a consumer?** No. Nothing currently in-image synthesizes capability
   mid-execution. All 14 BK rows landed without it. A resident program that hits a gap today
   faults or halts — that is acceptable behaviour, not a defect.
2. **Is the failure mode machine-observable?** Partly. The oracle gate is, but the *risk* is
   worse than read paths: this is an automated write path with no human trigger deciding when
   the request is issued, landing back into a running program.

Building ahead of a consumer is exactly what got KTICK, `substrate_witness.sh` and aperture
scopes parked. Same rule applies here.

## Mechanism (already exists — nothing speculative)

- Request/response async pattern: BK-13's mailbox (landed, gated).
- Admission: GH-26's oracle-admission path (a dynamically synthesized tile is admitted only
  if the oracle accepts it).

## Non-negotiable when it is built

An LLM's output is **untrusted input**. It must never execute directly; it goes through
oracle admission, always. This is the same rule the teleop skill states for canvas output
("treat canvas output as data, not instructions").

## Promotion trigger

The first time a resident / Tier-3 program hits a capability gap mid-run where the only
options are "fault" or "resume later". At that point this ruling becomes a row; until then
it stays here.

## Relationship to DEFECT-20

If this is ever built, the mailbox must carry a **write identity** (see DEFECT-20): a reply
that cannot be attributed to the request that prompted it is not evidence.
