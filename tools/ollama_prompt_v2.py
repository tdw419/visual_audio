#!/usr/bin/env python3
"""
Ollama-based prompt utilities for autonomous agent operations.

This module provides:
- Prompt templates for Ollama LLM analysis
- Container audit functionality that uses Ollama to self-analyze ROADMAP
- Autonomous verification of claimed task completion
- Contextual memory system for conversation history tracking

Key functions:
- prompt_ollama(): Send structured prompts to Ollama and get responses
- run_audit(): Autonomous audit loop that analyzes ROADMAP, verifies claims
- parse_roadmap_tasks(): Parse ROADMAP.md to extract task metadata
- verify_file_exists(): Check if files mentioned in receipts exist
- verify_test_exists(): Check if test files exist

Contextual Memory:
- ConversationHistory: Track prompt/response pairs per session
- get_context_prompt(): Retrieve relevant history for new prompts
- clear_history(): Clear session history
- list_sessions(): List all active sessions

The audit loop runs autonomously:
1. Parses ROADMAP.md for all COMPLETE tasks
2. Extracts receipts (file paths, implementation claims)
3. Verifies each receipt by checking file existence
4. Flags suspect tasks (COMPLETE but missing implementation)
5. Generates JSON report with detailed findings
6. Can run periodically via cron or daemon
"""

import fcntl
import json
import os
import re
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any


# ============================================================================
# CONTEXTUAL MEMORY SYSTEM
# ============================================================================

