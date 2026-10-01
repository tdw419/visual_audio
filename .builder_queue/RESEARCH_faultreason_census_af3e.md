# RESEARCH — Complete fault_reason classification pass: the oracle has 8
# fault sites, 5 carry evidence strings, 3 are silent — and one of the
# silent ones is a LOAD fence (S3), not just the store side

- Tick: 2026-09-27 ~23:0x CDT, builder af3e62239ce2 (Glyph OS Event Chain cron)
- HEAD at claim: b34ff0e8 (mailbox re-verified: newest RULING mtime
  1790550013 < HEAD commit time 1790562478 — clean; QUEUE_STATE.json:
  0 non-landed; all three remedy-* tickets landed → Phase 1c eligible.
  No new CLAIM QUEUE section, no newer RULING.)
- QUESTION (from tick 2's incidental find — RESEARCH_bk60_l4_oracle_
  remeasure_af3e.md F4): the unpaged E-K1 ST fence site (glyph :1075-1082)
  sets NO fault_reason. The prior "5-site classification pass" assumed the
  census was paged-path-only. Is that the complete picture, or are there
  more silent sites — and does the silence extend to a LOAD-side fence?

## METHOD

- Static enumeration: all `self.faulted = True` sites in GlyphCPUv2.step
  (tools/glyph_isa_v2.py) — 8 total, mapped to branches by reading each
  site's surrounding elif chain at HEAD b34ff0e8.
- Live probe .builder_queue/probe_faultreason_census_af3e.py — one leg per
  reachable site, manual step-loop, fault_reason/fault_addr/mode captured
  AT the faulting step. 3 runs byte-identical, results_md5
  9ffc70d50147a388a9f710378ce8ce20.
- Site S3 (LD tile E-K1, :932) needed a harness correction, itself
  receipted: a bare GlyphCPUv2 never traps on the tile branch because
  `_tile_confinement` defaults False and is armed ONLY by
  GlyphProcessTable.spawn(tile=...) (glyph_process.py:166) —
  dbg_tile_ld_confinement_af3e.py (direct flag arm) and
  dbg_tile_ld_spawn_af3e.py (real spawn path, exit statuses from the
  process table) both confirm the corrected posture.

## THE CENSUS (site -> branch -> carries fault_reason?)

| Site | Branch | fault_reason |
|---|---|---|
| S1 :845 | LD paged pt_tag_mismatch | YES (tag_reason) |
| S2 :876 | LD paged pte_invalid | YES (measured: "pte_invalid pte=0xc03 vaddr=0x3100 mode=USER op=LD site=glyph_isa_v2") |
| S3 :932 | LD tile-confinement E-K1 | **NO — measured silent** |
| S4 :977 | ST paged pt_tag_mismatch | YES (tag_reason) |
| S5 :1004 | ST paged pte_invalid | YES (measured: "pte_invalid pte=0x0 vaddr=0x3100 mode=USER op=ST site=glyph_isa_v2") |
| S6 :1052 | ST paged pfn-ceiling (DEFECT-23) | YES ("pfn=... ceiling=65536 ... site=glyph_isa_v2:764") |
| S7 :1082 | ST E-K1 fence (unpaged) | **NO — measured silent** (fault_addr 400, mode→SUPER, correct otherwise) |
| S8 :1107 | ST out-of-RAM-bounds | **NO — measured silent**, BOTH sub-branches: iso-armed E-K1-reuse (fault_addr 80000 = word 20000<<2, running_after True — vector taken) AND standalone stop (running_after False) |

## FINDINGS

