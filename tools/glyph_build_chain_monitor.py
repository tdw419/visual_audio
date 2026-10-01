"""Event-chain monitor for the Glyph OS builder loop.

Repo twin: the live copy at ~/.hermes/scripts/glyph_build_chain_monitor.py is
a shim that executes THIS file (same pattern as tools/seat_blocker_sensor.py),
so the lane can extend the instrument and it stays versioned.

Emits a STABLE state fingerprint of the visual_audio repo.
Cron hash-suppression: unchanged output = silent no-agent tick (free).
Output changes when:
  (a) a new commit lands,
  (b) the tracked-dirty count changes (defer -> clean etc.),
  (c) repair tickets appear/vanish in .builder_queue/ (REPAIR_PENDING),
  (d) a frozen-dirty tree persists — the stall TIER increments every
      STALL_SECS (30 min), so the fingerprint keeps changing and the
      adoption agent re-fires with rising attempt numbers. A stall can
      no longer be a one-shot dead end (2026-09-08 fix).
  (e) SUPPLY_STARVED — clean tree, no open tickets/defects, roadmap fully
      done: the top backlog row id enters the fingerprint as a LEVEL
      trigger so the backlog-promotion policy in the builder prompt gets
      woken. Roadmap exhaustion must not look like healthy rest
      (2026-09-19 incident: 9h silent idle after the last brief was
      consumed; see .builder_queue/REPAIR_PENDING_monitor_newest_mtime_epoch.md).

2026-09-19 stall-breaker fix (same incident): RUNTIME files — live-guest
heartbeats (.hermes_guest_context/) and pixel-container churn
(ubuntu_desktop_pxc1_v3_selfhost/, .pxc1_delta.jnl) — no longer feed the
dirty channel. They are rewritten every ~2min by daemons forever, so the
max-mtime freshness test could never see the tree as frozen: the stall
circuit breaker was dead while 243 tracked files looked perpetually fresh.
Landed work still signals via (a) head, WIP via real builder files.
Untracked files are ignored so output/ artifacts don't wake the agent.

2026-09-30 worktree-blindness fix (af3e62239ce2, BK-41 incident): the
builder correctly did its 35-minute session in an isolated git worktree
(worktrees/bk41-config, per AGENTS.md blast-radius rules). Mainline HEAD
never moved and mainline stayed tracked-clean, so every 2-minute tick
hashed identical output -> no_change (agent suppressed) from 13:48
onward while unlanded work sat in the worktree. WORK IN A WORKTREE IS
STILL WORK: (f) any linked worktree with tracked-dirty files or commits
unmerged into mainline now feeds the SAME channels mainline dirt does —
the dirty count, the freshness pool (stall tiers still escalate on an
abandoned worktree), and a wt= detail field so the woken agent knows
where the unlanded work lives. Untracked-only worktrees stay inert
(same artifact-churn philosophy as mainline). Clean-tree output is
byte-identical to the pre-fix format.
"""
import json
import os
import re
import subprocess
import sys
import time

REPO = "/home/jericho/projects/zion/projects/visual_audio"
STALL_SECS = 30 * 60
QUEUE_DIR = os.path.join(REPO, ".builder_queue")
ROADMAP = "systems/GLYPH_SELF_HOSTING_ROADMAP.md"
BACKLOG = "systems/GLYPH_BACKLOG.md"
MAX_TIER = 3  # circuit breaker: tier >= MAX_TIER -> auto-stash + defect

