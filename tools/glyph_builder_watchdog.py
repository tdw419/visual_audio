#!/usr/bin/env python3
"""glyph_builder_watchdog.py — Autonomous assistance & watchdog for Glyph OS builder.

Capabilities:
1. Disk Space Watchdog:
   - Tracks free space on /home.
   - Detects landed item worktrees (e.g. item28-rootinit, item29-containment once landed).
   - Safely prunes landed worktrees with `git worktree remove --force` to prevent disk crises.
   - Strictly protects `defect30-lbu` and any active unmerged worktrees.

2. Supply Starvation Watchdog:
   - Monitors .builder_queue/QUEUE_STATE.json.
   - When in-flight items land (e.g. item-29 landed), automatically appends
     staged downstream rungs (items 30–33) to prevent SUPPLY_STARVED idle stalls.

3. Desync & Stall Recovery:
   - Only acts on a genuinely diagnosed stall (stall_tier > 0 from
     glyph_build_chain_monitor.py) — never on idle+green-gate alone, since
     that combination is often just the ~2-minute gap before the next
     natural tick (2026-09-26 fix: the worktree-gate path used to fire
     unconditionally with no minimum idle duration).
   - Once a stall is diagnosed, checks whether a worktree's gate is 100%
     GREEN (the builder hit turn caps before landing) to explain it, then
     clears `monitor_state` so the next tick wakes the builder.

4. Health & Progress Reporting:
   - Emits structured status and action receipts.

5. System-1 Shadow Screener:
   - Evaluates unlogged landing and research receipts into .builder_queue/decision_log.jsonl.
   - Non-blocking shadow mode with local Ollama inference.
"""

from __future__ import annotations

import datetime
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path("/home/jericho/projects/zion/projects/visual_audio")
QUEUE_STATE_PATH = REPO_ROOT / ".builder_queue" / "QUEUE_STATE.json"
DRAFT_SUPPLY_PATH = Path("/home/jericho/.gemini/antigravity-cli/brain/02d562da-056b-4afa-ab10-8ebf35280e51/scratch/items_38_41_draft.json")
HERMES_DIR = Path("/home/jericho/.hermes")
HERMES_AGENT_DIR = HERMES_DIR / "hermes-agent"
CRON_JOB_ID = "af3e62239ce2"

PROTECTED_WORKTREES = {
    "defect30-lbu",
}

STAGED_SUPPLY_FALLBACK = [
    {
        "id": "item-38",
        "title": "Spatial window compositing & z-order elevation (overlapping tile damage clipping, top-window focus, drag repositioning)",
        "status": "queued",
        "blocks_on": ["item-37"],
        "claim_order": 38,
    },
    {
        "id": "item-39",
        "title": "Virtual terminal & PTY line discipline (ANSI/VT100 escape sequence parser, cursor movement, stdin/stdout IPC streams)",
        "status": "queued",
        "blocks_on": ["item-37", "item-38"],
        "claim_order": 39,
    },
    {
        "id": "item-40",
        "title": "Desktop notification daemon & system tray ABI (asynchronous agent toast alerts, status bar reactive applets)",
        "status": "queued",
        "blocks_on": ["item-38"],
        "claim_order": 40,
    },
    {
        "id": "item-41",
        "title": "Dynamic process lifecycle & spatial task manager (process kill/pause signals, interactive task manager tile, clean window close)",
        "status": "queued",
        "blocks_on": ["item-38", "item-39"],
        "claim_order": 41,
    },
]


def run_cmd(cmd: list[str], cwd: Path | None = None) -> tuple[int, str]:
    try:
        res = subprocess.run(
            cmd, cwd=str(cwd or REPO_ROOT), capture_output=True, text=True, check=False
        )
        return res.returncode, res.stdout + res.stderr
    except Exception as e:
        return 1, str(e)


def check_disk_space() -> dict[str, any]:
    h_total, h_used, h_free = shutil.disk_usage("/home")
    r_total, r_used, r_free = shutil.disk_usage("/")
    return {
        "home_free_gb": round(h_free / (1024 ** 3), 2),
        "home_total_gb": round(h_total / (1024 ** 3), 2),
        "home_used_pct": round((h_used / h_total) * 100, 1),
        "root_free_gb": round(r_free / (1024 ** 3), 2),
        "root_total_gb": round(r_total / (1024 ** 3), 2),
        "root_used_pct": round((r_used / r_total) * 100, 1),
    }


