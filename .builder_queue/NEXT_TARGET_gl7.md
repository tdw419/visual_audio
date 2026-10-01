# NEXT TARGET — GL-7 (ruled), with the binding gate condition (2026-09-12, cron af3e62239ce2)

**Status:** OPEN · **Seat:** builder orchestrator · **Ruled order:** `.builder_queue/RULING_next_lane_OSS_GL6_GL7.md`
(`8c56f43`) — primary supply **GL-6 then GL-7**; GL-6 landed loop-side (`ca201e0`, artifact `b5aa3f2` in the
OSS repo). GL-7 is next.

## GL-7's row, verbatim

> GL-7 | One benchmark, honestly reported, with caveats: cold-boot-to-first-instruction from a `.glyph.png`
> vs. a comparable baseline (WASM or a microVM) | A written benchmark doc with methodology, raw numbers,
> and an explicit "what this does not show" section — same honesty standard as S3_RECEIPT.md | QUEUED

## The artifact-form question — settled by measurement, not preference

The ruling's condition (1) is that **every artifact must be reproducible from the repo alone under the row's
own gate**; condition (2) keeps publishing with Jericho. Measured on this host (2026-09-12, before delegating):

| Probe | Result |
|---|---|
| `node` | **v24.13.0 present** — a 37-byte wasm module emitted from the stdlib compiles, instantiates, and `main()` returns `42` |
| `qemu-system-x86_64` | **present** — a 512-byte boot sector emitted from the stdlib prints `Booting from Hard Disk..AB` on COM1 |
| `wasmtime` / `wasmer` / `firecracker` / `hyperfine` | **ABSENT** (so: no wasmtime-based runner, no real microVM, no timing tool — the harness does its own timing) |
| `gcc`/`as` | present, **but not needed**: both baseline artifacts are emitted as bytes from Python stdlib code, so the gate needs no assembler and no npm |

So the deliverable measures **all three legs** (the row says "WASM **or** a microVM"; both are measurable here)
and reports them with the honesty section the row demands. The qemu leg is **not** a microVM — it is a full
VM including SeaBIOS — and the doc must say so and must not let that comparison flatter the result silently.

## BINDING GATE CONDITION (the seat's condition — a green gate is not evidence until it can fail)

The row's gate clause ("a written benchmark doc with methodology, raw numbers, and an explicit caveat
section") is **VACUOUS as stated**: a doc with typed-in numbers and a hand-written caveat list passes it.
That is exactly the fabrication failure mode hunted all day (cf. GL-6's binding condition at `f6b7d19`).
`tests/test_gl7_benchmark.py` MUST have all four legs:

1. **MEASUREMENT, not authorship** — the gate re-runs the *committed harness* itself and requires every
   leg to be either `status: measured` with positive finite numbers and its phase fields present, or
   explicitly `status: skipped` with a *named reason* (runtime absent). A number that did not come from a
   run in this process tree is a failure, not a pass.
2. **REGENERATION TOLERANCE** — the committed `docs/bench/cold_boot.json` must agree with a fresh
   re-measurement within a **factor of 3** on each headline number. Timing is noisy, so exact equality is
   the wrong assertion; a fabricated number (e.g. `0.0001 ms`) is outside any such band and fails.
3. **NEGATIVE LEG + BASELINE LIVENESS** — (a) perturbing one committed headline number beyond the
   tolerance MUST report RED **through the same checker the real assertions use** (a comparison that cannot
   fail is not a comparison); (b) the WASM baseline must be *executing*, not a print: the runner's returned
   value must equal the constant the module's own code computes (`42`), and the same emitter with a
   different constant must return that different value.
4. **DOC-CONSISTENCY + HONESTY** — the doc's number table must be recomputed from the committed JSON (the
   doc cannot drift from the data it cites; mutating a number in the doc must report RED), and the doc must
   carry a "what this does not show" section with the required caveats: page cache not dropped (no root),
   the qemu leg is a full VM not a microVM, pipe/marker latency is inside every number, single host/single
   run class, and interpreter/runtime startup dominates the headline.

Delegating GL-7 before these legs exist is out of bounds. The choice of baseline runtime was the loop's;
the falsifiability condition is not.

## What is deliberately NOT in scope

- Publishing, hosting, README claims, or the OSS roadmap's done-state (Jericho's, per condition (2)).
- Any number the harness cannot regenerate on the current tree.
- Widening the engine, the ABI, or the CLI to make the numbers nicer. If a number is unflattering, it is
  reported as measured with its caveat.
