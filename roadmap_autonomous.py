#!/usr/bin/env python3
"""
Autonomous Visual Audio Roadmap Executor with Verification Gate

Uses delegate_task to execute pending tasks from ROADMAP.md.
MUST call verify_task.py before marking any task as complete.

Features:
- Concurrency lockfile to prevent overlapping runs
- Per-task git commits for checkpointing
- Verification gate before task completion
"""
import re
import sys
import os
import json
import subprocess
import fcntl
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).parent
ROADMAP = ROOT / "ROADMAP.md"
VERIFY_SCRIPT = ROOT / "verify_task.py"
LOCKFILE = ROOT / ".hermes/roadmap_autonomous.lock"


def acquire_lock():
    """Acquire exclusive lock to prevent concurrent runs"""
    LOCKFILE.parent.mkdir(parents=True, exist_ok=True)
    try:
        lock_fd = open(LOCKFILE, 'w')
        fcntl.flock(lock_fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        lock_fd.write(f"{os.getpid()} {datetime.now().isoformat()}\n")
        lock_fd.flush()
        return lock_fd
    except (IOError, BlockingIOError):
        return None


def release_lock(lock_fd):
    """Release the lock file"""
    if lock_fd:
        fcntl.flock(lock_fd.fileno(), fcntl.LOCK_UN)
        lock_fd.close()
        if LOCKFILE.exists():
            LOCKFILE.unlink()


def parse_roadmap():
    """Parse ROADMAP.md and extract pending tasks"""
    content = ROADMAP.read_text()

    pending_tasks = []
    current_phase = None

    for line in content.split('\n'):
        phase_match = re.match(r'## Phase \d+:(.+?)\s+([🔴🟡🟢⚪])', line)
        if phase_match:
            current_phase = phase_match.group(1).strip()
            continue

        task_match = re.match(r'- \[ \]\s+\*\*([^*]+)\*\*:\s+(.+)', line)
        if task_match:
            task_id, description = task_match.groups()

            # Extract metadata from following lines
            priority = "MEDIUM"
            dependencies = []
            test_command = ""
            receipt_criteria = ""

            lines_after = content.split('\n')[content.split('\n').index(line)+1:]
            for next_line in lines_after[:10]:
                if next_line.startswith('## ') or (next_line.startswith('- ') and '\*\*' in next_line):
                    break

                if 'Priority:' in next_line:
                    match = re.search(r'Priority:\s+(\w+)', next_line)
                    if match:
                        priority = match.group(1)
                elif 'Dependencies:' in next_line:
                    match = re.search(r'Dependencies:\s*(.+)', next_line)
                    if match:
                        deps = match.group(1)
                        if deps != 'None':
                            dependencies = [d.strip() for d in deps.split(',')]
                elif 'Test:' in next_line:
                    match = re.search(r'Test:\s*(.+)', next_line)
                    if match:
                        test_command = match.group(1).strip()
                elif 'Receipt:' in next_line:
                    match = re.search(r'Receipt:\s*(.+)', next_line)
                    if match:
                        receipt_criteria = match.group(1).strip()

            pending_tasks.append({
                'id': task_id,
                'title': f"{task_id}: {description}",
                'description': description,
                'phase': current_phase,
                'priority': priority,
                'dependencies': dependencies,
                'test_command': test_command,
                'receipt_criteria': receipt_criteria
            })

    return pending_tasks


def get_next_task():
    """Get highest priority pending task"""
    pending = parse_roadmap()

    if not pending:
        return None

    priority_order = {'CRITICAL': 0, 'HIGH': 1, 'MEDIUM': 2, 'LOW': 3}
    pending.sort(key=lambda t: priority_order.get(t['priority'], 99))

    return pending[0]


def commit_task(task_id, receipt=""):
    """Git commit per verified task completion - stages all changed files"""
    # Stage ALL changed files so each task is one complete, revertible unit
    subprocess.run(['git', 'add', '-A'], cwd=ROOT, check=True)

    # Commit with message linking to task
    message = f"Complete {task_id}\n\n{receipt}"
    result = subprocess.run(
        ['git', 'commit', '-m', message],
        cwd=ROOT,
        capture_output=True,
        text=True
    )

    return result.returncode == 0


def mark_task_complete(task_id, receipt=""):
    """Mark task as complete in ROADMAP.md"""
    content = ROADMAP.read_text()
    lines = content.split('\n')

    for i, line in enumerate(lines):
        if f"- [ ] **{task_id}" in line:
            lines[i] = line.replace("- [ ]", "- [x]")

            # Update or add receipt
            if receipt:
                found_receipt = False
                for j in range(i, min(i + 10, len(lines))):
                    if "Receipt:" in lines[j]:
                        lines[j] = f"  - Receipt: {receipt}"
                        found_receipt = True
                        break

                if not found_receipt:
                    lines.insert(i + 2, f"  - Receipt: {receipt}")

            ROADMAP.write_text('\n'.join(lines))
            return True

    return False


def main():
    # Acquire lock
    lock_fd = acquire_lock()
    if lock_fd is None:
        print(f"Another roadmap_autonomous.py instance is already running (lockfile: {LOCKFILE})")
        print("Waiting for it to complete...")
        return 0

    try:
        task = get_next_task()

        if not task:
            print("No pending tasks in Visual Audio ROADMAP.md")
            print("All tasks completed!")
            return 0

        print(f"Visual Audio Roadmap Executor")
        print(f"Task: {task['title']}")
        print(f"Priority: {task['priority']}")
        print(f"Phase: {task['phase']}")
        print(f"Test: {task['test_command'][:80]}...")

        # CRITICAL: Run verification BEFORE marking complete
        print(f"\nVerifying task completion...")
        try:
            # Check if verify_task.py exists
            if not VERIFY_SCRIPT.exists():
                print(f"ERROR: verify_task.py not found at {VERIFY_SCRIPT}")
                print("Cannot verify task safely - aborting")
                return 1

            # Run verification (with timeout)
            result = subprocess.run(
                ['timeout', '60', sys.executable, str(VERIFY_SCRIPT), task['id']],
                capture_output=True,
                text=True,
                timeout=70
            )

            print(f"Verification output: {result.stdout}")

            # Exit codes: 0=PASS, 1=FAIL, 2=NEEDS_HUMAN, 3=BLOCKED
            if result.returncode == 1:
                print(f"\n✗ Task {task['id']} FAILS verification")
                print(f"Cannot mark complete. Fix failing tests first.")
                return 1
            elif result.returncode == 2:
                print(f"\n⚠ Task {task['id']} requires human review")
                print(f"Manual test cannot be auto-verified. Parking for review.")
                return 0
            elif result.returncode == 3:
                print(f"\n⚠ Task {task['id']} BLOCKED by dependencies")
                print(f"Cannot proceed until dependencies are complete.")
                return 0
            elif result.returncode == 0:
                print(f"\n✓ Task {task['id']} PASSES verification")

                # Only mark complete after verification passes
                receipt = f"Verified by verify_task.py at {datetime.now().isoformat()}"
                if mark_task_complete(task['id'], receipt):
                    print(f"✓ Marked {task['id']} as complete")

                    # Git commit per task
                    if commit_task(task['id'], receipt):
                        print(f"✓ Committed {task['id']} to git")
                    else:
                        print(f"⚠ Git commit failed (task marked complete but not committed)")

                    return 0
                else:
                    print(f"ERROR: Failed to update ROADMAP.md")
                    return 1
            else:
                print(f"ERROR: Verification failed unexpectedly (exit {result.returncode})")
                return 1

        except subprocess.TimeoutExpired:
            print(f"ERROR: Verification timed out - task tests may be hanging")
            return 1
        except Exception as e:
            print(f"ERROR: Verification failed: {e}")
            return 1
    finally:
        release_lock(lock_fd)


if __name__ == '__main__':
    sys.exit(main())