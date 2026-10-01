#!/usr/bin/env python3
"""Filter out blocked and unverifiable tasks before executing roadmap_autonomous.py"""
import re
import sys
import subprocess
from pathlib import Path

ROOT = Path(__file__).parent
ROADMAP = ROOT / "ROADMAP.md"
SKIPPED_TASKS_FILE = ROOT / ".hermes/skipped_tasks.txt"

# Load already skipped tasks
already_skipped = set()
if SKIPPED_TASKS_FILE.exists():
    already_skipped = set(SKIPPED_TASKS_FILE.read_text().splitlines())

def parse_and_filter():
    content = ROADMAP.read_text()
    actionable = []

    for i, line in enumerate(content.split('\n')):
        if not line.startswith('- [ ]'):
            continue

        task_match = re.match(r'- \[ \]\s+\*\*([^*]+)\*\*:\s+(.+)', line)
        if not task_match:
            continue

        task_id, description = task_match.groups()

        # Skip research tasks
        if task_id.startswith('TASK_R'):
            continue

        # Skip already skipped
        if task_id in already_skipped:
            continue

        # Look ahead for blockers and test command
        blocked = False
        test_cmd = ""
        lookahead = content.split('\n')[i+1:i+13]

        for l in lookahead:
            if l.startswith('## ') or (l.startswith('- [') and '**' in l):
                break
            if 'IN GEOS TASKS' in l or 'Status: Blocked' in l or 'Autopark' in l or 'REOPENED' in l:
                blocked = True
                break
            if 'Test:' in l:
                m = re.search(r'Test:\s*(.+)', l)
                if m:
                    test_cmd = m.group(1).strip()

        # Keep only tasks with a shell-test-like command
        if not blocked and test_cmd:
            prefix_ok = test_cmd.startswith('python3') or test_cmd.startswith('./') or \
                        test_cmd.startswith('pytest') or test_cmd.startswith('cargo test')
            if prefix_ok:
                actionable.append(task_id)

    return actionable

if __name__ == '__main__':
    actionable = parse_and_filter()
    if not actionable:
        # No feasible tasks now; output marker for cron job to skip delivery
        print("[SILENT]")
        sys.exit(0)

    # At least one actionable task exists; invoke the existing executor once
    sys.exit(subprocess.run([sys.executable, str(ROOT / 'roadmap_autonomous.py')], cwd=ROOT).returncode)
