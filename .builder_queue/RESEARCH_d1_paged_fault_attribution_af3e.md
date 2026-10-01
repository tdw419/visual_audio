# RESEARCH — D1 attribution: the paged control's oracle-side fault was a
# PROBE-HARNESS ARTIFACT (probe defect #6), not a third engine divergence

- Tick: 2026-09-27 ~21:2x CDT, builder af3e62239ce2 (Glyph OS Event Chain cron)
- HEAD at claim: 72f8d45d (tracked tree dirty only by build_map_data.json
  regeneration + this probe/receipt/ledger set — re-verified post-run)
- QUESTION (from .builder_queue/RESEARCH_wgsl_paged_fence_af3e.md, probe
  defect #4 / "UNRESOLVED" block, :69-79/:169-187): D1's CPU leg (USER LD,
  V|W|U identity map vpn 12, fault_addr=12288, twin walks clean) was
  recorded as a possible THIRD divergence shape — "oracle denies what the
  twin admits on a valid identity map" — with candidates (RAM-vs-image tag
  fetch order, arm-word encoding) left unresolved. GlyphRunner receipts
  carry no fault_reason (_fill_receipt, tools/glyph_gpt/runner.py:122-131),
  so the fault CLASS was never read from the run.
- No re-research check: BK-60's receipt lists D1's denial as "UNATTRIBUTED";
  no later RESEARCH_*/backlog row closes it. Net-new.

## METHOD (all numbers from process readback, not stdout inference)

