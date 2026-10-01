# RESEARCH — BK-51 post-landing twin tile probe: the LD side under an
# armed GO-2 tile — the twin now DIVERGES from the oracle in the
# admit-all direction (out-of-tile USER LD succeeds, r3 gets the canary)

- Tick type: Phase 1c research (af3e, 2026-09-27 ~14:2x CDT). Rule-5
  grep BEFORE harness build: BK-51's own receipt explicitly lists this
  leg as NOT proven ("walk_ld under a tile (read side) — unprobed",
  RESEARCH_wgsl_tile_fence_af3e.md:112-118); no other row or receipt
  measures the twin's tile-LD posture. The 69a53298 landing made the
  oracle side of exactly this leg load-bearing (spawn(tile=...) now
  arms _tile_confinement; out-of-tile USER LD traps), which is why the
  previously-latent question is now a measured engine divergence.
- Run selection: HEAD d4ee54f7 (my own previous tick: research receipt
  + ledger append only), tracked tree clean at claim, mailbox clean —
  newest RULING RULING_BK38_READ_POSTURE.md (mtime 1790533788) is
  older than HEAD commit time 1790536402 and CONSUMED by 69a53298,
  not binding new work. Monitor CLAIM_PENDING queue=0 stall_tier=0.
  CLAIM QUEUE empty (items 19..41 landed) → research eligible.

## Part 1 — BK-51's standing on-device legs RE-MEASURED at HEAD

`.builder_queue/probe_wgsl_tile_fence_af3e.py` (the original BK-51
probe, landed modules only), 2 runs this tick, byte-identical to each
other AND to the pre-landing receipt: results md5 9701e0d40eba3fd3f9ce
12b6dd6c4d89. Note this differs from the receipt's cited stdout md5
50bdb1728b72638872d4ffab0e168e84 — that was the STDOUT md5 (incl. the
results_md5 line printed by the older probe revision); the current
results-blob md5 is stable across runs and across the landing. All
structural verdicts UNCHANGED:
- D1: tile (5,0,2,4) armed, out-of-tile ST word 164 → fault 656,
  mode→SUPER, refused — the twin's ST-side E-K1 now shows BOX-style
  parity on the out-of-tile leg.
- D2 control: BOX0 armed, out-of-box ST → fault 400 (consult LIVE).
- D3: IN-tile ST word 160 → fault 640, refused, mode→SUPER — the
  twin STILL denies the lawful in-tile store (BK-51's core defect,
  open).
- D4: TILE_H cleared to 0 through the BK-50 MMIO door, mode USER,
  fault 0 — door composition still live.
Oracle controls re-run (dbg_wgsl_tile_oracle_af3e.py): out-of-tile ST
faulted=True fault_addr=656 (word lands post-replay via the BK-52
KFAULT_PC=0 continuation quirk, unchanged); in-tile control lands
clean, mode stays USER.

## Part 2 — NET-NEW: the twin's LD side under an armed tile

New probe `.builder_queue/probe_bk51_twin_tile_ld_af3e.py`, 3 runs
byte-identical, results md5 8334c4d4f5e56082fa39e530c48a1b89:
- L1 (twin, on-device): tile armed (mmio[88..91] = 5,0,2,4), seeded
  canary 0x0ADF00D at out-of-tile word 164, program = LD r3 <- 164;
  ST r3 -> 160; HALT. MEASURED: r3 == 11399181 (0x0ADF00D) — the
  OUT-OF-TILE LD SUCCEEDS on the twin; walk_ld has no tile consult.
  The exfil ST then traps (fault 640, ram[160]==0) — the ST-side fence
  catches the store but the VALUE is already in r3, printable via PRT.
- L2 (twin control): BK-51's standing in-tile ST trap reproduces
  (fault 640) — same-run harness sanity.
- L3 (twin control): in-tile LD word 160 → r3 == canary, mode stays
  USER, fault 0 — in-tile reads lawful on the twin.
- L4 (oracle, same program through the landed spawn(tile=...) path at
  HEAD): rc == EXIT_FAULT(1), faulted=True, fault_addr == 656
  (164×4), mode→SUPER — 69a53298's LD tile fence FIRES. The twin's
  L1 success is therefore a MEASURED ENGINE DIVERGENCE, not merely a
  missing guard: identical program, tile, and seed → oracle faults,
  twin hands the attacker the word.
- L5 (source): twin walk_ld body (fn walk_ld .. fn walk_st) contains
  ZERO "TILE" references; oracle carries the _tile_confinement LD
  branch (glyph_isa_v2.py:917-945).

## Reading

Direction bookkeeping for the sequenced fence commit (BK-38..45 +
BK-51):
- ST side (BK-51 as filed): twin DENIES-LAWFUL (in-tile store refused
  — deny-all direction, tile term missing from addr_in_box).
- LD side (this probe): twin ADMITS-UNLAWFUL (out-of-tile read
  succeeds — admit-all direction, tile consult missing from walk_ld).
The two sides fail in OPPOSITE directions on the same engine — adding
the tile predicate to addr_in_box alone fixes the ST side but leaves
the read channel; adding it to walk_ld must use the SAME
tiles∪boxes-or-allowed disjunction shape as the oracle's
_tile_confinement branch, and BK-50's door posture must make the TILE
words kernel-write-only on the twin or the new predicate is
guest-disarmable (BK-51 D4 measured the door clearing TILE_H).
Also pins BK-56's scope line: 69a53298's walk_ld gate covers ONLY the
BOX_MMIO range (`if (!is_super) return 0u;` at the MMIO branch,
wgsl_glyph_isa_v2.py:364); plain RAM reads are untouched, which is
exactly the path L1 rode.

## Consequence for the backlog

- BK-51's gate spec should gain one leg: L1b — tile-armed twin USER
  out-of-tile LD must NOT return the word (RED today: r3 == canary,
  this probe); parity leg vs the oracle's post-69a53298 behavior
  (fault, rd unchanged).
- The sequenced commit's twin-side work is now: walk_st tile term
  (fixes D3's deny-lawful), walk_ld tile consult (fixes L1's
  admit-unlawful), TILE-word write posture (closes D4's disarm), all
  mirrored to glyph_dispatch/src/ + glyph_dispatch/src/glyph/ per the
  triple-sync convention.
- Numbers structural (word values, fault codes, step counts, md5s,
  byte-identity) — rule-1 floors do not attach.

## Honesty block — what this tick did NOT verify

- The paged (pt_base != 0) walk_ld path under a tile — out of scope,
  as in every prior tile probe (both probes run the unpaged universal
  posture; the pt_base==0 short-circuit is what routes L1 around any
  hypothetical future consult).
- Whether the twin's LD-side divergence is reachable from any LANDED
  fleet/kernel image — no landed image arms a tile on the twin
  (wgsl_glyph_isa_v2.py:206-208 comment unchanged); the tile must be
  probe-seeded through mmio. Latent, like BK-51's ST side.
- The oracle's post-trap state in L4 (reaper vectoring, KFAULT_PC=0
  continuation) — BK-52 territory, not re-measured here; L4's evidence
  is the fault record at the LD step (fault_addr 656, rc EXIT_FAULT),
  not the post-replay memory image.
- WGSL non-blocking-smoke lane: probe is local-GPU only (RTX 5090,
  wgpu default device); no CI leg exists for it.
- Rule-1 floors: no rate/latency/cost claims made; floors not cited.