F1 — The census is 8 sites / 5 with evidence / 3 silent. The prior
   "5-site pass" (tick 2's F4 note, citing :876/:1006 comments) counted
   only the paged-path sites; S7's silence was already known; S3 and S8
   are NEW silence finds this tick.

F2 — S3 is a LOAD-side fence site going silent (tile-armed USER LD out of
   tile: faulted=True, fault_addr=16000, fault_reason=None, mode→SUPER,
   exit_status 1 under the real spawn path; in-tile control clean,
   exit_status 0, mode stays USER). Every prior classification-pass record
   (defect-23 receipt lineage) treated evidence-string coverage as a
   STORE-side + paged-path issue. A fault-classification consumer reading
   FAULT_ADDR alone cannot distinguish an out-of-tile READ from an
   out-of-box WRITE (S7) — both give fault_addr = addr<<2, mode SUPER,
   reason None. The classification-pass scope therefore widens: 3 sites,
   two of them fence sites, one load-side.

F3 — Harness discipline fact (probe defect #7, receipted): tile legs
   driven on a bare GlyphCPUv2 are DEAD — the fence never fires
   (census L3 leg: 21 steps, faulted=False, clean read of the seeded
   canary) because _tile_confinement is spawn-only. Any future probe
   claiming tile-branch coverage MUST go through GlyphProcessTable.spawn
   or explicitly arm the flag; a silent clean run proves nothing about
   the branch. This explains why S3's silence was never recorded: BK-51's
   oracle controls exercised the ST side via the spawn path (traps
   measured) but no LD-side leg with reason capture ran through spawn.

F4 — S8's two sub-branches are BOTH silent, and they differ in liveness:
   iso-armed leaves the task running (E-K1 vector, reaper continuity);
   standalone sets running=False (loud stop). A consumer keying on
   "faulted + running" sees two different severities but gets the same
   (empty) reason string from both.

F5 — Discrimination: the probe is not an always-null echo — C1/C2 parity
   legs return REAL reason strings under the identical harness (values
   quoted in the census table), and the site-specific shapes differ
   (tag/pfn strings vs None). L8b vs L8 proves the two S8 sub-branches
   diverge in running_after under one program shape.

## VERIFICATION STATUS

- RED/discrimination: C1+C2 carry populated strings; L7's fault_addr 400
  matches the BK-60 C1 measurement; S3's ST-twin control reproduces the
  BK-51 oracle control shape (fault_addr 656). The probe reproduces known
  results where they exist and extends the census where they don't.
- What this PASS does NOT prove: no engine code changed (research receipt
  — proposes, never lands); the static 8-site map is HEAD-scoped
  (b34ff0e8) and a future branch insert shifts line numbers; syscall-
  handler fault paths (BK-40's rc-based refusals) are NOT step()-level
  fault sites and are out of census scope; the WGSL twin has no
  fault_reason channel at all (twin divergence posture unchanged).
- Rule-1 floors: no rates/costs/timing — all numbers structural (word
  values, exit codes, step counts, md5s). Floors do not attach.

## CANDIDATE BACKLOG ITEM (BK-61, filed to systems/GLYPH_BACKLOG.md)

**fault_reason completion for the 3 silent sites** — S3 (LD tile E-K1),
S7 (ST E-K1), S8 (OOB store, both sub-branches) get the same evidence-
string treatment S2/S5 already carry ("op=LD tile-ek1", "op=ST ek1",
"oob len=<n>" vocabulary, site= tags matching :876's format). Gate
tests/test_bk61_fault_reason_census.py — L1: each of the 8 sites driven
live (S3 via spawn(tile=...) — the harness discipline F3 pins) asserts
fault_reason is a non-empty string naming op+class+site; L2: string
vocabulary rot-guard (each string contains its site= tag); L3: silent-today
RED — at HEAD, L1's S3/S7/S8 legs fail with reason None (measured, this
receipt); L4: non-vacuity — delete one new reason-set → its leg fires;
L5: family — defect-23 containment gate + BK-60 family legs stay green;
worktree isolation per AGENTS.md (engine-core file, 3 one-line additions).

## ARTIFACTS

- .builder_queue/probe_faultreason_census_af3e.py (census, 3x byte-identical)
- .builder_queue/dbg_tile_ld_confinement_af3e.py (S3 direct-arm diagnosis)
- .builder_queue/dbg_tile_ld_spawn_af3e.py (S3 spawn-path confirmation)
