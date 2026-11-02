#!/usr/bin/env python3
"""FACT-2 screener-freshness audit (RULING_factory_trust_infra_supply.md).

Question: does the System-1 watchdog (cron 9022a527b259, every 2m, reported
status=ok) actually WRITE dated outputs, or does it report ok without writing
(ok-without-write — Evidence-#4 silent-drift class)?

Enumerated output paths (from tools/glyph_builder_watchdog.py +
tools/geos_system1.py):
  1. .builder_queue/decision_log.jsonl   — screening decisions (:450-451)
  2. .builder_queue/RULING_SYSTEM1_ADVISORY_*.md — advisory rulings (:506,:544)
  3. build_map.png / build_map_data.json — spatial build map (watchdog step 7)
  4. .builder_queue/QUEUE_STATE.json     — supply replenish (step 4, tree-clean-gated)

Method: cron fire times come from the dated output files the scheduler writes
(~/.hermes/cron/output/<job>/). Output freshness = mtimes of the artifacts vs
the last fire in the observed window. Zero decision_log entries in a window is
LEGITIMATE when no unlogged receipts existed; the load-bearing freshness probe
is the build_map (rendered by the SAME main() call as the screener every tick)
tracking the last fire, plus per-receipt screening latency.

Verdict: FRESH or DRIFT; exit 0 = FRESH, exit 1 = DRIFT. RED-first is
demonstrated by --self-test, which fabricates a stale watchdog state and
proves the tool goes DRIFT (exit 1) on it before trusting a live FRESH.

Usage:
  python3 tools/audit_screener_freshness.py               # live, trailing 1h
  python3 tools/audit_screener_freshness.py --hours 2     # wider window
  python3 tools/audit_screener_freshness.py --self-test   # prove it can fail
"""
import argparse
import json
import shutil
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

CRON_JOB_ID = "9022a527b259"
CRON_OUT_ROOT = Path("/home/jericho/.hermes/cron/output")
DEFAULT_MAP_MAX_LAG_S = 180  # one scheduled tick + slack


def parse_fire_name(name: str):
    """'2026-10-07_18-44-12' -> aware datetime, else None."""
    try:
        return datetime.strptime(name, "%Y-%m-%d_%H-%M-%S").astimezone()
    except ValueError:
        return None


def audit(repo: Path, cron_out: Path, window_start: datetime, window_end: datetime,
          map_max_lag_s: int = DEFAULT_MAP_MAX_LAG_S):
    """Measure one window. Returns (verdict, details_dict). Pure read-only."""
    fires = []
    for f in sorted(cron_out.glob("*.md")):
        t = parse_fire_name(f.stem)
        if t and window_start <= t < window_end:
            fires.append((t, f))
    fires.sort()

    log = repo / ".builder_queue" / "decision_log.jsonl"
    scan_in_window = []
    if log.exists():
        for line in log.read_text(errors="ignore").splitlines():
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                d = json.loads(line)
            except Exception:
                continue
            ts = d.get("timestamp")
            if not ts or d.get("emitter") != "scan":
                continue
            try:
                dt = datetime.fromisoformat(ts)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                dt = dt.astimezone()
            except Exception:
                continue
            if window_start <= dt < window_end:
                scan_in_window.append((dt, d.get("ticket_id"), d.get("decision")))

    qdir = repo / ".builder_queue"
    advisories = []
    for p in qdir.glob("RULING_SYSTEM1_ADVISORY_*.md"):
        t = datetime.fromtimestamp(p.stat().st_mtime).astimezone()
        if window_start <= t < window_end:
            advisories.append((t, p.name))

    bmp = repo / "build_map.png"
    map_verdict = "NO_MAP"
    map_lag = None
    if bmp.exists() and fires:
        bmt = datetime.fromtimestamp(bmp.stat().st_mtime).astimezone()
        last_fire = max(t for t, _ in fires)
        map_lag = (bmt - last_fire).total_seconds()
        map_verdict = "FRESH" if 0 <= map_lag <= map_max_lag_s else "DRIFT"

    verdict = "FRESH" if (fires and map_verdict == "FRESH") else "DRIFT"
    details = {
        "window": (window_start.isoformat(), window_end.isoformat()),
        "fires": len(fires),
        "first_fire": fires[0][0].isoformat() if fires else None,
        "last_fire": fires[-1][0].isoformat() if fires else None,
        "decision_log_scan_entries": len(scan_in_window),
        "scan_entries": [(t.isoformat(), tid, dec) for t, tid, dec in scan_in_window],
        "advisory_rulings_written": len(advisories),
        "advisories": [n for _, n in advisories],
        "build_map_verdict": map_verdict,
        "build_map_lag_vs_last_fire_s": map_lag,
        "verdict": verdict,
    }
    return verdict, details


