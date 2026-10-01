#!/usr/bin/env python3
import re
from pathlib import Path

# Read ROADMAP.md
content = Path('ROADMAP.md').read_text()

# Parse all tasks to check completion status
all_tasks = {}
for line in content.split('\n'):
    m = re.match(r'- \[([ x])\]\s+\*\*([A-Z0-9_]+)\*\*', line)
    if m:
        all_tasks[m.group(2)] = m.group(1) == 'x'

# Parse pending tasks
pending_tasks = []
current_phase = None
lines = content.split('\n')

for i, line in enumerate(lines):
    phase_match = re.match(r'## Phase \d+:(.+?)\s+([🔴🟡🟢⚪])', line)
    if phase_match:
        current_phase = phase_match.group(1).strip()
        continue

    task_match = re.match(r'- \[ \]\s+\*\*([^*]+)\*\*:\s+(.+)', line)
    if task_match:
        task_id = task_match.group(1)
        description = task_match.group(2)
        
        # Extract metadata
        priority = 'MEDIUM'
        dependencies = []
        blocked = False
        status = ''

        lines_after = lines[i+1:i+11]
        for next_line in lines_after:
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
            elif 'Status:' in next_line:
                match = re.search(r'Status:\s*(.+)', next_line)
                if match:
                    status = match.group(1).strip()
                    blocked = 'Blocked' in status or 'REOPENED' in status

        # Check dependencies
        if dependencies:
            unmet_deps = [d for d in dependencies if not all_tasks.get(d, False)]
            if unmet_deps:
                print(f'{task_id}: BLOCKED by {unmet_deps}')
                blocked = True

        # Check title line
        if 'REOPENED' in description or 'falsely marked' in description:
            blocked = True

        if not blocked:
            pending_tasks.append({
                'id': task_id,
                'description': description,
                'phase': current_phase,
                'priority': priority
            })

priority_order = {'CRITICAL': 0, 'HIGH': 1, 'MEDIUM': 2, 'LOW': 3}
pending_tasks.sort(key=lambda t: priority_order.get(t['priority'], 99))

print(f'Total pending tasks: {len(pending_tasks)}')
for task in pending_tasks[:5]:
    print(f'  [{task["priority"]}] {task["id"]}: {task["description"]}')