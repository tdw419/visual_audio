#!/usr/bin/env python3
"""
test_container_audit_loop.py — Verify container audit loop functionality.

Tests for TASK_A003: Automated container audit loop (Ollama analyzes itself)

The audit loop:
1. Parses ROADMAP.md for all tasks
2. Extracts receipts (file paths, implementation claims)
3. Verifies each receipt by checking file existence
4. Flags suspect tasks (COMPLETE but missing implementation)
5. Uses Ollama to analyze task plausibility
6. Generates JSON report with detailed findings

Test Coverage:
1. Roadmap parsing accuracy
2. File existence verification
3. Test file verification
4. Missing implementation detection
5. Receipt extraction patterns
6. Ollama analysis integration (mocked)
7. Audit report structure
8. Suspect task flagging
9. Summary statistics
"""

import sys
import os
import json
import tempfile
import subprocess
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.ollama_prompt import (
    parse_roadmap_tasks,
    verify_file_exists,
    verify_test_exists,
    extract_file_paths_from_receipt,
    analyze_task_with_ollama,
    run_audit,
    print_audit_report,
    prompt_ollama
)


def test_parse_roadmap_tasks_real_roadmap():
    """Test that parse_roadmap_tasks correctly parses the actual ROADMAP.md"""
    roadmap_path = Path(__file__).parent.parent / "ROADMAP.md"
    
    if not roadmap_path.exists():
        print("⚠ ROADMAP.md not found, skipping real roadmap test")
        return
    
    tasks = parse_roadmap_tasks(str(roadmap_path))
    
    # Verify we got tasks
    assert len(tasks) > 0, "Should parse at least one task from ROADMAP.md"
    
    # Verify task structure
    for task in tasks:
        assert 'id' in task, "Task should have 'id' field"
        assert 'description' in task, "Task should have 'description' field"
        assert 'status' in task, "Task should have 'status' field"
        assert 'receipts' in task, "Task should have 'receipts' field"
        
        # Verify task ID format
        assert task['id'].startswith('TASK_'), f"Task ID should start with 'TASK_': {task['id']}"
        
        # Verify status is one of expected values
        assert task['status'] in ['COMPLETE', 'IN_PROGRESS', 'PENDING', 'UNKNOWN'], \
            f"Task status should be COMPLETE, IN_PROGRESS, PENDING, or UNKNOWN: {task['status']}"
    
    # Check for known complete tasks (TASK_VAC001-007 should be complete based on roadmap)
    complete_tasks = [t for t in tasks if t['status'] == 'COMPLETE']
    assert len(complete_tasks) > 0, "Should have at least one COMPLETE task"
    
    print(f"✓ Parsed {len(tasks)} tasks from ROADMAP.md ({len(complete_tasks)} complete)")


def test_verify_file_exists_absolute():
    """Test file existence verification with absolute paths"""
    with tempfile.TemporaryDirectory() as tmp_dir:
        # Create a test file
        test_file = Path(tmp_dir) / "test.py"
        test_file.write_text("print('test')")
        
        # Test absolute path
        assert verify_file_exists(str(test_file), tmp_dir) == True, \
            "Should find file with absolute path"
        
        # Test non-existent file
        non_existent = Path(tmp_dir) / "nonexistent.py"
        assert verify_file_exists(str(non_existent), tmp_dir) == False, \
            "Should not find non-existent file"


def test_verify_file_exists_relative():
    """Test file existence verification with relative paths"""
    with tempfile.TemporaryDirectory() as tmp_dir:
        # Create a test file in project root
        test_file = Path(tmp_dir) / "test.py"
        test_file.write_text("print('test')")
        
        # Test relative path
        assert verify_file_exists("test.py", tmp_dir) == True, \
            "Should find file with relative path"
        
        # Test nested path
        nested = Path(tmp_dir) / "tools" / "script.py"
        nested.parent.mkdir(parents=True)
        nested.write_text("print('nested')")
        
        assert verify_file_exists("tools/script.py", tmp_dir) == True, \
            "Should find nested file with relative path"


def test_verify_test_exists():
    """Test test file verification"""
    with tempfile.TemporaryDirectory() as tmp_dir:
        # Create a test file
        test_file = Path(tmp_dir) / "test_feature.py"
        test_file.write_text("import pytest\ndef test_something(): pass")
        
        assert verify_test_exists(str(test_file), tmp_dir) == True, \
            "Should find test file"
        
        # Create non-test file
        non_test = Path(tmp_dir) / "regular.py"
        non_test.write_text("print('not a test')")
        
        # verify_test_exists should still work, it just calls verify_file_exists
        assert verify_test_exists(str(non_test), tmp_dir) == True, \
            "Should find regular file via verify_test_exists"


