# RESEARCH: the WGSL twin's PAGED walker — first on-device measurement of
# the branch every prior probe scoped out (BK-60)

Builder: af3e (cron af3e62239ce2) · 2026-09-27 ~20:3x CDT · HEAD at claim
b9c6d8f4 · tracked tree clean at claim apart from this probe/receipt/ledger
append · probe `.builder_queue/probe_wgsl_paged_fence_af3e.py` · 3 runs
byte-identical, stdout md5 `053e8591bf6a9476a4fe2526800cbda1` (runs 5/6/7 of
the session; earlier runs 1-4 were probe-defect iterations, disclosed below).

## Question (rule-5 checked)

The WGSL twin's `walk_ld`/`walk_st` have a PAGED branch (pt_base != 0, the
GH-25 walker). Every prior WGSL probe ran UNPAGED: RESEARCH_ek1_vector_
hijack_wgsl_af3e.md:112-113 ("the paged branch of walk_st (:412-441) was not
probed ... Its unmapped-store `return false` is a disclosed divergent shape,
not re-measured"); RESEARCH_bk51_twin_tile_ld_af3e.md:104-105 (tile probes
"unpaged posture"). Prior-art grep found no RESEARCH_*/backlog row covering
the paged branch (BK-48/49/50/51/55/56/57 are all LD/ST/PUSH/MMIO/tile on
the unpaged path). Meanwhile BK-59 (2dbe69da) hard-gates Stage 3+ desktop
work on the BK-38..57 fence commit landing clean on BOTH engines, and GH-25
swap/fault legs already run paged workloads on the twin — the unprobed branch
is load-bearing, and a fence hole on the paged path would invalidate the
sequenced commit's "clean on both engines" premise.

Sub-questions:
1. Does the twin's paged LD check PTE_U/PTE_W like the oracle (S1)?
2. Does the paged path respect the box/tile fence and the BK-56 MMIO read
   posture — or is translation a fence bypass (S2)?
3. What does the twin's paged ST do on an unmapped VA — the disclosed silent
   `return false` (S3) — vs the oracle's pte_invalid E-K1 fault?

## Method

- Harness: the GH-25 gate's own image-stamping discipline
  (tests/test_gh25_hilbert_paging.py:229-247 `_write_pte`/`_arm_pt`): PT
  arm word 8211, tag 0x505447 at word 1535, PTE at 1548 — stamped into the
  IMAGE pixels post-bake so BOTH engines see the armed walker (the CPU's
  RAM-first PTE fetch finds memory[1548]==0 and falls back to the image
  PTE, the designed GH-25 path; the twin does the identical RAM-then-image
  fallback, wgsl_glyph_isa_v2.py:375-377/:414-416).
- USER mode: the kernel's own MODE_LATCH (8192) + KJMP prologue — CPU
  one-shot glyph_isa_v2.py:1270-1274, twin KJMP arm wgsl:618-633. TWO-PASS
  bake (gh25_hilbert_paging.py:268-284 shape) with the placeholder 'LDI r30
  0' present in BOTH passes (identical instruction counts; inserting the
  LDI between passes shifts :__task and mis-targets the jump — probe
  defect #2 below).
- Both engines run the IDENTICAL baked image: GlyphRunner.run() (CPU,
  ram_words=16384 → _iso_enabled live) and .run_wgsl() (RTX 5090, wgpu
  0.32.0), the latter with ram_seed for the canary word (twin RAM plane;
  the CPU gets the same value via a bake-time data_word at word 3072 —
  non-reserved, allowed by _BAKER_RESERVED_RANGES).
- Box armed in-program (ST to words 8195/8196 = [1200,1300) bytes) BEFORE
  the latch, the GH-20/GH-23 pre-arming discipline.
- Verdicts from receipt readback BYTES (memory[]/ram[]/registers_full/
  fault_addr), never stdout. 3 runs byte-identical.

## Findings

### S1 (source read) — confirmed by source, now measured on-device
Twin walk_ld paged branch: PTE_V refs=1, PTE_U refs=0, PTE_W refs=0.
PTE_U is DEFINED (wgsl:172) and never consulted anywhere in the walker.
Oracle: paged USER LD checks PTE_U (glyph_isa_v2.py:872-876), paged ST
checks PTE_W + PTE_U (:997), faulting pte_invalid through E-K1.

