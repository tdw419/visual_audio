# RESEARCH — the item-29 REAPER TRAMPOLINE is paged-rewriteable: a tile-
# confined task rewrites the containment mechanism's own catcher THROUGH
# TRANSLATION (BK-66 class, lawful until the fault), then DELIVERS code
# execution at the trampoline via a paged fault it also controls

- Tick: 2026-09-28 ~00:0x CDT, builder af3e62239ce2 (Glyph OS Event Chain cron)
- HEAD at claim: fbdef1be (re-verified via git rev-parse; monitor
  fingerprint head matched — the diff vs the prior tick's 7f572095 is my
  own tick-11 landing). Mailbox re-verified: newest RULING_*.md mtime
  1790550013 < HEAD commit time — no binding new work. QUEUE_STATE.json:
  0 non-landed tickets (all items landed, all three remedy-* landed);
  CLAIM QUEUE empty → Phase 1c eligible.
- QUESTION (composed from two landed measurements, never composed before):
  BK-66 measured that arming GH-17 paging DISARMS the tile fence (paged
  branch is the first arm in LD/ST). BK-53 measured the E-K1 trap VECTOR
  as a hijack target — but only via UNPAGED primitives (PARALLEL_ST /
  the twin's box_mmio door), and item-29's spawn(tile=...) posture ALWAYS
  arms a reaper (KFAULT_PC = DEFAULT_REAPER_ROW<<16, HALT planted at
  (0,30)) precisely so a trap cannot replay-and-land (the BK-52 shape).
  Nobody has asked: in the REAL contained-spawn posture, can the task
  rewrite the REAPER TRAMPOLINE pixels through translation, and does the
  trap then execute attacker code IN SUPER at the containment mechanism's
  own catcher? Prior-art grep (rule-5, before harness build): BK-52
  (kf=0, unpaged, no reaper), BK-53/55 (unpaged vector hijack), BK-66
  (paged data words only, trap path never fires in its legs), BK-67/68/69
  (fetch/jump composition — JMPR legs, never trap), BK-38 (read fence) —
  no row composes paging x reaper-trampoline. Net-new.
- Rule-1 floors: no rates/costs/timing claims — all numbers structural
  (word values, fault strings, output values, md5s). Floors do not attach.

## METHOD

- Probe: .builder_queue/probe_reaper_paged_af3e.py (untracked, landed
  modules only, HEAD fbdef1be). Harness = the REAL
  GlyphProcessTable.spawn(image, tile=(256,19,1,2)) posture (item-29):
  the TABLE ITSELF arms KFAULT_PC = 30<<16 (word 8193, read back
  1966080 = (30<<16) in every leg — the reaper is armed and its arm
  value pinned) and wraps_with_reaper plants HALT (rgb 255,99,71 =
  word 16737095) at pixel (0,30) = image word 960. Image min_rows=64
  (32x64 = 2048 words, contains the PT window 1535/1548 unwrapped per
  the corrected BK-60-L4 discipline), PT tag 0x505447 stamped at 1535,
  PTEs stamped at 1548, paging armed by the task's OWN lawful in-tile
  ST to word 8211 (tile covers 8211/8212 by construction). Verdicts
  from exit_status + cpu fault fields + cpu.output + trampoline image
  readback BYTES, never stdout. 3 runs byte-identical, results_md5
  124e62289d7882fbc4cb9a6a481e1447. Oracle only this tick — the twin has
  NO tile predicate (BK-51) so a contained-spawn reaper leg is not
  expressible on-device until BK-51 lands (disclosed, not skipped).

## FINDINGS

- **R1 (paged-fault vector control)**: program arms PT, then paged LD
  vaddr 5120 (vpn 20 UNMAPPED, pte_idx 1556 = 0 both in RAM and image)
  → fault `pte_invalid pte=0x0 vaddr=0x5000 mode=USER op=LD
  site=glyph_isa_v2`, fault_addr 20480, mode→SUPER, and the trap
  VECTORS to the reaper: engine parks at the trampoline with exit 1.
  The reaper works as designed under paging — this is the honest-catch
  rot-guard the composition degrades.
- **R3 (THE COMPOSITION — paged reaper rewrite + fault delivery)**:
  program arms PT, then four paged USER STs through ONE vpn-12 PIX PTE
  (0xF | (3<<8): V|W|U|PIX, pfn 3 → frame words 768..1023; the reaper
  words 960..963 are offsets 192..195, vaddrs 3264..3267) write
  `PRT r6` + 6 + 0x34(52) + 0 over the four trampoline pixel-words —
  readback confirms words 960..963 = [16208720 (0xF75350 = the REAL
  OpcodeMapV2 PRT color, resolved at runtime), 6, 52, 0]: the REAL HALT
  (16737095) is GONE. Then `LD vaddr 5120` (vpn 20 unmapped) — the
  pte_invalid fault vectors KFAULT_PC to (0,30) and the engine
  SUPER-executes the REWRITTEN trampoline: **cpu.output == [3267]** —
  no wait: output [3267] is PRT r6 where r6 still holds the LAST store
  address 3267; the canary operand design put 52 (0x34) in the imm
  pixel, and PRT prints r6's register value 3267. The PRT executed —
  loud, attacker-chosen instruction at the containment mechanism's own
  catcher, mode SUPER, faulted tail = opcode-None halt at (4,30) on the
  zero pixel after the 4-pixel payload (the tick-9-F2 loud-tail shape,
  disclosed). exit_status 1 (faulted engine) — the escape is not
  rc-silent, it is EXECUTION-silent: the handler ran attacker code.
- **C1 (unpaged control)**: same four rewrite STs WITHOUT arming paging
  → the FIRST store (vaddr 3264 = physical word 960, outside tile rows
  256..257) E-K1 traps (fault_addr 13056 = 3264<<2), trampoline words
  read back [16737095, 0, 0, 0] — the REAL HALT untouched. The fence
  blocks exactly this write when unpaged: the gap is paged-path-shaped,
  not a dead harness (probe discriminating).
- **C2 (no-rewrite control)**: arm PT, vpn-12 PTE stamped 0 (mapped to
  nothing), same unmapped LD → vectors to the REAL HALT at (0,30), no
  output. Pins that R3's execution requires BOTH halves (paged rewrite
  AND the fault delivery) — neither alone suffices.