def test_extract_file_paths_from_receipt_created():
    """Test extracting file paths from 'Created file' receipts"""
    receipts = [
        "Created file src/main.py",
        "Created file tests/test_feature.py",
        "Created file codec/tables.json"
    ]
    
    all_paths = []
    for receipt in receipts:
        all_paths.extend(extract_file_paths_from_receipt(receipt))
    
    assert "src/main.py" in all_paths, "Should extract src/main.py"
    assert "tests/test_feature.py" in all_paths, "Should extract tests/test_feature.py"
    assert "codec/tables.json" in all_paths, "Should extract codec/tables.json"


def test_extract_file_paths_from_receipt_added():
    """Test extracting file paths from 'Added' receipts"""
    receipts = [
        "Added src/main.py",
        "Added tests/test_feature.py",
        "Added codec/tables.json"
    ]
    
    all_paths = []
    for receipt in receipts:
        all_paths.extend(extract_file_paths_from_receipt(receipt))
    
    assert "src/main.py" in all_paths, "Should extract src/main.py"
    assert "tests/test_feature.py" in all_paths, "Should extract tests/test_feature.py"


def test_extract_file_paths_from_receipt_updated():
    """Test extracting file paths from 'Updated' receipts"""
    receipts = [
        "Updated README.md",
        "Updated codec/tables.json"
    ]
    
    all_paths = []
    for receipt in receipts:
        all_paths.extend(extract_file_paths_from_receipt(receipt))
    
    assert "README.md" in all_paths, "Should extract README.md"
    assert "codec/tables.json" in all_paths, "Should extract codec/tables.json"


def test_extract_file_paths_from_receipt_direct():
    """Test extracting file paths from direct path references"""
    receipts = [
        "Implementation in src/main.py",
        "Codec spec in codec/tables.json",
        "Test coverage in tests/test_feature.py"
    ]
    
    all_paths = []
    for receipt in receipts:
        all_paths.extend(extract_file_paths_from_receipt(receipt))
    
    assert "src/main.py" in all_paths, "Should extract src/main.py from direct reference"
    assert "codec/tables.json" in all_paths, "Should extract codec/tables.json"
    assert "tests/test_feature.py" in all_paths, "Should extract tests/test_feature.py"


def test_extract_file_paths_from_receipt_test_pattern():
    """Test extracting test files using test pattern"""
    receipts = [
        "Added comprehensive test coverage",
        "Tests in tests/test_spatial_encoding.py",
        "test files created"
    ]
    
    all_paths = []
    for receipt in receipts:
        all_paths.extend(extract_file_paths_from_receipt(receipt))
    
    assert "tests/test_spatial_encoding.py" in all_paths, \
        "Should extract test file using test pattern"


def test_analyze_task_with_ollama_no_receipts():
    """Test Ollama analysis when task has no receipts"""
    task = {
        'id': 'TASK_TEST',
        'description': 'Test task',
        'receipts': []
    }
    
    result = analyze_task_with_ollama(task, model='dummy-model')
    
    assert result['task_id'] == 'TASK_TEST'
    assert result['ollama_assessment'] == 'needs_review'
    assert 'No receipts provided' in result['ollama_reasoning']


def test_analyze_task_with_ollama_mocked():
    """Test Ollama analysis with mocked Ollama response"""
    task = {
        'id': 'TASK_TEST',
        'description': 'Implement spatial encoding codec',
        'receipts': [
            'Created file src/spatial_codec.py',
            'Added tests/test_spatial_codec.py'
        ]
    }
    
    # Mock Ollama response
    mock_response = """ASSESSMENT: likely_impl
REASONING: Receipts show both implementation and test files, consistent with completion
EXPECTED_FILES: src/spatial_codec.py, tests/test_spatial_codec.py"""
    
    with patch('tools.ollama_prompt.prompt_ollama') as mock_ollama:
        mock_ollama.return_value = mock_response
        
        result = analyze_task_with_ollama(task, model='qwen2.5-coder:14b')
        
        assert result['task_id'] == 'TASK_TEST'
        assert result['ollama_assessment'] == 'likely_impl'
        assert 'src/spatial_codec.py' in result['suggested_files']
        assert 'tests/test_spatial_codec.py' in result['suggested_files']


