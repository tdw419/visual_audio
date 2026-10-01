#!/usr/bin/env python3
"""Robust roadmap task executor that handles various task states"""
import re
import sys
import subprocess
from pathlib import Path

ROOT = Path(__file__).parent
ROADMAP = ROOT / "ROADMAP.md"
SKIPPED_TASKS_FILE = ROOT / ".hermes/skipped_tasks.txt"

# Load already skipped tasks
if SKIPPED_TASKS_FILE.exists():
    already_skipped = set(SKIPPED_TASKS_FILE.read_text().splitlines())
else:
    already_skipped = set()

def analyze_task_state():
    """Analyze all tasks and categorize them by state"""
    content = ROADMAP.read_text()
    
    categories = {
        'complete': [],
        'actionable': [],
        'blocked_geos': [],
        'blocked_deps': [],
        'no_test': [],
        'research': [],
        'already_skipped': []
    }
    
    all_tasks = {}
    for line in content.split('\n'):
        m = re.match(r'- \[([ x])\]\s+\*\*([A-Z0-9_]+)\*\*', line)
        if m:
            all_tasks[m.group(2)] = m.group(1) == 'x'
    
    current_phase = None
    
    for line in content.split('\n'):
        phase_match = re.match(r'## Phase \d+:(.+?)\s+([🔴🟡🟢⚪])', line)
        if phase_match:
            current_phase = phase_match.group(1).strip()
            continue
        
        task_match = re.match(r'- \[([ x])\]\s+\*\*([^*]+)\*\*:\s+(.+)', line)
        if task_match:
            status, task_id, description = task_match.groups()
            
            # Skip completed tasks
            if status == 'x':
                categories['complete'].append(task_id)
                continue
            
            # Extract metadata
            test_command = ""
            blocked = False
            block_reason = ""
            
            lines_after = content.split('\n')[content.split('\n').index(line)+1:]
            for next_line in lines_after[:12]:
                if next_line.startswith('## ') or (next_line.startswith('- [') and '**' in next_line):
                    break
                
                if 'IN GEOS TASKS' in next_line:
                    blocked = True
                    block_reason = "IN GEOS TASKS"
                    categories['blocked_geos'].append(task_id)
                    break
                elif 'Status: Blocked' in next_line or 'Autopark' in next_line:
                    blocked = True
                    block_reason = "blocked by status"
                    categories['blocked_deps'].append(task_id)
                    break
                elif 'Test:' in next_line:
                    match = re.search(r'Test:\s*(.+)', next_line)
                    if match:
                        test_command = match.group(1).strip()
            
            # Check research tasks
            if task_id.startswith('TASK_R'):
                categories['research'].append(task_id)
                blocked = True
                block_reason = "research task"
            
            # Check if already skipped
            if task_id in already_skipped:
                categories['already_skipped'].append(task_id)
                blocked = True
                block_reason = "already skipped"
            
            if not blocked:
                if test_command and test_command.startswith('python3') or test_command.startswith('./'):
                    categories['actionable'].append({
                        'id': task_id,
                        'description': description,
                        'test_command': test_command,
                        'phase': current_phase
                    })
                else:
                    categories['no_test'].append(task_id)
    
    return categories

def main():
    categories = analyze_task_state()
    
    print("=" * 70)
    print("Visual Audio Roadmap Task Analysis")
    print("=" * 70)
    print()
    
    print(f"✓ Complete: {len(categories['complete'])} tasks")
    print(f"→ Actionable: {len(categories['actionable'])} tasks")
    print(f"⚠ No valid test: {len(categories['no_test'])} tasks")
    print(f"🔒 Blocked by GeOS: {len(categories['blocked_geos'])} tasks")
    print(f"🔒 Blocked by deps: {len(categories['blocked_deps'])} tasks")
    print(f"🔬 Research tasks: {len(categories['research'])} tasks")
    print(f"⏭ Already skipped: {len(categories['already_skipped'])} tasks")
    print()
    
    total_tasks = sum(len(v) for v in categories.values())
    print(f"Total: {total_tasks} tasks analyzed")
    print()
    
    if categories['actionable']:
        print("Actionable tasks (can execute now):")
        for task in categories['actionable']:
            print(f"  {task['id']}: {task['test_command'][:60]}...")
        print()
        
        # Try to execute first actionable task
        task = categories['actionable'][0]
        print(f"Attempting to verify: {task['id']}")
        
        # Check if test file exists
        test_file = None
        if 'python3' in task['test_command']:
            parts = task['test_command'].split()
            if len(parts) > 1:
                test_file = parts[1]
        
        if test_file and (ROOT / test_file).exists():
            print(f"Test file exists: {test_file}")
            try:
                result = subprocess.run(
                    task['test_command'],
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=60,
                    cwd=ROOT
                )
                
                print(f"Exit code: {result.returncode}")
                if result.stdout:
                    print(f"Output: {result.stdout[:200]}")
                if result.stderr:
                    print(f"Errors: {result.stderr[:200]}")
                    
                if result.returncode == 0:
                    print(f"✓ {task['id']} PASSES")
                else:
                    print(f"✗ {task['id']} FAILS")
                    
            except subprocess.TimeoutExpired:
                print(f"✗ {task['id']} TIMED OUT")
        else:
            print(f"⚠ Test file not found: {test_file}")
            print(f"Marking as no-test task")
    else:
        print("No actionable tasks found with valid test commands.")
        print()
        
        if categories['no_test']:
            print("Tasks without valid test commands:")
            for task_id in categories['no_test']:
                print(f"  {task_id}")
        
        print()
        print("All remaining tasks require:")
        print("  - External dependencies (GeOS)")
        print("  - Human intervention")
        print("  - Research/exploration")
        print("  - Manual verification")

if __name__ == '__main__':
    main()
