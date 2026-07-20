#!/usr/bin/env python3
"""
Ollama-based prompt utilities for autonomous agent operations.

This module provides:
- Prompt templates for Ollama LLM analysis
- Container audit functionality that uses Ollama to self-analyze ROADMAP
- Autonomous verification of claimed task completion

Key functions:
- prompt_ollama(): Send structured prompts to Ollama and get responses
- run_audit(): Autonomous audit loop that analyzes ROADMAP, verifies claims
- parse_roadmap_tasks(): Parse ROADMAP.md to extract task metadata
- verify_file_exists(): Check if files mentioned in receipts exist
- verify_test_exists(): Check if test files exist

The audit loop runs autonomously:
1. Parses ROADMAP.md for all COMPLETE tasks
2. Extracts receipts (file paths, implementation claims)
3. Verifies each receipt by checking file existence
4. Flags suspect tasks (COMPLETE but missing implementation)
5. Generates JSON report with detailed findings
6. Can run periodically via cron or daemon
"""

import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple


def prompt_ollama(
    prompt: str,
    model: str = "qwen2.5-coder:14b",
    system_prompt: Optional[str] = None
) -> str:
    """
    Send a prompt to Ollama and get the response.

    Args:
        prompt: The prompt text to send to Ollama
        model: Ollama model to use (default: qwen2.5-coder:14b)
        system_prompt: Optional system prompt for context

    Returns:
        Ollama's response as a string

    Raises:
        subprocess.CalledProcessError: If Ollama command fails
    """
    args = ["ollama", "run", model]
    
    if system_prompt:
        # Build prompt with system instruction
        full_prompt = f"System: {system_prompt}\n\n{prompt}"
    else:
        full_prompt = prompt
    
    try:
        result = subprocess.run(
            args,
            input=full_prompt,
            capture_output=True,
            text=True,
            check=True,
            timeout=300  # 5 minute timeout
        )
        return result.stdout
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"Ollama timeout after 300 seconds")
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Ollama failed with exit code {e.returncode}: {e.stderr}")


def parse_roadmap_tasks(roadmap_path: str) -> List[Dict]:
    """
    Parse ROADMAP.md to extract task information.

    Extracts:
    - Task IDs (e.g., TASK_001)
    - Task descriptions
    - Status (COMPLETE, PENDING, etc.)
    - Completion dates
    - Receipts (file paths, implementation claims)

    Args:
        roadmap_path: Path to ROADMAP.md file

    Returns:
        List of task dictionaries with keys:
        - id: Task ID
        - description: Task description
        - status: Task status
        - completed: Completion date (if COMPLETE)
        - receipts: List of receipt strings
    """
    tasks = []
    
    try:
        with open(roadmap_path, 'r') as f:
            content = f.read()
    except FileNotFoundError:
        return []
    
    # Split into task blocks using the *** separator
    task_blocks = re.split(r'\n\*\*\* ', content)
    
    for block in task_blocks:
        if not block.strip():
            continue
        
        # Extract task ID and description (format: "TASK_001: Description")
        id_match = re.match(r'(TASK_\w+):\s*(.+)', block)
        if not id_match:
            continue
        
        task_id = id_match.group(1)
        description = id_match.group(2).strip()
        
        # Extract status
        status_match = re.search(r'Status:\s*(\w+)', block)
        status = status_match.group(1) if status_match else 'UNKNOWN'
        
        # Extract completion date
        completed_match = re.search(r'Completed:\s*(\d{4}-\d{2}-\d{2})', block)
        completed = completed_match.group(1) if completed_match else None
        
        # Extract all Receipt lines
        receipt_matches = re.findall(r'Receipt:\s*(.+)', block)
        receipts = receipt_matches
        
        tasks.append({
            'id': task_id,
            'description': description,
            'status': status,
            'completed': completed,
            'receipts': receipts
        })
    
    return tasks


def verify_file_exists(file_path: str, project_root: str) -> bool:
    """
    Check if a file exists in the project.

    Handles both absolute and relative paths.

    Args:
        file_path: Path to check (can be relative or absolute)
        project_root: Root directory of the project

    Returns:
        True if file exists, False otherwise
    """
    # Try as absolute path first
    if Path(file_path).exists():
        return True
    
    # Try as relative path from project root
    relative_path = Path(project_root) / file_path
    if relative_path.exists():
        return True
    
    return False