class ConversationHistory:
    """
    Manages conversation history for Ollama interactions.
    
    Tracks prompt/response pairs per session with persistence to disk.
    Enables container self-awareness by maintaining query history across sessions.
    Thread-safe for concurrent access.
    """
    
    def __init__(self, history_path: Optional[str] = None, max_exchanges: int = 10):
        """
        Initialize conversation history manager.
        
        Args:
            history_path: Path to JSON file for persistent storage.
                          Defaults to ~/.visual_audio/ollama_history.json
            max_exchanges: Maximum number of exchanges to keep per session (default: 10)
        """
        if history_path is None:
            # Default path: ~/.visual_audio/ollama_history.json
            home_dir = Path.home()
            history_dir = home_dir / '.visual_audio'
            history_dir.mkdir(parents=True, exist_ok=True)
            history_path = str(history_dir / 'ollama_history.json')
        
        self.history_path = history_path
        self.max_exchanges = max_exchanges
        self._lock = threading.RLock()
        self._data = self._load_history()
    
    def _load_history(self) -> Dict:
        """Load history from disk, handling missing/invalid files gracefully."""
        try:
            if os.path.exists(self.history_path):
                with open(self.history_path, 'r') as f:
                    data = json.load(f)
                    # Validate structure
                    if not isinstance(data, dict):
                        return {}
                    if not all(isinstance(v, list) for v in data.values()):
                        return {}
                    return data
        except (json.JSONDecodeError, IOError) as e:
            # Log but don't fail - start with empty history
            sys.stderr.write(f"Warning: Could not load history from {self.history_path}: {e}\n")
        
        return {}
    
    def _save_history(self) -> None:
        """Save history to disk with file locking for thread safety."""
        with self._lock:
            try:
                # Write to temporary file first, then rename for atomicity
                temp_path = self.history_path + '.tmp'
                with open(temp_path, 'w') as f:
                    fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                    json.dump(self._data, f, indent=2, default=str)
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
                
                # Atomic rename
                os.rename(temp_path, self.history_path)
            except IOError as e:
                sys.stderr.write(f"Warning: Could not save history to {self.history_path}: {e}\n")
    
    def add_exchange(
        self,
        session_id: str,
        prompt: str,
        response: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Add a prompt/response exchange to session history.
        
        Args:
            session_id: Unique session identifier (e.g., container ID, task ID)
            prompt: The prompt that was sent to Ollama
            response: The response received from Ollama
            metadata: Optional additional metadata (e.g., model, timestamp)
        """
        with self._lock:
            if session_id not in self._data:
                self._data[session_id] = []
            
            exchange = {
                'prompt': prompt,
                'response': response,
                'timestamp': datetime.now().isoformat(),
                'metadata': metadata or {}
            }
            
            self._data[session_id].append(exchange)
            
            # Trim to max_exchanges
            if len(self._data[session_id]) > self.max_exchanges:
                self._data[session_id] = self._data[session_id][-self.max_exchanges:]
            
            self._save_history()
    
    def get_exchanges(
        self,
        session_id: str,
        limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Get conversation history for a session.
        
        Args:
            session_id: Session identifier
            limit: Maximum number of exchanges to return (default: all)
        
        Returns:
            List of exchange dictionaries in chronological order
        """
        with self._lock:
            exchanges = self._data.get(session_id, [])
            if limit is not None and limit > 0:
                return exchanges[-limit:]
            return exchanges[:]
    
    def get_context_prompt(
        self,
        session_id: str,
        include_count: Optional[int] = None,
        format: str = "concise"
    ) -> str:
        """
        Generate a context prompt string from session history.
        
        Args:
            session_id: Session identifier
            include_count: Number of recent exchanges to include (default: max_exchanges)
            format: Format style: "concise" (default), "detailed", or "raw"
        
        Returns:
            Formatted context string suitable for including in prompts
        """
        if include_count is None:
            include_count = self.max_exchanges
        
        exchanges = self.get_exchanges(session_id, include_count)
        
        if not exchanges:
            return ""
        
        if format == "raw":
            # Simple concatenation
            return "\n".join([
                f"Q: {e['prompt']}\nA: {e['response']}"
                for e in exchanges
            ])
        
        elif format == "detailed":
            # Include timestamps and metadata
            lines = [f"Context from previous exchanges ({len(exchanges)} most recent):"]
            for i, e in enumerate(exchanges, 1):
                lines.append(f"\n{i}. [{e['timestamp'].split('T')[0]}]")
                lines.append(f"   Q: {e['prompt'][:200]}{'...' if len(e['prompt']) > 200 else ''}")
                lines.append(f"   A: {e['response'][:200]}{'...' if len(e['response']) > 200 else ''}")
            return "\n".join(lines)
        
        else:  # concise (default)
            # Clean, readable format
            lines = [f"Previous conversation context (last {len(exchanges)} exchanges):"]
            for e in exchanges:
                # Truncate for readability
                prompt = e['prompt'][:150] + ('...' if len(e['prompt']) > 150 else '')
                response = e['response'][:150] + ('...' if len(e['response']) > 150 else '')
                lines.append(f"- Q: {prompt}")
                lines.append(f"  A: {response}")
            return "\n".join(lines)
    
    def clear_session(self, session_id: str) -> int:
        """
        Clear all history for a specific session.
        
        Args:
            session_id: Session identifier to clear
        
        Returns:
            Number of exchanges removed
        """
        with self._lock:
            count = len(self._data.get(session_id, []))
            if session_id in self._data:
                del self._data[session_id]
                self._save_history()
            return count
    
    def clear_all(self) -> int:
        """
        Clear all session history.
        
        Returns:
            Total number of exchanges removed
        """
        with self._lock:
            total = sum(len(v) for v in self._data.values())
            self._data = {}
            self._save_history()
            return total
    
    def list_sessions(self) -> List[str]:
        """
        List all session IDs with stored history.
        
        Returns:
            List of session identifiers sorted by most recent activity
        """
        with self._lock:
            sessions = []
            for session_id, exchanges in self._data.items():
                if exchanges:
                    # Get most recent timestamp
                    last_exchange = exchanges[-1]
                    last_time = last_exchange.get('timestamp', '')
                    sessions.append((session_id, last_time))
            
            # Sort by most recent timestamp
            sessions.sort(key=lambda x: x[1], reverse=True)
            return [s[0] for s in sessions]
    
    def get_session_info(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        Get detailed information about a session.
        
        Args:
            session_id: Session identifier
        
        Returns:
            Dictionary with session stats or None if not found
        """
        with self._lock:
            exchanges = self._data.get(session_id)
            if not exchanges:
                return None
            
            return {
                'session_id': session_id,
                'exchange_count': len(exchanges),
                'first_exchange': exchanges[0].get('timestamp'),
                'last_exchange': exchanges[-1].get('timestamp'),
                'models_used': list(set(
                    e.get('metadata', {}).get('model') for e in exchanges
                    if e.get('metadata', {}).get('model')
                ))
            }


# Global instance for convenience (can be overridden by passing explicit instance)
_default_history = None


def get_default_history() -> ConversationHistory:
    """Get or create the default conversation history instance."""
    global _default_history
    if _default_history is None:
        _default_history = ConversationHistory()
    return _default_history


# ============================================================================
# OLLAMA INTERACTION FUNCTIONS (ENHANCED WITH CONTEXT)
# ============================================================================

def prompt_ollama(
    prompt: str,
    model: str = "qwen2.5-coder:14b",
    system_prompt: Optional[str] = None,
    session_id: Optional[str] = None,
    include_context: bool = False,
    context_count: Optional[int] = None,
    history: Optional[ConversationHistory] = None
) -> str:
    """
    Send a prompt to Ollama and get the response, with optional context tracking.
    
    Args:
        prompt: The prompt text to send to Ollama
        model: Ollama model to use (default: qwen2.5-coder:14b)
        system_prompt: Optional system prompt for context
        session_id: Optional session identifier for conversation history
        include_context: If True and session_id provided, include prior context
        context_count: Number of prior exchanges to include (default: max_exchanges)
        history: Optional ConversationHistory instance (uses default if not provided)
    
    Returns:
        Ollama's response as a string
    
    Raises:
        subprocess.CalledProcessError: If Ollama command fails
        RuntimeError: If Ollama times out or fails
    """
    history = history or get_default_history()
    
    # Build full prompt with context
    full_prompt_parts = []
    
    # Add system prompt if provided
    if system_prompt:
        full_prompt_parts.append(f"System: {system_prompt}")
        full_prompt_parts.append("")  # Blank line
    
    # Add conversation context if requested
    if include_context and session_id:
        context = history.get_context_prompt(session_id, limit=context_count, format="concise")
        if context:
            full_prompt_parts.append(context)
            full_prompt_parts.append("")  # Blank line before new prompt
            full_prompt_parts.append("--- New question ---")
    
    # Add the current prompt
    full_prompt_parts.append(prompt)
    
    full_prompt = "\n".join(full_prompt_parts)
    
    try:
        result = subprocess.run(
            ["ollama", "run", model],
            input=full_prompt,
            capture_output=True,
            text=True,
            check=True,
            timeout=300  # 5 minute timeout
        )
        
        response = result.stdout
        
        # Store in history if session_id provided
        if session_id:
            history.add_exchange(
                session_id,
                prompt,
                response,
                metadata={
                    'model': model,
                    'timestamp': datetime.now().isoformat()
                }
            )
        
        return response
    
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"Ollama timeout after 300 seconds")
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Ollama failed with exit code {e.returncode}: {e.stderr}")


def clear_history(
    session_id: Optional[str] = None,
    history: Optional[ConversationHistory] = None
) -> int:
    """
    Clear conversation history.
    
    Args:
        session_id: Specific session to clear, or None to clear all
        history: Optional ConversationHistory instance (uses default if not provided)
    
    Returns:
        Number of exchanges removed
    """
    history = history or get_default_history()
    
    if session_id:
        return history.clear_session(session_id)
    else:
        return history.clear_all()


def list_sessions(
    history: Optional[ConversationHistory] = None
) -> List[str]:
    """
    List all session IDs with stored history.
    
    Args:
        history: Optional ConversationHistory instance (uses default if not provided)
    
    Returns:
        List of session identifiers sorted by most recent activity
    """
    history = history or get_default_history()
    return history.list_sessions()


def get_session_info(
    session_id: str,
    history: Optional[ConversationHistory] = None
) -> Optional[Dict[str, Any]]:
    """
    Get detailed information about a session.
    
    Args:
        session_id: Session identifier
        history: Optional ConversationHistory instance (uses default if not provided)
    
    Returns:
        Dictionary with session stats or None if not found
    """
    history = history or get_default_history()
    return history.get_session_info(session_id)


# ============================================================================
# ROADMAP PARSING AND AUDIT FUNCTIONS
# ============================================================================

def parse_roadmap_tasks(roadmap_path: str) -> List[Dict]:
    """
    Parse ROADMAP.md to extract task information.

    Handles the markdown format:
    - Task lines: `- [x] **TASK_XXX**: Description`
    - Status from checkbox: `[ ]` = PENDING, `[x]` = COMPLETE
    - Metadata: `- Priority:`, `- Receipt:`, `- Test:`, etc.

    Args:
        roadmap_path: Path to ROADMAP.md file

    Returns:
        List of task dictionaries with keys:
        - id: Task ID
        - description: Task description
        - status: Task status (COMPLETE, PENDING, IN_PROGRESS, UNKNOWN)
        - priority: Task priority (CRITICAL, HIGH, MEDIUM, LOW, UNKNOWN)
        - receipts: List of receipt strings
        - test_command: Test command string
        - completed: Completion date (if COMPLETE)
    """
    try:
        with open(roadmap_path, 'r') as f:
            content = f.read()
    except FileNotFoundError:
        return []

    tasks = []
    current_task = None

    for line in content.split('\n'):
        # Task marker line: `- [x] **TASK_XXX**: Description`
        task_match = re.match(r'-\s+\[(x| )\]\s+\*\*([^*]+)\*\*:\s*(.+)', line)
        if task_match:
            # Save previous task
            if current_task:
                tasks.append(current_task)

            # Extract task info
            checkbox, task_id, description = task_match.groups()
            status = 'COMPLETE' if checkbox == 'x' else 'PENDING'

            current_task = {
                'id': task_id.strip(),
                'description': description.strip(),
                'status': status,
                'priority': 'UNKNOWN',
                'receipts': [],
                'test_command': '',
                'completed': None
            }
            continue

        # Metadata lines for current task (indented with spaces)
        if current_task and line.startswith('  - '):
            metadata_match = re.match(r'\s+-\s+(\w+):\s*(.+)', line)
            if metadata_match:
                key, value = metadata_match.groups()
                key_lower = key.lower()
                
                if key_lower == 'priority':
                    current_task['priority'] = value.strip().upper()
                elif key_lower == 'receipt':
                    current_task['receipts'].append(value.strip())
                elif key_lower == 'test':
                    current_task['test_command'] = value.strip()
                elif key_lower == 'completed':
                    current_task['completed'] = value.strip()

    # Save last task
    if current_task:
        tasks.append(current_task)

    return tasks


def verify_file_exists(project_root: str, file_path: str) -> Tuple[bool, str]:
    """
    Verify that a file exists in the project.
    
    Args:
        project_root: Root directory of the project
        file_path: Relative or absolute path to file
    
    Returns:
        Tuple of (exists, message)
    """
    if os.path.isabs(file_path):
        full_path = file_path
    else:
        full_path = os.path.join(project_root, file_path)
    
    if os.path.exists(full_path):
        return True, f"File exists: {file_path}"
    else:
        return False, f"File NOT FOUND: {file_path} (looked for {full_path})"


def verify_test_exists(project_root: str, test_path: str) -> Tuple[bool, str]:
    """
    Verify that a test file exists.
    
    Args:
        project_root: Root directory of the project
        test_path: Path to test file
    
    Returns:
        Tuple of (exists, message)
    """
    return verify_file_exists(project_root, test_path)


def run_audit(
    project_root: str,
    output_path: str = 'audit_report.json',
    model: str = 'qwen2.5-coder:14b',
    use_ollama: bool = True,
    session_id: str = 'audit_session'
) -> Dict:
    """
    Run autonomous audit of ROADMAP completion claims.
    
    Args:
        project_root: Root directory of the project
        output_path: Path to output JSON report
        model: Ollama model to use for analysis
        use_ollama: If True, use Ollama to analyze claims
        session_id: Session ID for conversation history tracking
    
    Returns:
        Dictionary with audit results
    """
    roadmap_path = os.path.join(project_root, 'ROADMAP.md')
    tasks = parse_roadmap_tasks(roadmap_path)
    
    complete_tasks = [t for t in tasks if t['status'] == 'COMPLETE']
    
    report = {
        'timestamp': datetime.now().isoformat(),
        'project_root': project_root,
        'total_tasks': len(tasks),
        'complete_tasks': len(complete_tasks),
        'suspect_tasks': 0,
        'verified_tasks': 0,
        'tasks': []
    }
    
    for task in complete_tasks:
        task_report = {
            'id': task['id'],
            'description': task['description'],
            'receipts': [],
            'test_verified': False,
            'suspect': False,
            'reasons': []
        }
        
        # Verify receipts
        all_receipts_ok = True
        for receipt in task['receipts']:
            exists, msg = verify_file_exists(project_root, receipt)
            task_report['receipts'].append({
                'path': receipt,
                'exists': exists,
                'message': msg
            })
            if not exists:
                all_receipts_ok = False
                task_report['suspect'] = True
                task_report['reasons'].append(f"Missing receipt: {receipt}")
        
        # Verify test if provided
        if task['test_command']:
            # Extract test file from command (simple heuristic)
            test_match = re.search(r'(\w+_?test\.py)', task['test_command'])
            if test_match:
                test_path = test_match.group(1)
                exists, msg = verify_test_exists(project_root, test_path)
                task_report['test_verified'] = exists
                if not exists:
                    task_report['suspect'] = True
                    task_report['reasons'].append(f"Missing test: {test_path}")
        
        # If using Ollama and task is suspect, get AI analysis
        if use_ollama and task_report['suspect']:
            try:
                analysis_prompt = f"""
Analyze this task completion claim and determine if it's legitimate:

Task: {task['id']}
Description: {task['description']}
Receipts: {task['receipts']}
Test command: {task['test_command']}
Verification results: {task_report['reasons']}

Is this task likely actually complete? Consider:
1. Could receipts be in different locations?
2. Could test files be generated dynamically?
3. Could this be a naming mismatch?
4. Is the description vague enough to interpret multiple ways?

Respond with JSON: {{"legitimate": true/false, "confidence": 0-1, "reason": "explanation"}}
"""
                response = prompt_ollama(
                    analysis_prompt,
                    model=model,
                    session_id=session_id,
                    include_context=True
                )
                
                # Try to parse JSON from response
                try:
                    analysis = json.loads(response)
                    if analysis.get('legitimate', False):
                        task_report['suspect'] = False
                        task_report['ai_analysis'] = analysis
                        report['verified_tasks'] += 1
                    else:
                        task_report['ai_analysis'] = analysis
                        report['suspect_tasks'] += 1
                except json.JSONDecodeError:
                    # If AI didn't return JSON, keep suspect status
                    task_report['ai_analysis'] = {'raw_response': response}
                    report['suspect_tasks'] += 1
                
            except Exception as e:
                task_report['ai_error'] = str(e)
                report['suspect_tasks'] += 1
        
        report['tasks'].append(task_report)
    
    report['summary'] = {
        'total': len(tasks),
        'complete': len(complete_tasks),
        'verified': report['verified_tasks'],
        'suspect': report['suspect_tasks']
    }
    
    # Write report
    with open(output_path, 'w') as f:
        json.dump(report, f, indent=2)
    
    return report


def print_audit_report(report: Dict) -> None:
    """
    Print audit report to stdout in a human-readable format.
    
    Args:
        report: Audit report dictionary
    """
    print("=" * 60)
    print(f"AUDIT REPORT - {report['timestamp']}")
    print("=" * 60)
    print(f"Project: {report['project_root']}")
    print(f"Total tasks: {report['summary']['total']}")
    print(f"Complete tasks: {report['summary']['complete']}")
    print(f"Verified: {report['summary']['verified']}")
    print(f"Suspect: {report['summary']['suspect']}")
    print("=" * 60)
    
    for task in report['tasks']:
        status_icon = "✓" if not task['suspect'] else "?"
        print(f"\n{status_icon} {task['id']}: {task['description']}")
        
        if task['suspect']:
            print(f"  ⚠ SUSPECT: {', '.join(task['reasons'])}")
            if 'ai_analysis' in task:
                print(f"  AI Analysis: {task['ai_analysis'].get('reason', 'N/A')}")
        else:
            if task['receipts']:
                print(f"  Receipts verified: {len([r for r in task['receipts'] if r['exists']])}/{len(task['receipts'])}")
            if task['test_verified']:
                print(f"  Test verified: ✓")


# ============================================================================
# CLI INTERFACE
# ============================================================================

def main():
    """Command-line interface for audit tool."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Autonomous ROADMAP audit with Ollama analysis'
    )
    parser.add_argument(
        'project_root',
        nargs='?',
        default='.',
        help='Root directory of the project (default: current directory)'
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
    parser.add_argument(
        '--session-id',
        default='audit_session',
        help='Session ID for conversation history (default: audit_session)'
    )
    parser.add_argument(
        '--clear-history',
        action='store_true',
        help='Clear conversation history before running audit'
    )
    parser.add_argument(
        '--list-sessions',
        action='store_true',
        help='List all conversation history sessions and exit'
    )
    parser.add_argument(
        '--session-info',
        metavar='SESSION_ID',
        help='Show detailed info for a specific session and exit'
    )
    
    args = parser.parse_args()
    
    # Handle history management commands
    if args.list_sessions:
        sessions = list_sessions()
        print("Active sessions:")
        for i, session_id in enumerate(sessions, 1):
            info = get_session_info(session_id)
            if info:
                print(f"  {i}. {session_id} ({info['exchange_count']} exchanges, last: {info['last_exchange']})")
        return
    
    if args.session_info:
        info = get_session_info(args.session_info)
        if info:
            print(f"Session: {info['session_id']}")
            print(f"  Exchanges: {info['exchange_count']}")
            print(f"  First: {info['first_exchange']}")
            print(f"  Last: {info['last_exchange']}")
            print(f"  Models: {', '.join(info['models_used']) or 'None'}")
        else:
            print(f"Session not found: {args.session_info}")
        return
    
    # Clear history if requested
    if args.clear_history:
        count = clear_history()
        print(f"Cleared {count} historical exchanges")
    
    # Run audit
    report = run_audit(
        args.project_root,
        args.output,
        args.model,
        use_ollama=not args.no_ollama,
        session_id=args.session_id
    )
    
    if args.print_report:
        print_audit_report(report)
    
    # Exit with error if suspect tasks found
    if report['summary']['suspect_tasks'] > 0:
        sys.exit(1)


if __name__ == '__main__':
    main()