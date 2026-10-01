# GLYPH OS BUILDER — OPERATIONS & REBUILD MANUAL

**Purpose:** Everything needed to understand, operate, or REBUILD FROM SCRATCH
the autonomous builder loop that develops the Glyph GPU OS.

**Repo:** `/home/jericho/projects/zion/projects/visual_audio` (branch
`glyph-transpiler-autoloop`) · **Owner:** Jericho · **Last verified:**
2026-09-24 (all job states read live from `~/.hermes/cron/jobs.json`)

---

## 1. THE MENTAL MODEL

One sentence: **a cron-fired LLM agent reads a ledger file in the repo,
claims work, builds it, gates it, receipts it, commits it — and a monitor
script ensures it only wakes when there is real work or real change.**

The design principle: *the repo is the database.* Every claim, ruling,
receipt, brief, and defect lives as a committed file in
`.builder_queue/`. Cron state lives in `~/.hermes/cron/jobs.json`.
Nothing important lives only in anyone's memory.

```
                    ┌──────────────────────────────┐
                    │  Hermes cron (every 2 min)   │
                    │  job af3e62239ce2            │
                    └──────────┬───────────────────┘
                               │ runs monitor script FIRST
                               ▼
              ┌────────────────────────────────────┐
              │ glyph_build_chain_monitor.py       │
              │ (canonical: tools/ in repo; shim   │
              │  in ~/.hermes/scripts/ for cron)   │
              │ Prints: head= state= queue= supply=│
              └───────┬──────────────────┬─────────┘
        output UNCHANGED   │        output CHANGED
        (silent no-op tick)│        (wakes the agent)
                           ▼                ▼
                   [nothing happens]  ┌─────────────────────────┐
                                      │ LLM agent (GLM) runs    │
                                      │ with the job PROMPT:    │
                                      │ PHASE 1a: read ledger   │
                                      │ PHASE 1b: claim queue   │
                                      │ PHASE 1c: research if   │
                                      │          queue empty    │
                                      │ PHASE 2:  build + gate  │
                                      │ PHASE 3:  receipt+commit│
                                      └─────────────────────────┘
```

**Components (all rebuildable from this doc):**

| Component | Location | Role |
|---|---|---|
| Builder cron job | `~/.hermes/cron/jobs.json` id `af3e62239ce2`, name "Glyph OS Event Chain", `*/2 * * * *`, deliver=local, enabled | The heartbeat. Prompt = the lane's constitution (12KB, see §3). Monitor-gated. |
| Monitor script (canonical) | `tools/glyph_build_chain_monitor.py` (repo) | Cheap check: prints `head=<sha> tracked_dirty=N state=CLEAN|DIRTY_ACTIVE stall_tier=N queue=N supply=ok`. Hash of this output gates the agent. |
| Monitor shim | `~/.hermes/scripts/glyph_build_chain_monitor.py` | 12-line runpy shim so cron can execute the repo-canonical script. **Never edit behavior here.** |
| Ledger | `.builder_queue/PRODUCT_LANE_STATE.md` | THE database. STATUS line, current rung, claim queue rounds, rulings, receipts index. Agent reads it FIRST every tick. |
| Backlog | `systems/GLYPH_BACKLOG.md` | Spec'd-but-unclaimed work rows (BK-N format with gate specs). |
| Receipts | `.builder_queue/RECEIPT_*.md` | Evidence per landing: RED-first arc, gate transcript, "what this PASS does NOT prove". |
| Dogfood daemon | system crontab: `*/10 * * * * tools/dogfood_gpu_os.py --cron` | LLM-driven fuzzer driving GlyphL1Shell; files `.builder_queue/DEFECT_DOGFOOD_*.json` on anomaly; marks RESOLVED on green re-run. |
| Dogfood CI gate | `tests/test_bk23_dogfood_ci_gate.py` | Proves the above loop's machinery works (suite pass, schema, wake trigger, self-heal, budget). |
| External auditor | cron `3dd4f184d5b0` "Claude Code GH Auditor" `*/30` | Clean-room `claude -p` audit of recent commits; HEAD-gated; never commits. |
| Output archive | `~/.hermes/cron/output/af3e62239ce2/` | Every tick's full transcript (51+ files). Forensics live here. |

**Intentionally PAUSED jobs (do not "fix"):**
- `5ad75de3aac3` seat-blocker-watch, `6bc104112fff` glyph-os-health-watch —
  paused 2026-09-19 14:35 by Jericho; resuming is his call alone.
- `b0f0eb15a225` product-lane standalone (2h) — superseded by af3e62239ce2;
  paused to prevent lane contention.

