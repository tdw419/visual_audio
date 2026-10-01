#!/usr/bin/env python3
"""
route_b_status.py — Display Route B roadmap execution status
"""
import json
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).parent
CHECKPOINT = ROOT / ".route_b_checkpoint.json"
ROADMAP = ROOT / "ROUTE_B_OFFLOAD_ROADMAP.md"

def main():
    print(f"Route B Offload Status - {datetime.now().isoformat()}")
    print()

    # Parse roadmap phases
    phases = []
    if ROADMAP.exists():
        content = ROADMAP.read_text()
        import re
        for match in re.finditer(r"## (Phase \d+).*?\n(.*?)(?=---|\n## |\Z)", content, re.DOTALL):
            phase_name = match.group(1)
            phase_text = match.group(2)

            if "✅ DONE" in phase_text:
                status = "✅ DONE"
            elif "⚠️ PARTIAL" in phase_text:
                status = "⚠️ PARTIAL"
            elif "[x]" in phase_text:
                status = "✅ DONE"
            else:
                status = "⬜ TODO"

            phases.append((phase_name, status))

    # Load checkpoint
    checkpoint = {}
    if CHECKPOINT.exists():
        checkpoint = json.loads(CHECKPOINT.read_text())

    # Display status
    print("Roadmap Progress:")
    for phase_name, status in phases:
        if phase_name in checkpoint.get("completed_phases", []):
            print(f"  {phase_name}: {status} (executor)")
        else:
            print(f"  {phase_name}: {status}")

    print()
    if checkpoint:
        print(f"Executor Checkpoint:")
        print(f"  Current Phase: {checkpoint['current_phase']}")
        print(f"  Completed: {len(checkpoint.get('completed_phases', []))} phases")
        print(f"  Last Attempt: {checkpoint.get('last_attempt', 'Never')}")
    else:
        print("ℹ No checkpoint found - executor hasn't run yet")

if __name__ == '__main__':
    main()