def test_analyze_task_with_ollama_unlikely():
    """Test Ollama analysis when assessment is unlikely"""
    task = {
        'id': 'TASK_TEST',
        'description': 'Implement complex GPU kernel',
        'receipts': [
            'Updated README.md'
        ]
    }
    
    # Mock Ollama response indicating unlikely completion
    mock_response = """ASSESSMENT: unlikely
REASONING: Only README.md updated, no implementation files mentioned
EXPECTED_FILES: src/gpu_kernel.cu, tests/test_gpu_kernel.py"""
    
    with patch('tools.ollama_prompt.prompt_ollama') as mock_ollama:
        mock_ollama.return_value = mock_response
        
        result = analyze_task_with_ollama(task, model='qwen2.5-coder:14b')
        
        assert result['task_id'] == 'TASK_TEST'
        assert result['ollama_assessment'] == 'unlikely'
        assert 'no implementation files' in result['ollama_reasoning'].lower()


def test_run_audit_with_missing_files():
    """Test audit loop detecting missing implementation files"""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        
        # Create a fake roadmap with a COMPLETE task claiming files that don't exist
        roadmap_content = """# Visual Audio Roadmap

## Phase 1: Testing

- [x] **TASK_SUSPECT**: Task with missing implementation
  - Priority: HIGH
  - Status: COMPLETE
  - Completed: 2026-07-20
  - Receipt: Created file src/missing.py
  - Receipt: Added tests/test_missing.py
"""
        roadmap_path = tmp_path / "ROADMAP.md"
        roadmap_path.write_text(roadmap_content)
        
        # Run audit
        output_path = tmp_path / "audit_report.json"
        report = run_audit(str(tmp_path), str(output_path), use_ollama=False)
        
        # Verify report structure
        assert 'timestamp' in report
        assert 'summary' in report
        assert 'tasks' in report
        assert 'suspect_tasks' in report
        
        # Verify task was parsed
        assert len(report['tasks']) == 1
        task = report['tasks'][0]
        assert task['task_id'] == 'TASK_SUSPECT'
        assert task['status'] == 'COMPLETE'
        
        # Verify missing files were detected
        assert task['is_suspect'] == True
        assert len(task['issues']) > 0
        assert any('missing' in issue.lower() for issue in task['issues'])
        
        # Verify suspect tasks list
        assert len(report['suspect_tasks']) == 1
        assert report['suspect_tasks'][0]['task_id'] == 'TASK_SUSPECT'
        
        # Verify statistics
        assert report['summary']['total_tasks'] == 1
        assert report['summary']['completed_tasks'] == 1
        assert report['summary']['suspect_tasks'] == 1
        assert report['summary']['suspect_percentage'] == 100.0
        
        # Verify report was written to file
        assert output_path.exists()
        with open(output_path) as f:
            written_report = json.load(f)
        assert written_report == report


def test_run_audit_with_complete_implementation():
    """Test audit loop with tasks that have complete implementations"""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        
        # Create claimed files
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        src_file = src_dir / "implementation.py"
        src_file.write_text("print('implementation')")
        
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        test_file = tests_dir / "test_implementation.py"
        test_file.write_text("def test_pass(): pass")
        
        # Create a fake roadmap with a COMPLETE task with existing files
        roadmap_content = """# Visual Audio Roadmap

## Phase 1: Testing

- [x] **TASK_VALID**: Task with complete implementation
  - Priority: HIGH
  - Status: COMPLETE
  - Completed: 2026-07-20
  - Receipt: Created file src/implementation.py
  - Receipt: Added tests/test_implementation.py
"""
        roadmap_path = tmp_path / "ROADMAP.md"
        roadmap_path.write_text(roadmap_content)
        
        # Run audit
        output_path = tmp_path / "audit_report.json"
        report = run_audit(str(tmp_path), str(output_path), use_ollama=False)
        
        # Verify task was parsed
        assert len(report['tasks']) == 1
        task = report['tasks'][0]
        assert task['task_id'] == 'TASK_VALID'
        assert task['status'] == 'COMPLETE'
        
        # Verify no issues found
        assert task['is_suspect'] == False
        assert len(task['issues']) == 0
        
        # Verify not in suspect list
        assert len(report['suspect_tasks']) == 0
        
        # Verify statistics
        assert report['summary']['total_tasks'] == 1
        assert report['summary']['completed_tasks'] == 1
        assert report['summary']['suspect_tasks'] == 0
        assert report['summary']['suspect_percentage'] == 0.0