def print_report(d: dict):
    print(f"window: {d['window'][0]} .. {d['window'][1]}")
    print(f"cron fires in window: {d['fires']}  (first {d['first_fire']}, last {d['last_fire']})")
    print(f"decision_log scan entries in window: {d['decision_log_scan_entries']}"
          f"  (0 is legitimate when no unlogged receipts existed)")
    for t, tid, dec in d["scan_entries"]:
        print(f"  {t}  {tid}  {dec}")
    print(f"advisory rulings written in window: {d['advisory_rulings_written']}")
    for n in d["advisories"]:
        print(f"  {n}")
    print(f"build_map vs last fire: {d['build_map_verdict']} "
          f"(lag {d['build_map_lag_vs_last_fire_s']}s, allowed 0..{DEFAULT_MAP_MAX_LAG_S}s)")
    print(f"VERDICT: {d['verdict']}")


def self_test():
    """RED leg: fabricate a stale watchdog and prove the tool goes DRIFT (exit 1)."""
    tmp = Path(tempfile.mkdtemp(prefix="fact2_selftest_"))
    try:
        repo = tmp / "repo"
        qdir = repo / ".builder_queue"
        qdir.mkdir(parents=True)
        cron_out = tmp / "cronout"
        cron_out.mkdir()

        now = datetime.now().astimezone()
        # 5 recent fires, but NO artifacts written at/after them:
        for i in range(5):
            t = now - timedelta(minutes=2 * (i + 1))
            (cron_out / (t.strftime("%Y-%m-%d_%H-%M-%S") + ".md")).write_text(
                "# ok-silent tick (fabricated)\n")
        # stale map: last touched 3h ago
        old = now - timedelta(hours=3)
        import os
        os.utime(repo / ".." / ".." / "." if False else (repo), None)  # no-op guard
        bmp = repo / "build_map.png"
        bmp.write_bytes(b"\x89PNG fake")
        os.utime(bmp, (old.timestamp(), old.timestamp()))

        ws, we = now - timedelta(hours=1), now + timedelta(minutes=1)
        verdict, _ = audit(repo, cron_out, ws, we)
        if verdict != "DRIFT":
            print(f"SELF-TEST RED FAILED: fabricated stale state produced verdict "
                  f"{verdict} (expected DRIFT) — the tool cannot fail, it is decoration.")
            return 2
        print("SELF-TEST RED PASS: fabricated stale watchdog -> DRIFT (tool can fail).")

        # GREEN control: same fires, fresh map -> FRESH
        import os as _os
        _os.utime(bmp, None)
        verdict2, _ = audit(repo, cron_out, ws, we)
        if verdict2 != "FRESH":
            print(f"SELF-TEST CONTROL FAILED: fresh map produced {verdict2} (expected FRESH).")
            return 2
        print("SELF-TEST CONTROL PASS: fresh map -> FRESH.")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", type=Path,
                    default=Path("/home/jericho/projects/zion/projects/visual_audio"))
    ap.add_argument("--hours", type=float, default=1.0,
                    help="trailing window size in hours (default 1)")
    ap.add_argument("--self-test", action="store_true",
                    help="prove the tool can go DRIFT before trusting a live FRESH")
    args = ap.parse_args()

    if args.self_test:
        sys.exit(self_test())

    now = datetime.now().astimezone()
    ws, we = now - timedelta(hours=args.hours), now + timedelta(minutes=1)
    verdict, details = audit(args.repo, CRON_OUT_ROOT / CRON_JOB_ID, ws, we)
    print_report(details)
    sys.exit(0 if verdict == "FRESH" else 1)


if __name__ == "__main__":
    main()
