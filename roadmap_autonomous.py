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

# Blocked phase status indicators - skip tasks in phases with these status indicators
BLOCKED_PHASE_INDICATORS = {"BLOCKED", "EXPLORATORY"}
# Minimum priority to consider (skip LOW priority tasks)
MIN_PRIORITY = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2}


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
    """Parse ROADMAP.md and extract pending tasks with phase blocking and priority filtering"""
    content = ROADMAP.read_text()
    
    pending_tasks = []
    current_phase = None
    current_task_id = None
    current_task_data = {}
    
    for line_num, line in enumerate(content.split('\n'), 1):
        phase_match = re.match(r'## Phase \d+:(.+?)\s+([🔴🟡🟢⚪])(.*)', line)
        if phase_match:
            phase_title = phase_match.group(1).strip()
            phase_status = phase_match.group(2)
            phase_text = phase_match.group(3).strip()
            
            # Check if phase is blocked by looking for keywords in phase text
            is_blocked = any(indicator in phase_text.upper() for indicator in BLOCKED_PHASE_INDICATORS)
            current_phase = None if is_blocked else phase_title
            # Finalize any pending task data
            if current_task_id and current_task_data:
                pending_tasks.append(current_task_data)
                current_task_id = None
                current_task_data = {}
            continue
        
        # Task marker line - both incomplete and complete
        task_match = re.match(r'- \[(x| )\]\s+\*\*([^*]+)\*\*:\s+(.+)', line)
        if task_match:
            # Finalize previous task data if exists
            if current_task_id and current_task_data:
                pending_tasks.append(current_task_data)
            
            status, task_id, description = task_match.groups()
            
            # Skip completed tasks
            if status == 'x':
                current_task_id = None
                current_task_data = {}
                continue
            
            # Start new task data
            # Skip tasks in blocked phases
            if not current_phase:
                current_task_id = None
                current_task_data = {}
                continue
                
            current_task_id = task_id
            current_task_data = {
                'id': task_id,
                'title': f"{task_id}: {description}",
                'description': description,
                'phase': current_phase,
                'priority': "MEDIUM",
                'dependencies': [],
                'test_command': "",
                'receipt_criteria': ""
            }
            continue
        
        # Process metadata lines for current task
        if current_task_id:
            if 'Priority:' in line:
                match = re.search(r'Priority:\s+(\w+)', line)
                if match:
                    current_task_data['priority'] = match.group(1)
            elif 'Dependencies:' in line:
                match = re.search(r'Dependencies:\s*(.+)', line)
                if match:
                    deps = match.group(1)
                    if deps != 'None':
                        current_task_data['dependencies'] = [d.strip() for d in deps.split(',')]
            elif 'Test:' in line:
                match = re.search(r'Test:\s*(.+)', line)
                if match:
                    current_task_data['test_command'] = match.group(1).strip()
            elif 'Receipt:' in line:
                match = re.search(r'Receipt:\s*(.+)', line)
                if match:
                    current_task_data['receipt_criteria'] = match.group(1).strip()
    
    # Finalize last task data
    if current_task_id and current_task_data:
        pending_tasks.append(current_task_data)
    
    # Filter by minimum priority (skip LOW priority)
    filtered_tasks = [
        t for t in pending_tasks 
        if t['priority'] in MIN_PRIORITY
    ]
    
    return filtered_tasks


SKIPPED_TASKS_FILE = ROOT / ".hermes/skipped_tasks.txt"

def load_skipped_tasks():
    """Load list of tasks that were skipped due to failures"""
    if SKIPPED_TASKS_FILE.exists():
        return set(SKIPPED_TASKS_FILE.read_text().splitlines())
    return set()

def skip_task(task_id, reason=""):
    """Mark a task as skipped"""
    SKIPPED_TASKS_FILE.parent.mkdir(parents=True, exist_ok=True)
    skipped = load_skipped_tasks()
    skipped.add(task_id)
    SKIPPED_TASKS_FILE.write_text('\n'.join(sorted(skipped)))
    print(f"→ Task {task_id} skipped ({reason})")

def get_next_task():
    """Get highest priority pending task"""
    pending = parse_roadmap()
    skipped = load_skipped_tasks()
    
    # Filter out skipped tasks
    pending = [t for t in pending if t['id'] not in skipped]

    if not pending:
        print("DEBUG: No pending tasks found after filtering")
        return None

    print(f"DEBUG: Found {len(pending)} pending tasks:")
    for t in pending:
        print(f"  - {t['id']}: {t['priority']} (test: {t['test_command'][:50] if t['test_command'] else 'none'})")

    priority_order = {'CRITICAL': 0, 'HIGH': 1, 'MEDIUM': 2, 'LOW': 3}
    pending.sort(key=lambda t: priority_order.get(t['priority'], 99))

    return pending[0]


def commit_task(task_id, receipt=""):
    """Git commit per verified task completion - stages code + ROADMAP, never untracked files.

    Strategy:
    - git add -u: stages all modified tracked files (code changes + ROADMAP)
    - git add src/ tools/ tests/: stages new files created in code directories
    - Never stages untracked files like keys/*private*.pem (blocked by .gitignore)

    This commits the task as one revertible unit without leaking secrets.
    """
    # Stage modified tracked files (code + ROADMAP)
    result = subprocess.run(['git', 'add', '-u'], cwd=ROOT, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"⚠ Failed to stage tracked changes: {result.stderr}")
        return False

    # Stage new files in code directories (src/, tools/, tests/)
    # These are directories where autonomous agents create new code
    for code_dir in ['src', 'tools', 'tests']:
        code_path = ROOT / code_dir
        if code_path.exists():
            result = subprocess.run(['git', 'add', str(code_path)], cwd=ROOT, capture_output=True, text=True)
            if result.returncode != 0:
                print(f"⚠ Failed to stage {code_dir}/: {result.stderr}")
                return False

    # Commit with message linking to task
    message = f"Complete {task_id}\n\n{receipt}"
    result = subprocess.run(
        ['git', 'commit', '-m', message],
        cwd=ROOT,
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        # Check if nothing to commit (possible if task only touched ignored files)
        if 'nothing to commit' in result.stdout.lower() or 'nothing to commit' in result.stderr.lower():
            print(f"⚠ No changes staged for {task_id} (may have only touched ignored files)")
            return True  # Not a failure, just no changes to commit

        print(f"⚠ Failed to commit {task_id}: {result.stderr}")
        return False

    return True


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
                print(f"Skipping this task for now and continuing to next.")
                skip_task(task['id'], "verification failed")
                return 0
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