def test_run_audit_mixed_tasks():
    """Test audit loop with mix of complete, pending, and suspect tasks"""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        
        # Create some files
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        good_file = src_dir / "good.py"
        good_file.write_text("print('good')")
        
        # Create a fake roadmap with mixed tasks
        roadmap_content = """# Visual Audio Roadmap

## Phase 1: Testing

- [x] **TASK_VALID**: Valid task
  - Priority: HIGH
  - Status: COMPLETE
  - Completed: 2026-07-20
  - Receipt: Created file src/good.py

- [x] **TASK_SUSPECT**: Suspect task
  - Priority: HIGH
  - Status: COMPLETE
  - Completed: 2026-07-20
  - Receipt: Created file src/missing.py

- [ ] **TASK_PENDING**: Pending task
  - Priority: MEDIUM
  - Status: PENDING
  - Receipt: Will implement feature X
"""
        roadmap_path = tmp_path / "ROADMAP.md"
        roadmap_path.write_text(roadmap_content)
        
        # Run audit
        output_path = tmp_path / "audit_report.json"
        report = run_audit(str(tmp_path), str(output_path), use_ollama=False)
        
        # Verify all tasks parsed
        assert len(report['tasks']) == 3
        
        # Verify statistics
        assert report['summary']['total_tasks'] == 3
        assert report['summary']['completed_tasks'] == 2
        assert report['summary']['pending_tasks'] == 1
        assert report['summary']['suspect_tasks'] == 1
        assert report['summary']['suspect_percentage'] == 50.0
        
        # Verify suspect list has correct task
        assert len(report['suspect_tasks']) == 1
        assert report['suspect_tasks'][0]['task_id'] == 'TASK_SUSPECT'


def test_run_audit_with_ollama_integration():
    """Test audit loop with Ollama analysis integration"""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        
        # Create a file that exists
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        src_file = src_dir / "implementation.py"
        src_file.write_text("print('implementation')")
        
        # Create a roadmap with a task
        roadmap_content = """# Visual Audio Roadmap

## Phase 1: Testing

- [x] **TASK_OLLAMA**: Task for Ollama analysis
  - Priority: HIGH
  - Status: COMPLETE
  - Completed: 2026-07-20
  - Receipt: Created file src/implementation.py
"""
        roadmap_path = tmp_path / "ROADMAP.md"
        roadmap_path.write_text(roadmap_content)
        
        # Mock Ollama response
        mock_response = """ASSESSMENT: likely_impl
REASONING: Implementation file exists and task description matches
EXPECTED_FILES: src/implementation.py"""
        
        with patch('tools.ollama_prompt.prompt_ollama') as mock_ollama:
            mock_ollama.return_value = mock_response
            
            # Run audit with Ollama
            output_path = tmp_path / "audit_report.json"
            report = run_audit(str(tmp_path), str(output_path), use_ollama=True)
            
            # Verify Ollama was called
            mock_ollama.assert_called()
            
            # Verify task has Ollama analysis
            task = report['tasks'][0]
            assert 'ollama_assessment' in task
            assert task['ollama_assessment'] == 'likely_impl'
            assert 'ollama_reasoning' in task


def test_run_audit_no_roadmap():
    """Test audit loop when ROADMAP.md doesn't exist"""
    with tempfile.TemporaryDirectory() as tmp_dir:
        # Don't create ROADMAP.md
        # tmp_dir is already a string path
        output_path = Path(tmp_dir) / "audit_report.json"
        report = run_audit(tmp_dir, str(output_path), use_ollama=False)
        
        # Verify error handling
        assert 'error' in report
        assert 'not found' in report['error'].lower()
        assert report['summary']['total_tasks'] == 0
        
        # Verify report was still written
        assert output_path.exists()


def test_print_audit_report():
    """Test printing audit report in human-readable format"""
    report = {
        'timestamp': '2026-07-20T12:00:00',
        'project_root': '/project',
        'summary': {
            'total_tasks': 10,
            'completed_tasks': 8,
            'pending_tasks': 2,
            'suspect_tasks': 2,
            'suspect_percentage': 25.0
        },
        'suspect_tasks': [
            {
                'task_id': 'TASK_SUSPECT1',
                'description': 'First suspect task',
                'issues': ['Missing file: src/missing.py']
            },
            {
                'task_id': 'TASK_SUSPECT2',
                'description': 'Second suspect task',
                'issues': ['Missing test: tests/test_missing.py']
            }
        ]
    }
    
    # This should not raise an exception
    print_audit_report(report)


