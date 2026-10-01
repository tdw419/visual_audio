#!/usr/bin/env python3
"""
container_audit_loop.py — Automated container self-audit system.

The container periodically analyzes ROADMAP.md using Ollama to identify
suspect tasks (marked complete but lacking verification or code implementations).

Usage:
  python3 tools/container_audit_loop.py --dry-run --once
  python3 tools/container_audit_loop.py --daemon --interval 3600

Requirements:
  - Ollama service running
  - VA_CONTAINER environment variable set (if in container mode)
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any


@dataclass
class Task:
    """Represents a task from ROADMAP.md."""
    id: str
    description: str
    status: str
    phase: Optional[str] = None
    test_command: Optional[str] = None
    receipt_criteria: Optional[str] = None


class ContainerAuditor:
    """
    Automated container self-audit system.

    Analyzes ROADMAP.md and identifies tasks marked as complete that may
    lack proper verification or code implementations.
    """

    def __init__(
        self,
        project_root: Optional[Path] = None,
        model: str = "qwen2.5-coder:14b",
        dry_run: bool = False,
        audit_dir: Optional[Path] = None
    ):
        """Initialize the auditor."""
        self.project_root = project_root or Path(__file__).parent.parent
        self.model = model
        self.dry_run = dry_run
        self.audit_dir = audit_dir or self.project_root / ".container_audit"
        self.roadmap_path = self.project_root / "ROADMAP.md"

        # Ensure audit directory exists
        if not self.dry_run:
            self.audit_dir.mkdir(parents=True, exist_ok=True)

    def parse_roadmap(self) -> List[Task]:
        """
        Parse ROADMAP.md and extract all tasks.

        Returns:
            List of Task objects
        """
        tasks = []
        current_phase = None

        if not self.roadmap_path.exists():
            print(f"WARNING: ROADMAP.md not found at {self.roadmap_path}")
            return tasks

        with open(self.roadmap_path) as f:
            for line in f:
                # Extract phase header
                phase_match = re.match(r"^##+\s+(.+?)\s*$", line)
                if phase_match:
                    current_phase = phase_match.group(1).strip()
                    continue

                # Extract task line - ROADMAP format: "- [x] **TASK_XXX**:" or "- [ ] **TASK_XXX**:"
                task_match = re.match(r"^\-\s+\[([xX\s])\]\s+\*\*(TASK_\w+)\*\*:\s+(.+)", line)
                if task_match:
                    status_char, task_id, description = task_match.groups()
                    status = "completed" if status_char.lower() == "x" else "pending"

                    tasks.append(Task(
                        id=task_id,
                        description=description.strip(),
                        status=status,
                        phase=current_phase
                    ))

        return tasks

    def verify_code_exists(self, task: Task) -> Dict[str, Any]:
        """
        Verify if code implementation exists for a task.

        Searches for task ID in codebase and checks for related files.

        Args:
            task: Task to verify

        Returns:
            Dict with 'found', 'files', 'evidence' keys
        """
        # Search for task ID in files
        task_id = task.id
        task_id_lower = task.id.lower()
        evidence = []

        # Direct filename matches (limit to first 5 for speed in dry-run)
        matching_files = list(self.project_root.rglob(f"*{task_id_lower}*"))[:10 if self.dry_run else 100]
        evidence.append(f"Direct filename matches: {len(matching_files)}")

        found = len(matching_files) > 0

        # Skip grep search in dry-run mode for speed
        if not self.dry_run:
            # Content search (grep-like)
            try:
                result = subprocess.run(
                    ["grep", "-r", "-l", task_id, str(self.project_root)],
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                if result.returncode == 0:
                    files_with_id = result.stdout.strip().split('\n')
                    evidence.append(f"Content references: {len(files_with_id)}")
                else:
                    evidence.append("Content references: 0")
            except (subprocess.TimeoutExpired, FileNotFoundError):
                evidence.append("Content search skipped (grep unavailable)")
        else:
            evidence.append("Content search: skipped (dry run)")

        # Check test files for task ID (limit to 5 files in dry-run)
        test_files = list(self.project_root.rglob("test_*.py"))[:5 if self.dry_run else 50]
        test_matches = []
        for test_file in test_files:
            try:
                content = test_file.read_text()
                if task_id in content:
                    test_matches.append(str(test_file.relative_to(self.project_root)))
            except Exception:
                pass
        evidence.append(f"Test file matches: {len(test_matches)}")

        found = found or len(test_matches) > 0

        return {
            "found": found,
            "files": [str(f.relative_to(self.project_root)) for f in matching_files[:10]],
            "test_files": test_matches[:10],
            "evidence": evidence
        }

    def _build_analysis_prompt(
        self,
        completed_tasks: List[Task],
        verification_results: Dict[str, Dict[str, Any]]
    ) -> str:
        """
        Build analysis prompt for Ollama.

        Args:
            completed_tasks: List of completed tasks
            verification_results: Verification results for each task

        Returns:
            Prompt string for Ollama
        """
        prompt_parts = [
            "You are analyzing a software project's ROADMAP.md to identify SUSPECT tasks.",
            "",
            "A SUSPECT task is marked as complete [X] but may be missing:",
            "  - Code implementation",
            "  - Test coverage",
            "  - Verification procedures",
            "",
            "Analyze these completed tasks and identify SUSPECT ones:",
            ""
        ]

        for task in completed_tasks:
            verification = verification_results.get(task.id, {})
            prompt_parts.append(f"\nTASK ID: {task.id}")
            prompt_parts.append(f"Description: {task.description}")
            prompt_parts.append(f"Phase: {task.phase or 'Unknown'}")

            if verification:
                prompt_parts.append(f"Files found: {verification.get('found', False)}")
                prompt_parts.append(f"Evidence: {'; '.join(verification.get('evidence', []))}")
            else:
                prompt_parts.append("Verification: NOT RUN")

        prompt_parts.extend([
            "",
            "OUTPUT FORMAT (JSON only, no extra text):",
            "{",
            '  "suspect_tasks": [',
            '    {',
            '      "task_id": "TASK_XXX",',
            '      "reason": "explanation of why this is suspect",',
            '      "severity": "HIGH|MEDIUM|LOW"',
            '    }',
            '  ],',
            '  "recommendation": "overall assessment and next steps"',
            "}"
        ])

        return "\n".join(prompt_parts)

    def call_ollama(self, prompt: str) -> Optional[str]:
        """
        Call Ollama with the analysis prompt.

        Args:
            prompt: Analysis prompt

        Returns:
            Ollama response or None if failed
        """
        try:
            result = subprocess.run(
                ["ollama", "run", self.model, prompt],
                capture_output=True,
                text=True,
                timeout=300
            )

            if result.returncode != 0:
                print(f"ERROR: Ollama call failed: {result.stderr}")
                return None

            return result.stdout
        except subprocess.TimeoutExpired:
            print("ERROR: Ollama call timed out")
            return None
        except FileNotFoundError:
            print("ERROR: Ollama not found in PATH")
            return None

    def run_audit(self) -> Dict[str, Any]:
        """
        Run the complete audit cycle.

        Returns:
            Dict with audit results
        """
        print("Starting container audit...")
        print(f"Project root: {self.project_root}")
        print(f"ROADMAP: {self.roadmap_path}")
        print(f"Model: {self.model}")
        print(f"Dry run: {self.dry_run}")

        # Parse roadmap
        print("\nParsing ROADMAP.md...")
        tasks = self.parse_roadmap()
        print(f"Found {len(tasks)} tasks")

        completed_tasks = [t for t in tasks if t.status == "completed"]
        pending_tasks = [t for t in tasks if t.status == "pending"]

        print(f"  Completed: {len(completed_tasks)}")
        print(f"  Pending: {len(pending_tasks)}")

        if not completed_tasks:
            print("\nNo completed tasks to audit")
            return {
                "timestamp": datetime.now().isoformat(),
                "model": self.model,
                "findings": [],
                "suspect_tasks": [],
                "status": "complete"
            }

        # Verify code exists for completed tasks
        print("\nVerifying code implementations...")
        verification_results = {}
        for task in completed_tasks:
            verification = self.verify_code_exists(task)
            verification_results[task.id] = verification
            found_status = "FOUND" if verification["found"] else "NOT FOUND"
            print(f"  {task.id}: {found_status}")

        # Build analysis prompt
        print("\nBuilding analysis prompt...")
        prompt = self._build_analysis_prompt(completed_tasks, verification_results)

        # Call Ollama for analysis
        print("\nAnalyzing with Ollama...")
        ollama_response = None
        suspect_tasks = []

        if not self.dry_run:
            ollama_response = self.call_ollama(prompt)

            if ollama_response:
                # Try to parse JSON response
                try:
                    analysis = json.loads(ollama_response)
                    suspect_tasks = analysis.get("suspect_tasks", [])
                except json.JSONDecodeError:
                    print("WARNING: Failed to parse Ollama JSON response")
                    # Try to extract JSON from response
                    json_match = re.search(r'\{[\s\S]*\}', ollama_response)
                    if json_match:
                        try:
                            analysis = json.loads(json_match.group())
                            suspect_tasks = analysis.get("suspect_tasks", [])
                        except json.JSONDecodeError:
                            pass
        else:
            print("(Dry run: skipping Ollama call)")
            # In dry-run mode, do basic suspect detection locally
            print("(Dry run: performing basic suspect detection locally)")
            for task in completed_tasks:
                verification = verification_results.get(task.id, {})
                if not verification.get("found", False):
                    suspect_tasks.append({
                        "task_id": task.id,
                        "reason": "No code files or tests found for this completed task",
                        "severity": "HIGH"
                    })

        # Compile audit results
        audit_result = {
            "timestamp": datetime.now().isoformat(),
            "model": self.model,
            "summary": {
                "total_tasks": len(tasks),
                "completed_tasks": len(completed_tasks),
                "pending_tasks": len(pending_tasks),
                "suspect_tasks": len(suspect_tasks)
            },
            "verifications": {
                task_id: {
                    "found": v["found"],
                    "files": v["files"],
                    "evidence": v["evidence"]
                }
                for task_id, v in verification_results.items()
            },
            "suspect_tasks": suspect_tasks,
            "ollama_response": ollama_response if ollama_response else "Skipped (dry run)",
            "status": "complete"
        }

        # Save audit log
        if not self.dry_run:
            log_file = self.audit_dir / f"audit_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            with open(log_file, "w") as f:
                json.dump(audit_result, f, indent=2)
            print(f"\nAudit log saved to: {log_file}")

        return audit_result

    def print_summary(self, audit_result: Dict[str, Any]):
        """Print audit summary to console."""
        print("\n" + "="*60)
        print("AUDIT SUMMARY")
        print("="*60)

        summary = audit_result.get("summary", {})
        print(f"Total tasks: {summary.get('total_tasks', 0)}")
        print(f"Completed: {summary.get('completed_tasks', 0)}")
        print(f"Pending: {summary.get('pending_tasks', 0)}")
        print(f"SUSPECT: {summary.get('suspect_tasks', 0)}")

        suspect_tasks = audit_result.get("suspect_tasks", [])
        if suspect_tasks:
            print("\nSUSPECT TASKS:")
            for suspect in suspect_tasks:
                print(f"  [{suspect.get('severity', 'MEDIUM')}] {suspect.get('task_id', 'Unknown')}")
                print(f"    Reason: {suspect.get('reason', 'N/A')}")
        else:
            print("\nNo suspect tasks identified")

        print("="*60)


def main():
    parser = argparse.ArgumentParser(
        description="Automated container self-audit system"
    )
    parser.add_argument(
        "--model",
        default=os.environ.get("OLLAMA_MODEL", "qwen2.5-coder:14b"),
        help="Ollama model to use"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run without calling Ollama or saving logs"
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run audit once and exit (default behavior)"
    )
    parser.add_argument(
        "--daemon",
        action="store_true",
        help="Run as daemon with periodic audits"
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=3600,
        help="Audit interval in seconds (default: 3600)"
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        help="Override project root directory"
    )
    parser.add_argument(
        "--audit-dir",
        type=Path,
        help="Override audit log directory"
    )

    args = parser.parse_args()

    # Create auditor
    auditor = ContainerAuditor(
        project_root=args.project_root,
        model=args.model,
        dry_run=args.dry_run,
        audit_dir=args.audit_dir
    )

    # Run audit
    if args.daemon:
        print(f"Starting daemon mode (interval: {args.interval}s)")
        while True:
            try:
                audit_result = auditor.run_audit()
                auditor.print_summary(audit_result)

                print(f"\nNext audit in {args.interval}s...")
                time.sleep(args.interval)
            except KeyboardInterrupt:
                print("\nDaemon stopped by user")
                break
            except Exception as e:
                print(f"ERROR: {e}")
                time.sleep(args.interval)
    else:
        # Single run
        audit_result = auditor.run_audit()
        auditor.print_summary(audit_result)

    return 0


if __name__ == "__main__":
    sys.exit(main())