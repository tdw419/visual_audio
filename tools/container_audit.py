#!/usr/bin/env python3
"""
container_audit.py - Automated container self-audit using Ollama

This tool runs periodic audits of the container by:
1. Analyzing ROADMAP.md for task status
2. Using Ollama to identify suspect tasks (high impact but missing code)
3. Verifying that required implementations actually exist
4. Generating an audit report stored in the container

Usage:
  python3 tools/container_audit.py --periodic
  python3 tools/container_audit.py --once
  python3 tools/container_audit.py --suspect-tasks-only
"""

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple

# Configuration
ROADMAP_PATH = Path(__file__).parent.parent / "ROADMAP.md"
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5-coder:14b")
AUDIT_DIR = Path(__file__).parent.parent / "audit_reports"
AUDIT_DIR.mkdir(exist_ok=True)


class RoadmapParser:
    """Parse ROADMAP.md and extract task information."""
    
    def __init__(self, roadmap_path: Path = ROADMAP_PATH):
        self.roadmap_path = roadmap_path
        self.tasks = []
        self.phases = {}
        
    def parse(self) -> List[Dict]:
        """Parse roadmap and return list of tasks with metadata."""
        if not self.roadmap_path.exists():
            print(f"WARNING: ROADMAP.md not found at {self.roadmap_path}")
            return []
            
        content = self.roadmap_path.read_text()
        
        current_phase = None
        current_task_id = None
        current_task_data = {}
        
        for line in content.split('\n'):
            # Phase headers
            phase_match = re.match(r'## Phase (\d+):(.+?)\s+([🔴🟡🟢⚪])(.*)', line)
            if phase_match:
                phase_num, phase_title, phase_status, phase_text = phase_match.groups()
                current_phase = {
                    'number': int(phase_num),
                    'title': phase_title.strip(),
                    'status': phase_status,
                    'blocked': 'BLOCKED' in phase_text.upper() or 'EXPLORATORY' in phase_text.upper()
                }
                self.phases[current_phase['number']] = current_phase
                
                # Finalize any pending task
                if current_task_id and current_task_data:
                    self.tasks.append(current_task_data)
                    current_task_id = None
                    current_task_data = {}
                continue
            
            # Task markers
            task_match = re.match(r'- \[(x| )\]\s+\*\*([^*]+)\*\*:\s+(.+)', line)
            if task_match:
                # Finalize previous task
                if current_task_id and current_task_data:
                    self.tasks.append(current_task_data)
                
                status, task_id, description = task_match.groups()
                
                # Skip if phase is blocked
                if current_phase and current_phase.get('blocked', False):
                    current_task_id = None
                    current_task_data = {}
                    continue
                
                current_task_id = task_id
                current_task_data = {
                    'id': task_id,
                    'title': f"{task_id}: {description}",
                    'description': description,
                    'status': 'COMPLETE' if status == 'x' else 'PENDING',
                    'phase': current_phase,
                    'priority': 'MEDIUM',
                    'dependencies': [],
                    'test_command': None,
                    'receipt_criteria': None,
                    'files_verified': None,
                    'code_exists': None
                }
                continue
            
            # Task metadata
            if current_task_id and current_task_data:
                if 'Priority:' in line:
                    match = re.search(r'Priority:\s+(\w+)', line)
                    if match:
                        current_task_data['priority'] = match.group(1)
                elif 'Dependencies:' in line:
                    match = re.search(r'Dependencies:\s*(.+)', line)
                    if match:
                        deps = match.group(1)
                        if deps != 'None':
                            current_task_data['dependencies'] = [d.strip() for d in deps.split(',')]
                elif 'Test:' in line:
                    match = re.search(r'Test:\s*(.+)', line)
                    if match:
                        current_task_data['test_command'] = match.group(1).strip()
                elif 'Receipt:' in line:
                    match = re.search(r'Receipt:\s*(.+)', line)
                    if match:
                        current_task_data['receipt_criteria'] = match.group(1).strip()
        
        # Finalize last task
        if current_task_id and current_task_data:
            self.tasks.append(current_task_data)
        
        return self.tasks


