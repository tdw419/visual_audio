# REBUILDING GLYPH OS FROM SCRATCH

**Purpose:** If everything disappeared — repo, cron jobs, monitor scripts, Hermes state — this document
is the complete recipe to reconstruct the project and the autonomous loop that builds it.
**Written:** 2026-09-09, at GH-20-in-flight. Update the "Current State" section as items land.
**Source of truth order of authority:** (1) this file's process rules, (2) `systems/GLYPH_SELF_HOSTING_ROADMAP.md`
for *what* to build, (3) memory/skills for *how* (pitfalls), never a receipt alone.

---

## 1. WHAT THIS PROJECT IS (recovered in one paragraph)

Glyph OS: a spatial computer where a 2D pixel image IS the machine — program code, kernel, syscall
table, stdlib, and filesystem are all pixel regions executed by GlyphCPUv2 (a Python reference CPU with
a WGSL GPU twin, required to stay bit-parity-exact). A Python toolchain (baker, oracle, autoatlas)
*compiles and admits* spatial code but never runs the system. Self-hosting here means: **new code
enters the image ONLY through an oracle-verified admission gate** (`autoatlas.ingest()`), not because a
host script wrote pixels. The roadmap migrates one category at a time (syscalls → stdlib → FS → POSIX →
libc) from host-Python into proven in-image tiles. "Proof before run, receipts as hashes" is the
constitutional rule — a feature without a failing-test-first gate and a commit receipt is out of scope,
no matter how useful it looks.

## 2. REPOSITORY LAYOUT (what to recreate)

```
visual_audio/                       # branch: glyph-transpiler-autoloop (NOT master)
├── systems/GLYPH_SELF_HOSTING_ROADMAP.md   # THE plan: GH-1..GH-25 rows, each with full gate spec
├── tools/glyph_gpt/
│   ├── baker.py            (~4.5K lines — assembles Glyph ISA v2 asm → pixel image; all kernel modes)
│   ├── autoatlas.py        (admission pipeline: ingest() + admit_syscall() + _pix_write_word())
│   ├── oracle.py           (GlyphCPUv2 word-exact verification harness)
│   └── checkpoint.pt       (GlyphGPT 838K params — neural drafting, optional but referenced)
├── tools/glyph_isa_v2.py   (OpcodeMapV2 — NOTE: ADD/SUB/AND/OR/XOR/SHL/SHR only, NO MUL)
├── tools/geos_hilbert.py   (d2xy Hilbert addressing — shared coordinate space, do not fork it)
├── glyph_dispatch/         (sibling subsystem: RISC-V control plane + GPU offload, own ROADMAP.md)
├── tests/test_ghN_*.py     (one gate file per roadmap item; the ONLY completion oracle)
├── .builder_queue/         (JSON tickets: {"ticket_id","step","failing_command","attempt","max_attempts"})
│   └── resolved/           (retired tickets live here, never deleted)
├── .worktrees/<name>/      (parallel tracks work in isolated git worktrees, merge only after green)
└── output/                 (bakes + debug probes; .gitignore'd except receipt-cited files)
```

## 3. THE FIVE CRON JOBS (the loop, exactly as running today)

All live in `~/.hermes/cron/jobs.json`; scripts in `~/.hermes/scripts/`. Rebuild in this order:

### 3.1 glyph_build_chain_monitor.py  — the nervous system (no_agent monitor)
Fingerprint-driven event chain. Prints ONE stable line, hashed per tick; unchanged = silent free tick.
```
head=<sha> tracked_dirty=<n> newest_mtime=<t> state=<STATE> stall_tier=<n> queue=<n> ticket_age_h=<n>
```
States (the hard-won logic — ALL THREE triggers are load-bearing):
- `DIRTY_ACTIVE` — tracked files modified → builder at work, don't touch.
- `FROZEN_STALLED_T{1..3}` — dirty AND mtime older than 30m; tier escalates every 30m (circuit breaker
  at T3: auto-stash + defect). **MUST stat absolute paths** (`os.path.join(REPO, p)`) — the scheduler's
  CWD is not the repo; relative stat fails → mtime 0 → wedged silent (2026-09-08 incident).
- `CLEAN` — tree clean.
- `REPAIR_PENDING` — **CLEAN + open `.json` ticket in `.builder_queue/`** → level-trigger:
  include `ticket_age_h` (hours since newest ticket mtime) in the fingerprint so it stays hot until the
  ticket retires. Without this, a committed-RED-gate + stable-queue-count freezes the hash and the loop
  sleeps forever (2026-09-09 incident: GH-20 slept 22:41→02:35). Open tickets ARE pending work; queue
  COUNT alone is not a signal because it doesn't change when a ticket sits unadopted.
