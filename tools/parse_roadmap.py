#!/usr/bin/env python3
"""
Parse Visual Audio ROADMAP.md to extract task information.

Handles the markdown format used in the project:
- Task lines: `- [ ] **TASK_XXX**: Description`
- Status from checkbox: `[ ]` = pending, `[x]` = complete
- Metadata indented with spaces: `- Priority:`, `- Receipt:`, `- Test:`, etc.
"""

import re
from pathlib import Path
from typing import Dict, List


def parse_roadmap_tasks(roadmap_path: str) -> List[Dict]:
    """
    Parse ROADMAP.md to extract task information.

    Handles the markdown format:
    - Task lines: `- [ ] **TASK_XXX**: Description`
    - Status from checkbox: `[ ]` = PENDING, `[x]` = COMPLETE
    - Metadata: `- Priority:`, `- Receipt:`, `- Test:`, etc.

    Args:
        roadmap_path: Path to ROADMAP.md file

    Returns:
        List of task dictionaries with keys:
        - id: Task ID
        - description: Task description
        - status: Task status (COMPLETE, PENDING, UNKNOWN)
        - priority: Task priority (CRITICAL, HIGH, MEDIUM, LOW, UNKNOWN)
        - receipts: List of receipt strings
        - test_command: Test command string
    """
    try:
        with open(roadmap_path, 'r') as f:
            content = f.read()
    except FileNotFoundError:
        return []

    tasks = []
    current_task = None

    for line in content.split('\n'):
        # Task marker line: `- [x] **TASK_XXX**: Description`
        task_match = re.match(r'-\s+\[(x| )\]\s+\*\*([^*]+)\*\*:\s*(.+)', line)
        if task_match:
            # Save previous task
            if current_task:
                tasks.append(current_task)

            # Extract task info
            checkbox, task_id, description = task_match.groups()
            status = 'COMPLETE' if checkbox == 'x' else 'PENDING'

            current_task = {
                'id': task_id.strip(),
                'description': description.strip(),
                'status': status,
                'priority': 'UNKNOWN',
                'receipts': [],
                'test_command': '',
                'completed': None
            }
            continue

        # Metadata lines for current task (indented with spaces)
        if current_task and line.startswith('  - '):
            metadata = line[4:].strip()

            # Priority
            priority_match = re.match(r'Priority:\s*(\w+)', metadata)
            if priority_match:
                current_task['priority'] = priority_match.group(1)
                continue

            # Receipt
            receipt_match = re.match(r'Receipt:\s*(.+)', metadata)
            if receipt_match:
                current_task['receipts'].append(receipt_match.group(1).strip())
                continue

            # Test
            test_match = re.match(r'Test:\s*(.+)', metadata)
            if test_match:
                current_task['test_command'] = test_match.group(1).strip()
                continue

            # Status
            status_match = re.match(r'Status:\s*(.+)', metadata)
            if status_match:
                status_str = status_match.group(1).strip().upper()
                # Map various status strings to standard ones
                if 'COMPLETE' in status_str or '✅' in status_str:
                    current_task['status'] = 'COMPLETE'
                elif 'PENDING' in status_str or 'NOT STARTED' in status_str:
                    current_task['status'] = 'PENDING'
                elif 'IN PROGRESS' in status_str or '🟡' in status_str:
                    current_task['status'] = 'IN_PROGRESS'
                continue

            # Completion date
            completed_match = re.search(r'(\d{4}-\d{2}-\d{2})', metadata)
            if completed_match and current_task['status'] == 'COMPLETE':
                current_task['completed'] = completed_match.group(1)

    # Save last task
    if current_task:
        tasks.append(current_task)

    return tasks


def main():
    """Test the parser by printing all tasks."""
    import sys

    if len(sys.argv) > 1:
        roadmap_path = sys.argv[1]
    else:
        roadmap_path = Path(__file__).parent.parent / "ROADMAP.md"

    tasks = parse_roadmap_tasks(roadmap_path)

    print(f"Parsed {len(tasks)} tasks from {roadmap_path}")
    print()

    for task in tasks[:10]:  # Show first 10
        print(f"Task: {task['id']}")
        print(f"  Description: {task['description']}")
        print(f"  Status: {task['status']}")
        print(f"  Priority: {task['priority']}")
        if task['receipts']:
            print(f"  Receipts ({len(task['receipts'])}):")
            for receipt in task['receipts'][:3]:
                print(f"    - {receipt}")
        print()


if __name__ == '__main__':
    main()