# Daemon/runtime churn: these tracked paths are rewritten continuously by
# live processes (guest Hermes heartbeat, pixel writeback). They are repo
# state only in the sense that a running machine is "state" — they must
# never make a 9h-stalled tree look fresh.
RUNTIME_EXEMPT_DIRS = (
    ".hermes_guest_context/",
    "ubuntu_desktop_pxc1_v3_selfhost/",
)
RUNTIME_EXEMPT_FILES = (
    ".pxc1_delta.jnl",
    # 2026-09-22 phantom-stall fix: the live runtime appends "Test" proposal
    # pings to this tracked log every ~5min (llama3.1 update-proposal watcher).
    # It is in .gitignore but tracked (added before the ignore rule), so its
    # continuous rewrites kept the freshness pool warm -> FROZEN_STALLED was
    # unreachable while the lane idled (observed as FROZEN_STALLED_T1 climbing
    # only via stale mtimes of OTHER churn files). Exempt it like the guest
    # heartbeat. Same class as the 2026-09-19 exemption pass (055fadea).
    ".update_proposals.log",
    # .venv console-script shebangs flip between python3.11/python3 on every
    # env-repair reinstall (measured diff: path-string only, no logic). One-time
    # churn with zero repo meaning; a tree that is otherwise clean must not
    # look dirty-stalled because of an interpreter upgrade.
    ".venv/bin/normalizer",
    ".venv/bin/numba",
    # 2026-09-28 self-reference churn fix (measured, af3e62239ce2): the build
    # map embeds the last-400-commit window + frontier_commit + generated_at
    # in build_map_data.json, so EVERY commit makes the committed copy stale
    # and the next regeneration (BM000 watchdog step 7, glyph_builder_watchdog
    # :421-431) re-dirties the tree ~5min later. Measured: committing the map
    # re-dirtied it 11s after landing; the window shift (oldest commit evicted)
    # means the committed copy can NEVER converge — a fixpoint that does not
    # exist. The churn also kept the freshness pool permanently warm, making
    # FROZEN_STALLED unreachable (same phantom-freshness class as the
    # 2026-09-22 exemption above). Map content is repo state via HEAD commits,
    # which the fingerprint already carries as `head=` — no signal is lost.
    "build_map_data.json",
    "build_map.png",
)

_ID_RE = re.compile(r"^[A-Z][A-Z0-9-]+$")
_DONE_RE = re.compile(r"✅\s*\**\s*done", re.IGNORECASE)


def is_exempt(path: str) -> bool:
    """True for daemon-churn files that must not feed freshness/dirty signals."""
    return (
        path.startswith(RUNTIME_EXEMPT_DIRS)
        or path in RUNTIME_EXEMPT_FILES
    )


def _git(*args: str) -> str:
    r = subprocess.run(
        ["git", "-C", REPO, *args], capture_output=True, text=True, timeout=30
    )
    return r.stdout


def open_roadmap_rows(text: str) -> list:
    """Roadmap TABLE rows whose status cell is not a done-closure."""
    ids = []
    for line in text.splitlines():
        if not line.lstrip().startswith("|"):
            continue
        cols = [c.strip() for c in line.split("|") if c.strip()]
        if len(cols) < 2:
            continue
        rid, status = cols[0], cols[-1]
        if not _ID_RE.match(rid) or rid in ("ID", "Row"):
            continue
        if _DONE_RE.search(status):
            continue
        ids.append(rid)
    return ids


def top_backlog_row(text: str) -> str:
    """First backlog table row id (BK-...), or '' if the backlog is empty."""
    for line in text.splitlines():
        if not line.lstrip().startswith("|"):
            continue
        cols = [c.strip() for c in line.split("|") if c.strip()]
        if cols and cols[0].startswith("BK-"):
            return cols[0]
    return ""


def _ticket_status(fn: str) -> str:
    """Ticket-state extraction: TOP-LEVEL 'status' only.

    2026-09-28 phantom fix (CURRENT_TICKET.json
    REPAIR_bk54_results_file_counts_as_ticket): the old body regex-matched
    the FIRST '"status"' anywhere in the file, so probe-results DATA (e.g.
    probe_bk54_blast_radius_af3e.results.json, whose nested probe legs carry
    '"status": "OK"') counted as an open ticket -> permanent REPAIR_PENDING
    queue=1 on a CLEAN tree. Parse the JSON and read the top-level key;
    nested leg statuses are DATA, not ticket state. Gate: L8 in
    tests/test_monitor_fingerprint_hygiene.py (RED pre-fix, live instrument).
    """
    try:
        with open(fn, encoding="utf-8", errors="ignore") as f:
            return (json.load(f).get("status") or "").upper()
    except Exception:
        pass
    # Fallback for non-JSON ticket files (e.g. *.md): the status line sits at
    # column 0 in every real queue markdown, so anchor to line start — a
    # nested mention inside prose/indented content is not ticket state.
    try:
        m = re.search(
            r'^"status"\s*:\s*"([^"]{0,40})',
            open(fn, encoding="utf-8", errors="ignore").read(),
            re.MULTILINE,
        )
        return m.group(1).upper() if m else ""
    except OSError:
        return ""


