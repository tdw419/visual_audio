# Event-Driven Builder Loop — How the Glyph OS Builds Itself

**Status:** Active as of 2026-09-06
**Job:** `af3e62239ce2` ("Glyph OS Event Chain") — Hermes cron, session `default`
**Replaced:** `f05353787a31` ("Glyph OS Builder Loop", 15-minute timer — removed)
**Branch:** `glyph-transpiler-autoloop` in `/home/jericho/projects/zion/projects/visual_audio`

---

## 1. The Problem It Solves

The original builder was a **timed cron**: every 15 minutes, wake an agent and hope
the previous increment had finished. That has three failure modes:

1. **Wasted runs** — fires while the tree is dirty (previous run still working),
   does nothing, costs an LLM call anyway.
2. **Wrong-time runs** — fires when nothing is ready, or sits idle after a
   commit landed because the next tick is 10 minutes away.
3. **Latency floor** — average ~7.5 minutes of dead time between increments,
   purely a property of the timer, not the work.

The fix is **event-driven chaining**: fire when the repo *state changes*, not
when a clock ticks. The user-visible behavior is exactly what was asked for:

```
prompt → agent response → commit → state change detected → prompt again → ...
```

## 2. Architecture

```
┌────────────────────────────────────────────────────────────────┐
│ Hermes cron scheduler, tick = every 2 minutes                  │
│                                                                │
│   1. Run monitor script (pure Python, NO LLM, ~50ms)          │
│        glyph_build_chain_monitor.py                            │
│        prints: "head=<sha> tracked_dirty=<n>"                  │
│                                                                │
│   2. Hash the output against the previous tick                │
│        SAME   → silent no-op tick. Zero cost. Agent never runs.│
│        CHANGED → inject diff into prompt, run builder agent    │
│                                                                │
│   3. Builder agent (fresh context each fire)                  │
│        RECON → claim next ⏳ roadmap item → RED test →         │
│        implement → regression gate → COMMIT (receipts in body)│
│        → roadmap row updated                                   │
│                                                                │
│   4. The commit CHANGES the git HEAD                          │
│        → next tick's fingerprint differs                       │
│        → chain fires again ≤2 min later. Self-sustaining.     │
└────────────────────────────────────────────────────────────────┘
```

**The load-bearing insight:** the builder's contract is "every increment ends in
a commit." That makes git HEAD a perfect completion event — no custom IPC, no
daemon socket, no message queue. The filesystem that stores the work *is* the
event bus.

## 3. The Monitor Script

Path: `/home/jericho/.hermes/scripts/glyph_build_chain_monitor.py`

It emits a **stable, deterministic fingerprint** of the repo:

```
head=<full commit sha> tracked_dirty=<count of modified/deleted/staged tracked files>
```

Fingerprint changes when:

| Event | Effect on fingerprint |
|---|---|
| New commit lands (increment done) | `head` changes → **agent fires** |
| Tree goes clean after a defer (sibling finished) | `tracked_dirty` 1→0 → **agent fires** |
| Tree goes dirty (sibling starts working) | `tracked_dirty` 0→1 → agent fires, sees dirty tree, defers harmlessly |
| Untracked files change (`output/` artifacts, logs) | ignored (`??` filtered) → silent |
| Nothing happened | identical bytes → silent |

Two properties matter:

- **Determinism:** no timestamps, no random ordering — identical states must
  produce byte-identical output or every tick would look "changed" and the
  agent would fire 720 times a day. (This is the classic monitor-mode bug.)
- **Untracked exclusion:** noisy artifact directories never wake the builder.

## 4. The Builder Agent Contract

Each fire is a **fresh context** (no memory of previous runs). All coordination
happens through repo state, which is the point:

1. **RECON** — read `systems/GLYPH_SELF_HOSTING_ROADMAP.md`.
   Any tracked file dirty? → print `DIRTY TREE — deferred`, touch nothing, stop.
2. **Stale check** — is the first ⏳ item actually still undone? A sibling
   session may have committed it; if so, advance.
3. **RED** — write the failing oracle test first; paste the failing output.
4. **GREEN** — implement; run the item gate + full GH regression suite; paste receipts.
5. **COMMIT** — receipts in the commit body; roadmap row updated with the sha.

Hard rules baked into the prompt:
- Path-restricted: `tools/glyph_gpt/{baker,runner,kernel}.py`,
  `tests/test_gh*.py`, the GH roadmap only. Never rv64i fixtures,
  glyph_dispatch, or SB-3 files.
- Never push, never rewrite history, never `git checkout -- .` (a prior
  revision of the prompt had this — it would have destroyed sibling
  work-in-progress; see §6).
