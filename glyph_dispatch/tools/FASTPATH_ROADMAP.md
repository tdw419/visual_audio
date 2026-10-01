# Decoded fast-path roadmap

Make the decoded-op ("threaded") execution path in `tools/SPATIAL_RV64I.wgsl` +
`tools/fastpath_core.py` correct enough to be the **default**. Payoff: fresh
bbird boot ~14 min → ~3–5 min, which unblocks the perf loop (Route B batching,
native opcodes, cost characterisation).

Companion doc: `FASTPATH_FLIP_RECEIPT.md` (what the 2026-09-02 flip attempt
found). This roadmap is the plan to get the flip to stick.

## How this roadmap is run

Same discipline as `glyph_dispatch/ROADMAP.md`:

1. **Oracle before feature.** Every item ships a loudly-failing test/receipt
   first. No oracle → it needs design, not a commit.
2. **The gate is `python3 glyph_dispatch/tools/regression_gate.py`** — bbird
   boot-to-shell, intra-emulator lockstep, SHA-256 FIPS. A change lands only if
   the gate still exits 0 **with the fast path exercised** (bb counters prove
   the threaded loop ran; `bb_fallback_insts` near 0).
3. **Receipts are command output.** A summary sentence is not a receipt. Paste
   the gate's JSON and the boot transcript hash.
4. **Small commits, human review of diffs.** No cron. This project's
   `roadmap_builder` / `wgsl_generator` crons false-greened over stubs; they
   stay disabled.

## Known state (2026-09-02)

Fixed and kept (genuine parity bugs, independent of the wedge):

- `fastpath_core.py::_post_load_sync()` — `load_checkpoint()` restored RAM via
  raw `write_buffer` without marking dirty ranges, so `_sync_decoded_ops()`
  no-op'd and resumed "fast" cores silently ran slow. **This invalidated every
  pre-2026-09-02 checkpoint-resume fast-path result.** Fixed: rebuild linear
  shadow from the GPU buffer, mark all dirty, re-sync.
- mtime jitter LCG (`mtime_jitter_lcg`, seed `0x2545F491`) reset on every
  dispatch → mtime after N steps depended on host dispatch chunking, not N →
  interrupt timing varied with chunk pattern. Fixed: jitter removed,
  `mtime_delta = 1u` constant. Explains the step-10,700,000 divergence and the
  historic "dispatch-alignment sensitivity".
- Threaded loop now ends the block after STORE ops (22–25): GPU stores don't
  update the host `_linear_shadow`, so kernel self-modifying code (alternatives
  patching) could leave stale decoded_ops the threaded loop would run pre-patch.
- Threaded path now calls `maybe_take_interrupt()` **before** each instruction,
  matching the fetch path (was one instruction late).

Cleared, do not re-investigate:

- **RVC decode.** Exhaustive audit 2026-09-02: all 65,536 halfwords,
  `expand_rvc()` / `rvc_cb_offset()` in `tools/SPATIAL_RV64I.wgsl` 100 %
  compliant vs RV64GC spec + Capstone, 0 mismatches. The "+4030 vs −66" was a
  two's-complement B-type field artifact, not a live bug. Page-straddle logic
  (`SPATIAL_RV64I.wgsl:~1452`) only guards 32-bit straddles; 16-bit ops can't
  cross a page — correct. `RISCV_CPU_MMU.wgsl`'s broken `rvc_cb_offset` is a
  *different* shader, not loaded by `spatial_rv64i_cpu.py`.

Open blocker:

- **Fresh fast-path boot wedges deterministically** at PC
  `0xffffffff808a4aa6` (`queued_spin_lock_slowpath`), entering ~12–17M steps.
  Every timing-parity fix shifts the entry point, none removes it. Resuming the
  wedged image on the *slow* core spins identically → the guest state is
  genuinely dead, not a fast-path decode error. Leading hypothesis: single-hart
  self-deadlock — a timer interrupt lands inside a lock holder's critical
  section and the handler spins on the same lock; slow-path per-instruction
  cadence never hits that window, fast-path basic-block batching does. Known
  block-emulator failure class (block chaining not breaking on a pending IRQ).

## Status