**Rule:** cron truth = `~/.hermes/cron/jobs.json`, read live. Tickets,
ledger prose, and session memory about cron state go stale; the JSON does not.

---

## 2. THE TICK CYCLE (what happens every 2 minutes)

1. Cron fires; runs `glyph_build_chain_monitor.py` first.
2. Monitor reads repo HEAD, dirty state, ledger queue count. Prints one line.
3. Hermes hashes the monitor output (exact bytes):
   - **Unchanged** → suppress the LLM entirely. Silent tick. Zero tokens.
   - **Changed** → inject "MONITOR CHANGE DETECTED" + diff into the prompt,
     run the LLM agent with the job prompt.
4. Agent executes the prompt's phases (§3).
5. Full transcript written to `~/.hermes/cron/output/af3e62239ce2/<ts>.md`.

This is the Hermes "change-gated monitor" pattern: the LLM only wakes on
real churn. That's how a 2-minute cron costs near-nothing while idle.

---

## 3. THE PROMPT (the lane's constitution)

Stored in `jobs.json` under `af3e62239ce2.prompt` (~12KB). Key clauses —
a rebuild MUST reproduce these:

1. **Ledger-first:** read `PRODUCT_LANE_STATE.md` FIRST. If its STATUS is
   FALSIFIED / PAUSED / COMPLETE → output nothing, end silently. Never
   revive a falsified lane.
2. **PHASE 1a/1b:** check the claim queue (the `## CLAIM QUEUE ROUND N`
   sections). One active ticket at a time, lowest number first. If queue
   empty → PHASE 1c research: exactly ONE new backlog row per tick, from
   real friction (never re-research an existing RESEARCH_*/BK row).
3. **Mailbox rule:** re-verify HEAD before acting (parallel sessions land
   work mid-flight; never act on stale briefs).
4. **Gate discipline:** every landing is RED-first (prove the test can
   fail) → GREEN → full lane-family regression → WGSL twin parity for
   engine changes (same commit) → receipt with "what this PASS does NOT
   prove" → commit so HEAD backs the claim.
5. **Honesty clause:** a ledger claim HEAD doesn't back is a defect;
   complete-or-revert it, never re-state it.
6. **Self-hosting phase doctrine:** invocation-inside (Phase 2, landed) ≠
   authoring-inside (L4) ≠ execution-inside (Phase 3). Every claim names
   its phase and shows the boundary leg.
7. **Halt/continuity:** verdicts like "landed" require commit hash +
   re-runnable probe. Batch/pipe verification never certifies UI/pixels
   (operator-eyes legs stay PENDING in receipts).

To rebuild: `hermes cron create` with schedule `*/2 * * * *`,
`monitor_script=glyph_build_chain_monitor.py`, `deliver=local`, and the
prompt reconstructed from this section + the current prompt in jobs.json
(export it first: read the JSON, extract `.prompt`).

---

## 4. THE SUPPLY CHAIN (how work enters the queue)

Three legitimate sources, in priority order:

1. **Seat lane rounds** — a Hermes operator session files
   `## CLAIM QUEUE ROUND N` in the ledger with numbered items, each with
   brief + gate + receipt name. Committed to the repo. (Rounds 1-11 exist.)
