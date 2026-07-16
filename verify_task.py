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

def parse_task_test_command(task_id: str) -> tuple:
    """
    Extract the test command and its type from ROADMAP.md for a given task ID.

    Args:
        task_id: Task identifier (e.g., TASK_G2P002)

    Returns:
        Tuple of (test_command, test_type) where test_type is:
        - "shell": Runnable shell command
        - "manual": Requires human verification (contains "Manual" or "manual")
        - "prose": Descriptive test, not executable
        - "none": No test specified
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
                    # Two formats:
                    # 1. - Test: `command` (backtick-wrapped)
                    # 2. - Test: command (plain text)
                    backtick_match = re.search(r'`([^`]+)`', test_line)
                    if backtick_match:
                        cmd = backtick_match.group(1).strip()
                    else:
                        # Fallback: extract after "Test:" colon, strip leading whitespace
                        test_match = re.search(r'Test:\s*(.+)', test_line)
                        if test_match:
                            cmd = test_match.group(1).strip()
                            # Remove trailing comments like "(7/7 pass)" or "(manual)"
                            cmd = re.sub(r'\s*\(.*\)', '', cmd).strip()
                        else:
                            continue

                    cmd_lower = cmd.lower()

                    # Detect test type
                    if 'manual' in cmd_lower:
                        return cmd, "manual"
                    elif cmd.startswith('verify') or 'check' in cmd_lower:
                        # These are prose descriptions, not executable commands
                        return cmd, "prose"
                    elif not cmd or cmd == 'none':
                        return "", "none"
                    else:
                        return cmd, "shell"
                elif test_line.startswith('## ') or (test_line.startswith('- [') and '**' in test_line):
                    # Hit next task or section, stop looking
                    break

    return "", "none"

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

    # Get test command and type
    test_command, test_type = parse_task_test_command(task_id)

    if test_type == "none":
        print(f"[NEEDS_HUMAN] {task_id}: No test specified")
        sys.exit(2)
    elif test_type == "manual":
        print(f"[NEEDS_HUMAN] {task_id}: Manual verification required: {test_command}")
        sys.exit(2)
    elif test_type == "prose":
        print(f"[NEEDS_HUMAN] {task_id}: Descriptive test (not executable): {test_command}")
        sys.exit(2)

    # Run shell test
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