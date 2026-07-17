#!/usr/bin/env python3
"""Process remaining roadmap tasks, excluding blocked and research tasks"""
import re
import sys
import subprocess
from pathlib import Path

ROOT = Path(__file__).parent
ROADMAP = ROOT / "ROADMAP.md"
VERIFY_SCRIPT = ROOT / "verify_task.py"
SKIPPED_TASKS_FILE = ROOT / ".hermes/skipped_tasks.txt"

# Load already skipped tasks
if SKIPPED_TASKS_FILE.exists():
    already_skipped = set(SKIPPED_TASKS_FILE.read_text().splitlines())
else:
    already_skipped = set()

def parse_roadmap():
    """Parse ROADMAP.md and extract non-blocked tasks"""
    content = ROADMAP.read_text()
    
    all_tasks = {}
    for line in content.split('\n'):
        m = re.match(r'- \[([ x])\]\s+\*\*([A-Z0-9_]+)\*\*', line)
        if m:
            all_tasks[m.group(2)] = m.group(1) == 'x'
    
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
            
            # Extract metadata and check for blockers
            test_command = ""
            blocked = False
            reason = ""
            
            lines_after = content.split('\n')[content.split('\n').index(line)+1:]
            for next_line in lines_after[:12]:
                if next_line.startswith('## ') or (next_line.startswith('- [') and '**' in next_line):
                    break
                
                # Check for blocking conditions
                if 'IN GEOS TASKS' in next_line:
                    blocked = True
                    reason = "IN GEOS TASKS"
                    break
                elif 'Status: Blocked' in next_line or 'Autopark' in next_line:
                    blocked = True
                    reason = "Status: Blocked"
                    break
                elif 'REOPENED' in next_line:
                    blocked = True
                    reason = "REOPENED"
                    break
                elif 'Priority: MEDIUM' in next_line and 'Research Directions' in current_phase:
                    blocked = True
                    reason = "Research task"
                    break
                elif 'Test:' in next_line:
                    match = re.search(r'Test:\s*(.+)', next_line)
                    if match:
                        test_command = match.group(1).strip()
            
            # Skip research tasks (TASK_R series)
            if task_id.startswith('TASK_R'):
                blocked = True
                reason = "Research task"
            
            # Skip already skipped tasks
            if task_id in already_skipped:
                blocked = True
                reason = "Already skipped"
            
            if not blocked and test_command:
                pending_tasks.append({
                    'id': task_id,
                    'description': description,
                    'phase': current_phase,
                    'test_command': test_command
                })
    
    return pending_tasks

def main():
    pending = parse_roadmap()
    
    if not pending:
        print("No actionable pending tasks found")
        print("All tasks are either complete, blocked, or require human intervention")
        return 0
    
    print(f"Found {len(pending)} actionable tasks:")
    for task in pending:
        print(f"  - {task['id']}: {task['test_command'][:60]}...")
    
    # Process first task
    task = pending[0]
    print(f"\nProcessing task: {task['id']}")
    print(f"Test: {task['test_command']}")
    
    # Run verification
    try:
        result = subprocess.run(
            [sys.executable, str(VERIFY_SCRIPT), task['id']],
            capture_output=True,
            text=True,
            timeout=70
        )
        
        print(f"Verification output:\n{result.stdout}")
        
        if result.returncode == 0:
            print(f"✓ Task {task['id']} verified successfully")
        elif result.returncode == 2:
            print(f"⚠ Task {task['id']} requires human verification")
        elif result.returncode == 3:
            print(f"⚠ Task {task['id']} blocked by dependencies")
        else:
            print(f"✗ Task {task['id']} failed verification")
    except subprocess.TimeoutExpired:
        print(f"✗ Task {task['id']} verification timed out")
    except Exception as e:
        print(f"✗ Error verifying task {task['id']}: {e}")
    
    return result.returncode if 'result' in locals() else 1

if __name__ == '__main__':
    sys.exit(main())
