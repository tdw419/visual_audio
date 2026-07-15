#!/usr/bin/env python3
import re
from pathlib import Path

ROOT = Path(__file__).parent
ROADMAP = ROOT / "ROADMAP.md"

def debug_parse_roadmap():
    """Debug version of parse_roadmap with detailed logging"""
    content = ROADMAP.read_text()

    # First, parse all tasks to check completion status
    all_tasks = {}
    for line in content.split('\n'):
        m = re.match(r'- \[([ x])\]\s+\*\*([A-Z0-9_]+)\*\*', line)
        if m:
            all_tasks[m.group(2)] = m.group(1) == 'x'

    print(f"DEBUG: all_tasks has {len(all_tasks)} entries")
    print(f"DEBUG: TASK_P001 completed = {all_tasks.get('TASK_P001', 'MISSING')}")
    print(f"DEBUG: TASK_X001 completed = {all_tasks.get('TASK_X001', 'MISSING')}")
    print(f"DEBUG: TASK_W001 completed = {all_tasks.get('TASK_W001', 'MISSING')}")
    print()

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
            print(f"DEBUG: Found pending task: {task_id}")

            # Extract metadata
            priority = "MEDIUM"
            dependencies = []
            test_command = ""
            receipt_criteria = ""
            blocked = False
            status = ""

            lines_after = content.split('\n')[content.split('\n').index(line)+1:]
            for next_line in lines_after[:10]:
                if next_line.startswith('## ') or (next_line.startswith('- ') and '**' in next_line):
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
                            for dep in deps.split(','):
                                dep = dep.strip()
                                task_id_match = re.match(r'([A-Z0-9_]+)', dep)
                                if task_id_match:
                                    dependencies.append(task_id_match.group(1))
                    print(f"  Dependencies: {dependencies}")
                elif 'Test:' in next_line:
                    match = re.search(r'Test:\s*(.+)', next_line)
                    if match:
                        test_command = match.group(1).strip()
                elif 'Receipt:' in next_line:
                    match = re.search(r'Receipt:\s*(.+)', next_line)
                    if match:
                        receipt_criteria = match.group(1).strip()
                elif 'Status:' in next_line:
                    match = re.search(r'Status:\s*(.+)', next_line)
                    if match:
                        status = match.group(1).strip()
                        blocked = 'Blocked' in status or 'REOPENED' in status

            # Also check the task title line for blocked indicators
            if 'REOPENED' in description or 'falsely marked' in description:
                blocked = True

            # Check if all dependencies are complete
            unmet_deps = [d for d in dependencies if not all_tasks.get(d, False)]
            if unmet_deps:
                print(f"  BLOCKED: unmet dependencies: {unmet_deps}")
                blocked = True

            # Skip blocked tasks
            if blocked:
                print(f"  -> SKIPPED (blocked)")
                continue

            print(f"  -> ADDED to pending_tasks list")
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

    print(f"\nDEBUG: Total pending_tasks: {len(pending_tasks)}")
    return pending_tasks

if __name__ == '__main__':
    debug_parse_roadmap()