- Resolved design forks (GH-13 mailbox, GH-14 tiered agents) are settled law —
  do not re-litigate. Genuinely unpinned choices → `BLOCKED-human` with two
  proposed options, move on.
- Circuit breakers: 3 failed attempts on one item → BLOCKED with receipt;
  2 consecutive blocks → stop and report.

## 5. Lifecycle & Cost

- **Steady state** (nothing to do): the 2-minute ticks run only the monitor
  script. No model call. Effectively free.
- **Active state** (chain firing): one agent run per completed increment,
  immediately after it. Latency between increments: ≤2 minutes (monitor tick
  interval) instead of ~7.5 minutes average (timer).
- **Self-termination:** the chain stops naturally when the roadmap is done
  (agent commits a final docs commit, fingerprint changes once more, agent
  wakes, finds nothing ⏳, reports complete, and that run's output — identical
  to any future "nothing to do" run — suppresses further fires only while the
  fingerprint stays identical). If you want a hard stop, pause or remove the
  job: `hermes` → cronjob action `pause`/`remove` with id `af3e62239ce2`.
- **Delivery is local-only** (CLI session). Progress is visible via
  `git log --oneline glyph-transpiler-autoloop`; there is no push channel.

## 6. Incident Notes (why the prompt says what it says)

- **Dirty-tree destruction hazard (found before first fire):** the original
  timed loop's RECON said to `git checkout -- .` on a dirty tree. With multiple
  writers (in-session agents, SB-3 session) that would have deleted sibling
  work-in-progress. Now: defer, never discard.
- **Session-scoped crons:** cron jobs are not visible across Hermes sessions.
  A session that didn't create the job cannot list, pause, or verify it —
  cross-session claims about cron state require the owning session to paste
  `cronjob list` output. This caused a genuine "your cron doesn't exist" /
  "yes it does" disagreement that both sides resolved only with receipts.
- **False-green history:** this repo's autonomous loops have repeatedly
  reported fake success. The loop is therefore judged by **commits + receipts**,
  never by its own reports: clean-room test runs, diff-vs-receipt comparison,
  and mechanism-level checks (e.g. did GH-6's test genuinely trap USER→SUPER,
  or take a SUPER-mode shortcut that passes tests while proving nothing).

## 6a. Stall Recovery — the FROZEN_STALLED adoption event (first catch 2026-09-06 ~20:02)

The monitor's original fingerprint (HEAD + dirty-count) had a blind spot: a
run that *dies mid-increment* changes no state, so the chain never fires
again — frozen-dirty and actively-dirty look identical. GH-7 hit exactly this
(files frozen at 18:27, silent past 20:00).

Fix, now deployed on both sides:

1. **Monitor** (`glyph_build_chain_monitor.py`) adds the newest mtime among
   dirty tracked files to the fingerprint; dirty + newest-mtime older than
   30 min ⇒ `state=FROZEN_STALLED` ⇒ hash changes ⇒ chain fires.
2. **Prompt** rule is three-way, not binary:
   - actively dirty (recent mtimes) → defer, touch nothing
   - clean → next roadmap item
   - FROZEN_STALLED → **adopt** the abandoned increment: review the
     uncommitted diff, complete it RED→GREEN, commit. Never discard
     (no `git checkout -- .` — adoption, not erasure).

First catch: the 20:02 tick adopted GH-7, resolved its 3 failing gates
(round-robin interleaving, fault-leg isolation, runner 200→199 lines), and
committed `1a4c064`. Recovery loop proven end-to-end.

## 6a-ii. Stall-recovery hardening — retry ladder + repair queue (2026-09-08)

The 6a fix had a one-shot flaw, exposed by the GH-15 Step 4 stall
(2026-09-07 21:46 → 2026-09-08 06:47, ~9h frozen): once `FROZEN_STALLED`
fired, every field of the fingerprint became constant (no writes, no
commits), the hash went permanently stable, and the chain went silent
after exactly ONE adoption fire — and that fire deferred (d4c9a72) instead
of adopting. Detection worked; *re-fire* didn't.

Three deployed fixes:

1. **Escalating retry ladder** (`glyph_build_chain_monitor.py`): frozen
   trees now report `state=FROZEN_STALLED_T<n>` with
   `n = floor(frozen_minutes/30)` capped at 3, plus `stall_tier=` and
   `queue=` in the fingerprint. Every 30 minutes of persistent stall
   changes the hash ⇒ the adoption agent re-fires with an attempt number
   it can read from the monitor line. A stall is never again a one-shot
   dead end.

