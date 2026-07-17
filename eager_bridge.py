#!/usr/bin/env python3
"""
eager_bridge.py — Eager Autonomous Ideation Bridge

Analyzes the Visual Audio codebase and generates new pending tasks for ROADMAP.md.
Used by the Eager autonomous agent (Ideation/Drafter mode) to propose new work.

This script ONLY APPENDS tasks to ROADMAP.md. It does NOT execute or verify them.
Execution and verification are handled by roadmap_autonomous.py, which also
acquires the same lockfile to prevent concurrent modifications.

Safety Guarantees:
- Uses shared lockfile (.hermes/roadmap_autonomous.lock) to prevent races
- Caps task generation (MAX_TASKS_PER_RUN = 3) to avoid queue flooding
- Requires runnable Test: commands (no prose/manual tasks)
- Validates task format before appending

Exit Codes:
0 = Success (tasks appended)
1 = Lock contention or error
"""

import sys
import os
import re
import json
import subprocess
import fcntl
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).parent
ROADMAP = ROOT / "ROADMAP.md"
LOCKFILE = ROOT / ".hermes/roadmap_autonomous.lock"

# Configuration
MAX_TASKS_PER_RUN = 3  # Cap tasks to avoid queue flooding
MAX_RECEIPT_CHARS = 500

# Task templates with runnable Test: commands
TASK_TEMPLATES = {
    "test_coverage": {
        "description": "Add comprehensive test coverage for {module}",
        "priority": "MEDIUM",
        "test": "python3 -m pytest tests/test_{module}.py -v --cov=src/{module}",
        "receipt": "All tests pass with >80% coverage"
    },
    "bug_fix": {
        "description": "Fix bug in {component}: {issue}",
        "priority": "HIGH",
        "test": "python3 -m pytest tests/test_{component}.py -v -k test_{issue}",
        "receipt": "Bug fixed, all tests pass"
    },
    "optimization": {
        "description": "Optimize {function} in {module} for {metric}",
        "priority": "MEDIUM",
        "test": "python3 benchmark_{module}.py --metric {metric} --before --after",
        "receipt": "Performance improved by >20%"
    },
    "documentation": {
        "description": "Document {component} API and usage patterns",
        "priority": "LOW",
        "test": "python3 -c \"import src.{component}; help(src.{component})\" | grep -i {component}",
        "receipt": "Documentation complete with examples"
    },
    "feature": {
        "description": "Add {feature} support to {component}",
        "priority": "HIGH",
        "test": "python3 -m pytest tests/test_{component}.py -v -k test_{feature}",
        "receipt": "{feature} working, all tests pass"
    }
}


