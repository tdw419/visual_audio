#!/usr/bin/env python3
"""
SkillOpt Autonomous Roadmap Executor - Batch Mode

Iteratively executes pending Visual Audio roadmap tasks until all are complete or blocked.
Combines autonomous execution with carry-forward for session continuity.

Usage:
  python3 skillopt_autonomous.py              # Run until no more tasks can proceed
  python3 skillopt_autonomous.py --once       # Execute only one task
  python3 skillopt_autonomous.py --list       # Show pending tasks without executing
"""

import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent
ROADMAP_AUTONOMOUS = ROOT / "roadmap_autonomous.py"
SKIP_LIST = ROOT / ".hermes/skip_tasks.txt"

# Tasks to skip (GeOS integration, blocked tasks)
SKIPPED_TASKS = set()
if SKIP_LIST.exists():
    SKIPPED_TASKS = set(SKIP_LIST.read_text().strip().split('\n'))


def is_skipped(task_id: str) -> bool:
    """Check if a task should be skipped."""
    return task_id in SKIPPED_TASKS


def run_executor_once() -> tuple[int, str, str]:
    """Run roadmap_autonomous.py once and capture output."""
    try:
        result = subprocess.run(
            [sys.executable, str(ROADMAP_AUTONOMOUS)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=120  # 2 minutes per task max
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return 124, '', 'Task execution timed out after 120s'


def parse_pending_from_roadmap() -> list:
    """Get list of pending task IDs from ROADMAP.md."""
    import re

    content = ROOT / "ROADMAP.md"
    if not content.exists():
        return []

    pending = []
    for line in content.read_text().split('\n'):
        if re.match(r'- \[ \]', line):
            m = re.search(r'\*\*([A-Z0-9_]+)\*\*', line)
            if m:
                task_id = m.group(1)
                if not is_skipped(task_id):
                    pending.append(task_id)

    return pending


def main():
    import argparse

    parser = argparse.ArgumentParser(description="SkillOpt autonomous roadmap executor")
    parser.add_argument('--once', action='store_true', help='Execute only one task')
    parser.add_argument('--list', action='store_true', help='List pending tasks without executing')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be executed')
    args = parser.parse_args()

    if args.list:
        pending = parse_pending_from_roadmap()
        print(f"Pending tasks ({len(pending)}):")
        for tid in pending:
            print(f"  - {tid}")
        print(f"\nSkipped tasks ({len(SKIPPED_TASKS)}):")
        for tid in SKIPPED_TASKS:
            print(f"  - {tid}")
        return 0

    pending = parse_pending_from_roadmap()

    if not pending:
        print("No pending tasks remaining (or all are skipped)")
        return 0

    if args.dry_run:
        print(f"Would execute {len(pending)} pending tasks:")
        for tid in pending:
            print(f"  - {tid}")
        return 0

    print(f"SkillOpt Autonomous Executor")
    print(f"Pending: {len(pending)} tasks")
    print(f"Skipped: {len(SKIPPED_TASKS)} tasks")
    print()

    iterations = 0
    max_iterations = 1 if args.once else 100

    while iterations < max_iterations:
        iterations += 1

        print(f"\n--- Iteration {iterations} ---")

        exit_code, stdout, stderr = run_executor_once()
        print(stdout)

        if stderr:
            print("STDERR:", stderr)

        # Check if we should stop
        if "No pending tasks" in stdout:
            print("\n✓ All tasks completed!")
            return 0

        if "requires human review" in stdout:
            print("\n⚠ Task requires human review - stopping")
            return 0

        if "BLOCKED by dependencies" in stdout:
            print("\n⚠ Task blocked by dependencies - stopping")
            return 0

        if exit_code != 0:
            print(f"\n✗ Executor failed with exit code {exit_code}")
            return exit_code

        # Brief pause between tasks
        time.sleep(1)

    print(f"\nCompleted {iterations} iterations (--once limit reached)")
    return 0


if __name__ == '__main__':
    sys.exit(main())