#!/usr/bin/env python3
"""
Manual Roadmap Task Executor - executes pending tasks by bypassing skipped tasks list
"""
import re
import sys
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).parent
ROADMAP = ROOT / "ROADMAP.md"

# Blocked phase status indicators - skip tasks in phases with these status indicators
BLOCKED_PHASE_INDICATORS = {"BLOCKED", "EXPLORATORY"}
# Minimum priority to consider (skip LOW priority tasks)
MIN_PRIORITY = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2}

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

def main():
    pending = parse_roadmap()
    
    if not pending:
        print("No pending tasks found")
        return 0
    
    priority_order = {'CRITICAL': 0, 'HIGH': 1, 'MEDIUM': 2, 'LOW': 3}
    pending.sort(key=lambda t: priority_order.get(t['priority'], 99))
    
    print(f"Found {len(pending)} pending tasks:")
    for i, t in enumerate(pending, 1):
        print(f"{i}. {t['id']}: {t['title']}")
        print(f"   Priority: {t['priority']}")
        print(f"   Phase: {t['phase']}")
        if t['test_command']:
            print(f"   Test: {t['test_command'][:100]}...")
        print()
    
    # Execute highest priority task
    task = pending[0]
    print(f"\n{'='*60}")
    print(f"EXECUTING TASK: {task['id']}")
    print(f"{'='*60}")
    print(f"Description: {task['description']}")
    print(f"Priority: {task['priority']}")
    print(f"Phase: {task['phase']}")
    
    if task['test_command']:
        print(f"\nTest command: {task['test_command']}")
        
        # Extract and run the test command
        test_cmd = re.sub(r'\s*\(.*\)', '', task['test_command']).strip()
        test_cmd = test_cmd.replace('`', '').strip()
        
        if test_cmd and 'manual' not in test_cmd.lower():
            print(f"\nRunning test: {test_cmd}")
            try:
                result = subprocess.run(
                    test_cmd,
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=120
                )
                
                if result.returncode == 0:
                    print(f"✓ Test passed")
                    if result.stdout:
                        print(f"Output: {result.stdout[:500]}")
                    
                    # Mark task as complete
                    content = ROADMAP.read_text()
                    lines = content.split('\n')
                    
                    for i, line in enumerate(lines):
                        if f"- [ ] **{task['id']}**" in line:
                            lines[i] = line.replace("- [ ]", "- [x]")
                            lines.insert(i + 2, f"  - Receipt: Executed by manual roadmap executor at {Path(__file__).stat().st_mtime}")
                            break
                    
                    ROADMAP.write_text('\n'.join(lines))
                    print(f"✓ Task marked as complete in ROADMAP.md")
                    
                else:
                    print(f"✗ Test failed with return code {result.returncode}")
                    if result.stderr:
                        print(f"Error: {result.stderr[:500]}")
                    
            except subprocess.TimeoutExpired:
                print(f"✗ Test timed out after 120 seconds")
            except Exception as e:
                print(f"✗ Error running test: {e}")
    
    return 0

if __name__ == '__main__':
    sys.exit(main())