def cleanup_tmp_scratch(min_age_seconds: int = 3600) -> list[str]:
    """Safely prune stale test scratch directories from /tmp (older than min_age_seconds).
    Prevents root fs ENOSPC [Errno 28] crashes without using prohibited rm -rf.
    """
    actions = []
    root = Path("/tmp")
    if not root.exists():
        return actions

    now = time.time()
    cutoff = now - min_age_seconds
    prefixes = ("glyph_l1_", "glyph_vfs_", "glyph_shell_", "l1wgsl_", "gwb_")
    uid = os.getuid()

    files_removed = 0
    dirs_removed = 0
    bytes_freed = 0

    try:
        for entry in os.scandir(str(root)):
            if entry.name.startswith(prefixes) and entry.is_dir(follow_symlinks=False):
                try:
                    st = entry.stat(follow_symlinks=False)
                    if st.st_uid == uid and st.st_mtime < cutoff:
                        p = Path(entry.path)
                        for r, ds, fs in os.walk(str(p), topdown=False):
                            for f in fs:
                                fp = os.path.join(r, f)
                                try:
                                    fst = os.stat(fp)
                                    bytes_freed += fst.st_blocks * 512
                                    os.unlink(fp)
                                    files_removed += 1
                                except Exception:
                                    pass
                            for d in ds:
                                dp = os.path.join(r, d)
                                try:
                                    os.rmdir(dp)
                                except Exception:
                                    pass
                        try:
                            os.rmdir(str(p))
                            dirs_removed += 1
                        except Exception:
                            pass
                except Exception:
                    pass
    except Exception as e:
        actions.append(f"Tmp scratch scan error: {e}")

    if files_removed > 0 or dirs_removed > 0:
        mb = round(bytes_freed / (1024 * 1024), 1)
        actions.append(f"Cleaned /tmp scratch: {files_removed} files, {dirs_removed} dirs freed {mb} MB")
    return actions


def get_git_worktrees() -> list[dict[str, str]]:
    rc, out = run_cmd(["git", "worktree", "list"])
    worktrees = []
    if rc != 0:
        return worktrees
    for line in out.splitlines():
        parts = line.strip().split()
        if len(parts) >= 2:
            path_str = parts[0]
            commit = parts[1]
            branch = parts[2].strip("[]") if len(parts) > 2 else ""
            worktrees.append({
                "path": path_str,
                "commit": commit,
                "branch": branch,
                "name": Path(path_str).name,
            })
    return worktrees


def prune_landed_worktrees(landed_items: set[str]) -> list[str]:
    actions = []
    worktrees = get_git_worktrees()
    for wt in worktrees:
        name = wt["name"]
        path_str = wt["path"]
        if name in PROTECTED_WORKTREES or path_str == str(REPO_ROOT):
            continue

        # Check if worktree belongs to a landed item (e.g. item28-rootinit, item29-containment)
        match = re.match(r"item(\d+)-", name)
        if match:
            item_num = match.group(1)
            item_id = f"item-{item_num}"
            if item_id in landed_items:
                print(f"[watchdog] Pruning landed worktree: {path_str} (item {item_id} is landed)")
                rc, out = run_cmd(["git", "worktree", "remove", "--force", path_str])
                if rc == 0:
                    actions.append(f"Pruned landed worktree {name} ({item_id})")
                else:
                    actions.append(f"Failed to prune {name}: {out.strip()}")
    return actions