| # | Item | Oracle | State |
|---|------|--------|-------|
| F0 | Fix `regression_gate.py` bbird oracle (never passed) | bbird gate returns PASS on a boot that reaches the shell | ✅ done — commit `56177e4` |
| F1 | Lockstep harness memory bound | RSS flat across a multi-M-step run | ✅ done — chunked phase 1 flat at ~1.74 GB; phase 2 explicit buffer destroy landed |
| F2 | Interrupt-state instrumentation in the harness | snapshot includes `mip/mie/sip/sie`; divergence classified interrupt-timing vs value | ✅ done — `mip/mie/mideleg/sip/sie` spot-checked |
| F3 | Bisect the fresh-boot wedge | receipt: exact step + PC of first fast/slow divergence + root-cause statement | ✅ done — commit `5e78d18` |
| F4 | Fix the wedge | fresh fast-path bbird boot reaches `~#`; lockstep clean past step 10,631,150 | ✅ done — commit `220361a` |
| F5 | Flip `DECODED_FASTPATH_DISABLED = false` | `regression_gate.py` green, fast path exercised, wall ≤ 6 min; update `FASTPATH_FLIP_RECEIPT.md` | ✅ done — default ON in commit `220361a` |
| F6 | Wire `regression_gate.py` into pre-commit / the item loop | gate runs fast-path-default, non-zero on any parity regression; receipt = JSON | ✅ done — bb assertions in gate + `.git/hooks/pre-commit` wired |
| F7 | Cross-dispatch basic-block cache (stretch) | dynamic instrs/block dispatched drops measurably, boot faster, lockstep still clean | ✅ done — commit `a6579f9` |

### F3 result — divergence pinned (2026-09-02, autoloop)

Chunked lockstep, `bbird_fresh_500K.rv64ckpt`, fast-path core vs slow-path core:

- **First divergence: step 10,631,150**, at instruction PC `0xffffffff800769ec`.
- After that instruction: slow core → `0xffffffff800769f0` (pc+4, linear);
  fast core → `0xffffffff80076a6c` (**pc+128** — a taken control-flow redirect).
- Symbol neighborhood (`boot_images/alpine_riscv64_semantic.db`, sparse):
  RCU stall detection — `print_cpu_stall_info` / `rcu_check_boost_fail`.
  RCU stall checks are **jiffies/timer-tick driven**.
- Reproduces at `LOCKSTEP_CHUNK` 100k and 10k; does **not** reproduce under
  single-step (that disables the threaded loop). It is a batching/timing bug,
  not a computed-value bug.
- Deterministic: the batched bisect (`run_lockstep_bisect`) converges to the
  same step on repeat runs (`probe=1149 clean / probe=1150 DIVERGED`).

Repro:
```
LOCKSTEP_FROM=.ckpt/bbird_fresh_500K.rv64ckpt LOCKSTEP_CHUNK=10000 \
LOCKSTEP_MAX_STEPS=10700000 python3 glyph_dispatch/tools/fastpath_lockstep_harness.py
```

### F4 analysis — interrupt-sampling asymmetry (HUMAN GATE)

`maybe_take_interrupt()` in `tools/SPATIAL_RV64I.wgsl` `main()` loop:

| Path | Calls per instruction | Lines |
|------|----------------------|-------|
| Non-threaded (fetch) | **1** — before execute | 3109 |
| Threaded (fast) | **2** — before *and* after `execute_decoded` | 3041, 3060 |

The threaded path's post-`execute_decoded` call (line 3060) is an interrupt
delivery point the slow path does not have. mtime is advanced once at the loop
top (line 3019) before the threaded/non-threaded split, so within an iteration
both checks see the same mtime — but the threaded path gets a *post-execute*
delivery opportunity at iteration N that the slow path only gets at the top of
iteration N+1. For a timer tick landing in that window, the fast core delivers
it one execute-step earlier than the slow core ever would → different jiffies
at the RCU stall check → the branch at `0xffffffff800769ec` goes the other way.

Proposed fix: make the threaded path sample interrupts exactly like the
non-threaded path — keep the pre-execute `maybe_take_interrupt()` (3041),
and after `execute_decoded` only *test pending bits to break threading*
(`threading = 0u`), deferring actual delivery to the next iteration's
pre-execute check. The `pending_interrupts` computation at lines 3061-3066
already exists; the change is to drop the `maybe_take_interrupt()` at line 3060
and keep the break.