def main() -> int:
    now = time.time()
    head = _git("rev-parse", "HEAD").strip()
    status = _git("status", "--porcelain")

    dirty_all = [ln for ln in status.splitlines() if not ln.startswith("??")]
    paths_all = [ln[3:].strip() for ln in dirty_all]
    # Runtime churn is not builder activity: exclude from BOTH the dirty
    # count and the freshness computation (2026-09-19 stall-breaker fix).
    paths = [p for p in paths_all if not is_exempt(p)]

    # Worktree-blindness fix (2026-09-30, BK-41 incident): unlanded work in
    # linked worktrees (git worktree list) is pending builder work exactly
    # like mainline dirt. For each linked worktree: tracked-dirty files add
    # to the dirty count as wt:<branch>:<path>, and their newest mtime joins
    # the freshness pool so an ABANDONED dirty worktree still escalates the
    # stall tier. Untracked-only worktrees stay inert (artifact churn must
    # not wake the loop — same rule as mainline). Commits unmerged into
    # mainline also count, so a finished-but-unmerged branch keeps the
    # fingerprint hot until the merge lands.
    wt_notes = []
    _wt_pool = []  # per-worktree newest mtimes, merged into freshness below
    try:
        r = subprocess.run(
            ["git", "-C", REPO, "worktree", "list", "--porcelain"],
            capture_output=True, text=True, timeout=30,
        )
        wt_dirs = [
            ln[len("worktree "):].strip()
            for ln in r.stdout.splitlines()
            if ln.startswith("worktree ")
        ]
    except Exception:
        wt_dirs = []
    for wt in wt_dirs:
        if os.path.realpath(wt) == os.path.realpath(REPO):
            continue  # mainline already counted above
        try:
            ws = subprocess.run(
                ["git", "-C", wt, "status", "--porcelain"],
                capture_output=True, text=True, timeout=30,
            ).stdout
            wbranch = subprocess.run(
                ["git", "-C", wt, "rev-parse", "--abbrev-ref", "HEAD"],
                capture_output=True, text=True, timeout=30,
            ).stdout.strip()
            # Unmerged commit count vs mainline HEAD (worktrees that are
            # clean but ahead keep the loop hot for the merge step).
            # `git rev-list HEAD..wt` (mainline..worktree) — a worktree tip
            # that is an ANCESTOR of mainline (already merged) counts 0;
            # `wt..HEAD` (reversed) counts commits mainline has that the
            # worktree lacks, i.e. every merged worktree looks "ahead".
            # Landed-then-abandoned worktrees (bk19, bk24) must read 0.
            ahead = subprocess.run(
                ["git", "-C", REPO, "rev-list", "--count",
                 f"HEAD..{wbranch}"],
                capture_output=True, text=True, timeout=30,
            ).stdout.strip()
        except Exception:
            continue
        wdirty = [
            ln[3:].strip() for ln in ws.splitlines()
            if ln.strip() and not ln.startswith("??")
        ]
        wtag = os.path.basename(wt.rstrip("/")) or wbranch
        if wdirty:
            for p in wdirty:
                paths.append(f"wt:{wtag}:{p}")
            wt_notes.append(f"{wtag}:{len(wdirty)}d")
            try:
                abs_wt = [os.path.join(wt, p) for p in wdirty]
                rs = subprocess.run(
                    ["stat", "-c", "%Y", *abs_wt],
                    capture_output=True, text=True, timeout=30,
                )
                wt_mtimes = [int(x) for x in rs.stdout.split()]
                if wt_mtimes:
                    _wt_pool.append(max(wt_mtimes))
            except Exception:
                pass
        # Clean-but-AHEAD worktree: the builder committed and the merge is
        # the remaining step. Without this, a committed-in-worktree state is
        # invisible again (the exact post-commit shape of the 13:46 stall).
        nahead = int(ahead) if ahead.strip().isdigit() else 0
        if nahead:
            wt_notes.append(f"{wtag}:{nahead}a")
            if not wdirty:
                # Keep the fingerprint hot for the merge: derive freshness
                # from the tip commit time so an abandoned ahead-worktree
                # still escalates through the stall tiers.
                try:
                    wt_when = int(subprocess.run(
                        ["git", "-C", wt, "log", "-1", "--format=%ct"],
                        capture_output=True, text=True, timeout=30,
                    ).stdout.strip())
                    if wt_when > 0:
                        _wt_pool.append(wt_when)
                except Exception:
                    pass

    frozen = True
    if paths:
        # Stat ABSOLUTE paths: the scheduler may run this script from any CWD
        # (gateway process cwd != REPO), and bare relative paths from
        # `git status --porcelain` would all fail stat -> newest_mtime=0 ->
        # permanently FROZEN_STALLED -> hash never changes -> loop wedged
        # silent (2026-09-08 incident: 2h+ blind while tree was DIRTY_ACTIVE).
        abs_paths = [os.path.join(REPO, p) for p in paths_all]
        r = subprocess.run(
            ["stat", "-c", "%Y", *abs_paths], capture_output=True, text=True, timeout=30
        )
        mtimes = [int(x) for x in r.stdout.split()]
        # Worktree dirty mtimes joined _wt_pool above; merge so an active
        # worktree counts as fresh and an abandoned one escalates tiers.
        mtimes.extend(_wt_pool)
        # Blind spot #3 fix (2026-09-09): builder activity includes substantive
        # run reports. A run may diagnose/probe and write an honest handoff
        # without touching tracked files. Check newest report (>1KB) so
        # activity resets to the run's end, and doesn't get stuck on stale
        # tracked file mtime.
        report_dir = "/home/jericho/.hermes/cron/output/af3e62239ce2"
        if os.path.isdir(report_dir):
            reps = [
                os.path.join(report_dir, f)
                for f in os.listdir(report_dir)
                if f.endswith(".md") and os.path.getsize(os.path.join(report_dir, f)) > 1000
            ]
            if reps:
                mtimes.append(max(int(os.path.getmtime(f)) for f in reps))
        newest = max(mtimes) if mtimes else 0
        frozen = (now - newest) > STALL_SECS
    else:
        newest = 0

    # Repair queue: OPEN tickets only. Counting all *.json made `queue=N` a
    # permanent part of the fingerprint (300+ closed files never shrink), and
    # clock-derived output churned hourly on a clean tree — the exact
    # clock-state phantom-wake mechanism banned by RULING_monitor_age_cadence
    # (bdc084b): the fingerprint must carry REPO STATE (status transitions),
    # never CLOCK STATE (ages, timestamps).
    queue = []
    if os.path.isdir(QUEUE_DIR):
        # DATA artifacts (no status field by design) are not repair tickets:
        # floors.json is R0-calibration output (calibrate_floors.py), and a
        # status-less json can never satisfy the CLOSED-filter below, so it
        # counted as an open ticket forever -> phantom REPAIR_PENDING on a
        # clean tree (2026-09-21, cron af3e62239ce2). Gate: L5 in
        # tests/test_monitor_fingerprint_hygiene.py.
        # Queue-control files (QUEUE_STATE.json, CURRENT_TICKET.json) are also
        # not repair tickets.
        queue = sorted(
            f for f in os.listdir(QUEUE_DIR)
            if f.endswith(".json")
            and not f.startswith("commit_msg_")
            and not f.startswith("append_")
            and f not in ("QUEUE_STATE.json", "CURRENT_TICKET.json")
            and _ticket_status(os.path.join(QUEUE_DIR, f)) != ""
            and not any(w in _ticket_status(os.path.join(QUEUE_DIR, f)) for w in ("CLOSED", "DONE", "STOPPED", "RESOLVED", "LANDED"))
        )
        # Structured queue defects (resilience PR-1):
        qs_path = os.path.join(QUEUE_DIR, "QUEUE_STATE.json")
        if os.path.exists(qs_path):
            try:
                with open(qs_path, encoding="utf-8") as f:
                    qs_data = json.load(f)
                for d in qs_data.get("defects", []):
                    st = d.get("status", "").upper()
                    if st and not any(w in st for w in ("CLOSED", "DONE", "STOPPED", "RESOLVED", "LANDED")):
                        queue.append(d.get("id", "DEFECT"))
            except Exception:
                pass

    # Escalating stall tier: 1 at 30m frozen, 2 at 60m, ... changes the
    # fingerprint every STALL_SECS while the stall persists.
    stall_tier = 0
    supply_note = "ok"
    if paths and frozen:
        stall_tier = int((now - newest) // STALL_SECS)
        state = f"FROZEN_STALLED_T{min(stall_tier, MAX_TIER)}"
    elif paths:
        state = "DIRTY_ACTIVE"
    else:
        stall_tier = 0
        state = "CLEAN"

    # Level-trigger for unclaimed pinned work: a clean tree with an open
    # done-with-defect (⚠️) roadmap item is NOT "nothing to do" — it's a
    # pending claim the edge-triggered hash cannot see. Keep the fingerprint
    # hot (item hash in output) until the ⚠️ is resolved, so the agent wakes.
    # SCOPE FIX 2026-09-12 (HEAD 3e2bd8e): only TABLE ROWS count. Prose lines
    # in the roadmap routinely *mention* the marker ("there is no open
    # ⏳/⚠️/DRAFT row", sweep footers), so a whole-file grep phantom-wakes the
    # loop. A row already carrying a "✅ done" closure is closed history.
    _roadmap = _git("show", f"HEAD:{ROADMAP}")
    # 2026-09-19 redirect: the builder loop's primary target is now the
    # GPU CPU emulator roadmap (GPU_CPU_EMULATOR_ROADMAP.md, PS-headers
    # not table rows). Its open phases feed the supply signal so a fully
    # done PS series reads as STARVED, not CLEAN-rest; the self-hosting
    # roadmap keeps feeding DEFECT_OPEN (⚠️ rows) as before.
    _ps_roadmap = _git("show", "HEAD:GPU_CPU_EMULATOR_ROADMAP.md")
    # Section-scan: a ### PS header is OPEN unless its section (to the
    # next ###/---) carries a done-closure. The done line sits BELOW the
    # header, so a header-line-only check would misclassify PS005.
    _ps_lines = _ps_roadmap.splitlines()
    _ps_open = []
    for _i, _ln in enumerate(_ps_lines):
        if not _ln.startswith("### PS"):
            continue
        _j = _i + 1
        while _j < len(_ps_lines) and not _ps_lines[_j].startswith("### ") and _ps_lines[_j].strip() != "---":
            _j += 1
        if not _DONE_RE.search("\n".join(_ps_lines[_i:_j])):
            _ps_open.append(_ln.strip()[:120])
    _defect = [
        ln.strip()[:120]
        for ln in _roadmap.splitlines()
        if ln.lstrip().startswith("|") and "⚠️" in ln and not _DONE_RE.search(ln)
    ]
    if not paths and _defect:
        state = "DEFECT_OPEN"

    # Level-trigger for OPEN repair tickets on a clean tree (2026-09-09 fix):
    # a committed RED gate + open .json ticket leaves the tree CLEAN and the
    # queue count stable, so the fingerprint froze and the loop slept 4h
    # instead of implementing the ticket (GH-20 spec-finalize incident). An
    # open ticket is pending work: include its count in the fingerprint so it
    # stays hot until the ticket is resolved/retired.
    if queue and not paths:
        state = "REPAIR_PENDING"

    # Level-trigger for supply exhaustion (2026-09-19): a clean tree with a
    # fully-done roadmap and no tickets is not "rest" — for a supply-driven
    # loop it is STARVATION. Surface the top backlog row as the promotion
    # candidate (stable id => stable bytes => single wake, then heat only
    # while the roadmap stays empty). The builder prompt's PHASE-1 backlog
    # promotion policy does the rest. No clock state in the output (bdc084b).
    if state == "CLEAN" and not queue and not _defect and not _ps_open:
        if not open_roadmap_rows(_roadmap):
            _backlog = _git("show", f"HEAD:{BACKLOG}")
            top = top_backlog_row(_backlog)
            if top:
                state = "SUPPLY_STARVED"
                supply_note = top
        # Structured queue (resilience PR-1): read QUEUE_STATE.json for canonical supply
        claimed_item = None
        qs_path = os.path.join(QUEUE_DIR, "QUEUE_STATE.json")
        if os.path.exists(qs_path):
            try:
                with open(qs_path, encoding="utf-8") as f:
                    qs_data = json.load(f)
                queue_items = qs_data.get("queue", [])
                landed_or_resolved = {
                    it["id"] for it in queue_items
                    if it.get("status", "").lower() in ("landed", "done", "closed", "resolved")
                }
                for d in qs_data.get("defects", []):
                    if d.get("status", "").lower() in ("resolved", "closed", "done", "landed"):
                        landed_or_resolved.add(d.get("id"))
                candidates = []
                for it in queue_items:
                    if it.get("status", "").lower() == "queued":
                        blocks_on = it.get("blocks_on", [])
                        if all(b in landed_or_resolved for b in blocks_on):
                            candidates.append(it)
                if candidates:
                    candidates.sort(key=lambda x: x.get("claim_order", 9999))
                    claimed_item = candidates[0]
            except Exception:
                pass

        if claimed_item:
            cid = claimed_item.get("id", "")
            title = claimed_item.get("title", "")
            c_desc = f"{cid}: {title}" if title else cid
            state = "CLAIM_PENDING"
            supply_note = f"claim: {c_desc[:48]}".rstrip()
        else:
            # 2026-09-24 split-brain fix: ledger fallback
            # 2026-09-28 phantom fix (CURRENT_TICKET.json
            # REPAIR_stale_NEXT_line_triggers_claim_pending): the scan below
            # regex-matched the FIRST '^NEXT:' ANYWHERE in the ledger — a
            # stale 2026-09-25 NEXT (ledger :3913) kept driving CLAIM_PENDING
            # on a queue-empty tree long after its round-9+ items were all
            # landed. NEXT lines are per-entry state: anchor the scan to the
            # MOST RECENT entry (the first '### ' block), not the first match
            # in the whole file. Cross-check stays textual (the structured
            # QUEUE_STATE.json above is already authoritative when present);
            # the 'queue empty' exclusion is retained.
            _ledger = _git("show", "HEAD:.builder_queue/PRODUCT_LANE_STATE.md")
            _next_end = _ledger.find("### ", 5)
            _scope = _ledger if _next_end < 0 else _ledger[:_next_end]
            _m = re.search(r"^NEXT: \*\*(.+?)\*\*", _scope, re.S | re.M)
            if _m and not re.search(r"queue empty", _m.group(1), re.I):
                _first = " ".join(_m.group(1).split())
                state = "CLAIM_PENDING"
                # Byte-stability (2026-09-24 stall #2): the cron harness strips
                # trailing whitespace from monitor output before hashing, so a
                # supply_note whose [:48] cut leaves a trailing space hashes
                # IDENTICAL to the stripped previous output forever — the
                # fingerprint froze and the agent never re-fired (verified:
                # stored snapshot '...seat lane' vs live '...seat lane \\n').
                # rstrip() the note AND the whole line so output is
                # strip-invariant: hash(live) == hash(stored) iff text equal.
                supply_note = f"claim: {_first[:48]}".rstrip()
    elif state == "CLEAN" and not queue and not _defect and _ps_open:
        # PS phases remain: level-trigger the next open phase id into the
        # fingerprint so the redirected loop stays hot while work remains.
        state = "PS_OPEN"
        supply_note = _ps_open[0][:40]

    wt_field = f" wt={','.join(wt_notes)}" if wt_notes else ""
    print(
        f"head={head} tracked_dirty={len(paths)} "
        f"state={state} stall_tier={stall_tier} queue={len(queue)} supply={supply_note}"
        f"{wt_field}".rstrip()
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
