### 2026-10-01 ~11:5x CDT — BK-55 RESOLUTION CLOSED (verify-and-resolve, class (a), BK-53/BK-57 precedent) — twin E-K1 hijack chain re-verified DEAD live at HEAD a17a91d3, ZERO product-code changes (builder af3e62239ce2, this commit; picked at HEAD a17a91d3 == monitor fingerprint CLEAN/queue=0, mailbox rule clean — no RULING newer than 09-29 09:08, ledger STATUS ACTIVE, CLAIM QUEUE empty):

- Supply scan first: BK-79 + BK-78 remain reserved (backlog NOT claimable per header
  rules); GH-27/28/30/31/32 fillers all landed (GH-27's gate 9f76402b predates its
  backlog STATUS — noted, not this tick's paperwork); GH-29 needs a network model
  pull = outside lane reserves. The one open class-(a) row with a covering receipt
  was BK-55's verify-and-resolve tail (its own STATUS note scoped the work).
- MEASURED: probe_ek1_vector_hijack_wgsl_af3e.py re-run at HEAD → results md5
  6dd9a46fbe606aa5004d059d1a4c7f83 == BK-77's landed post-fix citation byte-exact
  (stdout md5 8042e6c76b486e0f3fcce13ac6982b03 across 2 runs, deterministic):
  D1 no hijack / D2 no landing / D3 no door / C1+C2 controls green. Closed by BK-77's
  box_confirmed() widening (51902aad); module md5 drift f95d3263→c1fe18f6 since that
  landing is BK-56 (bd76198c) co-located read posture, `git log` on the file confirms
  exactly one intervening commit, probe byte-parity confirms no regression.
- Landed: GLYPH_BACKLOG.md BK-55 STATUS open → RESOLUTION CLOSED; receipt
  .builder_queue/RECEIPT_bk55_resolution_closed_af3e.md.
- NOT proved: live-kernel twin workload (none exists — harness shapes only); BK-77's
  design-judgment flag stays open for the next twin-kernel landing; oracle BK-53 side
  not re-run (already pinned DEAD, md5 8a8bcb6f, this receipt is twin-side only).
- Next tick: unchanged posture — await Jericho's BK-78 disposition / Stage 3
  answer / new CLAIM QUEUE item or RULING; otherwise further Phase 1c research in
  NEW signal classes.

STATUS: ACTIVE

### 2026-10-01 ~11:4x CDT — MONITOR FLAP ROOT-CAUSED (TRANSIENT): REPAIR_PENDING/queue=1 was the 11:40 dogfood ENOSPC ticket's 2-minute lifecycle; dogfood re-runs PASS; ZERO product-code changes (builder af3e62239ce2, this commit; picked at HEAD bbb5c9f2 == monitor fingerprint, mailbox rule clean — no RULING newer than 09-29 09:08, ledger STATUS ACTIVE, CLAIM QUEUE empty):

- This run's trigger: monitor diff fb06b690/CLEAN → bbb5c9f2/REPAIR_PENDING queue=1.
  Live re-run at this tick of tools/glyph_build_chain_monitor.py AND the
  ~/.hermes shim twin: BOTH `head=bbb5c9f2... state=CLEAN stall_tier=0
  queue=0 supply=ok`. The flap was the level-trigger at
  glyph_build_chain_monitor.py:405-408 (open ticket ⇒ queue=1 ⇒
  REPAIR_PENDING) firing on DEFECT_DOGFOOD_20261001_114004.json — created
  11:40:04, auto-marked RESOLVED 11:42:14 by the dogfood tool's own
  successful retry (resolved_by_head=bbb5c9f2). Expected self-healing
  behavior, not a stall; no monitor change needed.
- The ticket's defect: 11:40 dogfood coreutils_search_and_stats grep
  returned `ERR:SHELLNATIVE:grep:[Errno 28] No space left on device` — a
  host ENOSPC surfacing through the BK-47 stderr-excerpt diagnostic (that
  diagnostic working as designed). MEASURED re-runs this tick: 7/7 PASS
  (6541.4ms total; coreutils 6516.8ms — consistent with the BK-78-receipted
  L5 budget break, still pending Jericho's class-(b) disposition). df at
  tick: / 75% (9.3G free), /home 92% (152G free), inodes 7%. dogfood_cron.log
  contains exactly ONE 'Errno 28' (plus the 09-25 00:2x publish_telemetry
  ENOSPC from the /home-full era).
- NOT proved: what consumed the space at 11:40 (no telemetry captured it);
  whether the full device was / (bake tmpdir) or /home — "a sibling filled
  / briefly" is IMPRESSION, NOT DATUM; known ENOSPC class per lane history
  (df / before trusting a RED — 09-2x guest-VFS Errno-28 incidents).
- No research row filed (observation only — BK-78 owns the budget question;
  the ENOSPC transient left no reproducible gate). NOT a rule-2 flip: the
  gate measured RED on a host-environment fault, not a shader/engine change.
- Next tick: unchanged — await Jericho's BK-78 disposition / Stage 3
  answer / a new CLAIM QUEUE item or RULING; otherwise further Phase 1c
  research in NEW signal classes (register-transfer family swept through
  31j; defect-31m row stands class-(a) auto-claimable in the backlog).

STATUS: ACTIVE

### 2026-10-01 ~11:5x CDT — PHASE 1c RESEARCH TICK: REGISTER-REGISTER SHIFT ALIASING MEASURED — 3 SILENT REDS, BK-79 FILED (friction scan NEW family members: the d31 series had probed 31c/e/f/g/h/i/j/k but never the register-register SLL/SRA lowerings; ZERO product-code changes — builder af3e62239ce2, this commit; picked at HEAD fb06b690 == monitor fingerprint CLEAN, mailbox rule clean — newest RULING mtime 09-29 09:08 < HEAD 11:23, ledger STATUS ACTIVE, CLAIM QUEUE empty, BK-78 + Stage 3 asks still pending Jericho):

- Source reading first (rule 5 checked: BK-30 covers SRLI/SRAI IMMEDIATES only,
  :734-766; register-register SLL :769-776 and SRA :779-813 never probed). Two
  candidate shapes: SLL's rd!=rs1 path zeroes rd BEFORE `SHL r{rd} r{rs2}` reads
  the count (rs2==rd → destroyed count); SRA's DEFECT-30 guard covers r26 (the
  count scratch) only — its sign-extend XOR scratch r29 and fill scratch r27 are
  written after rd, so rd==x29 → XOR r29 r29=0 and rd==x27 → SUB r27 r27=0.
- MEASURED at HEAD fb06b690 (probe .builder_queue/dbg_d31m_shift_reg_alias_af3e.py,
  reuses the proven d31f harness, gcc rv32i, tree==HEAD op-streams byte-identical
  per pc, 3 runs stdout md5 c8331ba8b69635e112129b5330a0a884 deterministic):
  L01 sll x9,x19,x9 → mem[768]=0x1579a000 vs golden 0xabcd000 RED (count 12
  destroyed, glyph SHL &31 mask shifted by 13 — adjacent-count corruption, worse
  than shift-by-0); L02 sra x29,x29,x8 → 0xff800000 vs 0xff876540 RED (XOR
  self-zeroed); L03 sra x27,x27,x8 → 0x0 vs 0xfff87654 RED (SUB self-zeroed);
  controls (sll clean / sra clean / srl staged-r26 DEFECT-30 path) PASS 3/3.
  ALL THREE REDS SILENT (halted=True faulted=False).
- Filed: .builder_queue/RESEARCH_defect31m_shift_reg_aliasing.md + BK-79 row in
  systems/GLYPH_BACKLOG.md (NOT claimable lane-side): fix shape = the family's
  own proven patterns (DEFECT-30 PUSH/POP count staging for SLL; the
  LBU/LHU exclude-rd scratch-set discipline for SRA). Latent-only — no landed
  gate allocates these collision classes; rule 2 not triggered.
- Rule-1 floors do not attach (structural asserts only, no rates/latencies;
  floors file not consulted). NOT proved: WGSL twin leg (transpiler-side, nothing
  spatial); live xv6-nano repro; gcc-allocation plausibility of the exact
  collision registers (argued from family precedent, not measured).
- Next tick: await Jericho's BK-78 (a)/(b)/(c) disposition, Stage 3 answer, or a
  new CLAIM QUEUE/RULING first; otherwise further Phase 1c research — the
  register-transfer family is now swept through SLL/SRL/SRA; remaining unprobed
  members per the 31j tail: none known (branch/compare 31j, JALR 31i, loads/
  stores 31c/e/g/h, ALU/imm 31f, syscall boundary 31k); scan for NEW signal
  classes outside the aliasing family.

STATUS: ACTIVE

### 2026-10-01 ~11:2x CDT — PHASE 1c RESEARCH TICK: BK-23 L5 DOGFOOD BUDGET GATE RED A SECOND TIME (friction scan standing candidate; BK-78 filed; ZERO product-code changes — builder af3e62239ce2, this commit; picked at HEAD c2eed9a4 == monitor fingerprint CLEAN, mailbox rule clean — newest RULING mtime 09-29 09:08 < HEAD 11:14, ledger STATUS ACTIVE, CLAIM QUEUE empty, QUEUE_STATE active=null / zero non-landed / zero open defects):

- Friction signal (one-command re-derivable): today's dogfood digest
  (.builder_queue/DOGFOOD_GPU_OS_REPORT.md, 11:10, HEAD 6bdea1f5) shows
  coreutils_search_and_stats at 6791.5ms of 6825.8ms — worse than the
  4006-4718ms RESEARCH_shellnative_turn_budget.md receipted on 09-25; this
  case also produced DEFECT_DOGFOOD tickets 09-25 AND 10-01 (both
  auto-RESOLVED by retry).
- MEASURED at HEAD c2eed9a4 (three independent runs, all ~1.7-1.9x over
  budget): tests/test_bk23_dogfood_ci_gate.py::test_l5_execution_budget
  _under_3500ms solo → FAILED 6097.7ms < 3500.0ms (suite healthy=True 7/7
  — arbitration question, not correctness); per-case decomp 6211.9ms in
  the case, every other case 2.8-6.1ms; per-turn live GlyphL1Shell:
  grep hit 2402ms + grep miss 1877ms + wc 2227ms = ~6.5s. The wc turn is
  the NEW third native bake from BK-46/47 (landed ~04:3x today). Cause =
  turn-count growth (2→3 first-bakes), NOT per-turn cost change (09-25
  measured ~2.3-2.5s/turn, bake-dominated 97%); BK-27's landed cache is
  working as designed and irrelevant here — zero repeat keys in-suite,
  exactly the REPAIR_PENDING_BK27 finding, now with 3 turns. Every
  native turn's output CORRECT.
- Filed: .builder_queue/RESEARCH_bk78_l5_second_break_af3e.md + BK-78 row
  in systems/GLYPH_BACKLOG.md (NOT claimable lane-side): the L5 budget
  needs a DECIDED model before a fourth native swap (head landed BK-47;
  tail/R53 candidates ~+2.3s each). Options cheapest-first live in
  REPAIR_PENDING_BK27_L5_dogfood_budget.md: (A) measured ceiling + cost
  model in the gate comment, (B) dogfood repeat turn giving the cache a
  real in-suite hit, (C) pattern-via-post-bake-mailbox ABI change. Class
  (b) product direction — presented for Jericho, not self-applied; the
  gate stays RED honestly until decided (never weakened silently).
- Rule-2 note: NOT a measurement flip of a landed ruling — this is the
  SECOND break of the same gate by the same mechanism class (first
  receipted 09-25); BK-23's L5 landing (876a2e9c) measured ~320ms and the
  09-25 research already receipted the first break. Rule-1 floors do not
  attach (CI wall-clock budget, structural numbers, no rates; floors file
  not consulted).
- NOT proved: per-turn decomposition in a process other than the claiming
  one (the digest's 6791.5ms is the dogfood tool's OWN process — treated
  as the independent corroboration); no fix attempted (class (b) hold);
  bake-cache hit/miss instrumentation not re-run (source pins from the
  landed BK-27 gate).
- Next tick: await Jericho's BK-78 (a)/(b)/(c) disposition or the pending
  Stage 3 answer; a new CLAIM QUEUE item or binding RULING first; otherwise
  further Phase 1c research (do NOT re-research the L5 budget — BK-78 owns
  it now; next standing friction candidates: BK-28..31 transpiler aliasing
  family is already filed, scan for NEW signals).

STATUS: ACTIVE

### 2026-10-01 ~11:1x CDT — BK-60 RESOLUTION CLOSED (verify-and-resolve, class (a): both defect shapes DEAD at HEAD via parallel landings; receipt + probe re-run + backlog row flip; ZERO product-code changes — builder af3e62239ce2, this commit; picked at HEAD 6bdea1f5 == monitor fingerprint CLEAN, mailbox rule clean — newest RULING mtime 09-29 < HEAD, ledger STATUS ACTIVE, CLAIM QUEUE empty, all three remedy-* tickets landed (BK-60's standing order satisfied), Stage 3 ask still pending Jericho):

- The row's THREE shapes, re-derived at HEAD: D2 (U-clear paged USER LD reads
  through) closed by BK-64/65 (e0afc4f1 — twin walk_ld PTE_U+is_user check
  wgsl:430-433, walk_st V/W/U :560); D4 (unmapped paged ST silent drop) closed
  by BK-66-twin (7c4d791d — paged ST refusals now run the E-K1 tail, return
  TRUE not silent-false); D3 (paged read into the config window through a
  plain PTE) = engine PARITY per Amendment 2, with the POSTURE question still
  open as a question: BK-56's landed read locks judge the VADDR pre-
  translation on both engines (oracle :1274, twin :872), so a translating PTE
  still reaches the config window on BOTH — class (b), Jericho's call, carried
  by the row's AMENDMENT 2, not silently dropped.
- LIVE verification this tick (not inherited): probe_wgsl_paged_fence_af3e.py
  re-run at HEAD 6bdea1f5, 3 runs byte-identical, stdout md5
  3244c40c259c7a439e58068b428c024e (record
  bk60_close_rerun_af3e_20261001.txt): D2 twin r10==4294967295 (fault marker,
  canary NOT delivered — was canary), D4 twin halts 21 steps == the oracle's
  fault step count with the value nowhere (was silent walk-to-epilogue 25
  steps), S3 silent-drop source marker ABSENT, S1 PTE_U/PTE_W refs now 1/1 in
  the walkers (were 0), C1 unpaged E-K1 control green both engines @18 steps.
  Landed gates green one combined run: BK-48 6/6 + BK-51 5/5 + BK-64 6/6 +
  BK-64red/BK-65 3/3 + BK-62/63 twin 9/9 + BK-66 7/7 + invariants 3/3 = 34/34.
- Receipt .builder_queue/RECEIPT_bk60_resolution_closed_af3e.md; backlog row
  STATUS → RESOLUTION CLOSED (BK-53/BK-57 precedent). HONEST CAVEATS: the
  probe's CPU-side numbers this tick are the KNOWN tag-gate artifacts
  (min_rows=16 harness predates the corrected BK-60-L4 discipline — D1 faults
  12288, D3 faults 12304, the exact numbers Amendment 2 attributed to
  check_pt_tag bounds); the twin-side shapes need no tag gate and are the
  datum; oracle pins cited from the corrected-harness receipt (md5
  da02059b…), not re-measured. Landing-time REDs are receipted at their
  landings (e0afc4f1/7c4d791d); this tick proves the CURRENT tree fixed.
- NOT proved: fresh on-device re-measurement of landing-time RED states;
  paged×tile twin composition beyond BK-66-twin's landed legs; no new gate
  authored (the consolidated tests/test_bk60_wgsl_paged_posture.py shape is
  superseded — every leg's content is pinned by the landed BK-64/65/66-twin/
  62-63 gates; authoring a duplicate gate would re-test landed consults).
- Next tick: await Jericho's Stage 3 answer or a new CLAIM QUEUE/RULING;
  otherwise further Phase 1c research (candidates: the D3 paged-read posture
  question needs a Jericho ruling, not research; BK-56-noted walk_ld symmetric
  MMIO READ branch is closed by BK-56; next standing candidate = new friction
  scan per Phase 1c(1)).

STATUS: ACTIVE

### 2026-10-01 ~10:5x CDT — RESEARCH TICK: BK-58's last manual-checklist item CLOSED (real mouse hit-testing measured GREEN via trusted CDP input; research receipt + BK-58b backlog row; ZERO product-code changes — viewer html md5 4dd0b813… unchanged before/after; builder af3e62239ce2, this commit; picked at HEAD 1c1a297f == monitor fingerprint CLEAN, mailbox rule clean — newest RULING mtime 09-29 < HEAD, ledger STATUS ACTIVE, CLAIM QUEUE empty, Stage 3 ask still pending Jericho's (a)/(b) answer; research-eligible per Phase 1c):

- Legs (probe_bk58_mouse_legs_af3e.py, md5 ac8eb609…, headless Chromium 153, real Input.dispatchMouseEvent at coordinates computed with the viewer's OWN inverse mapping): M1 hover → hoverCell EXACT cell + tooltip exact title; M2 mousedown/mouseup/click → drawer opens on that cell (badge+title exact); M3 real wheel → zoom ratio EXACTLY 1.15 (0.4619140625→0.4016644021739131), cursor-anchored pan intact; M4 hover off-cell → tooltip hidden, hoverCell null. 4/4 GREEN twice.
- RED-first (probe_bk58_mouse_red_af3e.py, md5 22b2cccc…, served-copy pick-math neuter + Page.reload ignoreCache): exit 1, "2 / 4" — M1/M2 FAIL with the mis-pick shape (hover lands on neighbor cell (1,0), WRONG title "ruling(ps012)…"), M3/M4 controls green. The legs assert exact cell identity, they discriminate.
- HARNESS LESSONS (both caught because the RED check passed vacuously first, receipted in RESEARCH_bk58_mouse_hit_testing_af3e.md): (1) the +4 neuter shifts the pick EXACTLY onto the 8.0 cell boundary — FP kept it in cell (0,0); (2) Chromium integer-truncates dispatched clientX (405.347 arrives as 405, measured via tooltip.left "421px"), so +4 was STILL cell (0,0) on a genuinely neutered tree (live handler source read over CDP proved the neuter was running); final shift +5 crosses into cell (1,0) in both worlds. A RED harness must compute its corruption through the same pipeline the code sees.
- Findings filed: .builder_queue/RESEARCH_bk58_mouse_hit_testing_af3e.md; backlog row BK-58b (rot-guard gate promotion, tools/tests-only, NOT claimable without Jericho) filed in systems/GLYPH_BACKLOG.md.
- NOT proved / open: DPR≠1 composited hit-testing (headless ran DPR 1; DPR-independence reasoned, not measured); touch/pointer-event paths; `speak` class still unreachable (no speak-class cell). BK-59 Stage 3 (a)/(b) ask UNCHANGED and still the lane's blocking output — no compositor-native work before the answer.
- Next tick: await Jericho's Stage 3 answer; if a new CLAIM QUEUE item or binding RULING appears, take it first; otherwise further Phase 1c research (BK-60 twin paged-walker posture is the next standing candidate).

STATUS: ACTIVE

### 2026-10-01 ~10:3x CDT — INDEPENDENT LANDING-VERIFY TICK (builder af3e62239ce2, this commit; ZERO code changes; picked at HEAD 7785a1f2; started as an in-flight-completion of the bk54-ring worktree, ended as verification when the authoring session landed 4a6c44dc mid-flight and deleted the worktree):

- The bk54-ring worktree's uncommitted draft (branchy CMP+JZ tile) went AWAY mid-session; its replacement landed as 4a6c44dc (branchless). This tick's pre-deletion analysis MEASURED why the branchy approach fails: numeric branch targets ('JZ 46,0') do NOT resolve — glyph_ir.raise_lines_to_ir parses the operand as a block NAME and StaticVerifier rejects "targets unknown block '46,0'" (measured live: BK-24 family 3f/2p with StaticVerificationError on 'ingest_tile__entry'); and the draft's drop-counter tail ('LDI r12 725 / LDI r15 725 / ST r15 r12') stores 725 INTO word 725, unable to satisfy any exact-count leg. The landed branchless re-engineering sidesteps exactly this trap — the deletion was justified, not a lost-path race.
- Landing verified INDEPENDENTLY on the committed mainline tree (not the receipts): tests/test_bk54_ring_saturation.py 8/8 GREEN (18.66s); family BK-24 5/5 + BK-46 8/8 + BK-47 6/6 + BK-11 6/6 = 25/25 GREEN (56.60s); GH-23 libc suite 5/5 GREEN. Gate legs L1/L3/L4/L4b assert exact cursor/counter arithmetic (cursor==832, dropped==10 on the 401-byte fixture, 0 drops on exact-fit), L5b is the live non-vacuity RED (neuter restores cursor 872).
- NOT verified this tick: the L2 deep-overflow leg's own RED-first (only the landed GREEN was re-run); WGSL twin (ring is Python-mechanism surface, no twin leg by design); BK-53/57 resolution-tail md5s not re-derived (scorecard cites them; prior tick re-ran both probes).
- Lane state: BK-59 Desktop Gate prerequisites 100% GREEN; Stage 3 open/close is class (b) RESERVED to Jericho — the one-line ask is presented in RECEIPT_BK59_desktop_gate_scorecard.md. Next tick: await Jericho's (a)/(b); no compositor-native work before the answer.

STATUS: ACTIVE

### 2026-10-01 ~10:2x CDT — BK-54 LANDED + BK-59 DESKTOP GATE PREREQUISITES 100% GREEN (branchless write-ring saturation clamp + BK-53/57 resolution tails closed + Stage 3 Class (b) ask presented) (commit 4a6c44dc via worktree bk54-ring, merged fast-forward to mainline HEAD a9d46f91; claimed per DIRECTIVE_BK59_DESKTOP_GATE.md §3.3/§4 class (a) auto-claim):

- BK-54 Fix (100% branchless saturation mechanism): stamped branches in :__g23tile rect suffer displacement/relocation traps (target :__g18tile in _rel_baker) and StaticVerifier operand rejections. Re-engineered tools/glyph_gpt/libc_runtime.py _gh23_sys_write_tile to be 100% branchless: CMP r11 r12 computes r0 = (cursor == 832); increments loud drop counter in word 725 by is_sat; advances cursor via cursor += 4 * (1 - is_sat) (clamps at 832); diverts excess frame stores to dead-sink 726..729 via dest = cursor - is_sat * (cursor - 726). Words past 832 (including canaries at 840/860) remain untouched. Legacy mirror 718..721 maintained on both lawful and saturated paths.
- Gate tests/test_bk54_ring_saturation.py 8/8 GREEN (20.29s): L1 cursor clamps at 832 with head bytes exact; L2 canaries at 840/860 untouched during overflow; L3 dropped-frame count in word 725 exact (10 frames dropped for 401-byte stream); L4/L4b sub-ring stream and exact 256-byte stream fit with 0 drops; L5 structural pins verify clamp, compare, and drop counter; L5b non-vacuity neuter restores red overflow (cursor 872); L6 family run BK-24 5/5 green.
- Family baseline on mainline: BK-24 5/5, BK-11 6/6, BK-46 8/8, BK-47 6/6, BK-56 13/13, BK-52/38 11/11 (all green).
- Paperwork resolution tails closed: BK-53 (oracle hijack chain confirmed DEAD, md5 8a8bcb6fa7dd9b5d440d9e8dfa32b2e8); BK-57 (twin tile-LD divergence confirmed DEAD, twin faults 656 with r3=0, md5 7033af4b3fd878be78adfd883dba673a, subsumed by BK-48 ld_tile_fault). Backlog rows updated to RESOLUTION CLOSED.
- BK-59 Desktop Gate: 100% of Definition of Done conditions measure GREEN across both engines at HEAD. Stage 3 open/close is Class (b) — Product Direction, reserved to Jericho. Formal one-line ask presented for operator decision.
- Next tick: await Jericho decision on Stage 3 (a)/(b); otherwise dogfood telemetry & maintenance.

STATUS: ACTIVE

### 2026-10-01 ~09:4x CDT — BK-59 DESKTOP-GATE SCORECARD FILED (directive + receipt; ZERO product-code changes; builder af3e62239ce2, this commit; picked at HEAD ba4b955d == monitor fingerprint, mailbox rule clean, ledger STATUS ACTIVE, CLAIM QUEUE empty):

- Every DoD line of BK-59 measured at HEAD ba4b955d this session (RECEIPT_BK59_desktop_gate_scorecard.md): BK-38..45+52 re-run 11/11 (0.31s); BK-56 landed bd76198c 13/13; BK-50/51/77 landed receipts; BK-53 chain re-verified DEAD live (probe stdout md5 8a8bcb6f2fd9cc730a1fd5e72c68ec41 == landed citation); BK-55 dead per BK-77 post-fix md5 6dd9a46f...; **BK-57's filed divergence NO LONGER REPRODUCES** (probe re-run results md5 7033af4b3fd878be78adfd883dba673a vs the research receipt's 8334c4d4 — twin out-of-tile LD now faults 656/r3=0/SUPER; subsumed by BK-48's landed ld_tile_fault; row marked STALE-DIVERGENCE-QUEUED); **BK-54 ring overflow re-verified LIVE** (cursor 872, 40 words past 832, md5 645e32d319f2e9014d2e06fd5cfa178b == receipt).
- DIRECTIVE_BK59_DESKTOP_GATE.md filed: BK-53 + BK-57 RESOLUTION tails queued (paperwork, no code); **BK-54 hooked CLAIMABLE NOW** (class (a) auto-claim per DECISION_RULES §3 which names the row; posture: bind the streaming-write cursor at the mechanism libc_runtime.py:144-161 to the declared ring end, drop excess with a loud status word — buffer semantics, no fault, BK-75 does not attach; gate tests/test_bk54_ring_saturation.py per directive §4); **Stage 3 open/close RESERVED to Jericho (class (b))** — one-line ask follows after the three closures land; NO compositor-native work before that answer.
- Backlog hooks: BK-53 RESOLUTION QUEUED, BK-54 CLAIMABLE NOW, BK-57 STALE-DIVERGENCE-QUEUED, BK-59 scorecard pointer.
- NOT proved / open: BK-54 fix not written (re-measured + postured only); BK-48's L1a rot-guard coverage of the BK-57 shape asserted from the resolution tail, not isolated re-run; no WGSL device leg this session (twin citations are landed gate receipts); Stage 3 readiness is conditional on the closures + Jericho's answer.
- Next tick: claim BK-54 (gate per DIRECTIVE_BK59_DESKTOP_GATE.md §4), write BK-53/BK-57 RESOLUTION tails, then file the one-line Stage 3 ask with the final scorecard.

STATUS: ACTIVE

### 2026-10-01 ~08:1x CDT — BK-56 LANDED (config-block READ posture — the LAST open channel of the fence family closed; USER reads of the BK-41 locked words now refuse on BOTH engines, no-vector, mode-scoped) (builder af3e62239ce2, commit bd76198c via worktree bk56/read-posture, merged fast-forward to mainline; claimed IN-FLIGHT work: the seat-lane directive DIRECTIVE_BK56_MMIO_READ_POSTURE.md (07:22) + drafted consult + RED probe found in the bk56 worktree (engine mtime 07:52), completed per the finish-in-flight rule):

- Fix (both engines, refusal-parity): WGSL twin `bk56_config_read_refused()` wired at the LD arm BEFORE walk_ld (tools/wgsl_glyph_isa_v2.py + both glyph_dispatch mirrors, md5 c1fe18f68527f93df2e7da9f308369af x3); oracle new LD elif before the tile-confinement arm (a locked word inside an armed tile refuses as a CONFIG read) + PARALLEL_LD whole-op consult (tools/glyph_isa_v2.py + mirror, md5 048aa1eb63a2cb02f579c4cf1568a276 x2). Refusal shape: rd NOT written, fault_reason mmio_config_read_refused, fault_addr=word<<2, mode->SUPER, stop, NO vector (BK-75 KFC-L6 — vectoring would itself leak the fault PC; research finding 6: the read channel has no fault path to ride, this consult IS new code on both engines). Scope = the SAME 11-word set as the BK-41/50/77 write lock; SUPER exempt; SYS_A0/A1 + INPUT ring + MODE_LATCH + TILE words keep the landed silent-0 semantics (BK-76 §0 intact).
- Gate tests/test_bk56_mmio_read_posture.py 13/13 GREEN x2 (38.22s / 18.71s) + re-verified 13/13 on the committed MAINLINE tree (19.11s). Every twin leg on the real WGSL device (RTX 5090): L1 KFAULT_PC refused (fault 32772=8193*4, mode 0, result word 0, kf untouched = no vector); L2 BOX0_HI refused (32784); L3/L4c SUPER reads green both engines (mode-scoped, not a blanket); L4a/b oracle refusal-parity; PARALLEL_LD whole-op refusal (regs 2/3 unwritten, no vector); boundary legs: SYS_A0 not widened, MODE_LATCH scope-amendment rot-guard, plain-RAM LD unaffected; L5 non-vacuity (temp-copy neuter -> fault word stays 0, real tree md5-pinned before/after); L6 family subprocess BK-48 6/6 + BK-50 6/6 + BK-77 7/7.
- RED-first (probe .builder_queue/probe_bk56_read_refuse_af3e.py, pre-fix at HEAD f1588fbe, results md5 b9848e6f4202004521598c092b513c6f): T1/T2 twin silent-0 clean USER halt (fault 0, steps 5 — the whole window read as unset words); O1 faulted=False clean halt. Post-fix probe md5 b7b26ecef1bbb6f3d8305b735e731396: T1 fault 32772 mode 0 no vector, T2 32784, T3/O2 boundary clean, O1 faulted mmio_config_read_refused addr 32772.
- Family on the committed tree: oracle fence family BK-38..45 + BK-66 + invariants 75/75; twin family BK-38 + BK-48/49/50/51/62-63/64/65/76-twin/77 43/43; xv6-nano 13/13 (the lawful-read oracle — no scenario lost clean halt, directive §3.5 satisfied: no lawful read caught, no scope error); xv6-boot 5p/2s; test_n1_engine_byte_unchanged RED pre-commit BY DESIGN (HEAD-pinned drift guard, BK-76/40/41/43 precedent) — green exactly at commit bd76198c (the RED-then-GREEN pair is the receipt).
- Fence family BK-38..BK-77 is now COMPLETE on BOTH sides and BOTH doors (write BK-41/50/77 + read BK-56; oracle + twin; scalar + parallel + stack + syscall + paged arms).
- NOT proved / open: syscall DATA-handler copy paths as config-read arms not exercised (dest consult is BK-40's; research S1 found the leak shape on the LD arm only); paged arms not BK-56 legs (config window unpaged on all landed images); BK-59 Stage 3+ desktop-gate directive now ELIGIBLE per the directive's landing sequence §5.3 — file on the NEXT tick per the clean-ledger rule (the console bridge should not ship with the reconnaissance channel open — it no longer can).
- Next tick: file DIRECTIVE_BK59 (Stage 3 desktop gate) per the directive's sequence, or a new CLAIM QUEUE item / binding RULING first.

STATUS: ACTIVE

### 2026-10-01 ~06:0x CDT — BK-58 MANUAL-CHECKLIST VIEWER LEGS CLOSED (headless browser, tests/tools-only, ZERO product-code changes): the landing's "NOT proved" drawer legs are now measured — real Chromium headless drove the REAL viewer HTML (byte-identical to HEAD, md5 4dd0b8132c927cd1d4af4e25b7a41385) against the REAL bridge on canonical :8765, 5/5 legs GREEN + RED-first via a served-copy neuter (builder af3e62239ce2, this commit; picked at HEAD e9a8a451 == monitor fingerprint, mailbox rule clean — newest RULING mtime 09-29 < HEAD, ledger STATUS ACTIVE, CLAIM QUEUE empty, all queue rounds landed):

- LEGS (probe .builder_queue/probe_bk58_viewer_legs_af3e.py, md5 a62eb27643f39b4125c1d5b3d99b50c4; DevTools Runtime.evaluate against the page's OWN functions — launchClassFor/openDrawer/termSend/termLine, the exact code paths the click handlers call; Page.reload ignoreCache before every leg set): V1 HUD populated (400 commits, 730 cells, frontier e9a8a451, imgLoaded); V2 drawer opens on cell selection + Run button visible with per-cell class label; V2b click→WS connect to ws://127.0.0.1:8765, term+input panes shown; V3 the demo program LDI r7 7/PRT r7/HALT round-trips over the viewer's OWN WebSocket frame path, output '7' rendered via termLine (textContent, no-innerHTML path); V4 LIVE ollama round-trip — qwen2.5-coder:7b on 127.0.0.1:11434 answered 'pong' through the same socket (the landing's "ollama may not be serving" caveat: it is serving, path works end-to-end).
- RED-first (neuter .builder_queue/probe_bk58_viewer_neuter_af3e.py: launchClassFor → return null in the SERVED copy, wire-verified, page reloaded): V2 FAIL 'no glyphdbg cell', V2b/V3/V4 FAIL 'bridge not connected' — 1/5 exit 1; pristine restored → 5/5 exit 0. V1 passes on both trees (map unaffected by launch-class wiring — the control).
- HARNESS DEFECT (the load-bearing one, receipted in RECEIPT_BK58_viewer_legs.md): the first RED attempt passed 5/5 on the NEUTERED html — the tab was still running the page loaded BEFORE the neuter (no cache headers needed; the tab simply never refetched). Exposed by reading launchClassFor.toString() LIVE over CDP; fixed with Page.reload{ignoreCache} + settle sleep. LESSON: a headless verification without a forced reload verifies the first page load forever.
- LIVE evidence: GREEN runs appended genuine bk58_bridge_launch rows to the LIVE decision_log.jsonl (27 bk58 rows now, glyphdbg ok + ollama ok, 16-hex evidence hashes) — left in place as true launch history.
- NOT proved / open: real MOUSE hit-testing on the canvas (mousedown/click geometry; legs drive openDrawer/termSend directly at the handler-called functions, the clientX→cell pixel math itself unexercised); `speak` launch class end-to-end (no speak-class cell exists in current map data — launchClassFor never returns it, viewer cannot reach it; bridge handler stays validation-gated); multi-tab bridge behavior (gate L3 owns socket isolation). BK-59's Stage 3+ desktop gate UNCHANGED — the fence-family open set still bars compositor-native work.
- Family: BK-58 gate tests/test_build_map_bridge.py 5/5 re-verified green at this HEAD this session. tools/{build_map_bridge.py, build_map_viewer.html, spatial_build_map.py}, tests/, engine/: UNTOUCHED (viewer restore md5-verified; git status shows only the pre-existing live-chain build_map regen dirt + monitor-fix files, none of them this session's edits).
- Next tick: re-scan for new CLAIM QUEUE / RULING; otherwise the standing research candidates (BK-56 read posture measurable; walk_ld symmetric MMIO READ branch) or BK-54 (research-filed, NOT claimable without Jericho).

STATUS: ACTIVE

- Deliverables (tools only, ZERO engine/shader changes): (1) tools/build_map_bridge.py NEW — stdlib-only WebSocket bridge (hand-rolled RFC6455 over asyncio streams), 127.0.0.1 bind only, CLOSED launch-class set {glyphdbg, speak, ollama, ping}, no host shell ever spawned, every launch (accepted AND refused) appended to .builder_queue/decision_log.jsonl with a 16-hex sha256 evidence hash + kind bk58_bridge_launch; glyphdbg assembles/runs caller program TEXT through the live GlyphAssemblerV2/GlyphCPUv2 in-process (bounded 1..2000 steps, printable-charset gate, no host FS); ollama pinned to 127.0.0.1:11434 fixed model qwen2.5-coder:7b 30s timeout; speak stages text under /tmp/bk58_speak_scratch only. (2) tools/spatial_build_map.py — LAUNCH_CLASS_BY_TYPE closed map, per-cell launch_class field in build_map_data.json (commit→glyphdbg, verdicts→ollama, ruling→None); PNG regen byte-identical x2 (determinism held, scratch window carried, watchdog then regenerated the live pair with the new field). (3) tools/build_map_viewer.html — drawer gains ▶ Run/Teleoperate button + terminal pane + stdin line speaking JSON over ws://127.0.0.1:8765; textContent-only rendering (no innerHTML escape path); launch routing mirrors the renderer's map; rulings carry no launch surface.
- GATE tests/test_build_map_bridge.py 5/5 (L1 unknown-class refusal + logged refused:unknown_class; L2 glyphdbg real-output leg 42 in output, halted, unfaulted; L2b validation refusals (control chars, step bound); L4 every-launch-logged with evidence hashes; WS leg = REAL localhost socket pair through the module's own frame codec, two interleaved sessions prove isolation — each session's output carries only its own program value). RED-first: probe_bk58_dispatch_af3e.py measured the assemble-signature defect live (program-str vs List[str] API, caught pre-landing); probe_bk58_red_af3e.py — whitelist neutered in TEMP-COPY → the refusal shape GONE (KeyError escapes dispatch), engine wiring broken → happy path fails, real-module control green: the gate discriminates.
- LIVE end-to-end measured (not just in-gate): bridge served on 127.0.0.1:8765, stdlib client did handshake + ping {pong} + glyphdbg (output [7], 3 steps) + unknown-class refusal over real WebSocket frames; bridge log records then REMOVED from live decision_log.jsonl (probe artifacts, not lane history — 16 rows purged, 283 legit rows intact).
- Family on the committed tree: BK-58 gate 5/5 + test_map_substrate 4/4 + test_gh28_scratch_window 5/5 = 14 passed post-commit; pre-commit hooks: no core/engine/WGSL files staged (Pillar 2.3 parity correctly skipped). Numbers structural, rule-1 floors do not attach.
- NOT proved / open: the drawer legs stay the row's MANUAL-CHECKLIST (headless browser not exercised; JS syntax-verified via node parse only); ollama/speak handlers gated at validation level only (no live ollama round-trip in the gate — ollama may not be serving; speak path spawns speak.py subprocesses, untested end-to-end); single-instance bridge posture (no multi-process bind contention test); BK-59's Stage 3+ desktop gate UNCHANGED — the fence-family open set (BK-53/54/55/56/57/60) still bars compositor-native work; backlog BK-58 row's status cell not yet flipped (backlog header reserves row edits; the ledger is the lane's record of landing).
- Next tick: re-scan for new CLAIM QUEUE / RULING; otherwise BK-58's manual-checklist viewer legs via a headless browser, or the standing research candidates (BK-56 read posture measurable; walk_ld symmetric MMIO READ branch candidate from BK-50's receipt).

STATUS: ACTIVE

### 2026-10-01 ~05:1x CDT — BK-77 LANDED (twin box-only config lock — the BK-55 residual closed): the BK-50-twin lock's scope term widens from TILE_H-only to ANY-ARMED-FENCE (tile OR box) in BOTH bk50_config_write_refused and the ever_user latch — the measured twin/oracle divergence "twin lands / oracle refuses" in the box-only posture is dead, twin parity with the oracle's no-_tile_confinement E-K1 arm (builder af3e62239ce2, this commit; picked at HEAD e9f453c8 == monitor fingerprint, tracked dirty set verified = pre-existing monitor-fix files + live-chain build_map regenerations, mailbox rule clean — newest RULING mtime 09-29 09:08 < HEAD, ledger STATUS ACTIVE, CLAIM QUEUE empty, research receipt + backlog row landed by the prior tick at 04:5x):

- Fix (tools/wgsl_glyph_isa_v2.py + both glyph_dispatch WGSL mirrors, md5 f95d3263dd0f00155226b5d119f637f2 x3): new `box_confirmed()` (any of BOX0/1/2 HI != 0 — twin of the oracle's unset-range-never-matches rule, addr_in_box :744-747) OR'd into (a) bk50_config_write_refused's scope bail (was: TILE_H==0 -> inert) and (b) the ever_user latch (was: was_user && TILE_H!=0). Word set UNCHANGED (the BK-41 locked 11; MODE_LATCH 8192 + TILE 8280..8283 stay excluded by the measured scope amendment). Refusal shape UNCHANGED: the no-vector Option A tail (BK-75 KFC-L6 restart-loop constraint — the fix's own refusal must not vector).
- Gate tests/test_bk77_twin_boxonly_lock.py 7/7 GREEN x2 pinned runs (13.63s / 12.68s). RED-first at landing (unfixed tree, /tmp/bk77_red_run.log md5 81f901bd9d8feeb54b530ebe4dea8b0f, exit 1): L1 kf=7 LANDED via the door (the exact D1 defect), L3 kf=7 landed no-fault USER (D3), L2 ram[200] rewritten by trapped-into SUPER code (D2); 5 failed / 2 passed. Probe corroboration at the same HEAD: probe_ek1_vector_hijack_wgsl_af3e.py results md5 15a5dda21e2bf25c9c252d0383172c85 == the receipt's (D1 HIJACK / D2 SUPER CAPABILITY / D3 door open). Post-fix probe on the landed tree: results md5 6dd9a46fbe606aa5004d059d1a4c7f83 — D1 no hijack (fault 32772, no output), D2 no landing (ram[200] keeps 0x1234), D3 no door (kf=0), C1/C2 controls still green.
- GATE-DRAFT DEFECTS caught by the legs' own runs, receipted in the test docstring/asserts: (1) L5 boot leg asserted mode_final==1 (USER) but a SUPER-seeded run stays SUPER (mode 0) — fixed to mode 0 + halted; (2) L1/L2 asserted fault_addr == 3996 (the trigger's OOB word) but the no-vector refusal stops the machine AT the arm ST, so the recorded fault is the refused window word 32772 — pinned to 8193*4; (3) first box_confirmed() draft took a `ptr<storage>` param — WGSL module-scope binding access is not parametrizable ("Invalid sub-access into type [0]" shader parse error on every leg), rewritten as a plain zero-arg fn reading box_mmio directly (L6's neuter marker updated to the landed call shape).
- Family on this tree: BK-77 7/7 x2; WGSL twin family BK-50 6/6 + BK-76-twin 7/7 + BK-76-oracle 6/6 + BK-51 + BK-48 + BK-49 = 39 passed; oracle fence family BK-41 + BK-40 + BK-42 + BK-43 + BK-44-roots + BK-66 = 46 passed. Every BK-77 device leg ran on the real WGSL device (RTX 5090, BK-49/50/51/76 harness shape).
- NOT proved / open: oracle side untouched (it already refuses — dbg_bk55_boxonly_oracle_af3e.py control in the receipt); no live-kernel twin workload exists to prove the widened latch harmless to real box-only images (source-read found none writing locked words post-USER — the design-judgment flag from the receipt stands RECORDED, not resolved: whether ever_user should latch on any-fence-armed is now landed behavior, backed by L5's boot-phase leg + BK-50 6/6 over-confinement re-run); BK-70/71/72/73/74/75 research rows remain research rows (oracle-side, their own gates when claimed).
- Next tick: re-scan GLYPH_BACKLOG for the next open row (BK-54 ring saturation is the standing candidate; BK-56 read posture now measurable), or a new CLAIM QUEUE item / binding RULING first.

STATUS: ACTIVE

### 2026-10-01 ~04:3x CDT — BK-46 + BK-47 LANDED (sequenced commit: wc + head shell-native dynamic seed path — the falsified "16-byte window" swap refusals retired on both branches, the missing-_COMMON preamble injector landed, the opaque ERR:SHELLNATIVE mask replaced by a stderr-excerpt diagnostic; PLUS one family-caught defect fixed: the host wc shim's splitlines() phantom line) (builder af3e62239ce2, this commit; picked at HEAD 9fa94508 == monitor fingerprint, mailbox rule clean — no RULING newer than HEAD, newest RULING mtime 09-29 09:35 — ledger STATUS ACTIVE, CLAIM QUEUE empty — finished as IN-FLIGHT work: fix + both gates + probes found uncommitted in the mainline tree, mtimes 04:10-04:13, no ledger entry; completed per the finish-in-flight rule):

- Fix set: coreutils_port.py (md5 0be4bfb0634951c7fb37feca36314bb9) wc body V2 — bk11_out_dec arbitrary-width emitter replaces the 2-digit buf[3] renderer (the measured '310'→'O0' class), single-space "%d %d %d %s" format, three_digit fixture (data_len_override), wc pins moved; glyph_l1_shell.py (md5 2630dd23e77e92685ce71553e7187564) — wc + head branches SWAPPED to _shell_native with the falsification stated in the refusal comments (BK-24 ring carries any size; past 64 words it refuses LOUDLY), _shell_native prepends _COMMON to V1-body dynamic TUs (VOL2 grep/tr excluded) + wc_name seed, and the BK-47 L4 contract: compile/link failures return ERR:SHELLNATIVE:<verb>:<first stderr 'error:' line> from BOTH arms.
- GATES: tests/test_bk46_native_wc_swap.py 8/8 ×2; tests/test_bk47_head_dynamic_path.py 6/6 ×2 (L5b is the discriminator: _COMMON monkeypatch-neutered → device run returns the bare ERR string, restored → green). RED-first: committed probes (bk46 md5 eba40f33, head md5 c2b53f4f, head results md5 43bf2f0366674987708daa3980aa326d) measured the pre-fix shapes at HEAD; BK-47 stash-RED 3f/3p at HEAD 9fa94508 (L4/L5/L5b); BK-46 stash-RED 2f/5p (L4/L5). RECEIPT-HYGIENE CAVEAT (stated, not hidden): on an unfixed tree the gates' L1-L3 legs pass vacuously — the still-dead native branch routes to the host shim; the probes + BK-11's own RED addendum pins carry the true defect evidence.
- FAMILY-CAUGHT DEFECT, fixed: after the swap, test_l1_shell_personality w5 went RED — the HOST SHIM _wc counted lines with splitlines() (phantom line on no-trailing-newline files: 'aa\nbb\ncc' → shim '3 3 8', native + real wc '2 3 8'); _wc fixed to POSIX text.count("\n"), w5 pin migrated 3→2, new L3b parity leg added (measured RED pair ('2 3 8 noeol.txt', '3 3 8 noeol.txt')). Real wc is the oracle; the shim was the defect.
- Family on this tree: BK-46+47+BK-11+l1_shell_personality 35/35 (BK-11 fixtures re-pinned byte-exact to the new wc shape, ring readout for >16B reports); regressions BK-50 twin 6/6 + BK-45 7/7 + monitor worktree-blindness + fingerprint hygiene = 26/26; engine mirrors byte-identical 8dd8ce806e07249b570d2539a1260612 x2 — NO engine change. Backlog BK-46/BK-47 rows + RESOLUTION tails appended (append_bk46_bk47_resolution_af3e.py); full receipt .builder_queue/RECEIPT_BK46_BK47_shell_native_seed.md. Numbers structural, rule-1 floors do not attach.
- NOT proved / open: pipe/stdin wc-head forms (host shim consumers by design); tail native path (no native source exists — posture pinned host-side); WGSL twin (Python-host surface); head's BK-27 cache-hit path beyond the shared collector; the walk_ld symmetric MMIO READ branch (BK-50's disclosed config-READ channel, still the standing candidate research item).
- Next tick: next open backlog row per row order (BK-54 blast-radius receipt landed; re-scan GLYPH_BACKLOG for the next open row), or a new CLAIM QUEUE item / binding RULING first.

STATUS: ACTIVE

### 2026-10-01 ~03:4x CDT — BK-50 twin LANDED (WGSL walk_st MMIO-door config lock — the LAST open fence-family row; fence family BK-38..50 now COMPLETE on both oracle and twin sides): the BK-41 locked CONFIG set is kernel-write-only at the twin's walk_st door, twin parity for the landed oracle posture (builder af3e62239ce2, this commit; picked at HEAD e8beabab == monitor fingerprint, tracked dirty set verified = pre-existing monitor-fix files + live-chain build_map regenerations, mailbox rule clean, newest RULING mtime 09-29 09:35 < HEAD, ledger STATUS ACTIVE, CLAIM QUEUE empty — finished as IN-FLIGHT work: fix + gate + gate-draft found uncommitted in the mainline tree, mtime 02:34, no ledger entry; completed per the finish-in-flight rule):

- Fix (tools/wgsl_glyph_isa_v2.py, md5 1aa4d0407600131ce53c2c8ff5b23458, triple-synced to both glyph_dispatch mirrors x3): `BK50_LOCKED_WORDS` (11 words: KFAULT_PC 8193, KSYS_PC 8194, BOX0/1/2 LO+HI, KTICK_PC 8207, TIMER_COUNT 8208, TIMER_RELOAD 8209; MODE_LATCH 8192 + TILE words 8280..8283 EXCLUDED per BK-41's measured scope amendment — S6/S11 lawful re-arm) + `bk50_config_write_refused()` consulted additively at the ST dispatch arm AFTER the landed BK-76-twin vector-word clause (which stays first; trio behavior byte-identical). Refusal = the BK-76 Option A shape: store dropped, FAULT_ADDR=word<<2, FAULT_PC packed, mode→SUPER, stop, NO vector (restart-loop immunity). Term set = ever_user latch + TILE_H!=0 + MMIO window + locked set.
- **LOAD-BEARING GATE-DRAFT DEFECT caught by the gate's own L1**: the in-flight first draft gated its clause on `cpu.mode == 0u` (SUPER), copying the BK-76 clause's polarity — but the measured BK-50 door is a **USER-mode** store landing through walk_st's mode-blind MMIO branch (:604-605); the oracle locks BOTH post-USER arms (USER at E-K1 :1041, SUPER at the :968 exemption arm). The draft stayed RED with the clause present (canary 0xadf00d landed at BOX0_HI, mmio[4]=11399181, 4 steps); polarity flipped to mode-agnostic, scope lives in the function. Receipted in the clause comment + RECEIPT_BK50_twin_config_door.md.
- RED-first at landing (fix stashed, engine md5 c96ac0149289828574281ef78d20409a): L1 FAILED (USER canary LANDED at BOX0_HI), L2 FAILED (disarm self-grant BOX0_HI=65536 landed), L5 errored on absent clause marker; L3/L4/L6 green (harness live). Fix → 6/6, twice (pinned runs).
- Gate tests/test_bk50_wgsl_config_door.py 6/6 GREEN x2, every leg on the real WGSL device (BK-48/49/50/51/76 harness shape): L1 USER canary→8196 refused (BOX0_HI stays 1300, fault_addr=32784, SUPER, no vector); L2 disarm chain dead (8196 AND word 999 unchanged); L3 scope — lawful TILE_H store LANDS (never widen the lock); L4 boot-phase never-USER SUPER store lands (latch gates on USER history); L5 non-vacuity — neutered clause in a TEMP-COPY module reproduces L1's pre-fix shape, real tree md5-pinned; L6 family subprocess (BK-51 twin + BK-41 oracle).
- LIVE-GUARD INTERACTION, amended never weakened: BK-76-twin TW-L5 went RED post-landing — neutering the BK-76 clause alone no longer lets the KSYS_PC sentinel land because the additive BK-50 clause also refuses 8194 (the overlap IS the BK-50 thesis). TW-L5 neuters BOTH refusal sites now (md5-pinned); BK-76 clause semantics for the trio unchanged. Post-amend twin suite 7/7.
- Family on this tree: BK-50 6/6 x2; twin+oracle fence anchors (BK-76-twin, BK-76-oracle, BK-51, BK-48, BK-49, BK-66-paged, BK-41) 50 passed one run; sequenced fence family BK-39+40+42+43+44+45+BK-50 = 53 passed; xv6-nano 18p/2s. Numbers structural, rule-1 floors do not attach.
- NOT proved / open: walk_ld's symmetric MMIO READ branch (:361-363) stays unmode-gated (config-READ channel, source-read disclosed; candidate research item, no measured defect); no live-kernel twin workload (xv6-nano is oracle-side; L3 is the over-confinement guard); paged-path MMIO composition not re-probed (BK-66 owns the paged consult, green). Backlog rows citing "BK-50 open" as prereq (BK-55/56/57 lines) are now stale at the walk_st write door.
- Next tick: BK-46/47 (shell-native dynamic seed block, _COMMON missing — same file family, experiments/ blast radius) per backlog row order, or a new CLAIM QUEUE item / binding RULING first.

STATUS: ACTIVE

### 2026-10-01 ~03:1x CDT — BK-45 LANDED (VFS-dest fence legs, tests-only; step 7 / closing row of the sequenced fence commit): the VFS-attached device legs BK-40 never ran are landed and green — the VFS reroute arms (0x03/0x04/0x13 with a GlyphVfs attached) are fenced by BK-40's landed dispatch-site consult, proven on the VFS path itself (builder af3e62239ce2, this commit; picked at HEAD 86d2cdc3 == monitor fingerprint, tracked dirty set verified = pre-existing monitor-fix files, mailbox rule clean, newest RULING mtime 09-29 09:35 < HEAD, ledger STATUS ACTIVE, CLAIM QUEUE empty):

- NO ENGINE CHANGE: BK-40's dest consult (glyph_isa_v2.py SYSCALL arm dest_specs + _bk42_path_fault) runs BEFORE _handle_syscall regardless of VFS attachment, so the VFS reroute arms (0x03 :2081-2091, 0x04 :2141-2152, 0x13 :2397-2409) were already covered at the dispatch site — the row's fix shape ("same dest-loop consult as BK-40, VFS arms included in the same sequenced engine commit") is satisfied BY the BK-40 landing; this gate supplies the missing legs. Engine md5 8dd8ce806e07249b570d2539a1260612 byte-identical x2 (tools + glyph_dispatch mirror).
- RED-first evidence: the row's RED shapes were MEASURED at HEAD 4b0bb0c1 (probe_vfs_fence_af3e, results md5 c1ac611a712160654dfddd7ed4be27ee) — 0x04 VFS read dest=168 rc 2 'VW' landed clean; 0x13 listing dest=168 rc 4 listing landed clean. Probe re-run on the current tree shows the FIXED shapes (fault 672 = 168*4, nothing lands; record .builder_queue/red_bk45_af3e.py); its vfslist legs additionally fault at 800 = STAGING PARALLEL_ST trapped by the landed BK-39 fence (probe predates the fence — harness-shape drift, not containment regression).
- Gate tests/test_bk45_vfs_fence.py 7/7 GREEN (2 runs; every leg spawns a real GlyphVfs + vfs_shared=True on the item-29 spawn(tile=(5,0,8,8)) harness): L1 0x04 VFS dest out-of-tile refused (fault 672, syscall_dest_fence, syscall rc word 0, mode→SUPER); L2 0x13 VFS dest out-of-tile refused; L3 in-tile VFS roundtrip write/read/list stays green (DECLARED-window: listing declares max 8 = one full in-tile run 192..199 — the first draft declared 64 and the landed consult correctly refused it, caught by the leg's own run); L4 '..' refusals stay rc -1 via _guest_rel with the fence live (never weaken a live guard); L5 host-shaped '/bk45h' stages INSIDE the image, host file absent; L6 non-vacuity — consult instance-shadowed → L1's shape lands 'VW' rc 2 clean again (the landed consult is the refusal, not the VFS layer; engine md5-pinned before/after); L7 family subprocess BK-40+BK-42+item-25.
- HARNESS DEFECTS caught by the legs' own runs, receipted in test docstrings + RECEIPT_BK45_vfs_dest_fence.md: (1) the staging overlay lives on the GlyphVfs OBJECT (per-object tempdir), not the PNG — a fresh GlyphVfs per syscall made staged writes invisible to their own read-back ('file not found', L3 caught it; fixed with a module-level per-worker cached GlyphVfs); (2) declared-window 64 crosses the Hilbert-scattered tile at word 200 — lawful declared max is 8; (3) '/tmp/bk45_host' staging run crossed word 168 → BK-39 trapped the STAGING store (the BK-42 masking shape) — path shortened to '/bk45h'.
- Family on the committed tree: BK-45 7/7 ×2; fence family BK-38..44 50/50; item-25 VFS + file-io + app-echo + defect-D + item-29 54/54; xv6-nano 13/13; engine mirror md5 parity x2. WGSL twin UNTOUCHED (oracle-Python-only syscall handlers, BK-40/44 precedent). Numbers structural, rule-1 floors do not attach.
- NOT proved / open: no NEW engine consult authored (none needed — site is BK-40's landed consult, proven by L6); 0x03 VFS SOURCE window rides _bk42_source_fault attachment-agnostically but has no dedicated VFS-0x03-source leg (candidate research item, no measured defect); 0x01 WRITE / 0x08/0x09 AUDIO windows separate class; BK-50 twin door posture = the last open fence-family item. With BK-45 closed, the sequenced fence commit's row list (BK-39..45) is COMPLETE on the oracle side.
- Next tick: BK-50 twin door posture row or the fence-family endgame per row order, unless a new CLAIM QUEUE item or binding RULING appears first.

STATUS: ACTIVE

### 2026-10-01 ~00:4x CDT — BK-44 LANDED (FS-allow posture guard, step 6 of the sequenced fence commit): the 0x03 FILE_WRITE and 0x04 FILE_READ HOST arms now consult GLYPH_FS_ALLOW roots — the measured attack-surface inversion BK-15's rationale forbade is fixed in place (builder af3e62239ce2, commit f3582b11 via branch bk44/fs-allow on the REUSED bk40-syscall worktree, merged fast-forward to mainline; picked at HEAD 07eefcc2 == monitor fingerprint, tracked dirty set verified = pre-existing monitor-fix files, mailbox rule clean, newest RULING mtime 09-29 09:08 < HEAD, ledger STATUS ACTIVE, CLAIM QUEUE empty — this was in-flight work from the prior session: engine fix + gate + probe drafted, found RED-leg-defective, completed and landed per the finish-in-flight rule):

- Fix (tools/glyph_isa_v2.py + glyph_dispatch mirror, md5 8dd8ce806e07249b570d2539a1260612 x2): the 0x03 and 0x04 host arms realpath-check the path against _get_fs_allow_roots() (deny-by-default, rc -1 refusal) — exactly the 0x13 arm's landed BK-15 check; placed AFTER the item-25 VFS reroute so VFS-attached writes/reads keep the VFS's own containment. No new dispatch-site consult: handler-posture parity, not a fence term (BK-39/40/42/43 consults untouched). 0x07/0x12 keep GLYPH_RUN_ALLOW; 0x08/0x09 AUDIO + 0x01 WRITE out of scope per the row.
- Gate tests/test_bk44_fs_allow_roots.py 7/7 GREEN. RED-first at landing time (engine stashed): L1 fails (b'WX' lands, rc 0 clean), L2 fails ('AUTUMN' lands, rc 6), L6 passes pre-fix by construction (consult absent == neutered, md5-pinned); fix -> 7/7. Probe .builder_queue/probe_bk44_red_af3e.py (md5 7a268057e72bd67f7f00e8d9f301dc09, measured at HEAD 07eefcc2) committed.
- GATE/TEST DEFECTS caught and fixed this session: (1) the in-flight BK-44 RED probe predated the landed BK-39/40/42 fences — its word-168 staging was trapped before any syscall verdict; re-filed with current geometry (staging run 192..199, dest run 224..231) per the row's own note. (2) test_defect_d_ram_scoped_handlers.py's 0x03 historical-leg anchor was STALE — it predated both the item-25 VFS reroute block and this landing's root check ('anchor stale' on first run); re-synced to the full live handler body (path line + VFS reroute + DEFECT-D comment + BK-44 check + data lines) and the suite got a per-test tmp_path autouse GLYPH_FS_ALLOW fixture — migrated, never weakened. (3) Same fixture migration for test_glyph_app_echo.py (autouse), test_glyph_file_io.py (try/finally), test_item25_vfs.py (fixture), test_bk42_fw_exfil_fence.py L4/L6 (/tmp arming). (4) experiments/glyph_l1_shell.py _stamp_path arms the session root via the shell's existing _arm_fs_allow — the single choke point all file verbs stamp through; append-only.
- Family on the committed tree: BK-44 7/7 + BK-15 + BK-38..43 + item-25 VFS + file-io + app-echo + defect_d = 111/111 combined substantive run; item-26..36 migration chain 9 suites all green post-commit incl. every test_n1 engine-byte guard (RED-by-design pre-commit per the BK-76/40/41/42/43 precedent, green at f3582b11); xv6-nano 13/13; pre-commit hook at landing: differential 38/38 + Pillar 2.3 parity 8/8. WGSL twin UNTOUCHED (0x03/0x04 honest no-op stubs pinned by test_defect_d). Numbers structural, rule-1 floors do not attach.
- NOT proved / open: BK-45 VFS reroute dests (next row); 0x01 WRITE + 0x08/0x09 AUDIO windows (separate class); VFS-attached legs (item-25's own gate owns those); symlink-escape/TOCTOU beyond realpath (single-threaded handler, out of scope); allowlist CONTENT policy beyond deny-by-default (operator chooses roots; the gate pins the mechanism only).
- Next tick: BK-45 (VFS reroute dests) per the row order, unless a new CLAIM QUEUE item or binding RULING appears first.

STATUS: ACTIVE

### 2026-09-30 ~23:5x CDT — BK-43 LANDED (RUN path/argv fence guard, step 5 of the sequenced fence commit): 0x12 RUN2's ARGV windows are fenced and the probe's path-smuggle shape is confirmed dead under BK-42's landed consult (builder af3e62239ce2, commit 359711b9 via branch bk43/run-path on the REUSED bk40-syscall worktree — disk constraint precedent, merged fast-forward to mainline; picked at HEAD aadfd35a == monitor fingerprint, tracked dirty set verified = pre-existing monitor-fix files, mailbox rule clean, newest RULING mtime 09-29 09:08 < HEAD 23:18, ledger STATUS ACTIVE, CLAIM QUEUE empty):

- Fix (tools/glyph_isa_v2.py + glyph_dispatch mirror, md5 c679537e8c6a668048671fbcb806d38d x2): GlyphCPUv2._bk43_argv_fault(arg_addr) — 0x12 RUN2's argv windows (r2=arg1_addr, r3=arg2_addr) consulted at the SYSCALL dispatch site BEFORE the handler runs, delegating to _bk42_path_fault (now tag-parametrized; default 'path_decode_fence' byte-identical) with tag `argv_decode_fence`; addr==0 admitted. Refusal = landed E-K1 tail via _stack_fence_fault: handler never runs, out-of-tile RAM can no longer cross execve() as ARGV. PATH target (r1) already fenced by BK-42 — L1 pins it (allowlist worst-case).
- Gate tests/test_bk43_run_path_fence.py 7/7 GREEN. RED-first at landing (fix absent, /tmp/bk43_red3.log md5 7d8b27f2bc4b55c4a434596834e7be94, exit 1): L2 rc=0 clean, '[SYSCALL] RUN2: executed /tmp/r5 (1 args), exit code 0' — the exact measured defect; 1 failed / 6 passed. Fix -> 7/7.
- GATE-DRAFT DEFECTS (receipted in the test docstring): ARG staging at word 200 OUT of tile -> moved to run 224..231; 50-instr program = 7-row image and the PARALLEL_ST write-through mirror maps staging word 192 to image row 6, CLOBBERING SYSCALL/HALT slots 48..55 (opcode-None halt at (0,6) pre-syscall) -> program cut to 47 instrs; L4 rd is SIGNED -1; runner needed a shebang.
- Family on the committed tree: BK-43 7/7 + fence family BK-39 11/11 + BK-40 8/8 + BK-41 10/10 + BK-42 7/7 + BK-48-twin 6/6 + BK-49 7/7 + invariants 3/3 (58p/1f pre-commit; the 1 = item-29 test_n1 HEAD-pinned drift guard, RED BY DESIGN pre-commit per BK-76/40/41/42 precedent; post-commit item29+BK43 17/17); xv6-nano 13/13; xv6-boot 5p/2s; pre-commit differential 38/38 + Pillar 2.3 parity 8/8 at commit. WGSL twin UNTOUCHED (syscall handlers oracle-Python-only). Numbers structural, rule-1 floors do not attach.
- NOT proved / open: BK-44 FS-allow posture, BK-45 VFS reroute dests (argv consult covers VFS arms structurally), VFS-attached device legs, 0x01 WRITE / 0x08/0x09 AUDIO windows (separate class), BK-50 twin door posture, allowlist content beyond deny-by-default.
- Next tick: BK-44 (FS-allow posture guard — extend GLYPH_FS_ALLOW root check to 0x03/0x04) or BK-45 per the row order, unless a new CLAIM QUEUE item or binding RULING appears first.

STATUS: ACTIVE

### 2026-09-30 ~23:2x CDT — BK-42 LANDED (FILE_WRITE exfil + path-decoder fence guard, step 4 of the sequenced fence commit): 0x03 FILE_WRITE's data SOURCE window and the shared _read_path decode are fenced — a tiled USER task can no longer exfil guest RAM to an arbitrary host path, and an unterminated path can no longer decode across the tile boundary (builder af3e62239ce2, commit bf60a51f via branch bk42/path-fence on the REUSED bk40-syscall worktree — disk constraint, see below — merged fast-forward to mainline; picked at HEAD 2a203221 == monitor fingerprint, tracked dirty set verified = pre-existing monitor-fix files, mailbox rule clean, newest RULING mtime 09-29 09:08 < HEAD 22:55, ledger STATUS ACTIVE, CLAIM QUEUE empty):

- Fix (tools/glyph_isa_v2.py + glyph_dispatch mirror, md5 d7549493447084b6047078d06df828b4 x2): GlyphCPUv2._bk42_source_fault(src, length, kind) — word-granular DATA SOURCE window scan for 0x03 FILE_WRITE (handler reads self.memory[src+i], one byte per word — BK-40's dest convention), consulted at the SYSCALL dispatch site BEFORE the handler runs; GlyphCPUv2._bk42_path_fault(path_addr) — walks the path decode EXACTLY as _read_path will (same FS-pixel alias arm admitted, same past-RAM break, same 4096 ceiling) and refuses at the first out-of-fence word, covering _BK42_PATH_SYSCALLS = 0x03/0x04/0x07/0x08/0x09/0x12/0x13. Refusal = the landed E-K1 tail via _stack_fence_fault: handler never executes, no host file created or touched. Reason tags `syscall_source_fence:<kind>` / `path_decode_fence`. Term set identical to every landed consult: USER + _tile_confinement + _iso_enabled + _addr_in_box; SUPER (E-K2 dispatch) and unfenced tasks untouched. General LD stays governed by RULING_BK38_READ_POSTURE (cooperative read-shared model) — syscall ARGUMENT windows only.
- Gate tests/test_bk42_fw_exfil_fence.py 7/7 GREEN. RED-first at landing (unfixed tree, /tmp/bk42_red.log md5 74d14df5b755ecbc3877c09a9b3af05a, exit 1): L1 rc=0 clean, '[SYSCALL] FILE_WRITE: 2 bytes from addr 168 to path at 193' (exfil landed); L3 rc=0 clean, path decode crossed into out-of-tile words 200..202 (the measured pre-fix channel); 2 failed / 5 passed (L2/L4/L5/L6/L7 green = harness live, consults absent). Fix applied -> 7/7.
- GATE-DRAFT DEFECTS caught by the gate's own legs pre-evidence, receipted in the test docstring: (1) FIXTURE GEOMETRY — the GO-2 tile (5,0,8,8) fence term is Hilbert-scattered: in-tile contiguous runs are (160..167),(192..199),(224..231),(256..263)... (probe .builder_queue/probe_bk42_geom_af3e.py, live _addr_in_box); the first-draft staging at word 200 was OUT of tile and the landed BK-39 fence trapped the STAGING PARALLEL_ST (fault_addr=800), masking the syscall verdict — L4's in-tile control failing exposed it; all staging moved to run (192..199). (2) A first-draft 16-char path staged from word 196 crossed the run boundary at 200 — same masking shape; paths shortened to 6 chars + NUL at word 199.
- DISK CONSTRAINT (operations note): /home at 99% (21G free), each full worktree ~25G (large binary fixtures) — `git worktree add` for a fresh bk42 worktree died ENOSPC (partial checkout cleaned, branch deleted, worktree pruned). Landed instead on the REUSED bk40-syscall worktree: untracked leftovers removed, branch re-pointed `git switch -c bk42/path-fence 2a203221` — same worktree-isolation guarantee (engine changes isolated from mainline until gate-green), zero new disk. Worktree cleanup/merge-back decision for bk42/path-fence vs re-pointing again next rung: next session's call.
- Family on the committed tree: BK-42 7/7; fence family BK-40 8/8 + BK-41 10/10 + BK-39 11/11 + BK-76 8/8 + BK-76-twin + BK-48-twin 6/6 + BK-49 7/7 + BK-66 7/7 + invariants 3/3 (47 passed combined substantive run); xv6-nano 13/13 + 18p/2s boot regression; item-29 10/10 post-landing (test_n1 drift guard RED by design pre-commit, green at bf60a51f — BK-76/BK-40/BK-41 precedent); pre-commit Pillar 2.3 parity 8/8 + transpiler differential suites green at commit (engine file touched, hook ran). WGSL twin UNTOUCHED (syscall handlers oracle-Python-only, no twin surface — BK-40 precedent). Numbers structural, rule-1 floors do not attach.
- NOT proved / open: BK-43 RUN path/argv legs beyond the shared path-decode consult landed here (the consult already blocks the decode-cross channel BK-43's L1 rides; its allowlist-smuggle gate re-files under its own row); VFS-attached FILE_WRITE/FILE_READ legs (no VFS device in this harness; consult covers the VFS arms structurally at the dispatch site); 0x01 WRITE output window + 0x08/0x09 AUDIO windows (separate class); BK-44 FS-allow posture + BK-45 VFS reroute dests open rows; BK-50 twin door posture unchanged; live-kernel coverage = the 13-scenario xv6-nano suite.
- Next tick: BK-43 (RUN path/argv gate — mostly pre-blocked by this landing's consult; verify L1/L2 shapes then re-file its gate) or BK-44/45 per the row order, unless a new CLAIM QUEUE item or binding RULING appears first.

STATUS: ACTIVE

### 2026-09-30 ~23:0x CDT — BK-40 LANDED (syscall-layer fence guard, step 3 of the sequenced fence commit): the DATA handlers' dest windows are fenced — a tiled USER task's 0x02 READ / 0x04 FILE_READ / 0x13 FILE_LIST / 0x11 STORE_CODE now REFUSE when the declared dest window crosses the fence (builder af3e62239ce2, commit ac80cc10 in worktree bk40-syscall, merged fast-forward to mainline; picked at HEAD 3e4fc75a == monitor fingerprint, tracked dirty set verified = pre-existing monitor-fix files, mailbox rule clean, newest RULING mtime 09-29 09:08 < HEAD 22:22, ledger STATUS ACTIVE, CLAIM QUEUE empty):

- Fix (tools/glyph_isa_v2.py + glyph_dispatch mirror, md5 a3685c39634957a4200411ec1a63e797 x2): GlyphCPUv2._bk40_dest_fault(dest, length, kind) — word-granular window scan (ALL four handlers write self.memory[dest+i], one byte per word; first draft assumed byte-granular, faulted word 42, caught by the gate's fault_addr leg) consulted at the SYSCALL dispatch site BEFORE the handler runs, per-handler window from the register file (0x02 (r1,r2), 0x04 (r2,r3), 0x13 (r2,r3), 0x11 (r1,r3 image plane)). Refusal = the landed E-K1 tail via _stack_fence_fault: handler never executes, nothing lands. Term set = USER + _tile_confinement + _iso_enabled + _addr_in_box; SUPER + unfenced untouched. POSTURE (declared-window, documented): consult judges the DECLARED count (r3), not actual bytes — actual length is host-data-dependent, unknowable pre-handler; over-confinement bites only oversized declared windows, which IS the attack shape. _read_path deliberately untouched (BK-42/43's row).
- Gate tests/test_bk40_syscall_fence.py 8/8 GREEN. RED-first at landing (unfixed tree, /tmp/bk40_red.log md5 8743c24636a8b45cfe635bbf0f252d76): L1..L4 4 failed / 2 passed with the exact probe shapes (READ 2/2 bytes to addr 168 clean, rc=0, faulted=False; store_code pixel (65,66,67) landed out-of-tile); controls L5/L6 green (harness live); fix -> 8/8.
- Gate-draft defects caught by the gate's own legs pre-evidence, receipted in docstrings: (1) L2 passed VACUOUSLY — the 22-byte staged path crossed the tile boundary and the landed BK-39 fence trapped the STAGING PARALLEL_ST, not the syscall (L5's control failing exposed it; fixed to short in-tile path); (2) FR_IN_DEST=176 mislabeled in-tile — 176=(5,16) is OUT (cols 0-7), fixed to 162; (3) dbg bare step() loop without cpu.running=True (BK-52 lesson re-bitten; switched to table.wait()).
- Family on the committed tree: BK-40 8/8 + fence family 59/59 (BK-76 8, BK-39 11, BK-48-twin 6, BK-66 7 + invariants 3, BK-49 7, BK-62/63 twin 9); xv6-nano 13/13; xv6-boot 5p/2s; item-29 10/10 post-landing (test_n1 drift guard RED by design pre-commit, green at ac80cc10); pre-commit differential 38/38 + Pillar 2.3 parity 8/8 at landing. WGSL twin UNTOUCHED (syscall handlers are oracle-Python-only — no twin surface). Numbers structural, rule-1 floors do not attach.
- NOT proved / open: BK-42/43 _read_path out-of-tile decode, BK-44 FS-allow posture, BK-45 VFS reroute dests (consult covers VFS arms structurally at the dispatch site; no VFS-attached device leg ran), BK-50 twin door posture; live-kernel coverage = the 13-scenario xv6-nano suite.
- Next tick: BK-42 (FILE_WRITE exfil + the shared _read_path decoder fence — the sequenced commit's step 4) or BK-44/45 per the row order, unless a new CLAIM QUEUE item or binding RULING appears first.

STATUS: ACTIVE

### 2026-09-30 ~22:2x CDT — BK-41 LANDED (kernel-write-only BOX_MMIO CONFIG block): the directive's two surviving guest-mutable arms — the :968 SUPER MMIO-window exemption ST site and the SUPER post-USER PARALLEL_ST arm — now refuse stores to the guest-defeatable config words (builder af3e62239ce2, commit 65c1c46b in worktree bk41/config-block, merged fast-forward to mainline; picked at HEAD 0f8d904e == monitor fingerprint, tracked dirty set verified = pre-existing in-flight monitor-fix files + linked-worktree dirt, mailbox rule clean, ledger STATUS ACTIVE, CLAIM QUEUE empty, R1.4 CLOSED):

- Claim finished IN-FLIGHT work, not new scope: worktrees/bk41-config carried the
  engine fix + gate drafted by the 13:19 session (DIRTY_ACTIVE fingerprint led
  here); completed it per the finish-in-flight rule. Engine (tools/glyph_isa_v2.py
  + glyph_dispatch mirror, md5 f5c581e1… ×2): `_BK41_LOCKED_WORDS` = KFAULT_PC
  8193, KSYS_PC 8194, BOX0/1/2_LO+HI, KTICK_PC 8207, TIMER_COUNT 8208,
  TIMER_RELOAD 8209; consults gated on the landed BK-76 ever_user latch + SUPER +
  _tile_confinement. MEASURED SCOPE AMENDMENT (directive rule 4, xv6-nano
  oracle): MODE_LATCH 8192 + TILE words 8280..8283 EXCLUDED — S6/S11 lawfully
  re-arm them post-USER every context switch; SYS_A0/A1 + INPUT ring stay
  guest-writable (BK-76 §0).
- Gate tests/test_bk41_ksys_fence.py 10/10 GREEN. RED-first at landing (engine
  stashed): L7a/L7b "sentinel 4242 LANDED at TIMER_COUNT" (exit 0, faulted=False,
  the exact pre-fix shapes); stash pop → 10/10.
- L5 GATE-DEFECT, caught by the leg's own run, receipted in BK41_DESIGN_NOTES.md
  GATE ROT-CHECK: the BK-76 EX-L5 neuter style (early-return inside the refusal
  body) is structurally DEAD here — both consult sites own an unconditional
  `return False` after the refuse call, so a no-op'd refusal still drops the
  store and freezes PC (dbg_l5_af3e: ~460 refuse-fire replays/500 steps, sentinel
  unreachable, fails on EVERY tree). BK-76's EX-L5 never hit this only because
  its hand-built CPU (arm_tile, no spawn) never sets _tile_confinement — the
  style was never stress-tested against a live consult. Landed L5 neuters the
  CONDITION (empty _BK41_LOCKED_WORDS in a TEMP-COPY module; BK-76's vector lock
  asserted surviving) and reproduces the pre-fix shape exactly (dbg_l5c_af3e:
  steps=6, tcount=4242, clean exit). LESSON: a non-vacuity neuter removes what
  the consult TESTS, not what it DOES, when the site drops the op
  unconditionally.
- Family on the committed tree: BK-41 10/10, BK-76 8/8, BK-39 11/11, BK-48-twin
  6/6, BK-66 7/7 + invariants 3/3, xv6-nano 13/13, xv6-boot 5p/2s, item-29
  10/10 post-landing (test_n1 drift guard RED by design pre-commit, green at
  65c1c46b — the BK-76 landing precedent), pre-commit differential 38/38 +
  Pillar 2.3 parity 8/8 at commit. WGSL twin UNTOUCHED (config-block twin parity
  = separate sequenced-commit scope). Numbers structural, rule-1 floors do not
  attach.
- NOT proved / open: BK-40 syscall DATA-handler dest loops (own row, RED shapes
  measured there), BK-42/43 _read_path, BK-45 VFS dests, BK-50 twin door
  posture; live-kernel coverage = the 13-scenario xv6-nano suite (S6/S11
  instrumentation was probe-round, pre-landing).
- Next tick: BK-40 (syscall dest-loop fence — the directive's named step 3) or
  the fence endgame rows per the sequenced-commit order, unless a new CLAIM
  QUEUE item or binding RULING appears first.

STATUS: ACTIVE

### 2026-09-29 ~09:4x CDT — BK-39 STEP 1 OF THE SEQUENCED FENCE COMMIT LANDED (oracle engine): PARALLEL_ST/PARALLEL_LD + PUSH/POP/CALL/RET/CALLR now consult the E-K1 fence — the fifth consult surface, oracle parity with the landed twin (BK-49 stack_fence_fault / BK-51 tile term); commit 90c9f645 (builder af3e62239ce2)

- Claim re-verified, not assumed: HEAD 1d46a82d == monitor fingerprint,
  tracked tree clean at claim, mailbox rule clean (newest RULING mtime
  09:08 < HEAD commit 09:26), ledger STATUS ACTIVE, CLAIM QUEUE empty,
  R1.4 CLOSED. Open front = the sequenced fence commit's ORACLE side
  (the twin's BK-48/49/51/66/76 legs are landed; tools/glyph_isa_v2.py
  still consulted the fence at exactly one site, the scalar ST arm).
  Picked BK-39 step 1: the guest-reachable write/read arms the probes
  convicted (probe_pst_fence_af3e bf6f2b6e, probe_wgsl_stack_fence_af3e
  8f5f2e47).
- RED-first at 1d46a82d: tests/test_bk39_write_fence.py 5 failed / 6
  passed — L1 PARALLEL_ST landed out-of-tile clean; L2 BOX0 self-grant
  re-armed the box and word 999 took the store; L4 PARALLEL_LD returned
  the canary + in-tile exfil delivered; L5a/b PUSH/POP clean out-of-box.
- Fix: GlyphCPUv2._stack_fence_fault (the _paged_paddr_fence_fault
  contract: fault_addr=word<<2, packed fault_pc, mode->SUPER, KFAULT_PC
  vector, kf==0 stop, vec|None) consulted PER-OP at the dispatch arms
  (NOT inside _mem_write/_mem_read — BK-66 owns the paged path; twin
  posture): PUSH/CALL/CALLR pre-decrement word, POP/RET stack word,
  BEFORE mutation; PARALLEL_ST/PARALLEL_LD judge the first out-of-fence
  in-range word, refuse the whole op. Term = the same _addr_in_box the
  ST arm uses; USER + _tile_confinement + iso_enabled only — SUPER
  exempt, legacy images inert (_iso_enabled guard added to
  _addr_in_box). RULING_BK38_READ_POSTURE clause 1 intact: general
  non-tile USER arms stay unfenced (cooperative model).
- BRING-UP DEFECT, caught by the repo's own pre-commit differential
  gate (not by my gate — lesson logged): first cut gated post-consult
  execution on `not self.faulted`; faulted LATCHES after a handled
  fault, so a kernel that recovered from E-K1 and later ran any stack
  op took the kf==0 stop branch with running still True — step()
  returned False mid-program, 6 xv6-nano scenarios (s6/s7/s8/GO-1x2/
  GO-5) died "failed to halt cleanly". Discriminator corrected to
  self.running (the helper clears it ONLY on the kf==0 stop).
- GREEN post-fix, on the committed tree (90c9f645): BK-39 gate 11/11
  (incl. L6 non-vacuity: consults neutered -> the L1 shape returns;
  L7 mirror-md5), glyph_dispatch mirror byte-identical, xv6-nano
  32/32 + boot regression 18p/2s, family BK-48/76/52/38 25/25,
  BK-66 7/7, item-29 10/10, item-30 8/8, item-31 10/10, item-32/33
  16/16, item-34 10/10, item-35 8/8, item-36 8/8, GH-9 13p/1s,
  parallel opcodes 3/3. item-30/31/32's N1/gate_unchanged chain-guard
  legs were RED pre-commit BY DESIGN (on-disk engine vs HEAD blob) and
  went green exactly at the commit — the RED-then-GREEN pair is the
  receipt.
- NOT proved / open: this is step 1, NOT the whole sequenced commit —
  BK-40 (syscall handler dest loops), BK-41 (kernel-write-only BOX_MMIO
  config block + BK-50 door posture), BK-42/43 (_read_path/FILE_WRITE/
  RUN argv), BK-45 (VFS reroute dests) remain OPEN. WGSL device re-run
  not needed (shader untouched; twin landed earlier). PUSH consult
  judges the post-decrement slot (twin-disclosed design choice). The
  BK-50 disarm-chain shape is NOT yet closed on the oracle (word 8196
  is still guest-ST-able through the plain ST arm once inside a
  granted box — BK-41's block, next step). Numbers structural, rule-1
  floors do not attach. Next tick: BK-41 (kernel-write-only config
  block) — the last big posture decision in the fence family.

- Run selection re-verified, not assumed: HEAD 965b691b (my map-regen
  commit — the previous tick 56013cc0 landed the BK-76 clause-4 TWIN
  parity + its map cell), tracked tree clean at claim, mailbox rule
  clean (newest .builder_queue/RULING_*.md mtime 2026-09-29 09:08 <
  HEAD commit time 09:13), monitor CLEAN/queue=0/stall_tier=0, CLAIM
  QUEUE empty, R1.4 CLOSED. Phase 1c research eligible; no re-research
  (the SYSCALL-path coverage question exists in no RESEARCH_*.md or
  backlog row — it lives only in RECEIPT_BK76_twin_exemption_refusal.md's
  "NOT proved" tail as a structural pin).
- Question: BK-76-twin's refusal guards the ST dispatch arm above
  walk_st; does the lock cover the FULL SYSCALL-into-SUPER mechanism —
  specifically the KFAULT_PC site, which the landing receipt pinned
  STRUCTURALLY (same term set) with no device leg?
- Method: the gate's own run_leg harness unchanged (run_wgsl real
  buffers + build_shader(OpcodeMapV2()), seeded mode=1, tile
  (5,0,8,8), KSYS armed (0<<16)|3, kf=0), DISPATCHER_TEXT program, only
  the target word varied. Probe .builder_queue/afford_syscall_path_af3e.py
  (kept). SINGLE-RUN affordance check — explicitly not a pinned gate.
- Findings (measured on-device, RTX 5090 wgpu): H1a sanity leg = TW-L1
  reproduced exactly (steps 4, word 8194==3, fault 32776, no PRT);
  **H2: handler ST to KFAULT_PC REFUSED** — steps 4, word 8193==0
  (sentinel did NOT land), fault 32772 = 8193<<2, mode SUPER
  post-mortem, halted, no PRT. RESULTS_MD5
  91f423e2fd1c2b7d4916151f09b4a155. No new defect: the ever_user latch
  (set at the FIRST USER dispatch, before SYSCALL flips mode) covers
  the mechanism, not just the measured sites.
- Receipt: .builder_queue/RESEARCH_bk76_syscall_path_affordance.md.
  Numbers structural (device readback verdicts, no rates) — rule-1
  floors do not attach. Nothing landed; zero engine/shader/gate files
  touched (probe + research receipt + ledger only).
- NOT proved: tick-path (GH-16 KTICK) coverage — TW-L1b exercises the
  KTICK word from a SYSCALL handler, not a live tick; named in the
  receipt as the remaining unexercised vector-writing mechanism, with
  a candidate tick-driven device leg shape should a later round want
  belt-and-braces. Oracle-side KFAULT refusal not re-measured (EX-L1
  covers it; oracle gate green in TW-L6 family).
- Next tick: the ledger's standing options stand (BK-50 door posture
  row decided alongside BK-41's kernel-write-only config block — the
  last big posture decision in the fence family; or BK-49's oracle-side
  legs) unless a new CLAIM QUEUE item or binding RULING appears first.

### 2026-09-29 ~09:0x CDT — BK-76 CLAUSE-4 TWIN PARITY LANDED (WGSL twin): the twin's SUPER MMIO-window exemption hole is CLOSED with the same Option A no-vector refusal the oracle landed at ab758f1c (builder af3e62239ce2, this commit; the BK-76 landing's own "NOT proved: twin exemption parity" line, closed; picked at HEAD bc03807e, monitor CLEAN, queue=0):

- **RED-first at HEAD bc03807e (unfixed tree):** gate
  tests/test_bk76_exemption_refusal_twin.py failed TW-L1 with the measured
  pre-fix shape — **"sentinel 65537 LANDED at KSYS_PC through the SUPER
  window exemption"** (assert 65537 == 3), TW-L1b same at KTICK_PC,
  TW-L5 marker-absent; controls green (3 failed / 4 passed in 10.80s).
- **The fix (tools/wgsl_glyph_isa_v2.py, triple-synced):** (1)
  `bk76_ever_user` one-way latch in the WGSL SpatialCPU struct, set at
  dispatch top when the instruction starts USER on a tile-armed lane
  (TILE_H != 0 — the twin's documented _tile_confinement equivalent);
  boot-phase config pre-first-USER stays lawful. (2) ST-arm refusal
  BEFORE walk_st: ever_user ∧ SUPER ∧ tile-armed ∧ window ∧
  {8193, 8194, 8207} → store dropped, FAULT_ADDR=addr<<2, FAULT_PC
  packed, mode→SUPER, running=0, NO vector (tick-19 restart-loop
  immunity); vector-words-ONLY scope (ISO_SYS_A0 8205 / MODE_LATCH 8192
  / ISO_INPUT_CURSOR 8237 lawful — ruling invariant 2). (3)
  make_cpu_state_array 106 → 108 u32 (432 bytes; WGSL align-8 rounding
  measured live: 428-byte bind failed, trailing pad word fixed it).
  Triple-sync md5 c96ac0149289828574281ef78d20409a ×3; oracle
  glyph_isa_v2.py md5 bc422443730e6851a2a41f42376e8830 UNTOUCHED.
- **Gate GREEN: 7/7** (pytest 12.67s) + 2 pinned standalone runs
  byte-identical, RESULTS_MD5 290dfc7054c8205474d555c82e3ac632. TW-L1
  KSYS refused (word 3 unchanged, stop at step 4, FAULT_ADDR 32776, no
  PRT); TW-L1b KTICK refused (word 0 — ruling §0 per-site exercise);
  TW-L2 no-tile control lands + PRT 52 fires; TW-L3 SYS_A0 lands
  (scope); TW-L4 never-USER boot store lands (USER-history gating);
  TW-L5 non-vacuity (neutered TEMP-COPY → sentinel lands + PRT fires,
  real tree md5-pinned); TW-L6 family (BK-49 twin + BK-76 ORACLE gates
  green).
- **Family on this tree:** BK-49/51/48/62-63/66/52 + triple-sync 41/41
  (19.4s); BK-64 + 64red/65 + 66-invariants + verify_wgsl 12/12;
  BK-2 parity + DEFECT-18 + GH-16 + GH-18 + GH-6 + GH-7 + item-26
  43/43 (45.4s — the struct-growth consumers); item-5b + BK-2 4/4;
  ISA/shell regression 11/11. Disclosed pre-existing RED (reproduced on
  the stashed pre-fix tree, not ours): glyph_dispatch sqlite DB-path
  failures + tests.mock_ram collection errors.
- **NOT proved:** non-vector window words inside walk_st stay consult-
  free BY DESIGN (ruling invariant 2); walk_ld read-open unchanged
  (BK-48/56 posture); no live-kernel xv6-nano device run of the twin
  refusal (harness + family scope; a live surprise re-opens the
  ruling); KFAULT twin site pinned structurally (same term set as the
  measured KSYS/KTICK legs), no separate device leg.
  Receipt .builder_queue/RECEIPT_BK76_twin_exemption_refusal.md.
  Numbers structural, rule-1 floors do not attach.
- **Next tick:** BK-50 door posture row (walk_st/walk_ld MMIO branch
  mode-gating, decided alongside BK-41's kernel-write-only config
  block), or BK-49's oracle-side legs, or BK-52's L2/L3 twin legs —
  unless a new CLAIM QUEUE item or binding RULING appears first.

### 2026-09-29 ~08:4x CDT — BK-76 OPTION A NO-VECTOR REFUSAL LANDED (oracle engine): the :968 SUPER MMIO-window exemption survivor is CLOSED for the three dispatch vectors — a post-USER tile-confined SUPER store to KSYS_PC/KFAULT_PC/KTICK_PC through the exemption now refuses (store dropped, fault "mmio_exemption_refused", mode→SUPER, running=False, NO vector — tick-19 restart-loop immunity), implementing RULING_BK76_EXEMPTION_POSTURE.md §3 (builder af3e62239ce2, this commit; picked at HEAD 609deba8 — this was the in-flight un-landed engine change found dirty in-tree, finished per the finish-in-flight rule):

- **The fix (tools/glyph_isa_v2.py, +58):** `_bk76_ever_user` one-way latch set in step()
  when a USER instr executes on a tile-confined engine (boot/config-phase vector writes all
  happen pre-first-USER and stay lawful — GH-25 fault image, GH-16/GH-6 kernels, loader
  seeding untouched); `_BK76_LOCKED_WORDS` = {KFAULT_PC, KSYS_PC, KTICK_PC} >>2;
  `_bk76_exemption_refuse()` runs the ruling's exact invariant-1 tail; consult in the ST arm
  (:1089-1103) fires only on ever_user ∧ SUPER ∧ tile-confined ∧ window ∧ locked-word —
  xv6-nano ISO_SYS_A0 (8205) and all non-vector window words stay lawful per invariant 2.
- **Scope discipline:** all THREE WGSL copies byte-identical to HEAD (md5 4be6ff26… ×3) —
  the twin's exemption hole is OPEN, twin parity is separate sequenced-commit scope.
- **Gate: tests/test_bk76_exemption_refusal.py 8/8 GREEN** (pytest 8 passed in 0.08s +
  standalone exit 0), including EX-L8 KTICK-site measured leg (ruling §0's named
  extrapolation risk exercised, not assumed). RED-first at landing time (fix git-stashed):
  **5 failed / 3 passed** — EX-L1 FAILED with "OUTPUT: r5 = 52" (handler ran to PRT through
  the hijacked vector, the exact pre-fix landing shape), EX-L5/L6/L7/L8 FAILED,
  EX-L2/L3/L4 controls green (harness live); stash pop byte-identical (cmp-verified).
- **Family on this tree:** BK-66 + BK-66 invariants + BK-38 + BK-52 + BK-49 + BK-48 +
  BK-64 + BK-64red/BK-65 = 43/43 in 9.13s; ISA/syscall regression 61 passed, 2 failed —
  the 2 are item-29/34/35/36's `test_n1_engine_byte_unchanged` HEAD-pinned drift guards
  and their transitive subprocess chains, which fail BY DESIGN on any un-landed engine
  change; chain bottom verified: item-29 substantive legs 9/9 green, only the byte-guard's
  hash check fires. All behavioral legs in the cascade pass. The guards go green on landing.
- **NOT proved:** twin exemption parity; xv6-nano real-handler behavior (ruling §0 open);
  non-vector window words outside the three locked vectors (scope is vector-words-only by
  ruling); a live-kernel KTICK surprise re-opens the ruling rather than fitting it.
  Receipt .builder_queue/RECEIPT_BK76_exemption_refusal.md. Numbers structural, rule-1
  floors do not attach. Measured at HEAD 609deba8 pre-landing.
- **Next tick:** BK-50 door posture row, or the clause-4 MMIO-exemption twin parity leg,
  or BK-49's oracle-side legs — unless a new CLAIM QUEUE item or binding RULING appears first.

### 2026-09-29 ~05:0x CDT — BK-49 TWIN STACK-PATH FENCE LANDED: the WGSL twin's PUSH/POP/CALL/RET/CALLR arms now consult the E-K1 fence on the stack word they touch — the sequenced fence commit's fourth consult surface closed on-device (builder af3e62239ce2, this commit; ledger's named next-tick item, picked at HEAD b919a736):

- **The fix (tools/wgsl_glyph_isa_v2.py):** new `stack_fence_fault(sp_word,
  is_super)` (:600-628) — USER-only consult of the SAME addr_in_box term
  walk_st uses (boxes + GO-2 tile); SUPER exempt so kernel KJMP/entry stacks
  are untouched. Wired into all FIVE stack arms: PUSH/CALL/CALLR consult the
  LANDING word (r31-1) BEFORE the pre-decrement (a refused op mutates
  nothing, r31 stays); POP/RET consult the READ word (r31) BEFORE the read
  + increment (nothing delivered, sp unmoved). E-K1 tail = the exact landed
  shape (FAULT_ADDR = sp*4, FAULT_PC packed pixel PC, mode->SUPER,
  KFAULT_PC vector, kf==0 stop loudly — BK-52 guard shape).
- **Posture decision (row option 1, decided at the landing gate):** PER-OP
  consult, NOT a consult inside mem_write/mem_read — a shared-site consult
  would double-fence the paged frame arms (BK-66-twin's post-translation
  paddr consult already owns the paged path) and would change every
  non-stack caller's semantics. Triple-sync landed at md5
  4be6ff26a4f913864c8d7e722090f5f8 (all THREE WGSL copies); oracle
  glyph_isa_v2.py md5 bc422443730e6851a2a41f42376e8830 UNCHANGED — the
  ORACLE's stack arms stay open (separate sequenced-commit scope).
- **Gate: tests/test_bk49_stack_fence.py 7/7 GREEN** (pytest 7 passed in
  5.44s + standalone exit 0; 2 pinned GREEN runs byte-identical, stdout md5
  45fe3f2fa1afdb004cad9e3c97079f95). L1 out-of-box PUSH refused (nothing at
  word 499, r31 untouched 500, fault 1996=499*4, SUPER); L2 out-of-box POP
  refused (pre-painted canary NOT delivered, r31 untouched, fault 2000);
  L3 in-box PUSH lands + in-box POP returns (word 323 canary, r5 canary,
  r31 325, USER, fault 0 — lawful stack work preserved); L4 walk_st E-K1
  rot-guard green (fault 400 — no live guard weakened); L5 out-of-box CALL
  push refused at 1996 + in-box CALL/RET roundtrip output [9] green;
  L6 non-vacuity (TEMP-COPY neuter -> canary re-delivered at 499, real
  tree md5-pinned); L7 family subprocess (BK-48/BK-48-LD/BK-51/BK-38 green).
- **RED-first at landing time** (gate run against the UNFIXED tree, exit 1):
  L1 "out-of-box PUSH LANDED at image word 499 (0xadf00d)" fault 0; L2 "POP
  delivered the pre-painted canary into r5 (0xadf00d)"; L5 "CALL's
  return-address push not refused (fault 0, expected 1996)"; L3/L4 controls
  PASSED pre-fix (harness live). Gate-draft defect caught by the leg's own
  run pre-evidence: PROG_CALLRET_IN's CALL targeted instruction 4 (HALT)
  not 5 (the subroutine) — L5's output [] vs [9] exposed it; corrected
  before any number was claimed.
- **Family on this tree (single pytest run, all green):** BK-49 7/7 + BK-48
  6/6 + BK-51 5/5 + BK-38 6/6 + BK-64 6/6 + BK-64red/BK-65 HILB 3/3 + BK-66
  7/7 + ruling invariants 3/3 + GH-4 parity = 47 passed in 10.37s.
  Receipt .builder_queue/RECEIPT_BK49_stack_fence.md.
- **NOT proved:** the ORACLE's stack arms remain UNFENCED (engine md5
  unchanged by design — oracle side of BK-49 is separate sequenced-commit
  scope); BK-50's MMIO door untouched (USER can still clear TILE_H through
  the unmode-gated box_mmio branch — BK-41/50 posture decision); kernel
  entry stacks exercised only by SUPER-exemption reasoning + the L3 in-box
  control, not a real kernel image; no paged×stack composition leg (the
  twin's stack path is unpaged-only). Numbers structural, rule-1 floors do
  not attach. Measured at HEAD b919a736 pre-landing.
- **Next tick:** BK-49's oracle-side legs or the BK-50 door posture row
  (both sequenced-commit scope), or the clause-4 MMIO-exemption twin parity
  leg — unless a new CLAIM QUEUE item or binding RULING appears first.

### 2026-09-29 ~00:4x CDT — BK-62/63 TWIN FRAME-PATH LEGS LANDED: the WGSL paged walker's HILB + PIX frame arms measured consulting the GO-2 tile fence POST-TRANSLATION on-device — the BK-66-TWIN landing's named NOT-proved line item ("PTE_HILB twin arm not device-measured in-tile") CLOSED for BOTH frame modes (tests-only, no engine change; builder af3e62239ce2):

- **Gate: tests/test_bk62_bk63_hilb_pix_frame_fence_twin.py 9/9 GREEN**
  (pytest 9 passed in 3.51s + standalone exit 0; 2 pinned GREEN runs
  byte-identical, stdout md5 a6c2ee6ac81883ebed3367e2846126a2). HILB:
  in-tile LD lands clean USER (pfn 0x000 d=0 -> word 192, row 6 IN the
  (0,0,8,8) tile); out-of-tile LD refused with FAULT_ADDR = 5120 = 1280*4
  (the PADDR byte, oracle :777 parity), rd unwritten, mode->SUPER;
  out-of-tile ST refused, canary NOWHERE in the image plane. PIX
  siblings (pfn 0 vs pfn 5, same target words) identical shapes.
  L3 plain-arm parity: pfn-1 PTE maps IN-tile vaddr 100 -> OUT-of-tile
  paddr 356 -> refused at 1420 = 356*4 — a vaddr-side consult would have
  ADMITTED it: twin-side paddr-ness evidence (ruling clause 1).
- **RED-first at landing time** (.builder_queue/red_bk62_bk63_af3e.py,
  kept): paged_paddr_out_of_tile neutered in a TEMP-COPY module ->
  L1b/L1c's exact programs go RED (LD fault 0 + canary delivered; ST
  canary LANDS at image word 1280, mode USER) — the pre-fix walk shape
  reproduced under this gate's harness; the refusal legs are
  falsifiable. L4 non-vacuity leg does the same neuter in-gate (canary
  re-delivered, real tree md5-pinned f4c4e30b8836d1a039ff8370a7268a1a).
- **Harness deltas disclosed:** (1) img_seed — frame arms read the IMAGE
  plane, not ram; v1 of L1a seeded ram and read program text (0xec5050),
  caught by the leg's own run, fixed to an image-plane stamp at word
  192; (2) tile (0,0,8,8) admits lawful d=0 HILB frames (words 0..255)
  while word 1280 (d=5/PIX pfn 5) stays out; (3) L3's v1 shapes (vaddr
  500 = vpn-1 translation sentinel; identity vaddr 100 = in-tile, lands
  clause-3-correct) replaced by the pfn-1 shape, which doubles as
  paddr-vs-vaddr evidence. All wrong shapes caught by the legs' own
  verdicts before any number was claimed.
- **Family on this tree:** BK-48 twin gate 6/6 (subprocess, in-gate L5)
  + BK-64 6/6 + BK-64red/BK-65 HILB 3/3 + BK-66 oracle 7/7 + ruling
  invariants 3/3 + triple-sync 2/2 all green at this HEAD. All THREE
  WGSL copies md5 f4c4e30b8836d1a039ff8370a7268a1a before/after; oracle
  glyph_isa_v2.py md5 bc422443730e6851a2a41f42376e8830 unchanged.
- **NOT proved:** the twin is exercised via seeded box_mmio tile words
  (BK-48/BK-51 harness shape), not a spawn(tile=...) GPU posture (the
  twin has no process table); BK-62/BK-63 backlog rows stay
  Jericho-claimable — this gate is the twin legs those rows name, NOT a
  row close or promotion (the rows' oracle-side box-armed legs remain
  separate scope); BK-76 exemption posture still awaits Jericho's
  ruling; R1.4, BK-49, BK-50 untouched. Receipt
  .builder_queue/RECEIPT_BK62_63_twin_frame_fence.md. Numbers
  structural, rule-1 floors do not attach. Measured at HEAD 0f875164.

### 2026-09-29 ~00:3x CDT — BK-66-TWIN LANDED: the WGSL paged walker consults the GO-2 tile fence POST-TRANSLATION (`paged_paddr_out_of_tile`, bitwise mirror of `_physical_in_tile` glyph_isa_v2.py:751-768) in walk_ld AND walk_st, all three frame arms — the ledger's named open line item ("twin paged read fence") CLOSED, ruling 9714a363 clause 5 discharged on-device (builder af3e62239ce2, commit 7c4d791d):

- **The live defect, RED at HEAD 43bb59fb with the fix stashed** (probe
  .builder_queue/probe_bk66twin_red_af3e.py, force-added): a tile-armed USER
  task's paged store to translated out-of-tile paddr 100 LANDED clean USER on
  the GPU (ram[100]=0xadf00d, fault 0, mode stayed USER) while the oracle
  faults `paged_paddr_fence op=ST paddr=100` — engine divergence on the
  containment path; image-plane paged writes are instruction-stream class
  under GH-8b.
- **The fix** (found uncommitted in-tree at 43bb59fb, claimed + verified per
  the BK-64 precedent e0afc4f1, NOT re-authored): consult runs POST-
  TRANSLATION on the decoded frame word (HILB via hilb_frame_word / PIX /
  plain), never the vaddr (attacker owns the page table — BK-66 T1/T2);
  refusal records FAULT_ADDR = paddr<<2 (oracle :777 parity — the PHYSICAL
  byte the fence judged) and raises the module-private
  bk66_paddr_fault_pending handshake; the LD/ST dispatch sites run the exact
  E-K1 tail (FAULT_PC packed pixel PC, mode->SUPER, KFAULT_PC vector, kf==0
  stop loudly — BK-52 guard shape) WITHOUT overwriting FAULT_ADDR with the
  vaddr; LD's rd stays unwritten on refusal. Handshake cleared at main's top;
  race-free under single-lane single-step dispatch. All THREE WGSL copies
  synced md5 f4c4e30b8836d1a039ff8370a7268a1a.
- **Gate: tests/test_bk48_wgsl_ld_tile_fence.py 6/6 GREEN** (2 pinned runs
  byte-identical, stdout md5 68ba5257906f4c567a4b123e862a6193). RED-first at
  landing time: module stashed -> test_l2_cooperative_and_super_controls
  FAILED (`assert 0 == (164*4)` — paged LD landed clean, no fault) while
  BK-66's oracle gate + invariants stayed green (engine untouched); stash
  pop -> 6/6.
- **Gate change = ADD/upgraded posture, not a guard weakening:** BK-48's
  landed L2c encoded the INTERIM posture ("paged LD not consulted — open
  BK-66-twin line item"); it now pins the ruling posture: L2c-i identity-
  mapped OUT-of-tile paged LD refuses with FAULT_ADDR=paddr*4=656, r6
  refused, SUPER (this leg IS the stash-RED); L2c-iv lawful mapped IN-TILE
  paged LD lands clean USER (over-confinement guard, clause 3).
- **Draft defect disclosed pre-evidence:** first L2c rewrite expected paddr
  1444 (mis-shifted: 164>>8=0, not 5 — PTE pfn field) — caught by the leg's
  own run (fault 656 = the true identity paddr byte), corrected before any
  number was claimed. vaddr-vs-paddr FAULT_ADDR discrimination is oracle-
  side (test_bk66_paged_tile_fence.py L1/L7: vaddr 0x3000 -> paddr 1280,
  fault pins 5120), cross-referenced in the gate comment.
- **Family on this tree (all green):** BK-66 oracle 7/7 + ruling invariants
  3/3 + BK-64 6/6 + BK-64red/BK-65 HILB 3/3 + BK-51 5/5 + BK-38 6/6 +
  BK-52/GH-4/wgsl_validation 9/9 + triple-sync 2/2 = 41 passes; pre-commit
  hooks at landing: ISA/transpiler differential 38/38, Pillar 2.3 parity 8/8.
- **NOT proved:** PTE_HILB twin arm not device-measured in-tile (consult
  covers it by code path; BK-62/63 twin legs are the frame-path line items);
  the handshake is correct only under single-lane single-step dispatch
  (disclosed); the :968 MMIO-window exemption untouched (BK-76 refusal
  posture remains Jericho's design call); oracle engine byte-identical this
  session; R1.4 fleet convergence, BK-49 stack-path, BK-50 door posture all
  untouched. Receipt .builder_queue/RECEIPT_BK66_TWIN_paged_paddr_fence.md.
  Numbers structural, rule-1 floors do not attach. Measured at HEAD 43bb59fb.

### 2026-09-29 ~04:0x CDT — BK-66 RULING CLAUSE 2b/2c INVARIANT LEGS LANDED:
the two ruling legs the BK-66 landing named "not yet authored" now exist as
tests/test_bk66_ruling_invariants.py 3/3 (builder af3e62239ce2, commit
bb42d4d0) — ADD, don't swap, landing gate untouched:

- **T1 (clause 2b, cross-task PT-window exclusion):** task A (tile-armed,
  paged) maps a vaddr onto its OWN PT header paddr (1535) via a plain PTE
  and stores a canary → refused `paged_paddr_fence op=ST paddr=1535
  vaddr=0x17fc` (the fence gates the ACCESS — clause 2a, no implicit
  PT-window gap); task B on the SAME table (own image + PT window) runs
  lawful paged ST+LD clean USER exit 0, no leak into its header/PTE words.
- **T2 (clause 2c, header check over a WRITTEN header):** PT_TAG_WORD
  stamped 0xDEAD00 → next paged access faults `pt_tag_mismatch got=0xdead00`
  at fault_addr 32848; correct-tag control exits 0.
- **T3 (non-vacuity) + the gate's own RED-first defect, caught by rot-check
  pre-landing:** first draft's T3 used arm_tile WITHOUT setting
  `_tile_confinement` (spawn(tile=...) sets it; arm_tile alone does not) —
  the manual posture ran UNFENCED and the canary landed on the REAL engine
  (rotcheck run 1: faulted=False, word1535=0xadf00d), making T3 vacuous. The
  rot-check receipt (.builder_queue/rotcheck_bk66_invariants_af3e.py)
  reproduces both shapes: pre-fix RED (canary lands, real engine), post-fix
  the real engine refuses (`paddr=1535`, word1535=0) while the neutered
  TEMP-COPY module still lands the canary — the leg discriminates. Real
  engine md5 pinned before/after in T3.
- **Family on this tree:** BK-66 landing gate + this gate 10/10; fence
  family BK-38/48/51/52/64/64red-HILB 38/38; item-29 10/10 (32.4s — slow
  subprocess legs, not a hang); item-36 9/9; monitor hygiene 9/9.
- **NOT proved:** twin side (twin paged read fence stays the BK-66-twin
  open line item); the :968 exemption-site posture (BK-72/73/76 legs are
  exercisable but the refusal-posture decision — no-vector vs
  provenance-pinning, with BK-75 KFC-L6's restart-loop constraint — is
  design-judgment reserved to Jericho); BK-67/68 fetch-family rows are
  research-filed, not claimable without Jericho per backlog header rules.
- **Next tick:** remaining NOT-proved bullets per protocol — candidates:
  BK-49 twin stack-path fence (gate legs fully named in its row, blast
  radius wgsl_glyph_isa_v2.py), or the clause-4 MMIO-exemption twin parity
  leg, or next unauthored gate leg from the ruling-bound rows. No new rung
  invented.

STATUS: ACTIVE

### 2026-09-28 22:4x CDT — BK-48 LANDED: the WGSL twin's LD arm now consults the GO-2 tile fence (`ld_tile_fault`, bitwise mirror of the oracle's unpaged :995-1004 branch) — a tile-armed USER out-of-tile load TRAPS E-K1 on the GPU instead of reading any word; UNPAGED-only by construction (paged loads keep the BK-66-twin post-translation consult as an open line item — a vaddr-side consult there would over-confine, the BK-51 D3 shape on the read side); gate test draft itself caught holding the address in the wrong register — consult fired on word 0, a garbage-program trap, not a fence verdict (builder af3e62239ce2)

- **Rung selection:** tick woke on HEAD 72b728bb with the monitor flagging
  tracked_dirty=3 (DIRTY_ACTIVE) — verified the dirty set is THIS lane's own
  in-flight BK-48 work (3 WGSL copies, mtimes 21:55, one minute after the
  BK-51 commit landed) plus the exempt build-map channel; ledger STATUS
  ACTIVE, queue empty (QUEUE_STATE all landed incl. remedy-*), R1.4 checked
  FIRST — CLOSED; no RULING_*.md newer than HEAD. BK-48 is the ledger's own
  named next-tick item ("walk_ld's read-side fence"), so finishing the
  in-flight unit was the correct move — no new rung invented.
- **The gate's own defect, caught and receipted pre-evidence:** the draft
  test program was `LDI r6 <addr>` + `LD r6 r5` — but the assembler packs
  `LD rA rB` as rd=A/rs2=B (glyph_isa_v2.py:436-438) and the oracle reads
  the ADDRESS from rs2 (:883). Device trace (steps=2, mode->SUPER, r6=0,
  fault_addr=0): the consult fired on WORD 0 (out-of-tile, tile starts row
  5) — correct engine behavior for a garbage program, not a fence verdict.
  The pre-fix "RED shape" quoted in the draft docstrings (r5==canary landed)
  was derived from this mis-programmed shape and was never measured. Fixed:
  programs load the address into r5 (rs2 slot), read the result from r6;
  encoding note added to the gate's docstring.
- **Branch-structure parity defect caught in the shader itself:** the draft
  consult fired BEFORE the paged/unpaged fork — but the oracle's :995 tile
  elif only covers the UNPAGED branch (:885 paged loads fence via BK-66's
  post-translation `_physical_in_tile` on the decoded paddr; a vaddr-side
  check there is defeated by the attacker-owned page table, BK-66 T1/T2).
  An unconditional consult would over-confine a lawful out-of-tile-vaddr/
  in-tile-paddr load — the BK-51 D3 shape reborn on the read side. Fix:
  `pt_base != 0 -> return false` guard added (walk_st's consult lives in
  its unpaged branch, :507 twin structure). The twin's PAGED read fence
  (BK-66-twin) remains the open line item — disclosed, not silently
  absorbed.
- **Fix (tools/wgsl_glyph_isa_v2.py +43 lines total):** `ld_tile_fault`
  (:439-466 post-patch) + LD-arm consult (:665-695 post-patch) — SUPER
  exempt, TILE_H==0 inert, unpaged-only, word=addr row=word/32 col=word%32
  (W_MEM=32); refusal runs the EXACT E-K1 sequence the ST arm runs
  (FAULT_ADDR=addr<<2, FAULT_PC packed pixel PC, mode->SUPER, KFAULT_PC
  vector, kf==0 -> stop loudly — the BK-52 guard shape, never
  replay-and-land). All THREE WGSL copies synced md5 7bd66c660aa936ac000cb55a7d87f871.
- **Gate: tests/test_bk48_wgsl_ld_tile_fence.py 6/6** (force-added past the
  .gitignore test_*.py rule; 2 pinned runs byte-identical). L1a tile-armed
  USER out-of-tile LD traps (fault 656 = word164*4, r6 refused, mode SUPER
  — THE oracle-parity leg, RED pre-fix); L1b in-tile LD lands (r6=0x0ADF00D,
  mode USER, no fault); L2a TILE_H==0 cooperative LD unfenced (ruling
  clause 1); L2b SUPER LD exempt; L2c paged USER LD NOT vaddr-fenced (tagged
  PT at RAM 2001, "PTG" 0x505447, V|U identity PTE — the new
  branch-structure leg); L3 exfil shape closed (out-of-tile LD refuses ->
  in-tile ST carries 0x0, the canary never crosses); L4 non-vacuity
  (ld_tile_fault hard-false in a TEMP-COPY module -> canary re-delivered;
  real tree md5-pinned); L5 family subprocess leg (BK-51 gate + BK-38
  oracle gate).
- **RED-first demonstrated twice at landing time:** (1) full-fix stash ->
  L1a FAILED with the exact pre-fix shape ("fault 0, expected 656 — walk_ld
  returned the word"); stash pop -> 6/6. (2) L2c RED-leg: ONLY the
  pt_base!=0 guard removed -> L2c FAILED ("paged USER LD was vaddr-fenced,
  r6=0x0, mode 0, fault 656") proving the new leg has teeth; restored,
  md5 re-verified.
- **Family on this tree (post-fix, all green):** BK-48 6/6, BK-51 5/5,
  BK-38 oracle 6/6, wgsl_validation. build_map regenerated to frontier
  72b728bb (exempt map-lane channel, committed with the landing).
- **NOT proved:** the paged-path read fence (BK-66-twin — a paged USER LD
  still reads any translated paddr on the twin; that row's consult is
  post-translation on the oracle and its twin-side landing is a separate
  line item); BK-50 MMIO-read posture for TILE words (unchanged, config
  reads stay unmode-gated by design — reads return 0 to USER per BK-56
  parity); the oracle re-run (engine md5 bc422443 untouched — oracle-side
  :995 branch was already measured green in test_bk38_ld_fence.py 6/6);
  stack-path reads (BK-49's POP consult is a separate row). Numbers
  structural — rule-1 floors do not attach.
- Landed as 76c54ea0 (Pillar 2.3 pre-commit parity gate passed; build_map
  regen to frontier 76c54ea0 as 6bf6eb05). Next tick: BK-66-twin (paged
  read fence, post-translation paddr consult mirror of
  glyph_isa_v2.py:952-1004), or next NOT-proved bullet per protocol.

# PRODUCT LANE STATE — ledger for the Glyph GPU OS product roadmap

### 2026-09-28 21:4x CDT — BK-51 LANDED: the WGSL twin's `addr_in_box` now carries the GO-2 2D tile predicate (bitwise mirror of the oracle's :734-747 branch) — a tile-armed USER task's LAWFUL in-tile stores LAND on the GPU where the twin previously denied EVERY store, and out-of-tile stores still trap E-K1; the measured engine divergence is closed (builder af3e62239ce2)

- **Rung selection:** tick woke on HEAD b798b1c0 (monitor CLEAN,
  tracked_dirty=0, queue=0), mailbox re-verified — no RULING_*.md newer
  than HEAD (newest mtime 1790550013 < HEAD commit time 1790646940).
  QUEUE_STATE all landed, CURRENT_TICKET closed, R1.4 checked FIRST —
  CLOSED. Claim queue empty → fence-family line items per the ledger's
  own next-tick note: BK-51's twin tile term (the backlog row names it
  "the remaining line item of this composition" after BK-66's oracle-side
  consult landed; blast radius wgsl_glyph_isa_v2.py only).
- **RED (measured at HEAD b798b1c0, probe
  .builder_queue/probe_wgsl_tile_fence_af3e.py re-run, results md5
  9701e0d40eba3fd3f9ce12b6dd6c4d89, verdicts from ram/mmio readback
  bytes):** D3 — tile (5,0,2,4) armed in mmio[88..91], seeded-USER in-tile
  ST to word 160 → fault 640, mode→SUPER, REFUSED (the twin denies the
  lawful store; the oracle lands it clean) — exactly the backlog row's
  measured divergence, reproduced live; D1 out-of-tile ST traps 656
  (oracle parity held on the deny side); D2 box-only control fault 400
  (box consult live — D3 is the missing tile term, not a dead harness);
  D4 USER still clears TILE_H through the BK-50 unmode-gated MMIO door
  (composition defect disclosed, BK-50 scope, unchanged by this fix).
- **Fix (tools/wgsl_glyph_isa_v2.py, +52 lines):** the tile branch in
  `addr_in_box` (:478-528 post-patch) — TILE_H!=0 admits
  [trow,trow+h)×[tcol,tcol+w), word=byte>>2, row=word/32, col=word%32 —
  bitwise mirror of glyph_isa_v2.py:734-747; TILE_ROW/COL/H/W_WORD consts
  (8280..8283 = BOX_MMIO_BASE+0x160..0x16C >> 2) + W_MEM=32 const added.
  No signature change; walk_st's single consult site consumes the term —
  BK-48's read-side walk_ld gap is NOT this row (LD consult untouched).
  All THREE WGSL copies synced (tools/, glyph_dispatch/src/,
  glyph_dispatch/src/glyph/) md5 cf87ca1755a4d75bab04c752313a4f5d
  (triple-sync gate caught the third copy — good gate).
- **Gate: tests/test_bk51_wgsl_tile_fence.py 5/5** (force-added past the
  .gitignore test_*.py rule). L1a tile-armed USER in-tile ST lands
  (word160 0xadf00d, mode USER, no fault — the oracle-parity leg, RED
  pre-fix); L1b out-of-tile ST traps (fault 656, mode SUPER — fence
  stays live); L2 box-only arming still fences word 100 (fault 400) +
  tile-armed default-deny holds (the term ADDS admission, never removes
  deny); L3 non-vacuity — tile branch removed in a TEMP-COPY module →
  L1a's program re-traps (gate has teeth; real tree md5-pinned
  before/after); L4 family subprocess leg. RED-first demonstrated vs the
  LIVE defect at landing time: `git stash` of the fix → L1a FAILED with
  the exact pre-fix shape ("in-tile ST TRAPPED (fault 640, mode 0) — the
  twin denies the lawful store"); stash pop → 5/5, 2 pinned runs
  byte-identical.
- **Family on this tree (post-fix, all green):** BK-51 + BK-64 +
  BK-64-red/HILB + GH-4 + BK-12 + wgsl_validation 24/24; BK-66 7/7 +
  BK-52 + BK-38 18/18; triple-sync + SE024 + BK-2 10/10; item-36 8/8;
  GH-4 4/4. Pre-commit hook: Pillar parity gate to run at commit.
- **NOT proved:** BK-50 door posture for the TILE words (the BK-51 row's
  own L4 — design-judgment: USER can still clear TILE_H through the
  unmode-gated MMIO door, re-measured D4 today; decision reserved to the
  BK-41/50 sequenced commit, NOT silently taken here); walk_ld's
  read-side fence (BK-48's line item — a tile-armed task can still READ
  anywhere on the twin; this landing is store-side only); the fleet
  images arm no tile today (latent defect posture unchanged — the term
  is inert at TILE_H==0, byte-identical legacy behavior); W_MEM const
  assumes the 32-word grid (matches glyph_isa_v2.py:121; no runtime
  tie). Numbers structural — rule-1 floors do not attach.
- Next tick: BK-48's walk_ld consult (read-side twin fence, gate spec
  in the row), or the ruling clause 2b/2c invariant legs, or next
  NOT-proved bullet per protocol.

### 2026-09-28 21:0x CDT — PHASE 1c RESEARCH TICK 21: KSYS-side chain + persistence POST-consult — the E1 shape is NOT one-shot: guest re-arm of ksys chains a second dispatch through the re-armed vector ([7,7,52,0]) and self-re-arm persistence fires 75× in a 600-step budget; RED leg (no-vector exemption neuter) breaks both; the no-vector refuse is CLEANLY compatible with the KSYS site (builder af3e62239ce2)

- **Rung selection:** tick woke on HEAD b28a8f65 (tick-20 landing 507d91a0 +
  sibling SCENARIO-12 doc filing are both ancestors). Ledger STATUS ACTIVE,
  queue empty, CURRENT_TICKET closed, R1.4 checked FIRST — CLOSED; no
  RULING_*.md newer than HEAD (newest mtime 1790550013 < HEAD time
  1790645774); BK-76 refusal posture still pending → exemption legs stay
  blocked → Phase 1c research. Monitor flagged tracked_dirty=1 (DIRTY_ACTIVE)
  — verified the dirty set is ONLY the exempt build-map channel + untracked
  strays, no shared-file parallel session mid-flight. Rule-5 grep BEFORE
  harness build: tick 20's receipt names KSYS chain/persistence as the last
  UNMEASURED sibling; tick 19 measured KFAULT-side; ticks 15/16 SYSCALL-side
  PRE-consult only — net-new.
- **Measured (probe probe_ksys_chain_postconsult_af3e.py, real
  spawn(tile=(256,19,1,2)) posture, NO paging NO paint, 3 pinned runs
  identical, results_md5 2335277c5ccee3affe19f04b905876df):**
  K1 CHAIN — handler re-arms ksys←G2 (65540) via one :968-exempt SUPER-window
  ST; second SYSCALL vectors through the re-armed live read (glyph_isa_v2.py
  :1288) into G2; G2 unarms ksys←0; third SYSCALL takes the no-handler
  fallback → output [7,7,52,0], ksys_word_after 0, exit 0, no fault.
  K2 PERSISTENCE — self-re-arm + SYSRET loop: 75 handler fires in a 600-step
  budget, no fault, no guest escape (step cost per fire, not breakability).
  C1 unarm control clean ([7], ksys 0); C2 fixed-vector control [7,7];
  C3 unpaged USER ST → E-K1 refused (fence live).
- **RED leg (probe_ksys_chain_red_af3e.py, results_md5
  6ebd72a3ddfb4a670a671d48b8c7987c; engine md5 bc422443… asserted unchanged):**
  no-vector :968 exemption neuter breaks both green shapes — K1 [7,7,52,0]→[7]
  (re-arm refused, no second dispatch), K2 75 fires→1 then clean stop.
  SUB-FINDING for the BK-76 posture decision: unlike tick-19's KFAULT side
  (fault-path refuse → 162-fire restart loop), the KSYS site tolerates the
  no-vector refuse CLEANLY — no re-vector vehicle exists (ksys is read only
  at the SYSCALL arm). Evidence that no-vector + handler-must-not-store is
  the cheapest safe posture pending Jericho's ruling.
- **Landed this tick:** probes + results ×2 + receipt
  (RESEARCH_ksys_chain_postconsult_af3e.md) + BK-76 evidence-column fold. NO
  engine/shader code (md5 asserted); scope = .builder_queue/ +
  systems/GLYPH_BACKLOG.md + this ledger only.
- **Probe defects disclosed (pre-evidence):** draft layout miscount (tick-20
  v1 defect class — caught by wrong-shaped outputs before any conclusion,
  fixed with per-leg instr-count asserts); results-file path defect (wrote
  repo root once — stray deleted, path fixed); K2 self-re-arm byte-equality
  ambiguity (host arm == self value) — RED leg discriminates on
  fault_reason/faulted, K1's sentinel carries the landing proof.
- **NOT verified:** twin side (no SYSCALL/KSYS in the WGSL walker —
  oracle-only); steps-per-fire=8 derived by instruction count, not traced;
  xv6-nano real-handler posture unchanged open question (Jericho's ruling).
  Next tick: BK-76 exemption legs if the refusal posture is ruled; else
  research per Phase 1c.

### 2026-09-28 20:2x CDT — PHASE 1c RESEARCH TICK 20: the :968 SUPER MMIO-window exemption SURVIVES the BK-66 consult and is now reachable with ZERO fence violations (self-text dispatcher, no paging, no paint); BK-76 filed (builder af3e62239ce2)

- **Rung selection:** tick woke on HEAD bc43c4de (monitor CLEAN,
  tracked_dirty=0, queue=0); mailbox re-verified — no RULING_*.md newer
  than HEAD (newest mtime 1790550013 < HEAD time 1790643038). A parallel
  session landed ba015db3 (GH-32 + GH-30 doc-only specs) MID-TICK; this
  tick's probe work is untouched by it (no shared files) and receipts cite
  the measured-at HEAD ba015db3. QUEUE_STATE all landed, CURRENT_TICKET
  closed, R1.4 CLOSED — Phase 1c research. Rule-5 grep BEFORE harness
  build: no RESEARCH_*/backlog row measures exemption reachability
  POST-consult (BK-72..75 all say "fix must gate :968" from pre-consult
  measurements) — net-new.
- **First finding (verification, not new code):** re-ran all SIX
  dispatch-family probes (ticks 12-19) at HEAD — every composition leg
  now collapses at its PAINT store with `paged_paddr_fence op=ST`
  (results md5s e0c6e7e6 / cb178fe3 / 513376cf / 0ee8903b / 1f36d6f6 /
  8d70a3f3; none match the receipts' pre-consult md5s). EXPECTED
  post-fix shape — the consult is working; the receipts' RED shapes are
  closed. BK-66's own gate 7/7 remains the landing evidence; re-ran it
  green at HEAD (7 passed) plus family gates test_bk38 5/5 + test_bk64
  9/9 + test_bk52 11/11.
- **THE NEW MEASURED FACT (probe
  .builder_queue/probe_exemption_selftext_af3e.py + controls, 3 pinned
  runs identical, controls results md5 48aaa0c3d347b024b936ff03fd767405):**
  E1 — a tile-confined USER task whose OWN program text is the ksys
  dispatcher (host-armed ksys=(0,3), the loader-seed posture; NO paging,
  NO paint) SYSCALLs into SUPER and stores to KSYS_PC (word 8194)
  through the :968 MMIO-window exemption: ksys_word_after 65537 (the
  sentinel LANDS), output [52], mode_final USER, exit 0, no fault. The
  paddr consult never engages — the exemption short-circuits translation
  (guard at glyph_isa_v2.py:885/:1046). K1 SUPER no-tile control lands
  lawfully; K2 USER unpaged rot-guard E-K1 traps; K3 USER paged
  rot-guard refused by the consult (`paged_paddr_fence op=ST paddr=8194
  vaddr=0x8008`). TWO SERVING BRANCHES, ONE FENCE HOLE (BK-73's
  sub-finding) re-measured POST-consult: walk branch dead, exemption
  branch alive. WORSE than pre-consult in reachability terms: the
  attacker previously needed paged out-of-tile paint (now refused) —
  now the task's own unfetched-fenced text (BK-67/68/69) is a legal
  dispatcher body with zero violations.
- **Probe defect disclosed (pre-evidence):** v1 assumed packed
  (row<<16)|col dispatch targets and label-kept rows; the baker packs
  instructions contiguously (8 per 32-px row) so v1's ksys pointed at a
  zero pixel and the "landed" value was the probe's own host arm —
  caught by per-step trace (dbg_selftext_trace_af3e.py) + layout
  discovery (dbg_selftext_layout_af3e.py: instr N at pixel
  (4*(N%8), N//8)); v2 uses real layout + sentinel 65537 != host arm 3.
- **BK-76 filed** to systems/GLYPH_BACKLOG.md (gate: tests/
  test_bk66_paged_tile_fence.py grows EXEMPTION legs EX-L1..L5, RED
  today per E1; refusal posture no-vector vs provenance-pinned flagged
  design-judgment, BK-75 KFC-L6 binds it). Research landed probes +
  results + receipt (RESEARCH_exemption_survivor_af3e.md) + backlog row
  only — NO engine/shader code changed (engine md5 bc422443… untouched
  this tick; glyph_dispatch mirror still md5-identical).
- **NOT verified:** twin side (no MMIO window in the WGSL walker,
  oracle-only); xv6-nano real handler window-store behavior (a blanket
  exemption gate could break it — posture decision for the landing
  round); post-fix chain/persistence (all paint-based chains stop at the
  consult now; persistence via the E1 one-shot shape UNMEASURED).
  Next tick: new queue supply if it appears, else the BK-76 exemption
  legs are the cheapest UNBLOCKED fence-family line item IF Jericho
  rules the refusal posture — otherwise research per Phase 1c.

### 2026-09-28 19:50 CDT — BK-66 LANDED: the paged x tile fence composition is CLOSED — arming GH-17 paging no longer disarms the GO-2 tile fence; the paged arms now consult the TRANSLATED PADDR (Jericho's DESIGN RULING, commit 9714a363) via _physical_in_tile() in all six paged target arms (builder af3e62239ce2, commit 0628dcc4)

- **Rung selection:** tick woke on HEAD 08dbb7fa (monitor CLEAN,
  tracked_dirty=0, queue=0), mailbox re-verified: no RULING_*.md newer
  than HEAD (newest mtime 1790550013 < HEAD commit time 1790640308) —
  but the BLOCKER moved: the BK-66 posture decision that stalled the
  fence-commit family had landed as commit 9714a363 ("Jericho ruling
  (via Hermes): BK-66 posture = PADDR-side fence consult post-translation,
  closes BK-66/70/71 mechanically..."), ancestor of HEAD, +37 lines to
  systems/GLYPH_BACKLOG.md only. With the design-judgment resolved, BK-66
  became the cheapest UNBLOCKED fence-family line item (the ledger's own
  next-tick note named the family landing as blocked on exactly this
  decision). Claim-queue first per protocol: QUEUE_STATE all landed,
  CURRENT_TICKET closed, R1.4 checked BEFORE research — CLOSED (landed
  2026-09-21, later re-proven). BK-52 already LANDED last tick (bc7413e9).
- **RED (measured at HEAD 08dbb7fa, probe
  .builder_queue/probe_paged_tile_oracle_af3e.py, results md5
  32a9cc1809b9f33b6d512e0b9930ebf8 — BYTE-IDENTICAL to the research
  receipt's pinned 3-run md5):** T1 paged out-of-tile LD -> exit 0 clean
  USER, r10=0xadf00d (canary read through a full-flag PIX PTE, pfn 5 ->
  image word 1280, physically OUT of tile (256,19,1,2)); T2 paged
  out-of-tile ST -> exit 0 clean, canary LANDS at word 1280 — the exact
  instruction-stream-class shape; C1 unpaged LD fault 16000 / C2 unpaged
  ST fault 656 — the landed fences LIVE when pt_base == 0 (composition
  gap, not a dead fence).
- **Fix (ruling posture, not lane choice):** _physical_in_tile(word_addr)
  applies the GO-2 grid predicate (row = word // W_MEM, col = word %
  W_MEM; TILE_H==0 inert -> byte-identical legacy paging for unfenced
  tasks) to the DECODED physical target — pix_word in the HILB/PIX arms,
  paddr in the plain arm — in all SIX paged target sites (LD :901-940 /
  ST :1126-1180 post-patch numbering, LD+ST x HILB/PIX/plain). NO consult
  in the paged path sees a vaddr (ruling clause 1: vaddr-side is defeated
  by construction — the attacker owns the PT). _paged_paddr_fence_fault()
  mirrors the unpaged discipline: FAULT_ADDR = the physical BYTE address
  the fence judged, fault_reason names op/paddr/vaddr/site, drop to
  SUPER, KFAULT_PC vector WITH the BK-52 kf==0 stop guard (never
  replay-and-land). ST plain arm checks the fence BEFORE the DEFECT-23
  ceiling arm so a fenced store is a FENCE fault, not ceiling/extend
  absorption. MMIO exemption untouched (SUPER branch, clause 4); lawful
  paged work preserved (clause 3).
- **GREEN (same probe, results md5 2f12bcd8fdcfbba504c47294f232fed3):**
  T1 -> exit 1 SUPER, fault_addr 5120 (= 1280*4, the PADDR), reason
  "paged_paddr_fence op=LD paddr=1280 vaddr=0x3000", r10 refused; T2 ->
  same shape, canary NOWHERE; C1/C2/C3 byte-identical to the RED run —
  the unpaged fences and lawful in-tile work untouched.
- **Gate: tests/test_bk66_paged_tile_fence.py 7/7** (force-added past the
  .gitignore test_*.py rule). L1 paged out-of-tile LD traps AND pins the
  consult's PADDR-ness (fault_addr == 1280*4, reason contains "paddr=1280"
  — a vaddr-side implementation FAILS this leg, the ruling's own
  falsifier); L2 ST refused + canary absent; L3a mapped in-tile paged ST
  (vpn-32 PTE pfn 32, vaddr 8212 -> paddr 8212) lands clean USER (lawful
  work preserved); L3b the unmapped pte_invalid shape byte-identical
  (fault_addr 32848 — translation is NOT the fence's job); L4 unpaged
  rot-guards (out-of-tile LD/ST trap, in-tile LD+ST clean); L5
  non-vacuity — the consult neutered to `return True` in a TEMP-COPY
  module re-runs L1's program: faulted False + canary DELIVERED (pre-fix
  behavior reproduced; real tools/ engine md5 pinned identical
  before/after); L6 family subprocess leg (BK-38 + BK-64 gates green).
  Probe defect caught pre-landing: L5 v1's manual step loop never ran
  (cpu.running starts False outside cpu.run()) — the leg asserted against
  a never-stepped CPU and PASSED VACUOUSLY on first authoring only
  because the faulted-False assert also held trivially; the canary assert
  caught it; fixed by mirroring run()'s own `cpu.running = True`
  (tools/glyph_gpt/runner.py:57).
- **Family on this tree at HEAD 0628dcc4 (post-commit re-run):**
  test_bk66 7/7 + test_item29 10/10 + test_item30 6/6 + test_item31
  (incl. both R-gates + N1) + test_bk38_ld_fence 6/6 + test_bk64 6/6 =
  47/47 in one pytest invocation (4m38s, the N1 guards pin the engine to
  HEAD and pass at the landing commit). Pre-commit at the fix-tree:
  test_bk52 5/5, test_bk64_red_leg_and_bk65_hilb 3/3, GH-17 6/6, GH-25
  3/3, monitor hygiene 9/9, item-31 stratum 7/7 + 3 known-RED N1
  engine-byte guards (HEAD-pin by design — pass at the landing commit,
  disclosed, not chased). Pre-commit hook: Pillar 2.3 parity gate passed.
- **Mirror:** glyph_dispatch/src/glyph/glyph_isa_v2.py synced, md5
  bc422443730e6851a2a41f42376e8830 identical to tools/.
- **Worktree note:** AGENTS.md's core-file worktree-isolation rule is
  satisfied by the mirror-sync + full differential family (the edit is
  six guard insertions + two new helpers, no signature change — the same
  posture BK-52's landing used). One mid-tick hazard disclosed: a
  `git stash` RED-leg attempt (item-29 N1) popped into a conflict with a
  mid-flight build_map_data.json regen (the exempt churn channel); the
  stash entry was recovered via `git checkout stash -- tools/glyph_isa_v2.py`
  + drop; the RED leg was instead demonstrated by the pre-fix probe run at
  HEAD (md5-identical to the receipt), which is the stronger form anyway.
- **NOT proved:** WGSL twin side — BK-51's tile term is the twin-side
  line item of this same composition (ruling clause 5: twin takes the
  same paddr posture); wgsl_glyph_isa_v2.py untouched this commit. Ruling
  clause 2b/2c dedicated gate legs (cross-task PT-window exclusion +
  PT-tag header-when-paged leg) NOT yet authored — the consult gates PTE
  writes STRUCTURALLY (a paged ST to a PT word is judged by its translated
  paddr like any store) but the named invariant legs are follow-up.
  BK-70/71 inherit the consult site MECHANICALLY per the ruling but their
  own probes were not re-run post-fix this tick. Box-predicate paged
  composition (BOX0..2 ranges under paging) unmeasured — the tile is the
  ruled, measured posture; the box consult under paging rides the same
  translated-address principle but has no gate today. Numbers structural
  — rule-1 floors do not attach (no rate/cost claims).
- **Next tick:** BK-51's twin tile term (the twin-side line item, twin
  gate legs already named in its backlog row, blast radius
  wgsl_glyph_isa_v2.py, worktree isolation per AGENTS.md), or the ruling
  clause 2b/2c invariant legs, or next NOT-proved bullet per protocol.

STATUS: ACTIVE

### 2026-09-28 ~19:1x CDT — BK-52 LANDED: the oracle's KFAULT_PC=0 trap continuation is DEAD — both E-K1-class vector sites (glyph_isa_v2.py ST arm :1086 + iso-armed OOB sibling :1121) now carry the kf!=0 guard, byte-parity with the WGSL twin's walk_st arm (:602-609, already correct) — the replay-and-land bug is closed: a trapped task with no handler installed now STOPS at the trap instead of vectoring to (0,0) and replaying from entry in SUPER with the "refused" store landing (builder af3e62239ce2, commit bc7413e9)

- **Rung selection:** monitor CLEAN at HEAD e0afc4f1
  (tracked_dirty=0, queue=0, stall_tier=0), CURRENT_TICKET closed,
  CLAIM QUEUE empty (QUEUE_STATE 6/6 landed), mailbox clean (newest
  RULING mtime 1790550013 < HEAD commit time). R1.4 checked BEFORE
  research per the standing directive: CLOSED (landed 2026-09-21,
  RECEIPT_R14_wgsl_convergence.md, later re-proven halt@458 fleet
  non-zero). BK-66's posture decision still binds the paged-consult
  family rows. BK-52 chosen as the cheapest UNBLOCKED fence-family
  line item: prereqs none blocked, twin already carries the guard
  (pure oracle parity), gate spec fully named in the backlog row.
- **RED (measured at HEAD e0afc4f1, probe posture = arm_tile USER +
  tile (5,0,2,4) armed + KFAULT_PC=0, reaper row 30 planted):**
  no_handler {steps 7, fault_addr 656, mode_final SUPER, pc_final
  (12,0), word164 = 0x0ADF00D} — the trap vectored next_pc=(0,0),
  mode already SUPER, program REPLAYED from entry and the REFUSED
  out-of-tile store LANDED. with_handler control {steps 4, pc (0,30)}
  — parks on the reaper, store refused.
- **Fix:** two guard sites, mechanical twin parity — ST E-K1 arm
  (tools/glyph_isa_v2.py:1086) and the iso-armed in-box-OOB sibling
  (:1121) now test kf != 0 before vectoring; kf == 0 sets
  running=False (stop at the trap). No other vector site touched
  (the six paged/tag sites already carried the guard — :851/:890/
  :936?/:983/:1016/:1061 measured in the BK-52 research tick).
  glyph_dispatch/src/glyph/glyph_isa_v2.py mirror synced (md5
  357f3a67 identical to tools/).
- **GREEN (same probe):** no_handler {steps 3, word164 0, running
  False} — store does NOT land; handler leg byte-identical to the
  RED run's shape.
- **Gate:** tests/test_bk52_kfault0_trap.py 5/5 (force-added past the
  .gitignore test_*.py rule). L1 kf=0 halts at trap; L2 handler
  vector unchanged (never weaken a live guard); L3 sibling OOB site
  (BOX0 armed above RAM end — the reachable in-box-OOB posture, since
  _iso_enabled is a RAM-size property, not assignable); L4 non-vacuity
  — guard neutered to `if True` in a TEMP COPY re-runs L1's program,
  canary LANDS (pre-fix behavior reproduced, gate has teeth), real
  engine md5 pinned identical before/after; L5 family subprocess leg
  (test_bk38_ld_fence green). RED-first demonstrated at landing time:
  fix stashed -> 3 FAILED (L1/L3/L4), stash pop -> 5/5.
- **Family on this tree:** test_bk38_ld_fence 6/6,
  test_item29_containment 16/16 (N1 engine-byte guard pins on-disk vs
  HEAD — passes at this commit), test_bk64 6/6 + red/HILB 3/3,
  monitor hygiene 9/9, xv6-nano 13/13, map substrate 4/4. Pre-commit
  hook: transpiler differential 38/38 + Pillar 2.3 golden-corpus
  parity 8/8 (glyph_isa_v2.py is a core-file surface; worktree rule
  satisfied by the mirror-sync + full differential — the edit is two
  guard insertions, no signature change).
- **build_map.png/data.json regenerated to frontier bc7413e9**
  (cells 629, frontier (20,27)) — exempt build-map lane channel,
  content is the map's own regeneration.
- **NOT proved:** WGSL twin side re-measured on-device (twin already
  carried the guard; no shader change in this commit); the sibling
  :1116 branch under iso-DISABLED fixtures (dead there by
  construction — property returns False below _ISO_TOP_WORD);
  BK-50/BK-51 probe end-state legs that observed the post-trap
  replay state (the backlog row names this re-base — probe re-runs
  are a follow-up, not silently assumed).
- Numbers structural (steps, word values, fault addrs, modes, md5s)
  — rule-1 floors do not attach. Sixth line item of the BK-38..57
  sequenced fence commit family. Remaining known-open fence-family
  rows: BK-48/49/50/51/53/55/57 twin+execute-side consults (twin
  gate legs named, blast radius wgsl_glyph_isa_v2.py), BK-39..45
  oracle consult sites, BK-59+ and the BK-66-posture-bound rows.

### 2026-09-28 ~18:4x CDT — BK-64 + BK-65 LANDED: the WGSL twin's paged walker now enforces PTE_W / PTE_U (bitwise mirrors of the oracle's :1001/:873 checks) — the fifth and cheapest line item of the BK-38..57 sequenced fence commit family, measured GREEN with its own RED leg demonstrated this tick (builder af3e62239ce2)

- **Claim:** tick woke on HEAD 9f76402b with the BK-64 fix sitting
  UNCOMMITTED in the working tree (tools/wgsl_glyph_isa_v2.py, 45 lines)
  — left "for builder cron (working-tree diff present, claimed by builder
  under 9714a363)" by the 9f76402b session. The BK-64 gate file
  tests/test_bk64_pte_flag_paged.py was present but UNTRACKED
  (.gitignore test_*.py rule, force-add required). Ledger re-read per
  protocol: STATUS ACTIVE, queue empty, no RULING newer than HEAD
  (newest .builder_queue/RULING_*.md mtime 2026-09-27 18:00 < HEAD commit
  time 1790631184). The fix is exactly what BK-64/BK-65 specify: two
  predicate terms — walk_ld paged branch requires U in USER / SUPER
  exempt (mirror of glyph_isa_v2.py:873, :392-399) and walk_st paged
  branch requires V + (U in USER) + W with NO mode exemption (mirror of
  :1001, :429-440) — sitting BEFORE the HILB/PIX/Plain arm dispatch, so
  one check site covers all three frame arms (BK-65's measured
  conclusion, no additional code). NO new fix was authored this tick;
  the work was verification + gate completion + landing.
- **Verification (all re-run this tick):** BK-64 gate 6/6 GREEN
  (tests/test_bk64_pte_flag_paged.py: L1 W-clear PIX ST refused, L2
  U-clear PIX LD not delivered, L3 SUPER W-clear ST parity pin, L4
  full-flag ST/LD controls live, L5 flag-delta non-vacuity, L6
  neutered-check re-lands canary on a temp-copy module with the real
  module md5-pinned). Gates family: GH-17 paging, GH-25 Hilbert paging,
  BK-12 twin tier, GH-4 parity, GH-27 editor, monitor hygiene —
  combined run 45/45 GREEN (3.42s).
- **Gate completion this tick:** BK-64's gate as filed lacked (a) the
  RED leg demonstrated against the LIVE defect at landing time and (b)
  BK-65's HILB-arm legs. Both landed in
  tests/test_bk64_red_leg_and_bk65_hilb.py: RED leg = the ST flag check
  neutered in a TEMP COPY (V-only, pre-fix behavior) re-runs L1's exact
  program and the canary LANDS at frame word 1280 (0xadf00d) — the gate
  fires against the live defect; real tools/wgsl_glyph_isa_v2.py md5
  14ef6d2d2261775c87dc218e760ef952 pinned before/after the run.
  H1w: W-clear HILB ST (pfn 0x300 -> hilbert word 1280) refused. H1u:
  U-clear HILB LD not delivered (r10=0xffffffff, the walker's
  caller-visible fault marker). HILB pfn packing derived from the
  module's own hilb_frame_word body ((row<<8)|col, tick-7's 0x300
  encoding), not assumed. 3/3 GREEN (0.81s).
- **Known-RED pre-existing failures DISCLOSED, not introduced:** the
  broader tests/ sweep carries 23 failures that fail IDENTICALLY with
  the fix stashed (git stash -> same suites, same counts: color_explorer
  4 failed, gh24_s2_mcp_server 6 failed, go6_l2_virtqueue_walk 3 failed,
  orchestrator_speak_to_driver 2 failed, defect17_x31 1, defect_d_ram 1,
  agy_wrapper 1, bk23_dogfood 1, bk36_move_snapshot 1, dct_stego 2,
  cross_lingual_say 1 — verified by stash-diff this tick). None import
  the WGSL walker; all are environment/pre-existing (chip test classes,
  MCP server fixtures, driver harnesses). The full suite ALSO hangs
  indefinitely at test_item28_root_init.py::test_r3 on this host (killed
  at 41m, 0 CPU delta over 10s, 31 threads parked in Vulkan poll — same
  shape whether or not the fix is stashed); the -v run pinned the hang
  site for the next owner. NOT chased here — zero-relation to this
  landing, and killing other lanes' pytest processes mid-flight is not
  this lane's call.
- **Committed:** tools/wgsl_glyph_isa_v2.py (the fix) +
  tests/test_bk64_pte_flag_paged.py + tests/test_bk64_red_leg_and_bk65_h
  ilb.py (force-added past the .gitignore test_*.py rule per the repo's
  standing instruction). build_map.* left to the build-map lane
  (RUNTIME_EXEMPT churn channel). NOT proved: oracle-side flag parity
  re-measured on this tree (the oracle already faults these shapes —
  glyph_isa_v2.py:1001/:873 — pins live in L3/L4); the R1.4 WGSL
  fleet-convergence defect (halts @153, fleet words 0) is UNTOUCHED by
  this landing — BK-64's terms are flag-level and upstream of that
  halt; sibling walk sites outside the paged branch (unpaged arms) were
  not re-audited (they were measured fence-live by the BK-64/65 probes'
  C1 legs). Rule-1 floors do not attach (no rate/cost claims).

### 2026-09-28 ~15:4x CDT — STRAY LANDING: three 2026-09-27 research ticks verified on the live tree and committed (BK-45 VFS fence, BK-48 WGSL fence twin, BK-55 WGSL E-K1 vector hijack) — receipts/backlog rows were filed 09-27 but the probe + receipt artifacts were never committed (builder af3e62239ce2)

- **Found:** three complete-but-uncommitted research artifacts sitting in the
  tree since 2026-09-27 (02:4x–05:4x): `.builder_queue/probe_vfs_fence_af3e.py`
  + `RESEARCH_vfs_twin_fence.md` (BK-45), `probe_wgsl_fence_twin_af3e.py` +
  `RESEARCH_wgsl_fence_twin_af3e.md` (BK-48), `probe_ek1_vector_hijack_wgsl_af3e.py`
  + `RESEARCH_ek1_vector_hijack_wgsl_af3e.md` (BK-55). Ledger entries for all
  three exist at HEAD (the 09-27 sessions wrote prose + backlog rows but never
  ran the commit). Same class as tick 19's uncommitted KFAULT chain — landed
  per the verify-then-commit pattern, no new research this tick.
- **Verification (re-run on live tree at HEAD 33f0a445, engine md5
  untouched):** BK-48 stdout md5 658a55330c8c4b3cf143b30ccca6eda4 —
  BYTE-IDENTICAL to the receipt. BK-55 stdout md5
  555be18107f116c6caede990e6d0e1cc + results md5
  128582726113782d8c234a4a59d7b068 — both BYTE-IDENTICAL to the receipt;
  all five verdicts reproduce (D1 hijack, D2 super capability, D3
  guest-writable vector, C1 kf=0 halt, C2 fence-live). BK-45 results md5
  c1ac611a712160654dfddd7ed4be27ee — matches the receipt; all 9 legs'
  verdicts match; host /tmp/b8w asserted absent BEFORE and AFTER the run
  (path containment holds; probe's finally-cleanup live).
- **Committed:** probe + receipt files only (6 files, .builder_queue/) —
  the BK-45/48/55 backlog rows and ledger prose were already in git.
  NO engine or shader code changed; build_map_data.json left to the
  build-map lane (exempt channel).
- **NOT proved:** the 09-27 md5s were reproduced once each this tick, not
  3× (the receipts' own 3-run byte-identical claims stand as recorded);
  dbg_ek1_wgsl_draft{2..8}_af3e.py debug artifacts disclosed in the BK-55
  receipt were NOT found in .builder_queue (left in /tmp per the receipt's
  own note — debug-only, not evidence, not landed).

### 2026-09-28 ~15:2x CDT — MONITOR FIX 3: stale ledger NEXT line no longer drives CLAIM_PENDING (phantom claim-supply closed, builder af3e62239ce2)

- **Symptom:** third phantom in the same day, named in
  CURRENT_TICKET.json (REPAIR_stale_NEXT_line_triggers_claim_pending) at
  the previous tick: a clean, queue-empty tree read
  `state=CLAIM_PENDING queue=0 supply=claim: (round-9+ supply items
  18-23 from the seat lane…` — round-9/10 supply from 2026-09-25, all
  landed per QUEUE_STATE.json (25 landed, 0 queued).
- **Root cause (measured, not inferred):** the ledger fallback
  (tools/glyph_build_chain_monitor.py:352, the 2026-09-24 split-brain
  fix) regex-matched the FIRST `^NEXT:` ANYWHERE in
  HEAD:.builder_queue/PRODUCT_LANE_STATE.md — no recency anchor. The
  stale 2026-09-25 NEXT (ledger :3913) won; reproduced with the exact
  pre-fix regex: whole-file first match at offset 268495, deep in a
  stale entry, while the newest entry (first `### ` block) carries no
  NEXT at all. Same phantom class as the two fixed today (build-map
  self-reference churn; nested probe-leg statuses): a supply channel
  ingesting stale/non-ticket signal.
- **Fix (cheapest, ticket-named):** the NEXT scan is anchored to the
  MOST RECENT ledger entry — `_ledger.find("### ", 5)` bounds the scan
  scope; the `queue empty` exclusion is retained. NEXT lines are
  per-entry state; a NEXT in any older entry can never feed supply.
  Gate channel NOT weakened: a genuinely current NEXT line still
  level-triggers CLAIM_PENDING exactly as before.
- **Gates:** tests/test_monitor_fingerprint_hygiene.py 9/9 GREEN (new
  L9: source pin + live-instrument leg + deterministic mechanism leg).
  RED leg shown at landing time against the LIVE instrument: `git
  stash` of the monitor fix → `state=CLAIM_PENDING queue=0 supply=
  claim: (round-9+ supply items 18-23 from the seat lane` (phantom
  verbatim), L9 FAILED at :424; `stash pop` → 9/9 pass, supply=ok.
- **NOT proved:** the fallback channel is now exercised only by future
  real NEXT lines (leg L9c is conditional on the defect shape being
  present at HEAD, so it self-disarms once a future entry carries a
  legitimate NEXT — by design); whether any consumer other than the
  fingerprint reads prose NEXT lines (grep over tools/ + tests/ shows
  none); non-`### `-delimited ledgers (the format is lane-owned and
  stable since inception).
- Next tick: ledger re-read per protocol; queue empty + no open ticket
  → Phase 1c research eligibility per standing rules (KFAULT_PC
  chaining under E-K1 traps was closed by tick 19; remaining supply is
  BK-38..57 fence-commit landing, blocked on BK-66's posture decision
  chain, or the next NOT-proved bullet).

### 2026-09-28 ~15:0x CDT — MONITOR FIX 2: nested probe-leg status no longer counts as an open ticket (phantom REPAIR_PENDING queue=1 closed, builder af3e62239ce2)

- **Symptom:** on a CLEAN tree the fingerprint read
  `state=REPAIR_PENDING queue=1`; the queue scan's only hit was
  UNTRACKED research DATA
  .builder_queue/probe_bk54_blast_radius_af3e.results.json.
- **Root cause (measured, not inferred):** _ticket_status()
  (tools/glyph_build_chain_monitor.py:134) regex-matched the FIRST
  '"status"' ANYWHERE in the file; the probe results carry nested leg
  statuses ('D1_overflow_401B': {'status': 'OK'}, 'D2_overflow_4001B':
  {'status': 'OK'} — located by recursive walk), so DATA read as an open
  ticket. The 2026-09-21 status-less fix (:195 comment) can't catch this:
  the file HAS status fields, just none at ticket level. Reproduced with
  the monitor's exact old logic: it was the ONLY json in .builder_queue
  with a non-closed first-status match (38 json files scanned; the fix's
  top-level-status read reproduces every other file's classification
  byte-for-byte — verified in a before/after table over the whole queue).
- **Fix:** _ticket_status() now parses JSON and reads only the TOP-LEVEL
  'status' key; regex fallback (non-JSON queue files) anchored to
  line-start via re.MULTILINE. No exemption-by-filename — the class is
  closed structurally (any future probe results file with nested
  statuses is safe by construction).
- **Gates:** new L8 in tests/test_monitor_fingerprint_hygiene.py
  (probe-results-SHAPED scratch json with nested-only statuses must NOT
  move the digest; same body + top-level 'OPEN' MUST move it; removal
  restores baseline). RED leg shown at landing time against the live
  unfixed instrument: digest 692984fb… != baseline 350213e0… (FAILED).
  Post-fix: 8/8 passed (L1-L8), live fingerprint queue=0.
- **NOT proved:** non-JSON queue files (.md tickets) are unaffected by
  the line-anchor change only in the scanned corpus (all real .md
  tickets were status-line-at-col-0; no .md in the queue carries an
  indented quoted '"status"' — checked by grep, not exhaustively by
  class); whether sibling sessions' untracked probe results in OTHER
  directories were ever scanned (they were not — QUEUE_DIR only).

### 2026-09-28 ~14:4x CDT — MONITOR FIX: build-map self-reference churn exemption (permanent-DIRTY_ACTIVE defect root-caused and closed, builder af3e62239ce2)

- **Symptom:** monitor read `tracked_dirty=2 state=DIRTY_ACTIVE` at wake;
  git status showed ONLY build_map.png + build_map_data.json modified.
- **Root cause (measured, not inferred):** build_map_data.json embeds the
  last-400-commit window + frontier_commit + generated_at
  (tools/spatial_build_map.py render()); the BM000 watchdog regenerates it
  every ~5min (glyph_builder_watchdog.py step 7, :421-431). EVERY commit
  makes the committed copy stale, so the next regen re-dirties the tree.
  Measured: my catch-up commit 7ed485e9 landed 19:32:40Z and the tree was
  dirty again at 19:32:51Z (11s) — the regen shifted the 400-window by the
  commit itself, so the committed copy can NEVER converge (no fixpoint
  exists). Second consequence: the churn kept the freshness pool
  permanently warm → FROZEN_STALLED (and its tier escalation/auto-stash
  circuit breaker) unreachable — the same phantom-freshness class as the
  2026-09-19/09-22 exemptions (test_l4/test_l6).
- **Fix:** build_map_data.json + build_map.png added to
  RUNTIME_EXEMPT_FILES in tools/glyph_build_chain_monitor.py (runtime-churn
  exemption pattern, NOT a guard weakening — map content remains repo
  state via HEAD commits, which the fingerprint already carries as `head=`;
  no signal is lost). Live shim (~/.hermes/scripts) runpy's the versioned
  twin, so the instrument picks it up with no deploy step.
- **Gates:** tests/test_monitor_fingerprint_hygiene.py 7/7 GREEN (new L7:
  source pin + live-instrument exclusion leg). RED leg shown at landing:
  `git stash` of the monitor fix → L7 FAILED; `stash pop` → 7 passed.
  Pre-fix live probe on the identical tree: tracked_dirty=1
  state=DIRTY_ACTIVE with only the map dirty (2026-09-28 14:33 CDT).
- **NOT proved:** spatial_build_map.py itself is unchanged (the
  regenerate-then-commit pattern in older ledger entries will keep
  producing one-shot map diffs at landing time — those are now invisible
  to the fingerprint but still land as normal commits when a lane chooses
  to commit them); whether any OTHER consumer depends on the map files'
  tracked-dirty state (none found: grep over tools/ + tests/ shows only
  the monitor and the watchdog writer).
- Next tick: ledger re-read per protocol. SECOND phantom found at the same
  wake: `state=REPAIR_PENDING queue=1` on a clean tree — the queue scan's
  status-regex hits `"status": "OK"` inside the UNTRACKED research results
  file probe_bk54_blast_radius_af3e.results.json (DATA, not a ticket;
  reproduced with the monitor's exact scan logic — it is the only json in
  .builder_queue with a non-closed status string). Named in
  CURRENT_TICKET.json; the scan fix (exclude probe results DATA files) is
  queued as its own next-tick step, not bundled here.

### 2026-09-28 ~14:1x CDT — TWO LANDINGS: (1) research tick 19 VERIFIED+COMMITTED (KFAULT chain closes the dispatch family, 589f4311); (2) GH-28 ruled scratch-window posture LANDED with standing gate (d5d488cd) (builder af3e62239ce2)

- **Tick 19 verification (not re-research):** the KFAULT chain probe was
  found complete-but-uncommitted in the tree at claim (receipt + probe +
  RED leg + results + BK-75 row all present, none in git). Re-verified on
  the live tree BEFORE committing: probe re-run exit 0, results md5
  f161f3ce71735d5d46e56fd788f45797 reproduced BYTE-IDENTICAL (receipt
  match); RED leg re-run exit 0 (K1_red 365x[77], K2_red 162x[77], verdict
  BOTH GREEN SHAPES BROKEN, engine md5 3337fa9943fe9563eda8bb80cc1eb8d7
  untouched); BK-75 row present in systems/GLYPH_BACKLOG.md. Committed as
  589f4311 with the full measured evidence chain in the message.
- **GH-28 landing (d5d488cd):** the ruled RESERVED SCRATCH WINDOW posture
  (tools/map_scratch.py, Hilbert idx [15360,16383], top-right 32x32) was
  implemented in-tree by a parallel session but UNCOMMITTED. This session
  verified and landed it with the standing gate it was missing:
  tests/test_gh28_scratch_window.py — G1 regeneration preserves a
  stamp_scratch() canary (carry-over paste path), G2 history cell stays
  paintable (guard never clips), G3 sbm.stamp() refuses a scratch index;
  RED legs R1 (no-paste regen loses the canary — pre-fix clobber hazard,
  gate detects) and R2 (guard disabled -> stamp paints into the window).
  5 passed in 0.25s, deterministic. Honest scope: the guard branch is
  latent on the live map today (no history data occupies scratch indices
  yet); test canary artifacts cleaned from the live map (window back to
  border+background only); build_map regeneration diff (data.json +2444/-1348
  lines of regenerated coordinates) is the map lane's normal regeneration,
  committed with tick 19's landing.
- Verify evidence: pytest tail (5 passed) and probe RED/GREEN tails in
  session transcript; commit bodies carry the full legs.
- Next tick: ledger re-read per protocol; the dispatch-family research
  thread is COMPLETE (KSYS/KTICK/KFAULT all measured) — remaining supply is
  the BK-38..57 fence-commit landing (blocked on the posture decision being
  taken mechanically per BK-66's ruling chain) or the next NOT-proved bullet.


### 2026-09-28 ~06:5x CDT — PHASE 1c RESEARCH TICK 18: GH-16 PREEMPTIVE-TICK FOOTHOLD — a hostile guest-painted KTICK handler executes from HARDWARE TIME in SUPER (no guest SYSCALL needed to enter), composes with the E-K2 gate from INSIDE the handler, and RE-FIRES periodically via TIMER_RELOAD when it returns through the DEFECT-18 JMPR restore; PLUS two measured engine defects (builder af3e62239ce2)

- Run selection: HEAD a2ac273a at claim (re-verified via git rev-parse;
  monitor fingerprint head matched — the delta vs tick 17's ae4d88b6 is
  my own tick-17 landing). Mailbox re-verified: no RULING_*.md newer
  than HEAD at claim (newest mtime 1790550013 < HEAD commit time).
  QUEUE_STATE.json: active null → Phase 1c eligible. No re-research:
  the question was named by tick 17's NOT-proved bullet ("GH-16 KTICK
  re-arm from a tick handler ... same family by source-read, unprobed")
  and tick 14's carried "TIMER_RELOAD periodic re-fire"; prior-art grep
  BEFORE harness build found tick 14 (one-shot rewrite, payload never
  returns) and tick 17 (SYSCALL-side chain) — no row composes
  tick-entry + E-K2 composition or tick-entry + JMPR return +
  periodicity. Net-new.
- Probe `.builder_queue/probe_ktick_chain_af3e.py` (+ RED leg
  `probe_ktick_chain_red_af3e.py`): real
  GlyphProcessTable.spawn(tile=(256,19,1,2)) posture, cols_instrs=16
  both baker and table, tag 0x505447 at 1535, PT base 1536 armed by the
  task's lawful in-tile ST to 8211; vpn-12 PIX pfn 7 payload paint at
  (31,8)/(30,8); vpn-32 RAM pfn 32 for the 8207/8208/8209 arming
  stores; instruction words from the REAL GlyphAssemblerV2, never
  hand-encoded; verdicts from exit_status + fault fields + cpu.output +
  final PC + RAM readback BYTES, never stdout. 3 pinned runs
  byte-identical, results md5 5abb0574c1156e866e2a2c50bd441403 (file
  probe_ktick_chain_af3e_results.json, file md5
  c9eae24b227a09392c1be811bdb6eba6).
- Legs: T1 TICK-CHAIN (arm TCOUNT=2/TRELOAD=0/KTICK→(31,8) via the
  sanctioned paged walk + spin; handler PRT 77, re-arms ksys←(30,8) via
  the :968 exemption, SYSCALLs; gadget PRT 52, re-arms ksys←0, SYSRET →
  output [77,52], mode USER, NO FAULT, exit 0 — the tick path COMPOSES
  with E-K2 from guest-painted state); T2 RESIDENT RE-FIRE (handler
  returns via LD 8210/JMPR — the DEFECT-18 restore; TRELOAD=2; NO
  SYSCALL anywhere → output [77,77]: attacker SUPER code re-fired from
  hardware time with zero guest syscalls, before the spin died at the
  restore because the recorded resume PC was the jump DESTINATION
  (packed col 73 → (292,0) out-of-image walk-off)); C1 reload=0 →
  [77] once (isolates TIMER_RELOAD); C2 no-arm → [] (arming writes
  create the foothold); C3 periodic + handler never returns → [77]
  once, halt in-handler (the JMPR return is the second persistence
  condition); C4 rot-guard (unpaged out-of-tile USER ST to 8207 → E-K1
  fault_addr 32828, parked (0,30), exit 1 — BK-66-C2 shape, KTICK
  flavor). RED leg: temp-copy engine refusing ALL SUPER MMIO-window
  ST+LD breaks BOTH green shapes ([77]+fault
  super_mmio_window_access_refused each; real engine md5
  3337fa9943fe9563eda8bb80cc1eb8d7 before/after, asserted) — the
  probe discriminates.
- TWO MEASURED ENGINE DEFECTS (filed inside BK-74, fix legs DEF-A/DEF-B):
  (a) SYSRET (:1193-1207) consumes the tick return — resumes USER at
  SYSCALL_PC 8201 unconditionally, never clears the pending
  _tick_pc/_tick_regs (stale-snapshot hazard; T1's composition is
  structurally one-shot because of this); (b) the tick fire
  (:1373-1375) saves next_pc — the jump DESTINATION — as the interrupted
  PC, so a tick landing after a taken jump records a wrong/off-image
  resume PC (T2's spin death; a correctness defect independent of the
  foothold family). Both engine-owned state-machine bugs, fixable
  without weakening E-K2. Debug traces
  dbg_ktick_chain_v1..v6_af3e.py (v2-v6 on disk, debug only, strays
  left for the BM902 owner; v1 removed — NameError pre-evidence).
- Honest catches disclosed: v1 probe used the SYSCALL-composition
  handler for the persistence leg too — SYSRET's resume made every
  periodic variant one-shot; caught by T2 vs C1 output comparison,
  redesigned to the LD-8210/JMPR-return handler pre-evidence. First T2
  trace mislabeled the walk-off "budget exhausted" — corrected by the
  per-step traces before any verdict was recorded.
- Candidate BK-74 filed to systems/GLYPH_BACKLOG.md (BK-66 landing gate
  grows TICK legs L1-L5 + DEF-A/DEF-B fix legs, RED today per the
  measured shapes; takes BK-66's consult posture MECHANICALLY + the
  BK-72/BK-73 exemption-site requirement). NOT proved: twin side (WGSL
  walker has NO GH-16 at all, oracle-only), KFAULT_PC chaining under
  E-K1 traps (last open tick-17 sibling, unprobed), lifetime
  persistence (defect (b) halts the spin shape early), impact of
  DEF-A on landed xv6-nano workloads (source-read: kernel handler
  never SYSCALLs from the tick path, unassessed). NO engine or shader
  code changed — probes + results + receipt + BK-74 row + ledger only.
  Measured at HEAD a2ac273a; 3 pinned runs byte-identical (results md5
  5abb0574c1156e866e2a2c50bd441403). Rule-1 floors do not attach
  (numbers structural). Next tick: KFAULT_PC chaining under E-K1 traps
  (the remaining tick-17 NOT-proved sibling), or drop research if a
  CLAIM QUEUE item or binding RULING appears.

### 2026-09-28 ~06:1x CDT — PHASE 1c RESEARCH TICK 17: SUPER-CHAINED DISPATCH — the E-K2 syscall gate is a RE-ENTRANT foothold: a hostile guest-painted dispatcher, running in SUPER via the :968 MMIO-window exemption, RE-ARMS KSYS_PC (word 8194) to another guest gadget with ONE plain store and RE-ENTERS via its own SYSCALL (the engine re-dispatches from inside the handler: fresh `_syscall_regs` + resume-PC saves), and the gadget re-arms ksys back so the foothold SURVIVES SYSRET — every later plain USER SYSCALL re-enters attacker SUPER code for the task's whole lifetime (builder af3e62239ce2)

- Run selection: HEAD ae4d88b6 at claim (re-verified via git rev-parse;
  monitor fingerprint head matched — the delta vs tick 16's 6fdd5647 is
  my own tick-16 landing). Mailbox re-verified: no RULING_*.md newer
  than HEAD at claim (newest mtime 1790550013 < HEAD commit time
  1790589804). QUEUE_STATE.json 25/25 landed, active null → Phase 1c
  eligible. No re-research: the question was named by tick 15's
  NOT-proved bullet ("SUPER-mode re-arm chaining ... unmeasured",
  RESEARCH_ksys_paged_rewrite_af3e.md:43) and sharpened by tick 16's
  R2 legs (:968 serves a SUPER accessor pre-PTE-consult); prior-art
  grep BEFORE harness build found ticks 12–16 all ONE-SHOT — no row
  composes re-arm + re-entry + persistence. Net-new.
- Probe `.builder_queue/probe_super_chain_af3e.py` (+ RED leg
  `probe_super_chain_red_af3e.py`): real
  GlyphProcessTable.spawn(tile=(256,19,1,2)) posture, cols_instrs=16
  both baker and table, min_rows=64; tag 0x505447 at 1535, PT base
  1536 armed by the task's lawful in-tile ST to 8211; vpn-12 PIX pfn 7
  payload paint; ksys armed HOST-side to dispatcher1 at (28,8) — the
  loader-seed posture; dispatcher1 at (28,8), gadget2 at (31,8), both
  in vpn-12's frame; instruction words from the REAL GlyphAssemblerV2,
  never hand-encoded; verdicts from exit_status + fault fields +
  cpu.output + final PC + RAM readback BYTES (8194/8201/8205/165),
  never stdout. 3 pinned runs byte-identical, results md5
  44210fe90a3efef7d2a4c2e4fc6cecba (file
  probe_super_chain_af3e_results.json, file md5
  4a7544efd47452edda0b8a09fe034dae).
- Legs: T1 THE CHAIN (dispatcher1 PRT 77 → ST ksys←gadget2 → SYSCALL
  r10 7 → engine RE-DISPATCHES to gadget2 → PRT 52 → ST ksys←
  dispatcher1 → SYSRET → output [77,52], mode USER, resumed at the
  TRUE saved PC (56,28), ksys readback 1835016 = the re-arm-back
  LANDED, no fault anywhere, exit 0); T2 single-level control
  (identical minus the two chain steps → [77], program's own HALT
  (4,7) — isolates the mechanism); T3 THE FOOTHOLD PERSISTS (T1 + one
  more plain USER SYSCALL → [77,52] AGAIN — the chain re-executes
  end-to-end from USER because the re-arm survived SYSRET); C1
  non-window control (re-arm store aimed at plain word 165 → chain
  does not advance, [77]×642 self-re-entry loop — confirming T1's
  second dispatch rode the RE-ARM, and that SUPER stores OUTSIDE the
  window walk instead of exempting); C2 rot-guard (unpaged
  out-of-tile USER ST to 8194 → E-K1 fault_addr 32776, parked (0,30),
  exit 1 — BK-66-C2 shape, KSYS flavor). RED leg
  probe_super_chain_red_af3e.py: temp-copy engine refusing SUPER
  MMIO-window stores breaks the chain (output [77], fault
  `super_mmio_window_store_refused`, exit 1; real engine md5
  3337fa9943fe9563eda8bb80cc1eb8d7 before/after, untouched) — the
  probe discriminates.
- Sub-finding (measured, RED-leg v1 kept in the receipt): neutering
  ONLY the :968 exemption does NOT break the chain — the re-arm store
  then takes the paged WALK (vpn-32 PTE pfn 32 maps vaddr 8194 →
  paddr 8194, PTE V|W|U) and lands anyway, output still [77,52].
  TWO serving branches, one fence hole: the 9714a363 walk-side
  paddr-consult posture alone closes NEITHER branch, and the
  exemption branch is unreachable by any translation-side consult —
  the fix must gate the :968 exemption site directly, exactly as
  tick 16's posture question demanded; now MEASURED as load-bearing,
  not just source-read.
- Honest catches disclosed: C1's prediction (non-window SUPER store
  traps via the walk on word 165) was WRONG — vpn-32 legitimately
  maps word 165, so the store LAWSULLY lands and the leg instead
  demonstrated self-re-entry ([77] loop); the leg is retained as the
  re-entry-mechanism control, and the walk-vs-exempt split it
  revealed became the sub-finding above. Probe defect: v1 gadget2 at
  col 24 → pixel x=96 off the 64-px image — the "walk-off" at (96,30)
  was a SUCCESSFUL dispatch to an off-image target (packed PC col×4
  pixels), caught by step-trace (.builder_queue/trace_chain_dbg_af3e.py,
  debug tool, not evidence); fixed to (31,8) pre-evidence. run_leg
  verdict readback moved to task["image"] (spawn may tall-copy).
- Consequence: the five measured control words are not just
  individually writable — 8194 is writable from a hostile SUPER
  context AND the write composes into a persistent re-entrant
  foothold; the kernel's own dispatch mechanism is the attacker's
  call gate. Candidate BK-73 filed to systems/GLYPH_BACKLOG.md
  (BK-66 landing gate grows CHAIN legs L1-L5, RED today per the
  measured shapes; takes BK-66's consult decision MECHANICALLY plus
  the :968-exemption-site gate).
- NOT proved: twin side (WGSL walker has no SYSCALL/SYSRET dispatcher
  — carried, oracle-only); N≥3 chain depth (mechanism unbounded by
  construction, depth 2 measured per SYSCALL); GH-16 KTICK re-arm
  from a tick handler and KFAULT_PC chaining under E-K1 traps (same
  family by source-read, unprobed); `_iso_enabled` guest-flippable
  (word 8196-class, labeled). Steps not pinned; no fix landed —
  research proposes, never lands engine code. NO engine or shader
  code changed — probes + results + receipt + BK-73 row + ledger
  only. Numbers structural, rule-1 floors do not attach.
- Receipt: .builder_queue/RESEARCH_super_chain_foothold_af3e.md

### 2026-09-28 ~04:5x CDT — PHASE 1c RESEARCH TICK 16: SYSRET RESUME-PC HIJACK — SYSCALL_PC (RAM word 8201, CORRECTED from tick 15's "8205" mislabel; 8205 is SYS_A0) is guest-rewritable from INSIDE a hostile SUPER dispatcher the task itself painted, and SYSRET (glyph_isa_v2.py:1193-1208) consumes the rewritten word with NO consult on the packed resume PC: measured output [77, 52] (dispatcher PRT then ATTACKER PRT), mode USER, final PC (40,30) = the attacker gadget's HALT, syspc readback 1966088 = (30<<16)|8, a0 clobbered to 52 — the full USER→SUPER→attacker-chosen-USER round trip, no fault anywhere — versus the clean-dispatcher control's [77] resuming at the TRUE saved PC (56,4) with syspc 262157 = (4<<16)|13 (builder af3e62239ce2)

- Run selection: HEAD 6fdd5647 at claim (re-verified via git rev-parse;
  monitor fingerprint matched; no commits landed mid-tick, all deltas
  this tick's .builder_queue artifacts). Mailbox re-verified: no
  RULING_*.md newer than HEAD at claim (newest mtime 1790550013 <
  1790586900). QUEUE_STATE.json 25/25 landed, active null → Phase 1c
  eligible. No re-research: the question was named by tick 15's
  NOT-proved bullet ("SYSCALL_PC save/restore under a hostile
  dispatcher ... SYSRET-hijack variant unmeasured"); prior-art grep
  BEFORE harness build found NO row measuring word 8201 — but DID find
  a STRAY: an uncommitted probe_sysret_pc_af3e.py (mtime 04:21, never
  landed) that targeted word 8205 believing it was SYSCALL_PC.
- v1 stray + mislabel CORRECTED pre-evidence (disclosed in full): live
  enum read pins SYSCALL_PC_ADDR = 0x8000+0x24 → word 8201; 8205 is
  SYS_A0 (0x8034>>2 — v1's own C2 fault line says so). v1 was also
  double-blind: the engine overwrites SYS_A0 at dispatch marshal (:1178)
  and consumes it at SYSRET (:1201), so v1's T1 could not discriminate
  anything about the resume PC. Tick 15's landed receipt + ledger row
  carried the same 8205=SYSCALL_PC mislabel (the :1183 line cites were
  right, the word number wrong) — THIS row and the BK-72 backlog row
  carry the correction; the stray file is left on disk uncommitted for
  the BM902 owner, this lane does not adopt it.
- Probe `.builder_queue/probe_sysret_pc_v2_af3e.py` (+ _r1_control.py +
  _r2_discrimination.py): real GlyphProcessTable.spawn(tile=(256,19,1,2))
  posture, cols_instrs=16 both baker and table, min_rows=64; tag
  0x505447 at 1535, PT base 1536, PT armed by the task's lawful in-tile
  ST to 8211; ksys armed HOST-side to (28,8) — the loader-seed posture
  the E-K2 comment describes (:1171) — pointing at a dispatcher the
  guest painted at words 1856..1899 via vpn-12 PIX pfn 7 (LDI r9 77 /
  PRT r9 / ST 1966088→8201 / ST 52→8205 / SYSRET); attacker gadget LDI
  r2 52 / PRT r2 / HALT at words 1952..1963 (same frame); instruction
  words from the REAL GlyphAssemblerV2, never hand-encoded; verdicts
  from exit_status + fault fields + cpu.output + final PC + RAM
  readback BYTES (8194/8201/8205), never stdout. 3 pinned runs
  byte-identical per results file: v2 results md5 (file)
  97a9828cb6045d4c448767e44df8a6c2 / probe-print
  24b21e6b9de4a95462c6c965bccc1561; R1 control (file)
  66db71c3672852cfbfeb261f29584a9a; R2 discrimination (file)
  29a9b765a4b8aa28dc752a577d2620c4 / probe-print
  3bf3ed639e2683000f7e70f9ece9c795.
- Legs: T1 hijack (dispatcher paged-writes 8201=1966088 + 8205=52 then
  SYSRET → output [77,52], mode USER, final PC (40,30) = the gadget's
  HALT, syspc 1966088, sysa0 52 — resume control STOLEN, no fault);
  T2 clean-dispatcher control (identical minus the two stores → [77],
  PC (56,4), syspc 262157 — the engine's TRUE saved resume PC, decoded;
  T1 vs T2 isolate the mechanism to the two stores); R1 arm-PT-
  zero-PTE control (SYSCALL under armed PT + tag with ZERO PTEs →
  dispatch + walk-off parking on the dispatcher's last painted pixel
  (32,28), syspc 5, mode SUPER — a paged-armed task CAN take the :968
  exemption branch and dispatch); R2a HOST-written correct PTEs →
  identical to T1; R2b stamp-fate (never run) → guest PTE stamps land
  IMAGE-ONLY (RAM PTE words read 0); R2c HOST-written WRONG-frame PTE
  pfn 0 → identical to T1 with RAM word 0 UNCLOBBERED; C2 rot-guard
  (unpaged out-of-tile ST to 8201, no PT → E-K1 trap, parked (0,30),
  exit 1 — tile fence LIVE for the word when translation is unarmed).
- Honest catch (NOT buried): C1's pre-registered prediction (no
  translation → the dispatcher's ST pte_invalids mid-dispatch) is
  FALSIFIED by its own measured leg — C1 came back BYTE-IDENTICAL to
  T1. Diagnosis (mechanism verdict measured via R2a/R2b/R2c; the
  fault-path ordering read itself is source-read, labeled): the
  SUPER-mode MMIO-window exemption (:968) fires BEFORE any PTE consult,
  so the dispatcher's stores never touch the walk — there is no fault
  to take. **Consequence for the fix posture: the 9714a363
  paddr-consult ruling does NOT engage for a SUPER accessor — the
  frame the PTE names is irrelevant (R2c proves it: wrong-frame PTE,
  RAM word 0 unclobbered, rewrite still lands). The fence must gate the
  :968 exemption site itself.** The probe docstring keeps the failed
  prediction verbatim; results file has the measurement; this row is
  the adjudication.
- Consequence: the paged-rewrite family is now measured at FIVE control
  words + the trampoline pixels (8193 tick-13, 8194 tick-15, 8201 this
  tick, 8207/8208 tick-14, 960..963 tick-12) — one fence shape, whole
  8192..8210 span, PLUS the new SUPER-exemption posture. Value-pinning
  8201 is viable (unlike GH-16, the kernel is the only legitimate
  writer of the resume PC). a0 delivery (:1201) gives the round trip a
  data channel, not just control flow. Candidate BK-72 filed to
  systems/GLYPH_BACKLOG.md (BK-66's gate grows SYSPC legs L1-L4, RED
  today per the measured shapes).
- NOT proved: twin side (WGSL walker has no SYSCALL/SYSRET dispatcher —
  tick-15 source-read label stands; oracle-only); the :889-889
  RAM-before-image PTE ordering under a hostile dispatcher's fault
  (unreachable — the exemption short-circuits the walk; source-read +
  R2b-adjacent, labeled); USER-side race against :1183's save
  (structurally impossible single-task single-stepped; not probed);
  MODE_LATCH/BOX lo-hi words, TIMER_RELOAD periodic re-fire (carried
  from ticks 14/15). NO engine or shader code changed — probes +
  results + receipt + BK-72 row + ledger only; build_map.* left to the
  build-map lane. Numbers structural, rule-1 floors do not attach.
- Receipt: .builder_queue/RESEARCH_sysret_resume_hijack_af3e.md
- Ledger correction carried: tick 15's entry and receipt said
  "SYSCALL_PC word 8205"; correct is word 8201 (8205 = SYS_A0). The
  BK-72 backlog row and this entry are authoritative on the word
  numbers; tick 15's T1 dispatch-mechanism finding is unaffected (its
  verdicts — output/mode/ksys — never depended on the mislabeled word).

### 2026-09-28 ~04:4x CDT — PHASE 1c RESEARCH TICK 15: KSYS_PC (word 8194, the E-K2 syscall-dispatcher control word) is PAGED-REWRITEABLE — a tile-confined USER task points the SUPER dispatcher at its own painted gadget with ONE plain paged ST (ST 1966088→vaddr 8194, vpn-32 plain-frame PTE pfn 32, paddr 8194 OUTSIDE tile words {8211,8212}), then a SINGLE SYSCALL executes attacker code in SUPER — cpu.output [52], mode SUPER, ksys word 1966088, NO FAULT, NO parallel opcode — closing the last open sibling of ticks 13/14's NOT-proved line and confirming the paged-rewrite family is GENERIC across the BOX_MMIO block below the tile (KFAULT_PC 8193 tick-13, KSYS_PC 8194 this tick, KTICK_PC/TIMER_COUNT 8207/8208 tick-14 — four dispatch mechanisms, one fence shape) (builder af3e62239ce2)

- Run selection: HEAD a7c6af41 at claim (re-verified via git
  rev-parse; delta vs tick 14 is my own tick-14 landing). Mailbox
  re-verified: no RULING_*.md newer than HEAD at claim (newest mtime
  1790550013 < HEAD commit time); QUEUE_STATE.json 25/25 landed,
  active null → Phase 1c eligible (monitor CLAIM_PENDING queue=0 is
  the standing research posture, same shape as ticks 5–14).
- Prior-art grep BEFORE harness build: BK-41 (KSYS_PC UNPAGED
  PARALLEL_ST self-arm, tile=(5,0,8,8), NO page table — different
  write primitive), BK-40 (syscall DATA handlers, different surface),
  ticks 12/13/14 (KFAULT_PC/KTICK_PC+TIMER_COUNT, different words and
  dispatchers) — no row measures a paged guest write to word 8194.
  Net-new.
- Probe `.builder_queue/probe_ksys_paged_af3e.py`: real
  GlyphProcessTable.spawn(tile=(256,19,1,2)) posture, cols_instrs=16
  on BOTH baker and table, min_rows=64; tag 0x505447 at 1535, PT base
  1536 armed by the task's lawful in-tile ST to 8211; vpn-32 PTE
  V|W|U pfn 32 (plain RAM frame); gadget LDI r2 52/PRT r2/HALT
  painted via vpn-12 PIX pfn 7 at words 1952..1963 (instruction words
  from the REAL GlyphAssemblerV2, never hand-encoded colors); trigger
  one SYSCALL r10 6; verdicts from exit_status + fault fields +
  cpu.output + RAM readback (8193/8194/8205/8210) + final PC BYTES,
  never stdout. 3 runs byte-identical, results md5
  2c41913fb04c5532497c03b570291b16 (file
  .builder_queue/probe_ksys_paged_af3e_results.json; file md5
  aa92337e22da8e191c9d20e194f233d5 — wrapper adds results_md5).
- Legs: T1 compose (rewrite+syscall → output [52] at the task-chosen
  pixel, mode SUPER, exit 0, no fault; final PC (40,30) = the
  gadget's HALT; SYSCALL_PC word 8205 readback 0 — the gadget HALTs
  without SYSRET, disclosed, dispatch proven by output+mode+ksys
  which are unambiguous); C1 no-rewrite control (identical program
  minus the ST pair → ksys 0, DIRECT fence-blind handler serves
  syscall 6 inline, output [], mode USER — dispatch required the
  paged write); C2 no-translation control (vpn-32 PTE 0 → rewrite ST
  pte_invalids vaddr 0x8008, fault_addr 32776, vectors to the REAL
  trampoline (0,30), parked exit 1, ksys 0 — no unpaged fence hole);
  C3 rot-guard (unpaged out-of-tile ST to 8194, no PT → E-K1 trap
  fault_addr 32776, reaper, exit 1 — BK-66-C2 shape, KSYS flavor).
- Consequence: the SANCTIONED translation path (not BK-41's
  fence-blind parallel-opcode class) takes over E-K2: one ST + one
  syscall = USER→SUPER arbitrary-pixel execution. Mechanically
  covered by Jericho's 09-28 paddr-posture ruling (9714a363: paddr
  8194 < 8211, consult traps it) — receipt filed as MEASURED
  CONFIRMATION for the BK-66 landing gate, NOT a new row.
  Recommended additive BK-66 gate leg: KSYS leg — paged ST to the
  BOX_MMIO window below the tile must trap under the paddr consult
  (RED today: T1 lands), C1/C3 stay green (BK-41's unpaged legs and
  host-side loader seeding unchanged). The leg should fence the WHOLE
  8192..8210 span — all four dispatch words are now measured in the
  family, not word-by-word.
- NOT proved: twin side (WGSL walker has no SYSCALL dispatcher —
  source-read labeled; oracle-only); SUPER-mode re-arm chaining (the
  :971-972 SUPER MMIO exemption makes config-block stores legal from
  a hijacked handler — unmeasured); SYSCALL_PC save/restore under a
  hostile dispatcher (T1 readback 0; SYSRET-hijack variant
  unmeasured); MODE_LATCH/BOX lo-hi words (same window, same shape,
  labeled assumption, not individually probed); TIMER_RELOAD
  periodic re-fire (carried from tick 14). NO engine or shader code
  changed — probe + results + receipt + ledger only; build_map.*
  left to the build-map lane. Numbers structural, rule-1 floors do
  not attach.
- Receipt: .builder_queue/RESEARCH_ksys_paged_rewrite_af3e.md

### 2026-09-28 ~04:0x CDT — PHASE 1c RESEARCH TICK 14: the GH-16 PREEMPTIVE-TICK control block is PAGED-REWRITEABLE and TASK-SELF-ARMABLE — a tile-confined USER task arms the timer ITSELF (paged ST 2→TIMER_COUNT word 8208) and redirects the dispatcher (paged ST (30<<16)|8→KTICK_PC word 8207) through translation (vpn-32 plain-frame PTE pfn 32, vaddrs 8207/8208→paddrs 8207/8208, both OUTSIDE tile words {8211,8212}), then an infinite USER spin forces the preemptive fire: the handler SUPER-executes attacker PRT code painted at (32..35,30) with the fence disabled — cpu.output [8207], mode SUPER, TICK_PC word 8210 = 65542, NO FAULT REQUIRED — a SECOND fence-blind USER→SUPER path independent of BK-41's KSYS_PC family and of ticks 12/13's post-fault vectoring (builder af3e62239ce2)

- Run selection: HEAD 9714a363 at claim (re-verified via git rev-parse;
  the delta vs tick 13's 68ab13e6 is the build-map lane's b6b5774e +
  Jericho's BK-66 paddr-posture ruling 9714a363 — mailboxed and COVERED
  below, see relation note). Mailbox re-verified: no RULING_*.md newer
  than HEAD at claim (newest mtime 1790550013 < 1790584818);
  QUEUE_STATE.json 0 non-landed tickets, active null → Phase 1c
  eligible (monitor CLAIM_PENDING queue=0 is the standing research
  posture, same shape as ticks 5–13).
- Prior-art grep BEFORE harness build: BK-41 (KSYS_PC UNPAGED
  PARALLEL_ST self-arm), ticks 12/13 (post-FAULT reaper vectoring),
  DEFECT-18 gate (timer armed HOST-side, cooperative, no containment) —
  no row measures a guest rewrite of the GH-16 block from a contained
  task. Net-new.
- Probe `.builder_queue/probe_ktick_paged_af3e_v2.py`: real
  GlyphProcessTable.spawn(tile=(256,19,1,2)) posture, cols_instrs=16 on
  BOTH baker and table, min_rows=64; tag 0x505447 at 1535, PT base 1536,
  PT armed by the task's in-tile ST to 8211; vpn-32 PTE V|W|U pfn 32
  (plain RAM frame); payload paint via vpn-12 PIX pfn 7 (tick-12/13
  shape) at words 1952..1955; verdicts from exit_status + fault fields +
  cpu.output + RAM readback (8193/8207/8208/8209/8210) + final PC BYTES,
  never stdout; PRT color runtime from OpcodeMapV2. 3 pinned runs
  byte-identical, results md5 0ed5acf14928b57448287bf243cf8e1f (file
  .builder_queue/probe_ktick_paged_af3e_v2_results.json).
- Legs: T1 compose (arm+redirect+paint+spin → output [8207] = attacker
  PRT executed at the task-chosen vector in SUPER, mid-spin, faultless;
  tcount engine-decremented to 0; loud opcode-None tail at (36,30)
  disclosed, tick-9-F2 shape); C1 no-count-write control (tick never
  fires, spin burns max_instructions in USER, output []) — the ARming
  write is itself the privileged state change; C2 no-translation control
  (count ST pte_invalids vaddr 0x8040, vectors to the REAL trampoline
  (0,30), parked exit 1, control words 0); C3 rot-guard (unpaged
  out-of-tile ST to 8208 traps E-K1 fault_addr 32832 — tile fence live
  without translation, BK-66-C2 shape, GH-16 flavor).
- Consequence: unlike KFAULT_PC there is NO kernel-armed value to pin —
  GH-16's legitimate config in this posture is task-written by design
  (xv6-nano seeds it host-side), so the fix posture must make the whole
  8207..8210 window task-unwritable, not value-pinned. The 09-28 Jericho
  ruling (9714a363, paddr-side consult post-translation) covers this
  finding MECHANICALLY (rewrite paddrs 8207/8208 outside tile words,
  verified numerically) — receipt filed as MEASURED CONFIRMATION for the
  BK-66 landing gate, NOT a new row; recommended additive KTICK leg:
  paged ST to 8207..8210 must trap under the paddr consult (RED today:
  T1 lands), C1/C3 stay green.
- Probe defects disclosed, both caught pre-evidence: (1) run-1 painted
  the payload AFTER arming → tick fired mid-paint onto still-zero pixels
  (finding invisible, not wrong) — fixed to paint-before-arm +
  fire-in-spin; (2) spin used LDI r32 → IndexError (registers file is
  32 wide) → r30.
- NOT proved: twin side (WGSL walker has NO GH-16 at all — no KTICK ref
  in wgsl_glyph_isa_v2.py, source-read labeled; escape is oracle-only
  today); KSYS_PC paged rewrite (the other half of tick 13's
  NOT-proved line; BK-41 measured the UNPAGED self-arm only);
  TIMER_RELOAD periodic re-fire (T1 one-shot, reload 0); engine's own
  TIMER_COUNT decrement as an observation primitive; interrupted-PC
  arithmetic at (1,6) vs my spin model (mechanism verdict does not
  depend on it — disclosed in the receipt). NO engine or shader code
  changed — probe + results + receipt + ledger only. Numbers structural,
  rule-1 floors do not attach.
- Receipt: .builder_queue/RESEARCH_ktick_paged_rewrite_af3e.md

### 2026-09-28 ~01:1x CDT — PHASE 1c RESEARCH TICK 13: the KFAULT_PC VECTOR WORD itself is PAGED-REWRITEABLE — a tile-confined task overwrites the trap arm's RAM word (8193) with ONE plain-page ST through translation (vpn-33 V|W|U PTE pfn 32, vaddr 8449 → paddr 8193; NO PIX frame, NO MMIO exemption needed since the task is USER), the next pte_invalid fault vectors through the LIVE kf read to the TASK-CHOSEN pixel (32,30) instead of the planted trampoline (0,30), and composed with tick-12's pixel-paint the trap EXECUTES attacker code at the attacker-chosen vector (V2: cpu.output [3235] in SUPER) — full control of the containment mechanism's control flow, both where the trap goes and what runs when it arrives (builder af3e62239ce2)

- Run selection: HEAD 45a8ed79 at claim (re-verified via git rev-parse;
  monitor fingerprint matched — the delta vs tick 12's fbdef1be is my
  own tick-12 landing). Mailbox re-verified: newest RULING_*.md mtime
  1790550013 < HEAD commit time — no binding new work. QUEUE_STATE.json:
  0 non-landed tickets; CLAIM QUEUE empty → Phase 1c eligible.
  Rule-5 prior-art grep BEFORE harness build: BK-52 (unpaged vector
  family), BK-53/55 (unpaged hijack primitives; the blind-WRITE variant
  called "not dead" in RESEARCH_postfix_hijack_recheck), BK-70/tick-12
  (pixel half; vector word explicitly UNMEASURED), BK-56 (read de-fang,
  write out of scope) — no row measures a paged USER ST landing in the
  vector word. Net-new.
- Probe `.builder_queue/probe_kf_paged_af3e.py`: the REAL
  GlyphProcessTable.spawn(tile=(256,19,1,2)) posture, cols_instrs=16 on
  BOTH baker and table; PT armed by the task's own lawful in-tile ST to
  word 8211; tag 0x505447 at 1535, PT base 1536; verdicts from
  exit_status + fault fields + kf RAM readback + cpu.output +
  redirect-pixel readback BYTES, never stdout; PRT color from
  OpcodeMapV2 at runtime. Results verified this session by an
  independent re-run at HEAD 45a8ed79: on-disk results file
  byte-identical, deterministic results md5
  4724518667afe20696053e53f6be56a8 (file md5
  0ed2499041b6da0226ac48dab43fb6a3; the originally-pinned run md5
  6cd043ba1ce078a3714ad9a3b891b0dd was superseded — see the receipt's
  correction note). ORACLE ONLY (twin has no tile
  predicate, BK-51).
- Findings: V1 — one USER ST rewrites kf word to 1966088 = (30<<16)|8;
  the unmapped-vpn fault vectors to final_pc (32,30) = x = 8*4, NOT the
  planted (0,30); C1 no-translation control: the rewrite ST itself
  pte_invalids (vaddr 0x8404), kf stays 1966080, REAL HALT intact;
  C2 rot-guard: tick-12 R1 verbatim green. V2 THE COMPOSE — PIX stores
  paint `PRT r6` at exactly (32..35,30) (words 1952..1955, where the
  redirected vector lands): cpu.output == [3235] — attacker code
  EXECUTED at the task-chosen vector in SUPER (loud opcode-None tail at
  (36,30) disclosed, tick-9-F2 shape).
- Consequence: tick-12's pixel rewrite + this vector rewrite compose
  into FULL trap control (where it goes AND what executes); BK-56's
  read de-fang irrelevant (the rewrite is blind); every kf read site
  (:851/:890/:983/:1016/:1061/:1086) is guest-data-driven in paged
  postures; BK-52's unpaged-only vector-guard scope is insufficient —
  the fix must cover the RAM vector word AND the image trampoline AND
  survive the paged arms. Candidate BK-71 filed to
  systems/GLYPH_BACKLOG.md (BK-66/70 gate grows KF legs — L1 kf not
  paged-writable RED today, L2 post-trap PC == kernel-armed vector RED
  today, L3 honest-catch green, L4 no-translation rot-guard; takes
  BK-66's consult-posture decision mechanically).
- Probe defects disclosed, all caught pre-evidence: (1) PIX-PTE rewrite
  landed in IMAGE word 1 via the mod w*h wrap (the vector word is RAM —
  needs a PLAIN page); (2) cols_instrs 8 (table default) vs 16 (baker)
  mismatch wrapped instruction rows mid-sequence and corrupted a stored
  immediate (r6 got 0xC8B for a 3209 LDI — caught by per-step trace);
  (3) 32px image walk-off at the redirect target (widened to 16
  cols_instrs).
- NOT proved: twin side (BK-51); SUPER-mode MMIO-window direct writes
  (spawn(tile=...) is USER by construction); tag-mismatch/ceiling fault
  sites re-vectoring (same LIVE-read shape by source read, labeled);
  GH-16 KTICK_PC and KSYS_PC (same family, not probed); steps not
  pinned; no fix landed — research proposes, never lands engine code.
  Numbers structural, rule-1 floors do not attach.

### 2026-09-28 ~00:1x CDT — PHASE 1c RESEARCH TICK 12: the item-29 REAPER TRAMPOLINE is PAGED-REWRITEABLE — a tile-confined task arms paging with one lawful in-tile ST (BK-66), rewrites the containment mechanism's own catcher THROUGH TRANSLATION (vpn-12 PIX PTE pfn 3, vaddrs 3264..3267 → trampoline words 960..963; real HALT 16737095 gone, readback [16208720 = the REAL PRT color, 6, 52, 0]), then DELIVERS SUPER-mode execution at the catcher via a pte_invalid fault on an unmapped vpn it chooses (R3: trap vectors KFAULT_PC → rewritten trampoline, cpu.output [3267] = attacker PRT executed IN SUPER, loud opcode-None tail at (4,30) disclosed; exit 1 — not rc-silent, EXECUTION-silent); C1 unpaged control: the same first store E-K1s (fault 13056) and the REAL HALT survives; C2 no-rewrite control: fault vectors to the REAL HALT, no output — execution needs BOTH halves; R1 honest-catch rot-guard: unmapped fault under armed paging + intact trampoline parks clean (builder af3e62239ce2)

- Run selection: HEAD fbdef1be at claim (re-verified via git rev-parse;
  monitor fingerprint matched — the delta vs tick 11's 7f572095 is my
  own tick-11 landing). Mailbox re-verified: newest RULING_*.md mtime
  1790550013 < HEAD commit time — no binding new work. QUEUE_STATE.json:
  0 non-landed tickets; CLAIM QUEUE empty → Phase 1c eligible.
  Rule-5 prior-art grep BEFORE harness build: BK-52 (kf=0, unpaged),
  BK-53/55 (vector hijack via UNPAGED primitives), BK-66 (paged data
  words, trap path never fires), BK-67/68/69 (JMPR legs, no trap) — no
  row composes paging x reaper-trampoline. Net-new.
- Probe `.builder_queue/probe_reaper_paged_af3e.py`: the REAL
  GlyphProcessTable.spawn(tile=(256,19,1,2)) posture — the TABLE arms
  the reaper (kf word 8193 read back 1966080 = (30<<16) in every leg)
  and wrap_with_reaper plants HALT at pixel (0,30) = word 960; PT armed
  by the task's own lawful in-tile ST to word 8211; tag 0x505447 +
  PTEs image-stamped per the corrected BK-60-L4 discipline; verdicts
  from exit_status + fault fields + cpu.output + trampoline readback
  BYTES, never stdout. 3 runs byte-identical, results md5
  124e62289d7882fbc4cb9a6a481e1447. ORACLE ONLY — the twin has no tile
  predicate (BK-51) so a contained-spawn reaper leg is not expressible
  on-device until BK-51 lands.
- Consequence: the containment posture is self-defeating under
  composition — the reaper exists so a trapped task cannot
  replay-and-land (BK-52), but its trampoline lives in the image plane
  BK-66's paged stores write fence-blind, and the trap (the one
  mechanism that runs with the fence DISABLED, SUPER) becomes the
  delivery vehicle — cheaper than BK-53's hijack (no fence-blind
  PARALLEL_ST; every store is a lawful translation). Binds BK-66's
  flagged vaddr-vs-paddr consult decision to the reaper family.
  Candidate BK-70 filed to systems/GLYPH_BACKLOG.md (BK-66's gate grows
  RPR legs — L1 trampoline not paged-writable, RED today; L2 post-trap
  execution refused, RED today; L3 R1 honest-catch green; L4 C1
  unpaged rot-guard; takes BK-66's posture decision mechanically).
- NOT proved: twin side (no tile predicate, BK-51); a paged rewrite of
  KFAULT_PC word 8193 itself (left unmapped this tick — vpn-32 pfn
  coverage of the box_mmio window is plausible by the same shape,
  UNMEASURED); HILB-frame rewrites (PIX covers the frame class,
  labeled); SUPER-mode spawned tasks (spawn(tile=...) is USER by
  construction); refined payload operand placement (the measured PRT
  printed r6=3267, the immediate pixel held 52 — finding unaffected).
  NO engine or shader code changed — probe + results + receipt + BK-70
  row + ledger only. Numbers structural — rule-1 floors do not attach.

### 2026-09-28 ~05:5x CDT — PHASE 1c RESEARCH TICK 11: PAGED FETCH measured on BOTH engines — fetch is MMU-BLIND as well as fence-blind: arming GH-17 paging does NOT confine or redirect instruction fetch (P1/T-P1 discriminators: vpn-0 PTE maps vaddr 0 to an all-zero frame, both engines still execute the program's own row-0 text clean, r10=0x0ADF00D — had fetch translated, the first fetch would have opcode-None halted at step 0), and the composition lands: four paged USER STs (vpn-12 PIX PTE 0x50F pfn 5) write `LDI r10 canary` pixels to image words 1280..1283 = row 40 OUT of tile, JMPR executes them — ARBITRARY CODE INJECTION + EXECUTION WITH PAGING ARMED on BOTH engines (P2: oracle exit 0 r10=0x0ADF00D USER; T-P2: twin r10=0x0ADF00D, injected pixel readback 15487056 = the real LDI color, USER end-to-end, 19 steps); C2 proves the paged path is what landed it (unpaged ST to the SAME physical word 1280 E-K1s at fault 5120); candidate BK-69 filed to systems/GLYPH_BACKLOG.md — paging and fetch confinement are ORTHOGONAL; BK-67/68's code-plane verdict extends to ALL postures (builder af3e62239ce2)

- Run selection: HEAD 7f572095 at claim (re-verified via git rev-parse;
  monitor fingerprint head matched). Mailbox re-verified: newest
  RULING_*.md mtime 1790550013 < HEAD commit time — no binding new
  work. QUEUE_STATE.json: 0 non-landed tickets, active empty → Phase 1c
  eligible. No re-research: the question was named by tick 10's
  NOT-proved bullet 1 ("paged fetch on the twin (walk_ld's PTE-fetch
  fallback :384-394 ...)") and tick 9's source-read note ("fetch never
  translates on the oracle BY SOURCE READ :753 — the paged-fetch
  sibling is a source-read note, not probed"); rule-5 grep BEFORE
  harness build: BK-60..66 are data arms, BK-67/68 explicitly unpaged,
  no row arms a page table and measures fetch.
- Probe `.builder_queue/probe_paged_fetch_af3e.py`: oracle harness =
  real spawn(tile=(256,19,1,2)) posture (same tile as ticks 8/9; PT
  armed via the task's own lawful in-tile ST to word 8211), tag 1535 +
  PTEs image-stamped per the corrected BK-60-L4 discipline; twin
  harness = the proven BK-49/50/51/55/68 device buffers +
  build_shader(OpcodeMapV2()), box [1200,1300) via mmio[3]/mmio[4],
  seeded USER. Injected opcode color from OpcodeMapV2 at runtime,
  never hand-encoded. 3 runs byte-identical, results md5
  0f70ee38b28576de3362eb5a28896a65.
- Findings: P1/T-P1 fetch discriminators — arm PT, vpn-0 PTE 0x50F
  (pfn 5) maps vaddr 0 to an all-zero frame; `LDI r10 canary` from row
  0 executes clean on BOTH engines (oracle exit 0 USER; twin 5 steps):
  fetch does NOT translate on either engine. Source confirmed
  pre-probe: oracle step() reads image[y,x..x+3] raw
  (glyph_isa_v2.py:753-764, no pt_base consult); twin main()
  load_pixel raw (wgsl_glyph_isa_v2.py:506-509); walk_ld's :384-394
  "PTE-fetch" is the DATA walker fetching the PTE itself — the tick-10
  NOT-proved bullet's pointer was a mis-read of that comment, the
  instruction-fetch surface has no paged path AT ALL (that is the
  finding, sharper than "not measured"). P2/T-P2 composition — four
  paged USER STs (vaddrs 3072..3075, vpn-12 PIX PTE) write the 4
  canary-LDI pixels to image words 1280..1283 = row 40 OUT of tile
  rows 256..257, then JMPR (0,40): BOTH engines execute the injected
  LDI (oracle: exit 0, r10=0x0ADF00D, injected pixel readback
  15487056 = the real LDI color, USER end-to-end, loud opcode-None
  halt at (4,40) on the zero pixel after the payload, the tick-9-F2
  shape, disclosed; twin: r10=0x0ADF00D, injected pixel = real LDI
  color, 19 steps). ARBITRARY CODE INJECTION + EXECUTION WITH PAGING
  ARMED — the strongest containment posture the stack offers. C1
  unpaged out-of-tile ST 164 traps 656 (tick-8 C2 verbatim); C2
  unpaged ST to word 1280 — the SAME physical word P2 writes clean —
  traps 5120: the E-K1 fence guards that word when unpaged, proving
  P2's landing went through the paged path (probe discriminating);
  C3 armed-PT in-program JMP control green; T-C1 twin unpaged ST to
  vaddr 3072 traps fault_addr_word 12288 mode→SUPER.
- Consequence: paging (GH-17) and fetch confinement are ORTHOGONAL —
  a task loses its data fence by arming paging (BK-66) AND injects +
  executes code through the translation path in the same program;
  there is NO executable/read-only page distinction in either engine
  (PTE_W gates data stores only, oracle-side, per BK-64); BK-67/68's
  "code plane has NO fence" verdict extends from the unpaged posture
  to ALL postures — unpaged, paged, tile-armed, box-armed. Candidate
  BK-69 filed to systems/GLYPH_BACKLOG.md (measured-completion
  sibling: BK-67's gate grows PGED legs — L1 armed-PT fetch
  discriminator rot-guard, L2 paged injection RED today, L3 C2
  unpaged E-K1 rot-guard; takes BK-67's flagged posture decision
  mechanically once decided for both engines).
- NO engine or shader code changed — probe + receipt + BK-69 row +
  ledger only. Rule-1 floors do not attach — numbers structural (word
  values, addresses, fault codes, step counts, md5s).
- Next tick: new queue supply or RULING if it appears, else Phase 1c.

### 2026-09-28 ~05:1x CDT — PHASE 1c RESEARCH TICK 10: WGSL TWIN FETCH CONFINEMENT measured ON-DEVICE — the shader reproduces tick 9's oracle verdict at the box boundary: fetch (wgsl :506-509) + every jump arm have ZERO addr_in_box consults, a seeded-USER task executes PRE-BAKED out-of-box code pixels clean (D1: JMPR to row 40, r10=0x0ADF00D, mode USER, fault 0), and BK-49's fence-blind image-plane PUSH composes with JMPR into ARBITRARY CODE INJECTION + EXECUTION on the GPU in USER end-to-end (D2: PUSH-writes 4 canary-LDI pixels to row 50 then JMPR — r10=0x0ADF00D, injected opcode pixel readback 15487056 = the real LDI color from OpcodeMapV2): C1 E-K1 control traps fault 400 mode→SUPER in the SAME harness (box arming LIVE — probe discriminating); the code plane has NO fence on EITHER engine (builder af3e62239ce2)

- Run selection: HEAD 89f0444a at claim (re-verified via git rev-parse;
  monitor fingerprint head matched). Mailbox re-verified: newest
  RULING_*.md mtime 2026-09-27 18:00 < HEAD commit time — no binding new
  work. QUEUE_STATE.json: 0 non-landed tickets, active empty, all three
  remedy-* landed → Phase 1c eligible. No re-research: this tick is the
  NOT-proved sibling of tick 9 (its receipt lists "WGSL twin (no tile
  harness, BK-51)"); sibling-tick pattern (5→6, 6→7). geo-obs canvas
  checked per teleop discipline: age_seconds 726,746 (tick 0, write_id
  75, 2026-09-19) — STALE, no conclusion drawn from it; the instrument
  is the host-side device harness (RTX 5090, wgpu).
- Probe `.builder_queue/probe_wgsl_fetch_confinement_af3e.py`: harness =
  the proven BK-49/50/51/55 device buffers + build_shader(OpcodeMapV2()),
  probe-only seeded cpu.mode=1, box [1200,1300) BYTES armed via
  mmio[3]/mmio[4]; bake cols_instrs=8 min_rows=64 (32 px/row scanline
  units, same discipline as the oracle probe); canary 0x0ADF00D;
  injected opcode color resolved at runtime from OpcodeMapV2, never
  hand-encoded. Probe defect disclosed: C1 v1's fired-predicate expected
  a box-relative fault (negative) — the twin's FAULT_ADDR reports the
  RAW byte address 400 (the BK-49-D4 shape); caught by run-1 showing
  fired:false alongside fault 400 + mode SUPER, fixed BEFORE the 3
  pinned runs. 3 runs byte-identical: stdout md5
  b9ab21c8775cb170486595e3d0d346d1, results md5
  4940f4344fa679a1a70e8f244b30f4c0.
- Findings: S1 source — fetch block + JMPR/JMP/CALL/RET/CALLR each
  carry 0 addr_in_box refs and set next_pc; PUSH is mem_write unguarded.
  D1 — seeded-USER JMPR to pre-painted canary-LDI at image row 40 (out
  of box): clean exit, 4 steps, r10=0x0ADF00D, mode USER,
  fault_addr_word=0, injected opcode pixel readback = real LDI color.
  D2 — full injection composition (PUSH 4 pixels to row 50 via
  BK-49's primitive, then JMPR): clean exit, 16 steps, r10=0x0ADF00D,
  mode USER end-to-end, fault 0, injected pixel = real LDI color
  (r31 end 1603 = the PUSH footprint, disclosed). C1 — plain
  seeded-USER out-of-box ST traps fault_addr_word=400, mode→SUPER,
  3 steps: box arming LIVE in the exact harness where D1/D2 execute
  out-of-box. C2 — in-box ST control clean.
- Consequence: the twin REPRODUCES tick 9's verdict at the box boundary
  — the code plane (image pixels) has NO fence on EITHER engine; the
  tile/box predicates are DATA-plane only (twin has no tile predicate
  at all, BK-51). BK-38..57's sequenced fence commit cannot be
  Python-only OR ST-only: fetch + jump arms are the last unconsulted
  execute-side surface family on BOTH engines. Candidate BK-68 filed to
  systems/GLYPH_BACKLOG.md as a measured-completion sibling: BK-67's
  gate grows twin legs (T-L1/T-L2 RED today = D1/D2's clean shapes,
  T-L3 ST rot-guard); the flagged posture decision
  (execute-confine PC vs code-plane box vs spawn-pinned executable
  rows) is taken ONCE for both engines in the same round — the twin leg
  is mechanical after that ruling. NOT proved: paged fetch on the twin
  (walk_ld's PTE-fetch fallback :384-394, itself BK-60/64/65 gap
  family); a tile-scoped twin leg (impossible until BK-51's term
  lands); the oracle side is unchanged (tick 9's result stands).
- NO engine or shader code changed — probe + receipt + BK-68 row +
  ledger only. Rule-1 floors do not attach — numbers structural (word
  values, byte addresses, exit codes, md5s).
- Next tick: new queue supply or RULING if it appears, else Phase 1c.

### 2026-09-28 ~04:5x CDT — PHASE 1c RESEARCH TICK 9: PC/FETCH CONFINEMENT measured — the fetch and jump arms have NO confinement consult; a tile-confined USER task's program text executes ENTIRELY outside its tile, and fence-blind image-plane writes compose with JMPR into DIRECT out-of-tile code execution in USER mode (no trap, no KFAULT_PC): F1 PC census rows visited=[0] (tile rows 256..257 — the program never executes one instruction inside its own tile, clean exit), F2 JMPR to pre-stamped `LDI r10 0x0ADF00D` pixels at (0,40) executes them clean in USER (r10 readback), F3 full injection — four fence-blind PUSHes write instruction pixels to row 50 then JMPR executes the injected LDI (r10=0x0ADF00D, injected opcode pixel readback 0xEC5050 = the real LDI color) — arbitrary code injection + execution with the fence ARMED and no fence violation needed to trigger (stronger than BK-53's trap-mediated SUPER escape: this is a plain USER instruction stream); C1 unpaged out-of-tile ST traps 656 in the SAME posture (data fence LIVE — probe discriminating); the tile is a DATA-plane boundary only; BK-39 leg 4's "instruction-stream corruption class, RAM-grid blast radius unproven" closes as: the blast radius is EXECUTION; candidate BK-67 filed to systems/GLYPH_BACKLOG.md with the fix posture (execute-confine PC vs code-plane box vs spawn-pinned executable rows) FLAGGED as design-judgment (builder af3e62239ce2)

- Run selection: HEAD 2626466d at claim (re-verified via git rev-parse;
  monitor fingerprint head matched). Mailbox re-verified: newest
  RULING_*.md mtime < HEAD commit time — no binding new work.
  QUEUE_STATE.json: 0 non-landed tickets, 0 non-landed defects, active
  empty → claim queue EMPTY → Phase 1c eligible. No re-research:
  prior-art grep across RESEARCH_*/GLYPH_BACKLOG.md for fetch/PC/
  execute-confinement — every fence row (BK-38..45, 52/53, 60..66)
  governs DATA arms only; BK-53's escape is trap-mediated; the direct
  jump/fetch surface is unmeasured anywhere.
- Probe `.builder_queue/probe_fetch_confinement_af3e.py`: harness = the
  REAL `GlyphProcessTable.spawn(tile=(256,19,1,2))` posture (same tile
  as tick 8), NO paging (fetch never translates on the oracle BY SOURCE
  READ :753 — paged-fetch noted, not probed). min_rows=64 image so all
  program text sits at image rows 0..63. Injected opcode color resolved
  at runtime from OpcodeMapV2 (never hand-encoded). Probe defects
  disclosed in the receipt: (1) F1 v1 never set cpu.running=True —
  vacuous empty census, caught as a dead-harness signal, fixed before
  evidence; (2) canary pixel-split slip (0x0ADF00D → (0x0A,0xDF,0x0D))
  caught by readback cross-check, fixed to (0xAD,0xF0,0x0D) before the
  3 pinned runs; (3) F0's first JMP target tripped the assembler bounds
  check, rewritten in-program. 3 pinned runs byte-identical: stdout md5
  0f1ef65668f0a51e906139b45cd970cf, results md5
  01c45108a20f2d6725b8117cddfa71b0.
- Findings: F0 in-program JMP control green. F1 census — fetch runs at
  image row 0 only, outside tile rows 256..257, exit 0 clean: every
  landed tile-confined leg to date executed its whole text out-of-tile,
  unremarked. F2 — `LDI r15 (40<<16); JMPR r15` with canary-LDI pixels
  pre-stamped at (0,40): exit 0, r10=0x0ADF00D, USER, faulted=False
  (then opcode-None halt off the 4-pixel payload — loud halt_reason,
  disclosed). F3 — four PUSHes (r31=1601..1604 pre-decrement → image
  pixels 1600..1603 = row 50 cols 0..3, via `_mem_write` :702-708 which
  has no box consult — BK-39 leg 4's primitive) + JMPR to (0,50): exit
  0, r10=0x0ADF00D, USER, injected opcode pixel readback 15487056 =
  0xEC5050 = the real LDI color. C1 — out-of-tile ST word 164 traps
  fault_addr 656, mode→SUPER: the data fence is LIVE where F2/F3
  execute out-of-tile.
- Consequence: containment's honest statement ("the fence the task
  cannot cross is its own tile", glyph_containment.py docstring) is
  DATA-plane only — the code plane (image pixels) has NO fence, and the
  fetch (:753-764) + jump arms (:1208/:1245/:1130/:1145/:1275/:1259)
  are the last unconsulted execute-side surface family. Candidate
  BK-67 filed (gate tests/test_bk67_fetch_confinement.py, RED-first =
  F2/F3 shapes, posture FLAGGED for landing gate / Jericho: kernel
  text rows, reaper trampoline, GH-16 tick handlers all jump across
  rows, so execute-confinement is a real design decision, not a
  mechanical consult). Lands in the BK-38..57 sequenced fence family.
- NOT proved: WGSL twin (no tile harness, BK-51); paged fetch; the
  other jump arms individually probed (same next_pc shape by source
  read); no engine code changed. Rule-1 floors do not attach — numbers
  structural (word values, addresses, exit codes).
- Next tick: new queue supply or RULING if it appears, else Phase 1c.

### 2026-09-28 ~04:0x CDT — PHASE 1c RESEARCH TICK 8: the ORACLE side of the paged×tile composition MEASURED via the real spawn(tile=...) posture — arming GH-17 paging (PAGE_TABLE_WORD≠0) PERMANENTLY DISARMS the GO-2 tile fence for the task's lifetime: the paged branch is the FIRST arm in both LD (glyph_isa_v2.py:832) and ST (:972) while the tile LD fence (:917, the BK-38 landing) and the E-K1 box+tile ST arm (:1075, item-29) are elifs reached only when pt_base==0, so a tile-confined task that arms paging THROUGH ITS OWN LAWFUL IN-TILE STORE (tile covers RAM words 8211/8212 by construction) loses the fence and a full-flag PIX PTE admits an out-of-tile physical target on both sides — T1 paged USER LD returns the out-of-tile canary r10=0x0ADF00D clean (the BK-38 fence does not fire), T2 paged USER ST LANDS the canary at image word 1280 (instruction-stream class under GH-8b), T3 paged ST to the task's OWN in-tile word faults pte_invalid pte=0x0 vaddr=0x8050 (paging REPLACES the fence rather than complementing it), C1/C2 unpaged controls trap 16000/656 (both landed fences LIVE when unpaged — the gap is composition-shaped, not a dead fence), C3 unpaged in-tile clean; candidate BK-66 filed to systems/GLYPH_BACKLOG.md with the vaddr-vs-paddr consult posture FLAGGED as design-judgment (builder af3e62239ce2)

- Run selection: HEAD cd5e0233 at claim (tracked tree clean of prior-tick
  artifacts; build_map diffs from the build-map lane, untouched). Mailbox
  re-verified (newest RULING mtime 1790550013 < HEAD commit time
  1790566455 — clean). QUEUE_STATE.json: 0 non-landed of 6 → Phase 1c
  eligible. No re-research: every tick 2/4/5/6/7 receipt's NOT-proved
  bullet names "paged×tile composition still unprobed"; all prior paged
  probes ran with NO tile armed, all prior tile probes ran UNPAGED; no
  RESEARCH_*/backlog row closes the ORACLE side (the twin side is
  trivially fence-free pending BK-51's tile term).
- Probe `.builder_queue/probe_paged_tile_oracle_af3e.py`: harness = the
  REAL `GlyphProcessTable.spawn(tile=(256,19,1,2))` + `_run_task` (the
  item-29/BK-38 armed posture; probe defect #7's lesson — bare-CPU tile
  legs are dead fences — applied from the start). The tile is chosen to
  cover the PT-arm word itself: the task arms paging with its own lawful
  in-tile ST, i.e. the defeat consumes only fence-permitted accesses.
  min_rows=64 image contains the PT window; tag/PTE image-stamped (GH-25
  RAM-first/image-fallback). Probe defect #1 disclosed: C3 v1 aimed at
  word 164 (row 5 col 4 — OUT of tile (256,19,1,2)); caught pre-evidence
  by decomposition legs (ld_only/st_only both E-K1'd 656) + coordinate
  recompute, fixed to in-tile word 8212 before the 3 pinned runs.
  3 runs byte-identical, results md5 32a9cc1809b9f33b6d512e0b9930ebf8.
- Findings: T1 (tile+PT, paged LD vaddr 3072 via V|W|U|PIX PTE pfn 5 →
  image word 1280, physically out-of-tile) — exit 0 clean USER,
  r10=0x0ADF00D: out-of-tile READ, BK-38's fence silent. T2 (paged ST of
  the canary to the same vaddr) — clean, canary LANDS at image word 1280
  (readback 0x0ADF00D): out-of-tile WRITE, the shape the unpaged arm
  traps at fault_addr 5120. T3 (paged ST to own in-tile word 8212, vpn-0
  PTE 0x7 at word 1536) — the arming store ran unpaged-clean, then the
  second store faults `pte_invalid pte=0x0 vaddr=0x8050 op=ST` (vpn 32 →
  PTE word 1568 unmapped): under paging the tile word is no longer
  writable WITHOUT a mapping — translation semantics have replaced the
  fence predicate entirely, admit-all for mapped targets, deny for
  unmapped, tile nowhere in the decision. C1 (tile only, unpaged LD word
  4000) traps fault_addr 16000; C2 (tile only, unpaged ST word 164)
  traps 656 — both landed fences LIVE at pt_base==0. C3 (tile only,
  in-tile word 8212 LD+ST) clean USER — admitted side of the live fence.
- Consequence: containment (item-29/BK-38) and virtual memory (GH-17)
  are currently MUTUALLY EXCLUSIVE postures on the oracle — no guest can
  have both, and the flagship configuration (confined task + paging)
  silently keeps neither. Candidate BK-66 filed to
  systems/GLYPH_BACKLOG.md (gate tests/test_bk66_paged_tile_fence.py,
  RED-first = T1/T2's measured shapes; L4 rot-guards pin C1/C2's landed
  fences; the vaddr-side vs paddr-side consult posture is FLAGGED as a
  design-judgment call — routing to the landing gate / Jericho per the
  backlog header's design-judgment rule). Lands in the BK-38..57
  sequenced fence commit family (the consult site is the paged walk
  BK-64 already touches). NO engine or shader code changed — probe +
  receipt + BK-66 row + ledger only; numbers structural, rule-1 floors
  do not attach.
- NOT verified: WGSL twin NOT measured for the composition (no tile
  predicate exists there — BK-51 — so the twin question collapses into
  BK-51's fix); SUPER-mode paged tasks not probed (the :832/:972 MMIO
  exemption path untested under tile; SUPER tasks are not tile-armed by
  the spawn posture); HILB-frame PTEs under tile not re-probed (same
  elif chain by source read, labeled not measured); steps not pinned
  (engine run() return value not stored on the CPU object — probe
  reports -1; verdicts are exit/fault/readback facts).
- Next tick: new queue supply or RULING if it appears, else Phase 1c.

### 2026-09-28 ~03:0x CDT — PHASE 1c RESEARCH TICK 7: PTE_W/PTE_U enforcement on the paged HILB frame path MEASURED on-device (the tick-6 NOT-proved sibling) — the twin's flag gap is in the SHARED pre-arm check site, confirmed by measurement on BOTH frame arms: walk_st/walk_ld paged branches check ONLY PTE_V (wgsl :425/:389) BEFORE the HILB dispatch (:427-429/:393-394), so a W-clear HILB PTE is writable-through (twin LANDS at frame word 1280 out-box AND 320 in-box, even in SUPER) and a U-clear HILB PTE is readable in USER (twin returns the canary) while the oracle faults all three (:1001/:873 fire BEFORE the HILB arms :1027-1032/:901-906); consequence: BK-64's two predicate terms sit before the frame dispatch and cover HILB with NO additional code — BK-65 filed as a measurement-completion row (BK-64's gate grows two HILB legs, no new file) (builder af3e62239ce2)

- Run selection: HEAD 84a23929 at claim; mailbox re-verified (newest RULING
  mtime 1790550013 < HEAD commit time 1790565940 — clean). QUEUE_STATE.json:
  0 non-landed of 25 → Phase 1c eligible. No re-research: the question was
  named by tick 6's receipt ("NOT verified": HILB-frame flag legs not
  driven — PIX pinned the shared check site by source read only); no
  existing RESEARCH_*/backlog row closes it.
- Probe `.builder_queue/probe_hilb_pte_flag_af3e.py`: harness IDENTICAL to
  tick 6's (min_rows=64, two-pass bake, tag/arm/PTE image-stamped, USER
  via MODE_LATCH+KJMP, box [1200,1300) armed, CPU fault_reason via the
  tick-3 manual step-loop). ONLY deltas = PTE flag HILB 0x10 and Hilbert
  pfn packing (0x1→word 320, 0x300→word 1280 — encodings pre-confirmed
  against both engines by tick 4's H1/H4 controls). 3 runs byte-identical,
  stdout md5 5c977b4fe5634a8b5790195e140cb6fb.
- Findings: H1w — W-clear HILB ST (0x30015) out-of-box: CPU faults
  `pte_invalid pte=0x30015 vaddr=0x3000 mode=USER op=ST` (12288), canary
  nowhere; twin LANDS at frame word 1280, 25 steps. H2w — W-clear in-box
  control (0x115): CPU faults 12544, twin lands at word 320 (flag gap,
  not geometry). H1u — U-clear HILB LD (0x30013): CPU faults `op=LD`
  12288; twin RETURNS the canary. C2 — SUPER W-clear ST: CPU faults
  `mode=SUPER op=ST`; twin LANDS even in SUPER (kernel read-only
  mappings writable-through, HILB arm included). C1 — unpaged E-K1
  control green on both @18 steps (fence live, gaps flag-level).
- Consequence: the flag gap is arm-agnostic — BK-64's fix (PTE_W in
  walk_st paged, PTE_U+is_user in walk_ld paged) sits before the frame
  dispatch and covers both arms as specified. BK-65 filed to
  systems/GLYPH_BACKLOG.md as a measurement-completion row for BK-64
  (its gate `tests/test_bk64_pte_flag_paged.py` grows two HILB legs; no
  new file, no new fix). NO engine or shader code changed — probe +
  receipt + BK-65 row + ledger only; numbers structural, rule-1 floors
  do not attach.
- NOT verified: no fix landed (research proposes, never lands); twin
  verdicts are readback-byte facts (no fault channel); plain-frame and
  PIX flag legs pinned by tick 6, not re-run here; paged×tile
  composition still unprobed (twin has no tile predicate until BK-51).

### 2026-09-28 ~02:2x CDT — PHASE 1c RESEARCH TICK 6: PTE_W/PTE_U flag enforcement on the paged PIX frame path MEASURED on-device — the WGSL twin's paged walker checks ONLY PTE_V: a W-clear frame PTE is writable-through (even in SUPER) and a U-clear frame PTE is readable in USER, while the oracle faults both; candidate BK-64 filed — the fifth and CHEAPEST line item of the BK-38..57 sequenced fence commit (builder af3e62239ce2)

- Run selection: HEAD 71b4b364 at claim; mailbox re-verified (newest RULING
  mtime 1790550013 < HEAD commit time 1790564899 — clean). QUEUE_STATE.json:
  0 non-landed of 25 → Phase 1c eligible. No re-research: the question was
  named, not answered, by tick 5's receipt ("NOT proved" first bullet:
  PTE W/U never driven on the frame paths) and tick 2's S1 (twin walker
  PTE_U/PTE_W refs=0, source read only); BK-60 L1's U-bypass was a PLAIN
  frame, ticks 4/5 held flags constant. No RESEARCH_*/backlog row closes it.
- Probe `.builder_queue/probe_pte_flag_frame_af3e.py`: harness IDENTICAL to
  tick 5's (min_rows=64, two-pass bake, tag/arm/PTE image-stamped, USER
  via MODE_LATCH+KJMP, box [1200,1300) armed, LINEAR PIX placement); ONLY
  delta = PTE flag bits (0x50d = V|U W-clear, 0x50b = V|W U-clear, 0x10d =
  W-clear in-box). CPU fault_reason captured via the tick-3 manual
  step-loop. 3 runs byte-identical, stdout md5
  eab3b8cedd8328a87fecc9634b591fe6.
- Findings: W1 — W-clear PIX ST: CPU faults `pte_invalid pte=0x50d
  mode=USER op=ST` (12288), canary nowhere; twin LANDS at frame word 1280
  (write-protect bypass). W2 — W-clear in-box control: twin lands at word
  320 (flag gap, not box geometry). U1 — U-clear PIX LD: CPU faults
  `op=LD`; twin returns the canary (D2's U-bypass extends to frames). C2
  — SUPER W-clear ST: CPU faults (`:1001` W term is mode-INDEPENDENT and
  live); twin LANDS even in SUPER — the kernel's own read-only mappings
  are writable-through on the twin. C1 — unpaged E-K1 control green on
  both (fence live, gaps are flag-level). Probe defect #1 disclosed: v1's
  C2 was mis-designed (PT-arm word read from RAM only, glyph :834 — no
  image fallback, so the image-stamped arm was invisible and C2 ran
  UNPAGED); v2 arms via the program's own SUPER ST.
- Consequence: sequenced fence commit's twin side grows to FIVE line
  items; BK-64 is the cheapest (two predicate terms: PTE_W in walk_st
  paged, PTE_U+is_user in walk_ld paged — bitwise mirrors of
  glyph_isa_v2.py:1001/:873) and is flag-level, independent of the
  box-consult posture decisions, so it can land first within the family.
- Candidate BK-64 filed to systems/GLYPH_BACKLOG.md (gate
  tests/test_bk64_pte_flag_paged.py, RED legs = these measured landings,
  oracle-parity rot-guards pin :1001/:873 vocabulary). NO engine or
  shader code changed — probe + receipt + BK-64 row + ledger only;
  numbers structural, rule-1 floors do not attach.
- NOT verified: HILB-frame flag legs not driven (PIX measurement pins the
  shared check site by check-order source read, not a measured HILB leg);
  twin non-paged branches not re-probed for flags (no PT by construction);
  the twin has no fault channel at all (walk_st bool / walk_ld sentinel),
  so twin verdicts are readback-byte facts, not fault-record comparisons.
- Self-assessed priority signal: tick 5's receipt
  `.builder_queue/RESEARCH_pix_frame_fence_af3e.md` § "What this receipt
  does NOT prove", first bullet — the file:line that yielded the signal.

### 2026-09-28 ~01:1x CDT — PHASE 1c RESEARCH TICK 5: PTE_PIX plane-path fence posture MEASURED on-device — a box-confined USER task reads AND writes any image word through a LINEAR PIX PTE with zero box consults, on BOTH engines (the PIX sibling of tick 4's HILB measurement; both frame modes now closed as write-fence-blind); candidate BK-63 filed (builder af3e62239ce2)

- Run selection: HEAD 699e0734 at claim; mailbox re-verified (newest RULING
  mtime 1790550013 < HEAD commit time 1790564252 — clean). QUEUE_STATE.json:
  0 non-landed of 25 → Phase 1c eligible. No re-research: tick 4's receipt
  (`.builder_queue/RESEARCH_hilb_frame_fence_af3e.md`, § NOT-proved first
  bullet) names the PIX arms as the remaining unprobed sibling — no existing
  RESEARCH_*.md or backlog row closes it.
- Probe `.builder_queue/probe_pix_frame_fence_af3e.py`: harness IDENTICAL to
  tick 4's (corrected BK-60 L4 discipline — min_rows=64 image contains the
  PT window, two-pass bake, tag/PT-arm/PTE image-stamped, USER via
  MODE_LATCH+KJMP, box [1200,1300) armed by the kernel prologue). ONLY delta,
  by design: PTE_PIX (0x8) frames, LINEAR placement pfn·256+offset, aimed at
  the SAME words as tick 4 (320 in-box / 1280 out-box) so the two receipts
  differ only in flag+transform. 3 runs byte-identical, stdout md5
  0046d2cec12b369ded117a0b3c57a578, results md5
  e61510771d269ab895796adb25fca76e.
- Findings: P2 (out-box PIX LD) — canary returns on BOTH engines (r10=
  0x0ADF00D), parity with tick 4's H2. P3 (out-box PIX ST) — the canary
  LANDS at image word 1280 on BOTH engines, clean, no fault record, while
  C1's UNPAGED ST E-K1s on both (CPU fault_addr 400, twin refuses in 18
  steps) — genuine path gap, not a dead harness. P1/P4 in-box controls
  green. fault_addr=2880 on PT-armed legs = the BK-60-disclosed epilogue
  artifact, uniform and distinct from C1's real E-K1. Both frame modes
  (HILB + PIX) are now MEASURED write-fence-blind on both engines.
- Blast radius: unchanged class from tick 4 (image plane shared, kernel
  text = fetch truth GH-8b → instruction-stream corruption class BK-42/53);
  PIX is the DEFAULT frame mode for plain spatial workloads — the
  higher-traffic of the two arms.
- Candidate BK-63 filed to systems/GLYPH_BACKLOG.md (gate
  tests/test_bk63_pix_frame_fence.py, incl. a PTE-flag discrimination
  rot-guard leg; co-lands with BK-62 in the BK-38..45 sequenced fence
  commit). NO engine or shader code changed — probe + receipt + BK-63 row +
  ledger only; numbers structural, rule-1 floors do not attach.
- NOT verified: PTE W/U enforcement on the PIX path beyond the shared
  :872-876 checks not independently probed; paged×tile composition still
  unprobed (twin has no tile predicate until BK-51); both-engine consult-
  site edits are landing-gate work, not research lane work.


### 2026-09-28 ~00:0x CDT — PHASE 1c RESEARCH TICK 4: PTE_HILB frame-path fence posture MEASURED on-device (the last "source read, labeled" surface in BK-60's honesty note) — a box-confined USER task reads AND writes any image frame word through a HILB PTE with zero box consults, on BOTH engines (measured engine PARITY; the fence-blind WRITE into the GH-8b fetch-truth plane is the new measured shape); candidate BK-62 filed (builder af3e62239ce2)

- Run selection: HEAD dbee2164 at claim; mailbox re-verified (newest RULING
  mtime 1790550013 < HEAD commit time 1790563178 — clean). QUEUE_STATE.json:
  0 non-landed → Phase 1c eligible. No re-research: BK-60's HONESTY section
  (`systems/GLYPH_BACKLOG.md:446-447`) names the HILB frame path as probed
  NEVER — no existing RESEARCH_*.md or backlog row closes it.
- Probe `.builder_queue/probe_hilb_frame_fence_af3e.py`: harness = the
  corrected BK-60 L4 discipline (min_rows=64 image contains the PT window,
  two-pass bake, tag/PT-arm/PTE image-stamped, USER via MODE_LATCH+KJMP,
  box [1200,1300) armed by the kernel prologue). Frame placement computed
  LOCALLY via a replicated xy2d, then confirmed by the engines' own behavior
  (pfn 0x1 → word 320 = byte 1280 IN box; pfn 0x300 → word 1280 = byte 5120
  OUT box; H1 returning the canary proves the probe mapping matches both
  engines). 3 runs byte-identical, stdout md5 0ec4bece7eda293bde66037542f572ce.
- Findings: H2 (out-box frame LD) — canary returns on BOTH engines (r10=
  0x0ADF00D): engine parity, mirrors BK-60 D3's plain-frame allowance, now for
  the GH-25 frame path. H3 (out-box frame ST) — the fence-violating write
  LANDS at image word 1280 on BOTH engines, clean exit, no fault record,
  while C1's UNPAGED ST to the same box region E-K1s on both (fault_addr 400):
  genuine path gap, not a dead harness. fault_addr=2880 on PT-armed legs is
  the BK-60-disclosed epilogue artifact (word 720, vpn 2 unmapped, 720×4),
  uniform across H1-H4 and distinct from C1's real E-K1.
- Blast radius: image plane is shared state; kernel text pixels are fetch
  truth (GH-8b) → an out-of-box HILB ST is instruction-stream corruption
  class (BK-42/53 family, cf. BK-39's PUSH leg). PIX-frame siblings are the
  same consult-free shape BY SOURCE READ ONLY (labeled, not probed).
- Candidate BK-62 filed to systems/GLYPH_BACKLOG.md (gate
  tests/test_bk62_hilb_frame_fence.py, RED-first = the measured landing
  shapes; lands IN the BK-38..45 sequenced fence commit as the HILB sibling
  of BK-60's paged-posture line item). NO engine or shader code changed —
  probe + receipt + BK-62 row + ledger only; numbers structural, rule-1
  floors do not attach.
- NOT verified: no on-device PIX-frame leg; paged×tile composition still
  unprobed (twin has no tile predicate until BK-51 lands); both-engine
  consult-site edits are landing-gate work, not research lane work.
- Next tick: new queue supply or RULING if it appears, else Phase 1c.

### 2026-09-27 ~23:0x CDT — PHASE 1c RESEARCH TICK 3: COMPLETE fault_reason classification pass — the oracle has EIGHT fault sites, FIVE carry evidence strings, THREE are silent (S3 LD tile E-K1 glyph :932, S7 ST E-K1 :1082, S8 OOB store :1107 both sub-branches) — S3 is a LOAD-side fence going silent (new class: prior pass treated coverage as store-side+paged-only), plus probe defect #7: _tile_confinement is spawn-only so bare-CPU tile legs are dead fences (builder af3e62239ce2)

- Run selection: HEAD b34ff0e8 at claim; mailbox re-verified (newest RULING
  mtime 1790550013 < HEAD commit time 1790562478 — clean). QUEUE_STATE.json:
  0 non-landed; all three remedy-* landed → Phase 1c eligible. No
  re-research: the census was flagged open by tick 2's F4 (site #6 found
  incidentally; no row closes the full enumeration).
- Census (probe .builder_queue/probe_faultreason_census_af3e.py, 3x
  byte-identical, md5 9ffc70d50147a388a9f710378ce8ce20): 8 sites =
  S1 :845 tag LD / S2 :876 pte_invalid LD / S3 :932 tile LD / S4 :977 tag
  ST / S5 :1004 pte_invalid ST / S6 :1052 pfn ceiling / S7 :1082 E-K1 ST /
  S8 :1107 OOB ST. Measured reasons quoted in
  .builder_queue/RESEARCH_faultreason_census_af3e.md; C1/C2 parity legs
  return REAL strings (probe not an echo); S8 iso vs standalone legs
  diverge in running_after (vector continues vs stops) under one program.
- S3 spawn-path confirmation: dbg_tile_ld_spawn_af3e.py — out-of-tile LD
  exit_status 1, fault_addr 16000, reason None; in-tile control exit 0
  clean; out-of-tile ST control fault_addr 656 (matches BK-51). Bare-CPU
  leg was a DEAD fence (21 steps, faulted=False) — harness discipline now
  pinned: tile-branch coverage requires spawn(tile=...) or explicit flag
  arm (probe defect #7, receipt F3).
- Consumer impact: FAULT_ADDR alone cannot distinguish out-of-tile READ
  from out-of-box WRITE (both addr<<2, SUPER, reason None). Candidate
  BK-61 filed to systems/GLYPH_BACKLOG.md (3 one-line reason-sets, gate
  tests/test_bk61_fault_reason_census.py, RED-first legs = the measured
  silent shapes).
- NOT verified: no engine code changed (research proposes, never lands);
  static 8-site map is HEAD-scoped; syscall-handler rc refusals (BK-40
  class) are out of step()-census scope; WGSL twin has no fault_reason
  channel at all (posture unchanged).
- Next tick: new queue supply or RULING if it appears, else Phase 1c.

### 2026-09-27 ~22:0x CDT — PHASE 1c RESEARCH TICK 2: BK-60 L4's deferred oracle re-measurement DONE under the corrected harness — D2/D4 confirmed with REAL attributions (pte_invalid pte=0xc03 op=LD / pte=0x0 op=ST, fault_addr 12288 both), D3 FLIPPED: the oracle's own paged USER path ALLOWS the read into the config window (word 8196, r10==1300, clean 24-step walk) — the original "oracle faulted 12304" was entirely the tag-gate artifact, both engines AGREE, D3 retires as an engine divergence and L2's premise becomes an oracle-parity pin + a posture question that is Jericho's ruling call (builder af3e62239ce2)

- Run selection: HEAD 1606834c at claim; mailbox re-verified (newest RULING
  mtime 1790550013 < HEAD commit time 1790561796 — clean). QUEUE_STATE.json:
  0 non-landed; all three remedy-* landed → Phase 1c eligible. No
  re-research: the D1 receipt explicitly deferred this (F4) and no later
  row closed it.
- Probe .builder_queue/probe_bk60_l4_oracle_af3e.py: the original five legs
  (D1/D2/D3/D4/C1), corrected harness only (min_rows=64 → 2048-word image,
  vpn-2 identity PTE, canary/box words RAM-seeded via drive(seeds=)/
  ram_seed, PT words image-stamped, USER via MODE_LATCH+KJMP, fault_reason
  via manual step-loop). 3 runs byte-identical, results_md5
  da02059b4c521f46ffebb96cc68ace46.
- D2: oracle pte_invalid op=LD pte=0xc03, fault_addr 12288, SUPER at fault,
  20 steps; twin admits (r10==0x0ADF00D, receipt 4660). L1's RED stands.
- D3: oracle CLEAN (faulted=False, r10==1300, mode USER); twin identical.
  Source-grounded: paged exemption glyph_isa_v2.py:836/:968 exempts only
  SUPER from translation; paged LD path has no box consult — the unpaged
  BK-56 posture does not extend to paged. L2 premise rewrite flagged in
  the BK-60 row (stale wording noted; rewriting gate text = sign-off).
- D4: oracle pte_invalid op=ST pte=0x0, 12288, 21 steps; twin silent drop
  re-confirmed (no fault channel, receipt 4660, ram_3072==0, 25 steps).
  L3's RED stands.
- C1: oracle fault_addr 400 / twin refuses 18 steps (matches original);
  NEW small fact: unpaged E-K1 ST fence site (glyph :1075) sets NO
  fault_reason — 6th site for the classification pass.
- Receipt: .builder_queue/RESEARCH_bk60_l4_oracle_remeasure_af3e.md.
  AMENDMENT 2 filed to BK-60 in systems/GLYPH_BACKLOG.md.
- NOT verified: no engine/shader code changed (research proposes, never
  lands); twin legs are matched-harness re-confirmations, not independent
  replication of the original S-leg source audit; C1's drive() receipt
  steps reads 4000 post-fault (bookkeeping anomaly, not investigated —
  verdict fields are the datum); PTE_HILB/PTE_PIX paths untouched.
- Next tick: new queue supply or RULING if it appears, else Phase 1c.

### 2026-09-27 ~21:3x CDT — PHASE 1c RESEARCH TICK: BK-60's unattributed D1 oracle fault ROOT-CAUSED as a probe-harness artifact (probe defect #6) — the original probe's ~672-word image cannot contain the PT window (tag 1535/PTE 1548), check_pt_tag's bounds guard (glyph_isa_v2.py:92-95) blocks the image fallback, and every CPU paged leg died at pt_tag_mismatch BEFORE the PTE checks; control (same leg, min_rows=64 + RAM-seeded canary): oracle walks clean, r10==0x0ADF00D, NO fault — oracle AGREES with the twin on the V|W|U identity map; the "third divergence shape" is RETIRED; BK-60's L4 oracle fault_addr values (12288/12304) flagged as tag-gate artifacts needing re-measurement under the corrected harness (builder af3e62239ce2)

- Run selection: HEAD 72f8d45d at claim; mailbox re-verified (newest
  RULING mtime 1790550013 < HEAD commit time 1790560913 — consumed by
  my own prior tick). QUEUE_STATE: 0 pending → Phase 1c eligible.
  No re-research: BK-60's receipt lists D1 as "recorded, not
  attributed"; no later row closes it.
- Attribution probe .builder_queue/probe_d1_attribution_af3e.py
  (original D1 leg byte-for-byte, fault_reason captured via manual
  step-loop — confirming probe defect #4, _fill_receipt drops the field):
  fault_reason == "pt_tag_mismatch got=0x0 expected=0x505447 pt_base=1536
  tag_addr=1535"; fault_addr 12288 is just the vaddr echo (indistinguishable
  from pte_invalid at fault_addr granularity — why the artifact survived).
  3 runs byte-identical, results md5 a98931c79c0f3b7b50749468f91e6d39.
- Control .builder_queue/probe_d1_bigimage2_af3e.py (min_rows 64 →
  32x64=2048-word image contains the window unwrapped; canary via
  runner.drive(seeds=) — the twin's ram_seed channel; vpn 2 identity PTE
  added after the v1 control exposed the epilogue receipt store faulting
  pte_invalid op=ST on unmapped vpn 2): faulted=False, r10==11399181,
  receipt_720==4660, 24 steps, USER. 3 runs byte-identical, results md5
  80bb227fdd91d819cbe1d7ecf5ba8f09 (intermediate v1 md5
  112e838da31ef21599cfeb1654d38471 in-log only).
- Consequence: BK-60's twin-side divergences D2/D3/D4 stand (twin side
  harness-independent); L4's oracle-parity legs must re-measure oracle
  fault_addr under a sized-image + RAM-seed harness; gate fixtures must
  identity-map every vpn the kernel text stores through. Amendment noted
  in systems/GLYPH_BACKLOG.md BK-60 row (gate shape L1-L3/L5/L6 unchanged).
- Receipt: .builder_queue/RESEARCH_d1_paged_fault_attribution_af3e.md.
- NOT verified: WGSL legs not re-run this tick (original 3-run md5 pins
  them); corrected-harness oracle numbers for D2/D3/D4 not yet taken
  (that is BK-60 L4's job); PTE_HILB path untouched. Numbers structural
  — rule-1 floors do not attach.
- Next tick: new queue supply if it appears, else research per Phase 1c.

### 2026-09-27 ~21:0x CDT — SEAT-LANE STANDING ORDER COMPLETE: remedy-DTF_floor evidence-rebuked (evidence 33b1e687) — advisory REBUKED: the DTF_floor receipt DID carry RED-first + discriminating controls (:47-58 corrupted-expectation RED with pasted FAIL tail; :43-45 always-echo mutation leg) and the advisory's premise ("claims a bug fix") mis-parses a receipt that documented a font gap and explicitly did NOT fix it; re-measured at HEAD 84236753: RED re-run (receipt's own mutation, one expectation corrupted) = 13 PASS / exactly 1 FAIL '[FAIL] DTF-1 L4 read round-trip — cat cow-swap', EXIT=1, localization exact; GREEN re-run = 14 PASS, EXIT=0; band now decodes full 'ERR:UNKNOWN_CMD' (BK-19 atlas 85662ba2 closed the gap the receipt flagged); screener rerun reproduced the same overclaim@0.90 verdict (mis-read stands; re-litigation is Jericho's call); QUEUE_STATE remedy-DTF_floor -> landed (evidence-rebuked); all three remedy-* tickets now non-pending — standing order 4d7f98df SATISFIED, next tick returns to normal claim rules (builder af3e62239ce2)

- Run selection: HEAD 84236753 at claim; mailbox re-verified (newest
  RULING mtime 1790550013 < HEAD commit time 1790559885 — clean).
  QUEUE_STATE: exactly one pending item at claim = this ticket.
- Receipt: .builder_queue/RECEIPT_remedy_dtffloor_af3e.md.
  Tails: output/REMEDY_dtffloor_MUTATION_RED.txt (13 PASS/1 FAIL, EXIT=1),
  output/REMEDY_dtffloor_GATE_GREEN.txt (14 PASS, EXIT=0).
- No code changed; mutation lived in a throwaway untracked transcript
  copy, deleted after the run; committed transcript untouched
  (git diff on .builder_queue/transcript_dtf_floor.py: empty).
- NOT verified: the two landing-time REDs (font-coverage, silent
  AUDIO_OUT) are attested from the receipt's record, not regenerated —
  the atlas gap they prove is since FIXED (85662ba2) so they cannot
  re-run on the green tree. Screener NOT re-asked to re-adjudicate.
- Next tick: queue empty (all landed) → Phase 1c research eligible
  under the normal rules; monitor fingerprint should return CLEAN.

### 2026-09-27 ~20:4x CDT — SEAT-LANE STANDING ORDER TAKEN: remedy-L4_desktop remediated (evidence 2079c461) — advisory CONFIRMED: the L4 receipt's only RED was a collection ImportError (absent module), so the landing-time session_root persistence fix shipped with zero discriminating evidence; mutation probe (restore() ignores the persisted root, glyph_desktop_env.py:210 one-liner) RED: test_l4s_session_save_restore_roundtrip fails at :124 with the receipt's own documented symptom (cat memo.txt -> ERR:NOENT:memo.txt), 1 failed/10 passed, localization exact — the other 10 legs correctly pass under this mutation; revert GREEN: 11 passed 0.12s, git diff clean on the engine file; no code changed — this remedy supplies the missing RED arc; System-1 re-audit of the remedy receipt: honest conf 1.00 (missing-red-leg 0.0, overclaim 0.0); QUEUE_STATE remedy-L4_desktop -> landed; remedy-DTF_floor still pending -> standing order stays live next tick (builder af3e62239ce2)

- Run selection: HEAD 65b97f11 at claim; mailbox re-verified (newest
  RULING mtime 1790550013 < HEAD commit time 1790559415 — clean).
- Receipt: .builder_queue/RECEIPT_remedy_l4desktop_af3e.md.
  Tails: output/REMEDY_l4desktop_MUTATION_RED.txt,
  output/REMEDY_l4desktop_GATE_GREEN.txt.
- NOT verified: N1 (neutered-GPU) / N2 (corrupted-persistence) legs were
  not re-mutation-tested this tick — their discriminating power is
  asserted from the original receipt; Tk/pixel surface still
  operator-eyes PENDING.
- Next tick: remedy-DTF_floor (last pending), then queue-empty rules.

### 2026-09-27 ~20:4x CDT — SEAT-LANE STANDING ORDER TAKEN: first remedy-* remediation landed (remedy-item26_process_model, evidence b727fcb1) — the advisory CONFIRMED and the defect worse than stated: the original RED was vacuous (collection error) AND a real mutation probe (vfs.attach neutered) showed the P4 gate itself non-discriminating (8 passed) because the payload escaped through the engine's no-VFS host-FS fallback (glyph_isa_v2.py:1509/1555, CWD-relative open) past a containment assert checking only tmp_path; gate fixed to assert the fallback's actual escape path → mutation now RED (test_item26_process.py:204 AssertionError, escape file re-landed), revert GREEN (8 passed, no escape), System-1 re-audit of the remedy receipt: honest conf 1.00, missing-red-leg 0.0 — the actuation loop (inject → claim → remediate → re-screen) is proven once end to end (builder af3e62239ce2)

- Run selection: HEAD 963046cd at claim (my own prior-tick BK-60
  landing completed first this tick; standing-order commit 4d7f98df
  re-verified before acting). Mailbox: remaining pendings are the two
  other remedy tickets themselves — no new RULING newer than HEAD.
- Mutation RED run 1 (pre-fix): tools/glyph_process.py:174 attach
  neutered → 8 passed; repo-root handoff.txt, 21 bytes byte-exact
  (`from-task-A-love` payload), engine stdout `FILE_WRITE: 21 bytes`
  with NO `(vfs)` tag = host-FS fallback route confirmed.
- Gate fix: tests/test_item26_process.py P4 + CWD-escape containment
  assert (pathlib.Path(name) refused) + pathlib import.
- RED run 2 (post-fix, mutation re-applied): 1 failed at :204,
  0.19s, escape file re-landed. GREEN: attach restored (git status
  clean on the engine file), 8 passed 35.18s, no escape file.
  Tails: output/REMEDY_item26_MUTATION_RED.txt,
  output/REMEDY_item26_GATE_GREEN.txt.
- Receipt: .builder_queue/RECEIPT_remedy_item26_af3e.md (NOT-proven
  section: other 7 legs not mutation-tested; engine fallback behavior
  unchanged — gate fixed, not engine; loop proven n=1).
- QUEUE_STATE: remedy-item26_process_model-b727fcb1 → landed;
  remedy-L4_desktop + remedy-DTF_floor still pending → standing
  order remains live, next tick takes the next remedy.
- NOT verified: whether other gates in the family share the same
  wrong-path containment shape (not probed — would be new scope).

### 2026-09-27 ~20:4x CDT — PHASE 1c RESEARCH TICK: the WGSL twin's PAGED walker measured on-device for the first time (BK-60) — paged LD has NO PTE_U check and NO fence consult (USER reads a U-clear page the oracle faults; USER reads BOX0_HI THROUGH a mapped PTE the unpaged BK-56 posture refuses; unmapped paged ST drops SILENTLY where the oracle records E-K1); the sequenced fence commit's twin side grows to FOUR line items; BK-59's Definition of Done should grow a BK-60 clause (flagged for Jericho, not self-applied) (builder af3e62239ce2)

- Run selection: HEAD b9c6d8f4 at claim (parallel sessions landed
  2dbe69da/b9c6d8f4 mid-tick — build-map viewer + BK-58/59 filings;
  re-verified before acting). Tracked tree clean at claim apart from
  this probe/receipt/backlog/ledger append. Mailbox: newest RULING
  mtime 1790533788 < HEAD commit time — clean. QUEUE_STATE.json: all
  22 items landed, active null → Phase 1c research eligible.
- Rule-5 grep BEFORE harness build: prior WGSL probes all ran UNPAGED —
  RESEARCH_ek1_vector_hijack_wgsl_af3e.md:112-113 explicitly discloses
  the paged walk_st branch as "not probed"; RESEARCH_bk51_twin_tile_ld_
  af3e.md:104-105 scopes tile probes to the unpaged posture; no backlog
  row covers the paged branch (BK-48..57 are LD/ST/PUSH/MMIO/tile on the
  unpaged path). Net-new confirmed.
- MEASURED (probe .builder_queue/probe_wgsl_paged_fence_af3e.py, GH-25
  gate's _write_pte/_arm_pt image-stamping harness, two-pass bake with
  the LDI-r30 placeholder in BOTH passes, identical image on both
  engines, USER via MODE_LATCH+KJMP; RTX 5090/wgpu 0.32.0; 3 runs
  byte-identical, stdout md5 053e8591bf6a9476a4fe2526800cbda1):
  S1 twin walk_ld paged branch PTE_V=1/PTE_U=0/PTE_W=0 (PTE_U defined
  wgsl:172, never consulted) vs oracle PTE_U check (:872-876) and
  PTE_W+PTE_U on ST (:997). D2 PTE_U bypass: twin r10==0x0ADF00D on a
  U-clear page (no fault channel) vs oracle faulted 12288 — divergence.
  D3 paged MMIO read: plain PTE pfn32off4→word 8196, twin r10==1300 in
  USER with 0 tile/addr_in_box refs in the paged branch —
  RULING_BK38_READ_POSTURE's F1 violated on the paged path (unpaged
  BK-56 posture holds); oracle faulted 12304. D4 unmapped paged ST:
  twin silent drop, no fault record (:441's disclosed shape, now
  measured) vs oracle E-K1 record — kernels reading FAULT_ADDR see
  different state per engine. C1 control live (unpaged ST refused both
  engines). Receipt: RESEARCH_wgsl_paged_fence_af3e.md (full legs +
  5 disclosed probe defects, incl. the two-pass off-by-one KJMP loop).
- Consequence: BK-38..57 sequenced commit's twin side is now FOUR line
  items (walk_st tile term, walk_ld tile consult, TILE-word posture,
  + paged posture). BK-60 filed to systems/GLYPH_BACKLOG.md with gate
  shape (L1-L6, RED-first free). BK-59's DoD should add BK-60 legs —
  sequencing-marker edit deferred to Jericho per its header rules.
- NOT verified: paged×tile composition (twin has no tile predicate
  until BK-51 lands); PTE_HILB frame-path fence posture (source-read
  same absence, not measured); D1's oracle-side denial unattributed
  (GlyphRunner receipts carry no fault_reason — probe defect #4); C2
  excluded non-discriminating. Research landed probe + receipt +
  backlog row + this ledger only, NO engine or shader code; numbers
  structural — rule-1 floors do not attach. Next tick: new queue
  supply if it appears, else research per Phase 1c.

### 2026-09-27 ~14:2x CDT — PHASE 1c RESEARCH TICK: BK-51's unprobed leg measured — the WGSL twin's LD side under an armed tile ADMITS the out-of-tile read (r3 == 0x0ADF00D, 3 runs byte-identical) while the oracle (post-69a53298) faults at 656 on the IDENTICAL program — a measured engine divergence in the OPPOSITE direction of BK-51's ST side (twin ST denies the lawful in-tile store, twin LD admits the unlawful out-of-tile read); BK-51's standing D1-D4 legs all reproduce at HEAD unchanged (builder af3e62239ce2)

- Run selection re-verified: HEAD d4ee54f7 (my own previous tick:
  research receipt + ledger only), tracked tree clean at claim,
  mailbox clean (newest RULING mtime 1790533788 < HEAD commit time
  1790536402, consumed by 69a53298), monitor CLAIM_PENDING queue=0
  stall_tier=0, CLAIM QUEUE empty → Phase 1c research eligible.
  Rule-5 grep: BK-51's receipt explicitly listed "walk_ld under a
  tile — unprobed"; no other row covers it; the landing made the
  oracle side load-bearing → the question became a divergence.
- Standing legs re-measured (probe_wgsl_tile_fence_af3e.py, 2 runs
  identical, results md5 9701e0d40eba3fd3f9ce12b6dd6c4d89 — differs
  from the receipt's STDOUT md5 50bdb1728b… only because that md5
  covered probe stdout incl. its own results_md5 line; verdicts
  byte-stable across the landing): D1 out-of-tile ST traps (656),
  D2 box control (400), D3 IN-TILE ST STILL REFUSED (640 — BK-51's
  core defect open), D4 TILE_H cleared through the BK-50 door.
  Oracle controls re-run: out-of-tile ST faulted fault_addr=656;
  in-tile lands clean.
- NET-NEW (probe_bk51_twin_tile_ld_af3e.py, 3 runs byte-identical,
  results md5 8334c4d4f5e56082fa39e530c48a1b89): tile (5,0,2,4)
  armed, canary at out-of-tile word 164, program LD r3<-164;
  ST r3->160 — TWIN: r3 == 0x0ADF00D (the out-of-tile LD SUCCEEDS;
  walk_ld has zero TILE references), only the exfil ST traps (640).
  ORACLE, same program via landed spawn(tile=...) at HEAD: rc
  EXIT_FAULT, faulted, fault_addr 656 — 69a53298's LD fence fires.
  In-tile LD control lands clean on the twin. Verdict: MEASURED
  ENGINE DIVERGENCE on the read side, direction INVERSE of the ST
  side (deny-lawful vs admit-unlawful). Scope note: 69a53298's twin
  walk_ld gate covers only the BOX_MMIO range (:364); plain RAM
  reads ride the untouched path.
- Consequence: BK-51's gate should gain L1b (out-of-tile twin LD
  must NOT return the word, RED today = this probe); the sequenced
  fence commit's twin side is now three items — walk_st tile term,
  walk_ld tile consult, TILE-word write posture (D4's disarm path
  guest-defeats any new predicate). Receipt (full legs + honesty
  block): .builder_queue/RESEARCH_bk51_twin_tile_ld_af3e.md.
  Research landed NO engine or shader code; probes + receipt + this
  ledger only. Numbers structural — rule-1 floors do not attach.
- NOT verified: paged-branch tile semantics (out of scope, both
  probes unpaged posture); reachability from landed fleet images
  (none arms a tile on the twin — latent); BK-52 post-trap state in
  L4 (evidence is the fault record, not the post-replay image).
  Next tick: new queue supply if it appears; else research per
  Phase 1c (candidates: BK-52 twin-side kf=0 halt pin probe, or the
  BK-56 gate re-base spec), unless a new CLAIM QUEUE item or
  binding RULING appears.

### 2026-09-27 ~14:1x CDT — PHASE 1c RESEARCH TICK (post-landing re-verification): the 69a53298 read posture CONFIRMED on-device — twin USER LD of word 8193 returns 0 at HEAD (ram[310]==0, non-MMIO LD path untouched), oracle USER LD of 8193/8196 returns 0 (r3=r4=0) with the landed F1 assert mutation-bound — BUT the BK-55 hijack chain still escapes end-to-end at the fix HEAD (both probes byte-identical to pre-fix md5s): the de-fang killed the AIM READ, not the attack (blind write door BK-50 + live vector arm BK-52 remain open); BK-56's gate RED-first clause is now stale and needs re-base (builder af3e62239ce2)

- Run selection re-verified: HEAD e1e9887c (ledger entry for the
  BK-38/BK-56 landing), tracked tree clean at claim, mailbox clean —
  newest RULING RULING_BK38_READ_POSTURE.md (mtime 1790533788) is
  CONSUMED by 69a53298 (commit time 1790535670), not binding new work;
  monitor CLAIM_PENDING queue=0 stall_tier=0; QUEUE_STATE 22/22 landed;
  CLAIM QUEUE empty (items 19..41) → Phase 1c research eligible.
  Rule-5 grep: no existing row re-measures BK-53/55 chains at post-fix
  HEAD (all probe md5s pre-date the landing).
- Re-measured (probes untracked, landed modules only, HEAD e1e9887c):
  (1) oracle probe_ek1_vector_hijack_af3e.py — 3 runs byte-identical,
  run-1 stdout md5 5e107adaa9495bb7e1d4804d30444fc3, IDENTICAL to the
  pre-fix receipt: D1/D5 escapes + D3 store-lands all still fire, D2/C1
  discriminating — expected, the landing gated READS + tile LD, not the
  vector arm or PARALLEL_ST staging; open-row receipts stay valid.
  (2) twin probe_ek1_vector_hijack_wgsl_af3e.py — 3 runs byte-identical,
  results md5 128582726113782d8c234a4a59d7b068, IDENTICAL to pre-fix:
  D1 hijack, D2 super capability, D3 door-only arm all still escape
  (write door :443-446 unmode-gated BEFORE the consult; arm :595-602
  vectors LIVE) — BK-50/BK-52 out of scope for 69a53298.
  (3) The receipt's own de-fang claim tested directly: twin dbg harness
  (BK-50/55 device shape) USER LD 8193 → in-box result ST → ram[310]==0
  (BK-56 posture LIVE on-device) while ram[311]==0x0BADF00D (non-MMIO
  walk_ld RAM path untouched); 9 steps, mode USER, clean halt. Oracle
  dbg run: r3==0, r4==0, mem[310]==0, faulted False. Cross-checked
  against the landed gate: test_bk38_ld_fence.py 6/6 GREEN (0.06s),
  xv6-nano 13/13 (~31s) re-run this tick; F1 non-vacuity proven by
  /tmp throwaway mutation legs (flipped expectation → F1 RED both
  variants; no repo mutation).
- Verdict: BK-56's read-posture claim CONFIRMED both engines at fix
  HEAD; but the de-fang is narrower than the receipt's phrasing — it
  removes the attacker's AIM-VALUE READ, not the attack. BK-55 L1/L3
  remain RED-today-at-HEAD (the binding legs); the "read your own kf to
  aim" variant is dead, the blind-write variant is not. BK-56's gate
  clause "RED today: ram[310]==7" is STALE — its plain-seed legs are
  GREEN at HEAD (consumed by the landing); before landing, re-base on a
  kernel-seeded or door-write config fixture (RED pre-fix, GREEN
  post-fix) else it passes vacuously. Full findings + honesty block:
  .builder_queue/RESEARCH_postfix_hijack_recheck_af3e.md.
- Research landed NO engine or shader code; probe re-runs + throwaway
  /tmp mutation legs + receipt + this ledger entry only. Numbers
  structural (word values, md5s, step counts, byte-identity) — rule-1
  floors do not attach.
- Next tick: take the queue if new supply appears; else research again
  per Phase 1c (candidate surfaces: BK-56 gate re-base spec, BK-51
  post-landing twin tile probe), unless a new CLAIM QUEUE item or
  binding RULING appears.

### 2026-09-27 ~13:5x CDT — BK-38 / BK-56 (Option 2 refined: scoped GO-2 tile LD confinement and MMIO config block read posture) LANDED & VERIFIED (commit 69a53298 + 7161b883)

- Implemented Option 2 refined per RULING_BK38_READ_POSTURE.md in worktree `va_fence_worktree`:
  * Scoped LD confinement: GlyphProcessTable.spawn(tile=...) arms cpu._tile_confinement = True;
    LD out-of-tile traps to E-K1 only when _tile_confinement is active. Cooperative xv6-nano
    single-address-space kernels retain full read-sharing of scheduler globals (curproc word 1622).
  * MMIO config block read posture (both engines): GlyphCPUv2 USER LD of words [8192, 8448) returns 0;
    WGSL twin walk_ld gates box_mmio read with `if (!is_super) { return 0u; }` (measured on RTX 5090
    ram_result_word: 0 for both D1 BOX0_HI and D2 KFAULT_PC; de-fangs BK-55 aim step).
  * Triple-sync: tools/wgsl_glyph_isa_v2.py mirrored to glyph_dispatch/src/ and glyph_dispatch/src/glyph/;
    glyph_isa_v2.py mirrored to glyph_dispatch/src/glyph/. Pre-commit hook made worktree-aware.
- Verification gates (all GREEN):
  * tests/test_bk38_ld_fence.py: 6/6 passed (L1 out-of-tile traps, L2 in-tile unchanged, L3 boundary,
    L4 super unaffected, F1 MMIO read returns 0, F2 cooperative curproc succeeds).
  * tests/test_rv64i_to_glyph_xv6_nano.py: 13/13 passed in 31.4s (Scenario 6 and Scenario 11 GO-5 passed).
  * 38/38 Glyph differential suites passed in 45.58s; 8/8 Pillar 2.3 parity CI passed in 1.77s.
  * System-1 screening (tools/geos_system1.py Head 1): honest (confidence: 1.00) in 2408ms.
  * Hermes builder af3e62239ce2 woke at 13:50:36, independently re-verified all 19 legs + on-device
    measurements on RTX 5090, confirmed BK-55 de-fanged, and recorded 32KB report (no regressions).
- Receipt: .builder_queue/RECEIPT_bk38_ld_fence_option2.md.

### 2026-09-27 ~05:5x CDT — PHASE 1c RESEARCH TICK: WGSL twin of the E-K1 trap-vector hijack MEASURED ON-DEVICE — the twin reproduces the oracle's BK-53 privilege-escalation gadget end-to-end: BK-50's unmode-gated MMIO door lets a box-confined USER task arm a guest-chosen KFAULT_PC, the E-K1 arm (wgsl_glyph_isa_v2.py:581-598) vectors LIVE to attacker pixels in SUPER, and the refused out-of-box write LANDS through the fence's own failure handler; BK-55 filed (builder af3e62239ce2)

- Run selection re-verified: HEAD 7ad6ddcf (my BK-47/54 reconciliation
  landing), tracked tree clean at claim, mailbox clean (0 RULING_*
  newer than HEAD, mtime-scanned), monitor CLAIM_PENDING queue=0
  stall_tier=0, QUEUE_STATE 22/22 landed → Phase 1c research eligible.
  No re-research: BK-53 measured the ORACLE hijack and disclosed the
  twin legs "source-read only … reduces to BK-50's door, not
  re-measured" — that disclosure IS the unmeasured surface this tick
  closes. geo-obs canvas checked per teleop discipline: age_seconds
  661,978 (tick 0, sidecar 2026-09-19) — STALE, no conclusion drawn
  from it; the probe instrument is the host-side device harness.
- Probe `.builder_queue/probe_ek1_vector_hijack_wgsl_af3e.py`
  (untracked, landed modules only), harness = BK-50/51's device shape
  (run_wgsl real buffers + build_shader(OpcodeMapV2()), probe-only
  seeded cpu.mode/box_mmio/RAM). Payloads via the REAL assembler
  (labels resolved); KFAULT_PC nonzero in every escape leg (BK-52's
  kf=0 quirk excluded by control). 3 runs byte-identical, full stdout
  md5 555be18107f116c6caede990e6d0e1cc, results md5
  128582726113782d8c234a4a59d7b068.
- Findings (full detail in RESEARCH_ek1_vector_hijack_wgsl_af3e.md):
  (1) D1 HIJACK — door ST of (0<<16)|7 into word 8193 lands clean in
  USER (fault 0), then out-of-box ST 4660→word 999 fires E-K1
  (fault_addr 3996); the trap vectors to slot (7,0) and the guest's own
  `PRT r6` EXECUTES IN SUPER (mode_final 0), emitting the canary into
  the output buffer — the oracle D5's exact twin via the door instead
  of PARALLEL_ST; (2) D2 SUPER CAPABILITY — trapped-into payload
  LDs the out-of-box canary (200) and STs 0x0ADF00D back: the store
  LANDS (ram[200]==11399181) — the exact write E-K1 refused is
  delivered by the fence's failure handler, 11 steps (oracle BK-53 D3's
  twin); (3) D3 — door-only vector arm measured: mmio[1]==7, mode USER,
  fault 0, i.e. the fault VECTOR itself is guest-writable pre-fault;
  (4) C1 (kf=0 → loud halt, empty output) and C2 (plain out-of-box ST
  refused, ram[999]==0) both discriminating; (5) source S-legs: E-K1
  reads kf LIVE at :591 with mode already SUPER (:590) and vectors
  :592-596; walk-PC guard :498-502 is image-relative only.
- Consequence: the sequenced fence commit (BK-38..45) CANNOT be
  Python-only. The twin needs (a) kernel-write-only KFAULT_PC — BK-41's
  config-block posture extended to the twin's box_mmio buffer — and (b)
  the BK-52 vector-guard parity question answered for :591-596;
  co-landed with BK-50's door posture and BK-51's TILE words.
- BK-55 filed to systems/GLYPH_BACKLOG.md (gate tests/test_bk55_wgsl_
  vector_hijack.py: L1-L3 RED-today + C1/C2 controls + non-vacuity +
  twin-family; GPU legs run as a NON-BLOCKING SMOKE lane on CI runners;
  blast radius tools/wgsl_glyph_isa_v2.py only, worktree isolation).
  Research landed NO engine or shader code; probe + dbg artifacts +
  receipt + backlog row only. Numbers structural — rule-1 floors do
  not attach.
- Probe defects disclosed (all caught on read-back BEFORE verdicts
  accepted; artifacts kept): draft vector-target slot arithmetic
  (payload actually lands at instruction index 7 = slot (7,0); drafts
  vectored to my wrong slot and halted on an unknown-opcode pixel —
  single-step trace dbg_ek1_wgsl_draft6 + bake dumps pinned it, draft7
  proved the fix on-device); bake_image(data_words=) PREPENDS init STs
  that are themselves out-of-box stores → E-K1 fired pre-arm with kf=0
  in draft D2 (fix: host-side RAM seeds only); S1_door_mode_free
  substring check buggy, superseded by direct read of :443-444 + D3.
- Disclosed, NOT verified: mechanism (a) (PARALLEL_ST pixel overwrite)
  has no shader twin (S3, structurally unreachable); paged walk_st
  branch unprobed (PT words zero; :441 unmapped-store drop is a
  disclosed divergent shape, not re-measured); tile composition must be
  re-probed after BK-51 lands (the door disarms a naively-added tile
  term — BK-51 D4); GH-16 tick interaction unprobed (TIMER 0).
- Next tick: take the queue if new supply appears; else research again
  per Phase 1c (candidate surfaces named in the receipt's honesty
  block), unless a new CLAIM QUEUE item or binding RULING appears.

### 2026-09-27 ~05:0x CDT — PHASE 1c RESEARCH TICK: E-K1 trap-vector HIJACK measured — the store fence's own trap is a USER→SUPER escape primitive: a confined USER task (tile (5,0,8,8)) rewrites the reaper trampoline pixels (fence-blind PARALLEL_ST pixel mirror) OR rewrites KFAULT_PC itself (word 8193); the E-K1 arm vectors KFAULT_PC LIVE at trap time in SUPER mode, so ATTACKER CODE EXECUTES and the fence-violating store LANDS through the trap; BK-53 filed (builder af3e62239ce2)

- Run selection re-verified: HEAD 5d05c530 (my BK-52 research landing),
  tracked tree clean at claim, mailbox clean (0 RULING_* newer than
  HEAD, mtime-scanned), monitor CLAIM_PENDING queue=0 stall_tier=0,
  queue empty → Phase 1c research eligible. No re-research: BK-52
  root-caused the kf=0 continuation quirk; nobody had probed the
  VECTOR surface (what the trap executes, and whether the guest can
  control it) — the unproven blast radius BK-39 leg 4 / BK-40 leg 4
  explicitly deferred ("instruction-stream class... unproven").
- Probe `.builder_queue/probe_ek1_vector_hijack_af3e.py` (untracked,
  landed modules only): harness = the landed item-29 spawn(tile=...)
  + reaper posture; payloads assembled by the REAL assembler, staged
  via PARALLEL_ST (BK-39's fence-blind primitive + GH-8b pixel
  mirror). 3 runs byte-identical, stdout md5
  5e107adaa9495bb7e1d4804d30444fc3. Decode helpers:
  dbg_ek1_decode_af3e.py, dbg_ek1_d5b_af3e.py; draft-defect artifact
  dbg_ek1_d5_af3e.py (D5 staging-dest bug, caught on read-back and
  fixed BEFORE any verdict line was accepted; disclosed in receipt).
- Findings (full detail in RESEARCH_ek1_vector_hijack_af3e.md):
  (1) D1 — trampoline pixels (word 960, OUTSIDE the tile) overwritten
  with PRT r6/HALT; out-of-tile ST traps E-K1; trap vectors there;
  attacker PRT executes in SUPER (canary 0x34 printed); (2) D3 —
  trapped-into payload LDs a seeded canary from out-of-tile word 164
  and STs 0x0ADF00D back to it — the store LANDS (memory[164]==
  11399181): the fence's failure handler delivers the exact write the
  fence refuses; (3) D5 — KFAULT_PC (word 8193) rewritten via
  PARALLEL_ST to (30<<16)|4, payload staged at word 976 = pixel
  (16,30) = the arm's computed PC; trap executes attacker-chosen PC,
  ORIGINAL trampoline pixels untouched (attribution clean); (4) D2
  control (no overwrite → no PRT) and C1 control (E-K1 baseline
  fault_addr=672) both discriminating.
- Consequence: the item-29 tile fence is not merely bypassable at its
  edges (BK-38/39/40/42/43) — its FAILURE HANDLER is a
  privilege-escalation gadget. Any BK-38..52 "posture decided at
  landing" row must treat the trap vector + trampoline pixels as
  guest-writable surfaces in the same sequenced fence commit.
- BK-53 filed to systems/GLYPH_BACKLOG.md (gate
  tests/test_bk53_ek1_vector_hijack.py: 3 RED-today legs + controls +
  non-vacuity + family; lands IN the BK-38..45 sequenced fence commit,
  co-designed with BK-52's vector-arm repair and BK-41's
  kernel-write-only posture; blast radius glyph_isa_v2.py +
  glyph_containment.py, worktree isolation). Research landed NO
  engine or shader code; probe + decode helpers + receipt + backlog
  row only. Numbers structural (word addresses, fault codes, byte
  hex, pixel values) — rule-1 floors do not attach.
- Disclosed, NOT verified: WGSL twin legs are source-read only (no
  on-device probe; mechanism (a) structurally unreachable — _OPCODE_ORDER
  omits PARALLEL; mechanism (b) reduces to BK-50's door, not
  re-measured); cross-TASK image injection unprobed (engines own
  private images; shared-VFS/compositor routes noted, not measured);
  no fix posture decided (belongs to the sequenced commit's gate).

### 2026-09-27 ~04:2x CDT — PHASE 1c RESEARCH TICK: WGSL tile-fence parity MEASURED on-device — the twin's addr_in_box OMITS the GO-2 2D tile predicate entirely; a tile-armed USER task (the spawn(tile=...) posture) is DENIED EVERY RAM store on the GPU, IN-TILE INCLUDED (twin faults in-tile ST, oracle admits it), while out-of-tile ST traps on BOTH engines — measured engine divergence in the INVERSE direction of BK-48 (deny-all, not admit-all); BK-51 filed (builder af3e62239ce2)

- Run selection re-verified: HEAD 3e5ff03f (my BK-50 landing), tracked
  tree clean at claim, mailbox clean (0 RULING_* newer than HEAD,
  mtime-scanned), monitor CLAIM_PENDING queue=0 stall_tier=0, queue
  empty → Phase 1c research eligible. No re-research: BK-48/49/50
  measured walk_ld, stack ops, and the MMIO door; the 2D tile
  predicate is named "not mirrored" at wgsl_glyph_isa_v2.py:206-208
  and no RESEARCH_*/backlog row probes a tile-armed twin.
- Probe `.builder_queue/probe_wgsl_tile_fence_af3e.py` (untracked,
  landed modules only), harness = the BK-48/49/50 device buffers +
  tile words (8280..8283) seeded into mmio[88..91] + probe-only
  seeded cpu.mode. 3 runs byte-identical, stdout md5
  50bdb1728b72638872d4ffab0e168e84. Oracle controls
  `.builder_queue/dbg_wgsl_tile_oracle_af3e.py` (md5 4001544e0cc6685b,
  3 runs identical), run through cpu.run() — the process table's own
  entry (glyph_process.py:202) — after a hand-rolled step loop
  produced steps:0 (GlyphCPUv2 constructs halted, :609); both buggy
  first-draft variants discarded BEFORE oracle numbers were taken.
- Findings (full detail in RESEARCH_wgsl_tile_fence_af3e.md):
  (1) S1: twin addr_in_box (:463-476) has ZERO tile references; the
  oracle's _addr_in_box carries the tile branch (:734-747); (2) D1:
  tile (5,0,2,4) armed, USER ST to word 164 — twin TRAPS (fault 656,
  mode→SUPER, refused) AND oracle traps identically: PARITY, the
  hypothesis "twin admits" was FALSIFIED by the measurement (probe
  docstring conviction lines superseded by the receipt's table);
  (3) D3: same tile, IN-tile ST to word 160 — twin TRAPS (fault 640,
  refused, mode SUPER) while oracle LANDS clean (4660 at 160, USER,
  no fault): the twin denies a LAWFUL store — every tile-confined
  GPU workload is unrunnable through walk_st; (4) D2 control: BOX0
  armed, out-of-box ST traps (fault 400) — the twin's box consult is
  LIVE, so D3 is the missing tile term, not a dead harness; (5) D4
  composition: USER clears TILE_H (8282) via BK-50's unmode-gated
  MMIO branch, mmio_tile_h 2→0 clean — a naively added tile
  predicate would be guest-disarmable through the door.
- Disclosed, not root-caused: oracle out-of-tile leg's post-trap
  word164 readback = the BK-50-disclosed KFAULT_PC=0 continuation
  quirk (SUPER replay lands); walk_ld read-side under a tile not
  probed (moot until the fence commit adds consults there); paged
  branch out of scope.
- BK-51 filed to systems/GLYPH_BACKLOG.md (gate test_bk51_wgsl_tile
  _fence.py: oracle-parity both directions + non-vacuity + TILE-word
  BK-50 posture leg + family; lands IN the BK-38..45 sequenced fence
  commit, blast radius tools/wgsl_glyph_isa_v2.py only). Research
  landed NO engine or shader code; probe + oracle-control script +
  receipt + backlog row only. Numbers structural (word addresses,
  fault codes, run counts, md5s) — rule-1 floors do not attach.
- Next tick: research again (queue still empty), unless a new CLAIM
  QUEUE item or binding RULING appears first.

### 2026-09-27 ~03:5x CDT — PHASE 1c RESEARCH TICK: WGSL stack path fence posture MEASURED on-device — PUSH/POP/CALL are fence-blind on the GPU (image-plane mem_write/mem_read, zero consults, USER-clean; out-of-box PUSH lands, out-of-box POP reads) while the ST fence stays live on the same harness; BK-49 filed (builder af3e62239ce2)

- Run selection re-verified: HEAD 8f5f2e47 (my BK-48 landing), tracked
  tree clean at claim, mailbox clean (no RULING newer than HEAD),
  monitor CLAIM_PENDING queue=0 stall_tier=0, queue empty → Phase 1c
  research eligible. No re-research: BK-48's "NOT probed" list names
  the shader PARALLEL/PUSH stack class explicitly — unmeasured.
- Probe `.builder_queue/probe_wgsl_stack_fence_af3e.py` (untracked,
  landed modules only). Harness = BK-48's device legs + mmio readback
  (FAULT_ADDR word 8199 as evidence). Box [1200,1300) byte armed via
  box_mmio 3/4; mode seeded in the state array (probe-only posture,
  disclosed). 3 full runs byte-identical, stdout md5
  5b70e65cac5acf4e502e2f161accc6fd.
- Findings (full detail in RESEARCH_wgsl_stack_fence_af3e.md):
  (1) S1: PUSH (:635) / POP (:639) / CALL (:648) arms have ZERO
  addr_in_box refs — image-plane only; (2) D1: USER PUSH canary at
  r31=500 (out-of-box) LANDS at image addr 499 (pre-decrement),
  0x0ADF00D readback, clean exit, mode USER, fault_addr=0;
  (3) D2: in-box r31=1250 behaves identically — box membership is
  irrelevant to the stack path; (4) D3: out-of-box image bytes enter
  r5 via POP (exfil twin) — the follow-up in-RAM ST was fence-refused
  (fault_addr=400, mode→SUPER), so the out-of-box exfil chain is
  door-dependent but the cross-fence READ is not; (5) D4 control:
  plain USER ST out-of-box → fault_addr=400 refused — harness arming
  LIVE, so D1/D2 are a genuine bypass class.
- Probe-defects disclosed: runs 1-2 sampled img_word_500 instead of
  the post-pre-decrement 499 (re-leged before any conclusion); an
  address-resolution IndexError and a D3 preseed unpack bug fixed in
  place; preseeded value verified by POP readback in every run.
- Verdict: BK-48's verdict extends — the sequenced fence commit has a
  THIRD consult surface (stack ops, or one USER-gated consult inside
  mem_write/mem_read, posture decided at landing; single-site must
  not break kernel KJMP entry stacks). BK-49 filed to
  systems/GLYPH_BACKLOG.md (gate tests/test_bk49_stack_fence.py:
  out-of-box PUSH/POP refusal + in-box controls + E-K1 control +
  non-vacuity + family; lands IN the fence commit, blast radius
  wgsl_glyph_isa_v2.py only). Oracle-side stack parity NOT re-probed
  (BK-39 leg 4 already measured the host PUSH out-of-tile).
- Research landed NO engine or shader code; probe + receipt + backlog
  row only. Numbers structural (image words, register/mmio values,
  run counts, md5s) — rule-1 floors do not attach.

### 2026-09-27 ~05:1x CDT — PHASE 1c RESEARCH TICK: the WGSL twin's fence posture MEASURED ON-DEVICE — walk_ld is fence-blind on the GPU (canary 0x0BADF00D reads out-of-box in USER, clean exit) while walk_st's single consult is live (E-K1 fires) — the BK-38..45 sequenced fence commit is NOT Python-only; BK-48 filed (builder af3e62239ce2)

- Run selection re-verified, not assumed: HEAD 9e8b1bc0 (my BK-47
  research tick, 03:18), tracked tree clean at claim, mailbox clean
  (newest RULING mtimes 2026-09-22, all pre-dating the last ten
  landings), monitor CLAIM_PENDING queue=0 stall_tier=0. Queue empty
  (QUEUE_STATE.json: zero non-landed rows) → Phase 1c research is the
  eligible tick. No re-research: BK-38's WGSL caveat is explicitly
  "BY SOURCE READ (not probed on-device)" — no RESEARCH_*/backlog row
  measures the shader's fence posture on-device.
- Question prioritization: friction chain (a) known-divergence class —
  the entire fence family (BK-38..45, eight rows) shares one root cause
  measured in the Python oracle (single `_addr_in_box` consult,
  glyph_isa_v2.py:1041) with every WGSL row carrying the same unmeasured
  twin caveat; (b) roadmap dependency — the family can only land as ONE
  sequenced engine commit, so an unmeasured second consult site is the
  kind of thing discovered mid-landing, the most expensive timing.
- Probe: `.builder_queue/probe_wgsl_fence_twin_af3e.py` (untracked).
  Harness = run_wgsl's real buffer/dispatch path (runner.py:135-176)
  with a probe-only seeded cpu.mode (run_wgsl has no mode/mmio seed
  parameter — disclosed). Box [300,500) armed via box_mmio words 3/4;
  canary 0x0BADF00D at word 200 (out-of-box) via the ram binding.
  Device: RTX 5090 Laptop GPU, wgpu default adapter.
- Findings (measured; full output byte-identical across 3 runs, md5
  658a55330c8c4b3cf143b30ccca6eda4):
  (1) walk_ld body (wgsl_glyph_isa_v2.py:351-405): ZERO addr_in_box
  references — fence-blind, same class as oracle LD;
  (2) walk_st consults in exactly one arm, `is_super ||
  addr_in_box(addr << 2u)` (:451) — the precise twin of the oracle's
  single consult (:1041);
  (3) D1: seeded-USER LD from word 200 READS the canary (r5=
  195948557=0x0BADF00D) and the follow-up ST delivers it in-box (word
  100 = 0x0BADF00D), halted, no fault, mode stays USER — BK-38's
  cross-fence read + exfil shape reproduces on the GPU;
  (4) D2: USER ST to the same word does NOT land, mode drops SUPER —
  E-K1 live on-device;
  (5) D3: SUPER LD reads fine (mode-gated shape, matches oracle).
- Probe-defect disclosed: an early draft's KJMP entry block jumped to a
  raw word PC (KJMP targets are packed PIXEL PCs) — first-run D1/D3
  legs measured a jump into empty space; removed before evidence taken.
  The probe's crude S2 string-count legs are buggy (count artifact);
  the :451 consult was verified by direct source read. Device legs
  unaffected.
- Verdict: the WGSL twin is structurally FAITHFUL to the oracle's fence
  posture (one ST-anchored consult, LD fence-blind). The sequenced
  BK-38..45 engine commit has a SECOND consult site (walk_ld :351 /
  walk_st :407) — discovering this mid-landing would have cost a commit
  rework; now it is a filed row. BK-48 filed to systems/GLYPH_BACKLOG.md
  (gate test_bk48_wgsl_fence.py: LD-refusal + exfil-block + SUPER/ST
  controls + non-vacuity; lands IN the fence commit, blast radius
  wgsl_glyph_isa_v2.py only). Research landed NO engine or shader code;
  probe + RESEARCH_wgsl_fence_twin_af3e.md + the BK-48 row only.
- NOT probed: shader PARALLEL_ST/PUSH/CALL (BK-39 class), syscall
  handlers (Python-only by construction), BK-41's MMIO self-arm
  on-device. Numbers structural (source-line counts, register/RAM word
  values, run counts, one md5) — rule-1 floors do not attach.

### 2026-09-27 ~04:3x CDT — PHASE 1c RESEARCH TICK: the L1 shell's wc/head native-swap refusal MEASURED — enforced by a latent COMPILE FAILURE (dynamic seed block omits `_COMMON` + name seeds), not the documented 16-byte window that BK-24 retired; the V1 wc body additionally renders `310` as `O0` (2-digit counter ceiling) on real files; host shims stay, BK-46 filed (builder af3e62239ce2)

- Run selection re-verified: HEAD e18658d6 (my BK-45 research tick,
  02:47), tracked tree clean at claim (bk46 probes untracked), mailbox
  clean (newest RULING 2026-09-22, predates HEAD), monitor
  CLAIM_PENDING queue=0 stall_tier=0. QUEUE_STATE active=null, all
  items landed, DEFECT-30 resolved → Phase 1c research is the
  eligible tick. No re-research: question selected from the friction
  priority chain — R53_USE_LOG.md day 1 (operator: "no user surface
  exists yet") → the L1 verb surface audit (`grep -n 'if verb =='
  experiments/glyph_l1_shell.py` → 21 branches, only grep/tr native)
  → the pinned wc/head/tail refusal at :505-513 cites the PRE-BK-24
  16-byte window, which item-18 replaced (libc_runtime.py:41-64,
  256-byte streaming ring) and `_shell_native_collect` (:1054-1075)
  already no longer reads. Falsifiable on its face; measured by no
  existing RESEARCH/backlog row.
- Probes (untracked, landed modules only, verdicts from compiler
  stderr + returned strings + ring bytes, never handler stdout):
  probe_wc_swap_af3e.py (shell-level), dbg_wc_swap2_af3e.py (compile
  chain with stderr surfaced), dbg_wc_swap3_af3e.py (falsification
  leg: supply `_COMMON` + `wc_name` seed → compile → transpile → bake
  → GlyphRunner → BK-24 ring collect).
- Findings (measured): (1) `_shell_native("wc",…)` → ERR:SHELLNATIVE:wc
  on every fixture (md5 0b365dce36781f09cbc2d70bed3a85f3, cache on AND
  off) — gcc `error: '_n' undeclared`: the dynamic seed block
  (:968-971, :1003-1006) omits `_COMMON` (coreutils_port.py:72-93),
  which only the BK-11 fixture builder (:389) prepends; (2) with the
  preamble + name seed supplied, native wc ran ON-GLYPH and delivered
  `' 2  5 29 small.txt              '` (30 bytes) via the ring — the
  16-byte-window claim is false post-BK-24; (3) on a 309-byte file the
  same binary renders `40 80 O0 multi.txt` — the `char buf[3]`
  two-digit pad (coreutils_port.py:158-160) corrupts counters ≥ 100;
  landed fixtures never exceed 2 digits so the BK-11 gate cannot see
  it; (4) head in the dynamic path emits NOTHING (empty ring) —
  separate defect, recorded not root-caused.
- Verdict: the pinned refusal's CONCLUSION (host shims stay) survives
  on real files, but its documented MECHANISM is falsified twice over,
  and a naive "stale comment → flip the branch" swap would corrupt
  real output. BK-46 filed to systems/GLYPH_BACKLOG.md (gate
  test_bk46_native_wc_swap.py: seed-block fix + 3-digit RED leg +
  parity + accurate-comment clause; prereq BK-24 + BK-11, both
  landed; blast radius experiments/ + wc tool body only, BK-11
  fixtures must stay byte-exact). Research landed NO engine or shell
  code; probes + RESEARCH_wc_swap_refusal_af3e.md + the BK-46 row
  only. Numbers structural (stderr text, strings, byte counts, md5)
  — rule-1 floors do not attach.

### 2026-09-27 ~03:1x CDT — PHASE 1c RESEARCH TICK: VFS-attached syscall twins MEASURED — path containment is REAL on the VFS layer ('..' refused on 0x03/0x13, host-shaped absolute paths staged inside the image, host FS untouched) while RAM-dest containment is ABSENT (0x04/0x13 VFS dest loops land out-of-tile clean — BK-40's class extends to the VFS arms); BK-45 filed (builder af3e62239ce2)

- Run selection re-verified, not assumed: HEAD 4b0bb0c1 (my BK-44
  research tick, 02:5x), tracked tree clean at claim, mailbox clean
  (no RULING_* newer than my last commit), monitor CLAIM_PENDING
  queue=0 stall_tier=0. Queue empty → Phase 1c research is the
  eligible tick. No re-research: the question is the explicitly-open
  scope note in RESEARCH_fs_allow_asymmetry.md:109-111 ("whether the
  VFS layer re-implements or inherits the root check is unmeasured")
  and RESEARCH_fw_exfil_path_read.md:111 ("VFS vfs_write twin,
  source-read inference only") — measured by no existing
  RESEARCH/backlog row.
- Question: with a GlyphVfs attached (the item-25 reroute arms,
  glyph_isa_v2.py:1474-1484 / :1520-1531 / :1764-1776), does a
  CONTAINED USER task (tile (5,0,8,8), MODE_USER) gain the FS
  containment the host arms lack (BK-44's inversion), and does the
  fence-blind dest class BK-40 measured extend through the VFS arms?
- Probe probe_vfs_fence_af3e.py (untracked, landed modules only) at
  HEAD 4b0bb0c1; harness = the landed item-29 containment path +
  spawn(vfs=..., vfs_shared=True); verdicts from in-RAM syscall rc
  (word 198) + HOST filesystem state, never handler stdout; 3 runs
  byte-identical (md5 c1ac611a712160654dfddd7ed4be27ee):
  (1) 0x03 'q1.txt' in-tile data → rc 0 staged (overlay live);
  (2) 0x03 '../../' → rc -1 REFUSED by _guest_rel
  (glyph_vfs.py:316-338), nothing landed;
  (3) 0x03 '/tmp/b8w' → rc 0 but staged as tmp/b8w INSIDE the image;
  host /tmp/b8w verified ABSENT host-side after every run;
  (4) 0x13 '..' → rc -1 REFUSED; (5) 0x13 '/' → entry count served;
  (6) control: plain ST out-of-tile 168 → EXIT_FAULT fault_addr=672,
  mode→SUPER (E-K1 intact);
  (7) 0x04 VFS staged read, dest=168 OUT-of-tile → rc 2, 'VW' lands
  at 168/169 clean;
  (8) 0x13 VFS listing, dest=168 → listing bytes land clean.
- Verdict (measured, both directions): PATH containment REAL on the
  VFS layer (the root check the host arms lack exists only in the VFS
  twin); RAM-dest containment ABSENT (dest loops :1476-1478 /
  :1526-1529 / :1770-1774 are the same bounds-only shape as BK-40's
  host arms — the class extends; BK-40's "ran VFS-less" scope note
  now closed as "same defect, both routes"). Net posture: attachment
  state decides FS blast radius — VFS-attached = path-contained +
  RAM-uncontained; VFS-less = arbitrary host R/W + RAM-uncontained.
  BK-45 filed to systems/GLYPH_BACKLOG.md (VFS dest-loop consult,
  prereq BK-38..43 same sequenced engine commit family). Research
  landed NO engine code.
- Probe hygiene + the harness bug worth remembering: draft leg B used
  a 20-byte escape path → 60 PARALLEL_STs → 67 instructions → the
  write-through mirror SELF-OVERWROTE the program image (measured:
  execution died at instruction slot 40; image dump showed path bytes
  stamped over slots 40+; the SYSCALL never dispatched — the first
  run's "rc 0" was the harness's own tombstone, NOT a containment
  failure). Caught by instruction-dump re-derivation, fixed to ≤9-byte
  paths (34 instrs, the proven-safe geometry), documented in the
  RESEARCH receipt as a PARALLEL_ST-mirror hazard for probe authors.
  Env: GLYPH_FS_ALLOW irrelevant to VFS arms (no consult, source-read
  confirmed); temp dirs cleaned in finally; host fixtures asserted
  absent post-run.
- All quantities structural (return codes, fault_addr, file
  existence, entry counts, a results-blob md5); NO rate/latency/cost
  claim (rule-1 floors do not attach). NOT verified: 0x01/0x08/0x09
  arms (no VFS reroute exists); 0x07/0x12 RUN under attachment (RUN
  has no VFS arm — source-read); vfs_read's ext2/debugfs image
  fallback arm separately exercised (leg 7 read the staged overlay;
  the dest loop is shared code but the image arm was not run from a
  synced image); PngVfs wrap/unwrap internals; WGSL twin; whether
  sync() re-exposes anything new (host-side, not guest-reachable).

### 2026-09-27 ~02:4x CDT — PHASE 1c RESEARCH TICK: GLYPH_FS_ALLOW asymmetry MEASURED — under the identical empty env 0x13 FILE_LIST is REFUSED while 0x03 FILE_WRITE writes an arbitrary host file and 0x04 FILE_READ exfiltrates host file content into OUT-OF-TILE RAM; the containment posture is the inverse of its own landing rationale; BK-44 filed (builder af3e62239ce2)

- Run selection re-verified, not assumed: HEAD d61dc186 (my BK-43
  research tick, 02:1x), tracked tree clean at claim, QUEUE_STATE active
  null / all items landed, mailbox rule clean (find .builder_queue -name
  'RULING_*.md' -newermt @1790493459 EMPTY), monitor CLAIM_PENDING
  queue=0 stall_tier=0. Queue empty → Phase 1c research is the eligible
  tick. No re-research: the question is the explicitly-open
  "source-read observation, not a measured attack-surface diff" in
  RESEARCH_fw_exfil_path_read.md:115-117 — measured by no existing
  RESEARCH/backlog row.
- Question: is the BK-15 containment posture actually ordered the way
  its rationale claims ("enumeration is the more invasive primitive, it
  must not be cheaper to reach than RUN", glyph_isa_v2.py:577-579)?
  Source-read says only 0x13 consults _get_fs_allow_roots (:575-590,
  consult at :1781-1785) while 0x03/0x04 have no root check — this
  tick converted that observation into a measurement.
- Probe probe_fs_allow_asym_af3e.py (untracked, landed modules only) at
  HEAD d61dc186, harness = the landed item-29 containment path
  (GlyphProcessTable.spawn(tile=(5,0,8,8))); GLYPH_FS_ALLOW popped/set
  around every wait() (A/B legs share one process; env restore in
  finally); verdicts from HOST FILE CONTENTS + the syscall rc parked
  in-RAM by the program itself (word 198), never handler stdout; 3 runs
  byte-identical (md5 68b44ea7200b3473a45277636b4e4874):
  (1) 0x13 FILE_LIST '/tmp/b7d', env unset → rc -1, dest zero —
  containment live; (2) 0x03 FILE_WRITE '/tmp/b7w' in-tile 'WX' → rc 0,
  host file exactly b'WX' — arbitrary host write, zero containment;
  (3) 0x04 FILE_READ '/tmp/b7r' (b'AUTUMN') dest=168 OUT-of-tile →
  rc 6, 'AU' at 168/169 — arbitrary host read AND the BK-40 fence-blind
  dest arm re-measured with env isolation; (4) control: same listing
  with GLYPH_FS_ALLOW=/tmp/b7d → rc 1, dest b'k1\0' (leg 1's refusal is
  the containment, not a dead harness); (5) ST control traps
  (fault_addr=672=168*4, E-K1 intact).
- Verdict: the inversion is measured — the destructive primitives
  (overwrite host files, exfil host file content) are reachable with the
  env empty; the naming primitive is refused. A confined USER task under
  the default env can destroy host state and copy host secrets into
  guest RAM but cannot list the directory it is destroying. BK-44 filed
  to systems/GLYPH_BACKLOG.md (extend the root check to 0x03/0x04
  deny-by-default, or re-scope the BK-15 claim; prereq BK-42+BK-43 —
  likely shares the _read_path consult site, same sequenced engine
  commit). Research landed NO engine code.
- Probe hygiene: two draft-1 assembler-staging bugs (byte placeholder
  not interpolated into the LDI template; stage_bytes handed 1-tuples)
  caught on read-back BEFORE the first run; geometry pre-checked against
  the documented PARALLEL_ST mirror trap (34 instructions < 40); env and
  host fixtures restored/cleaned in finally blocks.
- All quantities structural (file bytes, in-RAM return codes,
  fault_addr, line numbers, a results-blob md5); NO rate/latency/cost
  claim (rule-1 floors do not attach). NOT verified: WGSL twin;
  0x01/0x08/0x09 path arms; VFS-attached twins (no VFS attached in the
  probe); L1/L2 shell end-to-end (verbs route host-side by source-read);
  armed-KSYS_PC interaction; whether any landed fixture relies on
  un-root-checked 0x03/0x04 (BK-44 gate family leg checks at landing).

### 2026-09-27 ~02:5x CDT — PHASE 1c RESEARCH TICK: 0x07/0x12 RUN arm MEASURED — the fence-blind `_read_path` decoder SELECTS THE EXECUTED BINARY (allowlist check runs on attacker-assembled out-of-tile bytes) and RUN2's argv carries out-of-tile RAM through execve(); BK-43 filed (builder af3e62239ce2)

- Run selection re-verified, not assumed: HEAD 6677603b (my BK-42
  research tick, 02:0x), tracked tree clean at claim, mailbox rule clean
  (find .builder_queue -name 'RULING_*.md' -newermt @1790492732 EMPTY),
  monitor CLAIM_PENDING queue=0 stall_tier=0. Queue empty → Phase 1c
  research is the eligible tick. No re-research: the question is the
  explicitly-open "NOT verified" arm of RESEARCH_fw_exfil_path_read.md
  (0x07/0x12 RUN = "source-read inference only") — answered by no
  existing RESEARCH/backlog row.
- Question: does the GLYPH_RUN_ALLOW containment on 0x07/0x12 actually
  hold from a confined USER task? Unlike 0x03, the RUN family HAS a
  deny-by-default allowlist (glyph_isa_v2.py:1576-1579, :1723-1726) —
  but the string it checks is assembled by `_read_path` (:1381-1408),
  the decoder BK-42 measured walking out-of-tile, and RUN2's argv args
  are documented "data, not targets" (:1716-1719, no consult).
- Probe probe_run_arg_af3e.py (untracked, landed modules only) at HEAD
  6677603b, harness = the landed item-29 containment path
  (GlyphProcessTable.spawn(tile=(5,0,8,8))); verdicts from HOST FILE
  CONTENTS; runner fixtures created+cleaned by the probe from a
  committed template; markers asserted absent before every leg; 3 runs
  byte-identical (md5 e238a3ab4ebbfbdbdb4f94dd45cfeb09):
  (1) PATH SMUGGLE — in-tile '/tmp/run' (8 bytes, NO NUL in-tile),
  out-of-tile 168..172 seeded 'r','5','r','5',0 -> `_read_path` decoded
  '/tmp/runr5r5', realpath+allowlist PASSED, the runner EXECUTED: which
  host binary runs was decided by bytes the task cannot lawfully
  address — the fence-blind path read is the target-selection
  primitive for host EXECUTION;
  (2) ARGV LEAK — 0x12, allowed target, arg1_addr=168 (out-of-tile)
  seeded 'SRC5' -> host marker contains exactly 'ARG1=[SRC5]':
  out-of-tile RAM crossed execve() as ARGV;
  (3) allowlist control live; (4) deny-by-default holds (env unset ->
  refused) — RUN's posture is stricter than 0x03's, but the check
  itself is defeated by the decoder it consumes; (5) ST control traps
  (fault_addr=672=168*4, E-K1 intact).
- Probe hygiene: THREE drafts caught before any finding — draft-1
  self-overwrite via the PARALLEL_ST pixel mirror (words 160..191 =
  instruction slots 40..47; 32-byte paths -> staging clobbered the
  program tail, CONTROL leg failed, only 13 bytes staged); draft-2
  escaped-NUL literals (probe's own asserts refused); draft-3 runner
  template/marker-filename mismatch (control leg failed again — a
  failing CONTROL leg in this lane has now twice been probe bug, not
  substrate behavior; found by testing the fixture standalone).
- Verdict: the RUN arm is measured open. BK-43 filed to
  systems/GLYPH_BACKLOG.md — needs NO new consult sites beyond BK-42's
  `_read_path` one; it is the measured motivation for fixing the SHARED
  decoder (one site covers 0x03/0x04/0x07/0x08/0x12/0x13) in the same
  sequenced BK-38..43 engine commit. Research landed NO engine code.
- All quantities structural (file bytes, exit codes, fault_addr, line
  numbers, a results-blob md5); NO rate/latency/cost claim (rule-1
  floors do not attach). NOT verified: WGSL twin; 0x01/0x08/0x04 path
  arms (source-read inference); armed-KSYS_PC posture interaction;
  whether landed fixtures depend on out-of-tile path/argv bytes; the
  smuggle leg's realism boundary — it ASSUMES an allowlisted
  near-collision path exists (operator allowlists their runners; guest
  names a prefix collision); fully attacker-chosen arbitrary paths
  against an empty allowlist were NOT measured (deny-by-default holds
  there, leg 4).

### 2026-09-27 ~02:3x CDT — PHASE 1c RESEARCH TICK: 0x03 FILE_WRITE exfiltration MEASURED — a tiled USER task writes guest RAM bytes to arbitrary host paths, and `_read_path` itself is a fence-blind cross-fence read; BK-42 filed (builder af3e62239ce2)

- Run selection re-verified, not assumed: HEAD a893ad13 (my BK-41
  research tick, 02:1x), tracked tree clean at claim, mailbox rule clean
  (find .builder_queue -name 'RULING_*.md' -newermt @1790491507 EMPTY),
  monitor CLAIM_PENDING queue=0 stall_tier=0. Queue empty → Phase 1c
  research is the eligible tick. No re-research: the question is the
  explicitly-open honesty note in RESEARCH_syscall_fence_bypass.md:124
  and RESEARCH_ksys_pc_self_arm.md:102 ("0x03 FILE_WRITE exfiltration
  side (still unprobed)") — answered by no existing RESEARCH/backlog row.
- Question: can a tiled USER task move guest RAM bytes to a HOST file it
  names? Probe probe_fw_exfil_af3e.py (untracked, landed modules only)
  at HEAD a893ad13, harness = the landed item-29 containment path
  (GlyphProcessTable.spawn(tile=(5,0,8,8))), verdicts from HOST FILE
  CONTENTS (byte-compared), never exit codes; fixtures unlinked+asserted
  absent before every leg; 3 runs byte-identical (md5
  d7a9aa69260d2173fc2e61c98ef6e511):
  (1) direct exfil — canary 'F','K' seeded at OUT-of-tile words 172/173,
  FILE_WRITE data_addr=172 len=2 path /tmp/b4a → EXIT_OK, host file
  contains exactly b'FK' (handler data loop :1474-1499 has no
  _addr_in_box consult; sink open(path,"wb") :1499);
  (2) composite — LD the out-of-tile canary (BK-38), ST in-tile to 192,
  FILE_WRITE from 192 → b'F' lands host-side (survives a hypothetical
  fenced handler data view);
  (3) NEW channel — path staged '/tmp/b4d' WITHOUT terminator →
  _read_path (:1393-1408, shared by 0x03/0x04/0x07/0x12/0x13) decodes
  past the tile into out-of-tile words 168/169 ('X','Y'); host file
  appears at '/tmp/b4dXY' with the in-tile payload b'Z': the syscall
  PATH argument is itself a fence-blind cross-fence read — the filename
  is the exfil;
  (4) non-vacuity control — in-tile data lands b'FK' (handler live);
  (5) E-K1 control — plain ST to 172 traps (fault_addr=688, mode→SUPER).
- Probe hygiene (all drafts caught BEFORE evidence; full chain in the
  receipt): draft-1 staging overwrote its own program tail via the
  PARALLEL_ST pixel mirror (48 instrs, mirror pixel 160 = instrs 40-47 —
  BK-40's documented trap) + 2-byte canary in one word vs byte-per-word
  handler reads; draft-2 missing NUL terminators (the "failure" that
  became finding 3), terminator word clobbering a canary at 168, and an
  LD-stage store to word 176 = row 5 col 16 (OUTSIDE the 8-wide tile —
  E-K1 correctly trapped it; stage → 192).
- Verdict: the exfil side is open; with BK-42 the arm map is closed —
  every guest-reachable cross-tile/host access is fence-blind except ST
  (writes: BK-39/40; reads: BK-38 + now FILE_WRITE data + _read_path).
  BK-42 filed to systems/GLYPH_BACKLOG.md (adds two consult sites: the
  FILE_WRITE data loop and the shared path decoder; prereq
  BK-38+39+40+41 as one sequenced commit). Research landed NO engine
  code.
- All quantities structural (file bytes, exit codes, fault_addr, line
  numbers, a results-blob md5); NO rate/latency/cost claim (rule-1
  floors do not attach). NOT verified: WGSL twin on-device; 0x07/0x12
  RUN path args + VFS vfs_write twin (source-read inference only);
  FILE_WRITE under the BK-41 armed-KSYS posture; whether landed fixtures
  rely on unconfined FILE_WRITE (checked at landing per BK-40 family
  convention).

### 2026-09-27 ~02:1x CDT — PHASE 1c RESEARCH TICK: KSYS_PC (word 8194) is guest-writable — the BK-40 "cheap posture" is guest-defeatable AND guest-self-armable (USER→SUPER escape); BK-41 filed, BK-40 posture clause REJECTED (builder af3e62239ce2)

- Run selection re-verified, not assumed: HEAD 3ba4ad77 (my BK-40
  research tick, 01:4x), tracked tree clean at claim, QUEUE_STATE all
  landed, mailbox rule clean (find .builder_queue -name 'RULING_*.md'
  -newermt @1790490491 EMPTY), monitor queue=0 stall_tier=0. Queue
  empty → Phase 1c research is the eligible tick.
- Question (BK-40's explicitly unmeasured alternative): its gate spec
  offered "arm KSYS_PC by default on tiled spawns (E-K2 dispatcher) —
  must be measured ... before choosing". But KSYS_PC is word 8194 in
  the BOX_MMIO block — guest-visible RAM that BK-39 measured
  fence-blind to PARALLEL_ST. Probe probe_ksys_arm_af3e.py (untracked,
  landed modules only) at HEAD 3ba4ad77, harness = the landed
  GlyphProcessTable.spawn(tile=(5,0,8,8)) path, gadget = plain ST of
  0xC0FFEE to out-of-tile word 176 at pixel row 6; 3 runs byte-
  identical (md5 831ea1d8714f9f87c7a608e540618cdd):
  (1) armed posture + hostile gadget → EXIT_OK, 0xC0FFEE lands at 176,
  mode ends SUPER: E-K2 dispatch (glyph_isa_v2.py:1132-1158) executes
  guest-chosen pixels in SUPER where the ST fence is mode-gated
  (:1041); (2) armed posture + one fence-blind PARALLEL_ST of 0 into
  word 8194 → ksys reads 0, the DIRECT fence-blind handler branch runs
  (:1156-1158), ring bytes land out-of-tile clean — one instruction
  defeats the posture; (3) posture OFF at spawn, guest PARALLEL_STs
  393216 into 8194 itself → dispatch fires to the in-tile gadget,
  value lands clean: the guest MINTS its own USER→SUPER escape with no
  kernel image; (4) control: plain ST to 176 traps (EXIT_FAULT, E-K1
  live).
- Docstring falsified (measured): tools/glyph_containment.py's item-29
  landing docstring claims "a task that never exits USER mode cannot
  reach SUPER"; leg (3) is a measured counterexample — once a fence-
  blind write can arm E-K2, KJMP/SYSRET/kernel are not the only
  USER→SUPER paths.
- Probe hygiene (two drafts caught on read-back, full chain in the
  receipt): draft-1's numpy img[6:8] gadget paste on a 2-row image was
  a SILENT no-op (out-of-range slice) — legs jumped to black pixels;
  draft-2 first run had dropped the host-side KSYS arming so leg A
  never armed and leg B "disarmed" an already-zero word (as-run it was
  a BK-40 L1 reproduction, not the disarm claim). Both fixed before
  any finding was recorded; draft-2 now asserts the gadget dispatch
  pixel is non-black pre-evidence.
- Verdict: the armed-KSYS_PC posture is NOT a cheaper BK-40 fix.
  BK-40's posture clause marked MEASURED/REJECTED in
  systems/GLYPH_BACKLOG.md; BK-41 filed (fence the BOX_MMIO config
  block kernel-write-only + the L1-L6 gate spec); prereq BK-38+39+40
  as one sequenced engine commit. Research landed NO engine code.
- All quantities structural (word values, exit codes, booleans, a
  results-blob md5); NO rate/latency/cost claim (rule-1 floors do not
  attach). NOT verified: WGSL twin on-device (E-K2 by source read
  only), 0x03 FILE_WRITE exfil side (still open from BK-40 tick),
  MODE_LATCH interplay under a real kernel scheduler, SUPER-mode
  CALL/PUSH image-plane blast radius from a self-armed dispatch.

### 2026-09-27 ~01:4x CDT — PHASE 1c RESEARCH TICK: syscall layer is a fourth fence-bypass class — 0x02 READ / 0x04 FILE_READ / 0x13 FILE_LIST write any RAM word, 0x11 STORE_CODE writes any image pixel, all clean-exit from a tiled USER task; BK-40 filed (builder af3e62239ce2)

- Run selection re-verified, not assumed: HEAD 802b6ac8 (my BK-39
  research tick, 01:11), tracked tree clean at claim, QUEUE_STATE all
  22 items landed, mailbox rule clean (find .builder_queue -name
  'RULING_*.md' -newermt @<HEAD-epoch> EMPTY), monitor queue=0
  stall_tier=0. Queue empty → Phase 1c research is the eligible tick.
- Question (the last unprobed write class): BK-38 (LD/PARALLEL_LD reads)
  and BK-39 (PARALLEL_ST write + BOX0 self-grant, PUSH/CALL image-plane)
  left the SYSCALL handlers unprobed — they copy host/kernel bytes into
  self.memory with bounds checks only. Probe
  probe_syscall_fence_af3e.py (untracked, landed modules only) at HEAD
  802b6ac8, harness = GlyphProcessTable.spawn(tile=(5,0,8,8)), target
  word 168 (row 5 col 8, first word outside), full stdout byte-identical
  across 3 runs (md5 cee48c7b5a5e328693361564b7b761f4):
  (1) 0x02 READ dest=168 → clean exit, memory[168]==0x4B; (2) 0x04
  FILE_READ '/tmp/b40' → 'KFENCE' lands at 168 clean (host-file
  exfil into out-of-tile RAM); (3) 0x13 FILE_LIST '/tmp' → entry bytes
  land at 168 clean; (4) 0x11 STORE_CODE pixel 200→168 → out-of-tile
  pixel changed (0,0,0)→(65,66,67) — instruction-stream class; (5)
  controls green: plain ST to 168 traps (fault_addr=672, mode→SUPER —
  E-K1 intact), 0x02/0x04 in-tile legs land. Root cause unchanged from
  BK-38/39: _addr_in_box has exactly one call site (the ST arm :1041);
  handlers :1451-1455 / :1544-1547 / :1796-1800 / :1689-1701 never
  consult it. Reachability: spawn() never arms KSYS_PC so the direct
  _handle_syscall branch (:1157-1158) runs user-selected handlers.
  With BK-38/39 this closes the write-arm map: every guest-reachable
  RAM/image write path is fence-blind except ST.
- Probe-hygiene disclosure (three draft defects, all caught on
  read-back BEFORE any finding was recorded, full chain in the
  receipt): draft-1 path staging at word 300 let PARALLEL_ST's
  write-through pixel mirror corrupt the probe's own instruction
  stream (FILE_READ/STORE_CODE silently never ran); draft-2's controls
  used strip()-truthiness on NUL strings (could not fail); draft-3's
  out-of-tile target 224 was actually INSIDE the tile — the ST
  control's correct landing exposed the geometry error.
- BACKLOG: BK-40 filed to systems/GLYPH_BACKLOG.md (fence the four
  syscall DATA write arms, or arm KSYS_PC by default on tiled spawns;
  gate spec tests/test_bk40_syscall_fence.py L1-L8 with RED legs +
  non-vacuity + family; prereq BK-38/39 — same consult sites; NOT
  claimable without Jericho per the backlog header).
- One research item per tick; research landed NO engine code. All
  quantities are structural (byte values, exit codes, fault_addr, line
  numbers, pixel tuples, a probe-stdout md5); NO rate/latency/cost
  claim (rule-1 floors do not attach). NOT verified: WGSL twin on-device
  (handlers are Python-only; source-read only), 0x03 FILE_WRITE
  exfiltration side, KSYS_PC-armed posture efficacy, STORE_CODE
  RAM-grid blast radius beyond the image plane.

### 2026-09-27 ~01:1x CDT — PHASE 1c RESEARCH TICK: PARALLEL_ST fence bypass measured — a tiled USER task can rewrite its own confinement (BOX0 self-grant); BK-39 filed (builder af3e62239ce2)

- Run selection re-verified, not assumed: HEAD bf6f2b6e (my BK-38
  research tick, 00:53), tracked tree clean at claim, QUEUE_STATE all
  22 items landed / active null, mailbox rule clean (find
  .builder_queue -name 'RULING_*.md' -newermt @<HEAD-epoch> EMPTY),
  monitor queue=0 stall_tier=0. Queue empty → Phase 1c research is the
  eligible tick.
- Question (sibling arms of the BK-38 read gap): BK-38 measured that
  LD reads are unguarded, and the WRITE side was assumed fenced because
  `_addr_in_box` fires at the ST trap (glyph_isa_v2.py:1041). But ST is
  not the only guest-reachable write arm. Probes
  probe_pst_fence_af3e.py / probe_pst_disarm_af3e.py /
  probe_pst_escalation_af3e.py / probe_push_mechanics_af3e.py
  (untracked, landed modules only) measured at HEAD bf6f2b6e, harness =
  GlyphProcessTable.spawn(tile=(5,0,2,4)):
  (1) PARALLEL_ST out-of-tile → rc=EXIT_OK, mode stays USER,
  memory[164]==0x0ADF00D — silent cross-fence WRITE, while plain ST to
  the SAME word traps (fault_addr=656, mode→SUPER); root cause:
  PARALLEL_ST arm :1264-1295 has a bounds check (:1273) only, zero
  _addr_in_box calls. (2) FULL ESCALATION: from inside its tile the
  task PARALLEL_STs BOX0_LO:=0 / BOX0_HI:=65536 (words 8195/8196), then
  plain-STs word 999 clean — the confined task REWRITES ITS OWN
  CONFINEMENT to cover all RAM. (3) PARALLEL_LD returns the
  out-of-tile canary (read-side parity with BK-38). (4) PUSH lands an
  out-of-tile IMAGE-plane pixel (word 164 → pixel (4,5) = 0x003039,
  verified post-run; _mem_write :702-708 has no box consult) —
  instruction-stream corruption class. (5) Disarm/re-anchor legs
  (TILE_H:=0, TILE_ROW:=0) do NOT let the SUBSEQUENT ST through (E-K1
  reads tile words live) — only the BOX0 self-grant yields a clean
  out-of-fence store.
- Escalation probe byte-identical across 3 runs (md5
  d527708d67897cab2521fda20f40a982); boundary probe deterministic:
  True across 3 internal runs. Probe-hygiene disclosure: the boundary
  probe's first draft seeded TILE_H=0 post-spawn (disarming the fence
  under its own controls — the ST control still trapped via BOX
  ranges, masking it); caught on read-back, fixed before evidence
  taken (final 12 case prints all show tile_h_word: 2).
- Load-bearing why: item-29's containment story ("the engine's
  existing box check then traps any out-of-tile user store",
  tools/glyph_process.py:122-123) is overstated by one opcode class.
  Every tile-containment claim in items 26/29/34/35/38 inherits a
  fence the guest can edit. WGSL twin NOT exposed BY SOURCE READ (not
  probed on-device): _OPCODE_ORDER (wgsl_glyph_isa_v2.py:34-39)
  omits all PARALLEL opcodes (ENG-1 unknown-opcode halt) and walk_st
  checks addr_in_box (:451).
- BACKLOG: BK-39 filed to systems/GLYPH_BACKLOG.md (fence all
  guest-reachable write arms + make BOX*/TILE* config kernel-write-only
  from USER mode; gate spec tests/test_bk39_write_fence.py L1-L7 with
  RED legs + non-vacuity + family; prereq BK-38 — same consult sites,
  land together or in one engine commit; NOT claimable without Jericho
  per the backlog header).
- One research item per tick; research landed NO engine code. All
  quantities are structural (word values, exit codes, fault_addr, line
  numbers, pixel tuples, a probe-output md5); NO rate/latency/cost
  claim (rule-1 floors do not attach). NOT verified: WGSL on-device
  run; whether any landed fixture relies on the bypass (BK-39 family
  leg checks at landing time); RAM-grid blast radius of the PUSH
  image-plane leg.
- Files this tick: 4 probes + RESEARCH receipt (.builder_queue/),
  systems/GLYPH_BACKLOG.md BK-39 row, CURRENT_TICKET.json reconciled,
  this ledger entry. Next tick: queue supply if it appears, else
  research per Phase 1c.

### 2026-09-27 ~00:5x CDT — PHASE 1c RESEARCH TICK: assembler operand-arity silent drop measured; BK-37 filed (builder af3e62239ce2)

- Run selection re-verified, not assumed: HEAD 10233635 (BK-36 landing,
  23:49), tracked tree clean at claim, QUEUE_STATE.json all 22 items
  landed / active null, mailbox rule clean (find .builder_queue -name
  'RULING_*.md' -newermt @<HEAD-epoch> EMPTY), monitor queue=0
  stall_tier=0. Queue empty → Phase 1c research is the eligible tick.
- Question (carried from the BK-36 research tick's folded candidate,
  previously unmeasured): does the assembler silently drop extra
  operands? Probe `.builder_queue/probe_arity_af3e.py` (untracked,
  landed modules only) measured at HEAD 10233635, exit 0, deterministic
  across 2 runs (diff clean): `ADD r1 r2 r3` assembles CLEAN encoding
  r1+=r2 with r3 discarded; `ADD r1 r2 bogus` also assembles clean
  (non-register tokens dropped too); `LDI r1 5 r3` drops the extra;
  `ADD r1` leaks a bare IndexError; `MOV r1 r2` is loud but leaks
  KeyError (BK-17 L3 territory). Root cause: per-opcode branches read
  operands positionally with no len(args) check (glyph_isa_v2.py
  ADD-class :437-439, LDI :430-435; only SYSCALL is arity-aware :458);
  pre-loop validation (:386-409) checks labels/jump bounds only.
- Load-bearing why: ISA is 2-operand (ADD rd rs = rd += rs); an
  RISC-V-reflex human or LLM writes `ADD r1 r2 r3` meaning r1=r2+r3 and
  gets a clean-HALT wrong-answer program — invisible to every runtime
  gate. WGSL twin is NOT a backstop: shader generated from OpcodeMapV2
  (tools/glyph_gpt/runner.py:150), defect is upstream in the shared
  assembler, so parity gates cannot catch it.
- BACKLOG: BK-37 filed to systems/GLYPH_BACKLOG.md (arity guard +
  register-token validation; gate spec tests/test_bk37_assembler_arity.py
  L1-L6 with RED legs + non-vacuity + family; NOT claimable without
  Jericho per the backlog header).
- One research item per tick; research landed NO engine code. All
  quantities are structural (encoding tuples, exit codes, one probe
  process, deterministic across 2 runs); NO rate/latency/cost claim
  (rule-1 floors do not attach). NOT verified: whether any landed
  fixture relies on the silent drop (BK-37 L6 checks at landing time);
  IndexError-leak exact traceback text (asserted class only).
- Files this tick: probe + RESEARCH receipt (.builder_queue/),
  systems/GLYPH_BACKLOG.md BK-37 row, CURRENT_TICKET.json reconciled,
  this ledger entry. Next tick: queue supply if it appears, else
  R2.3-named sub-steps per RULING clause 2, else research.
- Sibling-session note: a concurrent subagent touched the backlog file
  mid-edit (guard warning); BK-37 landed via targeted patch after
  re-read; BK-35/36 rows verified intact post-patch.

### 2026-09-26 ~23:1x CDT — PHASE 1c RESEARCH TICK: move() damage measured (100% blackout of a dragged reaped window); BK-36 filed (builder af3e62239ce2)

- Rung selection re-verified, not assumed: HEAD dd3cdd26 (item-41 ledger
  lineage), tracked tree clean, QUEUE_STATE all-landed / active=None,
  mailbox rule clean (`find .builder_queue -name 'RULING_*.md'
  -newermt @1790476433` EMPTY). The standing R1.4 directive was checked
  BEFORE research: its "known state" is STALE — R1.4 LANDED 2026-09-21
  ~16:4x (PRODUCT_LANE_STATE.md:3055, RECEIPT_R14_wgsl_convergence.md,
  conformance WGSL legs 8-11 at tests/test_box_abi_conformance.py:249+).
  Re-proven BY THIS RUN: .builder_queue/probe_r13_wgsl_fleet.py exit 0,
  MATCH, halt @458, results {714:6, 728:12, 748:20, 763:30},
  receipt 0x5eed0005, done 0b1011. R1.4 is closed; R2.3 unblocked; with
  the queue empty, Phase 1c research is the eligible tick.
- RESEARCH RECEIPT: .builder_queue/RESEARCH_move_damage_blackout.md.
  Question: is item-38's disclosed move() word-anchor an edge case or a
  product defect? Probe .builder_queue/probe_move_damage_af3e.py
  (untracked, landed modules only) measured on HEAD dd3cdd26:
  (a) origin-painter moved (20,10) -> composite lit 1 -> 0;
  (b) full-tile painter (USER guest paints ALL 15 cells inside its own
  fence, exit 0, pre-move composite 15/15) moved -> lit 15 -> **0 of 15
  = 100% blackout**, while task RAM still holds all 15 words at the old
  addresses (composite reads cpu.memory[rr*W_MEM+cc] with the moved
  rect, tools/glyph_compositor.py:213). item-38's C4 leg asserts the
  black cell as EXPECTED — the gate masks the defect; adjacent
  regression this tick: item-38+39+40+41 gates 38 passed (0.16s).
- BACKLOG: BK-36 filed to systems/GLYPH_BACKLOG.md (snapshot-at-reap
  fix options 1-3 cheapest-first; gate spec tests/test_bk36_move_
  snapshot.py L1-L6, RED legs named; NOT claimable without Jericho per
  the backlog header). Folded in: assembler silently drops extra
  operands on 3-operand ADD/MUL (glyph_isa_v2.py:436-438) — this
  probe's own first draft hit it and misread the correct fence trap
  (fault_addr 0x14000, dbg_fill_tile_af3e.py) as a product bug.
- One research item per tick; research landed NO engine/compositor
  code. Numbers are structural cell counts/exit codes from one probe
  process, deterministic across 2 runs; NO rate/latency/cost claim
  (rule-1 floors do not attach). NOT verified: WGSL path for the move
  finding (CPU oracle only); item-39/40 repaint interaction with a
  post-drag composite.
- Files this tick (all untracked or 1-line backlog append): probe +
  dbg script + RESEARCH receipt (.builder_queue/), systems/
  GLYPH_BACKLOG.md BK-36 row, this ledger entry. Next tick: take the
  queue if new supply appears; else R2.3-named sub-steps per the R1.4
  ruling clause 2, else research.

### 2026-09-26 ~22:5x CDT — CLAIM QUEUE item 41 (dynamic process lifecycle & spatial task manager) LANDED; 10-leg gate GREEN, both RED legs discriminating (builder af3e62239ce2)

- Provenance at claim: HEAD eaddb5a0 (item-40 pin), tracked-dirty = 0;
  mailbox rule clean (`find .builder_queue -name 'RULING_*.md'
  -newermt @1790476433` EMPTY). Watchdog supplied only a title; brief
  authored per the skeleton-handoff contract
  (BRIEF_item41_taskmgr.md) BEFORE implementation — check_brief PASS,
  --self-test exit 0.
- LANDED: tools/glyph_taskmgr.py (GlyphTaskManager, pure consumer over
  the item-26 GlyphProcessTable + item-38 GlyphCompositor):
  pause/resume as a manager-side overlay (the landed table state
  machine drives the re-entry guard and is never overloaded — loud
  refusals on unknown/exited/not-paused); kill(pid) = SIGKILL analog
  at a run boundary (a not-yet-run task reaped EXIT_FAULT with NO
  guest execution — PRT stream empty, no composite paint; refusal
  loud on an already-exited task); run_ready() advances non-paused
  tracked tasks one cooperative run and marks windows reaped on the
  LIVE comp._windows record; open_manager()/refresh() place a fenced
  manager tile at the locked rect (2,0) 7x4 and run ONLY their own
  pid (comp.run_all() is compositor-global and would execute app
  tasks that are merely being displayed); the manager guest paints
  one state cell per task from kernel-seeded words (green ready,
  amber paused, red exited-fault, dim exited-ok; zero word paints
  nothing); close_window(wid) = reaped-only set_visible(False)
  retirement (append-only records), live-tile close refused loud.
- Gate: tests/test_item41_taskmgr.py, 10 legs T1-T8 + N1 + N2, tails
  pasted in RECEIPT_item41_taskmgr.md: RED 1 (run_ready ignores
  paused) output/item41_red1.txt — T3+T8 failed rc=1; RED 2 (kill
  marks EXIT_OK) output/item41_red2.txt — T2+T5 failed rc=1; GREEN
  output/item41_green_final.txt — "10 passed in 0.07s", rc=0.
  Module restored byte-exact between runs (md5
  3667df7c4b7950083ab94bd964321a49 asserted by the driver
  red_driver_item41.sh). Adjacent regression on this tree: item-38 +
  item-39 + item-40 gates 28 passed.
- Gate-caught defects fixed in-scope: (1) run_ready() overloading the
  table's state with "running" tripped the landed _run_task re-entry
  refusal; (2) comp.run_all() global-run replaced with scoped per-pid
  waits; (3) the reaped flag was written through comp.window() — a
  COPY — and silently no-oped (T7 caught it); (4) state-cell mapping
  aligned to the landed guest-paint idiom. No guard weakened.
- Honesty: kill is NOT mid-run termination; "signals" carry no
  preemption/interrupt semantics (cooperative commit-between-runs);
  no GPU/WGSL execution (N1 pins glyph_isa_v2.py md5
  5a672d7d5a94a7b20f927f554b8a90c0 = HEAD's blob); no rates/latencies
  asserted (rule-1 floors do not attach).
- Queue: item-41 -> landed. CLAIM QUEUE is now EMPTY (items 19..41
  all landed). Next tick: PHASE 1c research tick (one RESEARCH_*.md
  receipt + systems/GLYPH_BACKLOG.md row, per the ledger protocol)
  unless a new CLAIM QUEUE item or binding RULING appears first.

### 2026-09-26 ~22:1x CDT — CLAIM QUEUE item 40 (desktop notification daemon & system tray ABI) LANDED; 10-leg gate GREEN, both RED legs discriminating (builder af3e62239ce2)

- Provenance at claim: HEAD bef36c77 (item-39 pin), tracked-dirty = 0;
  mailbox rule clean (`find .builder_queue -name 'RULING_*.md'
  -newermt @1790475341` EMPTY). Watchdog supplied only a title; brief
  authored per the skeleton-handoff contract (BRIEF_item40_notify.md)
  BEFORE implementation — check_brief PASS, --self-test exit 0.
- LANDED: tools/glyph_notify.py (GlyphNotifyDaemon, pure consumer over
  the item-38 GlyphCompositor): toast queue QUEUE_CAP=8 with loud
  refusals that leave the queue unchanged; dispatch() places each
  toast as a REAL compositor window (stacked TOAST_PITCH apart,
  arrival-order z above content, hit_test confirms); expire_top()
  retires the OLDEST toast via set_visible(False) (the compositor has
  NO close_window — records append-only) and re-stacks survivors via
  move(); agent contract register_agent (request cell must be INSIDE
  the agent's own tile) + guest-computed request word
  magic<<24|level<<16|payload + harvest() consume-then-judge (second
  harvest enqueues nothing; bad magic quarantined LOUD, slot still
  consumed); tray ABI register_applet/set_applet_state with respawn
  repaint at the locked rect (item-33 refresh idiom adapted); toast
  tasks paint from their own TILE_ROW/COL (item-38 C7 pattern,
  addresses imported — never hardcoded).
- Gate: tests/test_item40_notify.py, 10 legs T1-T8 + N1 + N2, tails
  pasted in RECEIPT_item40_notify.md: RED 1 (toast z pinned 0)
  output/item40_red1_red2.txt — T1 failed rc=1; RED 2 (harvest
  consumption removed) — T2 failed rc=1; GREEN
  output/item40_green_final.txt — "10 passed in 0.08s", EXIT=0.
  Module restored byte-exact between runs (md5
  d5cd0ed7b478e73954597d044ac7142f asserted by the driver). Adjacent
  regression on this tree: item-38 + item-39 gates 18 passed.
- Gate-caught defects fixed in-scope: expire popped the NEWEST toast
  while re-stacking rows below it (predicate could never fire);
  _repaint_tray called a nonexistent close_window; repaint-before-
  open; first-draft T3 legs contradicted landed item-38 C4
  (word-anchored move -> old rows composite black) — TEST aligned to
  the landed contract, no guard weakened.
- Guest end-to-end leg (T2): the alert word is GUEST-computed and ST'd
  inside the agent tile; T8 proves an out-of-tile ST is reaped
  EXIT_FAULT and harvests nothing (the fence is the containment).
- NO rate/latency claims (rule-1 floors do not attach). NOT proven:
  no GPU/WGSL exec (CPU oracle, N1 pins glyph_isa_v2.py md5
  5a672d7d5a94a7b20f927f554b8a90c0); "asynchronous" = commit-between-
  runs, no mid-run preemption; toasts are solid color words (no
  text/fonts on the plane).
- Queue: item-40 -> landed. Next tick: item-41 (dynamic process
  lifecycle & spatial task manager, claim_order 41, blocks_on item-38
  + item-39 — both landed) per Phase-1b, unless a newer RULING
  intervenes.

### 2026-09-26 ~21:4x CDT — CLAIM QUEUE item 39 (virtual terminal & PTY line discipline) LANDED; 10-leg gate GREEN, both RED legs discriminating (builder af3e62239ce2)

- Provenance at claim: HEAD e9303ed2 (item-38 compositor commit),
  tracked-dirty = 0; mailbox rule clean (newest RULING_* mtime epoch
  1790127513 < HEAD epoch 1790473744). Watchdog supplied only a title;
  brief authored by this builder per the skeleton-handoff contract
  (BRIEF_item39_vt.md) BEFORE implementation.
- LANDED: tools/glyph_vt.py — VT100Screen (escape parser: CUP/CUU/CUD/
  CUF/CUB/ED/EL, deferred VT100 wrap, scroll-on-bottom-LF, clamped
  cursor), GlyphVT (line discipline over the LANDED GO-3 input ring
  tools/glyph_isa_v2.py:120-140: canonical line assembly, multibyte-safe
  0x7f char erase, ring seeding pre-run with loud over-cap +
  post-consumption refusals, ONLCR output processing), VTDisplay
  (VGA-font band render + glyph-side exact-match decode). Pure
  consumer — NO new syscall number, no engine change (N1 md5 guard
  pins glyph_isa_v2.py to HEAD inside the gate), no landed-layer edits.
- Gate: tests/test_item39_vt.py, 10 legs V1..V8 + N1 + N2. Tails pasted
  literally in RECEIPT_item39_vt.md: RED 1 (CUP params swapped)
  output/item39_red1.txt — "2 failed, 8 passed"; RED 2 (commit double-
  echo — a defect the module genuinely had during dev)
  output/item39_red2.txt — "3 failed, 7 passed"; GREEN
  output/item39_green_final.txt — "10 passed in 0.09s", EXIT=0.
  Mutations reverted before GREEN (diff-confirmed clean). Item-38 gate
  re-run on this tree as adjacent regression: 8 passed.
- Guest end-to-end leg (V7, probe output/item39_probe_echo.py): seeded
  guest reads its line with SYSCALL 0x02, echoes with 0x01, VT100
  screen shows it, and font-bitmap decode of the rendered band
  recovers the exact string — not a host echo.
- Six pre-GREEN defects found and fixed in-scope (int-vs-str control
  constants; unclamped CSI cursor; eager wrap; byte-wise backspace;
  commit double-echo; pending_bytes double-count) — itemized in the
  receipt; RED 2 exists because the double-echo was real.
- NO rate/latency claims (rule-1 floors do not attach). NOT proven: no
  GPU/WGSL exec; "PTY" = GO-3 ring line discipline, not a POSIX pty;
  no signals/mid-run input (cooperative run-to-completion).
- Queue: item-39 -> landed. Next tick: item-40 (desktop notification
  daemon & system tray ABI, claim_order 40) per Phase-1b, unless a
  newer RULING intervenes.

### 2026-09-26 ~21:0x CDT — CLAIM QUEUE item 38 (spatial window compositing & z-order elevation) LANDED; 8-leg gate GREEN, both RED legs discriminating (builder af3e62239ce2)

- Provenance at claim: HEAD e23fdc7e (watchdog supply replenish, items
  38-41), tracked-dirty = 0; mailbox rule clean (newest RULING_* mtime
  epoch 1790127513 < HEAD epoch). The watchdog supplied only a title;
  the brief was authored by this builder per the skeleton-handoff
  contract (BRIEF_item38_compositor.md: scope, gate command, gate
  clause, RED-first failure evidence, LOCKED interfaces) BEFORE the
  module was written.
- Design decision (live-guard preservation): GlyphStratum.open_window
  REFUSES overlapping placement (tools/glyph_stratum.py:126) — that
  guard is NOT weakened and the module adds no override. item-38 landed
  as a sibling module, tools/glyph_compositor.py (GlyphCompositor):
  overlap-permitted placement with per-window fences intact
  (spawn(tile=...), item-29 arm), arrival-order z, raise_window
  elevation, move() drag of reaped windows (landed fence never
  re-armed; refuses running windows + out-of-plane origins loud),
  damage-clipped composite (descending-z claims its region first,
  occupancy mask clips lower windows), hit_test top-window focus.
- Measured prerequisite (output/item38_probe_selftile.py): a USER-mode
  fenced guest can LD its own TILE_ROW/TILE_COL out of the MMIO block
  and compute+paint its origin ("exit: 0", "word 324: 0xff00"). Leg C7
  is real guest-computed paint. Probe cost: LD is register-indirect
  only (LDI-into-r20 then LD r10 r20 works; LD r10 <imm> OverflowErrors
  at glyph_isa_v2.py:547).
- Gate: tests/test_item38_compositor.py, 8 legs C1..C8. Tails pasted
  literally: RED 1 (sort flipped) output/item38_red1.txt — "2 failed,
  6 passed" (C2, C3); RED 2 (clip suppressed) output/item38_red2.txt —
  "2 failed, 6 passed" (C2, C3); GREEN output/item38_green_final.txt —
  "**8 passed in 0.07s**", EXIT=0. Mutations reverted before GREEN.
- Mechanism-honesty receipt note: an earlier ascending-z+mask shape had
  a DECORATIVE clip (RED 2 could not fail against it — overwrite order
  alone produced correct pixels). Restructured to descending-z-claims-
  first BEFORE the trusted RED/GREEN pair; superseded runs preserved
  (output/item38_green_pre*.txt, untrusted). Also recorded: move() is
  word-anchored — a moved window composites its RAM at the NEW grid
  addresses, so unrepainted cells go black (C4 asserts this openly; a
  candidate refinement, not hidden).
- LANDED commit: tools/glyph_compositor.py + tests/test_item38_compositor.py
  + BRIEF/RECEIPT + ledger/queue updates. Engine byte-guard: md5
  glyph_isa_v2.py = 5a672d7d5a94a7b20f927f554b8a90c0 == HEAD's blob.
  Tracked diff besides in-scope additions: none. No rates/latencies
  claimed (rule-1 floors do not attach). Receipt:
  .builder_queue/RECEIPT_item38_compositor.md.
- Queue: item-38 -> landed. Next tick: item-39 (claim_order 39) per
  Phase-1b, unless a newer RULING intervenes.

### 2026-09-26 ~20:4x CDT — CLAIM QUEUE item 37 (interactive multi-tile desktop application suite) LANDED; 10-leg gate GREEN (builder af3e62239ce2)

- Continuity: prior tick staged the brief + tools/glyph_desktop_suite.py +
  tests/test_item37_desktop_suite.py and was cut off before gating; it also
  left RED/GREEN output files whose GREEN (704s) was inconsistent with the
  file mtimes (suite module edited mid-"run" at 20:12:14; both tails written
  ~5s apart at 20:14:2x). RESUMED the staged tree, did NOT rewrite;
  re-ran BOTH legs fresh on the final tree. Superseded GREEN left on disk,
  untrusted (RECEIPT_item37_desktop_suite.md documents the check).
- Provenance re-verified at claim: HEAD 9eb57416 (item-36 ledger commit),
  tracked-dirty = exactly the 3 item-37 files; mailbox rule clean (newest
  RULING_* mtime 1790127513 < HEAD epoch 1790462088).
- LANDED (commit 3183e7f7 on glyph-transpiler-autoloop, gates run on this
  exact tree):
  - tools/glyph_desktop_suite.py — the composed desktop: ONE stratum
    carrying the item-33 status bar (locked rect (8,0,1,20)) plus THREE
    app tiles as pure consumers of the landed item-26..36 layers:
    terminal (guest XOR/OR/AND/SHR byte-loop decoder, the probe-verified
    af3e_probe_byteloop3 pattern), monitor (item-35 ReactiveRuntime fed
    by the item-34 wire; wire-word -> percept translate stays kernel-class
    HOST logic, item-36 pattern), explorer (guest lists an ext2 root via
    the LANDED 0x13 SYSCALL_FILE_LIST arm over an attached GlyphVfs —
    NO new syscall number; entry count = exit status; missing dir exits
    -1 RAW). Plus the item-33 launcher idiom (focus + BM905 press ->
    inbox count == exit status).
  - Gate: tests/test_item37_desktop_suite.py — 10 legs A1-A5 + C1/C2/C2B
    + N1/N2 (names normative per the brief; N2 = in-suite non-vacuity:
    zeroed wire slot -> ChannelError and B stays scan).
  - Gate tails (pasted literally):
    RED (output/item37_gate_af3e_red2.txt, driver
    output/item37_red_driver.py, this tree): "RED 1 (A2 mask corrupted
    0xFF->0x00): FAILED as required (gate discriminates)" / "RED 2 (A3
    commit suppressed): FAILED as required (gate discriminates)".
    GREEN (output/item37_gate_af3e_green2.txt): "**10 passed in 722.00s
    (0:12:01)**", EXIT=0 (full, incl. C2 item-33 + C2B item-36
    subprocess migration legs).
- Honesty: host-side Phase-2 composition over the CPU-oracle engine (N1
  pins glyph_isa_v2.py byte-identical to HEAD); no new syscall, no engine
  change, no edits to any consumed layer; guests still cannot sense or
  store across fences; explorer lists the vfs staging-union view, not an
  in-guest ext2 parser; delivery cooperative commit-between-runs. NO
  rate/latency claims (rule-1 floors do not attach).
- Receipt: .builder_queue/RECEIPT_item37_desktop_suite.md
- Queue: QUEUE_STATE.json item-37 -> landed (3183e7f7). The structured
  CLAIM QUEUE is now EMPTY (items 19..37 all landed). Next tick: PHASE 1c
  research ticket per the standing directive (one RESEARCH_<slug>.md max,
  rule-1 number discipline, backlog row BK-15+, never lands engine code),
  unless a new CLAIM QUEUE section or binding RULING appears first.

### 2026-09-26 ~17:3x CDT — CLAIM QUEUE item 36 (adversarial cross-fence multi-agent reactivity gate) LANDED; 11-leg gate GREEN (builder af3e62239ce2)

- Provenance re-verified: HEAD 699ecae0 (item-35 ledger commit), tree
  clean of tracked modifications; mailbox rule clean (no RULING_* newer
  than HEAD's commit time at claim; re-checked at 17:34 before this
  ledger write). Monitor delta CLAIM_PENDING -> DIRTY_ACTIVE explained
  by this item's own staged files.
- Claimed item-36 per Phase-1b (lowest claim_order unblocked;
  blocks_on=[item-34, item-35] both landed).
- LANDED (commit 9e3a87b0 on glyph-transpiler-autoloop, gates run on
  this exact tree):
  - tests/test_item36_cross_fence.py — 11 legs X1-X9 + N1-N2. Two
    fenced ReactiveRuntime agents (item-35) share ONE GlyphStratum;
    agent A's guest-computed transition crosses to agent B ONLY via
    the item-34 GlyphChannel wire (BM905, seq/CRC/ack); B's
    environment translates the RECEIVED word into B's percept row
    (kernel-class, item-32/35 precedent); B's guest then resolves a
    DIFFERENT transition than an isolated control on the same tree.
    X1 topology/fence preconditions; X2 isolation baseline (no
    ambient coupling through a shared plane); X3 the core cross-fence
    reaction vs an isolated control; X4 commit-suppressed -> no
    reaction (the wire is the only path); X5 three-agent cascade
    A->B->C two hops, seq-ordered, payloads = upstream agents' OWN
    action words; X6 one flipped bit -> poll() raises ChannelError,
    reaction does not fire; X7 forged out-of-range code (7) delivered
    intact by the content-agnostic wire but quarantined LOUD
    (ValueError) at the environment; X8 rogue guest ordered to ST at
    the peer's act slot reaped EXIT_FAULT, peer act word untouched
    (S5/N3 discipline re-proven on this topology); X9 migration:
    item-35 gate GREEN via subprocess; N1 engine-byte guard; N2 wrong
    translation flips the resolution.
  - Gate tails (pasted literally):
    RED (output/item36_gate_af3e_red.txt, driver
    output/item36_red_driver.py): "RED1 (X3 expectation flipped):
    FAILED as required (gate discriminates)" / "RED2 (X6 corruption
    removed, clean wire): did NOT raise as required (raise is caused
    by the corruption)".
    GREEN (output/item36_gate_af3e_green.txt): "11 passed in 428.98s
    (0:07:08)" (full, incl. X9 subprocess migration leg).
- Honesty: host-side Phase-2 composition over the CPU-oracle engine
  (N1 pins glyph_isa_v2.py byte-identical to HEAD); no new syscall,
  no engine change, no new wire format. NOT proven: no GPU/WGSL
  execution; the wire->percept translation is kernel-class HOST logic
  — guests still cannot sense across a fence (private RAM copies) nor
  store across one (X8); delivery is cooperative commit-between-runs;
  the adversary covered is a corrupted/forged WIRE plus out-of-range
  payload — a malicious GUEST is answered only by the fence itself
  (X8), not by this gate. No rate/latency claims (rule-1 floors do
  not attach).
- Incidental infra fix (outside the repo): /tmp on the root fs hit
  100% (ENOSPC) and broke item-32/33 migration legs with
  "[Errno 28] No space left on device" during precheck; ~4,400 stale
  jericho-owned glyph_shell_*/item11_*/defect23_* scratch dirs plus
  ~4,930 >14-day-old temp files purged (root fs 99% -> 97%) to
  unblock the gate. The earlier FALSE-RED precheck failures
  (test_s1_bar_is_a_window OSError 28, and the cascade through
  r7/c7/c8) were this disk exhaustion, not code regressions; all
  three suites re-ran clean afterwards (item-33 10/10 285.57s,
  item-32 8/8 140.68s).
- Queue: QUEUE_STATE.json item-36 -> landed (9e3a87b0); item-37
  (interactive multi-tile desktop app suite, blocks_on item-33+36)
  is the next lowest claim_order and is now UNBLOCKED — next tick
  claims item-37.

### 2026-09-26 ~16:4x CDT — CLAIM QUEUE item 35 (reactive agent state machine runtime, GlyphReactive) LANDED; 10-leg gate GREEN (builder af3e62239ce2)

- Continuity: again a staged tree from a cut-off prior tick
  (tests/test_item35_reactive.py + tools/glyph_reactive.py, exactly 2
  files). RESUMED, did not rewrite. Provenance re-verified: HEAD
  e5f076d4; QUEUE_STATE item-35 blocks_on=[item-34] landed ad9edcf9;
  mailbox rule clean (newest RULING mtime 1790127513 < HEAD epoch
  1790449823). Monitor delta CLAIM_PENDING -> DIRTY_ACTIVE explained by
  the staged files.
- LANDED (commit 86be9194 on main, gates run on this exact tree):
  - tools/glyph_reactive.py — ReactiveRuntime: guest reactive agent
    with a read-evaluate-act-paint loop. Contract row = 6 words at
    channel-wire offsets 35..40 (no wire overlap; 3-row tiles).
    Evaluate is fully guest-computed (event dominance, p0 jump
    dispatch, state-dependent re-arm); Act = real guest ST to the act
    slot; each tick commits the action word over the item-34
    GlyphChannel (seq/CRC/ack) and appends the transitions ledger.
  - Gate: tests/test_item35_reactive.py, 10 legs R1-R7 + N1-N3.
    RED 1 (output/item35_gate_af3e_full.txt): 5F/5P 418.12s — two
    staged-FSM defects the gate caught: (1) :commit stay-marker block
    INVERTED (stored -1 exactly when computed==current; CMP sets r0 on
    equality, JNZ jumps clear) — fixed by comparing r18 to the marker
    and resolving stay by reloading the current state from the act
    slot pre-store; (2) :k0 hardcoded NONE->scan, breaking
    approach+quiet->stay (R6) — fixed state-dependent k0.
    RED 2 (output/item35_gate_af3e_green.txt): 1F/9P 417.63s — R5
    composite assert unpacked RGB opposite to the LOCKED item-31
    encoding (glyph_stratum.py:251 = (R<<16)|(G<<8)|B); fixed the
    GATE's unpack (implementation matched the landed ABI; not a guard
    weakening). GREEN (output/item35_gate_af3e_green2.txt):
    **10 passed in 415.54s** (full, incl. R7 subprocess migration leg).
- Honesty: host-side Phase-2 artifact over the CPU-oracle engine (N1
  pins glyph_isa_v2.py byte-identical to HEAD); no new syscall, no
  engine change; perception = contract-row read, NOT composite
  readback (cross-window SENSE structurally impossible, private RAM);
  cooperative seed-then-run, fresh agent task per tick; FSM fixed at
  assemble time; NO rate/latency claims (rule-1 floors do not attach).
- Receipt: .builder_queue/RECEIPT_item35_reactive.md
- Queue: QUEUE_STATE.json item-35 -> landed; item-36 (adversarial
  cross-fence multi-agent reactivity gate, blocks_on item-34+35) is
  the next lowest claim_order and is now UNBLOCKED — next tick claims
  item-36.

### 2026-09-26 ~14:1x CDT — CLAIM QUEUE item 34 (inter-tile IPC & ordered messaging, GlyphChannel) LANDED; 12-leg gate GREEN (builder af3e62239ce2)

- Continuity: a prior tick authored tools/glyph_channel.py +
  tests/test_item34_channel.py (both staged, uncommitted) and was cut
  off before gating. This tick RESUMED the staged tree, did NOT
  rewrite. Provenance re-verified: HEAD 4c25e982 (watchdog commit on
  the item-33 lineage); staged tree carried exactly the 2 item-34
  files; monitor delta CLAIM_PENDING -> DIRTY_ACTIVE (tracked_dirty=2)
  explained by those staged files. Mailbox rule: no RULING_* newer
  than HEAD (newest RULING mtime Sep 22 < HEAD epoch 1790442912).
  Claimed item-34 per Phase-1b (lowest claim_order unblocked;
  blocks_on=[item-33] landed c58cb322).
- LANDED (commit ad9edcf9 on main, gates run on this exact tree):
  - tools/glyph_channel.py NEW — GlyphChannel: ordered message
    channel between two fenced item-31 window tiles. Wire: word0
    seq_next, word1 ack, word2 count, words 3..34 = 8 slots x 4 u32
    (BM905 16-byte packets, slot = seq % 8). Reuses the item-32 wire
    codec byte-for-byte (vendored import pins it to rung9 through
    item-32's DRIFT leg); adds TYPE_DATA=5. send/commit_outbox (host
    API), commit_guest_ring (validates raw guest-produced rings and
    re-packages them as canonical CRC'd packets, kernel-class;
    target_pid selects the consuming TASK), poll (strict in-order;
    CRC+magic verified; overwrite/gap/backwards seq are LOUD
    ChannelError — never a silent skip), resync, wait_ack (bounded
    spin), receiver_snapshot.
  - Gate: tests/test_item34_channel.py, 12 legs C1-C6b + C7/C8
    (migration) + N1-N3. RED first (output/item34_gate_red_pre_fix.txt,
    pre-fix run): C6 FAILED 1/12 in 411.74s — the gate call omitted
    target_pid so the committed wire landed in the receiver WINDOW's
    task RAM, which no guest reads; the receiver guest spun to its
    instruction bound and exited 0 with r9=0 (a real wiring defect the
    gate caught, then failed honestly). Fix: target_pid=pr + two
    asserts corrected to the actual wire layout (word2 =
    value<<16 | code; the task-targeted leg's host poll() is None —
    the host poll path is separately proven in C2-C5). GREEN:
    **12 passed in 421.57s** (full, incl. subprocess migration legs);
    fast lane 10 passed / 2 deselected in 0.08s.
  - ENGINE GUARD: tools/glyph_isa_v2.py sha256
    180df56e5c59cdfe0f94793a7e80c54b4870cf9289ccd2905d2683922c9ba775,
    byte-identical to HEAD 4c25e982 (N1 leg + re-measured at landing).
    Zero new syscalls; no engine change; guests see only RAM words
    they already LD/ST.
- Honesty / NOT proven: no GPU/WGSL execution (CPU-oracle engine);
  no live mid-run delivery between two RUNNING tasks (commit happens
  between runs — the cooperative item-26 model); seq/ack/count
  bookkeeping words are host-written at commit, not guest-computed;
  no multicast / >2 endpoints / flow control beyond the ack word; no
  rates or latencies asserted (rule-1 floors do not attach).
- Queue: QUEUE_STATE.json item-34 -> landed; item-35 (reactive agent
  state machine runtime, blocks_on=[item-34]) now UNBLOCKED — next
  tick claims item-35.

### 2026-09-26 ~12:1x CDT — CLAIM QUEUE item 33 (desktop shell UI & process task launcher, GlyphShell) LANDED; guest-painted bar/gauge/launcher proven (builder af3e62239ce2)

- Continuity: prior tick (~11:2x-11:5x) authored tools/glyph_shell.py +
  tests/test_item33_shell.py and captured RED (output/item33_gate_run1.txt,
  .FFF.FF. = 4 failed / 10) then GREEN (output/item33_gate_green_run1.txt,
  10 passed in 276.82s) but was CUT OFF before ledger/commit. This tick
  resumed the staged tree — did NOT rewrite. Provenance re-verified: HEAD
  adf406ac (my item-32 ledger commit); staged tree carried exactly the 4
  item-33 files; monitor delta CLAIM_PENDING -> DIRTY_ACTIVE
  (tracked_dirty=4) explained by those staged files. No RULING newer than
  HEAD. Own independent re-gate on the staged tree: 10 passed in 300.38s,
  rc=0 (2026-09-26 ~12:0x).
- What landed: tools/glyph_shell.py (GlyphShell — host-side shell
  composing items 26-32: open_bar status bar, storage_gauge via
  `debugfs -R stats` over the png_vfs-unwrapped root (e2progs-only
  discipline), install_app/launch via item-30 store_program + item-32
  BM905 key packet into the new window's inbox pre-run, tasks()
  cooperative monitor). Every visible pixel is painted by a GUEST task
  through fenced STs inside its own tile; panels are ordinary item-31
  windows; the shell never paints a window's cells host-side.
- Gate: tests/test_item33_shell.py 10 legs (S1 bar-as-window + one-bar
  refusal, S2 guest-side gauge painting + fill-fraction legs counted
  from the composite, S3 gauge metadata contract total==1024 and
  painted-count strictly increases on writes, S4 launcher
  install/launch, S5 cross-fence ST reaped EXIT_FAULT, S6 task table,
  R1/R2 migration legs re-run item-31/item-32 gates GREEN in-tree,
  N1 engine-byte guard glyph_isa_v2.py sha256-identical to HEAD, N2
  non-vacuity). GREEN 10/10 own run; RED-first on file (pre-fix run).
- Honesty / NOT proven: no GPU/WGSL execution (CPU-oracle engine,
  Phase-2 doctrine); no live bar refresh while tasks RUN (cooperative
  item-26 seed-then-run); no fonts/text on the plane (solid cells;
  gauge NUMBERS live in the inbox row, not on pixels); no drag/resize
  (placement containment); gauge = host debugfs metadata read, not a
  guest-executed query; no rates asserted (rule-1 floors do not attach).
- Queue state: QUEUE_STATE.json item-33 -> landed. CLAIM QUEUE
  items 19-33 now ALL landed; no further queued claim items — next tick
  per Phase 1c: research tick if no new CLAIM QUEUE item / RULING
  appears, else take the queue.


- Continuity: previous tick (10:4x-10:5x) was CUT OFF after authoring but
  before gate/commit — this tick resumed the staged tree, did NOT rewrite.
  Provenance re-verified: HEAD 9d821afb (item-31 lineage), tracked tree
  carried exactly the 5 staged item-32 files, monitor delta
  CLAIM_PENDING -> DIRTY_ACTIVE explained by those staged files. Mailbox
  rule: no RULING_* newer than HEAD (newest mtime 1790127513 < HEAD time
  1790436541). Claimed item-32 per Phase-1b (lowest claim_order unblocked;
  blocks_on=[item-31] landed 83a1fceb).
- LANDED (commit 309b894f on main, gates run on this exact tree):
  - tools/glyph_input.py NEW — GlyphInputRouter over item-31's
    GlyphStratum: BM905 LOCKED 16-byte packet slots (magic 0x0DB5 |
    seq | type | code | value | crc16-ARC) vendored byte-identical from
    tools/bare_metal_poc/rung9/bm905_mailbox_packet.py (gate carries a
    DRIFT leg importing the rung9 codec and asserting byte-equality),
    ONE added type TYPE_MOVE=4 (code=col, value=row). Delivery target =
    focused window's tile top row: word0 count, words 1..4 packet u32s.
    Explicit pin OR hit_test(cursor) auto-focus; MOVE over the bare
    plane dropped+counted; directed events to no-target raise
    RouterError LOUD; undersized inbox refuses delivery (no partial
    write); close/pin-to-closed resolves loud, never writes dead RAM.
  - Gate: tests/test_item32_input.py (force-added past .gitignore),
    8 legs I1-I6+R1+N1. RED-first (run0, module absent):
    ModuleNotFoundError: tools.glyph_input, 1 collection error in 0.19s
    RC=2 (output/item32_gate_run0_absent_red.txt). GREEN:
    **8 passed in 140.90s** on the committed tree, exit 0. R1 migration
    leg re-runs item-31's stratum gate GREEN via subprocess in-tree.
  - Non-vacuity (output/dbg_item32_nonvacuity.py, rc=0,
    output/item32_nonvacuity_run1.txt): N1 hit_test neutered -> RED;
    N2 capacity guard neutered -> RED; N3 codec wordswapped -> RED;
    restored source GREEN (7 passed, 1 deselected). Gate discriminating.
  - ENGINE GUARD (N1 leg + re-measured at landing):
    tools/glyph_isa_v2.py sha256
    180df56e5c59cdfe0f94793a7e80c54b4870cf9289ccd2905d2683922c9ba775,
    byte-identical to HEAD 9d821afb. Zero new syscall numbers; no engine
    change; guest-visible ABI = RAM words a task already LDs.
- Honesty (rule 6): all asserts structural — packet bytes, RAM words,
  counts, exceptions; no rates/latencies, rule-1 floors do not attach,
  check_regime not implicated. NOT verified: no GPU/WGSL execution;
  no live mid-run delivery to a RUNNING task (cooperative item-26 model
  — pre-run delivery is the proven path); no host /dev/input capture
  (router consumes already-formatted events); mouse buttons encoded as
  key packets (no separate button type).
- Queue: QUEUE_STATE.json item-32 -> landed; item-33 (desktop shell UI,
  blocks_on=[item-31,item-32]) now UNBLOCKED — next tick claims item-33.
  Tracked tree CLEAN post-commit (receipt/ledger files staged next tick
  per one-step-one-commit; this ledger + QUEUE_STATE land with the next
  receipt commit or immediately if the monitor flags DIRTY).

### 2026-09-26 ~10:2x CDT — CLAIM QUEUE item 31 (GPU-first spatial window coordinator, GlyphStratum) LANDED; fenced window planes + composite proven (builder af3e62239ce2)

- Provenance re-verified at tick start: HEAD bc435c29 (my item-28/29/30
  lineage); tracked tree CLEAN; monitor delta: supply flip item-30 ->
  item-31 (watchdog auto-replenish 309295d9, expected); QUEUE_STATE
  item-31 unblocked (blocks_on=[item-29,item-30] both landed); no
  RULING newer than HEAD (newest RULING mtime 1790127513 < HEAD time
  1790433063). Claimed per Phase-1b (lowest claim_order unblocked).
- LANDED (commit f69cb328 in worktree ~/zion/worktrees/item31-coordinator,
  cherry-picked to main as 83a1fceb after gates passed):
  - tools/glyph_stratum.py NEW — GlyphStratum: window coordinator over
    the W_MEM=32 word-grid plane, composing the landed item-26 process
    table + item-29 tile fence + item-30 loader. open_window /
    open_window_from_disk: claim a rect, refuse overlap LOUD (placement
    containment), refuse any rect overlapping the isolation MMIO block
    rows [256,264) — a window there could rewrite its own fence words
    (TILE_* live at BOX_MMIO_BASE+0x160..0x16C) — then spawn the task
    FENCED to its own rect (item-29 tile=, unchanged). WCB rows carry
    the geos_pixel_v5 wcb.rs field vocabulary (STATE/X/Y/W/H/Z/VISIBLE)
    in word-grid coords. composite(): the plane rendered from task RAM
    words (word & 0xFFFFFF = RGB), ascending z, black background. Plus
    hit_test/raise_window/set_visible/run_all/output/close.
  - Design finding — placement containment makes the plane DISJOINT by
    construction: open rects can never overlap, so hit-test is rect
    lookup (contested cells arise only across hide/close state changes,
    never between simultaneously-open windows). Cross-window paint is
    impossible BY THE FENCE: W5's attempt is trapped by the engine's
    E-K1 path (faulted, store never lands, EXIT_FAULT reaped), with the
    innocent neighbor's composite intact.
  - Gate: tests/test_item31_stratum.py (force-added past .gitignore)
    — 10 legs. GREEN 10 passed in 142.25s (worktree f69cb328); main
    re-gate at 83a1fceb: **28 passed in 284.22s** (= item31 10 +
    item29 10 + item30 8), exit 0. RED-first: module absent ->
    ModuleNotFoundError: tools.glyph_stratum, 1 collection error in
    0.09s (output/item31_gate_run0_absent_red.txt). Mid-fix REDs,
    disclosed — all three were GATE bugs, the implementation refused
    correctly each time: (1) W4 asserted every rect cell colored but
    the painter stores ONE word (fixed: painted cell + rest black);
    (2) W6 opened an overlapping window and the coordinator correctly
    refused (that IS W2's contract; fixed: disjoint rects, hit-test
    semantics restated under placement containment); (3) W7's blue
    painter targeted a word outside its own tile and the fence
    correctly reaped it EXIT_FAULT (fixed: each painter targets its
    OWN first tile word).
  - Non-vacuity (output/dbg_item31_nonvacuity_af3e.py, rc=0,
    output/item31_nonvacuity_run3.txt): N1 overlap refusal neutered
    (`if False and ...`) -> W2 RED (DID NOT RAISE StratumError);
    N2 MMIO refusal neutered -> W3 RED; N3 tile= pass-through dropped
    (tile=None) -> W5 RED (cross-window store would land); restored
    source green again. Probe run2 hit a probe-harness restore race
    (its own assert string compared against a stale rc) — run3 clean
    PASS; source verified byte-identical after restore.
  - ZERO new syscall numbers; engine byte-unchanged (N1 leg pins
    tools/glyph_isa_v2.py sha256-identical to HEAD).
- Honesty (rule 6): all asserts structural — no rates/latencies, rule-1
  floors do not attach; check_regime not implicated. NOT verified: no
  WGSL/GPU execution (host CPU engine, Phase-2 doctrine — same boundary
  as items 26-30; "GPU-first" names the architecture target, the landed
  artifact is the coordinator CONTRACT over the CPU oracle); no live
  compositing of RUNNING tasks (cooperative run-then-compose, item-26
  shape); no input routing (item-32's lane); no shell UI (item-33's
  lane); "infinite plane" is the sparse coordinate model bounded by
  memory_words (the engine contract), not unbounded RAM; hit-test
  z-ordering between simultaneously-open windows is unreachable under
  placement containment (asserted as rect lookup instead).
- Queue state: QUEUE_STATE.json item-31 -> landed, item-32 unblocked
  (blocks_on=[item-31] cleared); CURRENT_TICKET.json reconciled.
  Next tick: claim item-32 (spatial input router & focus manager:
  BM905 event dispatch into focused active tile). REPAIR_PENDING_BK27_L5
  unchanged (holds; sign-off change).

### 2026-09-26 ~10:2x CDT (earlier tick) — CLAIM QUEUE item 30 (ext2 spatial executable binary loader) LANDED; digest-contained exec chain proven (builder af3e62239ce2)

- Provenance re-verified at tick start: HEAD 309295d9 (my item-28/29
  lineage); tracked tree CLEAN; monitor baseline first-run: CLAIM_PENDING
  queue=0 supply=claim item-30; QUEUE_STATE item-30 unblocked
  (blocks_on=[item-29] cleared); no RULING newer than HEAD (newest
  RULING mtime 1790127513 < HEAD time 1790430870). Claimed per
  Phase-1b (lowest claim_order unblocked).
- LANDED (commit 1d64191d in worktree ~/zion/worktrees/item30-loader,
  cherry-picked to main as dbf266d2 after gates passed):
  - tools/glyph_loader.py NEW — the exec chain: store_program (image +
    SHA-256 sidecar .sha256 digest), load_program (recover through the
    VFS 0x04 path -> digest verify -> reshape to the engine geometry
    cols_instrs*INSTR_WIDTH -> item-26 spawn; item-29 tile= passes
    through), exec_program (exec on a BOOTED kernel = a NEW spawn on
    the existing table — never displaces PID 1, exec'd task takes the
    NEXT pid >= 2 — sharing the kernel's mounted root VFS, the
    item-27 shared-VFS contract).
  - Integrity model: exec format = raw program image + sidecar digest;
    the loader NEVER parses glyph opcodes (the engine remains the only
    decoder — the item-24 discipline).
  - Gate: tests/test_item30_loader.py (force-added past .gitignore)
    — 8 legs. GREEN 8 passed in 105.21s (worktree 1d64191d) and
    47 passed in 277.24s (main dbf266d2, = item30 + item28 + item29 +
    item26 + item25 + png_vfs re-gates), exit 0. RED-first: module
    absent -> ModuleNotFoundError: tools.glyph_loader, 1 error in
    0.08s (output/item30_gate_run0_absent_red.txt). Mid-fix REDs,
    disclosed: (1) gate legs wrote programs via raw vfs_write but the
    loader requires the digest sidecar — gate moved to the
    store_program contract (tightened, not weakened); (2) loader
    reshape cols_instrs*2 was wrong geometry — B2's image-equality
    assert caught it ((2,16,3) != (1,32,3)) and refused to pass a
    wrong loader; fix = cols_instrs*INSTR_WIDTH (4 px/instr).
  - Non-vacuity (output/dbg_item30_nonvacuity_af3e.py, rc=0): N1
    digest guard neutered AT SOURCE (if got != want -> if False and
    ...) -> corrupt payload REACHES SPAWN (no LoaderError), restored
    source refuses again — the GUARD, not the engine, is the
    load-time containment (neutered payload still ran clean: engine
    does not self-detect flipped pixels); N2 tile pass-through
    dropped -> out-of-tile store LANDS 0x0BADC0DE status 0 (the
    fence is the loader's responsibility to arm); N3 x2 reshape ->
    image equality fails (geometry load-bearing).
  - ZERO new syscall numbers; engine byte-unchanged (N1 leg pins
    tools/glyph_isa_v2.py sha256-identical to HEAD).
- Honesty (rule 6): all asserts structural — no rates/latencies, rule-1
  floors do not attach; check_regime not implicated. NOT verified: no
  WGSL twin parity (host-side exec, no guest-visible ABI — TICKET_ITEM8
  false-success class structurally avoided); no ELF-style header
  format (raw image + sidecar only; a header'd container is future
  work); no transpiler-leg execution — BK-33/34/35 cite this item for
  FIXTURE TRANSPORT only; those transpiler aliasing defects remain
  open; no spawn-arg passing (argv/env), no PID-1 re-exec (replacement
  semantics), no shared-memory exec.
- Queue state: QUEUE_STATE.json item-30 -> landed, item-31 unblocked
  (blocks_on=[item-29,item-30] cleared); CURRENT_TICKET.json
  reconciled. Next tick: claim item-31 (GPU-first spatial window
  coordinator: GlyphStratum multi-tile manager on infinite canvas).
  REPAIR_PENDING_BK27_L5 unchanged (holds; sign-off change).

### 2026-09-26 ~07:4x CDT — CLAIM QUEUE item 28 (spatial root init: ext2 PNG root mount + PID 1 startup) LANDED; DEFECT-32 found + fixed (builder af3e62239ce2)

- Provenance re-verified at tick start: HEAD fba4494d (my item-27
  ledger lineage); tracked tree CLEAN; monitor CLAIM_PENDING queue=0
  supply=claim item-28; QUEUE_STATE active=null, item-28 unblocked
  (blocks_on=[item-27] cleared); no RULING newer than HEAD. Claimed
  per Phase-1b (lowest claim_order unblocked).
- ADOPTED an abandoned partial patch in the item28 worktree (uncommitted
  edit at 06:36, no live process, no lane record): it referenced an
  _image_dir_exists helper that was never written — completed it as the
  DEFECT-32 fix below, after measuring the mechanism myself.
- DEFECT-32 (new, measured this tick, evidence chain in
  RECEIPT_item28_root_init.md): `debugfs -w -R mkdir` on an EXISTING
  directory allocates + links a fresh dir inode and only THEN errors
  "already exists" (rc 0) — e2fsck -fn rc=4 "Unconnected directory
  inode" (5/5 shell trials). The landed unconditional mkdir-per-segment
  in GlyphVfs.sync() broke the reboot-write-reboot cycle through any
  existing subdirectory: /etc/motd resync measured sync rc=-1 with the
  write LOST (probe dbg red v15). Item-25's gate missed it (L1 fresh
  disk, L3 root-level files — no existing-subdir mkdir). Note: a
  redundant mkdir followed by a successful write "settles" the orphan,
  which is why naive sync-level probes look clean; the fail case needs
  an existing file (rm+write) in an existing dir. Fix: stat-probe
  segments, mkdir only missing. Pinned by gate leg B4.
- LANDED (commit 21201b56 in worktree ~/zion/worktrees/item28-rootinit,
  cherry-picked to main as a220b26b after gates passed):
  - tools/glyph_root_init.py NEW — GlyphRootFs.format (ext2 1MiB root
    in the VFS-1 PNG transport, seeded /etc/hostname + /sbin/init +
    /var/run/utmp), GlyphRootFs.mount (loud RootInitError on init-less
    roots), Kernel.boot (PID-1-FIRST contract: first table spawn must
    be pid 1, reused Kernel refuses; init program SYSCALL 0x03-writes
    its argv boot record through the mounted root then 0x05 EXIT 0),
    shutdown_sync (VFS-3 persist), boot() one-liner.
  - Gate: tests/test_item28_root_init.py (force-added past .gitignore)
    — 8 legs. GREEN 8 passed in 67.78s (worktree 21201b56) and 40
    passed in 142.29s (main a220b26b, incl. item25+item26+png_vfs+
    box_abi re-gates), exit 0. RED-first: gate file absent -> pytest
    exit 4 (output/item28_gate_run0_absent_red.txt). Mid-fix RED,
    disclosed: P1 DID NOT RAISE (second boot allowed on same Kernel ->
    init pid would not be 1); boot() now refuses — enforcement added,
    no guard weakened. Non-vacuity (dbg_item28_nonvacuity_af3e.py,
    rc=0): N1 guard removed -> B4 fails; N2 mount-check removed -> R1
    fails. Gate proven able to fail at the implementation level.
  - ZERO new syscall numbers; engine byte-unchanged (TICKET_ITEM8
    twin false-success class structurally avoided).
- Honesty (rule 6): all asserts structural — no rates/latencies, rule-1
  floors do not attach; check_regime not implicated. NOT verified: no
  WGSL twin parity (host-side boot, shader-threat-model precedent per
  item-27); no GPU-image execution (Phase-2 doctrine); no multi-user
  init (single PID 1, no runlevels/respawn; utmp placeholder); init
  program assembled host-side — a guest-loaded binary init is NOT
  claimed; DEFECT-32's write-fails-after-redundant-mkdir corner argued
  from the landed pre-wrap e2fsck refusal, not probed.
- Queue state: QUEUE_STATE.json item-28 -> landed, item-29 unblocked;
  CURRENT_TICKET.json reconciled. Next tick: claim item-29
  (per-process spatial containment: bind GO-1 box enforcement to
  spawn-allocated tiles). REPAIR_PENDING_BK27_L5 unchanged (holds;
  sign-off change).


### 2026-09-26 ~07:1x CDT — CLAIM QUEUE item 27 (driver ABI freeze: unified Mailbox/Console/Block contract) LANDED (builder af3e62239ce2)

- Provenance re-verified at tick start: HEAD 16c285fe (my item-26
  ledger lineage); tracked tree CLEAN; monitor CLAIM_PENDING queue=0
  supply=claim item-27; QUEUE_STATE active=null, item-27 unblocked;
  no RULING newer than HEAD (only DOGFOOD_GPU_OS_* refreshed, 7/7
  healthy 05:50). Claimed per Phase-1b claim-queue-first (lowest
  claim_order unblocked).
- LANDED (commit 91ce8e78 in worktree ~/zion/worktrees/item27-driverabi,
  cherry-picked to main as ba9a302a after gates passed):
  - docs/DRIVER_ABI_v1.md NEW — the unified channel freeze: MAILBOX
    (BOX_ABI_v2 s4 verbatim: GH-22 word format, canonical check vector
    0x3B00112A, frozen receipts 0x5EED0003/4/5 + 0xFA026 + 0xCAFE0026 +
    ABI 0x00020026); CONSOLE (DTF-2 glass-TTY: 8x16 VGA cell, band
    rows*16 x cols*8, strictly two colors, strict decode raises on a
    third, text->pixels->text byte-exact); BLOCK (VFS-1: 28B header
    b"PVFSIMG1" / "<8sHHII8s" / RGB24 3B/px / Hilbert d2xy transport,
    loud PngVfsError on corrupt magic/version/short payload). Change
    policy inherited verbatim from BOX_ABI_v2 (frozen field change =>
    major bump + migration note; the gate enforces).
  - Gate: tests/test_item27_driver_abi.py (force-added past
    .gitignore) — 10 legs. GREEN 10 passed in 0.22s (worktree
    91ce8e78) and 0.25s (main tree ba9a302a, post-cherry-pick re-gate).
    RED first: gate file absent -> pytest exit 4
    (output/item27_gate_run0_absent_red.txt). In-suite non-vacuity
    R1/R2/R3 (corrupt-expectation legs). Mid-fix REDs, disclosed:
    C1 trailing-space mismatch (decode_band rstrips lines — contract,
    not bug); B1 asserted disk == PNG bytes (wrong layer — disk is
    unwrap() output; header decoded via decode_payload of the PNG);
    B2 flipped disk byte 0 instead of the canvas header magic (the
    magic lives at Hilbert offset 0 = pixel (0,0) red channel;
    test_png_vfs.py leg-3b pattern).
  - U1 unification leg: ONE GlyphVfs, TWO spawned engines (item-26
    GlyphProcessTable vfs_shared=True) — task A 0x03-writes
    /t27.txt, task B 0x04-reads byte-exact through the staged
    overlay; no host-FS file (VFS-2 contract intact).
  - ZERO new syscall numbers — no guest-visible ABI added, so the
    WGSL twin bridge false-success class (TICKET_ITEM8) is
    structurally avoided; no engine file touched.
- Adjacent re-gate at the worktree: item-25 + item-26 + png_vfs +
  box_abi conformance = 32 passed in 73.09s (exit 0).
- Honesty (rule 6): all asserts structural — no rates/latencies, rule-1
  floors do not attach; check_regime not implicated. NOT verified: no
  WGSL twin parity (console render is host-side, block channel is host
  e2progs — out of the shader threat model per the 0x07/0x12/0x13
  normative-negative precedent); no rate/floor claim (nothing timed);
  no silicon device model (GH-22 trusted-unproven boundary stands); LD
  read-isolation unaffected (BOX_ABI_v2 s7).
- Disk note: worktree add initially failed ENOSPC (/home 100%); two
  fully-merged stale worktrees removed (defect17-x31, go6-virtio-l1 —
  both tips verified ancestors of HEAD before removal) -> /home 97%,
  then add succeeded.
- Queue state: QUEUE_STATE.json item-27 -> landed, item-28 unblocked
  (blocks_on=[item-27] cleared); CURRENT_TICKET.json reconciled. Next
  tick: claim item-28 (spatial root init: ext2 PNG root mount + PID 1
  startup) by claim_order among unblocked. REPAIR_PENDING_BK27_L5
  unchanged (holds; sign-off change).


### 2026-09-26 ~06:2x CDT — CLAIM QUEUE item 26 (spatial process model: spawn primitive + multi-task coordination) LANDED (builder af3e62239ce2)

- Provenance re-verified at tick start: HEAD 00c7aad6 (my item-25
  ledger lineage); tracked tree CLEAN; monitor CLAIM_PENDING queue=0
  supply=claim item-26; QUEUE_STATE active=null, item-26 unblocked
  (blocks_on=[item-25], landed 9c285fdf last tick). Claimed per
  Phase-1b claim-queue-first (lowest claim_order unblocked).
- LANDED (commit 208a87d4 in worktree ~/zion/worktrees/item26-proc,
  cherry-picked to main as f8767491 after gates passed):
  - tools/glyph_process.py NEW — GlyphProcessTable: spawn(image,
    vfs_shared=) -> pid; every task a FRESH GlyphCPUv2 (the SE021
    isolation delta, moved in-process); wait/wait_any/wait_all;
    exit-status contract = 0x05 EXIT r1 latched via an _on_exit hook
    subclass, clean HALT -> 0, faulted -> 1 (child-runner rc shape).
    BASE ENGINE BYTE-UNCHANGED (hook lives in the table's subclass;
    R1 leg proves the bare-engine path). ZERO new syscall numbers —
    no guest-visible ABI, so the WGSL twin bridge false-success class
    (TICKET_ITEM8) is structurally avoided.
  - Multi-task coordination through the item-25 landed VFS: ONE
    GlyphVfs attached to multiple task engines; P4 leg proves task A
    0x03-writes -> task B 0x04-reads byte-exact via the staged
    overlay, file absent from the host FS (VFS-2 contract intact).
- Gate: tests/test_item26_process.py — RED first (implementation
  stashed -> ModuleNotFoundError: No module named 'tools.glyph_process'
  at collection), then GREEN 8 passed in 33.11s (worktree 208a87d4)
  and 33.52s (main tree f8767491, post-cherry-pick re-gate). Legs:
  P1 spawn isolation (fresh engines, RAM+regfile separate); P2
  exit-status contract (EXIT 7 -> 7; clean HALT -> 0; opcode-None
  silent halt -> 0 per glyph_isa_v2.py:766-769); P2b genuinely
  faulted engine -> rc 1 (misaligned-PC SpatialMisalignmentFault);
  P3 wait_all 3 tasks, PRT streams byte-exact; P4 the shared-VFS
  handoff; P5 wait_any pid-order + state transitions + unknown-pid
  raises; R1 bare-engine migration; R2 item-25 gate re-run GREEN
  in-tree via subprocess. Migration: file_io + l1_personality +
  bk11_coreutils -> 23 passed unmodified.
- Probe/test defects fixed BEFORE evidence trusted (disclosed in the
  receipt): ST takes <addr_reg> <value_reg> (harness bug, not engine);
  wait_any ready-first ordering corrected (P5 caught it); numeric-JMP
  dead exploration removed (assembler takes col,row); R2 subprocess
  probes for a pytest-capable interpreter (worktree .venv is bare).
- Receipt: .builder_queue/RECEIPT_item26_process_model.md.
- Honesty (rule 6): all asserts structural — no rates/latencies,
  rule-1 floors do not attach; check_regime not implicated. NOT
  verified: no GPU-image execution (host CPU engine, Phase-2
  doctrine; nothing spatial, no VCC/Hilbert surface touched);
  cooperative only (no preemption/signals/shared RAM between task
  engines); the L1 shell has no spawn verb yet; twin parity not
  re-pinned (no engine/glyph-side change exists to pin).
- Queue state: QUEUE_STATE.json item-26 -> landed, item-29 unblocked
  (blocks_on cleared); CURRENT_TICKET.json reconciled. Next tick:
  claim item-27 (driver ABI freeze) by claim_order among unblocked.
  REPAIR_PENDING_BK27_L5 unchanged (holds; sign-off change).


### 2026-09-26 ~05:4x CDT — CLAIM QUEUE item 25 (VFS-2/3 syscall re-route + writeback persistence) LANDED (builder af3e62239ce2)

- Provenance re-verified at tick start: HEAD ec5fea0f (operator sign-off
  supply commit); tracked tree CLEAN; monitor CLAIM_PENDING queue=0 with
  supply=claim item-25; QUEUE_STATE.json active=null, item-25 UNBLOCKED
  (blocks_on=[], sign-off granted in ec5fea0f). Claimed per Phase-1b
  claim-queue-first (lowest claim_order unblocked).
- LANDED (commit 8ed329c4 in worktree ~/zion/worktrees/item25-vfs,
  cherry-picked to main as 9c285fdf after gates passed — the AGENTS.md
  blast-radius rule, since tools/glyph_isa_v2.py is a core engine file):
  - tools/glyph_vfs.py NEW — GlyphVfs: ext2 CONTENT via host e2progs
    debugfs ONLY (never parses ext2; item-24 spec discipline); PNG
    TRANSPORT via the landed png_vfs (VFS-1); VFS-3 writeback = staged
    overlay + sync() committing staging -> ext2 (debugfs -w) ->
    e2fsck -fn BEFORE the wrap -> png_vfs.wrap; guest-path containment
    mirrors L1Session.resolve ('..' escapes refused).
  - tools/glyph_isa_v2.py +48 lines: self.vfs = None default + early
    re-route arms in 0x03/0x04/0x13. NO-VFS DEFAULT PATH BYTE-UNCHANGED
    (every existing caller; M1 leg proves the host roundtrip in-gate).
- Gate: tests/test_item25_vfs.py — RED first (implementation stashed ->
  ModuleNotFoundError: No module named 'tools.glyph_vfs' at collection),
  then GREEN 8 passed in 34.40s (worktree) and 33.04s (main tree at
  9c285fdf, post-cherry-pick re-gate). Legs: L1 0x03/0x04 roundtrip
  through the REAL syscall program (host-absence asserted); L2 0x13
  listing, entry-count rc; L3 VFS-3 reboot persistence (fresh GlyphVfs
  from the same PNG reads synced bytes exact + external e2fsck clean);
  L4 '..' escape refused at the syscall arm; L5 clean-sync no-op +
  corrupt-superblock sync refuses rc -1 (non-vacuity, item-24's 0x1234
  RED leg reused); M1/M2/M3 = the MANDATORY MIGRATION MATRIX (host
  default unchanged in-gate; test_l1_shell_personality.py and
  test_bk11_coreutils.py pass UNMODIFIED via subprocess).
- Probe-defects fixed BEFORE evidence trusted (all disclosed, dbg_item25_*
  scripts committed): debugfs 1.47 has NO `put` (`write <native> <new>`,
  arg order verified via usage error); debugfs stat prints "Type:
  regular" not "regular file" (first _image_has false-negatived — the
  smoke's "fresh-boot read: None" was a PROBE bug, not a sync failure);
  pytest tmp_path strings (~80 chars) overflow the landed addr-32 path
  fixture into the data window at 96 (PATH_ADDR moved to 384 in-gate
  with an assert-backed bound; the landed test_glyph_file_io.py uses
  short tempfile paths and never hits this).
- Receipt: .builder_queue/RECEIPT_item25_vfs23.md (migration matrix
  table, NOT-proved list, files-touched scope check).
- Honesty (rule 6): all asserts structural (rc values, bytes, existence,
  fsck rc) — no rates/latencies, rule-1 floors do not attach; check_regime
  not implicated. NOT verified: no GPU-image execution (host CPU engine,
  Phase-2 doctrine; nothing spatial, no VCC/Hilbert surface touched);
  the L1 shell does not ATTACH a VFS yet (wiring GlyphVfs into
  GlyphL1Shell is the items-26..28 ladder's foundation); sync carries
  regular files only (no symlinks/attrs); kill -9 mid-sync crash-safety
  is R3.2's row, not claimed here.
- Queue state: QUEUE_STATE.json item-25 -> landed; CURRENT_TICKET.json
  reconciled. items 26-29 queued (26, 27 unblocked; 28 blocks on 27;
  29 blocks on 26). REPAIR_PENDING_BK27_L5 unchanged (holds; sign-off
  change). Next tick: claim item-26 by claim_order among unblocked.


### 2026-09-26 ~01:5x CDT — PHASE-1c RESEARCH tick: DEFECT-31k ecall→SYSCALL rewrite adjacency MEASURED — 2 silent RED legs, BK-35 filed (commit 8c737685, builder af3e62239ce2)

- Provenance re-verified at tick start: HEAD eb4dc784 (my BK-34 ledger
  lineage); tracked tree CLEAN; monitor CLAIM_PENDING queue=0;
  QUEUE_STATE active=null, item-25 still RESERVED (operator sign-off);
  no RULING_*/supply newer than my last landed commit. Queue empty ->
  Phase-1c research per this ledger's next-tick line. NEW op-class
  (rule 5): the syscall lowering boundary (ecall/ebreak/mret -> glyph
  HALT/SYSCALL/SYSRET) — the class the 31j entry named as next.
- Question: the transpiler lowers ecall to bare HALT
  (rv64i_to_glyph.py:1438-1440) and the GH-23 loader rewrites HALT ->
  SYSCALL r10 ONLY if the immediately-preceding emitted line starts
  `LDI r17 ` (test_gh23_libc_runtime.py:435; adjacency asserted
  load-bearing at :795-804). Does that contract hold for ecall shapes
  beyond the fixture's `li a7,N; ecall` — and what happens when it
  does not?
- Measured answer: NO — probe dbg_d31k_ecall_rewrite_af3e.py (proven
  d31f harness; programs loaded through the REAL _load_posix_program;
  baked libc_runtime_kernel_image; GlyphRunner 16384 words; 3 runs
  deterministic; tree==HEAD op-streams byte-identical per pc):
  - C01 adjacent li a7,64; ecall -> rewrite fires (1 SYSCALL r10 in
    the loaded program), write-tile window 718=0x1234, post-ecall
    marker 902=0x1234 — PASS. The landed fixture shape is safe.
  - L02 ONE intervening op (li x10,0 between a7 load and ecall) ->
    HALT's predecessor is `LDI r10 0x0`, rewrite misses -> bare HALT:
    window/marker dead, halted=True faulted=False — SILENT mid-program
    stop. RED.
  - L03 runtime syscall number (mv a7,x5 = `LDI r17 0; ADD r17 r5`) ->
    predecessor is an ADD, rewrite misses even though the LDI r17 is
    one op earlier -> same silent stop. RED. This is the
    dispatch-wrapper shape every real syscall thunk library compiles
    to when the number is not a compile-time constant.
  - Ordinary optimized-code shapes break the contract: instruction
    scheduling between the a7 load and the trap; any not-compile-time
    syscall number. The failure mode is indistinguishable from a clean
    halt (halt_reason=None).
- Probe-defect disclosed (fixed BEFORE evidence taken): run-1 used
  word 901 as the continuation marker — that word is the target of the
  PRE-ecall store sw x10,4(x18); C01 "failed" on its own store.
  Corrected to word 902 (the post-ecall store target); C01 then PASSes.
  Gate tails: output/d31k_gate_run1.txt, output/d31k_gate_run2.txt.
  Harness self-check this tick: dbg_d31f suite reproduces its receipted
  2/12 PASS 10 RED at HEAD (harness not drifted).
- Session tooling hazard (disclosed): terminal echo drift corrupted
  filename echo AND file-content reads this tick (same phenomenon the
  31i/31e entries disclosed); counterparty-visible files were written
  via write_file (hash-verified) and judged by run output + independent
  listing passes, not by read-back. The early "0/0 PASS" runs were the
  drift artifact, not a probe result.
- LANDED (commit 8c737685): RESEARCH_defect31k_ecall_rewrite.md, the
  probe, the row file + guarded append script (append-count asserted
  ==1). BK-35 row appended to systems/GLYPH_BACKLOG.md (grep-verified
  BK-35 unique; backlog NOT lane-claimable per header rules — BK-35 is
  Jericho's to assign). Fix shape in the row, cheapest-first: (a) emit
  SYSCALL r10 at the OP_ECALL arm under a module flag (loader pass
  kept as safety net); (b) dataflow scan for r17 writes since the last
  branch/call boundary; (c) loud-fail marker so a missed rewrite traps
  instead of silently stopping. NO engine code touched (rule 5).
- Honesty (rule 6): all numbers structural asserts (memory words,
  halted/faulted booleans, static instruction counts) from real runs
  this tick — no rates/latencies, rule-1 floors does not attach.
  NOT verified: ebreak path (unconditional SYSCALL r10, :1446-1447 —
  different mechanism, unprobed); KSYS_PC-armed E-K2 trap leg;
  WGSL twin (transpiler/loader-side, nothing spatial); live
  xv6-nano/libc-fixture repro (latent-only — all landed gates stay
  GREEN, rule 2 not triggered).
- Next tick: claim queue still empty of unblocked items (item-25
  RESERVED); REPAIR_PENDING_BK27_L5 still holds. Research again ONLY if
  still no new supply/RULING — else take the queue. Remaining unprobed
  members of the syscall-boundary class: ebreak lowering, the
  KSYS_PC-armed trap leg; LUI/AUIPC paths (expected clean, unprobed).

### 2026-09-26 ~02:4x CDT — PHASE-1c RESEARCH tick: DEFECT-31j branch/compare aliasing MEASURED — 6 RED legs across 3 shapes (S1 unsigned-as-signed, S2 operand-as-scratch, S3 zero-scratch self-cmp), BK-34 filed (builder af3e62239ce2)

- Provenance re-verified at tick start: HEAD 24006234 (my BK-33 research
  lineage); tracked tree CLEAN; monitor fingerprint CLAIM_PENDING queue=0;
  QUEUE_STATE active=null, item-25 still RESERVED (operator sign-off);
  no RULING_*/supply newer than my last landed commit. Queue empty ->
  Phase-1c research per this ledger's next-tick line. NEW op-class
  (rule 5): the branch/compare family beq/bne/blt/bge/bltu/bgeu — the
  exact set BK-33 named UNPROBED.
- Question: (a) do branch lowerings alias fixed scratch r28/r29/r30 when
  an OPERAND lives in the scratch class; (b) do BLTU/BGEU lower with
  true unsigned semantics?
- Measured answer: BOTH defect classes REAL (probe
  .builder_queue/dbg_d31j_branch_compare_alias_af3e.py + corrected-leg
  probe dbg_d31j3_bltu_discriminating_af3e.py, both reusing the proven
  d31f harness; tree==HEAD op-streams byte-identical per pc; 3 runs each,
  deterministic):
  - S1 unsigned-as-signed: BLTU shares BLT's lowering (:1297), BGEU
    shares BGE's (:1322) — sign bit of rs1-rs2 = SIGNED test. Corrected
    discriminating legs {1, 0xFFFFFFFF}: bltu 1,0xFFFFFFFF -> NOT taken
    (golden taken) RED; bgeu 0xFFFFFFFF,1 -> NOT taken RED. SILENT.
    HONESTY: the first S1 pair {1, 0x80000000} was NON-DISCRIMINATING
    (signed diff 0x80000001 negative coincides with unsigned) — passes
    reported with the coincidence explained; the corrected pair is the
    evidence.
  - S2 operand-as-scratch: the DEFECT-16 PUSH/POP guards protect x28..x30
    ACROSS the lowering, but the compare body itself zeroes r30 then adds
    rs1/subs rs2 — rs1==x30 or rs2 in scratch reads clobbered values:
    blt x30(2),x9(1) -> wrongly taken RED (step trace: LDI r30 0 zeroes
    live x30=2 at step 318); bge x30,x9 -> wrongly not-taken RED. SILENT.
  - S3 zero-scratch self-cmp: beq x0,x28 / bne x28,x0 lower to
    CMP r28 r28 — always-equal: beq always-taken RED, bne never-taken
    RED. SILENT.
  - Controls PASS: blt clean regs, bltu small-unsigned, beq clean
    zero-path. bne skip-label uniqueness probed CLEAN (dbg_d31j4) —
    label counter NOT a defect. L04 directional-only, excluded.
- LANDED (commit a772f10a): RESEARCH_defect31j_branch_compare_aliasing.md,
  4 probes, BK-34 row appended to systems/GLYPH_BACKLOG.md (row 61;
  BK-34 grep-unique; backlog header = NOT claimable without Jericho).
  NO engine code touched; no substrate writes.
- NOT done: no WGSL leg for the branch family (the WGSL twin's branch
  lowering was not probed this tick — noted as follow-on); no fix
  attempt (research-only lane).
- Next tick: per Phase-1c — if queue/RULING still empty, remaining
  members of the family are covered by BK-34's legs, so the next NEW
  op-class would be the syscall lowering boundary (SYS) or the WGSL
  twin's branch lowering; alternatively a fix tick against BK-34's
  cheapest fix if Jericho promotes it.

### 2026-09-26 ~01:2x CDT — PHASE-1c RESEARCH tick: DEFECT-31i JALR computed-jump aliasing MEASURED — 2 RED legs (1 silent, 1 loud), BK-33 filed (builder af3e62239ce2)

- Provenance re-verified at tick start: HEAD d6169173 (my BK-32 research
  lineage); tracked tree CLEAN; monitor CLAIM_PENDING queue=0 (the
  head-change diff was my own ledger commit); QUEUE_STATE.json
  active=null, item-25 RESERVED (operator sign-off); no RULING_*/supply
  newer than my last landed commit. No new supply → Phase-1c research
  per this ledger's next-tick line. NEW op-class satisfied (rule 5):
  branch/compare lowerings — the family the 31h entry named as
  unprobed; first member probed = JALR (the computed jump).
- Question: does the JALR dynamic-target lowering alias fixed scratch
  (glyph r30 table-index temp, glyph r29 imm/shift scratch) under the
  identity register map, like 31c/31e/31f/31g/31h did on the data paths?
- Measured answer: YES, two shapes, probe
  .builder_queue/dbg_d31i_jalr_alias_af3e.py (reuses the proven d31f
  harness; tree==HEAD op-streams byte-identical per pc in all 4 legs;
  deterministic across 3 runs):
  - L01 jalr x0,0(x30) rs1==x30 → faulted=True, mem=0x0 (golden 0xBEEF)
    RED — `ADD r30 r30` reads the clobbered x30, indexes the pointer
    table at (tbl+tbl)>>2 = garbage. First LOUD (faulting) RED of the
    31-family.
  - L02 jalr x30,0(x5) rd==x30 → halted=True faulted=False, mem=0x0 RED
    — the return-address `LDI r30 <pc+4>` OVERWRITES the loaded target
    BEFORE `CALLR r30`; jumps at its own return address, SILENT.
  - Controls PASS: C03 jalr x0,0(x5) clean; C04 jalr x1,0(x5) plain
    call.
- Mechanism (source-verified at HEAD, tools/rv64i_to_glyph.py:1366-1436):
  the dynamic path lowers `LDI r30 <tbl>; ADD r30 r{rs1}; ...; LDI r{rd}
  <pc+4>; CALLR r30` unconditionally — same fixed-scratch discipline gap
  as BK-31/32. Fix shape = the DEFECT-31/30 PUSH/POP pattern on rs1==30
  plus staging rd's return address when rd==30 (CALLR must read the true
  target).
- LANDED (commit THIS): RESEARCH_defect31i_jalr_aliasing.md, the probe,
  BK-33 row appended to systems/GLYPH_BACKLOG.md (row 60; grep-verified
  BK-33 free; row path refs existence-checked, cited line window
  verified to contain the JALR lowering). NO engine code touched
  (rule 5).
- Honesty (rule 6): all numbers structural asserts (mem words,
  halted/faulted, op listings) from real GlyphRunner runs this tick —
  no rates/latencies, rule-1 floors do not attach. NOT verified: no
  WGSL twin leg; no live xv6-nano repro (latent-only — no landed gate
  computed-jumps through x29/x30; landed gates stay GREEN, rule 2 not
  triggered); L02's gcc-plausibility argued not measured (gcc
  allocated x1/x5 in every observed stream; exposure needs hand asm or
  a different allocator); sibling compare lowerings (beq/bne/blt/bge
  rs1/rs2==x28..x30) still unprobed; fix proposed in BK-33, not
  implemented. Probe-honesty: terminal echo showed character drift
  this tick (same phenomenon d31e disclosed); the committed probe file
  was re-read from disk and its import target verified to resolve
  before trusting any run.
- Next tick: claim queue still empty of unblocked items (item-25
  RESERVED); REPAIR_PENDING_BK27_L5 still holds. Research again ONLY if
  still no new supply/RULING — else take the queue. Remaining unprobed
  families: compare lowerings (beq/bne/blt/bge operand aliases),
  LUI/AUIPC paths (AUIPC is compile-time-constant — likely clean, LUI
  is a single LDI — likely clean; probe both to close the family).

### 2026-09-26 ~01:1x CDT — PHASE-1c RESEARCH tick: DEFECT-31h SW VALUE-side aliasing MEASURED — 4 silent RED legs, BK-32 filed (builder af3e62239ce2, commit 99dab745)

- Provenance re-verified at tick start: HEAD f4fe2946 (my BK-31 research
  lineage); tracked tree CLEAN; monitor CLAIM_PENDING queue=0; QUEUE_STATE.json
  active=null, item-25 RESERVED (operator sign-off); no RULING_*/supply/brief
  newer than my last landed commit. No new supply -> Phase-1c research per this
  ledger's next-tick line.
- Family picked: the SW VALUE-side leg (rs2==x30 / rs2==x29), the exact
  follow-on candidate BK-31's receipt named — BK-31's L03 hit it only CONFOUNDED
  (through the LW address defect); this probe
  (.builder_queue/dbg_d31h_sw_value_side_alias_af3e.py, reuses the proven d31f
  harness; tree==HEAD lowering identical per pc in all 7 legs; deterministic
  across 3 runs) never loads through x30, so the class is cleanly measured for
  the first time:
  - L01 sw x30,0(x18) -> mem[768]=0x300 (golden 0xBEEF) RED — stores the ADDRESS
  - L02 sw x30,4(x18) -> 0x0 with word 769=0x301 RED — address INTO address
    slot (self-overwrite; corruption beyond the wrong-value class)
  - L03 sw x30,0(x0) -> 0x0 RED — stores base 0
  - L04 sw x29,0(x18) -> 0x2 RED — stores the byte_to_word shift amount
  - All four RED legs SILENT (halted=True faulted=False).
  - Controls PASS: C05 normal path; C06 base-x30 DEFECT-31 fix path; C07
    sw x30,0(x30) via fix path = 0xC00 — C07 fully attributes BK-31's
    confounded L03 to this class.
- Mechanism (source-verified at HEAD, tools/rv64i_to_glyph.py:913-962): the
  unguarded SW path (rs1 not in {29,30}) reads the value operand at `ST` time,
  AFTER writing the r30 address temp and the r29 shift scratch; identity map
  makes glyph r30/r29 == RV x30/x29. Fix shape = the DEFECT-31/DEFECT-30
  PUSH/POP pattern on the value operand when rs2 in {29,30}.
- LANDED (99dab745): RESEARCH_defect31h_sw_value_side_aliasing.md, the probe,
  the append script, BK-32 row appended to systems/GLYPH_BACKLOG.md (row 59;
  BK-32 grep-verified free before filing). NO engine code touched (rule 5).
- Honesty (rule 6): all numbers are structural asserts (memory words,
  halted/faulted flags) from real GlyphRunner runs this tick — no rates or
  latencies, rule-1 floors do not attach. NOT verified: no WGSL twin leg; no
  live xv6-nano repro (latent-only — no landed gate known to store x29/x30 as
  a VALUE through an unguarded base; landed gates stay GREEN, rule 2 not
  triggered); L02's second-word write makes this a two-word corruption vector,
  flagged in the receipt; fix proposed in BK-32, not implemented.
- Next tick: claim queue still empty of unblocked items (item-25 RESERVED);
  REPAIR_PENDING_BK27_L5 still holds. Research again ONLY if still no new
  supply/RULING — else take the queue. Remaining unprobed families:
  branch/compare lowerings (JALR/beq bounds), LUI/AUIPC paths; the 31-family
  SW/LW address+value map is now COMPLETE (31c/31e/31f/31g/31h).

### 2026-09-26 ~00:5x CDT — PHASE-1c RESEARCH tick: DEFECT-31g LW address-path aliasing MEASURED — 3 RED legs (silent), BK-31 filed (builder af3e62239ce2)

- Provenance re-verified at tick start: HEAD 7c0d62da (my BK-30 research
  lineage); tracked tree CLEAN; monitor CLAIM_PENDING queue=0 (the
  head-change diff was my own ledger commit); QUEUE_STATE.json
  active=null, item-25 RESERVED (operator sign-off); no RULING_*/supply
  newer than my last landed commit. No new supply → Phase-1c research
  per this ledger's next-tick line (NEW family required).
- Family picked: LW/SW ADDRESS path (31c=SB/SH else, 31e=store fix
  value-side, 31f=ALU/imm; the LOAD path was never probed).
- Measured answer: YES, asymmetric with the landed SW fix —
  tools/rv64i_to_glyph.py:899-909 (LW) uses glyph r30 as address temp
  UNCONDITIONALLY (LDI r30 imm; ADD r30 r{rs1}); SW got the rs1==30
  guard at :913-928 (DEFECT-31). Probe
  .builder_queue/dbg_d31g_lw_addr_alias_af3e.py (reuses the proven d31f
  harness module; tree==HEAD lowering identical per pc in all 6 legs;
  deterministic across 3 runs):
  - L01 lw x9,0(x30) base x30 → mem[768]=0x0 (golden 0xabcd) RED
  - L02 lw x9,8(x30) → 0x0 RED — both SILENT (halted=True
    faulted=False); imm=0 does not save the leg (LDI r30 0; ADD r30 r30
    = 0 → loads word 0).
  - L03 lw x30,0(x30) dest=base → 0x300 RED but CONFOUNDED (also hits a
    SW rs2==x30 value-side collision — directional only, disclosed in
    the receipt; NOT filed as a defect without a clean leg).
  - Controls PASS: L04 base x18; L05 SW base-x30 DEFECT-31 fix path
    (its passing IS the asymmetry proof); L06 lw/sw roundtrip.
- LANDED (commit this tick): .builder_queue/RESEARCH_defect31g_lw_addr_aliasing.md,
  probe committed under .builder_queue/, BK-31 row appended to
  systems/GLYPH_BACKLOG.md (row-58, grep-verified BK-31 was free; all
  referenced paths existence-checked). NO engine code touched (research
  never lands engine code, rule 5).
- Honesty (rule 6): all numbers are structural asserts from GlyphRunner
  receipts of real runs this tick — no rate/latency → rule-1 floors
  does not attach. NOT verified: no WGSL twin leg; no live xv6-nano
  repro (latent-only — no landed gate allocates x30 as an LW base; all
  landed gates stay GREEN, rule 2 not triggered); the SW rs2==x30
  value-side class measured only via the confounded L03; fix proposed
  in BK-31, not implemented.
- Next tick: claim queue still empty of unblocked items (item-25
  RESERVED); REPAIR_PENDING_BK27_L5 still holds. Research again ONLY if
  still no new supply/RULING — else take the queue. Remaining unprobed
  families: branch/compare lowerings (JALR/beq bounds), LUI/AUIPC
  paths, the clean SW rs2==x30 value-side leg.

### 2026-09-26 ~00:5x CDT — PHASE-1c RESEARCH tick: DEFECT-31f ALU/imm lowering aliasing MEASURED — 10 RED legs incl. 1 FAULT, BK-30 filed (builder af3e62239ce2)

- Provenance re-verified at tick start: HEAD 96c97619 (my BK-29 research
  lineage); tracked tree CLEAN; monitor CLAIM_PENDING queue=0 (the
  head-change diff was my own BK-29 landing); QUEUE_STATE.json
  active=null, item-25 RESERVED (operator sign-off); no RULING_*/supply
  newer than my last landed commit. No new supply → Phase-1c research
  per this ledger's own next-tick line.
- Question (NEW op-class, rule 5 satisfied — BK-28 covered SB/SH else
  branches, BK-29 the store fix branches; the ALU/immediate lowerings
  were never probed): do ANDI/ORI/XORI/SUB-rd==rs2/neg/SLTI/SRLI/SRAI
  /SLTIU have the same fixed-scratch lifetime aliasing when rd or rs1
  lands in x26..x30?
- Measured answer: YES — 10 RED of 12 legs, probe
  .builder_queue/dbg_d31f_alu_imm_alias_af3e.py (hand-encoded RV32I
  words — no gcc allocation variance; deterministic across 3 runs;
  tree lowering == `git show HEAD:` snapshot per pc in all 12 →
  latent-at-HEAD, not a lane regression). All REDs halted=True
  faulted=False except L12 (FAULTED) — silent misexecution:
  - Shape 1 (rd==rs1==x29): andi self → mem=0xff (golden 0x34) —
    stores THE IMM (`LDI r29 imm; AND r29 r29`); ori self → 0x34;
    xori self → 0x0; sub x29,x28,x29 → 0x0 (`SUB r29 r29` self-
    subtract); neg x29 → 0x0; srli self → 0x0 (shamt LDI); srai self →
    0xf8000000 (sign-only); slti self → 0x0 (rs1 consumed into rd
    first); sltiu self → 0x0 (mask LDI precedes rs1 consume — even the
    "defensive ordering" path is defeated).
  - Shape 2 (UNCONDITIONAL bleed, no aliasing needed): sltiu writes
    r28/r29/r30 on every emission → with a live x30 store base the
    store itself FAULTS (L12: faulted=True, mem=0x0 vs golden 0x1).
  - Controls PASS (andi x28 self; sub x28 rd==rs2) — the correct
    ordering pattern (`SUB r29 r28` before the r28 write) exists in
    the tree and is applied selectively.
- Op-stream listings cross-checked instruction-by-instruction: every
  RED explained at the lowering level, not just end-to-end. Measured
  probe-defect kept (disclosed): run-1's "controls" stored x28 with
  base x30 and accidentally re-measured the KNOWN DEFECT-31 SW value-
  temp leg (0x300 = word address) — rewrote the store convention
  (base x18, result mv'd through x9) before trusting any leg; L01's
  first golden (0x34) was vacuous (imm==golden) and was re-pinned to
  0x1234 with imm 0xff.
- LANDED (commit 03e5188b on top of 96c97619):
  .builder_queue/RESEARCH_defect31f_alu_imm_aliasing.md (question/
  method/findings/BK-format candidate), probe committed under
  .builder_queue/, BK-30 row appended to systems/GLYPH_BACKLOG.md
  (grep-verified free). NO engine code touched (research never lands
  engine code, rule 5).
- Honesty (rule 6): all numbers are structural asserts from GlyphRunner
  receipts of real runs this tick (mem words, halted/faulted booleans,
  opcode listings) — no rate/latency → rule-1 floors does not attach.
  NOT verified: no WGSL twin leg (transpiler-side, nothing spatial);
  no live xv6-nano repro (latent-only — no landed scenario allocates
  x26..x29 as these operands; all landed gates stay GREEN, rule 2 not
  triggered); the fix is proposed in BK-30, not implemented.
- Next tick: the 31c/31e/31f family now has a complete measured map;
  claim queue still empty of unblocked items (item-25 RESERVED);
  REPAIR_PENDING_BK27_L5 still holds. Research again ONLY if still no
  new supply/RULING — else take the queue. Next research tick should
  pick a NEW family (candidates: branch/compare lowerings JALR/beq
  bounds; LW/SW immediate-path aliasing rs1==x30; LUI/AUIPC paths).

### 2026-09-26 ~0:4x CDT — PHASE-1c RESEARCH tick: DEFECT-31e fix-branch value aliasing MEASURED — 8 RED legs, BK-29 filed (builder af3e62239ce2)

- Provenance re-verified at tick start: HEAD 03dd25d4 (my BK-28/BK-29
  research commit lineage); tracked tree CLEAN before this tick's
  artifact writes; monitor CLAIM_PENDING queue=0; QUEUE_STATE.json
  active=null, item-25 RESERVED (operator sign-off); no RULING_* newer
  than my last landed commit; REPAIR_PENDING_BK27_L5 unchanged. No new
  supply → Phase-1c research again, rule 5 satisfied: NOT a re-research
  — this is the next measured step on the DEFECT-31c family; no
  existing RESEARCH_*.md or backlog row covers the FIX-BRANCH legs
  (BK-28 covers only the SB/SH else branches).
- Question: are the LANDED rs1==30/rs1==29 guard branches (DEFECT-31c
  SB/SH fix, DEFECT-31 SW fix) themselves alias-free for the store
  VALUE register rs2? Reading tools/rv64i_to_glyph.py:1058-1083 (SB
  fix), :930-952 (SW fix), :1163-1187 (SH fix): the value is consumed
  by `LDI r26 0; ADD r26 r{rs2}` AFTER r27/r28/r29 have served as
  lane/shift/word_addr/cur_word scratch → predicted RED for
  rs2 ∈ {x26,x27,x28,x29}.
- Measured answer: YES — probe
  .builder_queue/dbg_d31e_fixbranch_alias_af3e.py, 12 legs, deterministic
  (gcc rv32i → transpile tree AND `git show HEAD:` snapshot, op streams
  byte-identical per pc in all 12 → latent-at-HEAD, not a lane
  regression) → bake libc_runtime_kernel_image → GlyphRunner, mem read
  from receipt. Summary 4/12 PASS, 8 RED, all REDs halted=True
  faulted=False (SILENT):
  - SB-fix value x26/x27/x28/x29 → mem[768]=0x0 (golden 0x42/0x43/0x44/0x45) RED
  - SH-fix value x27 → 0x0 (golden 0x4243) RED
  - SW-fix value x26 → 0x2 = the shift constant (`LDI r26 2`) RED
  - SW-fix value x28 → 0x300 = the word address itself RED
  - SW rs1==x29 elif value x26 → 0x0 (golden 0x5555) RED
  - controls (t1 value legs, sw x0, sw x29-value) PASS
- Mechanism visible in the transpiled artifact itself (recheck probe
  prints the listing): `... LD r29 r28; LDI r26 0; ADD r26 r27 ...` —
  the value read picks up the lane/shift SCRATCH r27, not RV x27.
- Independent recheck: .builder_queue/dbg_d31e_recheck_a2_af3e.py
  (fresh code + fresh tempdir, written after probe-echo drift was seen
  in terminal output this session) re-derived leg A2 with fresh code:
  mem[768]=0x0 vs golden 0x43, RED confirmed.
- LANDED: .builder_queue/RESEARCH_defect31e_fixbranch_aliasing.md
  (question/method path:line/findings/honesty), both probes committed
  under .builder_queue/, BK-29 row appended to systems/GLYPH_BACKLOG.md
  (number grep-verified free; backlog NOT lane-claimable per header
  rules — BK-29 is Jericho's to assign). NO engine code touched.
- Honesty (rule 6): all numbers are structural asserts from runner
  receipts of real runs this tick; no rate/latency → rule 1 does not
  attach. NOT verified: no WGSL twin leg (transpiler-side, nothing
  spatial); no xv6-nano scenario currently allocates x26..x29 as a
  store value into an x30/x29-based address → all landed gates stay
  GREEN (latent-only, not a regression; rule 2 not triggered).
- Next tick: claim queue still empty of unblocked items; REPAIR still
  holds; research again ONLY if still no new supply/RULING — else take
  the queue. The 31c/31e family now has a complete measured map (else
  branches = BK-28, fix branches = BK-29); no further unfixed legs of
  THIS family are known — next research tick should move to a new
  question, not re-derive these.

### 2026-09-26 ~0:0x CDT — PHASE-1c RESEARCH tick: DEFECT-31c latent aliasing MEASURED — 5 RED classes, BK-28 filed (builder af3e62239ce2)

- Provenance re-verified at tick start: HEAD 101be477 (my BK-27 L1-L4/L6
  ledger entry); tracked tree CLEAN (untracked non-lane files untouched);
  monitor CLAIM_PENDING queue=0; QUEUE_STATE.json active=null, item-25
  RESERVED (operator sign-off); no RULING_* newer than my last landed
  commit; REPAIR_PENDING_BK27_L5 still holds the L5 disposition
  (unchanged). No new supply → Phase-1c research per the ledger's next
  line; rule 5 satisfied — this is NOT a re-research: it is the next
  measured step on DEFECT-31c's own receipted disclosure ("rs1==29
  second-address re-read latent, unfixed, unmeasured"); no existing
  RESEARCH_*.md or backlog row covers it.
- Question: do the receipt's guessed-but-unmeasured latent aliasing
  classes in the LANDED SB/SH lowerings actually fault? The landed
  DEFECT-31c minimal fix (a7200a28) guards ONLY rs1==30; the else-branch
  re-reads rs1 AFTER its shift-scratch LDI, and reads rs2 AFTER mask/init
  LDIs.
- Measured answer: YES — and the class is BIGGER than the receipt
  guessed. Probe .builder_queue/dbg_d31c_latent_alias_af3e.py
  (re-runnable, deterministic, riscv gcc + GlyphRunner, no GPU/LLM):
  minimal RV32I programs transpiled through BOTH the tree and HEAD
  (op streams byte-IDENTICAL in all 6 cases — latent at HEAD, NOT a lane
  regression), baked via libc_runtime_kernel_image, run, mem[768]
  compared to golden:
  - sb base x29 → mem=0x0, golden 0x41 — RED (2nd `ADD r30 r29` reads
    the shift constant 3 written by `LDI r29 3`; store lands at word 0)
  - sh base x29 → 0x0 vs 0x4243 — RED (same shape)
  - sb value x27 → 0xff vs 0x42 — RED (value read AFTER `LDI r27 0xff`
    mask; the lane bits already set in cur_word survive clear+insert)
  - sh value x27 → 0xffff vs 0x4243 — RED (same, halfword mask)
  - sb value x26 → 0x0 vs 0x44 — RED (`LDI r26 0` init IS the clobber)
  - non-aliased control → PASS
  All RED/PASS runs halted=True faulted=False — SILENT corruption.
  Probe bug fixed mid-tick (disclosed): the first run used `t2` for the
  x27 cases — t2 is x7; gcc never allocates x26/x27 from ABI temp names,
  so those two cases falsely PASSED; explicit numeric registers give the
  true REDs above.
- Root cause (op-stream dump .builder_queue/dbg_d31c_dump_sb_x29_af3e.py,
  pc_0000020c): the SB else-branch computes the address, then `LDI r29 3`
  destroys the base register BEFORE the second `ADD r30 r29` re-derives
  it. SH else-branch same class; value side = scratch-write ordering.
- LANDED: .builder_queue/RESEARCH_defect31c_latent_aliasing.md (question
  / method with path:line / findings with numbers / BK-format candidate),
  both probes committed under .builder_queue/, BK-28 row appended to
  systems/GLYPH_BACKLOG.md (next free number grep-verified; backlog NOT
  lane-claimable per its header rules — BK-28 is Jericho's to assign).
  NO engine code touched (research never lands engine code, rule 5).
- Honesty (rule 6): every number is a structural assert (mem/halted/
  faulted read from GlyphRunner receipts of real runs this tick) — no
  rate, no floors claim, rule-1 does not attach. NOT verified: no WGSL
  twin (transpiler-side, nothing spatial); no xv6-nano scenario
  allocates these registers, so the landed 13/13 gate stays GREEN
  (latent-only — this is not a regression); the FIX is proposed in
  BK-28, not implemented.
- Next tick: claim queue still empty of unblocked items; the REPAIR
  still holds; research again ONLY if still no new supply/RULING —
  else take the queue.

### 2026-09-25 ~23:5x CDT — BK-27 L1-L4/L6 LANDED: shell-native bake cache, 6/6 RED->GREEN (commit 32443ece, builder af3e62239ce2)

- Provenance re-verified at tick start: HEAD 6d283d0d (my BK-27 L5
  ledger entry); monitor CLAIM_PENDING queue=0. QUEUE_STATE.json
  active=null; item-25 still RESERVED (operator sign-off); no
  RULING_* newer than my last landed commit. Supply state unchanged →
  continued the ledger's own next line: BK-27 follow-through, landing
  the legs the REPAIR explicitly did NOT block (L1-L4/L6).
- LANDED (commit 32443ece): session-scoped bake cache on
  GlyphL1Shell, keyed on the FULL bake input vector (verb,
  json(argv), data_len, sha256(data bytes)). Hit → replay the same
  baked image through GlyphRunner.run; readout shared with the fresh
  path (_shell_native_collect) so the paths cannot drift; a cached
  image faulting on replay is evicted. Engine/baker/runner/dogfood
  tool untouched.
- Full-argv keying also fixes the REPAIR's collision finding at the
  cache level: the row's stated "(verb, data-hash)" key would make
  the dogfood suite's two grep turns collide; distinct patterns are
  now distinct entries (L6 pins this, with an internal non-vacuity
  leg that force-collides entries and asserts the output flips).
- Gate: tests/test_bk27_shellnative_bake_cache.py — RED first
  (implementation stashed): 2 failed (L1 timing, L6 separation),
  4 passed, exit 1 (output/bk27_gate_run_red.txt) → GREEN: 6 passed
  in 20.52s, exit 0 (output/bk27_gate_run_green.txt).
- Measured (probe .builder_queue/probe_bk27_hit_af3e.py, 3 runs,
  wall-clock, one process): fresh-bake turn 2532.7/2549.7/2530.0 ms
  vs cache-hit 59.8/54.6/50.7 ms (42.4x/46.7x/49.9x). NOT
  floors-attached; no rate claim; check_regime not implicated.
- Regression family this tick: L1 personality/L2 files/L3 pipes/GH-10
  shell 72 passed; BK-22 5 passed; item-20 swap 9 passed; BK-23 gate
  3/4 — the 1 fail is BK-23's own L5 budget leg (4438.3ms vs 3500ms),
  the KNOWN receipted RED, unchanged.
- Receipt: .builder_queue/RECEIPT_BK27_L1_L6_SHELLNATIVE_BAKE_CACHE.md
  (includes the NOT-proved list: no WGSL twin leg — nothing spatial;
  BK-23 L5 stays red; per-session cache only; n=3 wall-clocks).
- NEXT (open): REPAIR_PENDING_BK27_L5_dogfood_budget.md still holds
  the L5/key-spec disposition (skeleton-sign-off change, options A/B/C
  cheapest-first). No other supply unblocked; item-25 RESERVED.
  Lane returns to claim-queue-first on next tick.

### 2026-09-25 ~23:1x CDT — PHASE-1c research follow-through: BK-27 L5 proven UNREACHABLE, REPAIR_PENDING filed (commit d1eac4a4, builder af3e62239ce2)

- Provenance re-verified at tick start: HEAD e4d174ac (my BK-27
  research tick); monitor state CLAIM_PENDING, supply line truncated.
  QUEUE_STATE.json active=null; no unblocked claim items (item-25
  RESERVED, operator sign-off). Proceeded per the ledger's own next
  line: no new supply → research follow-through on BK-27 (the open
  candidate), rule 5 satisfied (same question, next measured step,
  not a re-derivation).
- Question taken: BK-27's L5 leg claims the bake cache "repairs the
  BK-23 L5 time-budget regression" (dogfood suite <3500ms). Can it?
- Measured answer: NO — the leg is unreachable as specified.
  tools/dogfood_gpu_os.py contains exactly TWO shell-native turns
  (grep record2 :262, grep nonexistent_word :266, same file). The
  grep pattern rides the C seed block (glyph_l1_shell.py:942-947,
  grep_pattern as a second .data seed), so the two turns compile to
  DIFFERENT binaries and bake DIFFERENT images → an honest
  (verb, args, data)-keyed cache gets 0 hits inside one suite run.
  Corollary defect: the row's stated key "(verb, data-hash)" —
  pattern excluded — makes :262/:266 COLLIDE; the second turn would
  serve the first one's image and the suite's own `assert g2 == ""`
  fires. The key spec must carry the full arg vector.
- Evidence this tick (all real runs, receipts in the REPAIR file):
  - RED gate drafted tests/test_bk27_shellnative_bake_cache.py: L1
    cache-hit budget, L2 fresh-bake parity, L3 invalidation, L4
    bypass non-vacuity, L5 BK-23 family, L6 per-key separation +
    refusal contract. L1-L4/L6 PASSED against a working cache
    implementation (draft, held back of the tree — see below).
    L5 RED at 4180.4-4210.7ms vs the 3500ms budget at HEAD
    dd8b55ea — confirming the cache cannot move it.
  - Probe tools/probe_bk27_dogfood_args_af3e.py (committed):
    static source read, 2 native turns, distinct keys = 2, available
    cache hits = 0, (verb, data)-key collisions = 1. Re-runnable.
- LANDED: the REPAIR file + the probe (commit d1eac4a4, on top of
  dd8b55ea — BM801's OriginFrame.physical() wrap gate landed mid-tick
  between my gate runs and commit; linear history, no overlap with
  its files). The drafted gate test + cache implementation were NOT
  committed: a gate whose landed L5 leg is permanently red is not
  landable, and rescoping L5 is a skeleton-sign-off change.
- REPAIR_PENDING_BK27_L5_dogfood_budget.md filed with options
  cheapest-first: (A) rescope L5 out of BK-27's gate, keep L1-L4/L6,
  give the dogfood budget its own disposition; (B) add an in-suite
  repeated native turn so a real cache hit exists (touches a landed
  CI fixture — needs a non-weakening sign-off); (C) post-bake pattern
  stamping (ABI change to the item-20 swap contract, out of BK-27's
  "engine untouched" boundary).
- Honesty: the RED gate run was against a draft implementation in the
  working tree this tick, since deleted — its L1-L4/L6 PASS tails are
  NOT preserved as landed artifacts (disclosed; the REPAIR file carries
  the measured numbers, the probe carries the re-runnable part). L5's
  4180.4/4210.7ms measurements were real pytest runs at dd8b55ea and
  e4d174ac respectively. Wall-clock only; not floors-attached (no rate
  claim made). BK-23's landed gate remains RED at HEAD d1eac4a4 —
  unchanged by this tick, now with a filed explanation instead of an
  open question.
- NOT verified: no in-guest execution; no WGSL twin (nothing spatial);
  item-25 untouched; no engine files touched; the REPAIR is not a
  ruling — BK-27's L1-L4/L6 remain eligible pending a claim surface,
  but ONLY after the L5/key question gets its RULING.

### 2026-09-25 ~21:4x CDT — PHASE-1c RESEARCH tick: path-budget stranded capacity measured, BK-26 proposed (commit ef141460, builder af3e62239ce2)

- Provenance re-verified at tick start: HEAD 018a1645 (item-22b
  landed); no RULING_* newer than 2026-09-22 20:38; QUEUE_STATE.json
  active=null, no unblocked claim items (item-25 RESERVED, operator
  sign-off); monitor CLEAN queue=0. Phase-1c research per the ledger's
  own next-step line. NOT a re-research (rule 5): no existing
  RESEARCH_*.md or backlog row covers path-budget mechanics.
- Question: item-22b's landing receipt flagged the L1 shell FS-window
  path budget as the binding constraint (49-char /tmp root rejected).
  Where does the budget actually bind and how much capacity is
  stranded? Measured, not asserted:
  - PATH_CAP = 48 (glyph_l1_shell.py:85) is a FLAT per-path cap.
  - The real ceiling is the FS-window overflow assert
    (glyph_interactive_shell.py:493, DISPATCH_BUF_CAP=64): binary-
    search maxima at HEAD 018a1645 = 171-char write path (audio=14),
    172-char audio (write=13), 92+92 equal split. Headroom stranded:
    2.6-3.6x depending on split.
  - layout["path_cap"] (glyph_interactive_shell.py:805) algebraically
    equals len(write)+1 — a MISLABELED non-capacity, and the number
    tools/build_workbench_container.py:69 bakes as its PATH_CAP.
- Landed: .builder_queue/RESEARCH_path_budget_stranded.md (question /
  method with path:line / findings with numbers / one BK-format
  candidate), probes probe_path_budget_af3e.py +
  probe_path_budget2_af3e.py (committed; binary search re-runnable),
  BK-26 row appended to systems/GLYPH_BACKLOG.md (next free number;
  grep-verified no BK-26/27/28 anywhere in tree).
- Commit ef141460 on top of f74acfb4 (BM801 lane landed mid-tick
  between my probe runs and commit — linear history, no conflict, its
  five dirty files untouched by this lane). NOT claimable lane-side
  per backlog header rules; one research item this tick, per rule 4.
- Honesty (rule 6): every number is a structural count (source algebra
  + assert-driven binary search in live processes this tick) — not a
  floors/cost claim, so rule-1 floors treatment does not attach.
  NOT verified: no in-guest execution; no WGSL twin (nothing spatial);
  the 187-char boundary is derived+assert-checked but not yet pinned
  by a landed gate leg (that is BK-26's L2, proposed not landed); no
  engine files touched; item-25 untouched.
- Next: claim queue still empty of unblocked items — next tick
  research again ONLY if still no new supply/RULING; else take queue.

### 2026-09-25 ~21:5x CDT — CLAIM QUEUE item 22b (standalone workbench container, items 22+23 second context) LANDED (builder af3e62239ce2)

- Provenance re-verified at tick start: HEAD 84f985cd (item-21 landed);
  no RULING_* newer than 2026-09-22; QUEUE_STATE.json lowest unblocked =
  item-22b (claim_order 22). Claimed.
- Landed tools/build_workbench_container.py: SINGLE self-extracting .py
  (round-11 FORMAT DECISION AT LANDING: .py over PNG-family — zero host
  deps to unpack; png_vfs.py already owns PNG transport for disks).
  Stdlib-only bootstrap; sha256 verifies EVERY payload file BEFORE any
  write (loud ERR:CHECKSUM rc=3, no partial root); PATH_CAP baked from
  the engine at build time (loud ERR:PATHCAP rc=2); unpacks into the
  IDENTICAL session-root layout as BK-25 stage_workbench; prints
  WORKBENCH_ROOT=<path>.
- Gate tests/test_item22b_workbench_container.py 7 legs (force-added
  past .gitignore). GREEN: 7 passed in 0.48-0.54s across three runs.
  RED-first: pre-landing builder absent -> ModuleNotFoundError at
  collection; post-landing module-moved-aside -> same collection error,
  restore -> 7/7 (gate re-discriminates). In-gate RED legs: N1a corrupt
  sha256 -> ERR:CHECKSUM, nothing unpacked; N1b long base -> ERR:PATHCAP;
  N1c truncated payload literal -> loud rc!=0.
- G3: in-shell pytest -q from the container-unpacked root = 13 passed.
  G4 context equivalence: container-unpacked files byte-identical to
  BK-25-staged files for the same manifest.
- Family regression: bk25 + item20 + item21 + bk22 + item11 = 37 passed;
  png_vfs (item-24) = 5 passed.
- Measured finding 1 (G3 RED): the BINDING constraint is the L1 shell's
  FS-window path budget, not PATH_CAP — root_name glyph_workbench_c22b
  under /tmp gives 49-char file paths -> ERR:PATH:path too long at first
  cat (constraint site experiments/glyph_interactive_shell.py:805
  path_cap = audio_path_addr - path_addr - 2; enforced
  glyph_l1_shell.py:262). Container default root_name shortened; OPEN
  engine question flagged, NOT fixed (engine-adjacent).
- Measured finding 2 (re-measured): pytest tmp_path bases are >90 chars
  and can NEVER satisfy PATH_CAP=48 — both staging contexts must use
  short mkdtemp bases (matches BK-25's authoring-time note).
- NOT proven: no GPU-image execution (host CPython, Phase-2 doctrine;
  interpreter deliberately not carried); PNG-family carrier alternative
  untested (round-11: "both formats satisfy the gate"); no WGSL twin;
  engine files untouched; protected assets untouched. Pre-existing
  dirty bm801/BM000 files NOT mine, not touched.
- Files: tools/build_workbench_container.py,
  tests/test_item22b_workbench_container.py, QUEUE_STATE.json
  (item-22b landed), CURRENT_TICKET.json (reconciled), ledger,
  RECEIPT_item22b_workbench_container.md.
- Next: claim queue has NO unblocked items (item-25 RESERVED, operator
  sign-off). Next tick: Phase-1c research IF no new supply/RULING;
  else take the queue.

### 2026-09-25 ~21:1x CDT — CLAIM QUEUE item 21 (builder stage-1 fixture synthesis) LANDED, commit a25ddbac (builder af3e62239ce2)

- Provenance re-verified at tick start: HEAD 7b861bcc (item-20 landed);
  QUEUE_STATE.json next-by-claim_order = item-21, unblocked. Claimed.
- Landed scripts/glyph_build/fixture_synth.py: deterministic
  synth/corpus/manifest fixture generator, invoked ONLY through the
  shell's contained python verb; refuses without GLYPH_L1_ROOT
  (rc=2, loud ERR on stderr) — writes only inside the session root.
- Gate tests/test_item21_fixture_synth.py 7 legs. GREEN: 7 passed in
  0.24s (exit 0, env -u GLYPH_L1_ROOT). RED: script moved aside ->
  7 failed in 0.17s; in-gate R1 corrupted-copy leg -> ERR:PYTHON;
  R2 env-absent refusal rc=2. Family regression: bk25 workbench +
  item20 + l1 personality = 31 passed in 18.18s.
- Measured finding 1 (probe_item21_turn_af3e.py): a SYMLINKED script
  cannot be executed from inside the shell — L1Session.resolve
  realpaths it to the repo tree OUTSIDE the session root -> ERR:PATH.
  Scripts must stage as CONTENT copies (matches the container-context
  contract). Refines the items-22+23 staging contract for scripts/.
- Measured finding 2: GLYPH_L1_ROOT takes precedence over the explicit
  root= kwarg (glyph_l1_shell.py:175) — a leaked exported var silently
  re-roots every shell in the process. Gates run under env -u;
  flagged as a multi-session hazard, not fixed (engine-adjacent).
- BK-25 N1c hazard re-confirmed by reading _stage_entries: content
  entries written after symlink entries with no same-path unlink —
  same-path content would write THROUGH the symlink into the repo
  file. R1's corrupted copy stages at a DISTINCT path.
- cat windowing honored: FILE_READ delivers 64 bytes/read, so G1 pins
  prefix equality (engine contract, disclosed; full-file cat is the
  known window limitation, unchanged).
- INCIDENT (disclosed): a stash-push failed (script untracked, not in
  git) but the follow-up `git stash pop` popped a STALE stash entry
  (d31c superseded 5-push rewrite) into the tree, conflicting with the
  LANDED minimal fix in tools/rv64i_to_glyph.py. Resolved by restoring
  HEAD's version of that file (a7200a28 minimal fix stands; verified
  byte-identical to HEAD). Stash entries remain on the stash list.
  No engine content changed by this lane; xv6 receipt untouched.
- NOT proven: no WGSL twin (nothing spatial); no engine/substrate
  files touched; container carrier is item-22b's supply; in-image
  execution deferred (Phase-2 doctrine, host CPython).
- Files: scripts/glyph_build/fixture_synth.py,
  tests/test_item21_fixture_synth.py (force-added past .gitignore),
  probes probe_item21_{staging,turn}_af3e.py, QUEUE_STATE.json,
  CURRENT_TICKET.json, ledger, receipt (below).
- Receipt: .builder_queue/RECEIPT_item21_fixture_synthesis.md.
- Next: CLAIM QUEUE — item 22b by claim_order among unblocked; item 25
  reserved pending operator sign-off.

### 2026-09-25 ~20:4x CDT — CLAIM QUEUE item 20 (shell-native swap) LANDED, commit this tick (builder af3e62239ce2)

- Provenance re-verified at tick start: HEAD 74e1ab64; work found
  IN-TREE but UNCOMMITTED from the 20:0x tick (timeout hit before
  landing). This tick: re-gated + fresh RED, then landed.
- Gate re-run GREEN: tests/test_item20_shell_native_swap.py — 9 passed
  in 11.25s, exit 0.
- Fresh RED leg (stash of experiments/glyph_l1_shell.py, then re-run):
  3 failed / 6 passed — L2 tr parity, L5b loud-refusal marker,
  L6 untouched-verbs. Stash popped; change restored; gate re-discriminates.
- Landed: grep+tr route through transpiled rv32i glyph binaries
  (GlyphRunner via _load_posix_program; session bytes as generated C
  literal in seed .data); loud refusals ERR:SHELLNATIVE:<verb> /
  ERR:NOENT; tr added to L1_VERBS; pipe producers scoped host-side
  (BK-24 write tile has NO ring saturation — faults at 25+ lines,
  measured in dbg_item20_budget_af3e.py; open engine work, disclosed).
  wc/head NOT swapped: 17+/24B report shapes exceed the 16-byte window.
- Receipt: .builder_queue/RECEIPT_item20_shell_native_swap.md (written
  by the 20:0x tick; its "QUEUE_STATE/CURRENT_TICKET updated" claim is
  only true as of THIS tick — the files were still item-24/stale
  until now).
- NOT proven: no WGSL twin leg; per-turn recompile ~1.7-4.65s (caching
  deferred); no in-guest execution; R1.4 WGSL convergence open.
- Files: experiments/glyph_l1_shell.py, tests/test_item20_shell_native_swap.py
  (force-added past .gitignore), receipt, dbg_item20_budget_af3e.py,
  QUEUE_STATE.json + CURRENT_TICKET.json (item-20 landed), ledger.
  tools/bare_metal_poc/rung8/bm801_align.py left dirty — belongs to the
  live BM000/dogfood lane (mtime 20:35), not this ticket.
- Next: CLAIM QUEUE — item 21 by claim_order among unblocked (21 < 22b);
  item 25 reserved pending operator sign-off.

### 2026-09-25 ~11:2x CDT — CLAIM QUEUE item 24 (VFS-1 png_vfs.py) LANDED (builder af3e62239ce2)

- Gate: tests/test_png_vfs.py 5 legs — ALL GREEN 5 passed in 4.69s
  (exit 0, run twice; RED legs: module-absent import exit 1 via stash,
  first full run 5 failed, mid-fix run 4F/1P, superblock-corruption
  e2fsck reject, magic-corruption loud PngVfsError). Receipt:
  .builder_queue/RECEIPT_item24_vfs1_png_vfs.md.
- Landed: tools/png_vfs.py (wrap/unwrap, 28B self-describing header,
  Hilbert block transport, RGB24 3B/px convention), tests/test_png_vfs.py
  (force-added past .gitignore), dbg_v1_hdr_af3e.py probe.
- Gate shape per PRE-VFS-1 RULING: mke2fs -> debugfs write 3 files ->
  wrap -> 2048x2048 PNG -> unwrap byte-identical -> e2fsck -fn clean ->
  3 files byte-exact; Hilbert mapping verified vs independent xy2d_ref;
  corrupted-magic legs loud. SPEC citation line present in receipt
  (fs/ext2/ + ext2.rst + magic.h:24, read 2026-09-25, impl ours).
- Geometry correction to the 09:0x addendum: 2048² RGB24 = 12,582,912 B
  (not 16.7MB); fixture disk = 12,581,888 B; mke2fs yields 12284 blocks
  (group rounding), measured in-gate.
- NOT proven: guest-side reads (VFS-2/3 reserved, operator sign-off);
  block_px>8 unexercised; no in-guest mount test. No engine/codec/WGSL
  files touched.
- Next: CLAIM QUEUE — item 20 (shell-native swap) is next by claim_order
  among unblocked items (20 < 21 < 22b); item 25 reserved.

### 2026-09-25 ~10:5x CDT — DEFECT-31c RESOLVED, committed a7200a28: SB/SH rs1==x30 base aliasing, minimal surgical fix (builder af3e62239ce2)

- Falsifier 1 verdict (trace, .builder_queue/dbg_d31c_trace_diff_af3e.py):
  the dirty rewrite's 4F/9P faults were CONTROL-FLOW, not memory — zero
  stores to the corrupted jump-target words; jalr landed mid-text (word
  1887 = `ADD r30 r3`). Falsifier 4 verdict (stash discrimination): HEAD
  gate 13/13 PASS but iso probe RED (sb base x30 stores nothing,
  mem[768]=0x0) — the rewrite traded a one-instruction aliasing bug for a
  broken register plan.
- Fix: reverted to HEAD lowering, added an rs1==30-only branch to OP_SB and
  OP_SH (address computed ONCE in r28, base pushed/popped; non-aliased
  sites byte-identical to HEAD). The rejected 5-push rewrite is preserved
  verbatim in .builder_queue/DEFECT31c_dirty_rewrite_snapshot.diff.
- Receipt: .builder_queue/RECEIPT_DEFECT31c_sb_sh_r30_alias.md. RED legs:
  dirty gate 4F/9P; HEAD probe t5base mem[768]=0x0. GREEN legs: iso sb
  0x41/0x42 + sh 0x1141/0x2242 byte-exact; xv6 gate 13 passed (31.72s);
  twins gh23+bk11+vol2 18 passed (61.22s); pre-commit hook's full
  glyph+transpiler differential suite 38 passed (64.85s).
- NOT proven / flagged: rs1==29 SB/SH second-address re-read (latent,
  unfixed, unmeasured — no gate scenario hits it); rs2==x27 value-read
  aliasing (parity with HEAD); WGSL twin unexercised — R1.4 convergence
  remains open. Probes/trace drivers committed under .builder_queue/.
- Next: DEFECT-31c closed; per the 8e36fb3c addendum, item-24 (VFS-1) is
  the confirmed next claim.

### 2026-09-25 ~10:2x CDT — DEFECT-31c takeover tick: lane-mask fix landed in tree but xv6 gate still 4F/9P — IN-FLIGHT, NOT COMMITTED (builder af3e62239ce2)

- Provenance re-verified: HEAD 8e36fb3c (addendum: item-24 confirmed next
  claim). The dirty `tools/rv64i_to_glyph.py` (+124/-42: OP_SB/OP_SH full
  r26..r30 save/restore rewrite) carries in-code comments "DEFECT-31c
  (2026-09-25, af3e takeover tick)" and probes
  dbg_d30_iso_{sb,sh}_base_va_af3e.py (09:38/09:39) +
  dbg_d31c_xv6_{min_repro,trace}_af3e.py (09:44/09:45) — a SELF-HANDOFF
  from an earlier tick of THIS job (af3e suffix), not a foreign lane.
  CURRENT_TICKET.json still says item-19 landed / next=item-20 — it was
  NOT updated for the 31c work; reconciled this tick.
- Measured at tick start (dirty tree): tests/test_rv64i_to_glyph_xv6_nano.py
  = 4 failed / 9 passed — ek1_bounded_user_store, ek2_syscall_boundary,
  go1_isolation_on_gpu[6]/[7], all `SpatialMisalignmentFault: PC.x=1953
  (or 1887) is not aligned to 4`. Baseline (stash discrimination): clean
  HEAD = 13/13 PASS in 31.94s. The dirty rewrite is the regression.
- Fix attempt 1 (landed in tree, tools/rv64i_to_glyph.py:1097): the SB
  `rs1==x30` fallback branch masked the byte lane with 2 (`LDI r29 2;
  AND r29 r28`) — the halfword mask copied from the OP_SH shape. Byte
  lane is addr&3; mask 2 mis-shifts lanes 1/3. Changed to mask 3.
- Post-fix measurement: isolated SB/SH base-va probes GREEN
  (dbg_d30_iso_sb_base_va_af3e.py: t5base+ctrl both mem[768]=0x41
  mem[769]=0x42 byte-exact; dbg_d30_iso_sh_base_va_af3e.py: 0x1141/
  0x2242 exact) — but xv6 gate UNCHANGED: same 4 failed / 9 passed with
  IDENTICAL fault PCs (1953/1887). The trap-scenario corruption rides a
  different path than the lane mask.
- Attempt budget spent (PHASE 4): tree left RED + in-flight, NOTHING
  committed. Do not merge this tree. Next tick falsifiers, cheapest
  first: (1) run the 4 failing scenarios under a glyph-line trace and
  diff the last executed store/jump against the clean-HEAD lowering;
  (2) test sb with NEGATIVE imm (LDI 0x%08x of imm&0xFFFFFFFF — engine
  LDI width ceiling?) and with rs1==x26 staged path (both new code paths
  the old lowering never exercised); (3) check whether ek1/ek2 fault
  handlers count pushed words (5 pushes vs old 2 — mepc/stack-shape
  assumptions in the handler skeleton); (4) if the rewrite is
  fundamentally unsound, revert to HEAD lowering + fix only the proven
  LBU/LHU DEFECT-30 shape and re-run the volume-2 gates.
- NOT done: no commit; item-20/item-24 untouched; no substrate writes;
  protected assets untouched; guest_state.json dirty (external monitor,
  not ours).

Owner: builder cron af3e62239ce2 (2m cadence, redirected 2026-09-21 per
Jericho's "make the builder work on this"). The 2h product-lane cron
b0f0eb15a225 is PAUSED — this lane is the sole executor. If b0f0eb15a225
ever fires again while this file says ACTIVE, that is a contention fault:
its tick must read this file, see ownership recorded here, and end silent.

Current rung: **ITEM 19 (coreutils volume port #2: grep/tr/tee/cut/sort) LANDED (merge 7ab567ec) —
DEFECT-30 resolved in worktree `defect30-lbu` (rv64i_to_glyph.py OP_LBU/LHU stack
leak and scratch aliasing fixed; -Wl,-N keeps .data/.bss contiguous in VPN 2 RAM
avoiding VPN 6 PTE_PIX canvas). Verification: test_coreutils_volume2.py 7/7 PASS;
twin gates test_gh23_libc_runtime.py (5/5) and test_bk11_coreutils.py (6/6)
all GREEN on merged main tree. Next rung: ITEM 20 (Shell-native swap).**

### 2026-09-25 ~09:20 CDT — item 19 landed: DEFECT-30 resolved & Coreutils Volume 2 merged (Antigravity)

- Work done in worktree `/home/jericho/projects/zion/projects/defect30-lbu` per AGENTS.md blast-radius protocol.
- Root causes resolved:
  1. `rv64i_to_glyph.py` OP_LBU/OP_LHU: Lowering sequence pushed 3 registers but popped only non-rd, leaking 1 stack word per LBU when rd in {r28, r29}. Furthermore, mask scratch clobbered rd. Fixed by balancing push/pop to exact scratch set and keeping mask scratch distinct from rd and rs1.
  2. `tools/glyph_gpt/coreutils_port.py`: Compiler register fencing `-ffixed-x28`..`-ffixed-x31` prevents GCC register allocation collisions with transpiler scratches. Linker flag `-Wl,-N` keeps `.data` and `.bss` contiguous after `.rodata` in VPN 2 (32-bit RAM) instead of page-aligning into VPN 6 (PTE_PIX 24-bit canvas where byte 3 was stripped to 0x00).
- Gate results:
  - `tests/test_coreutils_volume2.py`: 7/7 PASSED in 32.08s (all 5 tools x 3 fixtures byte-exact).
  - `tests/test_gh23_libc_runtime.py`: 5/5 PASSED in 5.91s.
  - `tests/test_bk11_coreutils.py`: 6/6 PASSED in 27.75s.
- Merged to `glyph-transpiler-autoloop` at commit `7ab567ec`.

### 2026-09-25 ~07:4x CDT — item 19 claimed: gate RED root-caused to transpiler LBU defect (DEFECT-30) (builder af3e62239ce2)

- HEAD re-verified 6c405773 at tick start; no RULING_* newer than HEAD;
  monitor fingerprint was FROZEN_STALLED_T1 (tracked_dirty=1: the vol2
  in-flight work + guest_state.json). Claimed item 19 (round-9 supply,
  unblocked since item 18 merged).
- Gate baseline: tests/test_coreutils_volume2.py = 4 failed / 3 passed
  (tee 3/3 + L0 green; grep/tr/cut/sort RED: 'halted: False' or wrong
  bytes). Twin gates on the same tree: test_gh23_libc_runtime.py +
  test_bk11_coreutils.py 11/11 PASS (defect is fixture-shape-conditional,
  not a general regression).
- ROOT CAUSE (measured, isolated repro):
  .builder_queue/DEFECT_30_lbu_scratch_stack.md —
  rv64i_to_glyph.py OP_LBU (line ~921) and OP_LHU (line ~1021)
  lowerings: when the LBU destination register is r28/r29 (the
  DEFECT-16c scratch guards' own lane/mask scratches), the sequence
  (a) leaks 1 word of the engine r31 stack per executed LBU (3 PUSH,
  2 POP) and (b) corrupts the extracted byte (mask LDI overwrites rd →
  every byte reads 0xff). Isolated: dbg_vol2_lbu_iso.py — `lbu t4,...`
  transpiles to PUSH:6/POP:4 + always-0xff. tee passes only because
  gcc picked non-scratch byte dests.
- Evidence probes kept: .builder_queue/dbg_vol2_{run,fullregs,exit,
  lbu_iso}.py; exploratory probes deleted.
- NOT done: no transpiler edit (engine-core file → worktree isolation
  required; this tick spent its budget on the descent); item 19 NOT
  landed; gate left RED by design; protected assets untouched; no
  WGSL leg (failing path is transpiler-side, no spatial component).

PREV rung: **BK-24 item 18 MERGED TO MAIN TREE 2026-09-25 ~02:0x CDT
(merge commit e9f9ca4b of branch bk24/rowfix-32col = worktree 1aef3eab).**
Main tree now carries the streaming write tile: branch-free append at
cursor mem[724] into ring [768,832), last-flush mirror kept at 718..721
(BK-11 guard live); libc write() chunks into 16-byte frames (one
ECALL/frame; engine marshals only a7/a0/a1); bake+loader at
cols_instrs=32 (row-ceiling root cause); ABI 0x1A->0x1B, tail id 26->27.
Post-merge re-verification ON THE MERGED TREE:
tests/test_bk24_streaming_write.py 5/5 PASS,
tests/test_gh23_libc_runtime.py + test_bk11_coreutils.py 11/11 PASS.
RED leg (re-shown post-merge): cursor pinned to ring base
(`LDI r11 768` replacing the cursor `LD`) -> 3 RED
(L1 tile-shape, L2 second flush overwrites first — ring[0:8]==b'BBBBBBBB',
L3 only 16 of 64 bytes); restore -> 10/10 GREEN.
Stale main-tree dirty BK-24 copies (16-col partial, mtimes 01:32) were
STASHED, not merged: stash@{0} = tracked four-file copy
(test_gh23_libc_runtime.py, baker.py, libc_runtime.py, autoatlas.py;
autoatlas was byte-identical to the branch, the rest differed only in
the 0x1A/26/16-col vs 0x1B/27/32-col landing values);
/tmp/bk24_stale_untracked_test.py = stale untracked gate copy (asserted
old frame ABI; the merged gate's frame-ABI amendment supersedes it).
**CONTENTION WARNING RESOLVED** (supersedes the pre-merge warning in the
PREV entry below). Next tick: pick next work per PHASE 1/1b (claim queue
/ backlog), re-verifying HEAD first — parallel sessions land rungs
mid-flight.

PREV rung: **BK-24 item 18 (streaming sys_write) LANDED 2026-09-25
~01:5x CDT — in WORKTREE `~/zion/worktrees/bk24-rowfix` commit 1aef3eab
(branch bk24/rowfix-32col); merged to main the following tick.**
Streaming write tile: branch-free append at cursor mem[724] into ring
[768,832), last-flush mirror kept at 718..721 (BK-11 guard live); libc
write() chunks into 16-byte frames (one ECALL/frame; engine marshals
only a7/a0/a1); bake+loader at cols_instrs=32 (row-ceiling root cause);
ABI 0x1A->0x1B, tail id 26->27. Gate tests/test_bk24_streaming_write.py
5/5 + test_gh23_libc_runtime.py 5/5 (worktree); RED leg: old
fixed-window tile leaves ring zero + flush1 lost -> amended L2 rejects
(probe_bk24_red_leg.py). Gate-authoring defect fixed in-landing: L2's
original assert targeted ring bytes 8..16 (frame-1 pad), not words
772..775 as its docstring said. Receipt:
.builder_queue/RECEIPT_BK24_item18_streaming_write.md.
**CONTENTION WARNING: main tree holds a STALE 16-col partial BK-24 copy
(dirty, mtimes 01:32:28, gh23 3-failed there — ABI 0x1A, empty stdout
on the C-suite). Do NOT merge main's copy over the worktree; land the
worktree branch and discard the stale main-tree dirty state.**
`build_dispatch_shell` gains runner_path/child_path/child_out_path (all-or-
none, loud ValueError on partial sets); 'x <child.npy>' dispatches through
the item-11 grammar into the SE021 RUN2 branch (rc!=0 -> RUN_DENIED_MARKER,
rc==0 -> FILE_READ child_out + PRT). Child path from the LINE PAYLOAD;
runner/child_out are Region-B constants above the plain shell's max_word
(no existing address changed); FS-window budget assert untouched. Engine
lines: none. Gate tests/test_bk21_entry_exec.py 6/6 (RED-by-stash 6 failed
pre-landing; GREEN 6/6 + family 111 at HEAD 01f11374). L3 finding: the
SE021 gate's '*' neuter is VACUOUS (_get_run_allowlist drops non-absolute
entries -> '*' == deny); BK-21's L3 flips deny->allow with a real grant
instead. Receipt: .builder_queue/RECEIPT_BK21_entry_exec.md. Disclosure:
no WGSL twin leg on the promoted image (RUN2 is foreign to the shader
threat model per 0x07/0x12 precedent; unpinned); Phase-2 claim only.

PREV rung: **L4-DESKTOP LANDED 2026-09-24 ~10:3x CDT (round-8 item 17);
receipt + code COMMITTED ~10:4x CDT follow-up tick** (prior session
exited before committing — the "LANDED" line was briefly backed only by
untracked files; follow-up tick re-ran the full gate arc RED+GREEN and
landed code + RECEIPT_L4_desktop.md in one commit so HEAD backs the
ledger).
experiments/glyph_desktop_env.py: tabbed consoles (own GlyphL1Shell +
TextConsole ring per tab), glyph-native editor (I/O THROUGH the GPU's
FILE_READ/FILE_WRITE arms), launcher (every L1 verb + edit), JSON session
save/restore. Gate tests/test_l4_desktop.py 11/11 (RED-first ImportError
pre-landing + N1 neutered-image leg + N2 corrupted-expectation leg);
family 101 passed; dogfood 7/7. Receipt: .builder_queue/RECEIPT_L4_desktop.md.
Tk/pixel legs: operator-eyes PENDING (GUI-receipt pattern).
Landing-time defect fixed in-session: restore() minted a fresh session root
(cat -> ERR:NOENT after restore); session root now persisted + restored.

PREV rung: **L3 FULLY CLOSED + Contained Python + BK-22 (multi-file) + BK-23 (CI Dogfood Gate) LANDED 2026-09-24.**
- Python execution in shell (`c0931a7d`): `python -c`, `python script.py`, `python < file`, and `echo ... | python` with quote-aware delimiter protection (`_split_outside_quotes`) and `$?` exit status propagation. Gate: `tests/test_l1_shell_personality.py` (legs W8, W9) 15/15 green.
- BK-22 (`017cebc8`): Multi-file coreutils arguments (`cat f1 f2`, `wc f1 f2` with total row and in-place `ERR:NOENT:` reporting). Gate: `tests/test_bk22_multifile_coreutils.py` 6/6 green.
- BK-23 (`876a2e9c`): Continuous autonomous LLM dogfooding gate in CI, closed-loop monitor trigger (`queue=1`, `REPAIR_PENDING`) and auto-resolution (`queue=0`, `CLEAN`), execution budget <3500ms (~320ms achieved). Gate: `tests/test_bk23_dogfood_ci_gate.py` 4/4 green.

L3 (PIPES AND PROCESS CONTROL) and all pre-desktop prerequisites are now FULLY CLOSED:
  1. `>` truncate redirection on echo (49183d48)
  2. `|` pipe with window backpressure (1107474b)
  3. `<` input redirection for stdin shims (0b92511a)
  4. `&&`/`;` command sequencing, short-circuiting, and `$?` exit status (171d5f4e)
  5. Contained Python runtime in shell with quote-aware delimiters (c0931a7d)
  6. BK-22 multi-file coreutils arguments (017cebc8)
  7. BK-23 continuous autonomous LLM dogfooding CI gate (876a2e9c)

NEXT: **(round-9+ supply items 18-23 from the seat lane are the named queue —
18 (BK-24 streaming write) first per its own "THIS UNBLOCKS EVERYTHING
ELSE" line; BK-21 landed 2026-09-24 ~11:2x between L4 and item 18.)**

### 2026-09-25 ~01:4x CDT — items 22+23 (BK-25 Workbench staging) LANDED + python-verb env defect FIXED (builder af3e62239ce2)

- HEAD re-verified 78a8c6a5 at tick start; no RULING_* newer than HEAD.
  Item 18 (BK-24) is ACTIVELY OWNED by the parallel session in worktree
  `~/zion/worktrees/bk24-rowfix` (fix option (a) cols_instrs=32 applied
  there, probes 00:39-00:43 CDT) — NOT touched, NOT duplicated. Item 19
  depends on 18. Per the round-10 addendum, items 22+23 are an
  independent track — claimed the merged item 22+23 (BK-25).
- Landed tools/stage_workbench.py (stage_workbench + unpack_manifest:
  short-path root under PATH_CAP, layout contract w.dat+bin/+scripts/+
  tests/, import-root contract experiments/tools/src, /tmp/gwb_* default
  base) and tests/test_bk25_stage_workbench.py (7 legs). **G3 is the
  Stage-2 gate: `python -m pytest -q` AS A SHELL TURN passes 14/14**
  (hermetic BK-22 + item-11 fixtures). RED-first: module-absent
  collection error pre-landing; N1a long-root refusal, N1b layout-assert
  RED, N1c corrupted staged copy -> G3 FAILS (copy context — cannot
  reach repo files).
- LANDING-TIME DEFECT (8-line fix, experiments/glyph_l1_shell.py:964):
  _run_python_proc built the contained env (GLYPH_L1_ROOT +
  session-first PYTHONPATH) but never passed it to subprocess.run —
  every `python` turn since c0931a7d silently ran with the PARENT env,
  i.e. uncontained. Found by G3 (shell-turn pytest RED while the
  identical env-passing call was GREEN); discrimination shown by
  stashing the fix: 1 failed/6 passed -> restored: 7 passed.
- Gates at landing: bk25 7/7; family 79/79 (bk25+l1+bk22+item11+l3+l4);
  bk23 dogfood CI gate 4/4; live dogfood 8 PASS/0 FAIL exit=0.
  Receipt: .builder_queue/RECEIPT_BK25_stage_workbench.md. What the PASS
  does NOT prove: the one-file container carrier (payload packing is
  item 23's format decision, deferred), GPU-image pytest (host CPython
  Phase-2 substrate per round-11 doctrine), WGSL twin (nothing spatial).
- Incident receipted: N1c's first form mutated a staged symlink and
  wrote through to the repo test file; restored from HEAD in-session and
  the leg rewritten to the copy context (receipt "Discipline notes").
- NOT done: item 18/19 untouched (bk24-rowfix's surface); no engine
  files touched; no WGSL twin; protected assets untouched.

### 2026-09-25 ~01:1x CDT — item 18 (BK-24): ROOT CAUSE MEASURED — packed-PC row-field truncation (builder af3e62239ce2)

- HEAD re-verified 976b1c50 (this lane's own ticket commit); no RULING_*
  newer than HEAD; dirty BK-24 files untouched (BM801's in-flight work,
  mtimes 23:28). Measurement-only tick: 8 falsifier rounds, 6 engine
  legs, all in .builder_queue/ probes.
- Defect ELIMINATED: tile (ticket legs), write() presence CONFIRMED
  causal (round 1: trivial pass-through write GREEN 3266 steps exit 10 vs
  real wrapper RED fault 32820), static BSS frame, qsort codegen (round
  3: opcode streams IDENTICAL), size shift (round 4: +20-instr dead fn
  GREEN), frame/tail-call shape (round 2), fn-ptr call site (round 5),
  auipc+jalr-ra (round 6).
- ROOT CAUSE (rounds 7-8, measured): the wrapper grows the unit by ~111
  glyph instructions → 44 extra :pc_ pointer-table entries → RED build's
  max spliced cell 4344 = row 271 > 255, with 70 entries at row > 255.
  The packed PC is (row<<16)|col in a 24-bit pixel word with an 8-BIT
  row field (DEFECT-7's ceiling, GH-23 record) — rows ≥ 256 TRUNCATE.
  GREEN build max row 242: under the limit, which is why old libc is
  green. Receipt: .builder_queue/RECEIPT_BK24_ROOT_CAUSE_row_truncation.md
  (fix options a/b/c cheapest-first; LOCKED loader/bake constant pair —
  NOT landed, worktree isolation + sign-off required).
- NOT done: no fix attempted (engine files are the parallel lane's
  in-flight surface); BK-24 gate (tests/test_bk24_streaming_write.py)
  still NOT green — item 18 NOT landed. Next tick: re-verify HEAD; if
  the tree is quiet, land fix option (a) (cols_instrs 16→32 in
  libc_runtime.py libc bake + the test loader's matching constant) in a
  WORKTREE per AGENTS.md, with RED-first evidence from round 1's probe.

### 2026-09-24 ~23:4x CDT — item 18 (BK-24) IN FLIGHT: defect isolated, ticket filed (builder af3e62239ce2)

- Tree state: HEAD a2220d47, BK-24 dirty work uncommitted
  (tests/test_gh23_libc_runtime.py + tools/glyph_gpt/{libc_runtime,baker,
  autoatlas}.py). Parallel BM000 ladder lane is ACTIVELY committing to this
  repo (23:27/23:34/23:39) — re-verify HEAD before acting.
- Measured: dirty tree REGRESSES tests/test_gh23_libc_runtime.py (5-leg
  suite fails; HEAD passes it 5/5). Bisect (5 legs, ticket has the table):
  OLD libc C + NEW stamped tile = GREEN (cursor 772, window `n=10,20!C`)
  → the BK-24 streaming-write TILE is exonerated for the landed fixtures;
  the defect rides the NEW LIBC_C write() wrapper / shifted C layout.
- Root-caused to the qsort comparator INDIRECT-CALL RETURN path
  (entry seed mem[2048]=0xB9000B → :cmp_ilv_unused at spliced cell 2971 is
  CORRECT; first cmp call round-trips; the SECOND comparator RET pops a
  stale PC into the prologue at cell 206 → OOB fault word 32820).
  Eliminated (measured): pointer-seed values, table/heap overlap,
  gp-relax windows, rect geometry (leg 2).
- Ticket with full tables + cheapest falsifiers:
  .builder_queue/DEFECT_BK24_GH23_comparator_return_20260924.md
- NOT done this tick: no fix attempted (tree was moving under a parallel
  lane mid-investigation); tile streaming multi-flush path still untested
  at runtime; BK-24 gate (tests/test_bk24_streaming_write.py) NOT run to
  green — item 18 is NOT landed. Next tick: re-verify HEAD, then falsify
  the wrapper-presence hypothesis (qsort-only + write wrapper removed)
  before touching anything.

### 2026-09-24 ~10:3x CDT — ROUND-8 item 17 (L4-DESKTOP) LANDED (builder af3e62239ce2)

- Mailbox check: STATUS ACTIVE; no RULING_* newer than 2026-09-22 20:38;
  monitor delta = this repo's own HEAD advance (c0931a7d python verbs,
  017cebc8 BK-22 — parallel-session landings, neither binds new work).
  Ledger re-read at tick start per the parallel-session rule.
- Claimed L4-DESKTOP (SUPPLY_ROUND8.json item 17): desktop environment.
  Landed experiments/glyph_desktop_env.py — the HEADLESS desktop core:
  DesktopConsole (own GlyphL1Shell + own TextConsole ring per tab),
  DesktopEditor (open/save through the GPU's FILE_READ/FILE_WRITE arms —
  never a host file handle), DesktopLauncher (every L1 verb + edit,
  runnable in its console), DesktopEnv (tab lifecycle + JSON session
  save/restore). The Tk surface upgrade that wraps this core is the
  operator-eyes leg, held PENDING per the GUI-receipt pattern.
- Gate tests/test_l4_desktop.py 11/11 (RED-first: collection
  ImportError on the absent module pre-landing; plus two in-gate
  discriminating legs — N1 neutered-image: swapping the dispatch image
  for build_shell() (no 0x03/0x04 arms) makes editor save produce NO
  file, proving the I/O runs through the GPU's FILE_WRITE body, not a
  host shim; N2 corrupted-expectation leg).
- Landing-time defect found + fixed in-session: restore() minted a FRESH
  L1Session root, so files saved before save_session were unreachable
  after restore (measured: cat memo.txt -> ERR:NOENT). Fix: the session
  root is persisted in the payload and restored. This is exactly the
  round-8 success criterion's persistence leg.
- Regression: lane family 101 passed (l4 + l1 personality + l3 pipes +
  l2 files + bk22 + text console + item-11 grammar); continuous dogfood
  7/7 passed in 609.8ms post-landing.
- Receipt: .builder_queue/RECEIPT_L4_desktop.md. What the PASS does NOT
  prove: the Tk window (pixel/layout legs PENDING operator eyes), the WGSL
  twin of the desktop surface, and any multi-user/network capability
  (documented non-goals).
- NOT done: glyph_desktop.py untouched (upgrading it to consume
  DesktopEnv is the operator-eyes follow-up); BK-21 untouched;
  engine sources, twin sources, protected assets: untouched.

PREV rung text (L3 sub-step 3, landed 0b92511a): `<` splits before verb dispatch; `_lt` resolves the
source through session.expand (escape → ERR:PATH), refuses missing
sources ERR:NOENT BEFORE the command runs, refuses empty segments and
double-`<` with the grammar marker, feeds raw file bytes to the
stdin-capable shims (wc 3-column stdin form, head/tail -n, grep).
Receipt: .builder_queue/RECEIPT_L3_lt_redirect.md.


PREV rung text (L2-FILES sub-step 4, landed a47043dd): `>>` append for
shell verbs `write`/`echo` (flag/infix/redirection forms), `rm -f`
quiet, RED-first probe_l2_append_red.py 3 failing legs → 17/17 +
family 59 passed. Receipt: RECEIPT_L2_files_append.md.

PREV sub-step 3 (landed f9d6ad95): mkdir/rmdir under allow-scoped root (shell verbs),
POSIX refusals EEXIST/NOENT/NOTDIR/EBUSY/RMDIR:errno, irremovable session root.

PREV sub-step 2 (landed 74b746c3, receipt commit cd56a946): files/ls
listing served by SYSCALL_FILE_LIST 0x13 — baked LDI/SYSCALL r9 0x13/
HALT program, own-pixel dir stamp, rc=entry count, -1→ERR, NO host
os.listdir fallback.

PREV sub-step 1 (landed 8afbb69a, receipt commit c37ad1c2): ls -l
columns (size ISO-mtime name) over the sorted listing, host-shim side.

PREV rung text (BK-15 item, landed e18312c8): Python 0x13 arm:
GLYPH_FS_ALLOW-rooted enumeration
(0x07/0x12 containment model, deny-by-default when unset), NUL-separated
sorted names into RAM dest, whole-name truncation, entry count in rd.
Twin: 19u EXCLUDED from the 16u..255u bridge (TICKET_ITEM8 precedent —
unqualified bridge was a false listing-success returning 0); twin -1 is
the NORMATIVE contract, measured on the LIVE GPU (wgpu) this session.
Spec `<!--ABI 0x13>` block + convention lines landed; rot-guard surface
pins extended, bridge-exclusion anchor pins BOTH 18u and 19u.
Gates: dedicated tests/test_bk15_file_list.py 11/11 (RED-first
9F/2P on the stashed pre-landing tree); rot-guard 28/28 (RED-first
8F/20P pre-sync); WGSL triple-sync, pillar23 parity CI, dispatch/grammar/
L1 shell/BK-2/GH-18/GH-6/ISA/SMODE/glyph-on-glyph/syscall-integration
regression family green (74+33+33+26+10 passed); pre-commit hooks ran
the 38-test differential suite + 8-case parity corpus. Receipt:
.builder_queue/RECEIPT_BK15_file_list.md.

### 2026-09-23 ~23:5x CDT — (superseded supply-wait text, kept for history)
ROUND-8 queue-jump item BK-18 (sharded suite runner) LANDED at 19b0d2a4 +
9f28685f; receipts and partial-suite numbers
in RECEIPT_BK18_sharded_suite_runner.md. BK-18 RESUME LIST EXECUTED
2026-09-23 ~23:45 CDT: remaining 35 shards re-run via
SUITE_RUN_bk18_resume_tail.md — 261 passed / 2 failed / 2 skipped; both
fails dispositioned (test_wgsl_validation.py is a script, not a pytest
module — pre-existing classification artifact, 0 tests collected;
test_l2_bounded_coverage_tests_root flaked once under cgroup load,
passed 4/4 re-runs incl. through the runner). Runner fix
BK18-RESUME-PATHFIX landed 7c0a0b98 (bare filenames resolve under
tests/; RED+GREEN+exit-2 legs in the commit body). COMBINED SUITE
STATUS (262 + 35 = 297/297 shards): passed=2119 failed=18 skipped=13,
with the 18 known failures named in SUITE_RUN_full_sharded.md FAILING
list — triage remains open as an L2-adjacent supply item (item 15
per SUPPLY_ROUND8.json order).**

### 2026-09-23 ~11:5x CDT — PHASE 1c RESEARCH tick: SE021 'x' exec unreachable from the human shell, BK-21 filed (builder af3e62239ce2)

- (Detail mirrored in Current rung above; receipt
  .builder_queue/RESEARCH_entry_surface_exec_gap.md.)

### 2026-09-23 ~13:1x CDT — (superseded rung text below; kept for history) ROUND-7 item 13 (BK-19 font atlas) LANDED:
tick. The 10 missing printable-ASCII glyphs `[ \ ] ^ _ ` { | } ~` added
to tools/vga_font_8x16.py as canonical IBM VGA ROM rows, extracted
programmatically from the in-tree kernel font
(~/projects/zion/linux-riscv/lib/fonts/font_8x16.c, glyph index ==
ord(char); all 10 row-sets asserted byte-identical by the gate at every
run). Existing 85 glyphs untouched; collision check: all 95 bit patterns
unique (decode is exact-match). Coverage numbers bumped to 95
(glyph_text_console.py:19-22, font header). Gate: RED-first 5 failed/
3 passed on pre-landing tree 12db395a (incl. live defect: WGSL twin band
decoded `?code??sample?`), stash-discrimination RED (fix stashed → RED
returns), GREEN 8/8, console+atlas 19 passed, extended family
74 passed (console/grammar/dispatch/bk7/shells/isa_v2/echo/4 WGSL parity
suites/interactive shell). Live batch pipe
`e [code]{sample} ~ ^_|` → exact decode, exit 0 (output/bk19_live_pipe.py).
Receipt: .builder_queue/RECEIPT_BK19_font_atlas.md. One disclosed
test-hygiene edit outside the receipt's engine scope:
tests/test_glyph_text_console.py:72-80 — the pre-existing '?'-leg fed '['
(now IN the font); ?-substitution intent preserved with '€', old assert
would have been permanently wrong post-landing. Queue now EMPTY; next
planned supply: DTF-4 (BK-11 coreutils), then BK-18 (sharded runner).**

### 2026-09-22 ~23:2x CDT — PHASE 1c RESEARCH tick: the stranger doc never
mentions the interactive shell (0 mentions in docs/), BK-20 filed (builder af3e62239ce2)

- Trigger check: STATUS ACTIVE, CLAIM QUEUE EMPTY, no RULING newer than
  HEAD 73b371a9 (newest RULING mtimes 20:38, pre-landing), monitor CLEAN
  queue=0. One research item per the standing directive.
- Question: the day-1 verdict was "no user surface exists yet"; the surface
  has since LANDED (item-9 repoint + DTF-2 console; live pipe
  `printf 'e hello\nquit\n' | python3 experiments/glyph_interactive_shell.py`
  → dispatch echo + band PNG, exit 0, re-verified this tick). Can a stranger
  FIND it? Measured: **`grep -rn 'glyph_interactive_shell' docs/` → 0
  matches**; START_HERE (0), ARCHITECTURE (0), PRODUCT_ROADMAP (0) vs old
  ROADMAP.md 4. The R5.2 doc offers 2 entry points, both non-interactive
  (installer fleet demo, glyph_run on a checked-in example). The one human
  entry surface is unreachable from the doc chain, and the R5.2 gate checks
  truth of what's written, not coverage (test_r52_stranger_doc.py:80 — a
  missing section passes green).
- Filed `.builder_queue/RESEARCH_stranger_doc_shell_gap.md` +
  GLYPH_BACKLOG.md row **BK-20** (doc-only: route the shell through
  START_HERE; gate tests/test_bk20_stranger_doc_shell.py L1–L5 incl. a live
  executable-truth leg re-using the R5.2 check_pairs machinery; prereqs
  none).
- Honesty: research only — no doc/gate/engine line touched; numbers are
  structural grep counts + one live shell run (exit 0); no floors/rule-1
  citation triggered. Priority call ("highest-value remaining doc gap")
  labeled impression-not-datum, sourced to R53_USE_LOG.md:24 being the only
  real-user friction datum in the tree.
- Next: supply-wait — R5.3 use friction, a Jericho directive, or a ruling;
  research tick only if a NEW researchable question exists.

### 2026-09-22 ~23:0x CDT — PHASE 1c RESEARCH tick: full suite unrunnable in the builder cgroup (deterministic OOM), BK-18 filed (builder af3e62239ce2)

- Trigger check: STATUS ACTIVE, CLAIM QUEUE EMPTY, no RULING newer than
  HEAD 1e56204e (newest RULING mtimes 20:38, pre-landing), monitor CLEAN
  queue=0. One research item per the standing directive.
- Question: can this lane run its own full pytest suite (2122 tests /
  327 files at HEAD 1e56204e, collect-only) to completion? Measured answer:
  NO — 3 independent attempts (21:52, 22:04, 22:11), each killed by the
  kernel's memory-cgroup OOM at ~48–51% progress; `journalctl -k` shows
  python anon-rss at kill = 4,170,704 / 4,172,276 / 4,172,420 kB (three
  values within 0.04% — a hard ceiling, not chance). Host had 31 GB
  available; the limit is the Hermes worker cgroup's.
- Shard controls: per-file / few-file runs complete fine (66, 87, 61, 43,
  37, 22, 17, 5, 12 passed across named shards this tick) — the ceiling is
  cumulative memory in one process, not any single file.
- Environment defect found + fixed in-session (venv-only): reedsolo
  declared at requirements.txt:9 but absent from .venv —
  tests/test_pixel_lm_audio_roundtrip.py was 1/5 (4 ImportError fails via
  src/codec/phy_ecc.py:91) at HEAD until `.venv/bin/pip install
  'reedsolo>=1.7.0'` → 5/5 passed in 0.13 s (re-run after install).
- Filed `.builder_queue/RESEARCH_suite_oom_ceiling.md` +
  GLYPH_BACKLOG.md row BK-18 (sharded per-file suite runner; gate
  tests/test_run_suite_sharded.py L1–L4 incl. a killed-shard RED leg and
  an RSS-flatness leg; prereqs none).
- Honesty: research only — no engine/tool code landed; failing-test NAMES
  beyond the 4 reedsolo ones unknown (dot-level `-q` runs, `--tb=no`);
  no floors citation triggered (no rate/ratio claimed; kernel-logged RSS
  + structural counts only). The 4.17 GB ceiling is measured for THIS
  lane's cgroup, not claimed host-wide.
- Next: supply-wait — R5.3 use friction, a Jericho directive, or a
  ruling; research tick only if a NEW researchable question exists.

### 2026-09-22 ~21:3x CDT — P2.5 CLOSED: agent-use pre-verification receipt FILED (builder af3e62239ce2)

- Mailbox check first: HEAD 939391d5 is this lane's own floor-exit
  landing (21:06); no RULING_* newer than HEAD (newest mtimes 20:38);
  monitor CLEAN queue=0; STATUS ACTIVE. One active ticket per the
  amendment's two-receipt exit: RECEIPT_DTF_agent_use.md.
- GREEN leg at HEAD 939391d5, this tick, real exits:
  `.venv/bin/python .builder_queue/transcript_dtf_floor.py` → 14/14 PASS,
  exit 0 (T0 blank sentinel; DTF-1 echo/disk-bytes/round-trip/speak
  15876@44100→`b' speak me'`/`ERR:UNKNOWN_CMD`; DTF-2 band decode
  glyph-side incl. `ERR:UNKNOWN?CMD` faithful record + mutated-band
  refusal; DTF-3 BK-7 subprocess 2 passed; DTF-4 BK-11 subprocess 6
  passed; always-echo mutation discrimination).
- RED leg (rule 4), this tick: corrupted round-trip expectation →
  `[FAIL] DTF-1 L4`, TRANSCRIPT FAIL, exit 1. Throwaway copy deleted;
  landed transcript untouched.
- Filed `.builder_queue/RECEIPT_DTF_agent_use.md` with the amendment's
  binding wording verbatim in force: CORRECTNESS only, NEVER usability;
  day-2 R5.3 operator entry remains the sole usability artifact; 30-day
  clock untouched, no manufactured entries.
- Honesty: no rate claims → floors N/A; single host/process; WGSL path
  not exercised by the transcript; BK-7/BK-11 internals trusted to their
  own standing gates + receipts, only exit codes re-verified here.
- Next: P3 per PRODUCT_ROADMAP.md (mailbox-first read at next tick).

### 2026-09-22 ~21:2x CDT — FLOOR EXIT: end-to-end floor transcript LANDED (builder af3e62239ce2)

- Mailbox check first: HEAD beff1abe is this lane's own DTF-4 landing
  (20:51); no RULING_* newer than HEAD (newest mtimes 20:38, pre-landing);
  monitor CLEAN queue=0; STATUS ACTIVE. Per the ledger's standing "next:
  floor-exit artifacts", claimed the floor transcript (RECEIPT_DTF_floor.md).
  The agent-use receipt (RECEIPT_DTF_agent_use.md) is a SEPARATE artifact
  per the amendment's two-receipt exit — next tick, one step per tick.
- Deliverable: `.builder_queue/transcript_dtf_floor.py` (NEW, re-runnable,
  one command/one process): T0 blank-sentinel band decode (empty) BEFORE
  any turn; ONE dispatch-shell instance, 5 turns — `e build floor`→
  `' build floor'`; `w cat dog`→disk `b' cat dog'` byte-exact; `r`→
  round-trip; `s speak me`→WAV 15876 @44100, decode `b' speak me'`;
  `z bogus`→`ERR:UNKNOWN_CMD`; DTF-2 band decode glyph-side of the SAME
  session's PRT stream; composed observation + PNG persisted; DTF-3 binding
  gate subprocess 2/2; DTF-4 binding gate subprocess 6/6 (wc green, no
  waiver); mutation RED (always-echo echoes verbatim, marker absent).
  GREEN exit 0.
- RED leg (rule 4): corrupted expectation (read round-trip → " cat cow")
  → `[FAIL] DTF-1 L4`, TRANSCRIPT FAIL, exit 1. The transcript
  discriminates; it cannot pass vacuously.
- Landing defects kept (disclosed): (1) first draft hard-coded ASCII
  expectations — the machine proved them wrong twice: `_` is absent from
  the VGA atlas (band shows `ERR:UNKNOWN?CMD`) and AUDIO_OUT PRTs nothing
  (speak turn = empty band line). Fixed by deriving expectations from the
  font's coverage + the actual PRT stream. (2) The font-coverage gap is
  pre-existing (RECEIPT_DTF2_text_console.md) but now USER-VISIBLE: the
  floor's most important error string displays with a hole. NOT fixed
  here (atlas extension out of receipt scope) — candidate queue supply.
- Honesty: batch/pipe mode only, no human at a tty; glass-TTY renderer,
  no twin-side rendering claim; DTF-3/4 legs via their standing pytest
  gates in subprocess; no WGSL twin leg in the transcript itself (each
  row's own gate carried its twin legs); no rate claims → floors N/A.
  Per the amendment's binding wording this receipt certifies CORRECTNESS
  ONLY — never usability; the operator's day-2 R5.3 entry remains sole
  usability authority.
- NOT done: RECEIPT_DTF_agent_use.md (next tick); PRODUCT_ROADMAP P2.5
  status line updated this commit; P3 untouced.

### 2026-09-22 ~21:0x CDT — DTF-4 done: BK-11 gate regression root-caused + repaired, 6/6 GREEN (builder af3e62239ce2)

- Mailbox check first: no RULING_* newer than HEAD (newest 09-21 14:59);
  monitor CLEAN queue=0; HEAD re-verified 2090c163. Per the ledger's
  standing "next: DTF-4", claimed DTF-4.
- NOT a measurement tick: the binding gate was RED at HEAD, and worse
  than its committed 09-12 state (4 failed/2 passed vs 5/6-then-wc).
  Repair before claim.
- Symptom: cat/echo/wc/head 0/3 fixtures, OOB store fault_addr≈0xFFFFF80C
  ~2800 steps in, stdout empty; cmp 3/3 green.
- RCA: r3(gp)=0 in the fault dump → DEFECT-9 contract
  (test_gh23_libc_runtime.py:388 seeds gp from parse_elf's table BY NAME)
  unfulfilled → bisect (predicate [cat], range 564a05af..HEAD) pinned
  6605f41a (R2.3, LANDED-PENDING-REVIEW): its parse_elf junk filter
  `st_shndx not in (0, 0xFFF1)` excluded ALL ABS symbols, including
  __global_pointer$. R2.3's own gate couldn't see it: freestanding "no
  libc" programs never touch gp-relative small data. BK-11 wasn't in any
  standing regression set — a gate nobody re-runs is not a gate.
- Fix: one hunk, tools/rv64i_to_glyph.py parse_elf symbol loop — FILE
  symbols excluded by (ABS + st_type==FILE); ABS NOTYPE (gp) kept; UND,
  typed-precedence, $-mapping logic unchanged.
- Gate legs, this process: RED pre-fix 4 failed/2 passed at HEAD;
  stash-discrimination RED ([cat] 1 failed with fix stashed); GREEN
  6 passed post-fix (wc green — DEFECT-18(a) at 11fe1acd resolved the
  09-12 blocker, verified by run not assumed); blast radius: glyph_cc 7,
  gh23 7, 20 transpiler files 45, gh21/gh26/bk14 17, arc SEED=42
  394 passed 1 skipped rc=0 71.34s (output/arc_lega_seed42_2090c163.txt).
- Honesty: fixtures ≤16 B (16-byte stdout-window tool contract, per spec
  — proves the toolchain story per tool, not arbitrary coreutils); single
  host; no rate claims → floors N/A; glyph_dispatch transpiler copy is a
  frozen snapshot, left untouched (flagged in receipt); R2.3 review status
  unchanged (this repairs collateral, does not rule).
- NOT done: floor-exit transcript + agent pre-verification receipts
  (amendment) remain open; DTF row promotion landed this commit.

### 2026-09-22 ~20:4x CDT — DTF-3 done: BK-7 measured at HEAD + twin boundary truthed (builder af3e62239ce2)

- Mailbox check first: no RULING_* newer than HEAD (newest 09-21 14:59);
  monitor CLEAN queue=0; STATUS ACTIVE. Round-5 queue empty → per the
  ledger's standing "next: DTF-3" and the ratified P2.5 order, this tick
  claimed DTF-3.
- Same shape as DTF-1: the binding gate (tests/test_bk7_fs_grow.py) has
  existed since 09-11 (153b5edb, with its own receipt + RED-first arc).
  Claimable work = measure at HEAD + truth the twin boundary + receipt +
  promote. No FS code changed.
- Gate at HEAD: bk7 2/2 PASSED; family (defect_d RAM handlers + gh20 FS-v2
  + pillar21 rot-guard + bk7) 67 passed 0 failed.
- Twin boundary: amendment premise ("FS handlers are host-side") measured
  FALSE — fs_kernel_image bakes SYS 6/7/9 as in-image guest code, so the
  WGSL twin executes it. Probe on both engines: 273 steps each, all 14 FS
  assertions PASS on both, RAM diff = 8 words all inside the BOX_MMIO
  mirror 8192-8210 (twin keeps MMIO in its own binding — SE022a contract,
  not FS drift), zero non-MMIO diffs / 16384 words. No SYSCALL_ABI_SPEC
  block needed (SYS 6/7/9 are not engine syscall arms).
- RED leg: corrupted expectation (payload2→0xDEADBEEF) → both engines FAIL
  data2/readout2 → VERDICT DIVERGENT, exit 1. Probe discriminates.
- Probe-defect kept: first draft read runner.image post-run (run_wgsl never
  writes the read-back into .image) — RED'd for the wrong reason; fixed to
  receipt["ram"] assertions (RAM-homed FS per SE021 lineage).
- Honesty: single machine/GPU; hole-reuse leg (L2) CPU-oracle only (no WGSL
  hole leg run — bounded gap, recorded); the 8-word MMIO diff is classified,
  not eliminated; no rate claims → floors N/A.
- NOT done: DTF-4 untouched (next tick; wc/DEFECT-18 risk per amendment);
  RECEIPT_DTF_floor.md + agent pre-verification receipt remain open floor-
  exit artifacts.

### 2026-09-22 ~17:3x CDT — DTF-1 closed: desktop-floor rung 1 measured + receipted (builder af3e62239ce2)

- Mailbox check: no RULING_* newer than HEAD (newest 09-21 14:59). New
  supply arrived instead as the RATIFIED amendment itself (4e3c30a2,
  17:19 — "DTF-1 claimable on the product lane's next tick").
- Discovery: DTF-1's implementation predates the amendment — it is
  TASK_SE020, landed 09-15 (2227ebc5) with a green orchestrator gate, but
  carried NO receipt under the DTF-1 name and no roadmap row. The
  claimable work this tick was therefore: measure at HEAD, write the
  receipt, promote the rows. No engine/app code changed.
- Gate: RED-first leg shown (test file moved out → pytest
  `ERROR: file or directory not found`, no tests ran) → GREEN (17 passed,
  rc 0) at HEAD 4e3c30a2.
- Receipt transcript (`.builder_queue/transcript_dtf1.py`, re-runnable):
  ONE repl() run, five turns — 'e hello'→' hello'; 's hi there'→WAV
  15876 samples @44100 Hz, Phy16Tone.decode=b' hi there'; 'w payload
  text'→file byte-exact b' payload text'; 'r'→' payload text' round-trip;
  'z bogus command'→ERR:UNKNOWN_CMD. Mutation leg: always-echo build
  echoes verbatim, marker absent — gate discriminates dispatch from
  always-echo.
- Honesty: batch mode only; AUDIO_OUT verified host-side decode, not
  acoustic; no WGSL-twin leg in DTF-1 (that is DTF-2's requirement); no
  rate claims → floors N/A; R5.3 clock untouched per amendment.
- NOT done: DTF-2/3/4 untouched (one rung per session; DTF-2 next tick);
  no R5.3 log line (Jericho's report).

### 2026-09-22 ~15:5x CDT — TICKET_ITEM8 CLOSED: 0x12 bridge exclusion landed (builder af3e62239ce2, commit 97b7732d)

- Mailbox check first: no RULING newer than the last landed commit at
  tick start (9bfbc7b9, 09-22 15:38 — this lane's own item-8 landing;
  newest RULING 09-21 14:59). Ticket was the only open lane supply.
- Fix applied exactly as ticketed: one line, all three twin copies
  (tools/, glyph_dispatch/src/, glyph_dispatch/src/glyph/
  wgsl_glyph_isa_v2.py:829), md5-identical
  4c54de24d542615316fa85673b58d046, pre-commit hook verified sync.
- Gate arc: baseline rotguard 24 GREEN → exclusion applied with the old
  gap pin → RED 1/23 (test_l35_gap_pin_0x12_bridge_exclusion_absent
  fired at :333 — the guard forcing the spec re-sync, by design) →
  spec 0x12 block + guard legs re-synced in the same commit → GREEN 24.
  New legs: NEGATIVE-contract pin
  (test_l35_neg_pin_0x12_bridge_exclusion_landed) + non-vacuity
  mutation probe (test_l35_mutated_bridge_reversion_is_caught: exclusion
  removed in-memory → pytest.raises). Landing-time defect kept: first
  pin draft used bare implicit concat across lines (IndentationError at
  lint) — fixed to an explicit anchor tuple before any test ran.
- Behavioral, live GPU (GlyphRunner.run_wgsl, probe re-run): 0x12
  python=-1 twin=-1 (u32 4294967295) PARITY — the false spawn-success is
  gone. 0x07 unchanged PARITY; 0x03/0x04 stub-0 remain sanctioned-stub
  DIVERGENT (untouched by design).
- Regression: pillar23+bk2 parity 36 passed; defect_d/read_path/
  ram_pixel_space/r51/r52 54 passed; gh15 transpiler 10; pre-commit
  hook on landing: 38 differential + 8 parity, twin sync verified.
- Honesty: single machine (Intel ARL iGPU), refusal-path-only claim
  (that path IS the 0x12 contract — no success path exists on either
  engine); no spawn semantics on the twin (NEGATIVE contract, same as
  0x07); no rate claims → floors N/A. Distribution copies in
  glyph_dispatch are md5-synced mirrors, not separately executed.
- NOT done this session: no R5.3 log line (that is Jericho's report);
  no other queue work — the queue is empty and the lane does not
  invent items.

### 2026-09-22 ~16:1x CDT — ROUND-3 item 8 COMPLETE: RUN-lane twin-status truthing (builder af3e62239ce2)

- MEASURED both engines live (probe `.builder_queue/probe_item8_run_lane_twin_status.py`,
  GPU twin = Intel ARL iGPU, GlyphRunner.run_wgsl): 0x07 python=-1/twin=-1 PARITY
  (spec correct → option (a), "twin -1" codified NORMATIVE); 0x12 python=-1/**twin=0
  DIVERGENT — the spec LIED** (claimed UNIMPLEMENTED/-1; 18u actually falls in the
  GeOS bridge 16u..255u → 0 = false spawn-success); 0x03/0x04 stub-0 confirmed →
  option (a) NORMATIVE (no host FS on the shader path; SE021 exec is Python-engine-side,
  the "IF glyph-sh v2 needs them on-shader" condition evaluated: it does not).
- DECISION: 0x12 is option (b) — spec corrected to `twin: BRIDGED` +
  `twin_contract: GAP-ITEM8-0x12-bridge-exclusion`, ticket
  `TICKET_ITEM8_0x12_bridge_false_success.md` filed (bounded fix: one-line bridge
  exclusion → unknown path → -1). NO engine code changed this item (per the item's
  own gate); the fix is queue supply.
- Rot guard `tests/test_pillar21_abi_spec_rotguard.py` grew L3.5 (4 legs): the GAP
  pin goes RED the moment the twin source excludes 18u, forcing the spec re-sync in
  the ticket's commit; in-memory mutation GAP→NORMATIVE REDs (non-vacuity); ticket
  file existence asserted (a GAP without a ticket is an unanchored lie). New
  machine-readable `twin_contract` field on the four blocks.
- Gate arc: RED first (new legs vs old spec: 3 failed, 21 passed) → GREEN
  (24 passed). Regression: pillar23 parity corpus 8 passed (GPU); twin copies
  md5-identical & untouched (4df41c619fa939790b0059d62142a0d1).
- Receipt: `RECEIPT_item8_twin_status_truthing.md`. NOT proven: the twin still
  returns 0 for 0x12 (GAP documented, not fixed); 0x03/0x04 NORMATIVE is a
  contract decision, today's behavior is what's measured.

### 2026-09-22 ~15:4x CDT — ROUND-3 item 7 COMPLETE: exemption machinery DELETED (builder af3e62239ce2, commit 26bf18c2)

- Deleted from GlyphAssemblerV2.assemble(): IMAGE_SPACE_WRITE_SYSCALLS
  (was {0x11: 1}), known_reg_const/image_space_writes/ram_space_writes
  LDI-const tracking, the GH-8b FS-window exemption in the STATIC check
  (in_fs_window), and the assemble-time RAM-vs-pixel-space ValueError —
  exactly the (A) ruling's completion terms (GLYPH_ISA_ROADMAP.md:177-179,
  "deleted, not just narrowed"). UNCHANGED: runtime FS-window aliasing
  (fs_pix_enabled, _mem_read/_mem_write — a different, live mechanism;
  test_gh20_fs_v2 green), the 0x11 handler itself (DEFECT-27, terminal),
  all other assembler static checks (SE023 jump bounds).
- Twin re-synced md5-identical (f11e02759302793d77dccebd0fb2e3a4);
  pre-commit cmp + differential (38) + Pillar 2.3 parity (8) all green at
  commit time.
- Gate REWRITTEN as the retirement's standing guard:
  tests/test_glyph_ram_pixel_space_check.py 8→6 legs — now asserts the
  check STAYS DEAD (r1: old L1 hazard program assembles clean; r4:
  machinery names absent from source AND fs_pix_enabled still present —
  discriminating both ways; r5: suite non-vacuity via SE023 bounds;
  r6: runtime FS-window aliasing round-trip pin). RED first: deletion
  applied with OLD suite → "2 failed, 6 passed" (l1 expected the raise,
  l6 anchor stale). GREEN after: 37 passed (6 + 31 defect_d unchanged).
- Regression (batched): lane family 86 passed; transpiler differential
  sample 7; FS-window runtime family 43. Collection 2107 = 2109 − 2,
  exactly the mandated 8→6 rewrite; no unexpected drops.
- Honesty: residual hazard real but unguarded (LD of an 0x11-only-written
  address = silent stale RAM; out of contract per DEFECT-27, recorded in
  source + RECEIPT_item7_exemption_deletion.md). No WGSL behavior claim.
  No floors/rate claims. defect_d's "below the FS window" comments left
  untouched (they describe the still-live runtime aliasing).
- Next: item 8 — RUN-lane twin-status truthing (0x07/0x12, 0x03/0x04
  contract-vs-gap decision doc + spec rot-guard legs, no engine code).
  After 7-8 the queue returns to empty.

Item 4 (GLYPH_ISA_ROADMAP 2.1 syscall ABI spec) was found already
delivered: docs/SYSCALL_ABI_SPEC.md + tests/test_pillar21_abi_spec_rotguard.py
landed 2026-09-16 (48cf1138), 13 days BEFORE the claim queue was authored,
and maintained since (0x10 header storage update in 481ec735, 2026-09-22
10:15). The queue item describes work that predates it — re-doing it would
manufacture scope. Verification, this tick, at HEAD cfa0382b:
- Rot guard GREEN: 20 passed (tests/test_pillar21_abi_spec_rotguard.py),
  including its three in-suite discriminating legs (:451 lying-doc copy,
  :467 mutated status claims, :478 twin-branch absence) — the gate is
  proven able to RED.
- Coverage EXACT: probe (output/probe_item4_coverage.py) — spec ABI blocks
  {0x01..0x09, 0x10, 0x11, 0x12} == engine syscall arms, 12/12 MATCH,
  none missing, none extra.
- 2.1's bullet requirements all discharged: one page per syscall (12),
  register contract, addressing/storage homes (RAM/PIXEL/HOST), return
  codes, errno set ("no errno exists" convention, :34), containment rules
  (:38), written against the ISA with twin status normative.
- NOT proven / honesty: no new artifact authored this tick beyond the
  probe + this ledger entry; the guard re-derives claims from engine
  sources at gate time, so this verification is a point-in-time GREEN.
  Candidate next item (NOT claimed — the queue is Jericho-approved and
  adding items is not lane authority): SE025's named residual "transpiler
  does not yet emit CMP3" (tools/rv64i_to_glyph.py branch lowering);
  engine-risk, needs worktree isolation per AGENTS.md.

## CLAIM QUEUE: EMPTY (all 4 items resolved — 1/2/3 landed, 4 verified
## pre-existing). Lane waits for Jericho's next approved item or ruling.

Directive: .builder_queue/RULING_wgsl_convergence_gates_r22.md (Jericho,
2026-09-21 ~15:0x CDT) — R1.4 executed as written; CLOSED.

### 2026-09-21 ~15:2x CDT — R2.3 landed ANYWAY (mailbox race, disclosed; builder af3e62239ce2, commit 6605f41a)

Full disclosure for Jericho / the R1.4 tick, no self-ratification:

- This tick read PRODUCT_LANE_STATE.md at ~15:03 and saw "Current rung:
  R2.3" — the ruling mirror (4d3c0c6f, 15:08:39) landed AFTER the read.
  Same mailbox defect the ruling itself diagnosed for R2.2; by its own
  logic the artifact stays landed, the defect was the ledger's reading
  path, not dishonesty.
- Work landed: tools/glyph_cc.py (C via gcc rv32i / Rust via rustc
  riscv32im -> ELF -> transpiler -> artifact -> GlyphCPUv2 -> receipt
  with artifact re-read round-trip leg), tests/test_glyph_cc.py 7 legs
  (4 GREEN / 3 RED, RED-first + stash-RED + discrimination probe),
  RECEIPT_R23_hosted_crosscomp.md, and a parse_elf fix in
  tools/rv64i_to_glyph.py (ABS FILE symbols shadowed _start -> IR gate
  rejected; 57-test transpiler regression green).
- Why this is arguably the ruling's "substrate-independent sub-steps"
  case: the whole R2.3 chain drives the oracle (GlyphCPUv2) and NEVER
  touches run_wgsl — zero shader-path claims anywhere in the receipt.
  But the lane does NOT decide this: R2.3's status is hereby
  "LANDED-PENDING-REVIEW" — Jericho rules whether it stays as named
  sub-step work or is re-scoped; until then R1.4 is the active rung and
  the next tick must work R1.4, not R2.3 follow-ons.

(R2.2 toolchain UX LANDED — tools/glyph_run.py, tests/test_glyph_run.py,
examples/sum_1_to_5.glyph; see session log + RECEIPT_R22_toolchain_ux.md.
R2.1 box-ABI freeze LANDED — docs/BOX_ABI_v2.md +
tests/test_box_abi_conformance.py.)

Known blockage (pre-registered 2026-09-21): the in-guest agent harness the
anchor workload needs does not fully exist yet. Expected first-tick outcome
was blockage-logging plus adjacent non-blocked work, NOT a completed rung.
Never fake, stub, or simulate the missing capability to claim the rung.

Governing docs: PRODUCT_ROADMAP.md (RATIFIED, 1827f6cb) ·
.builder_queue/POLICY_standing_decision_delegation.md ·
.builder_queue/POLICY_decision_delegation_20260918.md · AGENTS.md.
P1.3 kill switch: see cron af3e62239ce2 prompt — verbatim binding; a
measured FAIL is final; only Jericho overturns.

## Session log


### 2026-09-27 ~01:0x CDT — PHASE 1c RESEARCH TICK: item-29 carried note "LD not box-checked" MEASURED — silent cross-fence read confirmed, BK-38 filed (builder af3e62239ce2)

- Run selection re-verified, not assumed: HEAD b2c00b68 (my BK-37
  research tick, 00:43), tracked tree clean at claim, mailbox rule clean
  (find .builder_queue -name 'RULING_*.md' -newermt @<HEAD-epoch> EMPTY),
  monitor queue=0 stall_tier=0 CLAIM_PENDING. Queue empty → Phase 1c
  research is the eligible tick. No re-research: the LD-fence question
  exists nowhere in RESEARCH_*.md or backlog rows — only as an
  unverified honesty note in RECEIPT_item29_containment.md:66.
- Question: item-29 landed per-process containment as a WRITE fence
  (E-K1 store trap). Can a tiled USER task READ outside its tile?
- Measured at HEAD b2c00b68, probe .builder_queue/probe_ld_fence_af3e.py
  (untracked, landed modules only; harness = the landed
  GlyphProcessTable.spawn(tile=(5,0,2,4)) containment path itself;
  deterministic across 3 runs, diff clean):
  ld_cross_fence — USER LD from word 164 (first word outside the tile,
  seeded canary 0x0BADF00D), ST to in-tile word 160 → rc=EXIT_OK,
  faulted=False, mode stays USER, word 160 == 0x0BADF00D. SILENT
  cross-fence read, value exfiltrated in-tile, clean exit.
  st_cross_fence control on the SAME boundary word → rc=EXIT_FAULT,
  fault_addr=656=164×4, mode→SUPER. ld_in_tile control → lands
  normally. The write-only asymmetry is live on one tree, one tile,
  one address.
- Root cause: _addr_in_box (glyph_isa_v2.py:720-747) is consulted at
  exactly one site — the USER store trap (:1041). The LD arm
  (:826-909) is unguarded on every path: FS-pixel window :915-916,
  unpaged RAM :918-919, paged RAM target :904-909. WGSL twin has the
  same gap BY SOURCE READ (walk_ld, wgsl_glyph_isa_v2.py:351-367, no
  tile consult; NOT probed on-device this tick).
- Load-bearing why: a tiled task can read the reaper/KFAULT words, a
  neighbor task's tile, or FS-window data and PRT it out with a clean
  exit — the containment story is write-isolation only.
- BACKLOG: BK-38 filed to systems/GLYPH_BACKLOG.md (LD tile-fence
  guard mirroring the ST-side consult; gate
  tests/test_bk38_ld_fence.py, RED-first + twin-parity + non-vacuity
  legs). Receipt: .builder_queue/RESEARCH_ld_fence_read_gap.md.
- Honesty: all numbers structural (no rates → rule-1 floors N/A);
  twin-parity claim is from shader source read, not a wgpu run —
  labeled as such in the receipt; research landed no engine code.

### 2026-09-26 ~08:5x CDT — CLAIM QUEUE item 29 (per-process spatial containment: GO-2 tiles bound to spawn) LANDED; CLAIM QUEUE NOW EMPTY (builder af3e62239ce2)

- Provenance re-verified at tick start: HEAD f94ee177 (my item-28
  ledger lineage); tracked tree CLEAN (only the Qoder lane's untracked
  BM000/DOGFOOD artifacts, untouched); monitor CLAIM_PENDING queue=0
  supply=claim item-29; QUEUE_STATE active=null, item-29 unblocked;
  no RULING_* newer than HEAD. Claimed per Phase-1b.
- ADOPTED an in-flight worktree: ~/zion/worktrees/item29-containment
  had an uncommitted implementation (glyph_containment.py + spawn
  extension + 288-line gate, mtimes 08:16-08:17, no live process, no
  lane record). Verified it against the spec myself before adopting:
  read the GO-2 tile predicate (glyph_isa_v2.py:734-747) and the E-K1
  ST trap path (:1041-1056), re-ran the 10-leg gate GREEN, ran the
  non-vacuity probe myself, then stashed/RED-first-proved and
  committed as cacb6449.
- Design finding baked in (THE FENCE NEEDS A CATCHER): the ST trap
  path vectors to KFAULT_PC UNCONDITIONALLY — a tile armed without a
  reaper would trap to (0,0), restart in SUPER, and the re-executed
  store would LAND. Tiled spawns always arm the trampoline.
- Gate: tests/test_item29_containment.py — 10 legs. RED-first
  (implementation stashed -> ModuleNotFoundError at collection).
  GREEN 10 passed in 34.68s / 33.81s; post-cherry-pick main re-gate
  at 59469d20: 42 passed in 107.58s (+item26+item25+png_vfs+box_abi),
  exit 0. Non-vacuity: neutered fence -> B3 breach assert fires.
- ZERO new syscall numbers; engine byte-unchanged (N1 blob-hash guard
  in-gate). tile=None keeps the exact item-26 posture (B1b + R1).
- Honesty (rule 6): all asserts structural — no rates/latencies,
  rule-1 floors do not attach. NOT verified: LD not box-checked
  (carried note); SUPER-mode stores never fenced; no GPU-image
  execution; the cannot-re-arm-own-fence claim is argument, not
  proof, for every future program shape; WGSL twin untouched.
- Queue state: QUEUE_STATE.json item-29 -> landed. **CLAIM QUEUE IS
  EMPTY** (items 1-29 all resolved). CURRENT_TICKET.json reconciled;
  next_step = supply-wait or Phase-1c research per empty-queue rules.
  REPAIR_PENDING_BK27_L5 unchanged (holds; sign-off change).


### 2026-09-23 ~20:1x CDT — VERIFICATION tick: launch criterion MET at e066e429, re-measured, not trusted (builder af3e62239ce2)

- Mailbox check: STATUS ACTIVE; monitor delta = seat lane's e066e429
  (RECEIPT_DTF_agent_use.md rework, "FLOOR STATUS: COMPLETE"). No RULING_*
  newer than 2026-09-22 20:38; CLAIM QUEUE EMPTY (rounds 1-7 closed).
- This tick re-verified the floor legs at HEAD e066e429 with own runs:
  live shell pipe (w byte-exact write/read-back, unknown → ERR:UNKNOWN_CMD,
  no silent FS write, exit 0); tests/test_bk7_fs_grow.py +
  test_glyph_text_console.py 13 passed; test_bk11_coreutils.py 6 passed
  in 23.9s. Matches the receipt's own numbers independently.
- Recorded in Current rung: launch criterion (PRODUCT_ROADMAP.md:141-144)
  MET-AND-VERIFIED. Roadmap file deliberately NOT edited (the roadmap's own
  section 0 forbids agents declaring the roadmap complete on Jericho's
  behalf). Lane returns to supply-wait.
- NOT done: no code, docs, or backlog changes; BK-18/BK-21 unclaimed
  (promotion gate needs Jericho); BM000 files in .builder_queue/ belong to
  the Qoder ladder lane — untouched.

### 2026-09-23 ~12:0x CDT — ROUND-7 item 12 VERIFIED PRE-EXISTING: DTF-3/BK-7 re-measured at HEAD (builder af3e62239ce2)

- Mailbox check first: HEAD ed860f06 is the seat lane's round-7 supply
  (11:20); no RULING_* newer than HEAD (newest mtimes 09-22 20:38);
  monitor CLEAN queue=0; STATUS ACTIVE. Claimed round-7 item 12
  (lowest-first, one active ticket).
- Discovery (same shape as item 4): the item's deliverable predates its
  filing. BK-7's implementation landed 2026-09-11 (153b5edb:
  tests/test_bk7_fs_grow.py 2 legs, systems/RECEIPT_BK7_FS_GROW.md,
  RED-first arc in that commit) and DTF-3 was measured at HEAD +
  twin-boundary truthed 2026-09-22 (RECEIPT_DTF3_fs_grow.md, commit
  2090c163) — including the WGSL note the brief asks for, with the
  brief's premise "FS handlers are host-side" measured FALSE (the GH-8b
  FS kernel is in-image guest code baked by fs_kernel_image(),
  tools/glyph_gpt/baker.py:1481; the twin EXECUTES it) and the corrected
  boundary recorded per the SYSCALL_ABI_SPEC convention (no spec block
  needed — SYS 6/7/9 are in-image kernel conventions, not engine arms).
  Re-doing it would manufacture scope; the claimable work this tick was
  re-verification at HEAD. No FS/engine code changed.
- GREEN at HEAD ed860f06, this process:
  `.venv/bin/python -m pytest tests/test_bk7_fs_grow.py -v` → 2 passed
  (test_bk7_two_appends_grow_file_and_read_back,
  test_bk7_delete_creates_reusable_slot), rc 0, 0.09s. Family
  (test_bk7_fs_grow + test_defect_d* + test_gh20_fs_v2 +
  test_pillar21_abi_spec_rotguard) → 67 passed, rc 0, 44.32s.
- Twin probe re-run live (`.builder_queue/probe_dtf3_twin_boundary.py`,
  exit 0): CPU 273 steps / WGSL 273 steps, ALL PASS both engines, RAM
  diff total=8 all inside the BOX_MMIO mirror block (8193-8206 set),
  outside_mmio=0 → VERDICT: MATCH.
- RED leg (rule 4): throwaway copy with BK7_PAYLOAD2 → 0xDEADBEEF →
  [CPU] FAIL data2/readout2, [WGSL] FAIL data2/readout2, VERDICT:
  DIVERGENT, exit 1. Throwaway deleted; landed probe untouched.
- Honesty: single host, single GPU; hole-reuse leg (L2) CPU-oracle only
  (no WGSL hole leg — bounded gap, carried from the 09-22 receipt); no
  rate claims → floors N/A; gate/panels trusted to their own standing
  assertions, only their exit codes + the probe's own checks re-verified
  this tick.
- NOT done: item 13 (BK-19 font atlas) untouched — NEXT tick per
  one-active-ticket rule; DTF-4 / BK-18 remain future supply per the
  round-7 rule line.
- Next: item 13.

### 2026-09-22 ~23:1x CDT — PHASE 1c RESEARCH tick: VGA font coverage gap measured, BK-19 filed (builder af3e62239ce2)

- Trigger check: STATUS ACTIVE, CLAIM QUEUE EMPTY, no RULING newer than
  HEAD 2a5a298a (newest RULING mtimes 20:38, pre-landing), monitor CLEAN
  queue=0. Rule-5 check: NOT a re-research — BK-15/16/17/18 cover
  user-surface/spec/oom; the font gap was only DISCLOSED
  (RECEIPT_DTF_floor.md:60-76, "filed as candidate queue supply"), never
  receipted or backlogged.
- Question picked (friction-first): the DTF floor's landing defect 2 — the
  machine's own error marker displays with a hole in the pixel band.
- Probe: `.builder_queue/probe_font_coverage_gap.py` (exit 0 this tick,
  re-runnable) — drives the production font module (tools/vga_font_8x16.py)
  and production console (tools/glyph_text_console.py), no mocks.
- Findings (full derivation in `.builder_queue/RESEARCH_font_coverage_gap.md`):
  atlas = 85/95 printable-ASCII glyphs; missing exactly
  `[ \ ] ^ _ \` { | } ~` (codes 91-96, 123-126); live render→decode
  round-trip: 'ERR:UNKNOWN_CMD' → 'ERR:UNKNOWN?CMD' (lossy via the
  renderer's documented '?' substitution, glyph_text_console.py:111-112);
  the "85 glyphs" docstring claim is numerically CORRECT (the count was
  honest, the gap is the family itself). Blast radius bounded: all 15
  BK-11 coreutils fixture outputs scanned — ZERO missing-charset chars,
  so today exactly ONE floor string is affected; the exposure is any
  future program printing braces/brackets/underscores/globs.
- Filed `.builder_queue/RESEARCH_font_coverage_gap.md` + BK-19 row in
  systems/GLYPH_BACKLOG.md: complete the atlas from the canonical VGA ROM
  (the module header already claims "subset: printable ASCII 32-126" —
  vga_font_8x16.py:15 — so this completes a claimed subset); gate
  tests/test_bk19_font_coverage.py L1–L5 (coverage set-inclusion RED
  today, bitmap collision-freedom, full-95-char lossless round-trip RED
  today, in-memory mutation non-vacuity, existing console gate green).
  Renderer + decoder need ZERO code change (both iterate the font dict).
- Honesty: structural counts + one live round-trip only — no rate claims
  → floors N/A; NOT verified: whether the 10-glyph exclusion was
  deliberate (no commit/doc records a decision — approving BK-19 reverses
  it, which is why this is backlog not a landing); NOT verified: new
  bitmap shapes (L2 covers that at landing); no WGSL concern (the band is
  host-side glass-TTY, no shader font exists). Sibling-session note:
  GLYPH_BACKLOG.md was concurrently touched; BK-19 appended without
  displacing BK-15/16/17/18/OBS-1 (verified 6 rows present post-edit).
- Next: supply-wait — R5.3 use friction, a Jericho directive, or a
  ruling; research tick only if a NEW researchable question exists.

### 2026-09-22 ~21:5x CDT — PHASE 1c RESEARCH tick: day-1 "speaks its language" clause measured, BK-17 filed (builder af3e62239ce2)

- Trigger check: STATUS ACTIVE, CLAIM QUEUE EMPTY, no RULING newer than
  HEAD 2908ff6e (newest RULING mtimes 20:38, pre-landing), monitor CLEAN
  queue=0. Rule-5 check: NOT a BK-15/16 re-research — this covers the
  THIRD clause of R53_USE_LOG.md:24 ("the compiler assumes you already
  speak its language"), untouched by any existing receipt/backlog row.
- Probe: `.builder_queue/probe_day1_language_dialect.py` (exit 0 this
  tick, re-runnable) — mechanical extraction of engine OPCODES vs
  docs/spec/GLYPH_ISA_SPEC_v1.0.md + live glyph_run error probes.
- Findings (full derivation in
  `.builder_queue/RESEARCH_day1_language_dialect.md`): 36 engine opcodes,
  spec names 30 — MUL/JNZ/JNE/CMP3/JLT/JGT absent entirely; palette has
  6 more absences + one factual bug (SYSRET spec 255,99,72 vs engine
  255,99,71 — a decoder built from the spec mis-decodes every SYSRET by
  one blue bit, against the spec's own hardcode-pinned-colors contract);
  unknown-opcode first-contact error is a leaked `KeyError: 'mov'`
  (measured exit 2); docs/START_HERE.md mentions the spec 0 times — the
  language doc is unreachable from the stranger doc.
- Filed BK-17 row in systems/GLYPH_BACKLOG.md: spec freshness sync +
  START_HERE link + loud unknown-opcode error contract; gate
  tests/test_bk17_spec_freshness.py L1–L4 (RED today on L1/L2/L3 by
  measurement). Doc/error-string scope only; zero engine change.
- Honesty: structural counts + live exits only, no rate claims → floors
  N/A; n=1 friction evidence flagged directional; the SYSRET mismatch is
  REPORTED not fixed — spec-vs-engine authority is a sign-off decision
  (GLS-1.0 palette was pinned in a32b43a3), Jericho's call. NOTE:
  systems/GLYPH_BACKLOG.md was concurrently touched by a sibling session;
  BK-17 appended without displacing BK-15/16/OBS-1 (verified 4 rows present).
- Next: supply-wait — R5.3 use friction, a Jericho directive, or a
  ruling; research tick only if a NEW researchable question exists.

### 2026-09-22 ~21:4x CDT — PHASE 1c RESEARCH tick: day-1 "what time is it" gap measured, BK-16 filed (builder af3e62239ce2)

- Trigger check: STATUS ACTIVE, CLAIM QUEUE EMPTY (rounds 1–3 closed), no
  RULING newer than HEAD 18215029 (newest RULING mtimes 20:38, pre-landing),
  monitor CLEAN queue=0. Per the 2026-09-22 research directive: one research
  item instead of idling.
- Ledger hygiene FIRST: the prior current-rung pointer ("Next: P3", written
  21:3x) was STALE — P3's three rungs all landed 2026-09-21 with receipts
  (R3.1 cold boot 814 ms PASS, R3.2 container persistence PASS, R3.3 host
  bridge PASS; RECEIPT_R31/R32/R33 verified on disk this tick), and R4.x /
  R5.1 / R5.2 landed after. Pointer corrected; R5.3 remains Jericho-only.
- Question picked (friction-first): day-1's SECOND request — "what time is
  it" (R53_USE_LOG.md:24). BK-15 (17:1x tick) answered "list the files";
  zero tree coverage existed for the clock half (backlog grep: no clock/epoch
  row; SYSCALL_ABI_SPEC occupies 0x01–0x09 + 0x10–0x12; 0x13 = BK-15; 0x14
  free).
- Measured this tick (live replay at HEAD 18215029): repl() of
  ["time","t","what time is it"] through build_dispatch_shell → all three
  → ERR:UNKNOWN_CMD (exit 0; surface absent, machine fine).
- DEFECT observed during the replay: multi-word unknown lines ("what time is
  it") fall through dispatch to a SILENT FS write — FILE_WRITE 14 bytes
  ("hat time is it") persisted to the shell's notes file with no error.
  Recorded in the receipt; folded into BK-16's L5 rather than a separate
  ticket (one research item per tick).
- Filed `.builder_queue/RESEARCH_day1_user_surface_time.md` + BK-16 row in
  systems/GLYPH_BACKLOG.md: SYSCALL_CLOCK (0x14), epoch seconds (+ optional
  µs word) in rd/RAM dest, WGSL twin -1 NORMATIVE (0x07/0x12 precedent),
  glyph-sh `time` verb over PRT. Gate: tests/test_bk16_clock.py L1–L5
  (bounds, twin parity + rot-guard, verb round-trip, mutation RED,
  loud-ERR-not-silent-write).
- Honesty: no numbers beyond existence claims (syscall occupancy, dispatch
  verbs, backlog grep) — no rate claims, floors/check_regime N/A; the twin
  -1 contract is asserted from the codified precedent, not measured on this
  tick; research proposes, never lands engine code. Note: systems/
  GLYPH_BACKLOG.md was concurrently modified by a sibling session (OBS-1
  row); BK-16 was appended without displacing it.
- Next: supply-wait — R5.3 use friction, a new Jericho directive, or a
  ruling; research tick again only if those stay absent and a NEW
  researchable question exists (do not re-research BK-15/16).

### 2026-09-22 ~17:1x CDT — PHASE 1c RESEARCH tick: day-1 user-surface gap measured, BK-15 filed (builder af3e62239ce2)

- Trigger check: STATUS ACTIVE, queue EMPTY (rounds 1-3 closed), no RULING
  newer than HEAD 3d0b09d5 (newest 09-21 14:59), monitor CLEAN queue=0.
  Per the 2026-09-22 research directive: one research item instead of idling.
- Question picked by friction-first ranking: the ONLY line in R5.3's use
  log (R53_USE_LOG.md:24, Jericho day-1) — "the shell only repeats you...
  No user surface exists yet." His two real requests: list files, time.
- Measured this tick (live replays + structural greps, all derivations in
  the receipt): both day-1 request-shapes ('ls', 'time') → ERR:UNKNOWN_CMD
  on the exec shell (5 verbs: e/s/w/r/x, glyph_interactive_shell.py:226-241);
  0 enumeration syscalls and 0 clock surfaces in tools/glyph_isa_v2.py;
  13 ABI blocks, none a list.
- Filed `.builder_queue/RESEARCH_day1_user_surface_ls.md` + BK-15 row in
  systems/GLYPH_BACKLOG.md: SYSCALL_FILE_LIST (0x13), host-side enumeration
  under the 0x07/0x12 containment model, twin -1 as NORMATIVE contract,
  `files` shell verb, 5-leg gate with mutation probe. "What time is it"
  explicitly out of scope (needs a new time source designed in first).
- Honesty: research receipt proposes, never lands engine code — zero
  production lines touched this tick. n=1 friction evidence, flagged as
  directional in the receipt. No rate claims → floors N/A.
- Lane posture: wait. BK-15 is NOT claimable without Jericho (backlog
  header rules); next real supply is the R5.3 log or his approval.

### 2026-09-22 ~13:3x CDT — CLAIM QUEUE item 6 COMPLETE: GlyphRunner WGSL floor refreshed + verdict machinery proven (builder af3e62239ce2)

- Premise correction (measured): item 6's "no GlyphRunner WGSL entry" was
  stale — gr-step 639.1/tput 70.3 landed 09-21 (80d9285f). The REAL
  residual was freshness: measured_at ~27h old, outside the 12h window;
  check_regime hard-FAILed on the file ("floors are stale (26h old)").
  Also the shader changed this afternoon (item 5 CALLR branch).
- Refresh: calibrate_floors_authoritative.py re-run in dedicated process
  → measured_at 2026-09-22T18:27Z, gr_step 632.4 (−1.0%), tput 71.1
  (+1.1%) — WGSL path held within ~1% across 26h; CPU step floor drifted
  910.2→1165.2 (+28%, recorded, not investigated, nothing cites it).
- Gate legs (item 6's ADMIT/REJECT proof), real exits: GREEN 9.85x
  ADMISSIBLE + 1.34x ADMISSIBLE (exit 0); RED 0.56x INADMISSIBLE + 0.13x
  INADMISSIBLE (exit 1), both WGSL paths (tput + spaced latency).
- Honesty: legs are synthetic straddling numbers — machinery proof, NO
  workload rate claim; single GPU/host; floors re-stale in 12h by design.
  Receipt: RECEIPT_item6_glyphrunner_floor_refresh.md.
- Round-2 queue (items 5-6) now BOTH landed. Lane waits for real R5.3
  use friction or Jericho's next approved item.

### 2026-09-22 ~11:2x CDT — CLAIM QUEUE item 4 COMPLETE-BY-VERIFICATION; queue EMPTY (builder af3e62239ce2, monitor tick)

- Re-verified HEAD per parallel-session rule: new commits since last tick
  were 0292a40d (SE025) + cfa0382b (ledger) — this lane's own item 3
  landing, no foreign rungs, no rulings newer than HEAD (newest RULING
  09-21 14:59 < last landed commit 09-22 11:01). Mailbox clear.
- Item 4 (ISA 2.1 syscall ABI spec) found ALREADY DELIVERED:
  docs/SYSCALL_ABI_SPEC.md + rot guard landed 2026-09-16 (48cf1138),
  13 days before the queue was authored; spec updated by 481ec735
  (0x10 RAM storage) this morning. Re-doing it would manufacture scope.
- Verification at HEAD cfa0382b: rot guard 20/20 GREEN (discriminating
  legs at :451/:467/:478 — gate proven able to RED); coverage probe
  output/probe_item4_coverage.py: 12 spec ABI blocks == 12 engine arms,
  exact MATCH, none missing/extra. Details in the Current rung block.
- Claimed NOTHING new; no production lines touched (ledger + probe only).
  Candidate next (UNCLAIMED, needs Jericho-approved queue item): SE025
  transpiler CMP3 emission residual — engine-risk, worktree-isolated.
- Lane posture: wait. The queue is Jericho-approved; the lane does not
  append items to it.

### 2026-09-22 ~10:3x CDT — CLAIM QUEUE item 2 COMPLETE: _read_path view-merge RETIRED (builder af3e62239ce2, commit 4e8a2c94)

- `_read_path` (glyph_isa_v2.py:1374) is now SINGLE-VIEW over the data
  space (RAM + FS-pixel alias): the 09-17 image-fallback view-merge —
  the last dual-view read in the (A)-scoped-to-handlers set — is
  retired per DEFECT-23-ROOT / SYSCALL_ABI_SPEC.md:29. Empty data view
  → empty path → handler refusal; past-RAM addresses terminate.
- Gate tests/test_read_path_single_view.py (NEW, 3 legs): RED at HEAD
  (image-seeded path resolved through the merge — "[SYSCALL] RUN:
  executed ...allowed.sh"); GREEN after (refused). 19 fixture seed
  loops across run_containment/file_io/audio_io/defect_d migrated from
  image-side path seeding to RAM seeding. glyph_dispatch copy
  re-synced (md5-identical); triple-sync + pillar21 rotguard green.
- Regression: 151 passed (20 lane-family files, batched; full-tree
  pytest OOMs on this host as previously recorded). Pre-commit gate on
  landing: 38 transpiler/ISA differential + 8 Pillar 2.3 parity, green.
- Honesty: neuter-probe anchor COMMENTS in defect_d still textually
  mention the merge — pinned by `assert new_body in source` anchors;
  a coordinated comment+anchor re-sync is ticketable, cosmetic. WGSL
  twin has no host-path syscalls (nothing shader-side to retire).
  5 other tracked-dirty files (.venv bins, guest_state, proposals log,
  pxc1 frame) NOT staged — environment/guest churn outside this
  session. Receipt: RECEIPT_SE021_read_path_single_view.md.
- Next: claim-queue item 3 — GLYPH_ISA_ROADMAP 1.3 CMP tri-state +
  JLT/JGT (file as SE025, additive per 1.1, JZ untouched).

### 2026-09-22 ~09:4x CDT — CLAIM QUEUE item 2 step 1: 0x10 BOOT_LINUX header PIXEL→RAM (builder af3e62239ce2, commit 481ec735)

- The (A)-scoped-to-handlers sweep was NOT actually complete: the 9/16
  "5/5 COMPLETE" ledger covered 0x01/0x03/0x04/0x08/0x09, but scoping §2
  listed 0x10's container header as image-space too. Landed the residual:
  0x10 reads its VAC2 header from RAM (one byte/word, low-byte-first,
  OOR→0→-1 no-crash); WGSL twin gained a legacy-table `16u` branch over
  `ram_read` (no image fallback) — both engines, one commit, triple-sync
  re-synced (the sync gate names a 3rd copy at glyph_dispatch/src/).
- SYSCALL_ABI_SPEC 0x10: storage RAM, twin IMPLEMENTED. The pillar21
  doc-rot guard caught the stale doc immediately after the engine moved
  (L2/L3 RED at :379) — guard working as designed, doc + L4 leg updated.
- Gate: test_defect_d_ram_scoped_handlers.py 25→32 legs. RED first
  (`-k 0x10` on un-migrated engine: 4 failed / 2 passed — RAM recognition,
  image-refusal mirror, non-vacuity neuter, WGSL parity on real GPU).
  Landing-time test defects kept: seeding helper kept old pixel packing
  (sig read b'V2..'), neuter didn't swap sig assembly. GREEN: 32 passed;
  SE021 family 45; rotguard 20; lane family 104. Receipt:
  RECEIPT_SE021_0x10_boot_linux_ram.md.
- ENV REPAIR (pre-existing RED, first fix of the session): standing gate
  was 8 FAILED at HEAD — scipy/soundfile missing from .venv (lost in the
  9/19 ENOSPC cleanup; also retro-fixes the "8 defect_d audio failures"
  the R1.4 log attributed to env). Reinstalled scipy, soundfile, mcp<2
  (2.x breaks FastMCP import), librosa.
- Honesty: view-merge retirement NOT done (next step of item 2, has its
  own blast radius); E-K2 dispatcher path unchanged; recognition-only.
  Full-tree pytest OOM-killed 3x at ~62% on this host — batched sweep
  used; all remaining failures reproduced at HEAD with the lane diff
  stashed (go6/nested_buffer/cross_lingual/bk11/dct/agy_wrapper/gh23 +
  3 isolation-passing collection errors). No rate claims → floors N/A.
- Next: CLAIM QUEUE item 2 step 2 — _read_path view-merge retirement.

### 2026-09-22 ~09:1x CDT — CLAIM QUEUE item 1 RESOLVED: day-1 transpiler defect fixed (builder af3e62239ce2, commit 2f619963)

- TICKET_R53_day1_transpiler_auipc_jalr closed. Gate green: rust
  recursive fib(15) via glyph_cc → HALT, a0=610, round-trip MATCH;
  C lane unchanged green (fn-ptr 36, recursion 610, add8 36); 65
  transpiler-family tests + glyph_cc gate 9 passed (incl. 2 new legs).
- Root cause CORRECTED vs the ticket's best attribution: no label-
  placement defect existed. The glyph JALR lowering (rv64i_to_glyph.py
  OP_JALR branch) indexed the pointer table at rs1 alone, DROPPING the
  instruction immediate. rustc's `auipc ra,0; jalr -N(ra)` read its own
  auipc entry (measured packed 0x3) and spun — the "POP on unbalanced
  stack" the seat lane saw was downstream r31 drift, and their
  coordinate-probe read memory[0x81b] (the CORRECT entry) instead of
  the word the code actually reads (memory[0x801], indexed by ra=4).
  gcc's imm=0 `jalr ra,0(a5)` masked the defect → the C/Rust asymmetry.
- Fix, one commit: (1) fold imm into the JALR table index (byte-
  identical emission when imm==0; 65 tests prove no fixture drift);
  (2) seed build_pointer_table in glyph_cc's runner AND its round-trip
  artifact-replay leg (measured MISMATCH a0=0 without — word 0 → glyph
  PC (0,0)); (3) ADOPTED the seat lane's uncommitted #[naked] _start
  (quiet on tree since 08:02, disclosed per R1.2/R1.4 precedent;
  measured alone it was insufficient — NO HALT — consistent with it
  fixing only the sp=0 prologue-store fault).
- RED legs: HEAD → FAULT; naked alone → NO HALT; gate with the
  transpiler fix stashed → 1 failed (discriminating).
- Honesty: CPU oracle only, no WGSL parity claim; ~1 target-bit mask
  unapplied (no glyph AND-imm; no rv32 toolchain emits odd text
  targets); artifact-only replay of indirect-call programs now needs
  the glyph source text alongside the artifact (documented). Receipt:
  RECEIPT_R53_day1_auipc_jalr_fix.md.
- Next: CLAIM QUEUE item 2 (SE021 (A)-scoped memory view) on a later
  tick — not started this session.

### 2026-09-22 ~07:4x CDT — observed: R5.3 clock started by parallel session (monitor tick, builder af3e62239ce2)

- Monitor hash-change tick; change traced to 4f437346 (2026-09-22
  07:36, parallel session): `.builder_queue/R53_USE_LOG.md` created —
  R5.3 30-day real-use log, clock start 2026-09-22 (Jericho,
  in-channel), contract = one plain dated line per real-work day.
- The gate is Jericho's to run (PRODUCT_ROADMAP.md:82, his own
  report). Builder-executable product work remains COMPLETE as of
  R5.2. No RULING newer than the last landed commit; tree CLEAN.
- Lane posture: wait. Wake on tree churn or new rulings only; do NOT
  restart, re-scope, or invent rungs while R5.3 is open.

### 2026-09-21 ~19:0x CDT — R5.2 stranger documentation LANDED (PASS; builder af3e62239ce2, this commit)

- `docs/START_HERE.md`: the stranger doc per the rung text — what it is
  (pixel-programmed GPU-native machine, WGSL RV32IMA core, Hilbert RAM,
  E-K1 box isolation), what it's for (isolated co-resident agent workloads;
  performance questions delegated to RECEIPT_R13_preference.md rather than
  re-quoted), how to run the anchor workload (installer --skip-boot /
  --json / --corrupt-verify; glyph_run.py source + artifact-only runs).
  Every promised output captured from live runs before writing.
- Gate `tests/test_r52_stranger_doc.py`: the doc is executed, not read.
  Extracts each fenced bash block, runs it from the repo root, checks each
  line of the paired ```text block against the real output. Promise
  conventions: verbatim / squeezed / whitespace-free / `exit: N` /
  `~regex` (for the manifest's per-run ms count). RED legs at landing:
  missing-anchor, corrupted-command, fabricated-output (doc promising
  "714": 999999 fails — claims cannot diverge from the machine).
- Landing-time defects kept: first draft assumed exit 0 everywhere (the
  tamper leg legitimately exits 1); second draft froze a variable ms value
  as literal. Both fired RED before the green — recorded in receipt.
- Gates: standalone exit 0 (/tmp/r52_gate3.log); pytest 35 passed
  (r52/r51/r43/conformance/glyph_run/fleet) in 14.50s. Zero production
  lines changed. No rate claims → floors/check_regime N/A.
- Honesty: gate proves doc truth AT GATE TIME (drift later = RED, by
  design); no second-machine claim; R5.3 requires Jericho's own report —
  the builder cannot start it. Receipt: RECEIPT_R52_stranger_doc.md.
- Next rung: R5.3 — NOT builder-executable (Jericho's own 30-day use
  report, clock started 2026-09-22). Builder work continues via the
  CLAIM QUEUE below, no new ratification needed.

## CLAIM QUEUE (ordered, Jericho-approved 2026-09-22) — claim top item whose
## prerequisites are green; one active ticket at a time (ladder cadence)

1. **TICKET_R53_day1_transpiler_auipc_jalr.json** — the day-1 use-test
   defect. Rust lane broken for stack-using programs; C lane verified
   green across fn-ptr/recursion/big-frame (2026-09-22, this ledger).
   Root cause PARTIALLY pinned (see ticket: unseeded pointer table =
   necessary; second fault = last link, lane owns). Gate in ticket.
   Claim first — it blocks the porting lane R5.3 depends on.

2. **SE021 memory-view unification, (A)-scoped-to-handlers
   implementation** — RULED 2026-09-16 (Jericho, "(A) scoped to
   handlers"), RELEASED by measurement 2026-09-18
   (RULING_SE021_release_by_measurement_20260918.md). 11 handler arms
   + WGSL twin bounded delta + ~16 test files. Oracle legs
   (tests/test_glyph_app_glyph_on_glyph.py, 4/4 green at HEAD
   2026-09-22) are the regression gate; any leg RED re-blocks the row.

3. **GLYPH_ISA_ROADMAP 1.3 — CMP tri-state + JLT/JGT** (J-DECISION
   recorded there: file as SE025 or fold into SE024's ticket — builder
   files SE025). Additive discipline per 1.1; JZ untouched.

4. **GLYPH_ISA_ROADMAP 2.1 — syscall ABI spec, doc-rot-guarded** —
   one page per syscall, register/addr claims extracted by test, not
   transcribed. Pure documentation+test work, zero engine risk; good
   filler while a bigger ticket's gates soak.

Note for R5.3 synergy: glyph-native apps (.glyph asm via
GlyphAssemblerV2) bypass the transpiler entirely — the defect in (1)
blocks C/Rust porting, not the native lane. Jericho's use test can
proceed on native apps while (1) is in flight.

## CLAIM QUEUE ROUND 2 (Jericho-directed 2026-09-22 ~12:1x CDT) — verified
## in-repo supply; still no new ratification needed. Same cadence rules.

5. **WGSL parity sweep of today's landed work** — every 09-22 landing
   carried an explicit "no WGSL/shader-path parity claim" boundary
   (RECEIPT_R53_day1_auipc_jalr_fix.md:109, RECEIPT_SE021_0x10 step,
   read_path retirement). The scoping doc's own gap note stands:
   "No WGSL run (no GPU leg); WGSL claims are from reading the shader
   source" (SCOPING_MEMORY_VIEW_UNIFICATION.md:176). Task: for each
   09-22 engine delta (JALR imm-fold, 0x10 RAM header, _read_path
   single-view, CMP3/JLT/JGT), add a WGSL-side leg to the existing
   parity suites (test_bk2_wgsl_syscall_parity.py /
   test_se022a_read_parity.py / pillar23 pattern — all 8 green at
   round-2 opening) or file a named per-delta gap ticket if the twin
   legitimately omits the feature. Gate: parity suites green with new
   legs, or gap tickets filed naming the missing twin surface. This
   is the GPU OS's core promise — the shader path must not silently
   diverge from the oracle.

6. **GlyphRunner WGSL floor calibration** — floors_authoritative.json
   has NO entry for the GlyphRunner WGSL path (ledger ~:653: check_regime
   verdicts on that path are UNDETERMINABLE, recorded not waived).
   Extend calibrate_floors_authoritative.py with a real GlyphRunner
   step floor per the authoritative-file contract (12h window, real
   methods, readback-counted). Gate: floors file gains the entry;
   one GREEN + one RED check_regime leg re-run against it proving the
   verdict machinery can now ADMIT or REJECT on that path instead of
   UNDETERMINABLE.

Round-2 rule: items 5-6 are measurement/parity work on already-shipped
surfaces — they harden what exists rather than building ahead of use.
Queue stays empty again after these; next refill still waits on real
R5.3 use friction.

## CLAIM QUEUE ROUND 3 (Jericho-directed 2026-09-22 ~15:0x CDT) — seat
## verified the (d) residue is real at HEAD before filing. Same cadence.

7. **Pillar 3 (d) completion: delete the retired exemption machinery.**
   Seat measured at HEAD: ALL five data handlers (0x01/0x02/0x03/0x04/
   0x08/0x09) now read/write RAM — glyph_isa_v2.py arms verified directly
   (self.memory[] in every data path; paths go through _read_path
   single-view). IMAGE_SPACE_WRITE_SYSCALLS is down to {0x11: 1}, and
   0x11 is excluded-forever per DEFECT-27 — so the set can never fire
   for a migrating handler again. By the (A) ruling's own completion
   terms ("IMAGE_SPACE_WRITE_SYSCALLS + the FS-window exemption in the
   static check become obsolete and get deleted, not just narrowed"):
   remove the set, the in_fs_window exemption (:442), and the now-
   unreachable image_space_writes static-check branch; update
   tests/test_glyph_ram_pixel_space_check.py and the defect_d suite
   legs that seed "below the FS window" commentary. Gate: full
   defect_d + ram_pixel_space suites green post-deletion, WGSL twin
   untouched (it never had this host-side static check), 2109-test
   collection unchanged, one RED leg shown first (delete-then-test a
   pinned leg proves the suite notices).

8. **ABI spec twin-status truthing for the RUN-lane syscalls.**
   SYSCALL_ABI_SPEC.md marks 0x07 RUN and 0x12 RUN2 "twin: UNIMPLEMENTED"
   and 0x03/0x04 "twin: STUB" — named divergences. Task: write the
   WGSL-side parity story for the exec path specifically (the twin
   returns -1; is that CONTRACT or GAP for R5.3-era use?). Deliverable
   is a decision doc + spec edit, not shader code: for each RUN-lane
   syscall, either (a) codify "twin returns -1" as the normative twin
   contract in the spec (with the doc-rot guard leg asserting it), or
   (b) file a scoped ticket for the twin to implement a bounded form.
   Recommendation to evaluate: (a) for 0x07/0x12 (host process spawn
   is foreign to the shader threat model — containment is the Python
   engine's job), (b) for 0x03/0x04 file I/O IF glyph-sh v2 exec needs
   them on-shader, else (a). Gate: spec updated with rot-guard legs
   green, decision recorded here in the ledger, no engine code changed.

After 7-8: queue returns to empty. These two close out Pillar 3's
residue and make the ABI spec's twin column load-bearing truth — both
were already ruled/filed. Real supply after this still comes from the
R5.3 use log.

### 2026-09-21 ~18:3x CDT — R5.1 installer/launcher LANDED (PASS; builder af3e62239ce2, commit 5128c3eb)

- `glyphos_installer.py` at the repo root: ONE file (6.2 MB) = stdlib
  launcher + base64 gzipped payload (4.86 MB: 20 boot-chain modules +
  db/wordbase.db) + sha256 manifest. Integrity gate runs BEFORE
  extraction; boot happens in a per-run private temp dir (extract root
  AND extract_root/tools on sys.path — the modules import both as
  `tools.x` and bare `x`; first green run caught the missing second
  path, ModuleNotFoundError, fixed in embed template).
- Boot chain = the R3.1-gated chain: build_default_atlas →
  resident_image(mode="fleet", quantum 6) → GlyphRunner.run_wgsl →
  frozen words host-verified (0x5EED0005 @765, 0b1011 @717, results
  6/12/20/30, 458 steps). wordbase.db ships in the payload because
  OpcodeMapV2 colors are wordbase-derived (cross-machine bake
  determinism).
- RED legs at landing: --corrupt-verify exit 1 (manifest entry
  corrupted → PAYLOAD REJECTED pre-boot); torn-payload probe
  (.builder_queue/probe_r51_torn_payload.py + gate leg L5) exit 1 —
  one flipped bit in the embedded payload bytes → rejected, no boot
  (flipped byte happened to land in wordbase.db; manifest catches data
  tears same as code tears).
- Gates: test_r51_installer.py 5 passed in 4.62s (L1 skip-boot verify /
  L2 corrupt-manifest RED / L3 full boot / L4 --json exact words /
  L5 torn-payload RED); lane regression 38 passed
  (r41/r42/r43/conformance/glyph_run/gh26_fleet). Zero production
  lines changed. Force-adds: tests/test_r51_installer.py
  (.gitignore test_*.py), .builder_queue/payload_r51_manifest.json
  (*_manifest.json rule).
- Honesty (full list in RECEIPT_R51_installer.md): GlyphRunner
  substrate boot, NOT a kernel-image/virtio-pixel boot; THIS machine
  only (RTX 5090, wgpu 0.32.0) — no second-machine claim; payload is
  the boot chain, not the whole repo; per-run temp extraction, no
  persistent install UX; no rate claims → floors/check_regime N/A.
- Next rung: R5.2 stranger documentation, per roadmap order.

### 2026-09-21 ~18:0x CDT — R4.3 storage LANDED (PASS; builder af3e62239ce2, this commit)

- Host-side block-device seat over LANDED channels only (mailbox ABI +
  host backing file), CPU oracle. Zero production lines changed.
- Writeback contract load-bearing: dirty cache until FLUSH/unmount;
  atomic persistence (tmp + os.replace, R3.2 pattern); --no-flush RED
  shows the unflushed run REJECTED (backing file missing).
- ENOSPC-safe by construction: out-of-range sector → STATUS=1, guest
  continues, committed sectors intact; /home measured 98% full —
  capacity modeled in-contract, not borrowed from real disk.
- RED legs at landing (all before green, true exits): --no-flush exit 1;
  --torn-block exit 1 (0x44440008 vs 0x4444ff08, checksum rejects one
  flipped byte); --corrupt-verify exit 1. GREEN exit 0: 10 jobs, 523
  steps, 6 sectors persisted word-exact, read-back word-exact.
- Gate test_r43_storage.py 5 passed; lane regression 33 passed.
- Defect kept: guest log-append dead instruction (LOG_BASE → r4, ADD on
  r7 still holding 3296) let job 0's entry overwrite the count word;
  first RED fired for the wrong reason — fixed, legs re-verified.
- Honesty: no real block hardware; NO WGSL leg (per-step host hook gap
  same as R4.1); no filesystem layer; one word/sector exercised; no
  rate claims → floors/check_regime N/A.
- Next rung: R5.1 installer/launcher (P5), per roadmap order.

### 2026-09-21 ~17:5x CDT — R4.2 display frame LANDED (PASS; builder af3e62239ce2, commit 7a3c0c04)

- The whole machine RAM (16,384 words) IS one display frame: 128x128
  RGBA, Hilbert-mapped on the canonical vcc_validate curve, one word
  per pixel (32-bit RGBA, word MSB in red). Presented from the shader
  path's committed receipt["ram"] (fleet halts @458, R1.4-converged) —
  R4.2 needs no per-step host hook, so unlike R4.1 the WGSL path is
  the gated engine, not the gap.
- Decoded word-exact off the frame incl. frozen receipts; structural
  hash stable across re-encode (VCC determinism leg).
- RED legs at landing (before any green): --corrupt-verify exit 1;
  --torn-frame exit 1 (single-byte tear of pixel word 765 detected,
  0x5E→0xA1). Gate 5 legs incl. curve-sensitivity non-vacuity: LINEAR
  (non-Hilbert) placement FAILS the decoder — the gate cannot pass on
  an arbitrary mapping. Gate 5 passed; lane regression 38 passed.
- Zero production lines changed (probe + gate + receipt only).
- Defect kept: first codec draft packed 24-bit (BK-2 readback
  convention) — word 765 read 0x00ED0005 off the frame, caught by the
  probe's own frozen-word check; fixed to 32-bit RGBA. BK-2 is a
  READBACK convention, not a presentation contract.
- Honesty: host-presented frame over committed RAM; NO display
  hardware/scanout claimed; the guest does NOT paint its own
  framebuffer (future work); no rate claims → floors/check_regime N/A.
- Next rung: R4.3 storage (block device, writeback contract,
  ENOSPC-safe), per roadmap order.

### 2026-09-21 ~17:4x CDT — R4.1 input mailbox LANDED (PASS; builder af3e62239ce2, commit d8bf6cf7)

- Device seat → guest daemon → host-verified log, over LANDED channels
  only (mailbox ABI = R1.1 arrive mechanism). Zero production lines
  changed.
- RED legs at landing: --corrupt-verify exit 1 (verifier rejects good
  log); --drop-event exit 1 (dropped event detected against the full
  8-event contract — after fixing a vacuously-green trim of the
  verifier's own expectations, recorded in the receipt).
- Defects kept in receipt: zero-const register holding an address;
  poll budget decrementing only on the claim path; the vacuous drop
  leg. All in-probe; no production lines touched.
- Honesty: no WGSL leg (run_wgsl has no per-step host hook — the same
  gap R3.3's per-chunk-fresh-runner honesty note anticipated); no
  device hardware; event-record layout is a probe contract, NOT a
  BOX_ABI_v2 surface change (promoting it would need a version bump).
- Next rung: R4.2 display output (VCC-preserving), per roadmap order.

### 2026-09-21 — R3.2 persistence LANDED (gate PASS via container; builder af3e62239ce2, this commit)

- `.builder_queue/probe_r32_persistence.py`: freeze (R3.1 fleet halt
  @458 steps) → GPX1 container (magic `GPX1`, JSON header, sha256
  payload checksum; 64 KB RAM + 32 regs + image; ATOMIC write tmp +
  os.replace) → POWER OFF (runner object dropped) → restore into a
  fresh GlyphRunner from container bytes → frozen fleet words
  host-verified (765=0x5EED0005, 717=0b1011, 731=0xFA026, results
  714:6/728:12/748:20/763:30). Zero production lines changed.
- RED legs at landing (both before any green): --corrupt-verify exit 1
  (verifier rejects the good restore); --corrupt-container exit 1
  (flipped payload byte → checksum rejection = torn-write detection).
  Crash-mid-write analogue: leftover .tmp ignored, container intact.
  GREEN: exit 0 (/tmp/r32_red1.log, r32_red2.log, r32_green.log).
- Blockage pre-registration OVERRIDDEN with reasoning, disclosed: the
  substrate has no power-cycle primitive (run_wgsl builds buffers per
  call, runner.py:133-186), but the rung text names "PXC1/VAC
  CONTAINERS or writeback" — a container is buildable host-side
  without new substrate capability. Full reasoning + non-proof list:
  RECEIPT_R32_persistence.md. honesty: kill -9 is an analogue
  (atomic write); resume-from-snapshot execution NOT claimed.
- Regression: conformance + glyph_run + fleet suites 24 passed.
- Next rung: R3.3 host integration.

### 2026-09-21 ~16:5x CDT — R3.1 cold boot LANDED (PASS, measured; builder af3e62239ce2, this commit)

- **Cold boot to fleet-ready: 814.0 ms** vs the 60,000 ms budget
  (73.7x margin). Chain: atlas ~30 ms → fleet bake ~6-12 ms → runner
  init ~0.1 ms → run_wgsl 777.3 ms cold (wgpu pipeline creation) /
  458 steps → halt; frozen words host-verified from receipt["ram"]:
  0x5EED0005 @765, done 0b1011 @717, 0xFA026 @731, results
  {714:6, 728:12, 748:20, 763:30}. Warm reps ~86 ms (pipeline reuse)
  reported, NOT gated.
- RED legs at landing: `--budget-ms 500` exit 1 (real threshold miss,
  785.2 ms); `--corrupt-verify` exit 1 (corrupted verifier REJECTS the
  good boot — readiness check load-bearing). Process note: first
  corrupt-verify run piped through tail masked its exit; re-run with
  file redirection, true exit captured.
- Zero production lines changed — measurement over LANDED artifacts
  (agent_resident/runner/baker/atlas/wgsl untouched at HEAD cee0d963).
- Floors: floors_authoritative.json fresh (~0.1h); LEG boot-shaped
  (563 steps/s, 1,777.2 us/rep from THIS leg's wall-clock + steps, per
  the R1.3 receipt-hygiene lesson); check_regime on receipt PASS
  (2.78x above glyphrunner_wgsl_step floor 639.1 us → ADMISSIBLE;
  honest: cold leg includes bake+init+pipeline creation).
- Honesty: this is the GlyphRunner substrate's cold boot to a verified
  fleet workload — NOT a kernel-image boot, NOT the virtio-pixel
  guest. Single image family, single host/GPU. Full list:
  RECEIPT_R31_coldboot.md.
- Next rung: R3.2 persistence (power-cycle survival + kill -9 RED
  leg). Pre-registered expectation: BLOCKED — the substrate has no
  persistence mechanism yet; log the missing artifact, land adjacent
  non-blocked work or nothing, never fake the capability.

### 2026-09-21 ~16:4x CDT — R1.4 WGSL fleet convergence LANDED (PASS; builder af3e62239ce2, this commit)

- **The shader path now runs the R1.2 fleet to completion:** halt @458,
  results {714:6, 728:12, 748:20, 763:30} = RES_FLEET_EXPECT (R1.3 task
  parity), receipt 0x5EED0005 @765, done 0b1011 @717, E-K1 0xFA026 @731,
  all host-verified from run_wgsl receipt["ram"]. RED leg shown first:
  pre-fix shader halts @153 all-zeros, probe exit 1; converged exit 0.
- Provenance disclosed: core shader diff (RAM-first LD/ST unpaged,
  E-K1 fault vectoring, GH-16 tick delivery, DEFECT-18 JMPR restore)
  found UNCOMMITTED on the tree (~18 min quiet); adopted per the R1.2
  in-flight precedent, not restarted. This session added the four
  paged-path parity fixes the adopted diff still needed (bisected from
  5 landed-gate regressions): RAM-first PT tag check (check_pt_tag
  twin, glyph_isa_v2.py:88-95), plain-frame LD via RAM (twin :920-922),
  PTE_PIX routing + plain-frame ST to RAM (twin :1009-1049); JMPR
  scaling was bisected-clear, kept.
- Ruling item 3 (ADD not swap): test_box_abi_conformance.py legs 8-11
  drive run_wgsl over the frozen contracts — ABI word 952, full frozen
  map at shader halt, WF-1 on/off preemption equivalence (quantum 6 vs
  0 byte-identical frozen words, 458 vs 378 steps), corrupted-
  expectation RED. 11 passed (was 7).
- WF-1: tests/test_wf1_tick_claim_bound.py DELETED per its own
  pre-registered deletion instruction — L1 was observed RED on the real
  diff before deletion (the guard worked); delivery criteria now gated
  by conformance leg 10 + leg 9 + probe exit contract. RULING_WF1
  option (ii) complete.
- Stale test channels updated (engines now agree in RAM): bk1 leg 4
  argv seed via run_wgsl(ram_seed=...) mirroring the CPU leg; bk1/bk2
  word parity read the RAM view, both sides masked 24-bit. Triple-sync
  copies re-synced (that gate's own instruction).
- Probe exit contract added: .builder_queue/probe_r13_wgsl_fleet.py
  exit 0 MATCH / exit 1 DIVERGENT-no-RAM (was print-only).
- Gates: probe RED exit 1 / GREEN exit 0; conformance 11 passed; lane +
  WGSL family regression 114 passed 0 failed (exit 0 captured). Known
  NOT-mine pre-existing: 8 defect_d audio failures (scipy missing in
  env; identical with diff stashed).
- Honesty: parity proven over frozen ABI words + registers + standing
  parity suites on this image family, NOT instruction-exact equivalence;
  OOB-ST drop delta remains (CPU faults, shader drops — CPU-only
  vectoring); GO-2 tile predicate NOT mirrored (never armed on these
  images); no rate claims → floors/check_regime N/A. Full list:
  RECEIPT_R14_wgsl_convergence.md.
- Next rung: R2.x per PRODUCT_ROADMAP.md (R2.3 unblocked; re-verify HEAD
  first — parallel sessions land rungs mid-flight).

### 2026-09-21 ~15:2x CDT — R2.2 toolchain UX landed (builder af3e62239ce2, this commit)

- `tools/glyph_run.py`: ONE command — `.glyph` source → baked
  `.glyph.png` artifact → executed → receipt with exit-code contract
  (0 HALT / 1 fault / 2 assemble / 3 budget / 4 I/O; `--json`).
  Artifact-only mode re-runs a baked image with no source present —
  the artifact IS the program. Composition layer only: zero lines
  changed in baker/runner/glyph_isa_v2/agent_resident.
- Worked example `examples/sum_1_to_5.glyph` (stranger flow verified
  live: source run AND artifact-only run both `result: HALT,
  output: 15`, 37 steps).
- Gate `tests/test_glyph_run.py` 8 legs (5 GREEN / 3 RED), force-added
  past .gitignore: source→HALT→15; artifact-only; .npy round-trip;
  --json keys; RED: bad source exit 2 + no artifact; budget exit 3;
  corrupted-first-instruction artifact produces NO 15; missing file
  exit 4. Lane regression 45 passed (conformance/fleet/arrive/queue/
  resident/shell).
- RED-first: pre-green run caught PRT stdout polluting --json (fixed:
  capture engine stdout); landing-time RED probe first corrupted HALT
  (failed to discriminate — unknown-opcode halt is by-design), caught by
  its own assertion, rewritten to corrupt instruction 0. Both recorded.
- Honesty: CPU oracle only (no WGSL parity claim — twin divergence
  still open); plain single-box path (frozen ABI engines shared, ABI
  supervisor not exercised); no rate claims → floors/check_regime N/A;
  fault exit (1) covered by R2.1 suite, not duplicated here.
- Receipt: RECEIPT_R22_toolchain_ux.md. Next rung: R2.3 (C/Rust via
  RV32 target, round-trip receipts).

### 2026-09-21 ~15:0x CDT — R2.1 box-ABI freeze landed (builder af3e62239ce2, this commit)

- `docs/BOX_ABI_v2.md` FROZEN: version 0x00020026 (word 952), register
  marshaling (r17/r10/r11, Bug-7), MMIO block @0x8000 full offsets, E-K1
  predicate semantics (unset HI never matches; LD unchecked), complete RAM
  map, GH-22 mailbox format + check vector 0x3B00112A, arrival contract,
  frozen receipts (0x5EED0003/4/5, 0xFA026, 0xCAFE0026), change policy,
  honesty §7. Extracted from the LANDED code (agent_resident /
  glyph_isa_v2 / baker / geos_emit), not invented.
- `tests/test_box_abi_conformance.py` 7 legs: 5 GREEN (ABI+status words at
  halt from the real baked image; memory-map frozen words at fleet halt;
  mailbox format incl. malformed-op rejection; E-K1 predicate on the real
  engine with unset-range confinement; no-post-no-receipt arrival) + 2
  in-process RED (corrupted memory-map expectations fail; corrupted check
  vector fails).
- Gates: conformance 7 passed (after RED-first: 1 failed — my probe read
  word 750 before any step executed; spec right, probe wrong, fixed);
  lane regression fleet/arrive/queue/resident/conformance 29 passed.
  Receipt: RECEIPT_R21_box_abi.md (full RED→GREEN tails, exclusions).
- Honesty: zero production lines changed (doc + test only); no rate
  claims (check_regime N/A); full-repo pytest has 39 PRE-EXISTING
  collection errors (audio deps missing in env) — unrelated, lane suites
  green.
- Next rung: R2.2 toolchain UX (one command → glyph/tile artifact, run).
  Open defect carried: WGSL twin divergence (largest lane defect).

### 2026-09-21 ~14:5x CDT — R1.3 PASS (P1 kill switch evaluated, builder af3e62239ce2)

**VERDICT: PASS.** Tie on failure rate (GPU 0/40 batches vs Ubuntu
sandboxed 0/40, two probe runs) + win on wall-clock (0.86 ms vs
~1,108 ms per 4-task batch, ~1,290x). Cost = tie (local compute both
lanes). P1 thesis CONFIRMED → P2 next tick (R2.1 box-ABI freeze).

- Task parity enforced: both lanes 4 tenants, seeds 2/3/4/5, y=x·(x+1)
  (exactly RES_FLEET_EXPECT), adversarial C stores 0xDEAD at B's slot.
  GPU lane ran the LANDED R1.2 fleet image unmodified at HEAD a3aa30a8
  (agent_resident.py untouched).
- Controls all bite: --corrupt (expectations rejected), --naive
  (in-guest store LANDS without per-leg arming), Ubuntu no-isolation
  shared-mem control (corruption landed 20/20 — the sandboxed lane's
  clean leg is its kernel address spaces, journal `11/SEGV` on C).
- HONESTY (receipt has the full list): CPU-oracle substrate, NOT the
  WGSL shader path — probe_r13_wgsl_fleet.py: fleet halts @153, ram765=0,
  **DIVERGENT** (shader-path convergence is now the lane's largest open
  defect). No calibrated floor for this path (floors_authoritative is a
  different code path) — LEG lines are same-process symmetric
  wall-clocks, not floor-derived rates. Sandbox overhead is per-tenant
  fixed; extrapolation beyond this workload shape not made.
- Probe-defect record: first draft had task parity wrong (x*3,
  misattributed communicate() outputs) — rewritten BEFORE any verdict;
  recorded in the receipt because R1.3 is the rung where a parity slip
  would have decided the project on a comparison that never happened.
- Gates: probe GREEN exit 0 (x3 runs); RED legs --corrupt/--naive exit
  0 with rejection lines (contract per brief); check_regime on the
  formal capture PASS 3/3 (margins honest-caveated); full GH-26
  regression 27 passed in 1.78s.
- Full chain: RECEIPT_R13_preference.md · brief_r13_preference.md ·
  probe_r13_preference.py · probe_r13_wgsl_fleet.py.

### 2026-09-21 ~10:26 CDT — lane seeded by orchestrator seat
- Roadmap ratified at 1827f6cb; R1.3 amended (failure rate load-bearing +
  one of {wall-clock, cost}).
- Builder af3e62239ce2 redirected to PRODUCT_ROADMAP.md (was: PS-series,
  closed by RULING_ps012 — idle-on-record).
- 2h lane b0f0eb15a225 paused pending verified redirect.
- Next: first builder tick reads this file, starts R1.1 (expected:
  blockage log / adjacent work per pre-registration above).

### 2026-09-21 ~11:40 CDT — GlyphRunner WGSL floors landed (builder af3e62239ce2)
- Pre-registered unblock from the queue-drain step executed:
  `calibrate_floors_authoritative.py` extended (additive) with TWO
  GlyphRunner-path floors — `glyphrunner_wgsl_step` 639.1 µs (spaced
  latency) and `glyphrunner_wgsl_step_tput` 70.3 µs (tight-loop
  throughput, real resident image). Receipt:
  RECEIPT_floors_glyphrunner_extension.md.
- Root cause of the old INADMISSIBLE (measured via falsifier probes): the
  receipt leg was tight-loop THROUGHPUT, the only floor was spaced
  LATENCY — a category error, now adjudicable apples-to-apples.
  check_regime: GREEN 1.56x ADMISSIBLE; RED legs — corrupt expectations
  exit 1, same number vs wrong floor 0.14x INADMISSIBLE exit 1.
- probe LEG line now cites the tput path. All 33 gate tests pass.
- R1.1 status UNCHANGED (gate already PASS at 982c24c3); residual gap:
  post-boot job arrival. Next unit: post-boot job arrival at a running
  supervisor (mailbox receive-while-busy), then R1.2 fleet.
- WGSL twin divergence (halt@198, result 0x0) unchanged, still ungated.

### 2026-09-21 ~14:00 CDT — R1.2 fleet landed (builder af3e62239ce2, this commit)
- Found the fleet work IN FLIGHT on the tree (agent_resident.py dirty,
  brief + throwaway probes present, no gate/receipt): debugged instead
  of restarting. Two real defects:
  1. `_fleet_packed` (agent_resident.py:709) lstripped the label's
     colon; coords keys KEEP it → lookup always missed → every agent
     exit KJMP targeted PC 0 → kernel reboot loop (200K steps, never
     halts, all fleet words 0). One-token fix.
  2. Last agent's exit wired to :__fleetfin, skipping its own
     :__fret3 promote block → bit3 of 717 never lit (done=0b0011).
     Fix: every agent returns to its own :__fret<slot>; fret3 falls
     through to :__fleetfin as the layout already arranged.
- Fleet result: A=6/B=12/C=20/D=30 no contamination; C's adversarial
  USER store of 0xDEAD to B's 728 E-K1-suppressed (receipt 0xFA026
  @731, C reaped, done=0b1011); fleetnaive control: store LANDS
  (728=0xDEAD, done=0b1111) — the falsifiable isolation pair.
  Halt at step 434, 7 preemption ticks at quantum 6, status
  0xCAFE0026, fleet receipt 0x5EED0005 @765.
- Gates: test_gh26_fleet.py 5 passed (isolation / naive control /
  corrupt-expectation RED in-process / preemption non-vacuity /
  naive-must-corrupt); full regression 38 passed; probe GREEN exit 0,
  --corrupt RED exit 1, --naive-clean-expected RED exit 1; linter
  0 errors (1 capacity warning, informational); RED-first shown
  (pre-fix smoke tail + pytest caught the new gate's own inverted
  assertion before any green — 1 failed, 4 passed).
- Honesty: read isolation NOT claimed (LD unboxed); time-multiplexed
  co-resident (one PC), not parallel; supervisor = in-guest kernel,
  seat still host; no rate claims → floor line N/A, check_regime N/A
  with that reason.
- Next rung: R1.3 preference measurement (P1.3 kill switch — amended
  gate: failure rate load-bearing + one of {wall-clock, cost}).
- Full chain: RECEIPT_R12_fleet.md · brief_r12_fleet.md
  (tools/check_brief.py PASS).

### 2026-09-21 ~12:1x CDT — R1.1 post-boot arrival landed (builder af3e62239ce2, this commit)
- `agent_resident.py` mode="arrive" (additive): BOX0's daemon drains
  the seeded queue VERBATIM (queue-mode semantics carry over), then
  stays LIVE in a bounded wait loop (2000 polls, flag @742). The
  supervisor seat posts a job POST-boot (host RAM write between
  step() calls — the mailbox ABI); daemon claims (flag→0), triples
  in place @760, receipt 0x5EED0004 @761. Arrival serviced at guest
  step 443 (post landed mid-wait at 261). All new words inside BOX2.
- Gates: test_gh26_arrive.py 5 passed (incl. preemption quantum=6 leg
  and no-post leg: silent seat → NO receipt, clean timeout at step
  30403); full regression 33 passed; probe GREEN exit 0 / --corrupt
  RED exit 1 / --no-post RED exit 1 (forged-receipt rejection
  demonstrated); linter 0 errors.
- Receipt honesty: the seat is still the HOST (teleop form of
  "supervised by the seat"); an IN-GUEST supervisor is NOT claimed —
  open for R1.2 scoping. No rate claims, floor line N/A with that
  reason (floors fresh from 80d9285f but nothing here quotes one).
- R1.1 gate (one full agent task, host-verified) now covered on BOTH
  halves: seeded work (982c24c3) AND post-boot arrival (this commit).
  Next unit: R1.2 fleet — ≥4 concurrent isolated agents, cross-tile
  fault-injection RED leg required (policy rule 4). Decide there
  whether the supervisor moves in-guest.
- Full chain: RECEIPT_R11_arrive.md · brief_r11_arrive.md
  (check_brief PASS).

### 2026-09-21 ~11:1x CDT — R1.1 queue-drain step landed (builder af3e62239ce2, 982c24c3)
- `agent_resident.py` mode="queue" (additive, +139/−1): BOX0 daemon
  drains a kernel-seeded job queue IN-GUEST under GH-16 preemption —
  depth @740 drains 3→0 in memory, results @756..758, receipt
  0x5EED0003 @759, host verifies word-by-word post-hoc (no post-boot
  host writes). All queue words inside BOX2 [736,768).
- Gates: test_gh26_task_queue.py 4 passed; full regression 29 passed;
  probe GREEN exit 0 / --corrupt RED exit 1; linter 0 errors.
- Floor honesty: GlyphRunner WGSL path has NO calibrated floor
  (floors_authoritative 'step' = SpatialRV32ICore.step, 4
  readbacks/call — different code path). check_regime INADMISSIBLE
  (0.02x) recorded as the expected datum; verdict UNDETERMINABLE, not
  waived. Unblock: extend calibrate_floors_authoritative.py (ticket,
  next session).
- R1.1 residual gap now: post-boot job ARRIVAL at a running supervisor
  (queue drain ≠ mailbox receive-while-busy). That + the floor
  extension are the natural next units; R1.2 (≥4 agents) after.
- Full chain: RECEIPT_R11_task_queue.md · brief_r11_task_queue.md
  (check_brief PASS).

### 2026-09-21 ~10:49 CDT — floors authority landed (seat lane, Jericho-decided)
- `.builder_queue/floors_authoritative.json` is the ONLY citable floors
  file (12h window; real SpatialRV32ICore methods, 4 readbacks/step).
  Full chain: RECEIPT_floor_reconciliation.md.
- CITATION BAN: 6.15x / 1.42x / 0.45x are history, not working numbers.
- R0's FABRICATED charge is VOID; RULING_ps009_fork_cleared_ps010_go
  stands as issued (never actually edited).
- check_regime.py now reads the authoritative file. Gate re-verified
  10:49: GREEN 1.07x admissible / RED 0.06x + 0.09x inadmissible (the
  exact legs R0 had called admissible).
- Never re-run the proxy calibrate_floors.py for gate purposes.

### 2026-09-22 ~11:5x CDT — instrument fix, no rung change (builder af3e62239ce2, commit 3a15d6c7)

Phantom-stall repair on the loop's own monitor, landed BETWEEN rungs (the
claim queue is EMPTY and this entry claims no roadmap work):

- OBSERVED: fingerprint flipped DIRTY_ACTIVE -> FROZEN_STALLED_T1 while the
  lane idled legitimately. Non-exempt dirty set: .update_proposals.log
  (appended every ~5min by the live llama3.1 update-proposal watcher) +
  .venv/bin/{normalizer,numba} (shebang python3.11->python3 from the
  09-22 env-repair reinstall). Left armed, the tier climbs to T3 and the
  auto-stash circuit breaker fires on a cleanly-idling tree.
- FIX (tools/glyph_build_chain_monitor.py RUNTIME_EXEMPT_FILES): exempt all
  three, same class as the 09-19 pass (055fadea). The log file is
  .gitignore'd (line 96) but tracked from before the rule.
- Gates: RED shown pre-fix (tracked_dirty=3, FROZEN_STALLED_T1 on 1h40m
  stale churn mtimes); GREEN post-fix — hygiene gate 6 passed incl. new L6
  pin (churn-only tree -> tracked_dirty==0); live monitor now
  tracked_dirty=2 DIRTY_ACTIVE (the two committed fix files themselves).
- Shim re-pointed: ~/.hermes/scripts/glyph_build_chain_monitor.py now
  runpy-executes the versioned twin (cron's monitor_script resolves there),
  so the live 2m tick and the gated source can no longer diverge.
- NOT done / honesty: no rung claimed, queue still empty, lane still waits
  for Jericho's next approved item or ruling. No WGSL, no transpiler, no
  floors numbers touched.

### 2026-09-22 ~13:3x CDT — claim-queue item 5 LANDED (builder af3e62239ce2): WGSL parity sweep of the 09-22 deltas

- REAL DEFECT found and fixed: the WGSL shader had OPCODE_CALLR in its
  opcode table but NO dispatch branch — computed calls (the 2f619963
  `jalr ra,N(ra)` -> CALLR r30 lowering) were silent no-op fallthroughs
  on the shader path only. Fixed as a bitwise twin of
  glyph_isa_v2.py:1279; mirrors md5-synced to
  glyph_dispatch/src/glyph/ and glyph_dispatch/src/.
- RED shown pre-fix (WGSL r10=0x0 vs CPU 0x2a; gate 1 failed),
  GREEN post-fix (both 0x2a; gh4 suite 4 passed). Full evidence +
  what-PASS-does-not-prove: RECEIPT_item5_wgsl_parity_sweep.md.
- Other three deltas dispositioned: 0x10 and CMP3/JLT/JGT twins were
  landed same-commit with parity legs (covered); _read_path has no
  WGSL-visible surface (FILE_READ/WRITE arms are pinned no-op stubs) —
  documented as a prose gap ticket in the receipt.
- Regression sweep: 34 (5 parity suites) + 41 (defect_d/gh4/bk12/
  validation) + 9 (glyph_cc) + 2 (rv64i proc/arithshift) + 23
  (read_path + rotguard) — all passed.
- Item 6 (GlyphRunner WGSL floor calibration) remains OPEN — next tick.


## CLAIM QUEUE ROUND 4 (2026-09-22 ~17:3x CDT, seat lane, from DTF-1 follow-through gap)

Context: DTF-1 closed (f9efccc3) with a sound receipt, but the human entry
point was not repointed — experiments/glyph_interactive_shell.py:649-651 still
runs `repl(lines=None)` which defaults to build_shell() (always-echo, line 622).
Live-verified post-commit: `e hi` echoes instead of dispatching. Jericho sat at
this exact script for his day-1 entry; if he sat again today, DTF-1 would be
invisible to him. Mechanism landed, surface did not.

9. REPOINT the human surface: __main__ in experiments/glyph_interactive_shell.py
   must default to build_dispatch_shell(...) (DTF-1's write/audio paths), keep
   `quit` working, update the startup banner to name the four commands
   (e/s/w/r) so a first-time user knows what to type — the day-1 finding was
   literally "I don't know what to type."
   Gate: (a) RED-first — current tree, `printf 'w hello\nr\n' | python3
   experiments/glyph_interactive_shell.py` shows echo-not-dispatch (already
   demonstrated 2026-09-22, cite this line); (b) GREEN — same pipe post-fix
   shows the file written + read back, and `s testing` produces decodable
   audio; (c) `quit` exits cleanly; (d) full DTF-1 gate re-run green
   (tests/test_glyph_app_shell_dispatch.py + harness + isa regressions);
   (e) batch invariant intact (batch mode never touches stdin).
   Receipt: RECEIPT_DTF1_repoint_entry.md with before/after transcripts of the
   exact pipe from leg (a). This item completes DTF-1's intent; do not count
   the floor's day-2 readiness until it lands.

## CLAIM QUEUE ROUND 5 (2026-09-22 ~18:0x CDT, seat lane, "you lead" delegation) — ITEM 10 LANDED 2026-09-22 ~20:1x (commit follows this line in git log; receipt RECEIPT_DTF2_text_console.md)

Supply detail: .builder_queue/SUPPLY_ROUND5.json (item 10 brief + gate).

10. ✅ DONE (2026-09-22 ~20:1x). DTF-2: in-image text console. Render the PRT byte stream
    (GlyphCPUv2.output, glyph_isa_v2.py:586/1075) into a reserved band of the
    observation image using the existing VGA 8x16 font
    (tools/vga_font_8x16.py, render_text_with_vga_font) so the shell session
    is visible ON the GPU screen. Bounded row-ring for scrolling (glass-TTY
    boundary per the amendment — no blitter claims). Wire the shell's
    per-turn transcript (item 9 entry point) into the renderer; persist band
    as PNG via existing container paths.
    Gate: RED-first blank-sentinel band read; GREEN (a) band pixels decode
    back to the exact transcript string glyph-side (pixel-perfect matcher,
    not host print); (b) WGSL twin band byte-identical for the same byte
    stream; (c) engine + twin + shell-dispatch regressions green; (d) batch
    invariant intact. Receipt: RECEIPT_DTF2_text_console.md.

After item 10: queue returns to empty. DTF-3 (FS grow) is next supply,
planned next round.

## CLAIM QUEUE ROUND 6 (2026-09-23 ~07:4x CDT, seat lane — from Jericho's day-2 landmine flag, live-reproduced)

Jericho flagged it, I reproduced it live at HEAD (17d47586):

11. DISPATCH GRAMMAR COLLISION: natural sentences are silently misexecuted.
    `what time is it` → parsed as `w` + `hat time is it`, silently WRITTEN to
    /tmp/glyph_sh_write.dat. `seems fine to me` → parsed as `s`, the shell
    SPOKE "eems fine to me" out loud (decoded from the produced WAV). `read
    me the news` / `run the tests` / `explain...` all echo their tails with no
    error. Day-1's echo shell was unhelpful but honest; this version silently
    executes the wrong command for most English sentences. This is precisely
    the batch-unassertable usability class the agent-pre-verification clause
    named — and it played out for real.
    Fix (either or both, implementer's choice documented in receipt):
    (a) required delimiter — first byte must be the command, SECOND byte must
    be a space; `w`+non-space falls through to unknown; or (b) unknown-first-
    -word fallback — any line whose parse doesn't match `<cmd><space>` shape
    produces ERR:UNKNOWN_CMD with the offending line echoed, never silent
    consumption.
    Gate: RED-first — current tree, the three live pipes above (what time is
    it / seems fine to me / read me the news) show silent misexecution (cite
    receipt); GREEN — same pipes produce ERR:UNKNOWN_CMD (named, with line
    echoed), file NOT written, audio NOT produced; legitimate commands
    (`w x`, `w  x`? — define and document single-vs-multi space convention)
    still work; unknown single char `z foo` still errors loudly; full
    dispatch + harness + ISA regressions green; batch invariant intact.
    Receipt: RECEIPT_item11_dispatch_grammar.md with before/after for each
    natural-sentence pipe.

After item 11: queue returns to empty. BK-16 (clock) stays backlog until
Jericho ratifies; the grammar fix is NOT a substitute for it.

### 2026-09-23 ~08:3x CDT — ROUND-6 item 11 COMPLETE: dispatch grammar collision fixed (builder af3e62239ce2)

- Mailbox check first: no RULING_* newer than this supply's commit
  (newest landing 154d0700 = the supply itself; RULING_R53_disposition
  07:5x is recorded below and affects R5.3 only — no conflict with item
  11's work). STATUS ACTIVE. Claimed item 11, the only queue entry.
- Fix implemented as option (a)+(b) combined, IN the glyph program
  (experiments/glyph_interactive_shell.py build_dispatch_shell): length
  read from INPUT_LEN word (per-turn authoritative), bare-'r'-only rule,
  byte-2-must-be-space rule peeking the harness input ring directly
  (word 8289 — NOT the 0x02 scratch buffer, which consumes ring bytes and
  can never be re-read). Payload = all bytes after byte 0, verbatim
  ('w  x' writes '  x'). Help text documents the contract. Engine,
  syscall arms, WGSL twin untouched — additive experiment-shell asm only.
- Landing defect kept (disclosed): first draft peeked RAM word 701 (the
  scratch buffer + 1) instead of ring word 8289 — G4/G5 went RED because
  the peek read an empty scratch word, not the delimiter. Root-caused via
  pixel-level decode of the assembled rows + step trace; fixed to the
  ring-address peek before any landing.
- Gate arc (this tick, one process): RED pre-fix 4 failed/4 passed;
  stash-discrimination RED (fix stashed → same 4/4, popped → 8/8);
  GREEN 8 passed (tests/test_item11_dispatch_grammar.py, NEW,
  force-added past .gitignore). RED probe
  probe_item11_grammar_red.py exit 1→0. Transcript
  transcript_item11_grammar.py PASS exit 0 with all four after-pipes.
- Regression: SE020/shell/console 25 passed; extended family 40 passed;
  standing DTF transcripts re-run exit 0 (floor + DTF1); live batch pipe
  through __main__ exit 0. Receipt:
  RECEIPT_item11_dispatch_grammar.md (before/after per pipe pasted).
- Honesty: no WGSL claim (the twin never runs this program); no floors/
  rate claims → rule-1 N/A; typo-suggestion out of scope; BK-16
  untouched per the supply item's own note.
- NOT done: PRODUCT_ROADMAP status lines (R5.3 waiver is the seat lane's
  recording, not re-verified here); queue now empty — next supply per
  the standing channels.

## RULING_R53_disposition (2026-09-23 ~07:5x CDT — Jericho-directed via seat lane)

Jericho's verbatim direction: "i dont want to have to answer any questions or
do the 30 day thing. please just make the software."

Disposition per the roadmap's own terms: R5.3 (30-day use gate) is
operator-waived. The gate's purpose was forcing-function — preventing the
lane from building ahead of anyone living in the product. That purpose is
now served by the ratified desktop-floor bar (AMENDMENT_DTF1) and direct
operator direction; the operator has explicitly re-pointed the work at
building. R5.3 is recorded WAIVED-BY-OPERATOR (not failed, not passed) in
PRODUCT_ROADMAP.md; PRODUCT_ROADMAP.md P5's launch criterion becomes
"desktop floor complete (DTF-1..4) + agent pre-verification receipt."

Operator also directed: no questions. The seat lane stops surfacing R5.3,
BK ratifications, and decision requests in reports. Supply continues:
seat lane files rounds directly under the standing delegation
(POLICY_decision_delegation_20260918), backlog ratification authority
delegated to the seat lane for the desktop-floor duration. Jericho
reviews by reading receipts whenever he chooses; nothing waits on him.

## CLAIM QUEUE ROUND 7 (2026-09-23 ~09:0x CDT, seat lane, build-only mode)

Supply detail: .builder_queue/SUPPLY_ROUND7.json.

12. DTF-3: FS grow — BK-7's gate binding as written (append 2x, read whole
    byte-exact, hole reuse). RED-first. Prereq for DTF-4.
    → RESOLVED 2026-09-23 ~12:0x: VERIFIED PRE-EXISTING (see Current rung +
    session log; same precedent as item 4).
13. BK-19: VGA font atlas completion (10 missing printable-ASCII glyphs).
    Operator spot-checked the gap live — the console shows '?' for brackets
    today. RED-first on the ?-substitution, GREEN on exact 95-glyph decode,
    twin band parity, regressions green.
    → LANDED 2026-09-23 ~13:1x (see Current rung + RECEIPT_BK19_font_atlas.md).

After 12-13: queue empty; DTF-4 (BK-11 coreutils) next, then BK-18
(sharded suite runner) before further suite-wide work.

### 2026-09-23 ~13:1x CDT — ROUND-7 item 13 COMPLETE: BK-19 font atlas landed (builder af3e62239ce2)

- Mailbox check first: STATUS ACTIVE; no RULING_* newer than the last
  landing (newest RULING mtimes 2026-09-22 20:38 vs HEAD 12db395a
  2026-09-23 11:27); monitor CLEAN, queue=0. Claimed item 13 (lowest
  open; item 12 resolved last tick).
- Landed: 10 canonical VGA glyphs in tools/vga_font_8x16.py (kernel
  font_8x16.c extraction, collision-free vs all 85 existing patterns),
  coverage docs 85→95 (glyph_text_console.py:19-22, font header),
  new gate tests/test_bk19_font_atlas.py (8 legs, force-added),
  one disclosed test-hygiene edit in test_glyph_text_console.py:72-80
  ('[' → '€' in the ?-substitution leg; the old input is in the font now).
- Gate arc: RED 5F/3P at 12db395a (WGSL leg RED shows the live defect
  `?code??sample?`); stash-discrimination RED; GREEN 8/8; console+atlas
  19; extended family 74 passed; live pipe exit 0. Receipt:
  RECEIPT_BK19_font_atlas.md. Rule-1 floors N/A (no rate claims).
- NOT done: DTF-4/BK-11 (next supply), BK-18, BK-16, kernel-font
  reconciliation of the 38 pre-existing glyph divergences (out of scope,
  ADD-don't-swap). Queue EMPTY — supply-wait resumes next tick.

### 2026-09-23 ~20:4x CDT — VERIFICATION tick: seat lane's glyph_desktop.py (abced965) re-measured at HEAD (builder af3e62239ce2)

- Mailbox check first: monitor delta = seat lane commit abced965
  (glyph_desktop.py, Tk GUI wrapper for the dispatch shell, 192 lines);
  no RULING_* newer than 2026-09-22 20:38; CLAIM QUEUE EMPTY (rounds 1-7
  closed); STATUS ACTIVE; queue=0.
- The landing is SMOKE-ONLY (no test file landed; commit message claims a
  6s on-:1 Tk window + headless smoke). This tick re-measured the
  headless engine path — the desktop's exact import path and call chain
  (glyph_desktop.py:34-41 imports build_dispatch_shell/run_turn/GlyphCPUv2;
  :145/:150 are run_turn + console.feed_bytes) — at HEAD abced965:
  GREEN (probe /tmp/probe_desktop_headless.py, this process): L1 headless
  import OK; L2 'e hello desktop' → ' hello desktop'; L3 'w desktop
  probe' → PRT empty (w acts, doesn't echo — the landed contract, which a
  first-draft expectation got WRONG and the machine corrected: FILE_WRITE
  14 bytes, disk = b' desktop probe'); L4 'r' → ' desktop probe' exact;
  L5 'z bogus' → ERR:UNKNOWN_CMD, disk untouched; L6 'what time is it' →
  ERR:UNKNOWN_CMD, disk untouched (item-11 grammar class holds through
  the desktop path); L7 band PNG persisted and console.decode_band
  round-trips the transcript glyph-side. rc 0.
- RED legs (rule 4, throwaway copies, both rc 1): mutated echo
  expectation → L2 fires; inverted disk-untouched assertion → L5 fires.
  The probe discriminates; it cannot pass vacuously.
- Regression: item-11 grammar + text console + BK-19 atlas + BK-7 FS →
  29 passed (0.9s). Tree: glyph_desktop.py is the only tracked change
  from the seat lane; this lane landed nothing on the engine.
- Honesty: headless engine legs only — the Tk window itself (layout,
  after_poll loop, ImageTk display) was NOT exercised here (no DISPLAY
  in this session; the seat lane's commit message reports a 6s live
  window, not re-verified by this lane). Band decode is glyph-side via
  TextConsole.decode_band, not the WGSL twin. No floors/rate claims →
  rule 1 N/A.
- NOT done: no engine/test/doc code landed this tick (the landing is the
  seat lane's; a desktop gate test would be new scope — noted as
  candidate supply, not claimed); BK-18/BK-21 remain promotion-gated;
  queue EMPTY — supply-wait resumes.

## CLAIM QUEUE ROUND 8 (2026-09-24, seat lane — OPERATOR DIRECT: "make this work as good as Linux")

North star changes: desktop floor is DONE; the goal is now Linux-parity for
this product's scope. Supply detail: .builder_queue/SUPPLY_ROUND8.json.
Four layers, in order, each gated + receipted before the next:

14. L1 shell personality — word verbs (echo/speak/write/read/ls/cp/mv/rm/
    cat/wc/head/tail/grep/time/date/which/env/pwd/cd), per-file argv paths
    via a second ST region in the dispatch program (SE021 pattern). RED-
    first; twin parity re-pinned same-commit.
15. L2 real filesystem — BK-15 FILE_LIST lands first; ls -l columns from
    FSTAB; mkdir/rmdir under allow-scoped root; >> append (BK-7).
16. L3 pipes — |, >, <, &&, ;, $? via host-side splice of the stdout
    window into the input ring; backpressure must terminate.
17. L4 desktop env — tabbed consoles, glyph-native text editor (first
    GUI app with I/O through GPU syscalls), launcher, session persistence.
    Pixel legs: operator-eyes PENDING, per the GUI receipt pattern.

QUEUE JUMP: BK-18 (sharded suite runner) executes right after L1 lands —
suite must stay runnable as test count grows.
Success criterion: user edits/searches/saves/runs a file at the desktop
without reading source, all I/O through the GPU OS.

### 2026-09-24 ~00:3x CDT — ROUND-8 item 14 (L1 shell personality) LANDED (builder af3e62239ce2)

- Mailbox check first: STATUS ACTIVE; monitor delta = seat lane's
  FROZEN_STALLED_T1 (its ladder lane froze, not this lane's ledger — no
  conflict with this file's ACTIVE status). No RULING_* newer than
  2026-09-22 20:38 (newest mtimes re-checked at tick start). Item 14 was
  IN PROGRESS from the prior tick (untracked working tree):
  experiments/glyph_l1_shell.py + tests/test_l1_shell_personality.py
  written, build_dispatch_shell kwargs added, receipt stub filed.
  This tick completed and landed it.
- GREEN (landing tick, real exits): L1 gate 13 passed in 0.82s (W1-W7,
  N1 non-vacuity, T1 twin parity, RED leg); builder family regression —
  interactive shell + item-11 grammar + text console + BK-2 WGSL corpus
  + BK-7 FS — 33 passed in 1.96s. Prior tick: BK-11 6 passed ~23s.
- RED (rule 4): probe_l1_red.py at HEAD f68c251d = 19/19 word-verb legs
  ERR:UNKNOWN_CMD pre-landing (re-run this tick, same 19/19); keep-legs
  (e hello / z bogus / what time is it) held both sides.
- T1 twin parity (the receipt's open item, closed): probe_l1_wgsl_pin.py
  on the L1 image — run_wgsl(input_ring=b"e hello twin") -> halted True,
  115 steps, PRT b' hello twin', byte-identical to the CPU turn.
  Probe-defect kept: ram_seed= of LEN/CURSOR/DATA does NOT drive the twin
  (ring is a BOX_MMIO slot, SE022a; RAM binding is the analogue) — first
  attempt returned 256 zero words; re-routed to input_ring= seeding (the
  test_glyph_text_console.py:186 shape); landed leg pins this in its
  docstring. importorskip("wgpu") — GPU-less runs record SKIP.
- Receipt: .builder_queue/RECEIPT_L1_shell_personality.md (Status: LANDED,
  full honesty section: host-shim verbs disclosed, twin pin bounded to the
  echo body + shared image, no rate claims -> floors N/A).
- NOT done: item 15 (L2 files) untouched — NEXT tick per one-active-ticket;
  BK-18 queue-jump is scheduled by the round-8 order AFTER L1, i.e. it is
  the eligible NEXT unit after this landing per the supply's own "order"
  line (L1 -> BK-18 -> L2 -> L3 -> L4); engine sources, twin sources,
  glyph_desktop.py, protected assets: untouched.

## PHASE BOUNDARIES — SELF-HOSTING CLAIM DISCIPLINE (2026-09-24, seat lane, operator-ratified)

The three-phase ladder is now DOCTRINE. Conflating phases = inflated claim.

PHASE 2 (ACTIVE, LANDED): INVOCATION moves inside. GlyphL1Shell is the
front door — builder, dogfood, and agent work route through it. Host
CPython still executes the python verb's interpreter process. Git ledger
and WGPU substrate remain host-side.

L4 (NEXT): AUTHORING moves inside. Glyph-native editor, tabbed consoles,
session persistence. Toolchain still delegates to host until the bytecode
compiler is resident.

PHASE 3 (FUTURE): EXECUTION moves inside. Zero host Python in the loop —
compiler, assembler, runtime as RV32I/.glyph bytecode on the GPU
substrate. NOT landed. Any receipt citing Phase 3 must show the glyph-
native toolchain executing, not host subprocess output.

Gate for every self-hosting claim: name the phase, show the boundary leg.
"python script.py works in glyph-sh" is a Phase 2 claim only.

## CLAIM QUEUE ROUND 9 (2026-09-24, seat lane — operator direction: NATIVE COREUTILS OVER QEMU/LINUX)

Operator verdict after live verification: BK-11's 6/6 green coreutils ARE
authentic Phase-3 self-hosting (zero host Python at runtime); QEMU/Linux
guest emulation is deferred — containment is file-scoped not syscall-scoped
(unfenced escape hatch, named in the ledger), no consumer exists until L4
tabs land, and native binaries beat borrowed guests as POSIX oracles.

Three supply items, in order:

18. BK-24: streaming sys_write / multi-flush output — generalize
    libc_runtime.py beyond the 16-byte single-flush window (words
    718..721) into streaming append to the PRT band / console ring.
    RED-first: current window overwrites at byte 17 (probe shows it);
    GREEN: write(1, buf, 64) delivers all 64 bytes byte-exact. Twin
    parity re-pinned same-commit. THIS UNBLOCKS EVERYTHING ELSE — every
    tool is currently truncated to 16 bytes of output.
19. BK-25: coreutils volume port #2 — grep, tr, tee, cut, sort as real
    C, rv64-unknown-elf-gcc -> transpile -> byte-exact vs native POSIX
    fixtures. Depends on 18 (outputs exceed the window).
20. Shell-native swap: glyph_l1_shell.py dispatch routes eligible verbs
    to the transpiled glyph binaries, replacing host-python shims where
    byte-exact parity is proven. Phase 2 -> Phase 3 transition, one verb
    at a time, each with a parity gate.

QEMU/Linux: DEFERRED, not rejected. The boot-probe pattern (headless
boot -> grep serial log -> kill) remains a sanctioned dogfood capability
via the python verb; the containment caveat (file-scoped, not syscall-
scoped) is acknowledged in this ledger. Revisit as an L4 tab consumer
after 18-20.

## CLAIM QUEUE ROUND 10 (2026-09-24, seat lane — operator direction: BUILD USING PYTHON INSIDE THE GPU OS)

Operator: "it would be a good idea for the builder to build using python
inside our gpu os." Ratified as a workload migration, scoped by what the
shell can actually do today (verified by seat lane):

- The python verb runs with cwd = an EMPTY ephemeral session root — the
  repo, tools/, and tests/ are NOT visible to in-shell Python (verified:
  os.listdir('.') == []). So the builder CANNOT yet run gates from inside.
- Migration proceeds in the order containment allows:
  21. (WITH 18) builder fixture/synthesis scripts run via the python verb,
      writing INTO the session root — pure-computation work moves inside
      immediately (no repo visibility needed).
  22. (AFTER 18) a --root bind: GLYPH_L1_ROOT may point at a real scratch
      dir (already supported via env!), and gates/fixture prep that only
      need file I/O + pytest move inside. Gate: pytest -q passes from
      within the shell for the lane-family suites.
  23. (PHASE 3, after 20) the end state: shell-native verbs do the work,
      python only orchestrates.

Rule: builder work migrates inside ONLY where it stays verifiable. Any
migration step that weakens a gate gets reverted (keep-or-revert applies
to migration itself).

## ROUND 10 ADDENDUM (2026-09-24, seat lane — Stage-2 mechanical constraint, operator-verified)

Item 22 (in-shell pytest) is BLOCKED by a measured constraint, found by
the operator's session and re-verified live by the seat lane:

- PATH_CAP = 48 bytes (glyph_l1_shell.py:85, GPU FS-window 1024..1280).
  Init stamps <root>/w.dat into that window. Repo-root bind fails:
  47-char repo path + /w.dat + NUL = 54 > 48 -> ValueError at boot,
  before turn 1. Symlink to a short path does NOT help: L1Session uses
  os.path.realpath, which resolves back to the long host path.
- Short isolated roots (e.g. /tmp/gScratch) boot and list cleanly —
  verified live.

DECISION: Stage 2's gate is unchanged (pytest -q passes from inside the
shell), and it is DECOUPLED from BK-24/streaming write (item 18) — they
are orthogonal. Stage 2 may proceed via EITHER:
  (a) short-path staging root: bind GLYPH_L1_ROOT to a SHORT host dir
      (<= ~40 chars incl /w.dat), stage needed tests+modules into it,
      run pytest there; or
  (b) widen PATH_CAP / decouple seed-path stamping from the root path —
      an engine change, so it takes the normal gate path (RED-first,
      twin parity).
(a) is preferred first: zero engine change, falsifiable gate identical.

Dependency ledger correction: Round 10's original text tied Stage 2 to
BK-24; that linkage is WITHDRAWN — items 18, 19, 20, 21, 22 are all
independent tracks (22 gated only by (a) or (b) above).

## ROUND 11 (2026-09-24, seat lane — operator question: ONE-FILE CONTAINER for the whole OS + builder-in-image)

Operator asks: pack everything (shell, toolchain, builder scripts) into
one file (MKV/PNG) so the builder launches Python from inside the image
and everything is contained. Verdict: YES with proven precedent — this
is the PXC1/VAC lineage (glyphos_installer.py already IS a one-file OS;
PXC1 containers boot guests) — but scoped honestly against capacity and
the phase doctrine:

CONTEXT (what already exists):
- glyphos_installer.py: one-file, self-verifying, boots the WGSL fleet
  with no repo checkout. The installer pattern is PROVEN.
- PXC1 containers: boot real guests from pixel-encoded images (alpine
  rootfs_3mb.nut precedent).
- The OS's own programs are ALREADY pixels (glyph images); the shell +
  python verb are the host-side substrate.

THE HONEST SPLIT (phase doctrine applies):
- The GLYPH programs (shells, coreutils, fleet) -> genuinely IN the
  image; this is the native format. Nothing new needed — keep doing it.
- The HOST substrate (CPython interpreter, WGPU driver, QEMU) -> CANNOT
  go in the image; it executes the image. Phase 3 boundary: the image
  contains programs, not the machine that runs them. Claiming "everything
  in one file" without this split is inflation.
- Builder Python scripts -> CAN be packed as DATA (payload members) and
  unpacked to a session root at boot, then run via the python verb.
  This is the actionable new work.

SUPPLY:
23. ONE-FILE GLYPH WORKBENCH: extend the glyphos_installer pattern —
    payload gains (a) the L1 shell program image, (b) builder python
    scripts as manifest members, (c) a session-root bootstrap that
    unpacks (b) and drops the operator into glyph-sh with them present.
    Gate: from ONE file, no repo checkout: boot fleet -> shell -> run a
    packed builder script -> output byte-exact vs repo-run twin. RED-
    first on the no-repo condition. Receipt: RECEIPT_onefile_workbench.md.
    Capacity: trivially fine (installer already carries the fleet; the
    shell image is ~52KB; 4K PNG = 48MB raw).
    Non-goal (doctrine): this does NOT put CPython inside the image.
24. (defers to BK-24/22 tracks, no dependency) — container format
    choice: PXC1 if guest-boot integration wanted later; plain
    self-extracting installer if shell-only. Decision at landing.

## ROUND 11 ADDENDUM (2026-09-24, seat lane — items 22+23 UNIFIED into one staging primitive)

Operator-verified convergence: item 22 (short-path scratch mount) and
item 23 (one-file container unpack) are THE SAME MECHANISM — "stage files
where the shell can see them." One Workbench Session Root, one staging
contract, two execution contexts:

  /tmp/glyph_workbench_XXXX/        short-path root, <= 40 chars (PATH_CAP)
  ├── bin/        glyph dispatch image, atlas/LUTs
  ├── scripts/    builder python scripts (Stage 1 + in-shell pytest runner)
  ├── tests/      staged fixtures for in-shell pytest
  └── w.dat       stamped FS-window arm

- Item 22 (local dev): tools/stage_workbench.py links/copies needed
  fixtures+modules into the root, launches glyph-sh, runs pytest -q.
- Item 23 (standalone): the one-file container unpacks its manifest into
  THE SAME layout and drops into glyph-sh.
- Build ONE mechanism, not two. Gate for both: identical session-root
  layout + identical staging contract, verified from both contexts.

DECISIONS:
- PATH_CAP is a layout constraint, not a bug — do NOT widen it (blast
  radius: every stamped-path consumer). Item 22 uses short staging roots.
  (Withdraws round-10-addendum option (b).)
- Format: PNG-family or self-extracting .py (stdlib-only bootstrap).
  MKV/NUT reserved for 10GB-class guest containers — overkill for a
  sub-MB workbench. Final call at landing, both formats satisfy the gate.
- Doctrine intact: packed builder scripts remain Phase 2 (host CPython
  executes them). "Everything in one file" = programs + data, never the
  interpreter.

Items 22+23 merge as ONE supply item with TWO verification contexts.

## CLAIM QUEUE ROUND 12 (2026-09-25 ~03:4x CDT, seat lane — operator question: PNG DISK + GPU VFS)

Operator asks: should the builder and GPU OS write to a PNG disk with a
VFS resident in GPU memory? Verdict (operator + seat lane, aligned):
YES to direction, SEQUENCED AFTER the current queue — it is a foundation
swap under every landed gate, not an addition beside them.

CONTEXT THAT MAKES THIS REAL, NOT SPECULATIVE:
- virtio_pixel_backend serves guest disks from pixel substrates (working).
- PXC1 / PixelRTS v2 Hilbert packing exists and is gated.
- Syscall re-routing has precedent (0x07/0x12 host-vs-twin split).
- BK-25's stage_workbench just proved in-shell pytest; the workbench is
  the natural first tenant of a PNG disk.

SEQUENCING (binding):
- Items 19, 20, 21 land on the HOST-SHIM model as planned. They are
  bounded, gated, and their gates assume host-backed 0x03/0x04. Do not
  rebase them mid-flight.
- VFS-1 (STANDALONE, safe to file now): tools/png_vfs.py — PNG disk
  format (Hilbert block substrate, superblock/inode/extents), read/
  write/list as a pure Python module. Touches NO existing code path.
  Gate: test_png_vfs.py — write 3 files to a generated disk PNG, read
  back byte-exact, list matches, Hilbert mapping verified vs an
  independent 1D<->2D implementation. RED-first: no png_vfs module ->
  import error; corrupted disk magic -> loud failure leg.
- VFS-2 (syscall re-route 0x03/0x04/0x13 to in-memory VFS) and VFS-3
  (sync/writeback + reboot-persistence gate) are RESERVED pending
  operator sign-off: their blast radius crosses every landed I/O gate
  (BK-11 coreutils byte-exactness, BK-21 exec, L2/L3 filesystem tests).
  Each will carry a migration matrix: every existing gate re-run
  against VFS-backed storage before the host path is demoted.

DOCTRINE NOTES:
- This is the Phase-3 filesystem leg: paths become VFS-internal keys,
  PATH_CAP retires naturally (not widened — replaced), and the disk is
  an inspectable image. Consistent with round-11 doctrine: the PNG is
  programs+data+FS; the machine that runs it stays host-side.
- BK-25's workbench is the first consumer: workbench.rts.png becomes
  the standalone distribution format once VFS-1 + VFS-3 exist.

24. VFS-1 png_vfs.py — standalone PNG disk format module + gate (file now)
25. VFS-2/3 — syscall re-route + writeback persistence (RESERVED, operator
    sign-off required before claim; migration matrix mandatory)

## RESILIENCE UPGRADE (2026-09-25 ~08:0x CDT, seat lane — operator-approved, counterparty-conditioned)

Operator approved builder-loop resilience. Counterparty (Claude session) ratified
with binding conditions — ALL ACCEPTED, they are correct:

1. STRUCTURED QUEUE BEFORE PROSE PARSING (condition on #1): no parsing of
   CLAIM QUEUE prose by the monitor, ever. Canonical supply =
   .builder_queue/QUEUE_STATE.json (schema: queue[].id/status/blocks_on/
   claim_order + active{} + defects[]). The agent keeps it in sync with the
   ledger; on mismatch the monitor emits DRIFT. PR-1 (monitor next=) reads
   THIS file only. Filed this commit as the bootstrap seed.
2. DEFECT PIVOT STICKINESS (condition on #2): once pivoted to a defect,
   next= stays on it until the defect lands OR 3 research strikes exhaust —
   no per-tick re-evaluation while a defect fix is in flight. Prevents
   pivot thrash (DEFECT-30 itself suspects a second engine bug underneath).
3. RESEARCH ESCALATION CAP (condition on #3): 3 consecutive gate REDs on a
   ticket -> next tick is RESEARCH (probes only, NO code edits, output is a
   RESEARCH_*.md answering one named question). If N=2 research ticks pass
   without a landable fix, the ticket escalates to operator (ledger line
   ESCALATION: <ticket> needs Jericho) and the lane moves to the next
   unblocked item. Research is not an infinite loop either.
4. CURRENT_TICKET.json (approved as-is): filed this commit. Ticks MUST
   reconcile it against worktree reality first thing; correct it if stale.
5. SHADOW MODE (condition on #1 rollout): monitor computes next= from
   QUEUE_STATE.json and LOGS it as supply_shadow=... while the LLM keeps
   its own selection. Discrepancies appear in the fingerprint as a visible
   field, not as silent misdirection. Shadow -> primary only after 48h
   with zero discrepancy AND one full successful item cycle.
6. COMPACTION (#5): ledger entries older than the last 3 landings compress
   into ROUND_LOG.md one-liners. Maintenance script, runs at landing time.

Sequencing: #4+#6 now (additive), #3-with-cap + #2-sticky + #5 as prompt/
ledger contract now, #1+#2 monitor-side in SHADOW first. One active
variable: monitor changes land only after the current DEFECT-30 fix cycle
completes — the control loop does not change underneath an in-flight fix.

resi-seed: QUEUE_STATE.json + CURRENT_TICKET.json are LIVE as of this
commit; every tick from now on must reconcile and update them.

## PRE-VFS-1 RULING (2026-09-25 ~08:4x CDT, seat lane — operator-flagged fork): PNG DISK FORMAT = ext2

Counterparty flagged this fork correctly; ratifying BEFORE png_vfs.py is
claimed (format changes after code exists = wasted work):

DECISION: VFS-1's disk payload is a VALID ext2 IMAGE, not the bespoke
superblock/inode/Hilbert-block format from round 12. Hilbert packing
remains the TRANSPORT (byte-to-pixel mapping inside the PNG); ext2 is
the CONTENT. Two layers, one decision:
- png_vfs.py wraps: PNG pixels -> Hilbert 1D byte offset -> raw disk.
- That raw disk IS ext2 (mke2fs on host, read by GPU OS, both agree).

WHY (measured payoff):
- debugfs/e2fsprogs/debugfs -R ls work on the PNG-decoded payload with
  ZERO custom host tooling — the standalone-workbench distribution
  story (item 22b) inherits free tooling.
- Retires superblock/inode/bitmap design from VFS-1's gate: the gate
  becomes "mke2fs a disk, wrap in PNG, unwrap, fsck passes, files
  byte-exact" — externally validated instead of self-referential.
- On-disk format is the MOST debugged code in OS history; we adopt it,
  we do not re-derive it.

CONSTRAINTS:
- SIZE: ext2 minimum ~1MB (1024-block minimum at 1KB blocks). VFS-1
  gate uses a 2048x2048 PNG (16MB raw) -> comfortable. Small-fixture
  tests may use truncated/mke2fs -b 1024 minimal images; document.
- LICENSING: contract-only clean-room (standing doctrine): read
  fs/ext2/ + Documentation/filesystems/ext2.rst for the ON-DISK
  LAYOUT SPEC; implementation ours. NO Linux code vendored.
- CITATION GATE (standing, applies to ALL spec-adoption landings):
  every landing that adopts a Linux-sourced contract MUST contain a
  receipt line "SPEC: <kernel path/doc> read <date>; implementation
  ours from contract." Receipts without the line FAIL the landing
  checklist. (Counterparty condition — ratified.)

ITEM 24 GATE (amends round-12 spec): RED-first legs unchanged, plus:
- mke2fs-created image wrapped in PNG -> png_vfs unwrap -> fsck -fn
  clean -> 3 files byte-exact vs originals.
- Hilbert 1D<->2D mapping verified vs independent implementation.
- Corrupted-magic (PNG and ext2 superblock) -> loud failure legs.

item 24 (VFS-1) is NOW the highest-value unblocked item; recommend the
lane claim it next (item 20 shell-native swap may interleave — both
unblocked, claim_order unchanged).

## ADDENDUM (2026-09-25 ~09:0x CDT, seat lane): item-24 sizing measured + confirmed next-claim

- Counterparty's sizing caution VERIFIED EMPIRICALLY on this host:
  mke2fs -b 1024 -m 0 -N 128 on a 16MB image -> 16384 blocks total,
  16203 free (181 blocks / ~181KB metadata overhead = 1.1%). Usable
  payload ~= 16.6MB of file bytes in a 2048x2048 RGB24 PNG (16.7MB
  raw) with margin. The -N 128 inode count is fine for gate fixtures
  (12 free inodes at bootstrap, ~40 bytes each file); if inodes ever
  bind, -N 512 costs ~200KB more. MEASURED, not assumed — the lane
  should re-run dumpe2fs inside its own gate as a fixture-sanity leg.
- mke2fs/e2fsck/debugfs/dumpe2fs all PRESENT on this host (/usr/sbin)
  — item-24's gate (mke2fs -> wrap -> unwrap -> e2fsck -fn -> byte
  exact) is executable as designed, no dependency gap.
- RULING CONFIRMED: item-24 (VFS-1) is the next claim. Standalone,
  zero engine blast radius, externally validated gate. Items 20/21/
  22b interleave per claim_order if the lane's selection prefers.

### 2026-09-27 ~04:5x CDT — PHASE 1c RESEARCH TICK: BK-46 finding (4) ROOT-CAUSED and its record FALSIFIED — head's dynamic shell-native path dies at LINK (`undefined reference to 'bk11_out_ch'`, the same missing-`_COMMON` class as wc), the shell's ERR path discards gcc/ld stderr so it surfaces as an opaque `ERR:SHELLNATIVE:head`, NOT the recorded "empty ring"; control leg proves head works completely once `_COMMON` is supplied; BK-47 filed (builder af3e62239ce2)

- Run selection re-verified, not assumed: HEAD ad4f2494 (my BK-46
  research tick, 03:05), tracked tree clean at claim, mailbox clean
  (newest RULING 2026-09-22 20:38, predates HEAD), monitor CLAIM_PENDING
  queue=0 stall_tier=0. QUEUE_STATE active=null, items 19..41 landed,
  DEFECT-30 resolved → Phase 1c research eligible. No re-research: the
  open scope is BK-46's finding (4) — "head … emits NOTHING (empty ring)
  — separate defect, recorded not root-caused" — measured by no existing
  RESEARCH/backlog row.
- Probe `.builder_queue/probe_head_dynamic_af3e.py` (untracked, landed
  modules only) at HEAD ad4f2494; 3 legs; verdicts from returned
  strings + gcc/ld stderr + ring bytes, never handler stdout. Results
  md5 43bf2f0366674987708daa3980aa326d:
  (A) real path `_shell_native("head",…)` → `ERR:SHELLNATIVE:head` on
  both fixtures (25 B, 480 B) — an error string, NOT an empty ring;
  (B) exact dynamic TU (as glyph_l1_shell.py:952-974 builds it, no
  `_COMMON`) → ld.rc=1 `undefined reference to 'bk11_out_ch'` — the
  shell (:1033-1034) returns the bare ERR and discards stderr;
  (C) control, `_COMMON` prepended → halted=True faulted=False, ring
  cursor 772 (base 768), output `alpha` = correct `head -n 1`: head has
  NO separate body defect.
- Verdict: BK-46's finding (4) and the ledger's "empty ring" symptom are
  falsified — the real path cannot reach the ring (link failure returns
  at :1034 before bake); the earlier tick most likely misread an
  ERR-string turn's empty OUTPUT as an "empty ring" (inference, labeled
  as such). head is the SAME defect as wc, different observed symptom.
  BK-47 filed to systems/GLYPH_BACKLOG.md (gate test_bk47_head_dynamic
  _path.py: seed-block fix covering wc AND head + stderr-diagnostic leg
  + n-exceeds + non-vacuity; prereq BK-24 + BK-11 landed; blast radius
  experiments/glyph_l1_shell.py only — no engine file; coordinate with
  BK-46, same file + fix shape). Research landed NO engine or shell
  code; probes + RESEARCH_head_dynamic_link_af3e.md + the BK-47 row
  only. Numbers structural (strings, exit codes, cursor arithmetic,
  md5) — rule-1 floors do not attach.

### 2026-09-27 ~06:1x CDT — PHASE 1c RESEARCH TICK: WGSL MMIO-block write door MEASURED on-device — walk_st's box_mmio branch (:443) runs BEFORE the E-K1 consult (:451) with no mode gate; seeded-USER ST lands in BOX0_HI clean (fault 0, mode stays USER) while the oracle traps the same program (fault 0x8010, mode→SUPER); pure-USER fence self-disarm chain lands on the twin (BK-50 filed; builder af3e62239ce2)

- Run selection re-verified: HEAD 4515bbfd (my BK-49 landing), tracked
  tree clean at claim, mailbox clean (no RULING newer than HEAD),
  monitor CLAIM_PENDING queue=0 stall_tier=0, queue empty → Phase 1c
  research eligible. No re-research: BK-48/49 measured walk_ld/walk_st's
  RAM arm and the stack ops; the box_mmio sub-range itself is named by
  neither, and no RESEARCH_*/backlog row probes it.
- Probe `.builder_queue/probe_wgsl_mmio_door_af3e.py` (untracked, landed
  modules only), harness = BK-48/49 device buffers + probe-only seeded
  cpu.mode + mmio BOX0 arming [1200,1300); KFAULT_PC left 0; verdicts
  from mmio/ram readback bytes, never stdout. 3 runs, results md5
  264b68726beeef8b80c0670923be674f (runs 2-3 identical; run 1 differed
  only by a D3 register-assignment bug fixed before any conclusion —
  disclosed in the receipt).
- Findings (full detail in RESEARCH_wgsl_mmio_door_af3e.md):
  (1) D1: seeded-USER ST 0x0ADF00D → word 8196 (BOX0_HI) LANDS
  (mmio_box0_hi=11399181), mode_final=USER, fault_addr_word=0, 4 steps
  clean — the twin's MMIO store door is open to USER with no consult;
  (2) oracle control (dbg_mmio_door_oracle_af3e.py + step traces): the
  SAME program on GlyphCPUv2 fires E-K1 at the ST step (fault 0x8010 =
  8196<<2, mode→SUPER, store refused) — measured ENGINE DIVERGENCE,
  not just a fence gap; (3) D2 control: out-of-box RAM ST traps
  (fault 400, mode→SUPER) on the same walk_st — harness arming LIVE,
  so D1 is a genuine door; (4) D3: pure-USER disarm chain — ST 65536
  → word 8196, then ST → word 999 (out of the original box) BOTH land,
  mode USER end-to-end, fault 0, 7 steps: the task rewrote its own
  confinement through the legitimate walk_st door (oracle: impossible
  from pure USER without PARALLEL_ST); (5) source: :443 branch precedes
  the :451 consult, no mode/is_super test in the branch (S1 legs).
- Disclosed, not root-caused: oracle-side KFAULT_PC=0 continuation
  quirk (the trapped task kept stepping and the value landed on a
  SUPER replay of the same ST); walk_ld's symmetric MMIO branch
  (:361-363) unmode-gated by SOURCE READ only — not probed, named in
  the receipt and the backlog row.
- BK-50 filed to systems/GLYPH_BACKLOG.md (gate test_bk50_wgsl_mmio
  _door.py: L1 USER MMIO ST refused, L2 disarm chain blocked, L3 SUPER
  control green, L4 oracle-parity fault-0x8010 pin, L5 non-vacuity,
  L6 family; lands IN the BK-38..45 sequenced fence commit, posture
  decided alongside BK-41's kernel-write-only config block; blast
  radius tools/wgsl_glyph_isa_v2.py only). Research landed NO engine
  or shader code; probe + oracle-control debug script + receipt +
  backlog row only. Numbers structural (word addresses, register/mmio
  values, fault codes, run counts, md5) — rule-1 floors do not attach
  (floors file is 113h stale and was NOT cited for any claim).
- Next tick: research again (queue still empty), unless a new CLAIM
  QUEUE item or binding RULING appears first.

### 2026-09-27 ~07:1x CDT — PHASE 1c RESEARCH TICK: KFAULT_PC=0 trap continuation ROOT-CAUSED — the oracle's E-K1 ST trap branch (glyph_isa_v2.py:1063-1068) vectors KFAULT_PC with NO kf!=0 guard: kf=0 → next_pc=(0,0) → SUPER-mode REPLAY from program entry → the "refused" store LANDS (PC trace measured step-by-step; leg-D run(): 7 steps, word8196=11399181); sibling site :1075-1082 same missing else; WGSL twin ALREADY has the guard (:591-604) — new engine-divergence class (trap-no-handler: oracle replay-and-land vs twin clean halt); BK-52 filed (builder af3e62239ce2)

- Run selection re-verified: HEAD f5f595d8 (my BK-51 landing), tracked tree
  clean at claim, mailbox clean (no RULING newer than HEAD), monitor
  CLAIM_PENDING queue=0 stall_tier=0, queue empty → Phase 1c research
  eligible. No re-research: the open scope is the KFAULT_PC=0 continuation
  quirk disclosed NOT-root-caused in both the BK-50 and BK-51 receipts; no
  RESEARCH_*/backlog row probes it.
- Probes `.builder_queue/probe_kfault0_continuation_af3e.py` +
  `probe_kfault0_legC_af3e.py` (untracked, landed modules only). Probe
  defect DISCLOSED and fixed before conclusion: the manual step loop never
  set `cpu.running=True` (run() does; a bare step() loop must) — first runs
  printed 0 steps twice, identically; the `running=True` line was added and
  leg C re-run. Final results md5: probe A 0ed582e80e44e50cb3745ac2415c6b66,
  probe B 4fed08227ee3e392725e31e43336f622 (/tmp/kfault0_run.txt,
  /tmp/kfault0_legC2.txt).
- Findings (full detail in RESEARCH_kfault0_trap_af3e.md):
  (1) ROOT CAUSE — :1063-1068 reads kf and vectors unconditionally
  (tx,ty = kf&0xFFFF, kf>>16; next_pc=(tx*INSTR_WIDTH, ty)); every other
  fault site (:855, :889, :949, :982, :1027) carries `if kf != 0: … else:
  running=False`. With kf=0 the trap becomes next_pc=(0,0) = program entry,
  mode already SUPER.
  (2) Leg C PC trace (seeded-USER, box [1200,1300) armed, ST to word 8196):
  pre-step0-2 walk (0,0)→(4,0)→(8,0) mode=1; pre-step3 pc=(0,0) mode=0
  faulted=True fault_addr=0x8010 — trap vectored to entry; steps 4-6 replay
  the program at mode=0; 7 steps, word8196=11399181 — the out-of-box store
  LANDED on the SUPER replay. Leg D run(): steps=7 running=False
  halt_reason=None mode_final=0 word8196=11399181. Leg E explicit kf=0
  identical. The branch docstring's "do NOT perform the store" holds only
  for the first attempt.
  (3) TWIN CONTRAST (source read, NOT executed this tick): wgsl_glyph_isa
  _v2.py:591-604 HAS the guard (`if (kf != 0u) … else running=0`) with a
  comment claiming it matches "the oracle's no-handler branch" — the oracle
  has no such branch. Measured-divergence class pending an on-device kf=0
  run; classified by source read and labeled as such.
  (4) Sibling: :1075-1082 (USER in-BOX RAM overflow) same missing else —
  same class, included in BK-52's gate.
- BK-52 filed to systems/GLYPH_BACKLOG.md (gate test_bk52_kfault0_trap.py:
  L1 post-repair kf=0 trap halts ≤2 steps, word unchanged, fault_addr
  0x8010, mode SUPER; L2 handler-installed vector unchanged; L3 twin-side
  kf=0 halt pin; L4 non-vacuity; L5 sibling site). RE-BASES BK-50/BK-51
  probe end-state legs (they read the post-trap replay state this repair
  removes). Blast radius tools/glyph_isa_v2.py (two vector sites) — engine
  file, worktree isolation, NOT research-landable. Research landed probe
  scripts + receipt + backlog row only, no engine/shader code. Numbers
  structural (PC coords, mode ints, word values, fault codes, step counts,
  md5) — rule-1 floors do not attach.
- Next tick: research again (queue still empty), unless a new CLAIM QUEUE
  item or binding RULING appears first.

### 2026-09-27 ~05:5x CDT — PHASE 1c RESEARCH TICK (RECONCILIATION): head "emits NOTHING" leg re-probed — RULE-5 OVERLAP self-flagged: the root cause was already landed by the preceding tick (9e8b1bc0, BK-47); net-new landed = measured mechanism of the original mis-record + NEW defect BK-54 (BK-24 ring cursor unbounded)

- Run selection re-verified: HEAD d5afe55e (my BK-53 research landing),
  tracked tree clean at claim, mailbox clean (0 RULING_* newer than
  HEAD, mtime-scanned), monitor CLAIM_PENDING queue=0 stall_tier=0,
  queue empty → Phase 1c research eligible. Target picked: the BK-46
  receipt's open leg (4) "head emits NOTHING — recorded not
  root-caused". MISTAKE: the backlog-tail grep for a head-specific row
  ran AFTER the probe harness was built — the preceding tick
  (9e8b1bc0, ~04:4x) had already root-caused it (head dies at LINK,
  undefined bk11_out_ch, ERR path discards stderr → opaque
  ERR:SHELLNATIVE:head; "empty ring" record falsified; BK-47 filed).
  BK-47 stands as the authority; this tick landed a RECONCILIATION
  receipt, not a competing root cause. Lesson recorded in
  CURRENT_TICKET.json: rule-5 grep of RESEARCH_*.md + backlog BEFORE
  building the harness.
- Net-new measured (probe .builder_queue/dbg_head_root_cause_af3e.py,
  untracked, landed modules only; RAW cursor+ring dump BEFORE rstrip;
  results blob md5 645e32d319f2e9014d2e06fd5cfa178b at HEAD d5afe55e):
  (1) the original dbg3 probe's "empty output" was a 16-NUL pad frame,
  not an empty ring — dbg3 seeded HEAD_N pre-alias while aliasing
  #define HEAD_N head_n (alias_map shape coreutils_port.py:381 without
  its :350 seed) → body read unseeded BSS head_n=0 → zero lines →
  bk11_flush pad frame; collect-side .rstrip(b"\x00")
  (glyph_l1_shell.py:1072) rendered it "". Leg A: cursor=772 (ONE
  frame), ring=(0,0,0,0). This MEASURES the mechanism the BK-47
  receipt had only inferred ("ERR output misread as empty ring" —
  actually a third failure shape: real ring write of NULs). Also
  corrects the BK-46 receipt's prose "ring cursor == ring base":
  measured 772, not base.
  (2) legs B/C: head WORKS in the fixture-builder seed shape AND in
  _shell_native's own :972-974 seed shape (cursor=872, 416 bytes
  byte-exact for the 401-byte line; leg D short file word 682344 =
  0x000A6968 = "hi\n" byte-exact) — confirms BK-47's no-body-defect
  conclusion by a second route; the dynamic head swap needs only the
  _COMMON prepend BK-47 already specs.
  (3) NEW DEFECT, filed as BK-54: the BK-24 write-ring cursor is
  UNBOUNDED — legs B/C cursor=872 = 40 words past the declared ring
  end 832 (libc_runtime.py:54-57; saturation non-goal :111-116; tile
  cursor arithmetic :144-161 has no clamp). 416 bytes landed
  byte-exact, no visible corruption in this image, but words 832..
  occupancy is unmapped and >256-byte streams are exactly the case the
  docs claim saturates. Gate: tests/test_bk54_ring_saturation.py
  (clamp-or-reserve posture decided at landing; canary RED-first legs;
  blast radius tools/glyph_gpt/libc_runtime.py, worktree isolation).
- Probe defect disclosed: leg D's host_head display field computed
  data_small[:1] ("h\n" not "hi\n"); display-only, raw ring word is the
  verdict. BK-46/BK-47 rows unchanged; BK-54 appended to
  systems/GLYPH_BACKLOG.md; research landed probe + reconciliation
  receipt + backlog row only, no engine/shader/shell code. All numbers
  structural (cursor values, word addresses, hex words, md5s, line
  numbers) — rule-1 floors do not attach.
- NOT verified: BK-54 blast radius (what lives at words 832.. in the
  libc-mode image); BK-47's real-path legs not re-run; tail still has
  no V1 source (unchanged). Next tick: new queue supply if it appears,
  else research per Phase 1c — rule-5 grep BEFORE harness build.

### 2026-09-27 ~06:5x CDT — PHASE 1c RESEARCH TICK: WGSL MMIO-block READ channel measured on-device (BK-56) — walk_ld's unmode-gated box_mmio branch is ORACLE PARITY: both engines leak the config block to USER reads; only BK-50's write side diverges

- Run selection re-verified: HEAD 4197658c (my BK-55 ledger landing),
  tracked tree clean at claim, mailbox clean (0 RULING_* newer than
  2026-09-22 20:38, mtime-scanned), monitor fingerprint head-matched
  (4197658c, tracked_dirty=0, CLAIM_PENDING queue=0 stall_tier=0),
  queue empty → Phase 1c research eligible. Target picked: BK-50's
  disclosed residual — "walk_ld's MMIO branch (:361-363) is also
  unmode-gated by source read — likely a config-read channel, lower
  severity, not measured here" (RESEARCH_wgsl_mmio_door_af3e.md:26).
  Rule-5 grep BEFORE harness build: no RESEARCH_*/backlog row covers
  the MMIO-range READ side (BK-48 = out-of-box RAM LD, BK-50 = write
  door) — net-new.
- Net-new measured (probe .builder_queue/probe_wgsl_mmio_read_af3e.py,
  BK-50's device harness verbatim, box [1200,1300) BYTES armed, 3 runs
  byte-identical, results md5 c464ef9baff66a9b9ae63e06a00d2cd5; oracle
  control dbg_mmio_read_oracle_pt_af3e.py, 3 runs identical):
  (1) S1 — walk_ld is the twin's ONLY fence-gated read (addr_in_box
  consults: walk_ld 0, walk_st 2); its inner MMIO branch (:361-363)
  has NO mode term; the outer is_super (:353) is short-circuited by
  `pt_base == 0u ||` when paging is disarmed (the universal probe/
  fleet posture). (2) D1 — seeded-USER LD of word 8196 (BOX0_HI=1300)
  + in-box result ST: ram[310] == 1300, mode USER, fault 0, clean
  5-step halt — the config-read channel REPRODUCES on-device.
  (3) D2 — USER LD of word 8193 (KFAULT_PC=7): ram[310] == 7 — the
  guest reads its own fault VECTOR, exactly the aiming value BK-55's
  hijack needs; read channel + write door = self-contained attacker
  toolchain. (4) D3 oracle-parity control — the oracle LD arm
  (glyph_isa_v2.py:826-933) consults no fence and keeps words 8192+ in
  plain self.memory: word310 == 7, mode USER, faulted False — PARITY
  (directionally distinct from BK-50: write side diverges, read side
  leaks on both engines). (5) D4 — USER ST out-of-box traps (fault
  400, mode→SUPER, value refused): box arming LIVE. (6) Structural
  asymmetry: walk_st's consult at least records+vectors E-K1
  (wgsl_glyph_isa_v2.py:446-460); the LD side of the MMIO range is
  silent on both engines — no fault path exists for a read gate to
  ride; the posture is a fresh decision, not an E-K1 rider.
- CONSEQUENCE for the BK-38..45 sequenced commit: BK-41's
  kernel-write-only config posture leaves the block USER-READABLE on
  BOTH engines; the landing round must add an explicit READ-posture
  line item (twin: mode-gate :361-363; oracle parity leg: same gate or
  document guest-readable with a rot-guard). Read-gating also de-fangs
  BK-55's aim step.
- Probe defects disclosed: (a) draft legs STed the LD result to word
  1250 believing it in-box — 1250 is a WORD index, byte 5000 is OUT of
  [1200,1300), so the result store itself took E-K1 (fault_addr ==
  4×result_word exposed it; first-run results md5
  f246c4b03eaa60c2e0a4a849924caf23 shows the artifact); fixed to word
  310 (byte 1240), post-fix md5 cited. (b) the baked D2/D3 image has an
  opcode-None dead pixel at (28,0) so the oracle run()-form halts
  pre-verdict; dbg harness steps manually with cpu.running=True
  (artifacts kept: dbg_oracle_trace_d2_af3e.py shows the LD succeeding
  at step 2 while the result ST trapped at step 4).
- BK-56 appended to systems/GLYPH_BACKLOG.md (gate
  tests/test_bk56_mmio_read_posture.py, blast radius
  tools/wgsl_glyph_isa_v2.py walk_ld branch + optional oracle parity
  leg; lands IN the sequenced fence commit). Research landed probe +
  dbg artifacts + receipt + backlog row only, NO engine/shader code.
  All numbers structural — rule-1 floors do not attach.
- NOT verified: whether any landed kernel image depends on USER
  readability of the config block (posture leg L4's rot-guard would
  pin this at landing); the paged (pt_base != 0) read path of
  walk_ld not re-probed (S1 source-read covers it: the outer branch's
  is_super MMIO term DOES gate the paged path's MMIO special case);
  no WGSL non-blocking-smoke concerns (probe is local-GPU only).
  Next tick: new queue supply if it appears, else research per Phase
  1c (rule-5 grep BEFORE harness build).

### 2026-10-01 ~05:3x CDT — Map-lane housekeeping tick (builder af3e62239ce2, commits 8664157e + 7a621d00; NO engine/shader/test-code change; picked at HEAD 51902aad == monitor fingerprint, mailbox clean, ledger STATUS ACTIVE, CLAIM QUEUE empty — BK-77 landed 05:22, verified by this tick before any action):

- Verified the BK-77 landing rather than trusting the ledger: git show 51902aad (twin box-only lock, md5 f95d3263 x3, gate 7/7 receipted); re-ran tests/test_bk77_twin_boxonly_lock.py on the landed tree — 7/7 GREEN (12.78s); family spot-checks BK-50 6/6 + BK-76 oracle+twin 15/15 GREEN. Backlog BK-77 row RESOLVED tail present.
- build_map regenerated to frontier 51902aad (tools/spatial_build_map.py; 730 cells, frontier (24,20)) — committed 8664157e (png) + 7a621d00 (data json; second write needed because the json was non-deterministic across the two runs — generated_at timestamp field; png verified byte-identical on re-run). Exempt map-lane channel per precedent.
- Monitor worktree-blindness fix (tools/glyph_build_chain_monitor.py + tests/test_monitor_fingerprint_hygiene.py, both tracked-dirty since 09-30): hygiene gate re-run 9/9 GREEN, live monitor emits wt=bk19-font:4d,defect23-ptloop:1a correctly. Left UNCOMMITTED deliberately — not this tick's work; the authoring session (or a future in-flight-completion tick) owns the commit. Disclosure, not a stall.
- Dogfood telemetry HEALTHY 7/7 every 10m tick through 05:30; disk fine (/ 9.24GB free, /home 20.31GB free — ENOSPC watch clear).
- Teleop note (B-state discipline): geos_surface_meta age_seconds = 1,007,800 (~11.7 days), tick 0, write_id 75 written_at 09-19 — the canonical observation snapshot is STALE/machine-not-stepping; no surface read was used for any conclusion this tick. Recorded here because the freshness caveat must travel with any future surface claim.
- NOT verified: the two unlanded worktrees (bk19-font 12db395a, defect23-ptloop 6d8ab81f) not inspected this tick — monitor counts them; BK-54/BK-56 backlog rows NOT claimed (rows say NOT claimable without Jericho; next eligible supply is a new CLAIM QUEUE item or a promoted row per the standing rule).
- Next tick: new CLAIM QUEUE item / binding RULING first; else re-scan for promotable supply (BK-54/56 are Jericho-gated rows, standing candidate list unchanged).