2. **Keep-or-revert discipline** (builder contract): a run must NEVER
   exit leaving tracked files dirty. Gate green → commit. Gate failing
   after real attempts → enqueue a repair ticket (below), stash the dirty
   diff (`git stash push -m "run-abandoned-<item>"`), leave the tree
   clean. Frozen-dirty should only ever happen on hard death (OOM, kill),
   never as a policy outcome.

3. **In-repo verbatim repair queue** (`.builder_queue/*.json`): when a
   run can't converge, it commits a structured ticket — NOT a vague
   self-prompt:

   ```json
   {
     "ticket_id": "fix_gh15_step4_wgsl",
     "roadmap_item": "GH-15",
     "step": 4,
     "failing_command": "PYTHONPATH=tools:. python3 -m pytest tests/... -v",
     "verbatim_error": "<exact assertion output, no paraphrase>",
     "files_touched": ["tools/glyph_gpt/atlas.py"],
     "hypothesis": "<one line, or omit>",
     "attempt": 1,
     "max_attempts": 3
   }
   ```

   Queue rules:
   - A ticket without verbatim failing tool output is invalid; the chain
     must reject it rather than execute it (anti-RFL: no "try harder"
     prompts — tickets are receipts, not hopes).
   - The monitor counts `queue=` in its fingerprint; a clean tree with
     tickets reports `state=CLEAN queue=N` ⇒ hash change ⇒ next fire pops
     the oldest ticket INSTEAD of new roadmap work. The ticket commit is
     itself the wake event — still fully event-driven, no heartbeat.
   - Resolution = gate green on the ticketed command → commit + delete
     the ticket file. Attempt ≥ 3 (filename suffix `.a3.json`) → convert
     to a ⚠️ defect cell in the roadmap row + stash + operator alert.
     No infinite self-repair ladder.
   - The repo remains the ONLY completion oracle: a ticket is a claim of
     "broken", never of "done". Done is a commit with a green gate.

First live exercise: the GH-15 Step 4 adoption (5e5e88b) landed before
this hardening shipped; the next stall tests the ladder end-to-end.

## 6b. External auditor — Claude Code gate (cron `3dd4f184d5b0`, 30m)

`claude_glyph_auditor.py` + `no_agent` cron: silent when no new commits,
defers on dirty tree (without advancing its pointer), audits up to 3 commits
per tick when clean, retries the same range after a timeout. Claude runs with
a **pytest-only allowlist** (`Read`, `Grep`, `git diff/show/log`,
`python3 -m pytest`), cwd = repo root — a third writer stack with zero write
access. State: `~/.hermes/state/claude_glyph_audit.json`.

**Auditor cwd pitfall (recorded 2026-09-06):** the auditor flagged the
glyph_dispatch SHA-256 lockstep gate "unreproducible — missing
`wordbase.db`". False alarm: the DB is tracked at the repo root, and the gate
passes 13/13 from the repo root; the failure came from a runner resolving the
DB relative to its own execution directory instead of the repo root. Any
sandbox runner MUST execute gates from the repo root (the auditor's cron
already pins `cwd=REPO`).

## 7. Operator Runbook

```bash
# What is the loop doing right now?
git -C /home/jericho/projects/zion/projects/visual_audio log --oneline -5
git -C /home/jericho/projects/zion/projects/visual_audio status --short

# What does the monitor see?
python3 /home/jericho/.hermes/scripts/glyph_build_chain_monitor.py

# Pause / resume / stop the chain (from the owning Hermes session)
#   cronjob action=pause  job_id=af3e62239ce2
#   cronjob action=resume job_id=af3e62239ce2
#   cronjob action=remove job_id=af3e62239ce2

# Audit an increment (never trust the receipt alone)
git -C /home/jericho/projects/zion/projects/visual_audio show <sha>   # diff vs receipt
PYTHONPATH=tools:. python3 -m pytest tests/test_gh*.py -q             # clean-room gate
```

**Working alongside the loop:** do host-side work either in a `git worktree`
(zero interference) or in non-loop-owned paths (SB-3, glyph_dispatch, docs),
committing small and fast — every hour of uncommitted dirty files is a tick
the chain defers.

## Model Escalation Receipt (2026-09-07 06:15)
qwen2.5-coder:14b ran the chain 23:01–06:10: ~240 fires, all 'completed',
ZERO commits — failed to adopt the frozen 22:07 baker.py increment. Diff was
also wrong-item (GH-9 loader, pre-priority-rule). Action: WIP preserved in
stash@{0} (message names it), builder flipped back to glm-4.7 for GH-8b.
Rule confirmed: local model = cheap ticks, cloud = hard increments. qwen
remains default AFTER GH-8b lands, for mechanical GH-9+ items, one at a time.
