#!/usr/bin/env python3
"""Update roadmap state to match actual ROADMAP.md checkbox status"""

import json
import re
from pathlib import Path
from datetime import datetime

# Parse ROADMAP.md for actual completion
roadmap = Path("ROADMAP.md").read_text()

# Count checkboxes
total_checkboxes = len(re.findall(r'^- \[', roadmap, re.MULTILINE))
completed_checkboxes = len(re.findall(r'^- \[x\]', roadmap, re.MULTILINE))
incomplete_checkboxes = len(re.findall(r'^- \[ \]', roadmap, re.MULTILINE))

print(f"Actual ROADMAP.md status:")
print(f"  Total checkboxes: {total_checkboxes}")
print(f"  Completed: {completed_checkboxes}")
print(f"  Incomplete: {incomplete_checkboxes}")

# Update state file to match reality
state = {
    "current_phase": 5,
    "completed_tasks": [f"task_{i}" for i in range(1, completed_checkboxes + 1)],
    "last_task": f"task_{completed_checkboxes}",
    "timestamp": datetime.now().isoformat(),
    "all_tasks_complete": incomplete_checkboxes == 0,
    "total_tasks": total_checkboxes,
    "completed_count": completed_checkboxes,
    "status": "in_progress" if incomplete_checkboxes > 0 else "complete"
}

# Write atomically
state_path = Path(".roadmap_state.json")
temp_path = state_path.with_suffix(".tmp")
with open(temp_path, "w") as f:
    json.dump(state, f, indent=2)
temp_path.replace(state_path)

print(f"\n✓ State file updated: {completed_checkboxes}/{total_checkboxes} tasks complete")
print(f"Status: {state['status']}")