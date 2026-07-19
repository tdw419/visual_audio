#!/usr/bin/env python3
"""
container_audit_loop.py — Automated container self-audit using Ollama

The container "thinks about itself" by:
1. Parsing ROADMAP.md to find tasks marked [x] (complete)
2. Using Ollama (via ollama_prompt.py) to identify suspect tasks
3. Verifying suspect tasks by checking test/implementation files exist
4. Storing analysis and verification results in the container

Usage (from container):
  python3 tools/container_audit_loop.py [--dry-run] [--container visual_audio.mkv]

Usage (from host with VA_CONTAINER env):
  VA_CONTAINER=visual_audio.mkv python3 tools/container_audit_loop.py
"""

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

# Default models (configurable via --model)
DEFAULT_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5-coder:14b")
FALLBACK_MODELS = ["qwen2.5-coder:latest", "phi3:latest"]

# Maximum number of tasks to include in Ollama prompt (prevent context overflow)
MAX_TASKS_IN_PROMPT = 50


def get_container_path():
    """Get container path from VA_CONTAINER env var or args."""
    container = os.environ.get("VA_CONTAINER")
    if not container:
        return None
    return container


def parse_complete_tasks(roadmap_path):
    """
    Parse ROADMAP.md to extract tasks marked as complete ([x]).

    Returns list of dicts with keys:
    - task_id: e.g., "TASK_W002"
    - description: task description text
    - test_command: test command if present
    - receipt_criteria: receipt criteria if present
    - status: current status field if present
    """
    tasks = []
    
    if not os.path.exists(roadmap_path):
        print(f"ERROR: ROADMAP.md not found at {roadmap_path}", file=sys.stderr)
        return tasks
    
    with open(roadmap_path, 'r') as f:
        content = f.read()
    
    # Parse line by line for better control
    lines = content.split('\n')
    i = 0
    
    while i < len(lines):
        line = lines[i]
        
        # Check for complete task: - [x] **TASK_ID**: Description
        # Also allow variations: * [x] or [x] without bold
        task_match = re.match(r'^[\s\-\*]*\s+\[x\]\s+\*\*(TASK_[A-Z0-9]+)\*\*:\s*(.+)', line)
        if not task_match:
            # Try alternative pattern without bold
            task_match = re.match(r'^[\s\-\*]*\s+\[x\]\s+(TASK_[A-Z0-9]+):\s*(.+)', line)
        
        if task_match:
            task_id = task_match.group(1)
            description = task_match.group(2).strip()
            
            task = {
                'task_id': task_id,
                'description': description,
                'test_command': '',
                'receipt_criteria': '',
                'status': ''
            }
            
            # Look ahead for task details (indented lines starting with -)
            j = i + 1
            while j < len(lines):
                detail_line = lines[j]
                
                # Stop when we reach a non-indented line or a new task
                if detail_line.strip() and not re.match(r'^\s{2,}-', detail_line):
                    # Check if this is a new task line
                    if re.match(r'^[\s\-\*]*\s+\[[x\s]\]\s+\*?\*?TASK_', detail_line):
                        break
                    # Stop at any other non-empty line at lower indentation
                    if not detail_line.startswith(' ' * 2):
                        break
                
                # Parse detail fields
                test_match = re.search(r'Test:\s*`(.+?)`', detail_line)
                if test_match:
                    task['test_command'] = test_match.group(1)
                
                receipt_match = re.search(r'Receipt:\s*(.+)', detail_line)
                if receipt_match:
                    task['receipt_criteria'] = receipt_match.group(1).strip()
                
                status_match = re.search(r'Status:\s*(.+)', detail_line)
                if status_match:
                    task['status'] = status_match.group(1).strip()
                
                j += 1
            
            tasks.append(task)
        
        i += 1
    
    return tasks