2. **Operator direct orders** — verbatim quotes recorded in the ledger
   (e.g. "make the builder work on this" 09-21; "just make the software"
   09-23 → R5.3 waived, build-only mode; "make this work as good as
   Linux" 09-24 → the L1-L4 layers).
3. **Research ticks (PHASE 1c)** — when the queue is empty, the lane
   derives ONE backlog row from real friction: day-1 use-log complaints,
   defects in shipped code, measured gaps (font coverage, suite OOM).
   These become BK-rows in `systems/GLYPH_BACKLOG.md`.

**Backlog ratification:** delegated to the seat lane under build-only mode
(POLICY_decision_delegation_20260918 + 2026-09-23 ruling). Operator reviews
receipts at leisure; nothing waits on him.

---

## 5. THE QUALITY MACHINE (why the output is trustworthy)

- **RED-first gates:** each test lands with proof it can fail (mutant
  leg, pre-fix probe transcript, or module-removal import error). No
  vacuous passes.
- **Receipts:** every landing ships `.builder_queue/RECEIPT_<thing>.md`
  with base revision, gate transcript, and an explicit NOT-verified list.
- **Twin parity:** engine changes re-pin the WGSL shader path in the same
  commit (the CALLR lesson: no oracle/shader drift).
- **Dogfood loop:** every 10 min, an LLM fuzzes the shell through its
  front door (GlyphL1Shell), files structured defects with Ollama triage,
  and the monitor's queue counter wakes the builder to fix them. BK-23's
  CI gate proves the loop's machinery (wake trigger, self-heal) works.
- **External audit:** Claude Code reviews recent commits clean-room every
  30 min, running tests itself, committing nothing.
- **Keep-or-revert:** migration/refactor steps are subject to the same
  gates; any step that weakens a gate is reverted.

---

## 6. OPERATIONS RUNBOOK

**Check health:**
```bash
python3 tools/glyph_build_chain_monitor.py     # want: CLEAN, stall_tier=0
python3 -m pytest tests/test_bk23_dogfood_ci_gate.py -q   # loop machinery
tail -5 ~/projects/zion/projects/visual_audio/.builder_queue/dogfood_cron.log
```

**Read the last tick:**
```bash
ls -t ~/.hermes/cron/output/af3e62239ce2/ | head -3
```

**File new work (the only way work enters):** append a
`## CLAIM QUEUE ROUND N+1` section to `.builder_queue/PRODUCT_LANE_STATE.md`
with numbered items (brief + gate + receipt name), commit. The monitor hash
changes; the lane claims on its next tick. **Do not** edit jobs.json to
change what the builder works on — the ledger is the interface.

**Pause the builder (full stop):**
```bash
hermes cron pause af3e62239ce2    # resume: hermes cron resume af3e62239ce2
```
First tick after resume runs the agent (hash drift) — normal.

**Silent-stall triage:** (1) monitor output unchanged for hours + no new
ticks in output/ → check cron process, then jobs.json enabled flag.
(2) Ticks present but status no_change → tree is static; that's correct
idle behavior, not a stall. (3) state=FALSIFIED in ledger → STOP; that
means a landing claim failed verification — human investigation required.

**REBUILD FROM SCRATCH (complete procedure):**
1. Hermes installed + gateway running (job scheduling enabled in config).
2. Recreate the monitor shim: `~/.hermes/scripts/glyph_build_chain_monitor.py`
   as the 12-line runpy shim pointing at
   `<repo>/tools/glyph_build_chain_monitor.py` (repo copy is canonical and
   test-gated by `tests/test_monitor_fingerprint_hygiene.py`).
3. Recreate the builder job:
   ```
   hermes cron create \
     --name "Glyph OS Event Chain" \
     --schedule "*/2 * * * *" \
     --monitor-script glyph_build_chain_monitor.py \
     --deliver local \
     --prompt "<constitution — reconstruct per §3, or export from a
               jobs.json backup>"
   ```
4. Recreate the dogfood crontab line (system crontab, not Hermes):
   `*/10 * * * * cd <repo> && /usr/bin/python3 tools/dogfood_gpu_os.py
   --cron >> .builder_queue/dogfood_cron.log 2>&1`
5. Recreate the auditor job: `*/30 * * * *`, script
   `~/.hermes/scripts/claude_glyph_auditor.py`, no_agent pattern
   (script IS the job), deliver local.
6. Verify: monitor prints `state=CLEAN`; file a trivial ledger round and
   confirm the lane claims it within one tick; run the BK-23 gate.
7. Leave 5ad75de3aac3 / 6bc104112fff / b0f0eb15a225 paused unless Jericho
   says otherwise (see §1).

**State to back up** (everything else is regenerable): `jobs.json`
(the prompt!), the repo (ledger + receipts + gates), `~/.hermes/cron/output/`
(forensics), system crontab.

---

## 7. HISTORICAL DIRECTIVES (do not re-litigate)

- 2026-09-19 14:22: builder halted by Jericho (BM905 era). **Superseded:**
  af3e62239ce2 unpaused + redirected 2026-09-21; watchdogs remain paused.
  Record: `.builder_queue/TICKET_BUILDER_HALTED_JERICHO_20260919_1422.md`
  (updated 09-24 with verified topology).
- 2026-09-21: "make the builder work on this" → PRODUCT_ROADMAP.md became
  the target; product lane born.
- 2026-09-23: "i dont want to have to answer any questions or do the 30 day
  thing. please just make the software." → R5.3 gate WAIVED-BY-OPERATOR;
  build-only mode; backlog ratification delegated to seat lane.
- 2026-09-23: agent-pre-verification amendment (AMENDMENT_DTF1): receipts
  certify correctness only; usability needs a human at the chair.
- 2026-09-24: self-hosting phase doctrine (invocation/authoring/execution);
  native coreutils prioritized over QEMU/Linux guest; workbench unification
  (items 22+23 = one staging primitive).

---

*This document lives in the repo it describes. If the builder and this
doc disagree, check jobs.json and the ledger, then fix whichever is wrong.*
