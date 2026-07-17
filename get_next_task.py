#!/usr/bin/env python3
"""
Autonomous Visual Audio Roadmap Executor
Uses Hermes delegate_task to execute pending tasks from ROADMAP.md
"""
import re, sys, os
from pathlib import Path
from datetime import datetime

ROADMAP = Path(__file__).parent / "ROADMAP.md"

# Blocked phase status indicators - skip tasks in phases with these status indicators
BLOCKED_PHASE_INDICATORS = {"BLOCKED", "EXPLORATORY"}
# Minimum priority to consider (skip LOW priority tasks)
MIN_PRIORITY = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2}

def parse_roadmap():
    """Parse ROADMAP.md and extract pending tasks"""
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