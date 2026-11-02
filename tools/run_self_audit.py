#!/usr/bin/env python3
"""
run_self_audit.py — Local, single-iteration self-audit loop for Visual Audio.

This tool runs ONE audit iteration and stops. It does NOT set up cron,
supervisord, or any recurring schedule. It's a safe, local-only check that:

1. Loads the ROADMAP.md file
2. Extracts tasks with implementation claims
3. Uses tools/ollama_prompt.py to analyze which tasks might be suspect
4. Uses tools/audit_checker.py to verify implementations actually exist
5. Outputs a report with findings

This is the SAFE LOCAL primitive that other systems can wrap if they want
periodic execution (e.g., via existing cron jobs or supervisord configs
managed by the human operator).

Usage:
  python3 tools/run_self_audit.py [--roadmap spec/ROADMAP.md] [--output audit_report.json]

Environment variables:
  OLLAMA_MODEL - Model to use for analysis (default: qwen2.5-coder:14b)
"""

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path


def load_roadmap(roadmap_path):
    """Load ROADMAP.md content."""
    if not Path(roadmap_path).exists():
        print(f"ERROR: ROADMAP not found: {roadmap_path}", file=sys.stderr)
        return None
    with open(roadmap_path, "r") as f:
        return f.read()


def extract_roadmap_tasks(roadmap_content):
    """
    Extract tasks from ROADMAP.md that have implementation claims.

    Looks for patterns like:
    - [x] TASK_XXX: Description (impl: tools/something.py)
    - [ ] TASK_XXX: Description (impl: tools/something.py)

    Returns list of dicts with task info.
    """
    tasks = []
    # Match task format: [x] or [ ] followed by TASK_ID: description (impl: path)
    pattern = r'^[\s]*\[[ x]\]\s+(TASK_\w+):\s*(.+?)(?:\(impl:\s*([^\)]+)\))?$'
    matches = re.finditer(pattern, roadmap_content, re.MULTILINE)

    for match in matches:
        task_id = match.group(1)
        description = match.group(2).strip()
        impl = match.group(3).strip() if match.group(3) else None

        tasks.append({
            "task_id": task_id,
            "description": description,
            "implementation": impl
        })

    return tasks


def analyze_with_ollama(tasks, model="qwen2.5-coder:14b"):
    """
    Use Ollama to identify which tasks have suspect implementations.

    This sends the task list to Ollama and asks it to flag tasks that:
    - Have no implementation path when marked complete
    - Have implementation paths that seem unlikely given the description
    - Have inconsistent status (marked complete but impl path doesn't exist)

    Returns a list of task IDs flagged as suspect.
    """
    # Build a summary of tasks for the prompt
    task_summary = []
    for task in tasks:
        status_mark = "COMPLETE" if task["implementation"] else "INCOMPLETE"
        impl_info = task["implementation"] if task["implementation"] else "None"
        task_summary.append(f"- {task['task_id']}: {status_mark} | {impl_info} | {task['description'][:100]}")

    prompt = """Analyze these Visual Audio ROADMAP tasks and flag tasks with SUSPECT implementations.

Rules for flagging:
1. Tasks marked COMPLETE but with no implementation path (impl: None)
2. Tasks marked COMPLETE with an implementation path that doesn't match the description
3. Tasks where the implementation path seems improbable (wrong file, wrong location)

Respond with a JSON array of task IDs to audit further:
["TASK_A001", "TASK_B123"]

Do NOT include any other text or explanation — ONLY the JSON array.

Tasks to analyze:
""" + "\n".join(task_summary)

    try:
        result = subprocess.run(
            ["ollama", "run", model, prompt],
            capture_output=True,
            text=True,
            timeout=300,
        )
    except subprocess.TimeoutExpired:
        print("WARNING: Ollama timeout, skipping AI analysis", file=sys.stderr)
        return []
    except FileNotFoundError:
        print("WARNING: Ollama not found, skipping AI analysis", file=sys.stderr)
        return []

    if result.returncode != 0:
        print(f"WARNING: Ollama failed: {result.stderr}", file=sys.stderr)
        return []

    # Try to parse JSON response
    try:
        # Extract JSON from response (Ollama might include extra text)
        json_match = re.search(r'\[.*\]', result.stdout, re.DOTALL)
        if json_match:
            suspect_tasks = json.loads(json_match.group())
            return suspect_tasks
        else:
            # Fallback: try parsing entire response
            return json.loads(result.stdout)
    except json.JSONDecodeError:
        print(f"WARNING: Could not parse Ollama response as JSON", file=sys.stderr)
        return []


