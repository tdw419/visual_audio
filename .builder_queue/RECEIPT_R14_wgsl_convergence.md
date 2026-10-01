# RECEIPT — R1.4 WGSL Fleet Convergence (GATE)

**Rung:** R1.4 per RULING_wgsl_convergence_gates_r22.md (Jericho, 2026-09-21 ~15:0x CDT)
**Session:** builder cron af3e62239ce2, 2026-09-21 ~16:0x–16:4x CDT
**Base:** be44539a (BM801 receipt; separate lane)

## Definition of done (from the ruling)

> probe_r13_wgsl_fleet.py runs the 4-tenant fleet to completion ON THE
> SHADER PATH (GlyphRunner.run_wgsl), fleet result words non-zero and
> host-verified, same task parity as R1.3 (y=x·(x+1), seeds 2/3/4/5).

**VERDICT: PASS (converged).** Green exit 0 with results {714:6, 728:12,
748:20, 763:30} = RES_FLEET_EXPECT exactly (y=x·(x+1) for seeds
2/3/4/5), fleet receipt 0x5EED0005 @765, done bits 0b1011 @717, E-K1
fault receipt 0xFA026 @731, halt at step 458 — all host-verified from
receipt["ram"] after run_wgsl().

## Provenance disclosure (honesty first)