### D1 (paged control, translation sanity) — twin walks, oracle faults
vpn 12 identity map (PTE V|W|U pfn 12), USER LD of vaddr 3072 (canary
0x0ADF00D seeded at ram[3072]):
- WGSL: r10 == 11399181 (0x0ADF00D), halted clean, 24 steps. Walker works.
- CPU: faulted=True, fault_addr=12288 (3072×4), 20 steps.
- INTERPRETATION: the CPU faulted on the LD — see "Honesty" below for why
  D1's CPU leg is NOT a clean translation control (suspected PTE_W-missing
  on an LD? No — LD checks V and U only; suspected cause: the CPU's image
  PTE fetch reads the PTE stamped at word 1548, but with ram_words=16384
  the tag fetch at 1535 ALSO hits RAM-first, finds 0, falls back to image
  — both should match. The likely actual cause is documented as UNRESOLVED,
  probe defect #4: the CPU fault_reason was not captured by GlyphRunner
  receipts, so pte_invalid vs something else is not distinguishable from
  this probe's outputs. The twin's legs stand on their own; the CPU side
  of D1 is recorded, not attributed.)

### D2 (PTE_U bypass) — MEASURED ENGINE DIVERGENCE
Same table, PTE = V|W (U CLEAR):
- WGSL: r10 == 0x0ADF00D — the USER read of a U-clear page SUCCEEDS
  on-device, no fault channel exists (halted clean).
- CPU: faulted=True, fault_addr=12288 — the oracle refuses the same read
  (glyph_isa_v2.py:872-876: USER + !PTE_U → pte_invalid E-K1).
- VERDICT: the twin admits a USER read the oracle faults. Same CLASS as
  BK-51/BK-57 (engine divergence on the read side) but on the PAGED path:
  the sequenced fence commit's twin side gains a FOURTH line item (paged
  PTE_U check) alongside walk_st tile term / walk_ld tile consult /
  TILE-word write posture.