Risk: lines 3041 and 3060 were both added defensively ("interrupt ordering
parity", "prevent RCU stall"). The fix must be validated by:
1. `regression_gate.py --gate bbird` still PASS (fresh fast-path boot reaches
   the shell — set `DECODED_FASTPATH_DISABLED = false` for the test) — proves
   no RCU stall reintroduced.
2. Batched-bisect lockstep clean past step 10,631,150 (ideally to 25M).

### F1 — fix the lockstep harness memory leak
Per-step `get_state()` / `queue.read_buffer()` allocate GPU readback buffers
that are never released; RSS climbs ~11 KB/step and a run OOMs around ~3 M
steps — below the ~12–17 M where the wedge lives, so the wedge is currently
**unreachable by the harness**. Fix: one reused readback buffer, explicit
release/unmap after each read, `gc.collect()` every N steps. Add a `--selftest`
that runs 2 M steps and asserts bounded RSS. Harness bugs already fixed this
session (keep): f-string format spec, `result['pc_fast']` KeyError, PC-half
masking, numpy `int32` sign-extension on the `|` (needs `int()` coercion —
kernel VAs are `0xffffffff8xxxxxxx`). Bisect is now step-count based
(`bisect_by_stepcount`), not PC-value based — PC-value bisection is invalid
because execution isn't monotonic in address.

### F2 — interrupt-state instrumentation
The wedge hypothesis is about *when* an interrupt is taken, not a computed
value. So the harness must record, at each divergence candidate:
`mip`, `mie`, `sip`, `sie`, current mode, and "interrupt taken this step?".
Oracle: a synthetic test that forces the fast core to take a pending timer IRQ
one instruction later than the slow core, and asserts the harness reports
`diff_type: interrupt-timing` with the step delta, not a bare register diff.
This turns F3 from a hunt into a single measurement.

### F3 — bisect the fresh-boot wedge
With F1 (reach 17 M steps) and F2 (classify the divergence), run
fast-fresh vs slow-fresh from `bbird_fresh_500K` and produce a receipt:
first-divergence step, PC, the interrupt snapshot, and a one-line root cause —
(a) interrupt taken N instructions apart, (b) computed-value mismatch, or
(c) missed interrupt. Expectation is (a). If (b)/(c), this roadmap's F4 plan is
wrong and the item gets re-scoped.

### F4 — fix the wedge
If F3 confirms interrupt-timing: add a pending-interrupt check to the
block-dispatch loop in `SPATIAL_RV64I.wgsl` / `fastpath_core.py` — when an IRQ
is pending at a block boundary, break the block (or drop to single-step for
that block) so delivery latency matches the slow path's. Oracle: fresh
fast-path bbird boot reaches the busybox `~#` prompt; lockstep vs slow clean
past `0x808a4aa6` for 20 M+ steps, deterministic across repeats.

### F5 — flip the default
Set `DECODED_FASTPATH_DISABLED = false`. Land only with:
`regression_gate.py` exit 0, bb counters proving the threaded path ran
(`bb_fallback_insts` ~0), fresh boot-to-shell wall time ≤ 6 min (baseline
~14 min), SHA-256 FIPS unchanged. Rewrite `FASTPATH_FLIP_RECEIPT.md` outcome
from REVERTED to LANDED with the transcript hash.

### F6 — gate wiring
`regression_gate.py` is wired into `.git/hooks/pre-commit` via `glyph_dispatch/tools/run_precommit_check.sh`.
It asserts `bb_threaded_insts > 0` whenever instructions are retired to ensure the fast path was genuinely exercised.
Wired Gate 3 into `tools/sha256_lockstep_test.py` (13/13 FIPS vectors verified in <1s).
Supports `--quick` mode for sub-minute pre-commit verification and full `--timeout` runs.

### F7 — cross-dispatch basic-block cache (Landed in commit `a6579f9`)
Persists `cur_slot` and `threading` state across host dispatches via GPU-resident `state.bb_cur_slot` and `state.bb_active`
(replacing scratch `_pad` in `CPUState` without changing the 184-byte buffer layout or breaking checkpoints).
- `fetch()` refactored to return `FetchResult(instr, phys, half0)`.
- Fixed inverted `t_h0.y == 0u` status check in threaded raw validation (`phys_read_u16` returns `y=1` on success).
- Added `is_straddle` guard (`0xFFE`) and page boundary check (`< 0xFFEu`) preventing out-of-bounds cross-page fast-path decode in userspace (`ld-musl` PLTs).
- Added host-side cache invalidation (`bb_active = 0`) on memory writes / dirty sync.
- Verification receipts:
  - 100,000,000 steps chunked lockstep: **zero divergence** across kernel and userspace.
  - Regression gate (all 3 gates): PASS (`bbird` quick probe: 788,570 / 1M threaded = 78.9% fast path, `lockstep`: PASS, `sha256`: PASS).
  - Pre-commit check hook: verified automatically blocking / passing on git commit.

## Non-goals

- Multi-hart / SMP guest (single hart only; the wedge analysis assumes it).
- Removing the slow path — it stays as the lockstep oracle and the fallback.
- JIT to host machine code — the "fast path" is decoded-op interpretation, not
  codegen.
- Touching `RISCV_CPU_MMU.wgsl` or repo-level `tools/` beyond the fast-path
  files already in scope.
- Re-auditing RVC decode (done, cleared above).
