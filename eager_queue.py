#!/usr/bin/env python3
"""
Project-specific eager queue manager for Visual Audio.
Uses .eager-state/task_queue.md instead of global eager state.
"""
import sys, re, json, os
from pathlib import Path

QUEUE_FILE = Path(__file__).parent.parent / ".eager-state" / "task_queue.md"

def parse_queue():
    if not QUEUE_FILE.exists():
        print(f"# No queue file at {QUEUE_FILE}")
        return []
    
    content = QUEUE_FILE.read_text()
    tasks = []
    current_task = {}
    
    for line in content.split('\n'):
        task_match = re.match(r'### (TASK_\d+)', line)
        if task_match:
            if current_task:
                tasks.append(current_task)
            current_task = {'id': task_match.group(1)}
        elif current_task:
            key_match = re.match(r'- \*\*(.+?)\*\*:\s*(.+)', line)
            if key_match:
                key, value = key_match.groups()
                current_task[key] = value
    
    if current_task:
        tasks.append(current_task)
    
    return tasks

def list_queue():
    tasks = parse_queue()
    print("=== Visual Audio Task Queue ===\n")
    
    pending = [t for t in tasks if 'Status' not in t or t.get('Status') == 'PENDING']
    in_progress = [t for t in tasks if t.get('Status') == 'IN_PROGRESS']
    completed = [t for t in tasks if t.get('Status') == 'COMPLETED']
    
    if pending:
        print(f"## PENDING ({len(pending)})")
        for t in pending:
            print(f"  - {t['id']}: {t.get('Status', 'PENDING')} priority={t.get('Priority', 'N/A')}")
    
    if in_progress:
        print(f"\n## IN_PROGRESS ({len(in_progress)})")
        for t in in_progress:
            print(f"  - {t['id']}: IN_PROGRESS priority={t.get('Priority', 'N/A')}")
    
    if completed:
        print(f"\n## COMPLETED ({len(completed)})")
        for t in completed:
            print(f"  - {t['id']}: COMPLETED")
    
    if not tasks:
        print("(No tasks in queue)")

if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == 'list':
        list_queue()
    else:
        print("Usage: eager_queue.py list")