The core shader diff (RAM-first LD/ST, E-K1 vectoring, GH-16 tick
delivery, DEFECT-18 restore) was found **uncommitted on the tree** this
tick (179 insertions in tools/wgsl_glyph_isa_v2.py, last mtime 15:46,
~18 min quiet; comments self-identify as R1.4 work). This lane adopted
it per the R1.2 precedent ("found the fleet work in flight... debugged
instead of restarting") instead of restarting. This session then:
verified the RED leg on HEAD, added the four missing paged-path parity
fixes (below), landed the ruling's item-3 WGSL ABI leg, executed the
WF-1 pre-registered deletion, gave the probe its exit contract, and
wrote this receipt. No provenance is claimed over the adopted diff.

## RED leg (gate shown able to fail) — rule 4

Pre-fix shader (HEAD state of tools/wgsl_glyph_isa_v2.py, diff stashed):

```
halted=True steps=153 err=None
ram[765]=0x00000000 (expect 0x5eed0005) ram[717]=0b0 ram[731]=0x0
results: {714: 0, 728: 0, 748: 0, 763: 0}
WGSL FLEET: DIVERGENT
RED_EXIT=1
```

(exactly the known starting state from the ruling: halts @153, words 0)

## GREEN leg

```
halted=True steps=458 err=None
ram[765]=0x5eed0005 (expect 0x5eed0005) ram[717]=0b1011 ram[731]=0xfa026
results: {714: 6, 728: 12, 748: 20, 763: 30}
WGSL FLEET: MATCH
GREEN_EXIT=0
```

## What this session fixed beyond the adopted diff

Bisected 5 regressions the adopted diff caused in landed parity gates
(variants tested: JMPR scaling revert — not the cause; PTE-fetch-only
revert — partial; E-K1 disable — no; unpaged-LD revert — no). Root
cause of the residue: the adopted diff moved stores to RAM but left the
paged path reading tag/PTE/frames from image pixels. Fixes (all bitwise
mirrors of the oracle):

1. walk_ld/walk_st page-table TAG check: RAM-first with image fallback
   — twin of check_pt_tag (glyph_isa_v2.py:88-95).
2. walk_ld plain (non-HILB/PIX) frame reads: RAM with ENG-3 wrap —
   twin of glyph_isa_v2.py:920-922.
3. walk_st PTE_PIX routing + plain-frame RAM writes — twin of
   glyph_isa_v2.py:1009-1049.
4. Two stale test channels updated to the converged world (both engines
   now write RAM; the pixel-view premise was R1.4's own target):
   - test_bk1_argv.py leg 4: WGSL argv seed moved from image-pixel
     writes to run_wgsl(ram_seed=...) — the same channel as the CPU
     leg's _seed_argv(cpu.memory,...); parity words compared in the RAM
     view, both sides masked to 24-bit container width.
   - test_bk2_wgsl_syscall_parity.py: UART/exit/status words compared
     in the RAM view (both masked 24-bit), docstring premise updated.
5. tests/test_wgsl_triple_sync.py: re-synced both glyph_dispatch copies
   (`cp tools/wgsl_glyph_isa_v2.py ...`) exactly as that gate instructs.

## Ruling item 3 — BOX_ABI_v2 WGSL leg (ADD, don't swap)

tests/test_box_abi_conformance.py grew legs 8–11 driving run_wgsl over
the frozen contracts (legs 1–7 untouched):

- Leg 8: ABI word 952 == 0x00020026 + status 950 == 0xCAFE0026 at
  shader-path halt.
- Leg 9: full frozen memory-map at shader-path fleet halt (results,
  done 0b1011, 0xFA026, 0x5EED0005, ticks>0, argv 0x3B00112A intact).
- Leg 10 (WF-1 delivery criterion): preemption ON (quantum 6) vs OFF
  (quantum 0) byte-identical frozen words on the GPU engine; measured
  458 vs 378 steps, identical results/receipts/tick counters.
- Leg 11 (RED, non-vacuity): corrupting expectation 714→999 fails the
  same assertion set against the same shader-run RAM. Additionally, the
  whole leg-9 set was shown RED against the pre-fix shader (bisect
  probe: "FAIL -> gate discriminates").
- wgpu device absence skips (not fails); a GPU-path failure is a
  failure.

Suite: **11 passed** (was 7).

## WF-1 bound gate deletion (pre-registered, not guard-weakening)

RULING_WF1_gpu_tick_semantics.md option (ii) pre-registered: the bound
gate "is deleted in the same commit that implements WGSL tick delivery
(making L1 false)". Delivery happened this commit (GH-16 tick delivery
in the shader, MMIO-armed KTICK, DEFECT-18 restore) and the delivery
criteria are now gated where they belong: conformance leg 10 (on/off
equivalence on the GPU engine) + leg 9 (frozen words) + the fleet probe
exit contract. L1 was observed RED on the real diff before deletion
(the guard worked; its hits list is in the session log). L2/L3/L4
passed at deletion time. tests/test_wf1_tick_claim_bound.py deleted.

## Probe exit contract

.builder_queue/probe_r13_wgsl_fleet.py: was print-only (always exit 0).
Now exit 0 = MATCH (receipt + done bits + full result-word equality),
exit 1 = DIVERGENT or no-RAM. RED on pre-fix shader exit 1 shown above.

## Gates run (this session, this tree)

- probe GREEN exit 0 / RED exit 1 (both tails above)
- test_box_abi_conformance.py: 11 passed
- Lane + WGSL-family regression (18 files, incl. fleet/arrive/queue/
  resident, gh17/gh25 paging, bk1/bk2 parity, se022a/se024/gh4/eng1,
  triple-sync, pillar21/23): **114 passed, 0 failed**, exit 0
  (/tmp/r14_regression.txt tail; full exit code captured)
- Known NOT-green, NOT-mine, pre-existing at HEAD: 8 failures in
  tests/test_defect_d_ram_scoped_handlers.py (scipy missing in env;
  verified failing identically with the diff stashed). Unrelated to
  this rung; left untouched.

## What the PASS does NOT prove

- CPU-oracle and WGSL are instruction-by-instruction identical — not
  proven; the proof is over the frozen ABI words + registers on THIS
  fleet image family (plus the standing se024/gh4/bk1/bk2 parity
  suites). Other image families may still diverge; triple-sync + the
  parity suites are the ongoing net.
- The OOB ST delta remains (documented in the shader): the CPU faults
  on out-of-RAM stores (lever #2), the shader drops them — fault
  vectoring for that one path is CPU-only. Not exercised by this gate.
- The 2D tile predicate (GO-2) is NOT mirrored in the shader (no
  fleet/kernel image arms a tile; an unset tile is inert on the oracle).
  A tile-armed image would be untested on the shader path.
- No rate/performance claim of any kind is made → floors/check_regime
  N/A with that reason (FLOORS AUTHORITY: no number quoted).
- WF-1's "byte-identical with preemption on and off" is proven over the
  fleet's tick-observable frozen words, not over full 16384-word RAM
  equality (steps legitimately differ: 458 vs 378).

## Scope

Changed: tools/wgsl_glyph_isa_v2.py (+ adopted-diff + paged fixes),
glyph_dispatch copies ×2 (triple-sync), tests/test_box_abi_conformance.py
(+4 legs), tests/test_bk1_argv.py (leg-4 channel), tests/test_bk2_wgsl_
syscall_parity.py (channel + docstring), tests/test_wf1_tick_claim_
bound.py (DELETED, pre-registered), .builder_queue/probe_r13_wgsl_fleet.py
(exit contract), PRODUCT_LANE_STATE.md (ledger), this receipt.
Not touched: .hermes_guest_context/guest_state.json (daemon-owned,
left dirty), protected assets, engine baker/agent_resident (zero lines).