def audit_tasks(tasks, task_ids_to_audit):
    """
    Audit specific tasks using audit_checker.py.

    Returns a list of audit results.
    """
    results = []
    script_dir = Path(__file__).parent
    checker_path = script_dir / "audit_checker.py"

    for task in tasks:
        if task["task_id"] not in task_ids_to_audit:
            continue

        if not task["implementation"]:
            # Flag tasks marked complete without implementation
            results.append({
                "task_id": task["task_id"],
                "spec": None,
                "passed": False,
                "issue": "Task marked complete but has no implementation path",
                "description": task["description"]
            })
            continue

        # Run audit_checker
        result = subprocess.run(
            [sys.executable, str(checker_path), "--impl", task["implementation"], "--json"],
            capture_output=True,
            text=True,
        )

        if result.returncode == 0 and result.stdout:
            try:
                audit_data = json.loads(result.stdout)
                audit_data["description"] = task["description"]
                results.append(audit_data)
            except json.JSONDecodeError:
                results.append({
                    "task_id": task["task_id"],
                    "spec": task["implementation"],
                    "passed": False,
                    "issue": f"Audit checker failed: {result.stdout}",
                    "description": task["description"]
                })
        else:
            results.append({
                "task_id": task["task_id"],
                "spec": task["implementation"],
                "passed": False,
                "issue": f"Audit checker failed: {result.stderr}",
                "description": task["description"]
            })

    return results


def generate_report(all_tasks, audit_results, suspect_task_ids):
    """
    Generate a comprehensive audit report.
    """
    report = {
        "timestamp": subprocess.check_output(["date", "-Iseconds"], text=True).strip(),
        "total_tasks": len(all_tasks),
        "suspect_by_ai": len(suspect_task_ids),
        "audited_tasks": len(audit_results),
        "failed_audits": sum(1 for r in audit_results if not r.get("passed", False)),
        "findings": audit_results,
        "summary": {
            "critical_issues": [],
            "warnings": [],
            "passed": []
        }
    }

    # Categorize findings
    for result in audit_results:
        if not result.get("passed", False):
            report["summary"]["critical_issues"].append({
                "task_id": result.get("task_id"),
                "issue": result.get("issue") or result.get("summary", "Unknown issue")
            })
        else:
            report["summary"]["passed"].append(result.get("task_id"))

    # Add warnings for tasks marked complete without implementation
    for task in all_tasks:
        if task["task_id"] in suspect_task_ids and not task["implementation"]:
            if task["task_id"] not in [f["task_id"] for f in report["summary"]["critical_issues"]]:
                report["summary"]["warnings"].append({
                    "task_id": task["task_id"],
                    "issue": "Flagged by AI but has no implementation path"
                })

    return report


def main():
    parser = argparse.ArgumentParser(
        description="Run local self-audit for Visual Audio ROADMAP"
    )
    parser.add_argument(
        "--roadmap",
        default="ROADMAP.md",
        help="Path to ROADMAP.md (default: ROADMAP.md)"
    )
    parser.add_argument(
        "--output",
        help="Output report to file (JSON format)"
    )
    parser.add_argument(
        "--model",
        default=os.environ.get("OLLAMA_MODEL", "qwen2.5-coder:14b"),
        help="Ollama model for analysis"
    )
    parser.add_argument(
        "--no-ai",
        action="store_true",
        help="Skip AI analysis, audit all tasks with implementations"
    )

    args = parser.parse_args()

    print(f"Starting self-audit for {args.roadmap}", file=sys.stderr)

    # Load ROADMAP
    roadmap_content = load_roadmap(args.roadmap)
    if not roadmap_content:
        return 1

    # Extract tasks
    tasks = extract_roadmap_tasks(roadmap_content)
    print(f"Extracted {len(tasks)} tasks from ROADMAP", file=sys.stderr)

    # Identify tasks to audit
    if args.no_ai:
        # Audit all tasks with implementations
        task_ids_to_audit = [t["task_id"] for t in tasks if t["implementation"]]
        print(f"Auditing all {len(task_ids_to_audit)} tasks with implementations", file=sys.stderr)
    else:
        # Use AI to identify suspect tasks
        suspect_task_ids = analyze_with_ollama(tasks, args.model)
        task_ids_to_audit = suspect_task_ids
        print(f"AI flagged {len(task_ids_to_audit)} suspect tasks", file=sys.stderr)

    # Run audits
    audit_results = audit_tasks(tasks, task_ids_to_audit)

    # Generate report
    report = generate_report(tasks, audit_results, task_ids_to_audit)

    # Output report
    if args.output:
        with open(args.output, "w") as f:
            json.dump(report, f, indent=2)
        print(f"Report written to {args.output}", file=sys.stderr)
    else:
        print(json.dumps(report, indent=2))

    # Summary
    print(f"\nAudit complete:", file=sys.stderr)
    print(f"  Total tasks: {report['total_tasks']}", file=sys.stderr)
    print(f"  Audited: {report['audited_tasks']}", file=sys.stderr)
    print(f"  Passed: {len(report['summary']['passed'])}", file=sys.stderr)
    print(f"  Failed: {report['failed_audits']}", file=sys.stderr)
    print(f"  Warnings: {len(report['summary']['warnings'])}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())