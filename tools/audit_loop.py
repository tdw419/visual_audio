#!/usr/bin/env python3
"""
audit_loop.py — Automated container self-audit using Ollama.

This tool enables the container to "audit itself" by:
1. Extracting ROADMAP.md from the container
2. Analyzing tasks marked complete but potentially missing implementations
3. Using Ollama for intelligent analysis beyond pattern matching
4. Verifying code existence and non-triviality
5. Reporting suspect tasks for human review

Usage (from container):
  python3 tools/va_container.py run visual_audio.mkv tools/audit_loop.py

Usage (from host with VA_CONTAINER env):
  VA_CONTAINER=visual_audio.mkv python3 tools/audit_loop.py

The audit loop:
- Parses ROADMAP.md for completed tasks (marked ✅)
- Extracts receipt criteria and test commands
- Verifies test files exist and are non-trivial
- Uses Ollama to analyze for suspicious patterns
- Stores audit report in analysis/audit_report.md
"""

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from datetime import datetime


# Default models (configurable via --model)
DEFAULT_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5-coder:14b")
FALLBACK_MODELS = ["qwen2.5-coder:latest", "phi3:latest"]


def get_container_path():
    """Get container path from VA_CONTAINER env var."""
    container = os.environ.get("VA_CONTAINER")
    if not container:
        print("ERROR: VA_CONTAINER environment variable not set", file=sys.stderr)
        print("When using 'va_container.py run', this is set automatically.", file=sys.stderr)
        sys.exit(1)
    return container