### D3 (MMIO read THROUGH the paged path) — BK-56's posture has a paged hole
Plain (non-HILB) PTE V|W|U pfn 32 offset 4 → physical word 8196 = BOX0_HI
(config block), box [1200,1300) armed, USER LD of vaddr 3076:
- WGSL: r10 == 1300 — the config value arrives in USER mode with zero
  consults (the paged branch checks no fence: 0 tile refs, 0 addr_in_box
  refs in walk_ld's paged branch). RULING_BK38_READ_POSTURE's F1
  falsifier ("box-confined USER LD of word 8196 must fault or read 0 on
  BOTH engines") is violated on the twin's paged path: the unpaged branch
  returns 0 (BK-56 landed), but translation routes AROUND the posture.
- CPU: faulted=True, fault_addr=12304 (3076×4) — the oracle refuses
  (pte_invalid or the U check; fault_reason not captured, see Honesty).
- VERDICT: BK-56's read posture is incomplete on the twin — it guards the
  unpaged box_mmio branch (:361-363) only. The sequenced commit needs a
  paged-path MMIO guard or an explicit posture ruling covering translation.

### D4 (unmapped paged ST) — the disclosed silent shape, measured
vpn 12 unmapped (PTE 0), USER ST canary → vaddr 3072:
- WGSL: halted "clean" (halted=true, no fault field in the receipt —
  walk_st's paged branch returns false with no fault record; mode stays
  USER via the receipt's halted-only view), value nowhere (ram[3072]==0).
  25 steps.
- CPU: faulted=True, fault_addr=12288, mode drops to SUPER, KFAULT_PC=0 →
  clean halt at 21 steps.
- VERDICT: the disclosed shape (RESEARCH_ek1_vector_hijack_wgsl_af3e.md:
  112-113) is confirmed on-device: the twin drops an unmapped paged store
  SILENTLY while the oracle records a fault and vectors E-K1. A kernel
  that relies on the fault record (xv6-nano's reaper reads FAULT_ADDR)
  sees different machine state on each engine after the same program.

### C1 (unpaged E-K1 control) — harness live
PT NOT armed, USER ST to word 100 (outside the box):
- WGSL: halted at 18 steps, ram[100]==0 — E-K1 refused (the twin's
  unpaged consult works; fault recorded in box_mmio, not surfaced in
  GlyphRunner's receipt).
- CPU: faulted=True, fault_addr=400 (100×4) — the canonical E-K1 record.
- The delta between C1 and D4 isolates the armed walker as the cause.

### C2 (SUPER paged control) — walker sane for the kernel
D3's table, SUPER-mode LD of vaddr 3076:
- BOTH engines: halted clean, 7 steps. WGSL r10==0 and CPU r10==0 — wait:
  CPU r10==0 and WGSL r10==0. The word read is ram[8196] on the twin
  (seeded 1300 via ram_seed) and memory[8196] on the CPU... BOTH read 0.
  INTERPRETATION (probe defect #5): C2's CPU leg ran without the walker
  armed via the KJMP-free prologue — but the tag/arm stamps WERE applied;
  r10==0 on both engines means the translation resolved to an UNSEEDED
  word (twin: ram[8196] was seeded... unless run_wgsl's ram_seed map used
  a different key). C2 is recorded as NON-DISCRIMINATING for posture and
  is excluded from the verdict set; D3's twin leg (r10==1300 with the
  identical PTE, USER mode) already demonstrates the translation itself
  works — C2 adds nothing and its 0s are unexplained. NOT a verdict leg.

## Consequence for the BK-38..57 sequenced fence commit

The twin side of the sequenced commit grows to FOUR line items (was three
after BK-57):
1. walk_st tile term (BK-51, deny-lawful D3)
2. walk_ld tile consult (BK-57, admit-unlawful L1)
3. TILE-word write posture (BK-50 door clears TILE_H — guest-defeats any
   new predicate)
4. NEW (this receipt): paged-path posture — walk_ld paged branch needs
   PTE_U (oracle parity, kills D2) AND either a fence/MMIO consult or an
   explicit posture ruling covering translation (kills D3); walk_st paged
   branch needs a fault-or-drop posture decision (D4's silent drop vs the
   oracle's recorded E-K1 — a state-visibility divergence for any kernel
   that reads FAULT_ADDR).

BK-60 filed to systems/GLYPH_BACKLOG.md with the D2/D3/D4 gate shape.

## Rule-1 floors

All cited numbers are STRUCTURAL (register values, byte/word addresses,
step counts, fault addresses, md5s, line numbers) — no rate, ratio,
latency, or cost is asserted; floors do not attach.

## Honesty — what this PASS does NOT prove

- D1's CPU leg is unattributed (fault_reason not in GlyphRunner receipts);
  the probe should have printed cpu.fault_reason directly. D2/D3/D4's CPU
  legs share that gap for the same reason — the oracle-side FAULT CLASS is
  inferred from glyph_isa_v2.py's source (:872-876/:997), not read from
  the run. The WGSL side (the load-bearing half: the twin's posture) is
  fully measured from readback bytes.
- The paged TILE composition (tile-armed + paged on the twin) is NOT
  probed: the twin has no tile predicate at all (BK-51), so paged×tile
  collapses to the paged row until BK-51 lands.
- GH-25 swap-path (PTE_HILB) frames were not exercised — D3 used a plain
  PTE. The Hilbert frame path's fence posture is unprobed (same consult
  absence by source read, not re-measured).
- C2 is non-discriminating (probe defect #5) and excluded from evidence.
- Non-blocking smoke: legs need a live GPU; on a GPU-less runner the WGSL
  side fails at device acquisition.
- The CPU's D1 fault (while the twin walks) is itself a THIRD divergence
  shape (oracle denies what the twin admits on a V|W|U identity map) —
  recorded, not root-caused; candidates are the tag's RAM-vs-image fetch
  order or the arm word's image-pixel encoding, both UNRESOLVED here.

## Probe defects (disclosed)

1. v1/v2 drafts assumed GlyphRunner could seed-then-rerun (runner re-creates
   the CPU and device buffers per call — impossible); v3 moved all state
   into program text + image stamps + one run per engine.
2. v2 two-pass bake computed :__task coords on pre-insertion text and
   inserted the LDI between passes — :__task shifted by one, KJMP landed on
   the MODE_LATCH store, 14→15→16→14 infinite loop (found via step trace,
   dbg artifact /tmp/dbg_c1d.py shape). v3 carries the placeholder in both
   passes (the gh25 discipline — identical instruction counts).
3. v3 first run left :__task out of the task bodies entirely (KeyError).
4. CPU fault_reason not captured (GlyphRunner._fill_receipt records
   faulted/fault_addr but not fault_reason) — oracle-side fault CLASSES
   are source-read inference, labeled above.
5. C2 returned 0 on both engines where 1300 was expected on the twin;
   unexplained, leg excluded from the verdict set rather than rationalized.