def build_audit_prompt(complete_tasks):
    """
    Build prompt for Ollama to identify suspect tasks.

    Suspect tasks are those marked complete but potentially lacking verification:
    - No test command specified
    - Test file doesn't exist (Ollama can't check, but can flag)
    - Receipt criteria are vague or missing
    - Status suggests incomplete work
    """
    # Limit tasks to prevent context overflow
    tasks_to_audit = complete_tasks[:MAX_TASKS_IN_PROMPT]
    
    prompt = """You are auditing a Visual Audio project ROADMAP.md to identify "suspect tasks" - tasks marked complete ([x]) but potentially lacking proper verification.

ANALYZE EACH COMPLETE TASK AND IDENTIFY SUSPECTS:

For each task, check:
1. Test command specified? If missing, suspect.
2. Test command looks plausible? (e.g., "pytest tests/test_*.py" or "python3 tool.py") If missing/malformed, suspect.
3. Receipt criteria specific? If vague ("complete", "done"), suspect.
4. Status field suggests issues? If empty or questionable, suspect.

TASKS TO ANALYZE:

"""
    
    for task in tasks_to_audit:
        prompt += f"\n**{task['task_id']}**: {task['description']}\n"
        prompt += f"  Test command: {task['test_command'] if task['test_command'] else '[MISSING]'}\n"
        prompt += f"  Receipt: {task['receipt_criteria'][:100] if task['receipt_criteria'] else '[MISSING]'}...\n"
        status = task.get('status', '')
        prompt += f"  Status: {status[:80] if status else '[NOT SPECIFIED]'}\n"
    
    if len(complete_tasks) > MAX_TASKS_IN_PROMPT:
        prompt += f"\n[... {len(complete_tasks) - MAX_TASKS_IN_PROMPT} more tasks truncated due to context limits ...]\n"
    
    prompt += """

RESPONSE FORMAT:
Return ONLY a JSON array of suspect tasks. Each entry must have:
- task_id: exact task ID from ROADMAP (e.g., "TASK_W002")
- description: brief description of the issue
- reason: why this task is suspect (e.g., "No test command specified", "Receipt criteria too vague")
- test_command: the test command from the task (or empty string)

Example response:
```json
[
  {
    "task_id": "TASK_W002",
    "description": "Test design decision",
    "reason": "No test command specified - cannot verify completion",
    "test_command": ""
  }
]
```

If no suspect tasks found, return empty array: []
"""
    
    return prompt


def parse_llm_json_response(response):
    """
    Parse Ollama JSON response, handling markdown code blocks.

    Ollama often wraps JSON in ```json ... ``` or just ``` ... ```
    """
    if not response:
        return []
    
    # Try to extract JSON from markdown code blocks
    patterns = [
        r'```json\s*\n(.*?)\n```',  # ```json ... ```
        r'```\s*\n(.*?)\n```',       # ``` ... ```
    ]
    
    for pattern in patterns:
        match = re.search(pattern, response, re.DOTALL)
        if match:
            json_text = match.group(1)
            try:
                return json.loads(json_text)
            except json.JSONDecodeError:
                continue
    
    # Try parsing entire response as JSON
    try:
        return json.loads(response)
    except json.JSONDecodeError:
        pass
    
    return []


def check_test_file_exists(test_command, project_root):
    """
    Check if the test file specified in test_command exists.

    Returns tuple (exists: bool, path: str|None)
    """
    if not test_command:
        return False, None
    
    # Extract file path from test command
    # Patterns: "python3 -m pytest tests/test_*.py"
    #          "python3 tools/tool.py"
    #          "pytest tests/*.py"
    
    # Match pytest patterns
    pytest_match = re.search(r'(?:python3 -m )?pytest\s+(\S+)', test_command)
    if pytest_match:
        path_pattern = pytest_match.group(1)
        
        # Handle wildcards - check if any files match
        if '*' in path_pattern or '?' in path_pattern:
            from glob import glob
            matches = glob(str(project_root / path_pattern))
            return len(matches) > 0, matches[0] if matches else None
        else:
            path = project_root / path_pattern
            return path.exists(), str(path) if path.exists() else None
    
    # Match python tool patterns
    python_match = re.search(r'python3\s+(\S+)', test_command)
    if python_match:
        path = project_root / python_match.group(1)
        return path.exists(), str(path) if path.exists() else None
    
    return False, None


