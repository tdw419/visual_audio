#!/usr/bin/env python3
"""
Autonomous Visual Audio Roadmap Executor
Uses Hermes delegate_task to execute pending tasks from ROADMAP.md
"""
import re, sys, os
from pathlib import Path
from datetime import datetime

ROADMAP = Path(__file__).parent / "ROADMAP.md"

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

def main():
    task = get_next_task()
    
    if not task:
        print("No pending tasks in Visual Audio ROADMAP.md")
        print("All tasks completed!")
        return 0
    
    print(f"Next task: {task['title']}")
    print(f"Priority: {task['priority']}")
    print(f"Phase: {task['phase']}")
    
    # Output JSON for delegate_task consumption
    import json
    print(json.dumps({
        'task_id': task['id'],
        'description': task['description'],
        'priority': task['priority'],
        'test_command': task['test_command'],
        'receipt_criteria': task['receipt_criteria'],
        'phase': task['phase']
    }))
    
    return 0

if __name__ == '__main__':
    sys.exit(main())