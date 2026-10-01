# RESEARCH — KFAULT_PC=0 trap continuation root-caused (builder af3e62239ce2, 2026-09-27 ~06:3x-07:0x CDT)

## Question

Two consecutive research receipts (RESEARCH_wgsl_mmio_door_af3e.md, BK-50; the BK-51
tile-fence tick) disclosed an oracle-side quirk, "not root-caused": with
`KFAULT_PC == 0` (no fault handler installed), a GlyphCPUv2 task that traps E-K1
*kept stepping* and the faulting store *landed* on a SUPER-mode replay — contradicting
the trap branch's own docstring ("do NOT perform the store"). Why does a trapped,
handler-less task continue at all?

## Method (what was read, what ran)

- Source read: `tools/glyph_isa_v2.py` — all fault-vector sites grepped for the
  `kf != 0` guard; the E-K1 ST trap branch read in full (:1049-1069); `step()`
  prologue (:750-777) and `run()` (:1816-1822) read to explain loop semantics.
- Source read (contrast): `tools/wgsl_glyph_isa_v2.py:585-605` — the twin's E-K1
  fault path, which DOES carry the guard.
- Probe A: `.builder_queue/probe_kfault0_continuation_af3e.py` (untracked, landed
  modules only) — the BK-50 oracle-control program (USER ST 0x0ADF00D → word 8196,
  box [1200,1300) armed, KFAULT_PC=0) run twice for determinism. Results md5
  `0ed582e80e44e50cb3745ac2415c6b66` (/tmp/kfault0_run.txt).
- Probe B: `.builder_queue/probe_kfault0_legC_af3e.py` — per-step PC/mode trace
  (leg C), full `run()` replay (leg D), explicit-KFAULT_PC=0 rerun (leg E).
  Results md5 `4fed08227ee3e392725e31e43336f622` (/tmp/kfault0_legC2.txt).
- Probe defects DISCLOSED: probe A's manual loop never set `cpu.running = True`
  (run() does; a bare step() loop must too) — printed 0 steps, twice, identically;
  fixed in probe B leg C before any conclusion was drawn from a trace leg. The
  leg-D `run()` result in probe A was unaffected by that defect. Probe B leg C
  initially also showed `steps=0` for the same reason; the `running=True` line was
  added and leg C re-run — the md5 above is the FIXED run.

## Findings

1. **ROOT CAUSE — missing `kf != 0` guard in the oracle's E-K1 ST trap branch.**
   `glyph_isa_v2.py:1063-1068`: after the trap records fault words and drops to
   SUPER, it vectors unconditionally:
   `kf = memory[KFAULT_PC_ADDR>>2]; tx, ty = kf & 0xFFFF, (kf>>16) & 0xFFFF;
   next_pc = (tx * INSTR_WIDTH, ty)`. With `KFAULT_PC == 0` this is `next_pc = (0,0)`
   — program entry. Every OTHER fault site in the same file guards this:
   :855-861, :889-895, :949-955, :982-988, :1027-1033 all read
   `if kf != 0: <vector> else: running=False`. The ST branch (:1063-1068) and the
   in-BOX RAM-overflow sibling (:1075-1082, same shape, same missing else) are the
   only two without it.
2. **The replay is the store.** Leg C trace (KFAULT_PC=0, seeded-USER):
   pre-step0..2 walk (0,0)→(4,0)→(8,0) at mode=1 (USER); pre-step3 shows
   `pc=(0,0) mode=0 faulted=True fault_addr=0x8010` — the trap vectored to entry,
   mode now SUPER; steps 4-6 walk the program AGAIN at mode=0; 7 steps total,
   `word8196 = 11399181` — the out-of-box store **landed** on the SUPER replay.
   `run()` (leg D): `steps:7 running:False halt_reason:None mode_final:0
   word8196: 11399181`. Leg E (explicit KFAULT_PC=0) identical: store landed.
   The docstring's "do NOT perform the store" holds only for the first attempt;
   the machine then hands the task a SUPER-mode re-execution of the same
   instruction.
3. **Determinism**: probe A legs A/B ran twice, byte-identical output (md5 above);
   leg E pins explicit-0 ≡ default-0.
4. **The WGSL twin is correct.** `wgsl_glyph_isa_v2.py:591-604` has the exact
   guard the oracle lacks: `if (kf != 0u) { vector } else { cpu.running = 0u;
   return; }` with a comment citing "the oracle's no-handler branch" — a comment
   that is wrong about the oracle. **Measured engine divergence class (new):**
   trap-no-handler semantics differ — oracle = SUPER replay-to-land, twin = clean
   halt. This also retroactively explains why the twin side of BK-50/BK-51
   measurements never showed the continuation quirk.
5. **Blast radius if repaired**: adding the guard at :1063-1068 and :1075-1082
   would change observable behavior of any harness that traps with no handler —
   including THIS lane's own BK-50/BK-51 probes (they read end-state after a
   trap; with the guard the task halts instead of replaying) and possibly
   xv6-nano harness expectations. Engine file (`glyph_isa_v2.py`) — this is a
   skeleton-sign-off-class repair, NOT research-landable.

## What this PASS does NOT prove

- No exhaustive audit that no third unguarded vector site exists (I grepped
  `kf = self.memory[KFAULT_PC_ADDR` — six guarded sites + two unguarded; a
  differently-shaped vector site could exist under another name).
- No WGSL on-device run this tick — the twin side is verified by SOURCE READ
  only (:585-605); its behavior at kf=0 has not been executed in this probe.
- The BK-50 "oracle control" end-state numbers (word8196=11399181 after fault)
  are hereby re-attributed to this root cause by mechanism reasoning, not by a
  fresh paired run under both guard states.
- Numbers are structural (PC coordinates, mode ints, word values, fault codes,
  step counts, md5) — rule-1 floors do not attach; floors file NOT cited.

## Candidate item (backlog format)

**BK-52 — oracle KFAULT_PC=0 trap continuation (guard parity + semantics pin).**
- Gate: `tests/test_bk52_kfault0_trap.py` — L1: seeded-USER out-of-box ST with
  KFAULT_PC=0 → post-repair: task HALTS at the trap (running=False ≤2 steps,
  word8196 unchanged, fault_addr=0x8010, mode=SUPER); L2: same trap WITH a
  handler installed → vectors to handler (unchanged behavior, green today);
  L3: twin-side control (wgsl run at kf=0 halts — pins the already-correct
  posture); L4: non-vacuity (corrupt the guard → L1 goes RED);
  L5: in-BOX overflow sibling site (:1075-1082) same pinned semantics.
- Prereqs: none blocked; lands with/after the BK-38..45 sequenced fence commit
  (same file); RE-BASES BK-50/BK-51 probe expectations (their end-state reads
  change under the repair).
- Blast radius: `tools/glyph_isa_v2.py` (two vector sites) + the named probes'
  end-state legs. Engine file → worktree isolation per AGENTS.md.