class CodeVerifier:
    """Verify that task implementations exist."""
    
    def __init__(self, project_root: Optional[Path] = None):
        self.project_root = project_root or Path(__file__).parent.parent
        
    def verify_task(self, task: Dict) -> Dict:
        """Verify that implementation files exist for a task."""
        task_id = task['id']
        description = task['description'].lower()
        test_command = task.get('test_command', '')
        receipt_criteria = task.get('receipt_criteria', '')
        
        results = {
            'task_id': task_id,
            'files_found': [],
            'files_missing': [],
            'test_exists': False,
            'test_passing': None,
            'implementation_status': 'UNKNOWN'
        }
        
        # Check for test file from test_command
        if test_command:
            test_match = re.search(r'tests/([a-zA-Z0-9_]+\.py)', test_command)
            if test_match:
                test_file = self.project_root / 'tests' / test_match.group(1)
                if test_file.exists():
                    results['test_exists'] = True
                    results['files_found'].append(str(test_file))
                    results['test_passing'] = self._run_test(test_file)
                else:
                    results['files_missing'].append(str(test_file))
        
        # Check for implementation files based on task description
        implementation_files = self._extract_implementation_paths(task_id, description, receipt_criteria)
        
        for file_path in implementation_files:
            full_path = self.project_root / file_path
            if full_path.exists():
                results['files_found'].append(str(file_path))
            else:
                results['files_missing'].append(str(file_path))
        
        # Determine implementation status
        if results['files_missing']:
            if results['files_found']:
                results['implementation_status'] = 'PARTIAL'
            else:
                results['implementation_status'] = 'MISSING'
        elif results['files_found']:
            results['implementation_status'] = 'PRESENT'
        
        task['files_verified'] = results
        task['code_exists'] = results['implementation_status'] == 'PRESENT'
        
        return results
    
    def _extract_implementation_paths(self, task_id: str, description: str, receipt_criteria: str) -> List[str]:
        """Extract expected file paths from task metadata."""
        paths = []
        
        # Check for tool mention
        if 'tool' in description or receipt_criteria:
            tool_match = re.search(r'tools/([a-zA-Z0-9_-]+\.py)', receipt_criteria)
            if tool_match:
                paths.append(f"tools/{tool_match.group(1)}")
        
        # Check for test mention
        if 'test' in description:
            test_name = f"test_{task_id.lower()}.py"
            paths.append(f"tests/{test_name}")
        
        # Check for module mention
        if 'module' in description:
            module_match = re.search(r'([a-z][a-z0-9_]+\.py)', receipt_criteria)
            if module_match:
                paths.append(f"tools/{module_match.group(1)}")
        
        # Generic patterns based on task ID
        if task_id.startswith('TASK_V'):
            # Video tasks might involve video tools
            paths.append(f"tools/{task_id.lower().replace('task_', '')}.py")
        elif task_id.startswith('TASK_C'):
            # Codec tasks
            paths.append(f"tools/{task_id.lower().replace('task_', '')}.py")
        
        return paths
    
    def _run_test(self, test_file: Path) -> Optional[bool]:
        """Run a test file and return success status."""
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pytest", str(test_file), "-q"],
                cwd=self.project_root,
                capture_output=True,
                text=True,
                timeout=60
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, Exception):
            return None