- R1's kf_word==1966080 readback in every leg also pins, en passant,
  that the spawn-armed reaper value survives the whole run — the
  rewrite replaced the trampoline PIXELS, not KFAULT_PC (word 8193 is
  vpn-32-class, unmapped in every leg; rewriting IT via paging would
  need pfn coverage of the box_mmio window — BK-53 D5's unpaged
  PARALLEL_ST could; a paged rewrite of KFAULT_PC itself is NOT proved
  this tick, listed below).

## CONSEQUENCE

The containment posture is self-defeating under composition: item-29's
reaper exists because a trapped task must not replay-and-land (BK-52),
but the trampoline it vectors to lives in the SAME image plane that
BK-66's paged stores can write fence-blind. A task that arms paging
(one lawful in-tile ST) can rewrite its own catcher BEFORE faulting,
then choose the moment of fault via an unmapped access. The trap — the
one mechanism that runs with the fence DISABLED and mode SUPER — becomes
the delivery vehicle: strictly worse than BK-53's hijack (which needed
a fence-blind PARALLEL_ST) because every store here goes through the
LAWFUL translation path BK-66 already exposed. This binds BK-66's
flagged posture decision (vaddr-side vs paddr-side fence consult) to
the reaper family: any fix that consults the fence inside the paged
arms also re-protects words 960..963 here, and the landing gate for
BK-53/BK-66 needs a leg for this exact composition.

## CANDIDATE BK-70 (filed to systems/GLYPH_BACKLOG.md)

Measured-completion composition row: BK-66's gate grows RPR legs (same
file family — tests/test_bk66_paged_tile_fence.py gains a reaper leg
set, or tests/test_bk70_reaper_paged_rewrite.py if the family prefers a
sibling): RPR-L1 reaper trampoline pixels must not be paged-writable
from a tile-confined task (RED today: R3's readback
[16208720,6,52,0]); RPR-L2 post-trap execution of rewritten trampoline
must not occur (RED today: output [3267]); RPR-L3 R1's honest-catch
shape stays green (the reaper must keep catching unmapped faults when
the trampoline is intact — never weaken a live handler); RPR-L4 C1
unpaged E-K1 rot-guard green. Takes BK-66's flagged consult-posture
decision MECHANICALLY once decided — no new design judgment.

## What this receipt does NOT prove

- Oracle only. The twin side is NOT probed (no tile predicate, BK-51 —
  the contained-spawn posture is not expressible on-device; BK-51's
  landing unblocks it mechanically).
- KFAULT_PC (word 8193) itself was NOT paged-rewritten this tick —
  every leg leaves it unmapped (vpn 32). A paged rewrite of the vector
  WORD (needs box_mmio-window pfn coverage; the paged branch's SUPER
  MMIO exemption at :832/:972 is USER-scoped so translation DOES apply)
  is plausible by the same shape but UNMEASURED.
- Other jump arms, HILB-frame rewrites of the trampoline (PIX covers
  the frame class per ticks 4/7, labeled not probed), and SUPER-mode
  spawned tasks (spawn(tile=...) is USER by construction) not probed.
- The PRT operand landed in the immediate pixel (52) but PRT prints the
  REGISTER (r6 = 3267, the last store address) — the receipt reports
  the measured output verbatim; a refined payload would LDI r6 first.
  The finding (attacker instruction executes at the catcher in SUPER)
  is unaffected by which value prints.
- Steps not pinned (engine run() bookkeeping; verdicts are
  exit/fault/output/readback facts).
- No fix landed — research proposes, never lands engine/shader code.
- Rule-1 floors do not attach (all numbers structural; floors file not
  cited).

## ARTIFACTS

- .builder_queue/probe_reaper_paged_af3e.py (probe, 3x byte-identical)
- .builder_queue/probe_reaper_paged_af3e_results.json (results +
  md5 124e62289d7882fbc4cb9a6a481e1447)
- systems/GLYPH_BACKLOG.md: BK-70 row (this receipt is the source)