def check_implementation_exists(description, task_id, project_root):
    """
    Heuristically search for implementation files based on task metadata.

    Returns tuple (exists: bool, path: str|None)
    """
    # Strategy 1: Search for files named after task_id
    # e.g., TASK_A003 -> search for "audit", "container", "loop"
    
    keywords = []
    
    # Extract keywords from task_id
    if task_id:
        # TASK_A003 -> "A003" -> look for "a003" patterns
        id_part = task_id.replace('TASK_', '').lower()
        keywords.append(id_part)
    
    # Extract keywords from description
    if description:
        # Split on common delimiters, keep meaningful words
        desc_words = re.findall(r'[a-z]{3,}', description.lower())
        keywords.extend(desc_words[:5])  # Take first 5 keywords
    
    # Search in common directories
    search_dirs = [
        project_root / "tools",
        project_root / "src",
        project_root / "scripts",
        project_root,
    ]
    
    for search_dir in search_dirs:
        if not search_dir.exists():
            continue
        
        # Search for files matching keywords
        for keyword in keywords:
            # Try exact filename match
            for ext in ['.py', '.rs', '.js', '.md']:
                potential_path = search_dir / f"{keyword}{ext}"
                if potential_path.exists():
                    return True, str(potential_path)
            
            # Try substring match in filenames
            try:
                for file_path in search_dir.rglob('*.py'):
                    if keyword in file_path.name.lower():
                        return True, str(file_path)
            except (PermissionError, RecursionError):
                continue
    
    return False, None


def verify_suspect_tasks(suspect_tasks, project_root):
    """
    Verify suspect tasks by checking test and implementation files.

    Returns dict with keys:
    - timestamp: ISO timestamp of verification
    - suspect_count: number of tasks to verify
    - pass_count: number of tasks that passed verification
    - fail_count: number of tasks that failed verification
    - tasks: list of verification results for each task
    """
    results = {
        'timestamp': datetime.utcnow().isoformat() + 'Z',
        'suspect_count': len(suspect_tasks),
        'pass_count': 0,
        'fail_count': 0,
        'tasks': []
    }
    
    for task in suspect_tasks:
        task_id = task.get('task_id', 'UNKNOWN')
        description = task.get('description', '')
        
        # Check test file
        test_exists, test_path = check_test_file_exists(
            task.get('test_command', ''), project_root
        )
        
        # Check implementation file
        impl_exists, impl_path = check_implementation_exists(
            description, task_id, project_root
        )
        
        # Determine status
        # Task passes if either test OR implementation exists
        # (ideally both, but at least one)
        status = 'PASS' if (test_exists or impl_exists) else 'FAIL'
        
        task_result = {
            'task_id': task_id,
            'description': description,
            'reason': task.get('reason', ''),
            'test_command': task.get('test_command', ''),
            'test_exists': test_exists,
            'test_path': test_path,
            'impl_exists': impl_exists,
            'impl_path': impl_path,
            'status': status
        }
        
        results['tasks'].append(task_result)
        
        if status == 'PASS':
            results['pass_count'] += 1
        else:
            results['fail_count'] += 1
    
    return results


def store_analysis_in_container(container, suspect_tasks, model, dry_run=False):
    """
    Store Ollama analysis results in container.

    Returns path to stored file (or temp path if dry_run)
    """
    import tempfile
    
    timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
    entry_name = f"audit_suspect_tasks_{timestamp}.json"
    
    # Create analysis report
    report = {
        'timestamp': datetime.utcnow().isoformat() + 'Z',
        'model': model,
        'suspect_count': len(suspect_tasks),
        'tasks': suspect_tasks
    }
    
    fd, temp_path = tempfile.mkstemp(suffix='_audit_suspect.json')
    os.close(fd)
    
    with open(temp_path, 'w') as f:
        json.dump(report, f, indent=2)
    
    if dry_run:
        return f"[DRY RUN] Would store in container as {entry_name}"
    
    # Use va_container.py to store in container
    script_dir = Path(__file__).parent
    container_tool = script_dir / "va_container.py"
    
    if not container_tool.exists():
        container_tool = "tools/va_container.py"
    
    note = f"Ollama audit analysis ({model}): {len(suspect_tasks)} suspect tasks identified"
    
    result = subprocess.run(
        [sys.executable, str(container_tool), "update", container, entry_name,
         temp_path, "--note", note],
        capture_output=True, text=True
    )
    
    if result.returncode != 0:
        result = subprocess.run(
            [sys.executable, str(container_tool), "add", container, temp_path,
             "--name", entry_name, "--role", "audit", "--note", note],
            capture_output=True, text=True
        )
    
    os.unlink(temp_path)
    
    if result.returncode != 0:
        print(f"WARNING: Failed to store analysis in container: {result.stderr}", file=sys.stderr)
        return None
    
    return entry_name


