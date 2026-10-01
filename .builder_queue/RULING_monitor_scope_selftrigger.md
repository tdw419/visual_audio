# RULING — monitor self-arm: the printed fingerprint must not contain the loop's own report

**Date:** 2026-09-13 ~20:5x CDT · **Seat:** orchestrator (cron `5ad75de3aac3`, seat-blocker-watch) ·
**Status:** MECHANISM-CLASS — authorized under `.builder_queue/RULING_standing_authorization.md`
("restoring self-documented behaviour"). Reversible; Jericho overrides by editing this file.
**Answers ticket:** `.builder_queue/REPAIR_PENDING_monitor_scope_selftrigger.md`

## Decision

`~/.hermes/scripts/glyph_build_chain_monitor.py` must print a fingerprint built from **repo state only**.
The report-directory leg (`:57-65`) stays — it still feeds `frozen` / `stall_tier` — but it must not reach the
**printed** field. Concretely: the leg's `newest` stays internal; `newest_mtime=` prints `max()` of the
*stat'd tracked-dirty file mtimes* (`0` when the tree is clean). One printed field changes; nothing else.

The lane applies this (it owns the gate discipline for instrument edits). The seat does not hand-edit the
watchdog inside a 15-minute sensor tick.

## Measured evidence (seat's own instruments, this tick, head `39ad5ce`)

| measurement | command | value |
|---|---|---|
| live fingerprint | `python3 ~/.hermes/scripts/glyph_build_chain_monitor.py` | `head=39ad5ce… tracked_dirty=1 newest_mtime=1789350504 state=DIRTY_ACTIVE stall_tier=0 queue=10 ticket_age_h=-1` |
| what that epoch *is* | `stat -c '%Y %s %n'` on the job's report dir | `1789350504 39898 …/af3e62239ce2/2026-09-13_20-48-24.md` — **the loop's own report, byte-for-byte** |
| script identity | `md5sum ~/.hermes/scripts/glyph_build_chain_monitor.py` | `5b868a9571f6f6b9b98dc92d80d82b31` (matches the md5 the ticket's probe asserted) |
| wake cadence in force | `~/.hermes/cron/jobs.json` | job `af3e62239ce2`, `every 2m`, `enabled=True`, `monitor_script=glyph_build_chain_monitor.py` |
| report size per tick | `ls -t …/af3e62239ce2/*.md` (top 3) | 39,898 / 40,396 / 41,046 B — all far over the 1 KB gate at `:62` |
| held probes | `output/monitor_selftrigger_probe.txt:10`, `output/monitor_ticket_age_wake_probe.txt:12` | `PROBE: PASS`, `PROBE VERDICT: PASS` |

**Why this is mechanism-class, not policy.** The script documents its own contract at `:3-15`: the output changes
when (a) a commit lands, (b) the tracked-dirty count changes, (c) tickets appear/vanish, (d) a frozen tree persists.
A cron output file written by the loop is none of those four. `:53-56` states the report leg's purpose in its own
words — blind-spot-#3 activity reset, i.e. it exists so `frozen` is measured against the *run's* end rather than a
stale tracked mtime — and `:126-130` then leaks that value into the hashed stdout. The code's stated contract and
its printed field disagree; the fix makes the code do what it says. No ceiling, no fault vocabulary, no ABI, no
cadence change — so nothing reserved to the seat is touched.

**Live consequence, not a hypothesis.** At the enabled 2-minute cadence every tick appends a ~40 KB report to the
watched directory, so `newest` moves every tick and the hash re-fires the agent: up to ~720 agent runs/day of which
the ticket measured 6 in a 3-hour window writing hold notes, with a no-work wake whose input the ticket records at
~137 K tokens. This is the same shape as the retired `17d00e00`/`Glyph Dispatch Monitor` class
(`glyph_dispatch/docs/MONITOR_RETIRED_20260912.md`): a green instrument re-deriving "nothing changed" at full cost.

## The gate the lane must satisfy (RED shown before GREEN)

Work on a **copy** first; the live report dir is never written by a test. Back up before touching the live script:
`cp -a ~/.hermes/scripts/glyph_build_chain_monitor.py ~/.hermes/scripts/glyph_build_chain_monitor.py.bak-<date>-mon-selfarm`.

- **L0 (falsifier, mandatory):** against the **pre-fix** script (md5 `5b868a…`) with a scratch repo + scratch report
  dir, drop one new >1 KB `.md` into the report dir with *no repo change* → fingerprint **changes**. Same input
  against the fixed script → byte-identical. The RED must reproduce the `newest_mtime` move, not just fail.
- **L1:** two runs, nothing changed → identical bytes.
- **L2:** `touch` a tracked-dirty file → fingerprint changes (condition (b) preserved).
- **L3 (anti-wedge, the 2026-09-08 class):** report stale past `STALL_SECS` → `stall_tier` still increments, so the
  fingerprint can never be permanently stable while a stall persists.
- **L4 (report leg retained):** a fresh report still flips `frozen` to `False` — the decision the leg exists for.
- **L5:** a `head` move and a `queue` count move each still change the fingerprint (conditions (a)/(c)).
- **L6:** the change is one printed field. Diff against the backup must show no other semantic edit; record the new
  md5 and the backup path in the receipt, plus the revert line (`cp -a <bak> <script>`).

## What this ruling does NOT license

- **No cadence tuning.** `ticket_age_h` and its bucket stay as they are. The hourly self-arm on a clean tree with an
  open ticket (`:117-124`) is a *deliberate* level trigger per its own comment, and how hot to keep it is the seat's.
  That half is filed as a separate ticket in `.builder_queue/` with `Seat: Jericho` — deliberately **not named by
  basename in this file** so the seat-blocker sensor keeps reporting it. Do not fold it into this work.
- **No tree-cleaning to fake a clean state.** Committing, ignoring, or `.gitignore`-ing another seat's tracked
  outputs (`tools/builder_eval/*.json`, `results.jsonl`) or this lane's `.update_proposals.log` to force `CLEAN` is
  not authorized here.
- **No re-scoping of the watchdog.** The report leg, `frozen`, `stall_tier`, `MAX_TIER`, the `DEFECT_OPEN` level
  trigger and the roadmap-row matcher (`:95-107`) are untouched — the 2026-09-08 incident was a mis-scoped leg, so
  edits beyond the one printed field are the exact class that produced it.
- **No other script, no schedule change.** Cron intervals/`STALL_SECS` are Jericho's instrument settings.

**Honest boundary:** this removes the *guaranteed per-tick* arm. It does not make the loop silent — while a tracked
file stays dirty (measured now: `.update_proposals.log`) or an open ticket ages, condition (b)/(c) still wake it.
That is the documented behaviour and stays.
