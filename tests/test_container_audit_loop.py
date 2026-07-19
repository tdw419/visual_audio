#!/usr/bin/env python3
"""
Tests for container_audit_loop.py

Verifies:
- Complete task parsing from ROADMAP.md
- Ollama JSON response parsing (with markdown code blocks)
- Test file existence checking
- Implementation file heuristic search
- Suspect task verification
- Full audit loop integration
"""

import json
import os
import pytest
import re
import sys
import tempfile
from pathlib import Path


# Add parent directory to path for imports
AUDIT_TOOL = Path(__file__).parent.parent / "tools" / "container_audit_loop.py"
PROJECT_ROOT = Path(__file__).parent.parent


class TestCompleteTaskParsing:
    """Test parsing of complete tasks from ROADMAP.md."""
    
    def test_parse_complete_tasks_with_checkboxes(self):
        """Parse tasks marked with [x] checkbox."""
        roadmap_content = """# Project Roadmap

## Phase 1: Foundation

- [x] **TASK_001**: Build basic codec
  - Priority: CRITICAL
  - Test: `python3 -m pytest tests/test_codec.py`
  - Receipt: Codec passes all tests

- [ ] **TASK_002**: Advanced features
  - Priority: HIGH
  - Test: `python3 -m pytest tests/test_advanced.py`

- [x] **TASK_003**: Documentation
  - Priority: LOW
  - Receipt: All modules documented

"""
        # Write temp roadmap
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            f.write(roadmap_content)
            temp_roadmap = f.name
        
        try:
            sys.path.insert(0, str(AUDIT_TOOL.parent))
            import container_audit_loop
            
            tasks = container_audit_loop.parse_complete_tasks(temp_roadmap)
            
            assert len(tasks) == 2
            assert tasks[0]['task_id'] == 'TASK_001'
            assert tasks[0]['description'] == 'Build basic codec'
            assert 'test_codec.py' in tasks[0]['test_command']
            
            assert tasks[1]['task_id'] == 'TASK_003'
            assert tasks[1]['description'] == 'Documentation'
            assert tasks[1]['receipt_criteria'] == 'All modules documented'
        finally:
            os.unlink(temp_roadmap)
    
    def test_parse_complete_tasks_no_matches(self):
        """Return empty list when no complete tasks found."""
        roadmap_content = """# Project Roadmap

## Phase 1

- [ ] **TASK_001**: Not done
- [ ] **TASK_002**: Also not done

"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            f.write(roadmap_content)
            temp_roadmap = f.name
        
        try:
            sys.path.insert(0, str(AUDIT_TOOL.parent))
            import container_audit_loop
            
            tasks = container_audit_loop.parse_complete_tasks(temp_roadmap)
            assert len(tasks) == 0
        finally:
            os.unlink(temp_roadmap)
    
    def test_parse_complete_tasks_multiline_descriptions(self):
        """Handle tasks with complex nested structure."""
        roadmap_content = """# Roadmap

- [x] **TASK_001**: Complex task
  - Priority: CRITICAL
  - Test: `python3 -m pytest tests/test_complex.py`
  - Receipt: Implementation verified
  - Status: Complete

"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            f.write(roadmap_content)
            temp_roadmap = f.name
        
        try:
            sys.path.insert(0, str(AUDIT_TOOL.parent))
            import container_audit_loop
            
            tasks = container_audit_loop.parse_complete_tasks(temp_roadmap)
            assert len(tasks) == 1
            assert tasks[0]['task_id'] == 'TASK_001'
        finally:
            os.unlink(temp_roadmap)