def check_and_replenish_supply() -> list[str]:
    actions = []
    if not QUEUE_STATE_PATH.exists():
        return actions

    try:
        with open(QUEUE_STATE_PATH, "r", encoding="utf-8") as f:
            qdata = json.load(f)
    except Exception as e:
        return [f"Error reading QUEUE_STATE.json: {e}"]

    queue = qdata.get("queue", [])
    landed_ids = {it["id"] for it in queue if it.get("status") == "landed"}
    existing_ids = {it["id"] for it in queue}

    # Only replenish if item-37 is landed and no remaining queued items exist
    queued_items = [it for it in queue if it.get("status") == "queued"]
    if "item-37" in landed_ids and len(queued_items) == 0:
        # Load draft supply
        new_items_to_add = []
        supply_source = STAGED_SUPPLY_FALLBACK
        if DRAFT_SUPPLY_PATH.exists():
            try:
                with open(DRAFT_SUPPLY_PATH, "r", encoding="utf-8") as f:
                    draft = json.load(f)
                    if isinstance(draft, list):
                        supply_source = draft
            except Exception:
                pass

        for item in supply_source:
            if item["id"] not in existing_ids:
                new_items_to_add.append({
                    "id": item["id"],
                    "title": item["title"],
                    "status": "queued",
                    "blocks_on": item.get("blocks_on", []),
                    "claim_order": item.get("claim_order", 99),
                })

        if new_items_to_add:
            # Check if repo main tree has no tracked dirty modifications before mutating QUEUE_STATE.json
            rc, diff = run_cmd(["git", "status", "--untracked-files=no", "--porcelain"])
            if rc == 0 and not diff.strip():
                queue.extend(new_items_to_add)
                qdata["queue"] = queue
                qdata["updated"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
                qdata["updated_by"] = "watchdog supply auto-replenish (items 38-41)"
                with open(QUEUE_STATE_PATH, "w", encoding="utf-8") as f:
                    json.dump(qdata, f, indent=2)
                run_cmd(["git", "add", ".builder_queue/QUEUE_STATE.json"])
                run_cmd(["git", "commit", "-m", "watchdog: auto-replenish queue supply (items 38-41 unblocked)"])
                actions.append(f"Appended {len(new_items_to_add)} supply items ({[it['id'] for it in new_items_to_add]}) to QUEUE_STATE.json")
            else:
                actions.append(f"Main tree dirty; deferred appending {len(new_items_to_add)} supply items")
    return actions


def is_builder_active() -> bool:
    log_path = HERMES_DIR / "logs" / "agent.log"
    if not log_path.exists():
        return False
    try:
        with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()[-2000:]
        af3e_lines = [l for l in lines if f"cron_{CRON_JOB_ID}" in l]
        if not af3e_lines:
            return False
        last = af3e_lines[-1]
        ended = any(k in last for k in ["Turn ended", "completed successfully", "skipping delivery", "suppressing agent run"])
        if ended:
            return False

        # Parse timestamp from log line: "2026-09-26 14:30:38,963 ..."
        m = re.match(r"^(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})", last)
        if m:
            last_dt = datetime.datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S")
            now_dt = datetime.datetime.now()
            # If the last activity was within 15 minutes, consider it actively running
            if (now_dt - last_dt).total_seconds() > 900:
                return False
        return True
    except Exception:
        return False


def check_and_recover_stalls() -> list[str]:
    actions = []
    if is_builder_active():
        return ["Builder session is actively executing."]

    # Gate: only intervene on a genuinely diagnosed stall (stall_tier > 0
    # from glyph_build_chain_monitor.py). The worktree-gate path below used
    # to fire unconditionally on any idle+green-gate combination with no
    # minimum idle duration — a green gate appearing in the ~2-minute gap
    # between two natural cron ticks would spoof a monitor_state reset for
    # no reason, since the next tick would have picked up the same change
    # for free. Both recovery paths now sit behind this one bar, matching
    # the "reserve for diagnosed desyncs, not routine" rule (2026-09-26).
    rc, mon_out = run_cmd(["python3", "tools/glyph_build_chain_monitor.py"])
    tier_m = re.search(r"stall_tier=(\d+)", mon_out) if rc == 0 else None
    if not tier_m or int(tier_m.group(1)) == 0:
        return ["No diagnosed stall (stall_tier=0) — waiting for natural tick."]

    # Inspect active item worktrees for completed green gates (diagnosis of
    # *what* stalled; the stall_tier check above already answered *whether*
    # to act).
    worktrees = get_git_worktrees()
    for wt in worktrees:
        wt_path = Path(wt["path"])
        name = wt["name"]
        if name in PROTECTED_WORKTREES or wt_path == REPO_ROOT:
            continue
        if not re.match(r"^item\d+-", name):
            continue

        test_files = list(wt_path.glob("tests/test_item*.py"))
        if not test_files:
            continue

        gate_file = test_files[0]
        rc, test_out = run_cmd(["pytest", str(gate_file), "-q", "-p", "no:randomly"], cwd=wt_path)
        if rc == 0 and "passed" in test_out and "failed" not in test_out:
            print(f"[watchdog] Diagnosed stall (tier {tier_m.group(1)}) + green gate in worktree {wt['name']}. Clearing monitor_state...")
            try:
                sys.path.insert(0, str(HERMES_AGENT_DIR))
                from cron.jobs import update_job
                update_job(CRON_JOB_ID, {"monitor_state": None})
                actions.append(f"Diagnosed real stall: cleared monitor_state for {CRON_JOB_ID} (green worktree {wt['name']} awaiting landing)")
            except Exception as e:
                actions.append(f"Failed to reset monitor_state: {e}")
            return actions

    # Diagnosed stall, but no green worktree explains it — plain reset.
    try:
        sys.path.insert(0, str(HERMES_AGENT_DIR))
        from cron.jobs import get_job, update_job
        j = get_job(CRON_JOB_ID)
        m_state = j.get("monitor_state") if j else None
        if m_state:
            print(f"[watchdog] Diagnosed real stall ({mon_out.strip()}). Clearing monitor_state...")
            update_job(CRON_JOB_ID, {"monitor_state": None})
            actions.append(f"Diagnosed real stall: cleared monitor_state for {CRON_JOB_ID}")
    except Exception as e:
        actions.append(f"Failed to reset monitor_state for stall: {e}")

    return actions


def screen_unlogged_receipts(max_evals: int = 3) -> list[str]:
    """Phase 2 (Advisory Mode) screening of unlogged receipts via local System-1 engine."""
    actions = []
    try:
        if str(REPO_ROOT) not in sys.path:
            sys.path.insert(0, str(REPO_ROOT))
        from tools.geos_system1 import scan_and_screen_unlogged
        qdir = REPO_ROOT / ".builder_queue"
        log_path = qdir / "decision_log.jsonl"
        decisions = scan_and_screen_unlogged(queue_dir=qdir, log_path=log_path, max_evals=max_evals, emit_advisories=True)
        if not decisions:
            actions.append("All recent receipts screened in decision_log.jsonl.")
        for d in decisions:
            adv_note = f" -> ADVISORY EMITTED: {Path(d.advisory_path).name}" if d.advisory_path else ""
            actions.append(f"[{d.head.upper()}] [{d.ticket_id}]: {d.decision} (conf: {d.confidence:.2f}, {d.latency_ms}ms){adv_note}")
    except Exception as e:
        actions.append(f"System-1 screening bypassed: {e}")
    return actions


def main():
    print("=== Glyph OS Builder Watchdog ===")
    disk = check_disk_space()
    print(f"Disk Free (/home): {disk['home_free_gb']} GB / {disk['home_total_gb']} GB ({disk['home_used_pct']}% used)")
    print(f"Disk Free (/root): {disk['root_free_gb']} GB / {disk['root_total_gb']} GB ({disk['root_used_pct']}% used)")

    # 1. Scratch hygiene: safely prune stale /tmp scratch older than 1h
    tmp_actions = cleanup_tmp_scratch(min_age_seconds=3600)
    for act in tmp_actions:
        print(f"[tmp_hygiene] {act}")

    # 2. Read current landed items
    landed_items = set()
    if QUEUE_STATE_PATH.exists():
        try:
            with open(QUEUE_STATE_PATH, "r", encoding="utf-8") as f:
                qdata = json.load(f)
                landed_items = {it["id"] for it in qdata.get("queue", []) if it.get("status") == "landed"}
        except Exception:
            pass

    # 3. Worktree hygiene
    prune_actions = prune_landed_worktrees(landed_items)
    for act in prune_actions:
        print(f"[prune] {act}")

    # 4. Supply replenishment
    supply_actions = check_and_replenish_supply()
    for act in supply_actions:
        print(f"[supply] {act}")

    # 5. Stall detection
    stall_actions = check_and_recover_stalls()
    for act in stall_actions:
        print(f"[stall] {act}")

    # 6. System-1 Shadow Screener (evaluates up to 3 unlogged receipts per tick)
    screen_actions = screen_unlogged_receipts(max_evals=3)
    for act in screen_actions:
        print(f"[system1] {act}")

    # 7. Spatial Build Map regeneration
    try:
        from tools.spatial_build_map import render as render_map
        map_out = REPO_ROOT / "build_map.png"
        data_out = REPO_ROOT / "build_map_data.json"
        minfo = render_map(128, map_out, data_out=data_out)
        print(f"[map] Updated spatial build map: {minfo['cells_used']}/{minfo['cells_total']} cells (frontier: {minfo['frontier_xy']})")
    except Exception as e:
        print(f"[map] Warning: could not render spatial build map: {e}")

    print("=== Watchdog Run Complete ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