- `DEFECT_OPEN` — clean tree + `⚠️` marker in roadmap rows.

### 3.2 "Glyph OS Event Chain" cron (id af3e62239ce2) — the builder
- Schedule: every 2 minutes. Model: glm-4.7 (pinned). monitor_script: glyph_build_chain_monitor.py.
- Prompt (verbatim, ~600 chars — short by design, context flows via continuity):
  "You are the Glyph OS builder loop for <REPO> (branch glyph-transpiler-autoloop). Clean tree + no
  tickets + no defects → implement the next open roadmap item in the Agent OS Arc (GH-16+) /
  Linux Integration Arc (GH-21..23) of systems/GLYPH_SELF_HOSTING_ROADMAP.md. Gate requirements are
  fully specified in the roadmap rows — implement exactly those legs, no design guessing.
  Receipt discipline: failing-test output before the fix, passing run after."
- Job MUST have `continuity: true` — each run inherits the previous run's output (probe scripts,
  diagnoses, ABI facts). This is the single biggest effectiveness multiplier.
- Steering: to course-correct a live relay, add `steering_external` key to the open ticket's JSON
  (additive only — never touch attempt counters).

### 3.3 Parallel-track worker cron (e.g. "GH-19 Stdlib Parallel Worker", id 3f328069efef)
- Schedule: every 15m, no monitor (fires only when a parallel item exists; disable when done).
- Prompt rules that made it work: absolute worktree path + CWD discipline (every command prefixed with
  `cd <worktree> &&`), commit ONLY to its branch, never merge (main chain merges after green + full
  regression from clean), do-not-touch list for main-chain files, keep-or-revert after 3 failed
  attempts, one commit per small batch (smallest risk first).
- Merge rule: merge to glyph-transpiler-autoloop only when the blocking main-chain item is green AND
  full regression passes from clean on the merge result.

### 3.4 "Claude Code GH Auditor" (id 3dd4f184d5b0) — the second opinion
- Every 30m, script claude_glyph_auditor.py, no_agent pattern. Two-tier: HEAD unchanged since last
  audit → silent exit; dirty → skip (never audit WIP); new commits (max 3, oldest first) →
  `claude -p` clean-room audit (it reads diffs + runs pytest itself). State in
  `~/.hermes/state/claude_glyph_audit.json`. Clean-room means: no continuity, sees only the diff —
  catches what the builder's own context blindspots hide.

### 3.5 glyph-os-health-watch (id 6bc104112fff) — sibling-subsystem watchdog
- Every 10m, monitor glyph_health_monitor.py — same hash pattern, for glyph_dispatch/ (verify.py gate,
  worktree cleanliness, stale daemon PIDs). Rebuild only if you keep glyph_dispatch.

## 4. THE OPERATING DISCIPLINE (the part that actually makes it work)

1. **Tickets over vibes.** Every unit of work enters as a JSON ticket: failing_command, context,
   attempt/max_attempts=3. The builder never invents scope; the roadmap row is the spec.
2. **Receipt discipline.** Every commit message: failing-test output BEFORE the fix, passing run AFTER.
   No summary sentences. (Reason: prevents the false-COMPLETE disease that killed earlier cron
   generations — see glyph_dispatch/ROADMAP.md preamble.)