def acquire_lock():
    """Acquire exclusive lock (same as roadmap_autonomous.py)"""
    LOCKFILE.parent.mkdir(parents=True, exist_ok=True)
    try:
        lock_fd = open(LOCKFILE, 'w')
        fcntl.flock(lock_fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        lock_fd.write(f"{os.getpid()} {datetime.now().isoformat()}\\n")
        lock_fd.flush()
        return lock_fd
    except (IOError, BlockingIOError):
        return None


def release_lock(lock_fd):
    """Release the lock file"""
    if lock_fd:
        fcntl.flock(lock_fd.fileno(), fcntl.LOCK_UN)
        lock_fd.close()
        if LOCKFILE.exists():
            LOCKFILE.unlink()


def analyze_codebase():
    """
    Analyze the codebase to identify gaps and generate task proposals.

    Returns:
        List of task proposals with id, description, priority, test_command, receipt_criteria
    """
    proposals = []
    review_notes = []  # ideas with no honest auto-test → human triage, not the gated ROADMAP

    # 1. Check for missing test coverage
    print("Analyzing test coverage...")
    src_dir = ROOT / "src"
    tests_dir = ROOT / "tests"

    if src_dir.exists():
        for py_file in src_dir.rglob("*.py"):
            module_name = py_file.stem
            # Skip dunder modules (__init__, __main__): a test for them is noise.
            if module_name.startswith("__"):
                continue
            test_file = tests_dir / f"test_{module_name}.py"

            if not test_file.exists():
                # Full (sanitized) name in the id — truncating to 8 chars collided
                # distinct modules (e.g. phoneme_input / phoneme_output).
                task_id = f"TASK_COV_{re.sub(r'[^A-Z0-9]', '_', module_name.upper())}"
                proposals.append({
                    "id": task_id,
                    "description": f"Add test coverage for {module_name} module",
                    "priority": "MEDIUM",
                    # Honest gate: the deliverable IS this test file. verify_task.py
                    # fails while it's absent and passes once it exists and runs.
                    "test_command": f"python3 -m pytest tests/test_{module_name}.py -v",
                    "receipt_criteria": f"All {module_name} functionality tested"
                })

    # NOTE: The scans below (TODO/FIXME, exception refactors, docstring gaps) are
    # genuinely useful ideas, but none has an automated test that actually proves
    # completion — a generic `pytest tests/test_<module>.py` (or a help() call that
    # always exits 0) passes whether or not the work was done. Auto-appending them
    # with such a Test would let roadmap_autonomous.py mark undone work COMPLETE
    # (false-green). So they go to a human-review queue instead of the gated ROADMAP.
    for py_file in (ROOT / "src").rglob("*.py"):
        content = py_file.read_text()
        module_name = py_file.stem
        for i, line in enumerate(content.split('\n'), 1):
            if "TODO" in line or "FIXME" in line:
                note = line.strip().replace("TODO:", "").replace("FIXME:", "").strip()
                review_notes.append(f"[TODO] {module_name}:{i} — {note[:80]}")

    for critical_path in ["executor/sandbox.py", "codec/phy.py"]:
        fp = src_dir / critical_path
        if fp.exists() and fp.read_text().count("except Exception") > 2:
            review_notes.append(f"[security] Broad exception handling in {critical_path} (>2 `except Exception`)")

    doc_def, doc_cls = r"def [a-z_]+\(", r"class [A-Z][a-zA-Z]+\("
    for py_file in (ROOT / "src").rglob("*.py"):
        if py_file.stem.startswith("__"):
            continue
        content = py_file.read_text()
        total = len(re.findall(doc_def, content)) + len(re.findall(doc_cls, content))
        docstrings = len(re.findall(r'"""', content)) // 2
        if total > 0 and docstrings < total * 0.5:
            review_notes.append(f"[docs] {py_file.stem}: only {docstrings}/{total} entities documented")

    # Deduplicate by task ID
    unique_proposals = {}
    for p in proposals:
        if p["id"] not in unique_proposals:
            unique_proposals[p["id"]] = p

    # Write non-verifiable ideas to a human-review queue (never the gated ROADMAP).
    review_path = ROOT / "docs" / "eager_review_queue.md"
    if review_notes:
        review_path.parent.mkdir(parents=True, exist_ok=True)
        review_path.write_text(
            "# Eager review queue (ideas without an automated completion test)\n\n"
            "These need a human to scope a real verification before becoming ROADMAP tasks.\n\n"
            + "\n".join(f"- {n}" for n in review_notes) + "\n"
        )
        print(f"  {len(review_notes)} non-verifiable ideas -> {review_path.relative_to(ROOT)}")

    # Return as sorted list (HIGH priority first)
    priority_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
    sorted_proposals = sorted(
        unique_proposals.values(),
        key=lambda x: priority_order.get(x["priority"], 99)
    )

    return sorted_proposals


def existing_task_ids():
    """Get set of existing task IDs from ROADMAP.md"""
    if not ROADMAP.exists():
        return set()

    content = ROADMAP.read_text()
    task_ids = set()

    # Match both - [ ] and - [x] tasks
    for line in content.split('\n'):
        match = re.search(r'- \[[ x]\] \*\*([^*]+)\*\*:', line)
        if match:
            task_ids.add(match.group(1))

    return task_ids


def validate_task(task):
    """
    Validate that a task proposal is well-formed.

    Checks:
    - Test command is executable (not prose/manual/none)
    - Priority is valid
    - Receipt is reasonable length
    - No duplicate ID

    Returns:
        (is_valid, error_message)
    """
    # Check test command type
    test_cmd = task["test_command"]

    # Executable patterns (from verify_task.py)
    # Note: patterns must match actual command (case-sensitive)
    executable_patterns = [
        r'^python3\b',
        r'^pytest\b',
        r'^python\b',
        r'^bash\b',
        r'^sh\b',
        r'^node\b',
        r'^npm\b',
        r'^make\b',
        r'^cargo\b',
        r'^go\b',
    ]

    # Reject prose/manual tests
    test_cmd_lower = test_cmd.lower()
    if 'manual' in test_cmd_lower or test_cmd.startswith('verify') or 'check' in test_cmd_lower:
        return False, "Test command must be executable (not prose/manual)"

    # Require executable pattern match
    if not any(re.match(pattern, test_cmd) for pattern in executable_patterns):
        return False, f"Test command must start with recognized interpreter: got '{test_cmd}'"

    # Check priority
    valid_priorities = {"CRITICAL", "HIGH", "MEDIUM", "LOW"}
    if task["priority"] not in valid_priorities:
        return False, f"Invalid priority: {task['priority']}"

    # Check receipt length
    if len(task["receipt_criteria"]) > MAX_RECEIPT_CHARS:
        return False, f"Receipt too long ({len(task['receipt_criteria'])} > {MAX_RECEIPT_CHARS})"

    return True, ""


def append_to_roadmap(tasks):
    """
    Append validated tasks to ROADMAP.md.

    Format:
    - [ ] **TASK_ID**: description
      - Priority: CRITICAL|HIGH|MEDIUM|LOW
      - Dependencies: TASK_A, TASK_B (or None)
      - Test: `command`
      - Receipt: criteria

    Args:
        tasks: List of validated task dictionaries

    Returns:
        Number of tasks appended
    """
    if not ROADMAP.exists():
        print(f"ERROR: {ROADMAP} not found")
        return 0

    # Read current roadmap
    content = ROADMAP.read_text()
    lines = content.split('\n')

    # Find end of file (last non-empty line)
    last_idx = len(lines) - 1
    while last_idx >= 0 and lines[last_idx].strip() == "":
        last_idx -= 1

    # Append tasks
    appended = 0
    for task in tasks:
        # Add blank line before task if not already blank
        if last_idx >= 0 and lines[last_idx].strip() != "":
            lines.append("")
            last_idx += 1

        # Task entry
        lines.append(f"- [ ] **{task['id']}**: {task['description']}")
        lines.append(f"  - Priority: {task['priority']}")
        lines.append(f"  - Dependencies: None")
        lines.append(f"  - Test: `{task['test_command']}`")
        lines.append(f"  - Receipt: {task['receipt_criteria']}")

        last_idx = len(lines) - 1
        appended += 1

    # Write back
    ROADMAP.write_text('\n'.join(lines))

    return appended


def main():
    print("Eager Autonomous Ideation Bridge")
    print("=" * 60)
    print()

    # Acquire lock
    lock_fd = acquire_lock()
    if lock_fd is None:
        print("ERROR: Cannot acquire lockfile")
        print(f"Another instance (roadmap_autonomous.py or eager_bridge.py) is running")
        return 1

    try:
        print(f"Lock acquired: {LOCKFILE}")
        print()

        # Get existing task IDs to avoid duplicates
        existing = existing_task_ids()
        print(f"Found {len(existing)} existing tasks in ROADMAP.md")
        print()

        # Analyze codebase for task proposals
        proposals = analyze_codebase()

        # Filter out duplicates
        new_proposals = [p for p in proposals if p["id"] not in existing]

        print(f"Generated {len(proposals)} total proposals")
        print(f"  - {len(new_proposals)} new (not duplicates)")
        print(f"  - {len(proposals) - len(new_proposals)} already exist")
        print()

        # Validate and cap
        valid_tasks = []
        for proposal in new_proposals[:MAX_TASKS_PER_RUN]:
            is_valid, error = validate_task(proposal)
            if is_valid:
                valid_tasks.append(proposal)
            else:
                print(f"  ✗ {proposal['id']}: {error}")
                print(f"     Test command: {proposal['test_command']}")

        print(f"Validated {len(valid_tasks)} tasks (capped at {MAX_TASKS_PER_RUN})")
        print()

        if not valid_tasks:
            print("No new tasks to append")
            return 0

        # Preview tasks
        print("Tasks to append:")
        for i, task in enumerate(valid_tasks, 1):
            print(f"{i}. {task['id']}: {task['description']}")
            print(f"   Priority: {task['priority']}")
            print(f"   Test: {task['test_command']}")
            print()

        # Append to ROADMAP.md
        appended = append_to_roadmap(valid_tasks)

        print(f"✓ Appended {appended} tasks to {ROADMAP}")
        print()
        print("These tasks will be picked up by roadmap_autonomous.py for execution and verification.")

        return 0

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        release_lock(lock_fd)
        print(f"Lock released: {LOCKFILE}")


if __name__ == '__main__':
    sys.exit(main())