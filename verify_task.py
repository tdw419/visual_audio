#!/usr/bin/env python3
"""
verify_task.py — Verification script for Visual Audio roadmap tasks.

Checks if a task is truly complete by running its test command.

Exit codes:
0 = PASS (task verified)
1 = FAIL (test failed)
2 = NEEDS_HUMAN (manual test or requires human verification)
3 = BLOCKED (dependencies not met)
"""

import subprocess
import sys
import os
import re
from pathlib import Path

ROOT = Path(__file__).parent
ROADMAP = ROOT / "ROADMAP.md"

def parse_task_test_command(task_id: str) -> str:
    """
    Extract the test command from ROADMAP.md for a given task ID.
    
    Args:
        task_id: Task identifier (e.g., TASK_G2P002)
    
    Returns:
        Test command string, or empty string if not found
    """
    content = ROADMAP.read_text()
    lines = content.split('\n')
    
    # Find the task line
    for i, line in enumerate(lines):
        if f'**{task_id}**:' in line and line.startswith('- [ ]'):
            # Look for Test: in the next 10 lines (starting from i+1 to skip the task line itself)
            for j in range(i + 1, min(i + 10, len(lines))):
                test_line = lines[j]
                if 'Test:' in test_line:
                    # Extract test command (after "Test:")
                    test_match = re.search(r'Test:\s*(.+)', test_line)
                    if test_match:
                        cmd = test_match.group(1).strip()
                        # Remove backticks if present
                        cmd = cmd.strip('`')
                        return cmd
                elif test_line.startswith('## ') or (test_line.startswith('- [') and '**' in test_line):
                    # Hit next task or section, stop looking
                    break
    
    return ""

def run_test(test_command: str, timeout: int = 60) -> tuple:
    """
    Run the test command and capture output.
    
    Args:
        test_command: Shell command to execute
        timeout: Maximum execution time in seconds
    
    Returns:
        Tuple of (returncode, stdout, stderr)
    """
    try:
        result = subprocess.run(
            test_command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=ROOT
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "Test timed out"
    except Exception as e:
        return -1, "", f"Error running test: {e}"

def main():
    if len(sys.argv) != 2:
        print("Usage: verify_task.py <TASK_ID>")
        sys.exit(1)
    
    task_id = sys.argv[1]
    
    # Get test command
    test_command = parse_task_test_command(task_id)
    
    if not test_command:
        print(f"[FAIL] {task_id}: No test command found in ROADMAP.md")
        sys.exit(1)
    
    # Run test
    returncode, stdout, stderr = run_test(test_command)
    
    # Combine output
    output = stdout
    if stderr:
        output += "\n" + stderr
    
    # Check result
    if returncode == 0:
        print(f"[PASS] {task_id}: Test passed")
        if output:
            print(f"Output: {output[:200]}")
        sys.exit(0)
    else:
        print(f"[FAIL] {task_id}: FAIL: {test_command} exited {returncode}")
        if output:
            print(output)
        sys.exit(1)

if __name__ == '__main__':
    main()