def store_verification_in_container(container, verification_results, dry_run=False):
    """
    Store verification results in container.

    Returns path to stored file (or temp path if dry_run)
    """
    import tempfile
    
    timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
    entry_name = f"audit_verification_{timestamp}.json"
    
    fd, temp_path = tempfile.mkstemp(suffix='_audit_verification.json')
    os.close(fd)
    
    with open(temp_path, 'w') as f:
        json.dump(verification_results, f, indent=2)
    
    if dry_run:
        return f"[DRY RUN] Would store in container as {entry_name}"
    
    # Use va_container.py to store in container
    script_dir = Path(__file__).parent
    container_tool = script_dir / "va_container.py"
    
    if not container_tool.exists():
        container_tool = "tools/va_container.py"
    
    pass_rate = 0
    if verification_results['suspect_count'] > 0:
        pass_rate = (verification_results['pass_count'] / verification_results['suspect_count']) * 100
    
    note = f"Audit verification: {verification_results['pass_count']}/{verification_results['suspect_count']} passed ({pass_rate:.1f}%)"
    
    result = subprocess.run(
        [sys.executable, str(container_tool), "update", container, entry_name,
         temp_path, "--note", note],
        capture_output=True, text=True
    )
    
    if result.returncode != 0:
        result = subprocess.run(
            [sys.executable, str(container_tool), "add", container, temp_path,
             "--name", entry_name, "--role", "audit", "--note", note],
            capture_output=True, text=True
        )
    
    os.unlink(temp_path)
    
    if result.returncode != 0:
        print(f"WARNING: Failed to store verification in container: {result.stderr}", file=sys.stderr)
        return None
    
    return entry_name


def call_ollama_via_script(prompt, model, context_path=None):
    """
    Call Ollama using ollama_prompt.py script.

    Returns response text or None on failure.
    """
    script_dir = Path(__file__).parent
    ollama_script = script_dir / "ollama_prompt.py"
    
    if not ollama_script.exists():
        print(f"ERROR: ollama_prompt.py not found at {ollama_script}", file=sys.stderr)
        return None
    
    # Build command
    cmd = [
        sys.executable,
        str(ollama_script),
        "--prompt", prompt,
        "--model", model,
        "--print"
    ]
    
    if context_path:
        cmd.extend(["--context", context_path])
    
    # Run with timeout
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    
    if result.returncode != 0:
        print(f"ERROR: ollama_prompt.py failed: {result.stderr}", file=sys.stderr)
        return None
    
    return result.stdout