3. **RED gate first.** Implementation items commit the loudly-failing test file BEFORE the
   implementation (GH-20 pattern: gate imports a function that doesn't exist yet). The spec is code.
4. **Verification seat.** An oversight session (human or Hermes main chat) NEVER edits the tree while a
   run is in flight. Its jobs: (a) re-run gates from CLEAN tree on every commit — never trust the
   loop's own tally; (b) confirm the Ollama-gated leg actually RAN (Ollama up), not skipped;
   (c) read landed diffs to reconcile ABI facts into specs; (d) file follow-up tickets for durability
   hazards found in diffs (e.g. table-reservation).
5. **Keep-or-revert.** 3 failed attempts on one failure → revert, record failure fingerprint in the
   queue, move on. The relay re-attacks with fresh context.
6. **Honest state only.** "Iteration cap hit mid-verify — not complete, no commit" is a GOOD run
   outcome. A run that can't finish should leave probes + a handoff note in its continuity output.
7. **Protected assets.** voicebook/, .rts/, rs_fixtures.json, boot containers — never modified without
   explicit user approval (AGENTS.md constitution). Never `rm -rf` directories; delete named files.

## 5. LESSONS PAID FOR IN RUNS (do not relearn these)

- **API timeouts (~150s) will kill runs mid-implementation.** The relay design assumes it: monitor
  re-fires, next run inherits probes + diagnosis, attempt counter increments. 2.3% failure rate is
  normal and self-healing. Do NOT swap models because of timeouts (they're provider-side).
  FIX APPLIED 2026-09-09: per-provider knobs in config.yaml under the provider block —
  `request_timeout_seconds: 600` (per-call ceiling, default 1800 but provider stalls hit the stale
  detector first) and `stale_timeout_seconds: 240` (time-to-first-byte before failover; implicit
  default 90s was too tight for glm-4.7's long thinking pauses). Backups: /tmp/config.yaml.bak-*.
  Knobs documented in hermes-agent run_agent.py::_resolved_api_call_timeout.
- **Monitor blind spots are the #1 infrastructure risk.** Two incidents, both "fingerprint froze":
  relative stat paths (fix: absolute), open-ticket-on-clean-tree (fix: REPAIR_PENDING + ticket_age_h).
  Generalize: ANY state the loop should act on MUST appear in the fingerprint, level-triggered, until
  resolved. A state that doesn't change the hash = invisible = infinite sleep.
- **ISA facts that cost sessions:** no MUL in OpcodeMapV2 (multiply = shift-add triple). LDI is exact —
  decimalize hex constants carefully (one 0x0ABC000C-vs-decimal typo ate a session). CMP writes a flag
  REGISTER (r0); CMP against r0 compares flag-to-flag, not value-to-zero. RAM-seeded words die between
  drive() calls — persist via image pixels (admit-mode PTE_PIX walk).
- **Address computations must be fail-safe.** _pix_write_word: explicit branches per region (fs window /
  tile rect / else ValueError). An unconstrained fallback once stamped a tile PC into dispatcher code —
  4 sessions to excavate. Any new word→pixel mapping gets an explicit branch + a reservation assertion.
- **Parallel tracks work only in worktrees** with file-ownership rules, and merge only through
  green-gate + full-regression preconditions written into the roadmap itself.
- **Phantom failures happen — suspect the test too.** One "bug" was a test asserting a hex-as-decimal
  constant wrong. Probe before patching the kernel.
- **Cron output dirs grow unbounded** (1.9 GB/day with continuity embedding). Prune periodically.
  output/ debug probes compound too — keep only receipt-cited ones.

## 6. BOOTSTRAP SEQUENCE (from zero, in order)

1. Repo on branch `glyph-transpiler-autoloop`; restore tools/ + tests/ + roadmap from backup (or
   accept rebuilding from GH-1: baker → oracle → standalone image → kernel-in-image → loader, per the
   roadmap's Phase-12 pattern — ~GH-1..GH-5 are the "from true scratch" path).
2. Write glyph_build_chain_monitor.py FIRST (§3.1), verify all five states by hand-simulating:
   touch a file → DIRTY_ACTIVE; sleep 31m → T1; clean+ticket → REPAIR_PENDING with age.
3. Create the builder cron (§3.2) with continuity ON. Queue a FIRST TICKET (don't let it roam):
   a small, fully-specified item with an existing gate (e.g. "make test_ghX pass").
4. Confirm the relay: run → commit → HEAD changes → monitor fires → next adoption. Only then add
   complexity (parallel worker, auditor).
5. Rebuild discipline incrementally: AGENTS.md constitution → keep-or-revert rule → receipt rule →
   clean-gate verification seat.
6. Restore scheduling hygiene: builder every 2m, parallel 15m, auditor 30m, health 10m. Stagger to
   avoid tick collisions (builder :00/:02..., auditor :30).

## 7. CURRENT STATE (update as items land — 2026-09-09 10:40)

- Green: GH-1..GH-17 (21 roadmap checks), GH-18 14/14 (incl. table-reservation leg), GH-19 27/27 merged, GH-20 5/5 (Pixel-FS v2 landed in 0d83f89).
- Active / Queued: GH-21 POSIX shim (mapping RV32/RV64 ECALLs sys_read=63, sys_write=64, sys_openat=56, sys_close=57, sys_exit=93, sys_brk=214 to Glyph syscalls/tiles).
- Queued downstream: GH-22 driver ABI, GH-23 picolibc, GH-24 observation bridge (S1+S2 only, S3 human-gated), GH-25 horizon stub.
- Tree state: clean at HEAD, builder loop active on branch glyph-transpiler-autoloop.
