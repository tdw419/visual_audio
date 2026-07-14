#!/usr/bin/env python3
"""
verify_task.py — Completion gate for the autonomous roadmap loop.

The autonomous executor must call this BEFORE flipping a task from [ ] to [x].
It refuses to certify a task complete unless:

  1. dependencies are all marked [x] in ROADMAP.md
  2. the task's `Test:` line is an actually-runnable command (not prose)
  3. that command exits 0 from a clean subprocess in the repo root

This is the guard that was missing when TASK_E003 got marked ✅ COMPLETE while
three of its own tests were red. Self-report is not a receipt; a green exit
code from a re-run is. Prose tests ("Manual verification of ...") can never be
machine-certified — they return NEEDS_HUMAN so the loop parks them for review
instead of silently passing them.

Usage:
  python3 verify_task.py TASK_E003          # -> exit 0 PASS / 1 FAIL / 2 NEEDS_HUMAN / 3 BLOCKED
  python3 verify_task.py --all              # audit every [x] task; nonzero if any is falsely green
"""

import re
import shlex
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent
ROADMAP = ROOT / "ROADMAP.md"

# A Test: line is runnable only if it starts with one of these.
RUNNABLE = ('python3 ', 'python ', 'pytest ', 'cargo ', './', 'bash ', 'sh ')

PASS, FAIL, NEEDS_HUMAN, BLOCKED = 0, 1, 2, 3


def parse_tasks():
    """Return {id: {done, deps, test, backtick_cmds}} for every task in ROADMAP."""
    tasks = {}
    cur = None
    for line in ROADMAP.read_text().split('\n'):
        m = re.match(r'- \[([ x])\]\s+\*\*([A-Z0-9_]+)\*\*', line)
        if m:
            cur = m.group(2)
            tasks[cur] = {'done': m.group(1) == 'x', 'deps': [], 'test': None}
            continue
        if cur is None:
            continue
        if 'Dependencies:' in line:
            deps = re.search(r'Dependencies:\s*(.+)', line).group(1).strip()
            if deps and deps != 'None':
                tasks[cur]['deps'] = re.findall(r'TASK_[A-Z0-9_]+', deps)
        elif 'Test:' in line and tasks[cur]['test'] is None:
            # prefer the first backticked command on the Test: line
            ticks = re.findall(r'`([^`]+)`', line)
            runnable = [c for c in ticks if c.strip().startswith(RUNNABLE)]
            tasks[cur]['test'] = runnable[0] if runnable else (
                ticks[0] if ticks else re.search(r'Test:\s*(.+)', line).group(1).strip())
    return tasks


def run_test(cmd: str) -> tuple:
    # Use venv Python for python3 commands
    if cmd.strip().startswith('python3 '):
        cmd = cmd.replace('python3 ', './venv/bin/python3 ', 1)
    # Compound commands (&&, ||, |, ;) need a shell; simple ones run directly.
    shell = any(op in cmd for op in ('&&', '||', '|', ';', '>'))
    try:
        p = subprocess.run(
            cmd if shell else shlex.split(cmd),
            cwd=ROOT, capture_output=True, text=True, timeout=600, shell=shell)
        return p.returncode, (p.stdout + p.stderr)[-2000:]
    except subprocess.TimeoutExpired:
        return 124, "TIMEOUT after 600s"
    except Exception as e:
        return 125, f"could not launch: {e}"


def verify(task_id: str, tasks: dict) -> tuple:
    """Return (verdict, message)."""
    if task_id not in tasks:
        return FAIL, f"{task_id} not found in ROADMAP.md"
    t = tasks[task_id]

    unmet = [d for d in t['deps'] if not tasks.get(d, {}).get('done')]
    if unmet:
        return BLOCKED, f"blocked: unmet dependencies {unmet}"

    cmd = t['test']
    if not cmd or not cmd.strip().startswith(RUNNABLE):
        return NEEDS_HUMAN, f"no runnable Test: command (found {cmd!r}) — needs human review"

    code, tail = run_test(cmd)
    if code == 0:
        return PASS, f"PASS: `{cmd}` exited 0"
    return FAIL, f"FAIL: `{cmd}` exited {code}\n{tail}"


def main():
    tasks = parse_tasks()

    if '--all' in sys.argv:
        bad = 0
        for tid, t in tasks.items():
            if not t['done']:
                continue
            verdict, msg = verify(tid, tasks)
            if verdict != PASS:
                bad += 1
                print(f"✗ {tid} is marked [x] but does NOT verify — {msg.splitlines()[0]}")
        if bad == 0:
            print("✓ every completed task re-verifies from a clean run")
        return 1 if bad else 0

    if len(sys.argv) < 2:
        print(__doc__)
        return FAIL
    verdict, msg = verify(sys.argv[1], tasks)
    label = {PASS: 'PASS', FAIL: 'FAIL', NEEDS_HUMAN: 'NEEDS_HUMAN', BLOCKED: 'BLOCKED'}[verdict]
    print(f"[{label}] {sys.argv[1]}: {msg}")
    return verdict


if __name__ == '__main__':
    sys.exit(main())
