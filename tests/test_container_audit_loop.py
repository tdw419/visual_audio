#!/usr/bin/env python3
"""
Tests for container audit loop functionality.
Standalone test runner (no pytest dependency).
"""

import json
import os
import tempfile
import shutil
import sys
from pathlib import Path


class TestResults:
    """Track test results."""
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.errors = []
    
    def add_pass(self):
        self.passed += 1
    
    def add_fail(self, test_name, message):
        self.failed += 1
        self.errors.append(f"{test_name}: {message}")
    
    def report(self):
        print(f"\n{'='*60}")
        print(f"Test Results: {self.passed} passed, {self.failed} failed")
        print(f"{'='*60}")
        if self.errors:
            print("\nFailed tests:")
            for error in self.errors:
                print(f"  ✗ {error}")
        print()
        return self.failed == 0


class TestContainerAuditLoop:
    """Test suite for ollama_prompt.py audit functionality."""
    
    def __init__(self):
        self.test_dir = None
        self.original_dir = None
        self.results = TestResults()
    
    def setup(self):
        """Set up test environment."""
        self.test_dir = tempfile.mkdtemp()
        self.original_dir = os.getcwd()
        os.chdir(self.test_dir)
        
        # Import the audit module
        sys.path.insert(0, os.path.join(self.original_dir, 'tools'))
        from ollama_prompt import parse_roadmap_tasks, verify_file_exists, verify_test_exists, run_audit
        self.parse_roadmap_tasks = parse_roadmap_tasks
        self.verify_file_exists = verify_file_exists
        self.verify_test_exists = verify_test_exists
        self.run_audit = run_audit
    
    def teardown(self):
        """Clean up test environment."""
        if self.original_dir:
            os.chdir(self.original_dir)
        if self.test_dir and os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir, ignore_errors=True)
    
    def assert_equals(self, actual, expected, test_name):
        if actual == expected:
            self.results.add_pass()
            print(f"  ✓ {test_name}")
        else:
            self.results.add_fail(test_name, f"Expected {expected}, got {actual}")
            print(f"  ✗ {test_name}")
    
    def assert_true(self, condition, test_name):
        if condition:
            self.results.add_pass()
            print(f"  ✓ {test_name}")
        else:
            self.results.add_fail(test_name, "Condition was False")
            print(f"  ✗ {test_name}")
    
    def run_all_tests(self):
        """Run all tests."""
        print("\n" + "="*60)
        print("Container Audit Loop Tests")
        print("="*60 + "\n")
        
        # Test 1: Basic ROADMAP parsing
        self.setup()
        try:
            roadmap_content = """# Phase 1
## Section A

*** TASK_001: First task ***
Status: PENDING

*** TASK_002: Second task ***
Status: COMPLETE
Completed: 2026-07-15
Receipt: Created file src/main.py

## Section B

*** TASK_003: Third task ***
Status: COMPLETE
Receipt: Implemented feature in tests/test_feature.py
"""
            with open('ROADMAP.md', 'w') as f:
                f.write(roadmap_content)
            
            tasks = self.parse_roadmap_tasks('ROADMAP.md')
            self.assert_equals(len(tasks), 3, "test_parse_roadmap_tasks_basic - count")
            self.assert_equals(tasks[0]['id'], 'TASK_001', "test_parse_roadmap_tasks_basic - id")
            self.assert_equals(tasks[0]['status'], 'PENDING', "test_parse_roadmap_tasks_basic - status")
            self.assert_equals(tasks[1]['receipts'], ['Created file src/main.py'], "test_parse_roadmap_tasks_basic - receipts")
        except Exception as e:
            self.results.add_fail("test_parse_roadmap_tasks_basic", str(e))
        finally:
            self.teardown()
        
        # Test 2: Multiple receipts
        self.setup()
        try:
            roadmap_content = """
*** TASK_001: Complex task ***
Status: COMPLETE
Completed: 2026-07-19
Receipt: Created file src/codec.py
Receipt: Added tests/test_codec.py
Receipt: Updated README.md
"""
            with open('ROADMAP.md', 'w') as f:
                f.write(roadmap_content)
            
            tasks = self.parse_roadmap_tasks('ROADMAP.md')
            self.assert_equals(len(tasks), 1, "test_parse_roadmap_tasks_multiple_receipts - count")
            self.assert_equals(len(tasks[0]['receipts']), 3, "test_parse_roadmap_tasks_multiple_receipts - receipt count")
        except Exception as e:
            self.results.add_fail("test_parse_roadmap_tasks_multiple_receipts", str(e))
        finally:
            self.teardown()
        
        # Test 3: File exists - true
        self.setup()
        try:
            os.makedirs('src', exist_ok=True)
            with open('src/test.py', 'w') as f:
                f.write('# test file')
            
            self.assert_true(self.verify_file_exists('src/test.py', '.'), "test_verify_file_exists_true")
        except Exception as e:
            self.results.add_fail("test_verify_file_exists_true", str(e))
        finally:
            self.teardown()
        
        # Test 4: File exists - false
        self.setup()
        try:
            self.assert_true(not self.verify_file_exists('src/missing.py', '.'), "test_verify_file_exists_false")
        except Exception as e:
            self.results.add_fail("test_verify_file_exists_false", str(e))
        finally:
            self.teardown()
        
        # Test 5: Test file exists
        self.setup()
        try:
            os.makedirs('tests', exist_ok=True)
            with open('tests/test_feature.py', 'w') as f:
                f.write('# test')
            
            self.assert_true(self.verify_test_exists('tests/test_feature.py', '.'), "test_verify_test_exists_true")
        except Exception as e:
            self.results.add_fail("test_verify_test_exists_true", str(e))
        finally:
            self.teardown()
        
        # Test 6: Audit identifies missing files
        self.setup()
        try:
            roadmap_content = """
*** TASK_001: Missing file task ***
Status: COMPLETE
Completed: 2026-07-19
Receipt: Created file src/missing.py

*** TASK_002: Valid task ***
Status: COMPLETE
Completed: 2026-07-19
Receipt: Created file src/valid.py
"""
            with open('ROADMAP.md', 'w') as f:
                f.write(roadmap_content)
            
            os.makedirs('src', exist_ok=True)
            with open('src/valid.py', 'w') as f:
                f.write('# valid')
            
            report = self.run_audit('.', 'audit_report.json')
            
            self.assert_true('summary' in report, "test_run_audit_identifies_missing_files - has summary")
            self.assert_true('suspect_tasks' in report, "test_run_audit_identifies_missing_files - has suspect_tasks")
            self.assert_equals(report['summary']['completed_tasks'], 2, "test_run_audit_identifies_missing_files - completed count")
            self.assert_equals(report['summary']['suspect_tasks'], 1, "test_run_audit_identifies_missing_files - suspect count")
            
            if report['suspect_tasks']:
                suspect = report['suspect_tasks'][0]
                self.assert_equals(suspect['task_id'], 'TASK_001', "test_run_audit_identifies_missing_files - suspect id")
                self.assert_true(suspect['is_suspect'], "test_run_audit_identifies_missing_files - is_suspect")
                self.assert_true(any('missing files' in issue.lower() for issue in suspect['issues']), 
                                "test_run_audit_identifies_missing_files - issue message")
        except Exception as e:
            self.results.add_fail("test_run_audit_identifies_missing_files", str(e))
        finally:
            self.teardown()
        
        # Test 7: Audit flags tasks with no receipts
        self.setup()
        try:
            roadmap_content = """
*** TASK_001: No receipts ***
Status: COMPLETE
Completed: 2026-07-19
"""
            with open('ROADMAP.md', 'w') as f:
                f.write(roadmap_content)
            
            report = self.run_audit('.', 'audit_report.json')
            
            self.assert_equals(report['summary']['suspect_tasks'], 1, "test_run_audit_no_receipts - suspect count")
            if report['suspect_tasks']:
                suspect = report['suspect_tasks'][0]
                self.assert_true('no receipts' in suspect['issues'][0].lower(), "test_run_audit_no_receipts - issue message")
        except Exception as e:
            self.results.add_fail("test_run_audit_no_receipts", str(e))
        finally:
            self.teardown()
        
        # Test 8: Audit ignores pending tasks
        self.setup()
        try:
            roadmap_content = """
*** TASK_001: Pending task ***
Status: PENDING
"""
            with open('ROADMAP.md', 'w') as f:
                f.write(roadmap_content)
            
            report = self.run_audit('.', 'audit_report.json')
            
            self.assert_equals(report['summary']['pending_tasks'], 1, "test_run_audit_ignores_pending_tasks - pending count")
            self.assert_equals(report['summary']['completed_tasks'], 0, "test_run_audit_ignores_pending_tasks - completed count")
            self.assert_equals(report['summary']['suspect_tasks'], 0, "test_run_audit_ignores_pending_tasks - suspect count")
        except Exception as e:
            self.results.add_fail("test_run_audit_ignores_pending_tasks", str(e))
        finally:
            self.teardown()
        
        # Test 9: Audit identifies missing test files
        self.setup()
        try:
            roadmap_content = """
*** TASK_001: Missing test ***
Status: COMPLETE
Completed: 2026-07-19
Receipt: Added test in tests/test_missing.py
"""
            with open('ROADMAP.md', 'w') as f:
                f.write(roadmap_content)
            
            report = self.run_audit('.', 'audit_report.json')
            
            self.assert_equals(report['summary']['suspect_tasks'], 1, "test_run_audit_missing_test_files - suspect count")
            if report['suspect_tasks']:
                suspect = report['suspect_tasks'][0]
                self.assert_true(any('missing test' in issue.lower() for issue in suspect['issues']), 
                                "test_run_audit_missing_test_files - issue message")
        except Exception as e:
            self.results.add_fail("test_run_audit_missing_test_files", str(e))
        finally:
            self.teardown()
        
        # Test 10: Audit generates report file
        self.setup()
        try:
            roadmap_content = """
*** TASK_001: Test task ***
Status: COMPLETE
Completed: 2026-07-19
Receipt: Created file src/test.py
"""
            with open('ROADMAP.md', 'w') as f:
                f.write(roadmap_content)
            
            os.makedirs('src', exist_ok=True)
            with open('src/test.py', 'w') as f:
                f.write('# test')
            
            report = self.run_audit('.', 'audit_report.json')
            
            self.assert_true(os.path.exists('audit_report.json'), "test_run_audit_generates_report_file - file exists")
            
            with open('audit_report.json', 'r') as f:
                file_report = json.load(f)
            
            self.assert_equals(file_report['timestamp'], report['timestamp'], "test_run_audit_generates_report_file - timestamp")
            self.assert_equals(file_report['summary'], report['summary'], "test_run_audit_generates_report_file - summary")
        except Exception as e:
            self.results.add_fail("test_run_audit_generates_report_file", str(e))
        finally:
            self.teardown()
        
        # Test 11: Audit handles missing ROADMAP
        self.setup()
        try:
            report = self.run_audit('.', 'audit_report.json')
            
            self.assert_true('error' in report, "test_run_audit_handles_missing_roadmap - has error")
            self.assert_true('ROADMAP.md not found' in report['error'], "test_run_audit_handles_missing_roadmap - error message")
            self.assert_equals(report['suspect_tasks'], [], "test_run_audit_handles_missing_roadmap - no suspects")
        except Exception as e:
            self.results.add_fail("test_run_audit_handles_missing_roadmap", str(e))
        finally:
            self.teardown()
        
        # Test 12: Audit summary statistics
        self.setup()
        try:
            roadmap_content = """
*** TASK_001: Valid task 1 ***
Status: COMPLETE
Completed: 2026-07-19
Receipt: Created file src/valid1.py

*** TASK_002: Valid task 2 ***
Status: COMPLETE
Completed: 2026-07-19
Receipt: Created file src/valid2.py

*** TASK_003: Suspect task ***
Status: COMPLETE
Completed: 2026-07-19
Receipt: Created file src/missing.py

*** TASK_004: Pending task ***
Status: PENDING
"""
            with open('ROADMAP.md', 'w') as f:
                f.write(roadmap_content)
            
            os.makedirs('src', exist_ok=True)
            with open('src/valid1.py', 'w') as f:
                f.write('# valid1')
            with open('src/valid2.py', 'w') as f:
                f.write('# valid2')
            
            report = self.run_audit('.', 'audit_report.json')
            
            self.assert_equals(report['summary']['total_tasks'], 4, "test_run_audit_summary_statistics - total")
            self.assert_equals(report['summary']['completed_tasks'], 3, "test_run_audit_summary_statistics - completed")
            self.assert_equals(report['summary']['pending_tasks'], 1, "test_run_audit_summary_statistics - pending")
            self.assert_equals(report['summary']['suspect_tasks'], 1, "test_run_audit_summary_statistics - suspects")
            self.assert_true('suspect_percentage' in report['summary'], "test_run_audit_summary_statistics - has percentage")
        except Exception as e:
            self.results.add_fail("test_run_audit_summary_statistics", str(e))
        finally:
            self.teardown()
        
        return self.results.report()


if __name__ == '__main__':
    tester = TestContainerAuditLoop()
    success = tester.run_all_tests()
    sys.exit(0 if success else 1)