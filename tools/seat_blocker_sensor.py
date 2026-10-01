#!/usr/bin/env python3
"""seat_blocker_sensor.py — deterministic sensor: does the SEAT owe the builder a decision?

Hermes hashes this output as EXACT BYTES to decide whether to wake the agent, so the output must
be STABLE across runs when nothing meaningful changed. Deliberately excluded: timestamps, ages,
durations, absolute paths, and the worktree's dirty-file list (the lane rewrites output/*.txt
constantly — listing those would wake the agent on nearly every tick and defeat suppression).

Reports only three things:
  1. UNANSWERED seat asks — REPAIR_PENDING_*.md tickets whose basename is mentioned by no RULING_*.md
  2. SUPPLY — roadmap rows whose status field is still open/queued
  3. REGRESSIONS — files that were PASS in the locked baseline and are FAIL/TIMEOUT in the newest sink
"""
import json
import os
import re
import sys

REPO = os.environ.get("GLYPH_REPO", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
QUEUE = os.path.join(REPO, ".builder_queue")
ROADMAP = os.path.join(REPO, "systems", "GLYPH_SELF_HOSTING_ROADMAP.md")
OUTPUT = os.path.join(REPO, "output")
BASELINE = os.path.join(REPO, "systems", "SUITE_BASELINE_2026-09-13.txt")

OPEN_WORDS = ("OPEN", "queued", "⏳", "BLOCKED", "RULING-PENDING")
DONE_WORDS = ("✅", "🔬", "closed", "DONE")


def _files(path, prefix="", suffix=""):
    if not os.path.isdir(path):
        return []
    return sorted(f for f in os.listdir(path) if f.startswith(prefix) and f.endswith(suffix))


def _ruling_text():
    return "\n".join(
        open(os.path.join(QUEUE, f), errors="ignore").read() for f in _files(QUEUE, "RULING_", ".md")
    )


def seat_asks():
    """Tickets that ask for a seat decision and are not yet answered by any RULING file."""
    ruled = _ruling_text()
    asks = []
    for name in _files(QUEUE, "REPAIR_PENDING_", ".md"):
        if name in ruled:
            continue
        body = open(os.path.join(QUEUE, name), errors="ignore").read()
        seat = re.search(r"Seat:?\*{0,2}\s*([^\n·|]+)", body)
        blocked = "BLOCKED-ON-DESIGN" in body
        who = (seat.group(1).lower() if seat else "")
        # Only the seat's own asks wake the seat: ignore tickets parked on the builder/lane.
        if not blocked and not any(w in who for w in ("jericho", "orchestrator", "seat", "lane")):
            continue
        if not (seat or blocked):
            continue
        asks.append("%s seat=%s blocked=%s" % (name[len("REPAIR_PENDING_"):-3],
                                               seat.group(1).strip()[:40] if seat else "-", blocked))
    return asks


def supply():
    """Rows in the roadmap whose status field says they are still open."""
    if not os.path.exists(ROADMAP):
        return ["supply: NO ROADMAP"]
    ids = []
    for line in open(ROADMAP, errors="ignore"):
        if not line.startswith("| "):
            continue
        cols = [c.strip() for c in line.split("|") if c.strip()]
        if len(cols) < 3:
            continue
        rid, status = cols[0], cols[-1]
        if not re.match(r"^[A-Z][A-Z0-9-]+$", rid) or rid in ("ID", "Row"):
            continue
        if any(w in status for w in DONE_WORDS):
            continue
        if any(w in status for w in OPEN_WORDS):
            ids.append(rid)
    return ["supply: OPEN=%d %s" % (len(ids), ",".join(sorted(set(ids))) or "(none)")]


def _verdicts(text):
    ansi = re.compile(r"\x1b\[[0-9;]*m")
    got = {}
    if text.lstrip().startswith("{"):
        for line in text.splitlines():
            try:
                rec = json.loads(line.strip())
            except Exception:
                continue
            if rec.get("path") and rec.get("verdict"):
                got[os.path.basename(rec["path"])] = rec["verdict"]
        return got
    for line in ansi.sub("", text).splitlines():
        m = re.search(r"\[(PASS|FAIL|TIMEOUT)\s*\]\s*(\S+)", line)
        if m:
            got[os.path.basename(m.group(2))] = m.group(1)
    return got


def regressions():
    if not os.path.exists(BASELINE):
        return ["regressions: NO BASELINE"]
    base = _verdicts(open(BASELINE, errors="ignore").read())
    sinks = _files(OUTPUT, suffix="_SINK.jsonl")
    if not sinks:
        return ["regressions: NO SINK"]
    newest = max(sinks, key=lambda f: os.path.getmtime(os.path.join(OUTPUT, f)))
    cur = _verdicts(open(os.path.join(OUTPUT, newest), errors="ignore").read())
    bad = sorted("REGRESSION %s %s->%s" % (f, base.get(f, "NEW"), v)
                 for f, v in cur.items() if v in ("FAIL", "TIMEOUT") and base.get(f, "PASS") == "PASS")
    return bad or ["regressions: none (baseline PASS set intact)"]


def prose_asks():
    """Decision-phrased briefs the ask-scanner cannot see.

    Gap this closes (2026-09-14): DEFECT-22's close sat in prose as "Jericho's call" with no
    REPAIR_PENDING ticket, so the sensor that exists to surface seat obligations could not see it.
    Phrases chosen by measured precision: "RULING-PENDING" (3 files), "needs a ruling" (3),
    "seat decision" (1) are precise; generic ones were rejected ("'s call" hits 20 files including
    ledger scripts - noise).
    """
    ruled = "\n".join(open(os.path.join(QUEUE, f), errors="ignore").read()
                      for f in _files(QUEUE, suffix=".md") if f.startswith("RULING_"))
    out = []
    for f in sorted(os.listdir(QUEUE)) if os.path.isdir(QUEUE) else []:
        if f.startswith("RULING_") or f.startswith("commit_msg_") or f.startswith("append_"):
            continue
        p = os.path.join(QUEUE, f)
        if f in ruled or p in ruled:
            continue
        try:
            body = open(p, errors="ignore").read()
        except (IOError, OSError):
            continue
        for ph in ("RULING-PENDING", "needs a ruling", "seat decision"):
            if ph in body:
                out.append("prose_ask: %s (%s)" % (f, ph))
                break
    return out or ["prose_asks: none"]


def main():
    lines = ["SEAT-BLOCKER SENSOR"]
    asks = seat_asks()
    lines.append("seat_asks: %d" % len(asks))
    lines += ["  " + a for a in asks]
    # Starvation visibility (2026-09-19): seat+lane need to SEE that the supply
    # pipeline is dry even when nothing is actionable. Counts are stable bytes,
    # not clock state: they change only when the roadmap/backlog actually do.
    import subprocess as _sp
    def _show(rel):
        return _sp.run(["git", "-C", REPO, "show", "HEAD:" + rel],
                       capture_output=True, text=True).stdout
    sup_all = supply()
    open_ids = 0
    for l in sup_all:
        m = re.match(r"supply: OPEN=(\d+)", l)
        if m:
            open_ids = int(m.group(1))
    bk = 0
    for line in _show("systems/GLYPH_BACKLOG.md").splitlines():
        if line.lstrip().startswith("|") and line.split("|")[1].strip().startswith("BK-"):
            bk += 1
    lines.append("supply_pipeline: roadmap_open=%d backlog_rows=%d%s"
                 % (open_ids, bk, " STARVED" if (open_ids == 0 and bk > 0) else ""))
    # Digest-safety: only the EXHAUSTED edge is seat-relevant. The open-row LIST changes every few
    # minutes as the lane closes rows, which made the digest churn and woke the agent on every tick
    # (measured ...: 3 fires / 1.0M tokens in 30 min for what were all non-decisions).
    # Counts are not seat decisions; the LANE must never wake the seat just for making progress.
    sup = [l for l in supply() if l.startswith("supply: EXHAUSTED") or l == "supply: NO ROADMAP"]
    lines += (sup or ["supply: ok"]) + regressions() + prose_asks()
    print("\n".join(lines))


if __name__ == "__main__":
    sys.exit(main())