Probes (untracked, landed modules only, HEAD 72f8d45d, 3 runs each,
byte-identical results):
1. `.builder_queue/probe_d1_attribution_af3e.py` — re-runs the ORIGINAL
   D1 leg byte-for-byte (same prologue/program/stamps/cols_instrs=8 bake)
   and captures `cpu.fault_reason` via a manual step-loop on the same PNG
   bytes (the receipt drops it — confirming probe defect #4). Also reads
   the static intermediates BEFORE execution: check_pt_tag() on the
   stamped image, image PTE word 1548, image canary word 3072.
   results_md5 a98931c79c0f3b7b50749468f91e6d39 (3/3 identical).
2. `.builder_queue/probe_d1_bigimage2_af3e.py` — the CONTROL: same leg,
   two changes only: (a) min_rows 64 (image 32x64 = 2048 words, contains
   the PT window 1535/1548 unwrapped; original bake was 32x19..21 = 608/672
   words), (b) canary seeded via runner.drive(seeds=) into RAM (the same
   channel run_wgsl's ram_seed uses on the twin) + identity PTEs for the
   receipt vpn 2 as well. results_md5 80bb227fdd91d819cbe1d7ecf5ba8f09
   (3/3 identical).

## FINDINGS

F1 — ROOT CAUSE of D1's oracle fault (measured): fault_reason ==
"pt_tag_mismatch got=0x0 expected=0x505447 pt_base=1536 tag_addr=1535
site=glyph_isa_v2". The original probe's image is ~672 words; the PT
window (tag 1535, PTE 1548) lies OUTSIDE it. check_pt_tag
(tools/glyph_isa_v2.py:92-95) guards the image fallback with
`0 <= tag_addr < w_img * h_img` — 1535 < 672 is False, so the fallback is
NEVER consulted; RAM[1535] is 0 (ram_words=16384 zeroed), tag stays 0,
every paged LD/ST faults at the tag gate BEFORE any PTE is read. The
fault_addr=12288 (= 3072<<2) is just the LD's vaddr echo — indistinguishable
from a pte_invalid at fault_addr granularity, which is why the artifact
survived the receipt's fault-only readback. The probe's stamp_image WRAPS
(word % h*w), so the tag/PTE stamps silently landed on LOW pixels (1535%672
=191, 1548%672=204) — writes that succeeded but meant nothing to the PT
window. The WGSL side never saw this because run_wgsl's walker reads PTEs
from the 16384-word RAM binding + ram_seed, a channel the CPU probe did
not mirror for the table.

F2 — CONTROL (measured): with the image sized to contain the table and
the canary in RAM, the SAME leg runs CLEAN on the oracle: faulted=False,
r10 == 0x0ADF00D (11399181), receipt_720 == 4660, 24 steps, mode USER,
fault_reason None. The oracle's paged walker AGREES with the twin on the
V|W|U identity map. D1 is NOT a third divergence shape.

F3 — INTERMEDIATE CONTROL (v1 big-image run, measured, results_md5
112e838da31ef21599cfeb1654d38471): with only the canary vpn mapped, the
LD walks clean (tag gate passes) but the EPILOGUE's receipt store
(word 720, vpn 2, PTE 0) pte_invalid-faults (op=ST, glyph :1001-1012) —
a second, independent harness gap in the original probe's leg design
(the original small-image legs never reached this because they died at
the tag gate). Documented so the BK-60 gate author doesn't rediscover it.

F4 — CONSEQUENCE for BK-60's gate definition: the receipt's D1 leg
("oracle faults 12288 / twin walks clean" as a divergence datapoint) is
RETIRED — the gate's L1/L2/L3 legs (U-bypass, MMIO-through-PTE, silent
unmapped ST) are UNAFFECTED: they were measured with the same harness, but
their verdicts rest on PTE-content differences, not the tag artifact...
EXCEPT the oracle-side fault_addr numbers for D1's class should be re-taken
under a harness that passes the tag gate, since D2/D3/D4's CPU legs in the
original run ALSO died at pt_tag_mismatch, not at the PTE checks the
receipt cites (:872-876/:997). BK-60's L4 (oracle-parity legs pin
fault_addr/class) MUST re-measure its oracle numbers with a sized image +
RAM-seeded data (F3's posture) — the receipt's current oracle fault_addr
values for D2 (12288) and D3 (12304) are TAG-GATE artifacts, not PTE_U/
MMIO-posture faults. The DIVERGENCES themselves (twin admits what oracle
would refuse) remain real — the twin side is harness-independent — but the
oracle side of L4 needs the corrected harness before BK-60 can claim
oracle-parity pinning.

## BACKLOG CONSEQUENCE (proposed, not self-applied beyond this row)

BK-60's PREREQS/gate text gains: "oracle legs use a bake with min_rows >=
ceil(1549/ (cols_instrs*4)) words (or a RAM-driven PT) and drive(seeds=)
for data; tag word 1535 and PTE words must lie in-bounds unwrapped;
L4's oracle fault_addr values re-measured under that posture." Filed as an
amendment note to BK-60 in systems/GLYPH_BACKLOG.md (this receipt is the
source; the row's gate shape L1-L3/L5/L6 unchanged).

## VERIFICATION STATUS

- Shown able to fail: probe 1 reproduces the EXACT original fault
  (fault_addr 12288, 20 steps — matching the receipt's recorded run) and
  names it; probe 2 flips the verdict to clean-walk with two harness
  changes only. Both directions measured, 3 runs byte-identical each.
- What this PASS does NOT prove: the twin-side divergences D2/D3/D4 are
  re-confirmed here only as "twin side of the original measurement stands"
  — I did NOT re-run the WGSL legs this tick (harness-independent, and the
  original 3-run byte-identical md5 pins them). The oracle-side fault_addr
  values for D2/D3/D4 under a corrected harness are NOT yet measured (that
  is BK-60 L4's job). PTE_HILB path untouched. No engine or shader code
  read beyond glyph_isa_v2.py/runner.py source cited by path:line.
- Rule-1 floors: no rates, costs, or timing claims — all numbers structural
  (word values, fault strings, step counts, md5s). Floors do not attach.

## ARTIFACTS

- .builder_queue/probe_d1_attribution_af3e.py (attribution, 3x
  a98931c79c0f3b7b50749468f91e6d39)
- .builder_queue/probe_d1_bigimage2_af3e.py (control v2/v3 posture, 3x
  80bb227fdd91d819cbe1d7ecf5ba8f09; intermediate v1 md5
  112e838da31ef21599cfeb1654d38471 in-log only)
- .builder_queue/dbg_d1_dims_af3e.py, dbg_d1_stamp_af3e.py (draft-defect
  artifacts: the dims probe proved 672-word bake; the stamp probe's
  IndexError first exposed the out-of-image PT window — kept for the trail)