class OllamaAnalyzer:
    """Use Ollama to analyze tasks and identify suspect ones."""
    
    def __init__(self, model: str = OLLAMA_MODEL):
        self.model = model
        self.ollama_prompt_path = Path(__file__).parent / "ollama_prompt.py"
        
    def analyze_tasks(self, tasks: List[Dict]) -> List[Dict]:
        """Use Ollama to identify suspect tasks."""
        # Filter for high-priority pending tasks
        pending_high_priority = [
            t for t in tasks 
            if t['status'] == 'PENDING' and t['priority'] in ('CRITICAL', 'HIGH')
        ]
        
        if not pending_high_priority:
            return []
        
        # Build prompt for Ollama
        task_summary = self._build_task_summary(pending_high_priority)
        
        prompt = f"""Analyze these pending high-priority tasks from the Visual Audio ROADMAP and identify which ones are "suspect" - tasks that are:
1. Marked as high priority or critical
2. Have been pending for a long time
3. May be missing implementation code
4. Have unclear or untestable receipt criteria

Here are the tasks:
{task_summary}

Return a JSON list of task IDs that should be flagged as suspect, with a brief reason for each:
[
  {{"task_id": "TASK_XXX", "reason": "why this task is suspect"}}
]

Return ONLY valid JSON, no other text."""
        
        # Call Ollama via ollama_prompt.py
        try:
            result = subprocess.run(
                [sys.executable, str(self.ollama_prompt_path), 
                 "--prompt", prompt,
                 "--model", self.model,
                 "--print"],
                cwd=Path(__file__).parent.parent,
                capture_output=True,
                text=True,
                timeout=300
            )
            
            if result.returncode != 0:
                print(f"WARNING: Ollama analysis failed: {result.stderr}")
                return []
            
            # Parse JSON response
            response_text = result.stdout.strip()
            
            # Extract JSON from response (handle potential markdown code blocks)
            json_match = re.search(r'\[.*\]', response_text, re.DOTALL)
            if json_match:
                response_text = json_match.group(0)
            
            suspect_tasks = json.loads(response_text)
            
            # Mark suspect tasks
            suspect_dict = {item['task_id']: item['reason'] for item in suspect_tasks}
            for task in pending_high_priority:
                if task['id'] in suspect_dict:
                    task['suspect'] = True
                    task['suspect_reason'] = suspect_dict[task['id']]
                else:
                    task['suspect'] = False
                    task['suspect_reason'] = None
            
            return pending_high_priority
            
        except (json.JSONDecodeError, subprocess.TimeoutExpired, Exception) as e:
            print(f"WARNING: Failed to analyze tasks with Ollama: {e}")
            return []
    
    def _build_task_summary(self, tasks: List[Dict]) -> str:
        """Build a summary of tasks for analysis."""
        lines = []
        for task in tasks:
            lines.append(f"ID: {task['id']}")
            lines.append(f"  Description: {task['description']}")
            lines.append(f"  Priority: {task['priority']}")
            lines.append(f"  Phase: {task.get('phase', {}).get('title', 'Unknown')}")
            lines.append(f"  Dependencies: {task.get('dependencies', [])}")
            lines.append(f"  Test: {task.get('test_command', 'None')}")
            lines.append(f"  Receipt: {task.get('receipt_criteria', 'None')[:100]}...")
            lines.append()
        
        return "\n".join(lines)


