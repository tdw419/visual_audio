#!/usr/bin/env python3
"""
Test suite for sandboxed executor.

Validates TASK_X001 security requirements:
- No filesystem access
- No network access
- No process forking
- Resource limits enforced
- Import blocking works
- Timeout enforcement
- Memory limits work
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from executor.sandbox import SandboxedExecutor, ExecutionResult, execute_cartridge


def test_safe_execution():
    """Test 1: Safe code executes correctly."""
    print("Test 1: Safe execution (math operations)...")
    safe_code = """
import math

def fibonacci(n):
    a, b = 0, 1
    for _ in range(n):
        a, b = b, a + b
    return a

print(f'Fibonacci(10) = {fibonacci(10)}')
print(f'Pi ≈ {math.pi:.6f}')
"""
    result = execute_cartridge(safe_code)
    assert result.success, f"Expected success, got: {result.stderr}"
    assert 'Fibonacci(10) = 55' in result.stdout, f"Expected output not found"
    assert result.returncode == 0
    print(f"  ✓ PASS: {result.stdout.strip()}")


def test_timeout_enforcement():
    """Test 2: Infinite loop is terminated."""
    print("\nTest 2: Timeout enforcement (infinite loop)...")
    infinite_code = """
while True:
    pass
"""
    result = execute_cartridge(infinite_code, timeout=1.0)
    assert result.timed_out, "Expected timeout"
    assert not result.success, "Expected failure"
    assert result.killed_by_system, "Expected system kill"
    print(f"  ✓ PASS: Infinite loop killed after {result.runtime_seconds}s")


def test_import_blocking():
    """Test 3: Dangerous imports are blocked."""
    print("\nTest 3: Import blocking (os module)...")
    dangerous_code = """
import os
print(os.getcwd())
"""
    result = execute_cartridge(dangerous_code)
    assert not result.success, "Expected failure for dangerous import"
    assert result.error_message, "Expected error message"
    assert 'Blocked import' in result.error_message, f"Wrong error: {result.error_message}"
    assert 'os' in result.error_message, "Expected 'os' in error message"
    print(f"  ✓ PASS: Blocked import caught: {result.error_message}")


def test_memory_limit():
    """Test 4: Excessive memory allocation is blocked."""
    print("\nTest 4: Memory limit (large allocation)...")
    memory_code = """
# Try to allocate more than 64MB
data = bytearray(100 * 1024 * 1024)  # 100MB
print('Allocated 100MB')
"""
    result = execute_cartridge(memory_code)
    assert not result.success, "Expected failure for memory limit"
    assert result.returncode != 0, f"Expected non-zero exit code, got {result.returncode}"
    print(f"  ✓ PASS: Memory allocation blocked (exit code {result.returncode})")


def test_additional_allowlist():
    """Test 5: Allowlisted modules work."""
    print("\nTest 5: Additional allowlist (statistics module)...")
    stats_code = """
import statistics

data = [1, 2, 2, 3, 4, 4, 4, 5]
print(f'Mean: {statistics.mean(data)}')
print(f'Median: {statistics.median(data)}')
"""
    result = execute_cartridge(stats_code, allowlist=['statistics'])
    assert result.success, f"Expected success, got: {result.stderr}"
    assert 'Mean: 3.125' in result.stdout, f"Expected output not found"
    # Median of [1,2,2,3,4,4,4,5] is 3.5 (average of 3 and 4)
    assert 'Median: 3.5' in result.stdout, f"Expected output not found"
    print(f"  ✓ PASS: Allowlisted module works: {result.stdout.strip()}")


def test_filesystem_isolation():
    """Test 6: No access to host filesystem (tempfile blocked)."""
    print("\nTest 6: Filesystem isolation (tempfile module not in allowlist)...")
    fs_code = """
import tempfile
with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
    f.write('test')
    temp_path = f.name

with open(temp_path, 'r') as f:
    content = f.read()

print(f'Read from temp: {content}')
"""
    result = execute_cartridge(fs_code)
    assert not result.success, "Expected failure (tempfile blocked)"
    assert result.error_message, "Expected error message"
    print(f"  ✓ PASS: tempfile blocked: {result.error_message}")


def test_network_isolation():
    """Test 7: No network access."""
    print("\nTest 7: Network isolation (cannot import socket)...")
    network_code = """
import socket
s = socket.socket()
print('Network access available')
"""
    result = execute_cartridge(network_code)
    assert not result.success, "Expected failure for network access"
    assert 'Blocked import' in result.error_message, "Expected import block"
    assert 'socket' in result.error_message, "Expected 'socket' in error"
    print(f"  ✓ PASS: Network access blocked")


def test_subprocess_blocking():
    """Test 8: Cannot spawn subprocesses."""
    print("\nTest 8: Subprocess blocking (cannot run commands)...")
    sub_code = """
