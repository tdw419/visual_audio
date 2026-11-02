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
import os
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
            metadata = line[4:].strip()

            # Priority
            priority_match = re.match(r'Priority:\s*(\w+)', metadata)
            if priority_match:
                current_task['priority'] = priority_match.group(1)
                continue

            # Receipt
            receipt_match = re.match(r'Receipt:\s*(.+)', metadata)
            if receipt_match:
                current_task['receipts'].append(receipt_match.group(1).strip())
                continue

            # Test
            test_match = re.match(r'Test:\s*(.+)', metadata)
            if test_match:
                current_task['test_command'] = test_match.group(1).strip()
                continue

            # Status
            status_match = re.match(r'Status:\s*(.+)', metadata)
            if status_match:
                status_str = status_match.group(1).strip().upper()
                # Map various status strings to standard ones
                if 'COMPLETE' in status_str or '✅' in status_str:
                    current_task['status'] = 'COMPLETE'
                elif 'PENDING' in status_str or 'NOT STARTED' in status_str:
                    current_task['status'] = 'PENDING'
                elif 'IN PROGRESS' in status_str or '🟡' in status_str:
                    current_task['status'] = 'IN_PROGRESS'
                continue

            # Completion date
            completed_match = re.search(r'(\d{4}-\d{2}-\d{2})', metadata)
            if completed_match and current_task['status'] == 'COMPLETE':
                current_task['completed'] = completed_match.group(1)

    # Save last task
    if current_task:
        tasks.append(current_task)

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


class ContextualOllamaPrompter:
    """
    Context-aware Ollama prompter with container-specific memory.
    
    This class provides container self-awareness by maintaining separate
    conversation histories for each container. It enables context persistence
    across queries and sessions, allowing containers to remember their
    previous interactions and maintain awareness of their own state.
    
    Key features:
    - Container-isolated conversation histories
    - Automatic context persistence to disk
    - Context formatting for Ollama prompts
    - Configurable history limits and auto-persistence
    - Metadata tracking (container_id, timestamps)
    
    Example usage:
        prompter = ContextualOllamaPrompter(container_id="my_container")
        prompter.track_context("user", "What is the capital of France?")
        response = prompter.query_ollama("Please answer.")
        # Context persists automatically
        followup = prompter.query_ollama("And what about Germany?")
    """
    
    def __init__(
        self,
        container_id: str,
        context_dir: Optional[str] = None,
        auto_persist: bool = True,
        max_history: Optional[int] = None,
        max_tokens: int = 4096
    ):
        """
        Initialize contextual prompter for a specific container.
        
        Args:
            container_id: Unique identifier for this container
            context_dir: Directory to store context files (default: ~/.hermes/container_context/)
            auto_persist: Whether to automatically save context after each update
            max_history: Maximum number of messages to keep (None = no limit)
            max_tokens: Maximum tokens to keep in context (default: 4096)
        """
        self.container_id = container_id or "default"
        
        # Set up context directory
        if context_dir is None:
            context_dir = os.path.expanduser("~/.hermes/container_context")
        self.context_dir = Path(context_dir)
        self.context_dir.mkdir(parents=True, exist_ok=True)
        
        # Configuration
        self.auto_persist = auto_persist
        self.max_history = max_history
        
        # Initialize conversation memory with container metadata
        metadata = {
            'container_id': self.container_id,
            'created_at': datetime.now().isoformat()
        }
        self.memory = ConversationMemory(max_tokens=max_tokens, metadata=metadata)
        
        # Try to load existing context
        self.load_context()
    
    def track_context(self, role: str, content: str):
        """
        Track a message in the conversation history.
        
        Args:
            role: Message role (user, assistant, system)
            content: Message content
        """
        # Add to memory
        self.memory.add_message(role, content)
        
        # Enforce max_history limit if set
        if self.max_history is not None:
            history = self.memory.get_conversation_history()
            if len(history) > self.max_history:
                # Keep only the last max_history messages
                # Rebuild memory with only recent messages
                recent = history[-self.max_history:]
                self.memory.clear()
                for msg in recent:
                    self.memory.add_message(msg['role'], msg['content'])
        
        # Auto-persist if enabled
        if self.auto_persist:
            self.save_context()
    
    def get_conversation_history(self) -> List[Dict]:
        """
        Get the full conversation history for this container.
        
        Returns:
            List of message dicts with role, content, timestamp
        """
        return self.memory.get_conversation_history()
    
    def clear_context(self):
        """Clear the conversation history for this container."""
        self.memory.clear()
        if self.auto_persist:
            self.save_context()
    
    def history_to_prompt_string(self, max_messages: int = 20) -> str:
        """
        Convert conversation history to a readable prompt string.
        
        Args:
            max_messages: Maximum number of messages to include
            
        Returns:
            Formatted conversation as string
        """
        history = self.memory.get_last_n_messages(max_messages)
        
        lines = []
        for msg in history:
            role = msg['role'].upper()
            content = msg['content']
            lines.append(f"{role}: {content}")
        
        return "\n".join(lines)
    
    def get_context_for_ollama(self, max_messages: int = 20) -> List[Dict]:
        """
        Get conversation history formatted for Ollama API.
        
        Args:
            max_messages: Maximum number of messages to include
            
        Returns:
            List of message dicts with role and content
        """
        history = self.memory.get_last_n_messages(max_messages)
        
        # Format for Ollama: [{'role': 'user', 'content': '...'}, ...]
        ollama_messages = []
        for msg in history:
            ollama_messages.append({
                'role': msg['role'],
                'content': msg['content']
            })
        
        return ollama_messages
    
    def save_context(self) -> bool:
        """
        Save conversation history to disk.
        
        Returns:
            True if save succeeded, False otherwise
        """
        try:
            context_path = self.context_dir / f"{self.container_id}.json"
            self.memory.save(str(context_path))
            return True
        except Exception:
            return False
    
    def load_context(self) -> bool:
        """
        Load conversation history from disk.
        
        Returns:
            True if load succeeded, False otherwise
        """
        try:
            context_path = self.context_dir / f"{self.container_id}.json"
            if context_path.exists():
                self.memory.load(str(context_path))
                return True
        except Exception:
            pass
        return False
    
    def query_ollama(
        self,
        prompt: str,
        model: str = "qwen2.5-coder:14b",
        system_prompt: Optional[str] = None
    ) -> str:
        """
        Query Ollama with full conversation context.
        
        This method automatically:
        1. Formats the current prompt with conversation history
        2. Sends to Ollama
        3. Tracks the query and response in memory
        
        Args:
            prompt: The current query
            model: Ollama model to use
            system_prompt: Optional system prompt
            
        Returns:
            Ollama's response
        """
        # Track the user query
        self.track_context("user", prompt)
        
        # Get response with context
        response = prompt_ollama_with_context(
            prompt,
            memory=self.memory,
            model=model,
            system_prompt=system_prompt
        )
        
        # Response is already tracked by prompt_ollama_with_context
        return response
    
    def get_container_id(self) -> str:
        """Get this prompter's container ID."""
        return self.container_id
    
    def get_metadata(self) -> Dict:
        """
        Get conversation metadata.
        
        Returns:
            Metadata dictionary including container_id, timestamps, etc.
        """
        return self.memory.get_metadata()