def verify_test_exists(test_path: str, project_root: str) -> bool:
    """
    Check if a test file exists.

    Similar to verify_file_exists but specifically for test files.

    Args:
        test_path: Path to test file
        project_root: Root directory of the project

    Returns:
        True if test file exists, False otherwise
    """
    return verify_file_exists(test_path, project_root)


def extract_file_paths_from_receipt(receipt: str) -> List[str]:
    """
    Extract file paths from a receipt string.

    Handles various receipt formats:
    - "Created file src/main.py"
    - "Added tests/test_feature.py"
    - "Updated README.md"
    - "Implemented codec.py"

    Args:
        receipt: Receipt string from ROADMAP

    Returns:
        List of file paths found in the receipt
    """
    paths = []
    
    # Pattern 1: "Created file <path>"
    match = re.search(r'Created file\s+(\S+)', receipt)
    if match:
        paths.append(match.group(1))
    
    # Pattern 2: "Added <path>"
    match = re.search(r'Added\s+(\S+)', receipt)
    if match:
        paths.append(match.group(1))
    
    # Pattern 3: "Updated <path>"
    match = re.search(r'Updated\s+(\S+)', receipt)
    if match:
        paths.append(match.group(1))
    
    # Pattern 4: Direct path reference (e.g., "src/main.py")
    # Look for paths with common extensions
    path_match = re.search(r'[\w/]+\.(py|rs|md|json|yaml|yml|toml|txt|sh)\b', receipt)
    if path_match and path_match.group(0) not in paths:
        paths.append(path_match.group(0))
    
    # Pattern 5: "tests/test_<something>.py"
    test_match = re.search(r'tests/test_\w+\.py', receipt)
    if test_match and test_match.group(0) not in paths:
        paths.append(test_match.group(0))
    
    return paths


def analyze_task_with_ollama(task: Dict, model: str = "qwen2.5-coder:14b") -> Dict:
    """
    Use Ollama to analyze a task and assess implementation likelihood.

    This is the core "Ollama analyzes itself" functionality.
    The LLM evaluates whether a task's description and receipts
    plausibly indicate real implementation.

    Args:
        task: Task dictionary with id, description, status, receipts
        model: Ollama model to use

    Returns:
        Analysis dictionary with keys:
        - task_id: Task ID
        - description: Task description
        - receipts: Receipt list
        - ollama_assessment: LLM's assessment (likely_impl, unlikely, needs_review)
        - ollama_reasoning: LLM's reasoning text
        - suggested_files: Files LLM expects should exist
    """
    if not task['receipts']:
        return {
            'task_id': task['id'],
            'description': task['description'],
            'receipts': task['receipts'],
            'ollama_assessment': 'needs_review',
            'ollama_reasoning': 'No receipts provided - cannot verify completion',
            'suggested_files': []
        }
    
    # Build prompt for Ollama
    prompt = f"""Analyze this claimed completed task and assess whether the receipts plausibly indicate real implementation.

Task ID: {task['id']}
Task Description: {task['description']}
Receipts:
{chr(10).join(f"- {r}" for r in task['receipts'])}

Assess:
1. Do these receipts plausibly indicate the task was actually completed?
2. What specific files should exist if this task is truly done?
3. Are there any red flags or inconsistencies?

Respond in this format:
ASSESSMENT: [likely_impl | unlikely | needs_review]
REASONING: [brief explanation]
EXPECTED_FILES: [comma-separated list of expected files]
"""

    try:
        response = prompt_ollama(
            prompt,
            model,
            system_prompt="You are an autonomous code auditor. Assess task completion claims objectively."
        )
        
        # Parse response
        assessment = 'needs_review'
        reasoning = response
        expected_files = []
        
        for line in response.split('\n'):
            if line.startswith('ASSESSMENT:'):
                assessment = line.split(':', 1)[1].strip()
            elif line.startswith('REASONING:'):
                reasoning = line.split(':', 1)[1].strip()
            elif line.startswith('EXPECTED_FILES:'):
                files_str = line.split(':', 1)[1].strip()
                expected_files = [f.strip() for f in files_str.split(',') if f.strip()]
        
        return {
            'task_id': task['id'],
            'description': task['description'],
            'receipts': task['receipts'],
            'ollama_assessment': assessment,
            'ollama_reasoning': reasoning,
            'suggested_files': expected_files
        }
    
    except Exception as e:
        return {
            'task_id': task['id'],
            'description': task['description'],
            'receipts': task['receipts'],
            'ollama_assessment': 'needs_review',
            'ollama_reasoning': f'Ollama analysis failed: {e}',
            'suggested_files': []
        }