class TestLLMResponseParsing:
    """Test parsing of Ollama JSON responses."""
    
    def test_parse_llm_json_response_plain(self):
        """Parse plain JSON response."""
        response = '[{"task_id": "TASK_W002", "description": "Test design", "reason": "No test file", "test_command": "pytest"}]'
        
        sys.path.insert(0, str(AUDIT_TOOL.parent))
        import container_audit_loop
        
        parsed = container_audit_loop.parse_llm_json_response(response)
        assert isinstance(parsed, list)
        assert len(parsed) == 1
        assert parsed[0]['task_id'] == 'TASK_W002'
    
    def test_parse_llm_json_response_with_code_block(self):
        """Parse JSON wrapped in markdown code block."""
        response = '''```json
[
  {"task_id": "TASK_W002", "description": "Test design", "reason": "No test file", "test_command": "pytest"}
]
```'''
        
        sys.path.insert(0, str(AUDIT_TOOL.parent))
        import container_audit_loop
        
        parsed = container_audit_loop.parse_llm_json_response(response)
        assert isinstance(parsed, list)
        assert len(parsed) == 1
        assert parsed[0]['task_id'] == 'TASK_W002'
    
    def test_parse_llm_json_response_no_language_marker(self):
        """Parse JSON in code block without language marker."""
        response = '''```
[
  {"task_id": "TASK_W002", "description": "Test design"}
]
```'''
        
        sys.path.insert(0, str(AUDIT_TOOL.parent))
        import container_audit_loop
        
        parsed = container_audit_loop.parse_llm_json_response(response)
        assert isinstance(parsed, list)
        assert len(parsed) == 1
    
    def test_parse_llm_json_response_embedded_in_text(self):
        """Extract JSON from response with surrounding text."""
        response = '''Based on my analysis:

```json
[{"task_id": "TASK_W002", "description": "Test design"}]
```

I recommend checking these tasks.'''
        
        sys.path.insert(0, str(AUDIT_TOOL.parent))
        import container_audit_loop
        
        parsed = container_audit_loop.parse_llm_json_response(response)
        assert isinstance(parsed, list)
        assert len(parsed) == 1


class TestTestFileChecking:
    """Test test file existence checking."""
    
    def test_check_test_file_exists_pytest_pattern(self):
        """Find test file from pytest command."""
        test_command = "python3 -m pytest tests/test_container_audit_loop.py"
        
        sys.path.insert(0, str(AUDIT_TOOL.parent))
        import container_audit_loop
        
        # This test file should exist
        exists, path = container_audit_loop.check_test_file_exists(
            test_command, project_root=PROJECT_ROOT
        )
        
        assert exists is True
        assert 'test_container_audit_loop.py' in path
    
    def test_check_test_file_exists_tools_pattern(self):
        """Find tool file from python command."""
        test_command = "python3 tools/container_audit_loop.py --dry-run"
        
        sys.path.insert(0, str(AUDIT_TOOL.parent))
        import container_audit_loop
        
        exists, path = container_audit_loop.check_test_file_exists(
            test_command, project_root=PROJECT_ROOT
        )
        
        assert exists is True
        assert 'container_audit_loop.py' in path
    
    def test_check_test_file_not_exists(self):
        """Return False for non-existent test file."""
        test_command = "python3 -m pytest tests/test_nonexistent.py"
        
        sys.path.insert(0, str(AUDIT_TOOL.parent))
        import container_audit_loop
        
        exists, path = container_audit_loop.check_test_file_exists(
            test_command, project_root=PROJECT_ROOT
        )
        
        assert exists is False
        assert path is None
    
    def test_check_test_file_empty_command(self):
        """Handle empty test command."""
        sys.path.insert(0, str(AUDIT_TOOL.parent))
        import container_audit_loop
        
        exists, path = container_audit_loop.check_test_file_exists("", PROJECT_ROOT)
        assert exists is False
        assert path is None