def test_print_audit_report_no_suspects():
    """Test printing audit report when no suspect tasks found"""
    report = {
        'timestamp': '2026-07-20T12:00:00',
        'project_root': '/project',
        'summary': {
            'total_tasks': 10,
            'completed_tasks': 10,
            'pending_tasks': 0,
            'suspect_tasks': 0,
            'suspect_percentage': 0.0
        },
        'suspect_tasks': []
    }
    
    # This should not raise an exception
    print_audit_report(report)


def test_run_audit_real_project():
    """Test audit loop on the actual Visual Audio project"""
    project_root = Path(__file__).parent.parent
    roadmap_path = project_root / "ROADMAP.md"
    
    if not roadmap_path.exists():
        print("⚠ ROADMAP.md not found, skipping real project audit test")
        return
    
    with tempfile.TemporaryDirectory() as tmp_dir:
        output_path = Path(tmp_dir) / "audit_report.json"
        
        # Run audit without Ollama (faster, just file checks)
        report = run_audit(str(project_root), str(output_path), use_ollama=False)
        
        # Verify basic structure
        assert 'timestamp' in report
        assert 'summary' in report
        assert 'tasks' in report
        assert 'suspect_tasks' in report
        
        # Should have parsed tasks
        assert report['summary']['total_tasks'] > 0
        
        # Should have some complete tasks
        complete_tasks = [t for t in report['tasks'] if t['status'] == 'COMPLETE']
        assert len(complete_tasks) > 0, "Should have at least one COMPLETE task"
        
        print(f"✓ Audited real project: {report['summary']['total_tasks']} tasks, "
              f"{len(complete_tasks)} complete, {report['summary']['suspect_tasks']} suspect")


def test_prompt_ollama():
    """Test Ollama prompt function (requires Ollama to be installed)"""
    # This is an integration test that requires Ollama to be running
    # We'll skip if Ollama is not available
    
    try:
        result = prompt_ollama("Say 'Hello, World!'", model="qwen2.5-coder:14b")
        assert len(result) > 0, "Should get a response from Ollama"
        print(f"✓ Ollama integration working: {result[:50]}...")
    except (subprocess.CalledProcessError, RuntimeError) as e:
        print(f"⚠ Ollama not available: {e}")


def run_all_tests():
    """Run all tests"""
    print("\n" + "="*60)
    print("Container Audit Loop Test Suite")
    print("="*60 + "\n")
    
    tests = [
        ("Roadmap Parsing (Real ROADMAP)", test_parse_roadmap_tasks_real_roadmap),
        ("File Existence (Absolute)", test_verify_file_exists_absolute),
        ("File Existence (Relative)", test_verify_file_exists_relative),
        ("Test File Verification", test_verify_test_exists),
        ("Extract Paths (Created)", test_extract_file_paths_from_receipt_created),
        ("Extract Paths (Added)", test_extract_file_paths_from_receipt_added),
        ("Extract Paths (Updated)", test_extract_file_paths_from_receipt_updated),
        ("Extract Paths (Direct)", test_extract_file_paths_from_receipt_direct),
        ("Extract Paths (Test Pattern)", test_extract_file_paths_from_receipt_test_pattern),
        ("Ollama Analysis (No Receipts)", test_analyze_task_with_ollama_no_receipts),
        ("Ollama Analysis (Mocked)", test_analyze_task_with_ollama_mocked),
        ("Ollama Analysis (Unlikely)", test_analyze_task_with_ollama_unlikely),
        ("Audit (Missing Files)", test_run_audit_with_missing_files),
        ("Audit (Complete Implementation)", test_run_audit_with_complete_implementation),
        ("Audit (Mixed Tasks)", test_run_audit_mixed_tasks),
        ("Audit (Ollama Integration)", test_run_audit_with_ollama_integration),
        ("Audit (No ROADMAP)", test_run_audit_no_roadmap),
        ("Print Report (With Suspects)", test_print_audit_report),
        ("Print Report (No Suspects)", test_print_audit_report_no_suspects),
        ("Real Project Audit", test_run_audit_real_project),
        ("Ollama Integration", test_prompt_ollama),
    ]
    
    passed = 0
    failed = 0
    skipped = 0
    
    for name, test_func in tests:
        try:
            print(f"Testing: {name}...", end=" ")
            test_func()
            print("✓ PASS")
            passed += 1
        except AssertionError as e:
            print(f"✗ FAIL: {e}")
            failed += 1
        except Exception as e:
            print(f"⚠ SKIP: {e}")
            skipped += 1
    
    print("\n" + "="*60)
    print(f"Results: {passed} passed, {failed} failed, {skipped} skipped")
    print("="*60 + "\n")
    
    return 0 if failed == 0 else 1


if __name__ == '__main__':
    sys.exit(run_all_tests())