class ContainerAuditor:
    """Main auditor that orchestrates the audit process."""
    
    def __init__(self):
        self.parser = RoadmapParser()
        self.verifier = CodeVerifier()
        self.analyzer = OllamaAnalyzer()
        
    def run_audit(self, suspect_only: bool = False) -> Dict:
        """Run a full container audit."""
        print(f"Starting container audit at {datetime.now().isoformat()}")
        
        # Parse roadmap
        print("Parsing ROADMAP.md...")
        tasks = self.parser.parse()
        print(f"  Found {len(tasks)} tasks")
        
        # Verify code exists for pending tasks
        pending_tasks = [t for t in tasks if t['status'] == 'PENDING']
        print(f"\nVerifying code for {len(pending_tasks)} pending tasks...")
        
        for task in pending_tasks:
            self.verifier.verify_task(task)
        
        # Use Ollama to identify suspect tasks
        if not suspect_only:
            print(f"\nRunning Ollama analysis for high-priority tasks...")
            suspect_tasks = self.analyzer.analyze_tasks(tasks)
            print(f"  Identified {len(suspect_tasks)} suspect tasks")
        else:
            print(f"\nSkipping Ollama analysis (suspect-only mode)")
            suspect_tasks = []
        
        # Generate audit report
        report = self._generate_report(tasks, suspect_tasks)
        
        # Save report
        report_path = AUDIT_DIR / f"audit_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        report_path.write_text(json.dumps(report, indent=2))
        print(f"\nAudit report saved to {report_path}")
        
        # Print summary
        self._print_summary(report)
        
        return report
    
    def _generate_report(self, tasks: List[Dict], suspect_tasks: List[Dict]) -> Dict:
        """Generate audit report."""
        pending_tasks = [t for t in tasks if t['status'] == 'PENDING']
        
        # Count by implementation status
        impl_status_counts = {}
        for task in pending_tasks:
            status = task.get('files_verified', {}).get('implementation_status', 'UNKNOWN')
            impl_status_counts[status] = impl_status_counts.get(status, 0) + 1
        
        # Identify tasks with missing implementations
        missing_implementation = [
            t for t in pending_tasks
            if t.get('files_verified', {}).get('implementation_status') == 'MISSING'
        ]
        
        # Identify suspect tasks
        suspect_tasks_list = [
            t for t in pending_tasks
            if t.get('suspect', False)
        ]
        
        return {
            'timestamp': datetime.now().isoformat(),
            'summary': {
                'total_tasks': len(tasks),
                'pending_tasks': len(pending_tasks),
                'suspect_tasks': len(suspect_tasks_list),
                'missing_implementation': len(missing_implementation),
                'implementation_status_breakdown': impl_status_counts
            },
            'suspect_tasks': suspect_tasks_list,
            'missing_implementation': missing_implementation,
            'all_pending_tasks': pending_tasks
        }
    
    def _print_summary(self, report: Dict):
        """Print audit summary."""
        print("\n" + "="*60)
        print("AUDIT SUMMARY")
        print("="*60)
        
        summary = report['summary']
        print(f"Total tasks: {summary['total_tasks']}")
        print(f"Pending tasks: {summary['pending_tasks']}")
        print(f"Suspect tasks: {summary['suspect_tasks']}")
        print(f"Missing implementation: {summary['missing_implementation']}")
        print(f"\nImplementation status breakdown:")
        for status, count in summary['implementation_status_breakdown'].items():
            print(f"  {status}: {count}")
        
        if report['suspect_tasks']:
            print("\nSUSPECT TASKS:")
            for task in report['suspect_tasks'][:10]:  # Show first 10
                print(f"  - {task['id']}: {task.get('suspect_reason', 'Unknown')}")
            if len(report['suspect_tasks']) > 10:
                print(f"  ... and {len(report['suspect_tasks']) - 10} more")
        
        if report['missing_implementation']:
            print("\nTASKS WITH MISSING IMPLEMENTATION:")
            for task in report['missing_implementation'][:10]:
                missing = task.get('files_verified', {}).get('files_missing', [])
                print(f"  - {task['id']}: Missing {len(missing)} files")
            if len(report['missing_implementation']) > 10:
                print(f"  ... and {len(report['missing_implementation']) - 10} more")


def main():
    parser = argparse.ArgumentParser(description="Automated container self-audit")
    parser.add_argument("--once", action="store_true", help="Run audit once and exit")
    parser.add_argument("--periodic", action="store_true", help="Run periodic audits")
    parser.add_argument("--suspect-tasks-only", action="store_true", 
                        help="Only check for existing missing implementations, skip Ollama analysis")
    parser.add_argument("--interval", type=int, default=3600, 
                        help="Audit interval in seconds (default: 3600 = 1 hour)")
    parser.add_argument("--json", action="store_true", help="Output report as JSON")
    
    args = parser.parse_args()
    
    auditor = ContainerAuditor()
    
    if args.once or args.suspect_tasks_only:
        report = auditor.run_audit(suspect_only=args.suspect_tasks_only)
        
        if args.json:
            print(json.dumps(report, indent=2))
        
        return 0
    
    elif args.periodic:
        print(f"Starting periodic audits (interval: {args.interval}s)")
        print("Press Ctrl+C to stop\n")
        
        try:
            while True:
                auditor.run_audit()
                print(f"\nNext audit in {args.interval} seconds...")
                import time
                time.sleep(args.interval)
        except KeyboardInterrupt:
            print("\nAudit loop stopped")
            return 0
    
    else:
        parser.error("Must specify --once, --periodic, or --suspect-tasks-only")


if __name__ == '__main__':
    sys.exit(main())