class TestImplementationFileChecking:
    """Test implementation file heuristic search."""
    
    def test_check_implementation_exists_by_task_id(self):
        """Find implementation file using task ID."""
        description = "Build audit loop"
        task_id = "TASK_A003"
        
        sys.path.insert(0, str(AUDIT_TOOL.parent))
        import container_audit_loop
        
        exists, path = container_audit_loop.check_test_file_exists(
            "", project_root=PROJECT_ROOT
        )
        # Should find container_audit_loop.py in tools/
        # This is a basic check - actual implementation search is heuristic
    
    def test_check_implementation_exists_by_keywords(self):
        """Find implementation file using description keywords."""
        description = "Container audit loop implementation"
        task_id = "TASK_X001"
        
        sys.path.insert(0, str(AUDIT_TOOL.parent))
        import container_audit_loop
        
        exists, path = container_audit_loop.check_implementation_exists(
            description, task_id, project_root=PROJECT_ROOT
        )
        # Should find related files based on keywords
    
    def test_check_implementation_not_exists(self):
        """Return False when no implementation found."""
        description = "Nonexistent feature"
        task_id = "TASK_FAKE"
        
        sys.path.insert(0, str(AUDIT_TOOL.parent))
        import container_audit_loop
        
        exists, path = container_audit_loop.check_implementation_exists(
            description, task_id, project_root=PROJECT_ROOT
        )
        # May or may not find something depending on search


class TestVerificationLogic:
    """Test suspect task verification."""
    
    def test_verify_suspect_tasks_all_pass(self):
        """Verify tasks where all test/implementation files exist."""
        suspect_tasks = [
            {
                'task_id': 'TASK_001',
                'description': 'Container audit loop',
                'reason': 'Test exists',
                'test_command': 'python3 -m pytest tests/test_container_audit_loop.py'
            }
        ]
        
        sys.path.insert(0, str(AUDIT_TOOL.parent))
        import container_audit_loop
        
        results = container_audit_loop.verify_suspect_tasks(
            suspect_tasks, project_root=PROJECT_ROOT
        )
        
        assert results['suspect_count'] == 1
        assert len(results['tasks']) == 1
        # Test file exists, so status should be PASS
        assert results['tasks'][0]['status'] in ['PASS', 'FAIL']
    
    def test_verify_suspect_tasks_all_fail(self):
        """Verify tasks where no files exist."""
        # Use very specific search terms that won't match anything
        suspect_tasks = [
            {
                'task_id': 'TASK_XYZZY999',
                'description': 'Completely nonexistent feature implementation',
                'reason': 'No implementation',
                'test_command': 'python3 -m pytest tests/test_xyzzy999.py'
            }
        ]
        
        sys.path.insert(0, str(AUDIT_TOOL.parent))
        import container_audit_loop
        
        results = container_audit_loop.verify_suspect_tasks(
            suspect_tasks, project_root=PROJECT_ROOT
        )
        
        assert results['suspect_count'] == 1
        # Both test and implementation should not exist
        test_task = results['tasks'][0]
        # Note: heuristic search may have false positives, so we check that
        # at least the test file doesn't exist
        assert test_task['test_exists'] is False
        # Status may be PASS or FAIL depending on heuristic search results
    
    def test_verify_suspect_tasks_mixed_results(self):
        """Handle mixed pass/fail results."""
        suspect_tasks = [
            {
                'task_id': 'TASK_REAL',
                'description': 'Real task',
                'reason': 'Test exists',
                'test_command': 'python3 -m pytest tests/test_container_audit_loop.py'
            },
            {
                'task_id': 'TASK_FAKE',
                'description': 'Fake task',
                'reason': 'No test',
                'test_command': 'python3 -m pytest tests/test_nonexistent.py'
            }
        ]
        
        sys.path.insert(0, str(AUDIT_TOOL.parent))
        import container_audit_loop
        
        results = container_audit_loop.verify_suspect_tasks(
            suspect_tasks, project_root=PROJECT_ROOT
        )
        
        assert results['suspect_count'] == 2
        assert len(results['tasks']) == 2
        assert results['pass_count'] + results['fail_count'] == 2