def run_audit(project_root: str, output_path: str, model: str = "qwen2.5-coder:14b", use_ollama: bool = True) -> Dict:
    """
    Run autonomous audit loop on the project.

    This is the main entry point for the container audit functionality.
    It analyzes the ROADMAP, verifies file existence, and optionally
    uses Ollama to assess implementation likelihood.

    Args:
        project_root: Root directory of the project
        output_path: Path where audit report JSON will be written
        model: Ollama model to use for analysis
        use_ollama: Whether to use Ollama for deep analysis (default: True)

    Returns:
        Audit report dictionary with keys:
        - timestamp: ISO timestamp of audit
        - project_root: Project root directory
        - summary: Statistics (total, completed, pending, suspect)
        - tasks: All tasks with verification status
        - suspect_tasks: List of tasks marked as suspect
        - error: Error message if ROADMAP not found
    """
    roadmap_path = Path(project_root) / 'ROADMAP.md'
    
    # Parse roadmap
    if not roadmap_path.exists():
        report = {
            'timestamp': datetime.now().isoformat(),
            'project_root': project_root,
            'summary': {
                'total_tasks': 0,
                'completed_tasks': 0,
                'pending_tasks': 0,
                'suspect_tasks': 0
            },
            'tasks': [],
            'suspect_tasks': [],
            'error': f'ROADMAP.md not found at {roadmap_path}'
        }
        
        # Write report even on error
        with open(output_path, 'w') as f:
            json.dump(report, f, indent=2)
        
        return report
    
    tasks = parse_roadmap_tasks(str(roadmap_path))
    
    # Analyze each task
    analyzed_tasks = []
    suspect_tasks = []
    
    for task in tasks:
        analyzed = {
            'task_id': task['id'],
            'description': task['description'],
            'status': task['status'],
            'completed': task['completed'],
            'receipts': task['receipts'],
            'is_suspect': False,
            'issues': []
        }
        
        # Skip pending tasks
        if task['status'] != 'COMPLETE':
            analyzed_tasks.append(analyzed)
            continue
        
        # Check for no receipts
        if not task['receipts']:
            analyzed['is_suspect'] = True
            analyzed['issues'].append('No receipts provided - cannot verify completion')
            suspect_tasks.append(analyzed)
            analyzed_tasks.append(analyzed)
            continue
        
        # Extract and verify file paths
        all_files = []
        for receipt in task['receipts']:
            file_paths = extract_file_paths_from_receipt(receipt)
            all_files.extend(file_paths)
        
        # Check for test files specifically
        has_test_receipt = any('test' in r.lower() for r in task['receipts'])
        test_files = [f for f in all_files if 'test' in f.lower() and f.endswith('.py')]
        
        # Verify files exist
        missing_files = []
        for file_path in all_files:
            if not verify_file_exists(file_path, project_root):
                missing_files.append(file_path)
        
        # Verify test files exist if claimed
        missing_tests = []
        if has_test_receipt:
            for test_path in test_files:
                if not verify_test_exists(test_path, project_root):
                    missing_tests.append(test_path)
        
        # Record issues
        if missing_files:
            analyzed['issues'].append(f'Missing files: {", ".join(missing_files)}')
            analyzed['missing_files'] = missing_files
        
        if missing_tests:
            analyzed['issues'].append(f'Missing test files: {", ".join(missing_tests)}')
            analyzed['missing_tests'] = missing_tests
        
        # Optional Ollama analysis
        if use_ollama:
            try:
                ollama_analysis = analyze_task_with_ollama(task, model)
                analyzed['ollama_assessment'] = ollama_analysis['ollama_assessment']
                analyzed['ollama_reasoning'] = ollama_analysis['ollama_reasoning']
                
                # If Ollama says unlikely, mark as suspect
                if ollama_analysis['ollama_assessment'] == 'unlikely':
                    analyzed['is_suspect'] = True
                    analyzed['issues'].append(f'Ollama assessment: {ollama_analysis["ollama_reasoning"]}')
                
                # Check suggested files
                for suggested in ollama_analysis['suggested_files']:
                    if not verify_file_exists(suggested, project_root):
                        if suggested not in missing_files:
                            analyzed['issues'].append(f'Ollama suggested file missing: {suggested}')
                            missing_files.append(suggested)
            except Exception as e:
                analyzed['ollama_error'] = str(e)
        
        # Mark as suspect if any issues
        if analyzed['issues']:
            analyzed['is_suspect'] = True
            suspect_tasks.append(analyzed)
        
        analyzed_tasks.append(analyzed)
    
    # Build summary
    total = len(analyzed_tasks)
    completed = sum(1 for t in analyzed_tasks if t['status'] == 'COMPLETE')
    pending = total - completed
    suspect = len(suspect_tasks)
    
    report = {
        'timestamp': datetime.now().isoformat(),
        'project_root': project_root,
        'summary': {
            'total_tasks': total,
            'completed_tasks': completed,
            'pending_tasks': pending,
            'suspect_tasks': suspect,
            'suspect_percentage': round(suspect / completed * 100, 1) if completed > 0 else 0
        },
        'tasks': analyzed_tasks,
        'suspect_tasks': suspect_tasks
    }
    
    # Write report
    with open(output_path, 'w') as f:
        json.dump(report, f, indent=2)
    
    return report


