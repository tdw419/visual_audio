#!/usr/bin/env python3
"""glyph_builder_ladder.py — BK-255 / FACT-3 halt-escalation LADDER (auditor side).

Ruling: .builder_queue/RULING_factory_trust_infra_supply.md (FACT-3).
Design: .builder_queue/DESIGN_factory_fact3_halt_escalation.md (§Action ladder,
§Gate spec line "Ladder wiring ... separate step with its own RED-first test on
the watchdog, only after the collector gate is green" — collector landed
398b019b, tests/test_bk255_halt_escalation.py 9/9 GREEN).

This module is the AUDITOR-side consumer of tools.geos_system1.rolling_halt_signal.
Per the design doc and the AGENTS.md second-checker amendment, the signal is
compute-and-report only; ONLY this ladder (wired into the auditor cron
9022a527b259's watchdog run via tools/glyph_builder_watchdog.py step 8) ACTS on
it. The builder never self-halts and never self-unhalts.

Action ladder (design doc, verbatim mapping):
  leg 1  fire + not yet armed   -> append a kind=="halt_escalation" row to
       decision_log.jsonl AND write
       .builder_queue/TICKET_ESCALATION_audit_halt_<UTCdate>.md naming the
       rebuked advisories + measured window. NOTHING is paused.
  leg 2  fire + already armed AND the prior escalation ticket is >24h old
       (unacknowledged)         -> pause the builder cron af3e62239ce2 via the
       Hermes cron API (pause_job). Restore is Jericho-only per
       .builder_queue/RESUME_BUILDER_RUNBOOK.md.
  leg 3  no fire                -> no-op (returns reason).

ARM STATE: append-only in the decision log itself — the most recent
kind=="halt_escalation" row IS the armed flag (design §Action ladder leg 4:
"the armed flag lives in the decision_log ... append-only and auditable").
Acknowledgment is a Jericho commit touching the escalation ticket; the ladder
detects it by mtime of the ticket file being NEWER than the armed row's
timestamp (a commit checks out / rewrites the file, bumping mtime; no log
forking, no state file). Reset also accepts the ticket file being deleted
(resolved-and-removed by convention).

NO PAUSE EVER HAPPENS while the signal does not fire. The pause path requires
ALL of: signal.fire True AND an armed row exists AND that row is >window old
AND the ticket was not touched since. Every input is measured, receipted, and
fail-safe: ANY exception in the fire path degrades to a no-op with the error
string in the returned actions list.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO_ROOT = Path("/home/jericho/projects/zion/projects/visual_audio")
QUEUE_DIR = REPO_ROOT / ".builder_queue"
DEFAULT_LOG_PATH = QUEUE_DIR / "decision_log.jsonl"
BUILDER_CRON_ID = "af3e62239ce2"

# BK-255 PROPOSED defaults (PENDING-JERICHO sign-off) — same values as
# tools/geos_system1.py HALT_* constants; kept local so the watchdog never
# imports the screener module just for constants (import isolation between
# auditor arm and screener arm).
LADDER_WINDOW_HOURS = 24
LADDER_MIN_ADJUDICATED = 3
LADDER_MIN_REBUKE_RATE = 2.0 / 3.0


def _last_escalation_row(log_path: Path) -> Optional[Dict[str, Any]]:
    """Most recent kind=='halt_escalation' row, or None. Append-only read:
    never raises on malformed rows; skips them."""
    try:
        with open(log_path, "r", encoding="utf-8") as f:
            last: Optional[Dict[str, Any]] = None
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(row, dict) and row.get("kind") == "halt_escalation":
                    last = row
    except OSError:
        return None
    return last


def _ticket_path_for(armed_row: Dict[str, Any], log_path: Path) -> Path:
    """The escalation ticket named by the armed row (fallback: today's name in
    the log's queue dir — fixture isolation, never the module global)."""
    name = armed_row.get("ticket")
    if name:
        return log_path.parent / str(name)
    date = armed_row.get("timestamp", "")[:10] or datetime.now(timezone.utc).date().isoformat()
    return log_path.parent / f"TICKET_ESCALATION_audit_halt_{date}.md"


def _ticket_acknowledged(armed_row: Dict[str, Any], ticket: Path, now: datetime) -> bool:
    """Jericho acknowledgment = a commit touching the escalation ticket after
    the armed row was written (mtime bump) or the ticket removed."""
    if not ticket.exists():
        return True
    try:
        mtime = datetime.fromtimestamp(ticket.stat().st_mtime, tz=timezone.utc)
    except OSError:
        return True
    ts = armed_row.get("timestamp")
    if not ts:
        return False
    try:
        armed_at = datetime.fromisoformat(ts)
    except ValueError:
        return False
    if armed_at.tzinfo is None:
        armed_at = armed_at.replace(tzinfo=timezone.utc)
    return mtime > armed_at


def run_halt_ladder(
    log_path: Path = DEFAULT_LOG_PATH,
    window_hours: int = LADDER_WINDOW_HOURS,
    min_adjudicated: int = LADDER_MIN_ADJUDICATED,
    min_rebuke_rate: float = LADDER_MIN_REBUKE_RATE,
    now: Optional[datetime] = None,
    allow_pause: bool = True,
    signal_fn=None,
    pause_fn=None,
    armed_row: Optional[Dict[str, Any]] = None,
    stdout=None,
) -> List[str]:
    """One auditor-tick pass of the BK-255 action ladder.

    ``armed_row`` overrides the log scan (tests inject fixtures; the default
    None means "read the last halt_escalation row from log_path").

    Returns a list of human-readable action lines (empty = silent tick).
    This function is the ONLY caller of pause_fn in the codebase; tests inject
    a recorder so the real cron pause is never fired from a test process.
    """
    actions: List[str] = []
    out = stdout if stdout is not None else sys.stdout
    now = now or datetime.now(timezone.utc)

    # Signal: reuse the collector, never fork the arithmetic. The collector
    # itself degrades to fire=False on unreadable logs.
    if signal_fn is None:
        # Local (watchdog-side) import — keeps the auditor arm decoupled from
        # the screener module at import time; the function is pure.
        repo_str = str(REPO_ROOT)
        if repo_str not in sys.path:
            sys.path.insert(0, repo_str)
        from tools.geos_system1 import rolling_halt_signal as signal_fn  # noqa: E731
    signal = signal_fn(
        log_path=log_path,
        window_hours=window_hours,
        min_adjudicated=min_adjudicated,
        min_rebuke_rate=min_rebuke_rate,
        now=now,
    )

    armed = armed_row if armed_row is not None else _last_escalation_row(log_path)

    if not signal.get("fire"):
        if armed is not None:
            ticket = _ticket_path_for(armed, log_path)
            if _ticket_acknowledged(armed, ticket, now):
                actions.append(
                    f"[halt-ladder] no fire; prior escalation ({armed.get('timestamp', '?')}) "
                    f"acknowledged (ticket touched/removed after arming) — no action"
                )
            else:
                actions.append(
                    f"[halt-ladder] no fire; armed escalation standing since "
                    f"{armed.get('timestamp', '?')} (unacknowledged, within window) — monitoring"
                )
        return actions

    # ---- fire ----
    if armed is None:
        # Ladder leg 1: first fire -> ticket + decision_log row. NOTHING paused.
        # Ticket lands in the LOG's queue dir (fixture isolation — a fixture
        # log must never write into the live queue; same defect class the
        # collector gate caught at tick-140).
        queue_dir = log_path.parent
        ticket = queue_dir / f"TICKET_ESCALATION_audit_halt_{now.date().isoformat()}.md"
        rebuked_names = signal.get("reason", "")
        ticket_body = (
            f"# TICKET: AUDIT HALT-ESCALATION (BK-255 / FACT-3) — {now.isoformat()}\n\n"
            f"Signal FIRED under the PROPOSED defaults (PENDING-JERICHO):\n"
            f"window={window_hours}h, min_adjudicated={min_adjudicated}, "
            f"min_rebuke_rate={min_rebuke_rate:.3f}\n\n"
            f"Measured: {rebuked_names}\n\n"
            f"This ticket is the leg-1 NOTIFICATION. NOTHING is paused on first fire.\n"
            f"If the signal fires again >{window_hours}h after this arming row without "
            f"this file being touched by a Jericho commit, the auditor cron "
            f"(9022a527b259) pauses builder cron {BUILDER_CRON_ID} per the design doc.\n"
            f"Restore is Jericho-only: .builder_queue/RESUME_BUILDER_RUNBOOK.md\n"
        )
        try:
            ticket.write_text(ticket_body, encoding="utf-8")
            actions.append(f"[halt-ladder] LEG 1: escalation ticket written: {ticket.name}")
        except OSError as e:
            actions.append(f"[halt-ladder] LEG 1 ticket WRITE FAILED (fail-safe, no pause): {e}")
            return actions
        row = {
            "kind": "halt_escalation",
            "timestamp": now.isoformat(),
            "window_hours": window_hours,
            "distinct_adjudicated": signal.get("distinct_adjudicated"),
            "rebuked": signal.get("rebuked"),
            "confirmed": signal.get("confirmed"),
            "fire_reason": signal.get("reason"),
            "ticket": ticket.name,
            "action": "notified",
            "emitter": "auditor-ladder",
        }
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(row) + "\n")
            actions.append("[halt-ladder] LEG 1: halt_escalation row appended to decision_log (arm state)")
        except OSError as e:
            actions.append(f"[halt-ladder] LEG 1 decision_log append FAILED: {e}")
        return actions

    # fire + already armed: leg 2 requires the prior arming to be >window old
    # AND unacknowledged.
    ticket = _ticket_path_for(armed, log_path)
    if _ticket_acknowledged(armed, ticket, now):
        # Acknowledged: re-arm fresh (a new fire after acknowledgment is a NEW
        # leg-1 event). armed_row=None hides the stale armed row from the
        # recursive call so it takes the leg-1 path.
        actions.append(
            "[halt-ladder] fire; prior escalation acknowledged — re-arming (leg 1)"
        )
        sub = run_halt_ladder(
            log_path=log_path,
            window_hours=window_hours,
            min_adjudicated=min_adjudicated,
            min_rebuke_rate=min_rebuke_rate,
            now=now,
            allow_pause=allow_pause,
            signal_fn=signal_fn,
            pause_fn=pause_fn,
            armed_row=None,
            stdout=out,
        )
        return actions + sub

    ts = armed.get("timestamp", "")
    try:
        armed_at = datetime.fromisoformat(ts)
        if armed_at.tzinfo is None:
            armed_at = armed_at.replace(tzinfo=timezone.utc)
    except ValueError:
        armed_at = None
    if armed_at is None:
        actions.append(
            f"[halt-ladder] fire; armed row has unparseable timestamp {ts!r} — "
            f"fail-safe NO PAUSE (auditable defect in log)"
        )
        return actions
    age_hours = (now - armed_at).total_seconds() / 3600.0
    if age_hours <= window_hours:
        actions.append(
            f"[halt-ladder] fire; escalation armed {age_hours:.1f}h ago "
            f"(<= {window_hours}h) — first-day rule holds, NOTHING paused"
        )
        return actions

    # Ladder leg 2: sustained, unacknowledged fire -> pause the builder cron.
    if not allow_pause:
        actions.append("[halt-ladder] LEG 2 condition met but allow_pause=False (dry-run) — no cron touched")
        return actions
    if pause_fn is None:
        try:
            hermes_agent = Path("/home/jericho/.hermes/hermes-agent")
            if str(hermes_agent) not in sys.path:
                sys.path.insert(0, str(hermes_agent))
            from cron.jobs import pause_job as pause_fn  # type: ignore
        except Exception as e:
            actions.append(f"[halt-ladder] LEG 2 pause IMPORT failed (fail-safe no pause): {e}")
            return actions
    try:
        reason = (
            f"BK-255 halt-escalation: signal fired {age_hours:.1f}h after arming "
            f"({armed.get('ticket', '?')}); unacknowledged; design doc leg 2"
        )
        result = pause_fn(BUILDER_CRON_ID, reason=reason)
        if result:
            actions.append(
                f"[halt-ladder] LEG 2: builder cron {BUILDER_CRON_ID} PAUSED "
                f"(armed {age_hours:.1f}h, unacknowledged). Jericho-only restore per "
                f"RESUME_BUILDER_RUNBOOK.md"
            )
            row = {
                "kind": "halt_escalation",
                "timestamp": now.isoformat(),
                "action": "paused_builder",
                "ticket": armed.get("ticket"),
                "fire_reason": signal.get("reason"),
                "emitter": "auditor-ladder",
            }
            try:
                with open(log_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(row) + "\n")
            except OSError as e:
                actions.append(f"[halt-ladder] LEG 2 log append failed: {e}")
        else:
            actions.append("[halt-ladder] LEG 2 pause call returned falsy — verify cron state manually")
    except Exception as e:
        actions.append(f"[halt-ladder] LEG 2 pause FAILED (fail-safe, no state change): {e}")
    return actions