def extract_entry(container, entry_name):
    """Extract an entry from the container to a temp file, return path."""
    import tempfile

    fd, temp_path = tempfile.mkstemp(suffix=f"_{entry_name.replace('/', '_')}")
    os.close(fd)

    # Try to extract using sibling va_container.py
    script_dir = Path(__file__).parent
    container_tool = script_dir / "va_container.py"

    if not container_tool.exists():
        # Fallback: assume tools/va_container.py is in PATH
        container_tool = "tools/va_container.py"

    result = subprocess.run(
        [sys.executable, str(container_tool), "cat", container, entry_name, "-o", temp_path],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        print(f"ERROR: Failed to extract {entry_name}", file=sys.stderr)
        print(result.stderr, file=sys.stderr)
        os.unlink(temp_path)
        return None

    return temp_path


def parse_roadmap_tasks(roadmap_content):
    """
    Parse ROADMAP.md to extract task information.

    Returns:
        dict: {
            'complete': [{'id': 'TASK_XYZ', 'description': '...', 'test': '...', 'receipt': '...'}],
            'incomplete': [{'id': 'TASK_XYZ', 'description': '...'}],
            'total': int
        }
    """
    tasks = {'complete': [], 'incomplete': [], 'total': 0}
    
    # Pattern to match task entries with multi-line details (2-space indentation)
    # Matches: - [x] **TASK_ID**: Description
    # Followed by lines starting with "  " (two spaces)
    task_pattern = re.compile(r'^- \[(x| )\] \*\*(TASK_[A-Z0-9]+)\*\*:[^\n]*\n((?:  [^\n]*\n)*)', re.MULTILINE)
    
    matches = task_pattern.findall(roadmap_content)
    
    for status, task_id, details in matches:
        tasks['total'] += 1
        is_complete = status == 'x'
        
        # Extract title/description from the task itself (not global search)
        # The task pattern matches: "- [x] **TASK_ID**: Description\n"
        # So we need to re-find just the title line for this specific task
        title_pattern = re.compile(rf'^- \[{status}\] \*\*{re.escape(task_id)}\*\*:\s*(.+)$', re.MULTILINE)
        title_match = title_pattern.search(roadmap_content)
        if not title_match:
            continue
            
        description = title_match.group(1).strip()
        
        task_info = {
            'id': task_id,
            'description': description,
            'details': details.strip(),
        }
        
        if is_complete:
            # Extract test command if present (backtick-wrapped)
            test_match = re.search(r'-\s+Test:\s*`(.+?)`', details)
            if test_match:
                task_info['test'] = test_match.group(1).strip()
            
            # Extract receipt criteria if present
            receipt_match = re.search(r'-\s+Receipt:\s*(.+?)(?=\n  -|\Z)', details, re.DOTALL)
            if receipt_match:
                task_info['receipt'] = receipt_match.group(1).strip()
            
            tasks['complete'].append(task_info)
        else:
            # Try to extract receipt for incomplete tasks too (for verification)
            receipt_match = re.search(r'-\s+Receipt:\s*(.+?)(?=\n  -|\Z)', details, re.DOTALL)
            if receipt_match:
                task_info['receipt'] = receipt_match.group(1).strip()
            tasks['incomplete'].append(task_info)
    
    return tasks


def verify_test_file_exists(test_command):
    """
    Check if test file mentioned in test command exists and is non-trivial.
    
    Returns:
        dict: {'exists': bool, 'path': str, 'lines': int, 'is_trivial': bool}
    """
    # Extract file path from test command
    # Common patterns: python3 tests/test_xxx.py, python tests/test_xxx.py
    test_match = re.search(r'python[23]?\s+(\S+\.py)', test_command)
    if not test_match:
        return {'exists': False, 'path': None, 'lines': 0, 'is_trivial': False}
    
    test_path = test_match.group(1)
    
    # Check if file exists
    if not os.path.exists(test_path):
        return {'exists': False, 'path': test_path, 'lines': 0, 'is_trivial': False}
    
    # Count lines
    try:
        with open(test_path, 'r') as f:
            lines = len(f.readlines())
    except Exception:
        lines = 0
    
    # Check if trivial (5 or fewer lines indicates a stub)
    is_trivial = lines <= 5
    
    return {
        'exists': True,
        'path': test_path,
        'lines': lines,
        'is_trivial': is_trivial
    }


def verify_implementation_exists(task_id, receipt):
    """
    Check if implementation files exist based on receipt criteria.
    
    Returns:
        dict: {'found': bool, 'files': [str], 'missing': [str]}
    """
    # Extract file paths from receipt
    # Common patterns: tools/xxx.py, tests/xxx.py, docs/xxx.md
    # Match until whitespace or punctuation (comma, period)
    file_patterns = re.findall(r'(tools/\S+?|tests/\S+?|docs/\S+?|src/\S+?)(?=[\s,.]|$)', receipt)
    
    found_files = []
    missing_files = []
    
    for file_path in file_patterns:
        if os.path.exists(file_path):
            found_files.append(file_path)
        else:
            missing_files.append(file_path)
    
    return {
        'found': len(found_files) > 0,
        'files': found_files,
        'missing_files': missing_files
    }


def call_ollama_for_audit(prompt, model=DEFAULT_MODEL):
    """Call Ollama for intelligent audit analysis."""
    
    result = subprocess.run(
        ["ollama", "run", model, prompt],
        capture_output=True,
        text=True,
        timeout=300,
    )
    
    if result.returncode != 0:
        if "model" in result.stderr.lower():
            print(f"ERROR: Model '{model}' not found or unavailable", file=sys.stderr)
            return None
        print(f"ERROR: Ollama call failed: {result.stderr}", file=sys.stderr)
        return None
    
    return result.stdout


def analyze_suspicious_patterns(tasks, model=DEFAULT_MODEL):
    """
    Use Ollama to analyze tasks for suspicious patterns indicating false completions.
    
    Returns:
        dict: {
            'suspect_task_ids': [str],
            'analysis': str,
            'confidence_scores': {task_id: float}
        }
    """
    if not tasks['complete']:
        return {
            'suspect_task_ids': [],
            'analysis': 'No completed tasks to analyze.',
            'confidence_scores': {}
        }
    
    # Build prompt for Ollama
    prompt = """You are analyzing a software development ROADMAP.md for false task completion claims.

For each task below, assess whether it's truly complete or suspicious:

TASK LIST:
"""
    
    for i, task in enumerate(tasks['complete'][:20], 1):  # Limit to 20 tasks to avoid context overflow
        prompt += f"\n{i}. TASK {task['id']}: {task['description'][:100]}...\n"
        if 'test' in task:
            prompt += f"   Test command: {task['test']}\n"
        if 'receipt' in task:
            prompt += f"   Receipt criteria: {task['receipt'][:100]}...\n"
    
    prompt += """

ANALYSIS TASKS:
1. Identify tasks that are suspicious (likely false completions)
2. For each suspicious task, provide:
   - Task ID
   - Confidence score (0.0-1.0, where 1.0 is definitely suspicious)
   - Reason for suspicion

OUTPUT FORMAT (JSON only, no explanation):
{
  "suspect_tasks": [
    {"task_id": "TASK_XYZ", "confidence": 0.85, "reason": "..."}
  ],
  "summary": "Brief summary of findings"
}
"""
    
    response = call_ollama_for_audit(prompt, model)
    
    if not response:
        # Try fallback models
        for fallback in FALLBACK_MODELS:
            print(f"Retrying with fallback model: {fallback}", file=sys.stderr)
            response = call_ollama_for_audit(prompt, fallback)
            if response:
                break
    
    if not response:
        print("WARNING: Ollama analysis failed, using pattern matching only", file=sys.stderr)
        return {
            'suspect_task_ids': [],
            'analysis': 'Ollama analysis unavailable.',
            'confidence_scores': {}
        }
    
    # Try to parse JSON from response
    try:
        # Find JSON in response (handle markdown code blocks)
        json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', response, re.DOTALL)
        if json_match:
            json_str = json_match.group(1)
        else:
            json_str = response.strip()
        
        analysis_data = json.loads(json_str)
        
        suspect_ids = []
        confidence_scores = {}
        
        for suspect in analysis_data.get('suspect_tasks', []):
            task_id = suspect.get('task_id')
            if task_id:
                suspect_ids.append(task_id)
                confidence_scores[task_id] = suspect.get('confidence', 0.5)
        
        return {
            'suspect_task_ids': suspect_ids,
            'analysis': analysis_data.get('summary', 'No summary provided'),
            'confidence_scores': confidence_scores
        }
        
    except json.JSONDecodeError as e:
        print(f"WARNING: Failed to parse Ollama JSON response: {e}", file=sys.stderr)
        print(f"Response was: {response[:200]}...", file=sys.stderr)
        return {
            'suspect_task_ids': [],
            'analysis': f'Ollama response parsing failed: {e}',
            'confidence_scores': {}
        }


def run_audit(container_path, model=DEFAULT_MODEL, use_ollama=True):
    """
    Run the complete audit loop.
    
    Returns:
        dict: Audit results with suspect tasks and verification status
    """
    print("Starting container self-audit...", file=sys.stderr)
    
    # Extract ROADMAP.md
    print("Extracting ROADMAP.md from container...", file=sys.stderr)
    roadmap_path = extract_entry(container_path, "ROADMAP.md")
    
    if not roadmap_path:
        print("ERROR: Failed to extract ROADMAP.md", file=sys.stderr)
        return {'error': 'Failed to extract ROADMAP.md'}
    
    # Parse tasks
    with open(roadmap_path, 'r') as f:
        roadmap_content = f.read()
    
    os.unlink(roadmap_path)
    
    tasks = parse_roadmap_tasks(roadmap_content)
    
    print(f"Parsed {tasks['total']} total tasks: {len(tasks['complete'])} complete, {len(tasks['incomplete'])} incomplete", file=sys.stderr)
    
    # Verify completed tasks
    suspect_tasks = []
    
    for task in tasks['complete']:
        task_id = task['id']
        verification = {
            'task_id': task_id,
            'description': task['description'][:100],
            'test_exists': False,
            'test_is_trivial': False,
            'implementation_exists': False,
            'manual_review_required': False
        }
        
        # Check test file
        if 'test' in task:
            test_info = verify_test_file_exists(task['test'])
            verification['test_exists'] = test_info['exists']
            verification['test_is_trivial'] = test_info['is_trivial']
            verification['test_path'] = test_info['path']
        
        # Check implementation
        if 'receipt' in task:
            impl_info = verify_implementation_exists(task_id, task['receipt'])
            verification['implementation_exists'] = impl_info['found']
            verification['impl_files'] = impl_info['files']
            verification['missing_files'] = impl_info['missing']
        
        # Flag as suspect if missing tests or implementation
        if not verification['test_exists'] or not verification['implementation_exists']:
            verification['manual_review_required'] = True
            suspect_tasks.append(verification)
    
    # Ollama analysis for deeper inspection
    ollama_analysis = None
    if use_ollama:
        print("Running Ollama analysis...", file=sys.stderr)
        ollama_analysis = analyze_suspicious_patterns(tasks, model)
        
        # Cross-reference Ollama findings with verification
        ollama_suspect_ids = set(ollama_analysis.get('suspect_task_ids', []))
        
        for task_verification in suspect_tasks:
            if task_verification['task_id'] in ollama_suspect_ids:
                task_verification['ollama_suspicion'] = True
                task_verification['ollama_confidence'] = ollama_analysis['confidence_scores'].get(
                    task_verification['task_id'], 0.0
                )
    
    print(f"Audit complete: {len(suspect_tasks)} suspect tasks identified", file=sys.stderr)
    
    return {
        'timestamp': datetime.now().isoformat(),
        'total_tasks': tasks['total'],
        'complete_tasks': len(tasks['complete']),
        'incomplete_tasks': len(tasks['incomplete']),
        'suspect_tasks': suspect_tasks,
        'ollama_analysis': ollama_analysis,
        'suspect_count': len(suspect_tasks)
    }


def generate_audit_report(audit_results):
    """Generate a human-readable audit report."""
    report = f"""# Container Self-Audit Report
**Generated:** {audit_results['timestamp']}

## Summary

| Metric | Count |
|--------|-------|
| Total Tasks | {audit_results['total_tasks']} |
| Complete Tasks | {audit_results['complete_tasks']} |
| Incomplete Tasks | {audit_results['incomplete_tasks']} |
| **Suspect Tasks** | **{audit_results['suspect_count']}** |

## Suspect Tasks (Manual Review Required)

"""
    
    if not audit_results['suspect_tasks']:
        report += "*No suspect tasks found. All completed tasks verified.*\n\n"
    else:
        for i, task in enumerate(audit_results['suspect_tasks'], 1):
            report += f"### {i}. {task['task_id']}\n\n"
            report += f"**Description:** {task['description']}\n\n"
            
            report += "**Verification Status:**\n\n"
            report += f"- Test file exists: {task.get('test_exists', False)} ✅❌\n"
            if 'test_path' in task:
                report += f"  - Path: {task['test_path']}\n"
            if 'test_is_trivial' in task:
                report += f"  - Is trivial: {task['test_is_trivial']} ⚠️\n"
            
            report += f"- Implementation exists: {task.get('implementation_exists', False)} ✅❌\n"
            if 'impl_files' in task:
                report += f"  - Found: {', '.join(task['impl_files']) or 'None'}\n"
            if 'missing_files' in task:
                report += f"  - Missing: {', '.join(task['missing_files']) or 'None'}\n"
            
            if task.get('ollama_suspicion'):
                report += f"- **Ollama Suspicion:** Yes (confidence: {task['ollama_confidence']:.2f}) 🤖\n"
            
            report += "\n---\n\n"
    
    # Ollama analysis section
    if audit_results.get('ollama_analysis'):
        ollama = audit_results['ollama_analysis']
        report += "## Ollama Analysis\n\n"
        report += f"**Summary:** {ollama.get('analysis', 'No analysis available')}\n\n"
        
        if ollama.get('suspect_task_ids'):
            report += "**Ollama-flagged tasks:**\n\n"
            for task_id in ollama['suspect_task_ids']:
                confidence = ollama['confidence_scores'].get(task_id, 0.0)
                report += f"- {task_id} (confidence: {confidence:.2f})\n"
            report += "\n"
    
    report += "## Recommendations\n\n"
    
    if audit_results['suspect_count'] == 0:
        report += "✅ All completed tasks have been verified. No action required.\n\n"
    else:
        report += f"⚠️ {audit_results['suspect_count']} tasks require manual review.\n\n"
        report += "Actions:\n"
        report += "1. Review each suspect task's implementation\n"
        report += "2. Verify test files are comprehensive (not just stubs)\n"
        report += "3. Update ROADMAP.md status if tasks are actually incomplete\n"
        report += "4. Run tests to verify claims: `python3 -m pytest tests/ -q`\n\n"
    
    report += "---\n\n"
    report += "*This report was generated automatically by tools/audit_loop.py*\n"
    
    return report


def main():
    parser = argparse.ArgumentParser(
        description="Automated container self-audit using Ollama"
    )
    parser.add_argument(
        "--model", default=DEFAULT_MODEL, help=f"Ollama model (default: {DEFAULT_MODEL})"
    )
    parser.add_argument(
        "--no-ollama", action="store_true", help="Skip Ollama analysis, use pattern matching only"
    )
    parser.add_argument(
        "--output", help="Output file for audit report (default: analysis/audit_report.md)"
    )
    parser.add_argument(
        "--json", action="store_true", help="Output results as JSON instead of human-readable report"
    )
    
    args = parser.parse_args()
    
    # Get container path
    container = get_container_path()
    print(f"Container: {container}", file=sys.stderr)
    
    # Run audit
    audit_results = run_audit(
        container,
        model=args.model,
        use_ollama=not args.no_ollama
    )
    
    if 'error' in audit_results:
        print(f"ERROR: {audit_results['error']}", file=sys.stderr)
        return 1
    
    # Generate output
    if args.json:
        print(json.dumps(audit_results, indent=2))
    else:
        report = generate_audit_report(audit_results)
        print(report)
        
        # Store report in container if --output specified
        if args.output:
            import tempfile
            fd, temp_path = tempfile.mkstemp(suffix="_audit_report.md")
            os.close(fd)
            
            with open(temp_path, 'w') as f:
                f.write(report)
            
            # Upsert into container
            script_dir = Path(__file__).parent
            container_tool = script_dir / "va_container.py"
            note = f"Audit report - {audit_results['suspect_count']} suspect tasks"
            
            result = subprocess.run(
                [sys.executable, str(container_tool), "update", container, args.output,
                 temp_path, "--note", note],
                capture_output=True, text=True,
            )
            if result.returncode != 0:
                result = subprocess.run(
                    [sys.executable, str(container_tool), "add", container, temp_path,
                     "--name", args.output, "--role", "analysis", "--note", note],
                    capture_output=True, text=True,
                )
            
            os.unlink(temp_path)
            
            if result.returncode == 0:
                print(f"Report stored in container: {args.output}", file=sys.stderr)
            else:
                print(f"WARNING: Failed to store report in container", file=sys.stderr)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())