def main():
    parser = argparse.ArgumentParser(
        description="Automated container self-audit using Ollama"
    )
    parser.add_argument(
        "--container",
        help="Container path (default: VA_CONTAINER env var)"
    )
    parser.add_argument(
        "--roadmap",
        default="ROADMAP.md",
        help="Path to ROADMAP.md (default: ROADMAP.md)"
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"Ollama model (default: {DEFAULT_MODEL})"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Dry run: don't store results in container"
    )
    parser.add_argument(
        "--no-ollama",
        action="store_true",
        help="Skip Ollama analysis, just parse ROADMAP and test/impl checking"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Verbose output"
    )
    
    args = parser.parse_args()
    
    # Get container path
    container = args.container or get_container_path()
    if not container and not args.dry_run:
        print("ERROR: Container path required (set VA_CONTAINER or use --container)", file=sys.stderr)
        print("Use --dry-run to test without container", file=sys.stderr)
        return 1
    
    # Get project root (directory containing ROADMAP.md)
    roadmap_path = Path(args.roadmap).resolve()
    project_root = roadmap_path.parent
    
    if args.verbose:
        print(f"Project root: {project_root}")
        print(f"ROADMAP: {roadmap_path}")
        print(f"Container: {container if container else '[DRY RUN]'}")
    
    # Step 1: Parse complete tasks from ROADMAP
    if args.verbose:
        print("\nStep 1: Parsing complete tasks from ROADMAP.md...")
    
    complete_tasks = parse_complete_tasks(roadmap_path)
    
    if args.verbose:
        print(f"Found {len(complete_tasks)} complete tasks")
    
    if not complete_tasks:
        print("WARNING: No complete tasks found in ROADMAP.md", file=sys.stderr)
        return 0
    
    # Step 2: Build audit prompt and call Ollama
    suspect_tasks = []
    analysis_entry = None
    
    if not args.no_ollama:
        if args.verbose:
            print("\nStep 2: Building audit prompt and calling Ollama...")
        
        prompt = build_audit_prompt(complete_tasks)
        
        # Use ollama_prompt.py to call Ollama
        response = call_ollama_via_script(prompt, args.model)
        
        if not response:
            print("ERROR: Failed to get Ollama response", file=sys.stderr)
            return 1
        
        # Parse JSON response
        suspect_tasks = parse_llm_json_response(response)
        
        if args.verbose:
            print(f"Ollama identified {len(suspect_tasks)} suspect tasks")
        
        # Store analysis in container
        analysis_entry = store_analysis_in_container(
            container, suspect_tasks, args.model, args.dry_run
        )
        
        if args.verbose and analysis_entry:
            print(f"Analysis stored: {analysis_entry}")
    else:
        print("Skipping Ollama analysis (--no-ollama)")
    
    # If Ollama found no suspects or --no-ollama was used,
    # we can still do a basic sanity check on all complete tasks
    if not suspect_tasks and not args.no_ollama:
        print("No suspect tasks identified by Ollama")
    
    # Step 3: Verify suspect tasks
    if args.verbose:
        print("\nStep 3: Verifying suspect tasks...")
    
    # If no suspects from Ollama but --no-ollama, verify all complete tasks
    tasks_to_verify = suspect_tasks
    if not tasks_to_verify and args.no_ollama:
        # Convert complete_tasks to suspect_tasks format for verification
        tasks_to_verify = [
            {
                'task_id': t['task_id'],
                'description': t['description'],
                'reason': 'Full audit (--no-ollama)',
                'test_command': t['test_command']
            }
            for t in complete_tasks
        ]
    
    if not tasks_to_verify:
        print("No tasks to verify")
        return 0
    
    verification_results = verify_suspect_tasks(tasks_to_verify, project_root)
    
    if args.verbose:
        print(f"Verification: {verification_results['pass_count']}/{verification_results['suspect_count']} passed")
    
    # Step 4: Store verification results
    verification_entry = store_verification_in_container(
        container, verification_results, args.dry_run
    )
    
    if args.verbose and verification_entry:
        print(f"Verification stored: {verification_entry}")
    
    # Print summary
    print("\n" + "="*60)
    print("AUDIT SUMMARY")
    print("="*60)
    print(f"Complete tasks analyzed: {len(complete_tasks)}")
    print(f"Suspect tasks identified: {verification_results['suspect_count']}")
    print(f"Verification passed: {verification_results['pass_count']}")
    print(f"Verification failed: {verification_results['fail_count']}")
    
    if verification_results['suspect_count'] > 0:
        pass_rate = (verification_results['pass_count'] / verification_results['suspect_count']) * 100
        print(f"Pass rate: {pass_rate:.1f}%")
    
    # Print failed tasks
    if verification_results['fail_count'] > 0:
        print("\nFailed tasks (missing verification):")
        for task in verification_results['tasks']:
            if task['status'] == 'FAIL':
                print(f"  - {task['task_id']}: {task['description']}")
                print(f"    Reason: {task['reason']}")
                print(f"    Test exists: {task['test_exists']}")
                print(f"    Implementation exists: {task['impl_exists']}")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())