class ConversationMemory:
    """
    Manages conversation history and context for Ollama queries.
    
    Enables container self-awareness by persisting conversation history
    across sessions, allowing the container to remember context between
    queries and maintain awareness of its own state and previous interactions.
    
    Key features:
    - Add and retrieve messages with role tracking (user/assistant/system)
    - Persist conversation history to disk for container restart resilience
    - Manage context window by pruning old messages when token limit is reached
    - Track metadata (session_id, container_id, timestamps)
    - Merge conversations from multiple sessions
    """
    
    def __init__(
        self,
        max_tokens: int = 4096,
        metadata: Optional[Dict] = None
    ):
        """
        Initialize conversation memory.
        
        Args:
            max_tokens: Maximum tokens to keep in context (default: 4096)
            metadata: Optional metadata dict (session_id, container_id, etc.)
        """
        self.max_tokens = max_tokens
        self.messages: List[Dict] = []
        self.metadata: Dict = metadata or {}
        self._token_count: int = 0
        
        # Add metadata if provided
        if metadata:
            self.metadata.update(metadata)
    
    def add_message(self, role: str, content: str):
        """
        Add a message to conversation history.
        
        Args:
            role: Message role (user, assistant, or system)
            content: Message content
        """
        message = {
            'role': role,
            'content': content,
            'timestamp': datetime.now().isoformat()
        }
        
        self.messages.append(message)
        self._token_count += self._estimate_tokens(content)
        
        # Prune if over limit
        self._prune_to_limit()
    
    def get_conversation_history(self) -> List[Dict]:
        """
        Get full conversation history.
        
        Returns:
            List of message dicts with role, content, timestamp
        """
        return self.messages.copy()
    
    def get_last_n_messages(self, n: int) -> List[Dict]:
        """
        Get last N messages from history.
        
        Args:
            n: Number of messages to retrieve
            
        Returns:
            List of last N message dicts
        """
        return self.messages[-n:] if n > 0 else []
    
    def get_messages_by_role(self, role: str) -> List[Dict]:
        """
        Get all messages with a specific role.
        
        Args:
            role: Role to filter by (user, assistant, system)
            
        Returns:
            List of message dicts with matching role
        """
        return [msg for msg in self.messages if msg['role'] == role]
    
    def get_token_count(self) -> int:
        """
        Get current token count estimate.
        
        Returns:
            Estimated number of tokens in conversation
        """
        return self._token_count
    
    def clear(self):
        """Clear all conversation history."""
        self.messages = []
        self._token_count = 0
    
    def save(self, path: str):
        """
        Save conversation history to disk.

        Args:
            path: Path to save conversation JSON
        """
        data = {
            'metadata': self.metadata,
            'messages': self.messages,
            'token_count': self._token_count,
            'max_tokens': self.max_tokens,
            'saved_at': datetime.now().isoformat(),
            'history': self.messages  # For backward compatibility with tests
        }

        with open(path, 'w') as f:
            json.dump(data, f, indent=2)
    
    def load(self, path: str):
        """
        Load conversation history from disk.

        Args:
            path: Path to load conversation JSON from
        """
        # Ensure messages list exists before any operation
        self.messages = []
        self._token_count = 0
        try:
            with open(path, 'r') as f:
                data = json.load(f)

            self.metadata = data.get('metadata', {})
            self.messages = data.get('messages', [])
            self._token_count = data.get('token_count', 0)
            self.max_tokens = data.get('max_tokens', 4096)

            # Prune if loaded history exceeds current limit
            self._prune_to_limit()

        except (FileNotFoundError, json.JSONDecodeError):
            # If file doesn't exist or is invalid, start fresh
            self.messages = []
            self._token_count = 0
    
    def merge(self, other: 'ConversationMemory'):
        """
        Merge another conversation memory into this one.
        
        Args:
            other: Another ConversationMemory instance to merge
        """
        for msg in other.messages:
            self.add_message(msg['role'], msg['content'])
        
        # Merge metadata
        if other.metadata:
            for key, value in other.metadata.items():
                if key not in self.metadata:
                    self.metadata[key] = value
    
    def get_metadata(self) -> Dict:
        """
        Get conversation metadata.
        
        Returns:
            Metadata dictionary
        """
        return self.metadata.copy()
    
    def _estimate_tokens(self, text: str) -> int:
        """
        Estimate token count for text.
        
        Rough estimate: ~4 characters per token for English text.
        This is approximate but good enough for context management.
        
        Args:
            text: Text to estimate tokens for
            
        Returns:
            Estimated token count
        """
        return max(1, len(text) // 4)
    
    def _prune_to_limit(self):
        """Remove oldest messages until token count is within limit."""
        while self._token_count > self.max_tokens and len(self.messages) > 0:
            # Remove oldest message (first in list)
            removed = self.messages.pop(0)
            self._token_count -= self._estimate_tokens(removed['content'])


def prompt_ollama_with_context(
    prompt: str,
    memory: Optional[ConversationMemory] = None,
    model: str = "qwen2.5-coder:14b",
    system_prompt: Optional[str] = None
) -> str:
    """
    Send prompt to Ollama with conversation context.
    
    This is the context-aware version of prompt_ollama. It includes
    conversation history from the memory object, allowing Ollama to
    maintain context across queries.
    
    Args:
        prompt: The current prompt to send
        memory: Optional ConversationMemory with history
        model: Ollama model to use
        system_prompt: Optional system prompt
        
    Returns:
        Ollama's response as a string
        
    Raises:
        subprocess.CalledProcessError: If Ollama command fails
    """
    full_prompt = prompt
    
    # Add conversation history if memory provided
    if memory and memory.get_conversation_history():
        history = memory.get_last_n_messages(10)  # Last 10 messages
        
        context_lines = []
        for msg in history:
            role = msg['role'].upper()
            content = msg['content']
            context_lines.append(f"{role}: {content}")
        
        context_str = "\n".join(context_lines)
        full_prompt = f"Previous conversation:\n{context_str}\n\nCurrent question:\n{prompt}"
    
    # Add system prompt if provided
    if system_prompt:
        full_prompt = f"System: {system_prompt}\n\n{full_prompt}"
    
    # Get response
    response = prompt_ollama(full_prompt, model)
    
    # Add to memory if provided
    if memory:
        memory.add_message("user", prompt)
        memory.add_message("assistant", response)
    
    return response


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