def print_audit_report(report: Dict):
    """
    Print audit report in human-readable format.

    Args:
        report: Audit report dictionary from run_audit()
    """
    print(f"\n{'='*60}")
    print(f"Container Audit Report")
    print(f"{'='*60}")
    print(f"Timestamp: {report['timestamp']}")
    print(f"Project: {report['project_root']}")
    print(f"\nSummary:")
    print(f"  Total tasks: {report['summary']['total_tasks']}")
    print(f"  Completed: {report['summary']['completed_tasks']}")
    print(f"  Pending: {report['summary']['pending_tasks']}")
    print(f"  Suspect: {report['summary']['suspect_tasks']} ({report['summary']['suspect_percentage']}%)")
    
    if report.get('error'):
        print(f"\nError: {report['error']}")
    
    if report['suspect_tasks']:
        print(f"\n{'='*60}")
        print("Suspect Tasks:")
        print(f"{'='*60}")
        for task in report['suspect_tasks']:
            print(f"\n{task['task_id']}: {task['description']}")
            for issue in task['issues']:
                print(f"  ✗ {issue}")
    else:
        print(f"\n{'='*60}")
        print("No suspect tasks found - audit passed!")
        print(f"{'='*60}")
    
    print()


def main():
    """CLI entry point for audit functionality."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Run container audit loop using Ollama analysis'
    )
    parser.add_argument(
        'project_root',
        nargs='?',
        default='.',
        help='Project root directory (default: current directory)'
    )
    parser.add_argument(
        '-o', '--output',
        default='audit_report.json',
        help='Output report path (default: audit_report.json)'
    )
    parser.add_argument(
        '-m', '--model',
        default='qwen2.5-coder:14b',
        help='Ollama model to use (default: qwen2.5-coder:14b)'
    )
    parser.add_argument(
        '--no-ollama',
        action='store_true',
        help='Skip Ollama analysis, only verify file existence'
    )
    parser.add_argument(
        '--print',
        action='store_true',
        dest='print_report',
        help='Print report to stdout'
    )
    
    args = parser.parse_args()
    
    report = run_audit(
        args.project_root,
        args.output,
        args.model,
        use_ollama=not args.no_ollama
    )
    
    if args.print_report:
        print_audit_report(report)
    
    # Exit with error if suspect tasks found
    if report['summary']['suspect_tasks'] > 0:
        sys.exit(1)


if __name__ == '__main__':
    main()