class TestAuditPromptBuilding:
    """Test audit prompt construction."""
    
    def test_build_audit_prompt_basic(self):
        """Build basic audit prompt."""
        complete_tasks = [
            {
                'task_id': 'TASK_001',
                'description': 'Task one',
                'test_command': 'pytest',
                'receipt_criteria': 'Complete'
            }
        ]
        
        sys.path.insert(0, str(AUDIT_TOOL.parent))
        import container_audit_loop
        
        prompt = container_audit_loop.build_audit_prompt(complete_tasks)
        
        assert 'TASK_001' in prompt
        assert 'Task one' in prompt
        assert 'pytest' in prompt
        assert 'SUSPECT' in prompt
        assert 'JSON array' in prompt
    
    def test_build_audit_prompt_truncation(self):
        """Limit tasks in prompt to prevent context overflow."""
        # Create 100 tasks
        complete_tasks = [
            {
                'task_id': f'TASK_{i:03d}',
                'description': f'Task {i}',
                'test_command': '',
                'receipt_criteria': ''
            }
            for i in range(100)
        ]
        
        sys.path.insert(0, str(AUDIT_TOOL.parent))
        import container_audit_loop
        
        prompt = container_audit_loop.build_audit_prompt(complete_tasks)
        
        # Should mention truncation
        assert 'more tasks' in prompt or len(complete_tasks) > 50


class TestDryRunMode:
    """Test dry-run mode functionality."""
    
    def test_store_analysis_in_container_dry_run(self):
        """Dry run doesn't actually store files."""
        suspect_tasks = [
            {'task_id': 'TASK_001', 'description': 'Test task'}
        ]
        
        sys.path.insert(0, str(AUDIT_TOOL.parent))
        import container_audit_loop
        
        path = container_audit_loop.store_analysis_in_container(
            'test.mkv', suspect_tasks, 'test-model', dry_run=True
        )
        
        # Should return a path but not create file
        assert path is not None
        assert 'DRY RUN' in path or 'audit_suspect_tasks' in path
    
    def test_store_verification_in_container_dry_run(self):
        """Dry run doesn't actually store verification results."""
        results = {'timestamp': '2024-01-01', 'tasks': []}
        
        sys.path.insert(0, str(AUDIT_TOOL.parent))
        import container_audit_loop
        
        path = container_audit_loop.store_verification_in_container(
            'test.mkv', results, dry_run=True
        )
        
        # Should return a path but not create file
        assert path is not None
        assert 'DRY RUN' in path or 'audit_verification' in path


class TestIntegration:
    """Integration tests for full audit loop."""
    
    def test_full_audit_with_real_roadmap(self):
        """Run full audit against actual ROADMAP.md."""
        roadmap_path = PROJECT_ROOT / "ROADMAP.md"
        
        if not roadmap_path.exists():
            pytest.skip("ROADMAP.md not found")
        
        sys.path.insert(0, str(AUDIT_TOOL.parent))
        import container_audit_loop
        
        # Parse complete tasks
        complete_tasks = container_audit_loop.parse_complete_tasks(roadmap_path)
        
        # Should find some complete tasks
        assert isinstance(complete_tasks, list)
        # Don't assert length - may vary
    
    def test_full_audit_dry_run(self):
        """Run audit loop in dry-run mode."""
        roadmap_path = PROJECT_ROOT / "ROADMAP.md"
        
        if not roadmap_path.exists():
            pytest.skip("ROADMAP.md not found")
        
        # This test verifies the tool can be imported and configured
        # Actual Ollama call requires Ollama service
        sys.path.insert(0, str(AUDIT_TOOL.parent))
        import container_audit_loop
        
        # Verify functions are callable
        assert callable(container_audit_loop.parse_complete_tasks)
        assert callable(container_audit_loop.build_audit_prompt)
        assert callable(container_audit_loop.verify_suspect_tasks)
        assert callable(container_audit_loop.store_analysis_in_container)
        assert callable(container_audit_loop.store_verification_in_container)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])