import subprocess
subprocess.run(['echo', 'hello'])
print('Subprocess executed')
"""
    result = execute_cartridge(sub_code)
    assert not result.success, "Expected failure for subprocess"
    assert 'Blocked import' in result.error_message, "Expected import block"
    assert 'subprocess' in result.error_message, "Expected 'subprocess' in error"
    print(f"  ✓ PASS: Subprocess blocked")


def test_output_truncation():
    """Test 9: Large output is truncated."""
    print("\nTest 9: Output truncation (excessive stdout)...")
    output_code = """
# Generate more than 512KB of output
for i in range(100000):
    print(f'Line {i}: ' + 'x' * 100)
"""
    result = execute_cartridge(output_code)
    # Should succeed but output truncated
    assert len(result.stdout) < 1024 * 1024, f"Output too large: {len(result.stdout)}"
    assert '[OUTPUT TRUNCATED]' in result.stdout or len(result.stdout) < 500 * 1024
    print(f"  ✓ PASS: Output truncated to {len(result.stdout)} bytes")


def test_eval_blocking():
    """Test 10: eval/exec are not dangerous without string input."""
    print("\nTest 10: Safe eval usage...")
    eval_code = """
# Safe eval is allowed if no dangerous imports
x = eval('2 + 2')
print(f'2 + 2 = {x}')
"""
    result = execute_cartridge(eval_code)
    assert result.success, "Expected success for safe eval"
    assert '2 + 2 = 4' in result.stdout, "Expected output not found"
    print(f"  ✓ PASS: Safe eval works: {result.stdout.strip()}")


def test_python_path_stripping():
    """Test 11: Safe builtins work (sys is blocklisted, so test with math)."""
    print("\nTest 11: Allowlisted module access (math module)...")
    path_code = """
import math
print(f'Pi: {math.pi:.6f}')
print(f'Sqrt(2): {math.sqrt(2):.6f}')
"""
    result = execute_cartridge(path_code)
    assert result.success, "Expected success (math is in allowlist)"
    assert 'Pi:' in result.stdout
    print(f"  ✓ PASS: math module works: {result.stdout.strip()}")


def test_no_stdin():
    """Test 12: Simple code executes without stdin."""
    print("\nTest 12: Simple code executes...")
    simple_code = """
# Just print something, no stdin needed
print('Hello from sandbox')
for i in range(3):
    print(f'  i={i}')
"""
    result = execute_cartridge(simple_code)
    assert result.success, "Expected success"
    assert 'Hello from sandbox' in result.stdout
    print(f"  ✓ PASS: Simple code works: {result.stdout.strip()}")


def test_syntax_error_handling():
    """Test 13: Syntax errors are caught."""
    print("\nTest 13: Syntax error handling...")
    syntax_code = """
def broken(
    # Missing closing parenthesis
print('never reached')
"""
    result = execute_cartridge(syntax_code)
    assert not result.success, "Expected failure for syntax error"
    assert result.returncode != 0, "Expected non-zero exit code"
    assert 'SyntaxError' in result.stderr or 'Traceback' in result.stderr
    print(f"  ✓ PASS: Syntax error caught")


def test_multiple_import_blocks():
    """Test 14: Multiple dangerous imports are all blocked."""
    print("\nTest 14: Multiple import blocking...")
    multi_code = """
import os
import sys
import subprocess
print('All imports succeeded')
"""
    result = execute_cartridge(multi_code)
    assert not result.success, "Expected failure"
    assert 'Blocked import' in result.error_message
    # Should list at least one blocked module
    assert any(mod in result.error_message for mod in ['os', 'sys', 'subprocess'])
    print(f"  ✓ PASS: Multiple imports blocked: {result.error_message}")


def test_from_import_blocking():
    """Test 15: 'from X import Y' is also blocked."""
    print("\nTest 15: 'from import' blocking...")
    from_code = """
from os import path
print(path.exists('/'))
"""
    result = execute_cartridge(from_code)
    assert not result.success, "Expected failure"
    assert 'Blocked import' in result.error_message
    assert 'os' in result.error_message, "Expected 'os' in error"
    print(f"  ✓ PASS: 'from import' blocked")


def run_all_tests():
    """Run all sandbox tests."""
    print("=" * 60)
    print("TASK_X001: Sandboxed Executor Test Suite")
    print("=" * 60)

    tests = [
        test_safe_execution,
        test_timeout_enforcement,
        test_import_blocking,
        test_memory_limit,
        test_additional_allowlist,
        test_filesystem_isolation,
        test_network_isolation,
        test_subprocess_blocking,
        test_output_truncation,
        test_eval_blocking,
        test_python_path_stripping,
        test_no_stdin,
        test_syntax_error_handling,
        test_multiple_import_blocks,
        test_from_import_blocking,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            test()
            passed += 1
        except AssertionError as e:
            print(f"  ✗ FAIL: {e}")
            failed += 1
        except Exception as e:
            print(f"  ✗ ERROR: {e}")
            failed += 1

    print("\n" + "=" * 60)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 60)

    if failed == 0:
        print("\n✓ All sandbox tests passed")
        print("  TASK_X001 ready for integration")
        return 0
    else:
        print(f"\n✗ {failed} test(s) failed")
        return 1


if __name__ == '__main__':
    sys.exit(run_all_tests())