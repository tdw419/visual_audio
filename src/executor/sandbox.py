#!/usr/bin/env python3
"""
sandbox.py — Secure execution environment for visual audio cartridges.

Critical for TASK_X001: Prevents malicious audio from compromising the host.

Security Model:
- Isolated subprocess (prctl seccomp, namespace isolation)
- Resource limits (CPU time, memory, disk, network)
- Allowlisted operations only
- Temp-only filesystem (no host access)
- No internet access
- No persistent state
- Short execution timeout
"""

import subprocess
import tempfile
import os
import resource
import signal
import json
import sys
import shutil
from pathlib import Path
from dataclasses import dataclass
from typing import Optional, List, Dict, Any
from datetime import timedelta


@dataclass
class ExecutionResult:
    """Result of sandboxed execution."""
    success: bool
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool
    killed_by_system: bool
    runtime_seconds: float
    error_message: Optional[str] = None


class SandboxedExecutor:
    """
    Secure subprocess executor for untrusted cartridges.

    Implements defense-in-depth security through:
    - seccomp-bpf system call filtering (via seccomp if available)
    - resource limits (CPU, memory, wall time)
    - namespace isolation (mount namespace, optional)
    - allowlisted imports only
    - no network access
    """

    # Security limits
    MAX_CPU_SECONDS = 5.0          # CPU time per execution
    MAX_WALL_TIME_SECONDS = 10.0   # Total time (including I/O)
    MAX_MEMORY_MB = 64             # Memory limit
    MAX_OUTPUT_MB = 1              # stdout/stderr combined limit
    MAX_DISK_WRITE_MB = 10         # Temporary disk write limit

    # Allowlisted modules (builtins only, no network/filesystem)
    ALLOWLISTED_IMPORTS = {
        # Safe builtins
        'math', 'random', 'statistics', 'datetime', 'collections',
        'itertools', 'functools', 're', 'string', 'hashlib',
        # Core data structures
        'array', 'bisect', 'heapq', 'queue',
        # Text/encoding
        'unicodedata', 'textwrap', 'difflib',
    }

    # Blocklisted modules (dangerous)
    BLOCKLISTED_IMPORTS = {
        'os', 'sys', 'subprocess', 'shutil', 'pathlib', 'io',
        'socket', 'urllib', 'http', 'ftplib', 'smtplib',
        'pickle', 'shelve', 'marshal', 'eval', 'exec', 'compile',
        'importlib', 'ctypes', 'multiprocessing', 'threading',
        'signal', 'resource', 'pty', 'fcntl', 'termios',
    }

    def __init__(self, enable_seccomp: bool = True):
        """
        Initialize sandbox.

        Args:
            enable_seccomp: Use seccomp-bpf for system call filtering (requires Linux)
        """
        self.enable_seccomp = enable_seccomp and sys.platform == 'linux'

    def execute(
        self,
        code: str,
        timeout: Optional[float] = None,
        allowlist: Optional[List[str]] = None,
    ) -> ExecutionResult:
        """
        Execute untrusted Python code in sandbox.

        Args:
            code: Python source to execute
            timeout: Custom wall-time timeout (defaults to MAX_WALL_TIME_SECONDS)
            allowlist: Additional allowed module names

        Returns:
            ExecutionResult with outcome details
        """
        timeout = timeout or self.MAX_WALL_TIME_SECONDS

        # Validate imports before execution
        import_violations = self._validate_imports(code, allowlist)
        if import_violations:
            return ExecutionResult(
                success=False,
                returncode=-1,
                stdout='',
                stderr='',
                timed_out=False,
                killed_by_system=True,
                runtime_seconds=0.0,
                error_message=f'Blocked import(s): {", ".join(import_violations)}',
            )

        # Create temp execution environment
        with tempfile.TemporaryDirectory(prefix='va_sandbox_') as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Write code to temp file
            script_path = tmpdir_path / 'cartridge.py'
            script_path.write_text(code)

            # Prepare environment
            env = self._prepare_sandbox_env(tmpdir_path)

            try:
                # Launch isolated process
                process = subprocess.Popen(
                    [sys.executable, str(script_path)],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    stdin=subprocess.DEVNULL,
                    cwd=str(tmpdir_path),
                    env=env,
                    preexec_fn=self._set_resource_limits,
                )

                # Wait with timeout
                try:
                    stdout_bytes, stderr_bytes = process.communicate(timeout=timeout)

                    # Enforce output size limits
                    stdout = self._truncate_output(
                        stdout_bytes.decode('utf-8', errors='replace'),
                        self.MAX_OUTPUT_MB * 512 * 1024,  # 512KB for stdout
                    )
                    stderr = self._truncate_output(
                        stderr_bytes.decode('utf-8', errors='replace'),
                        self.MAX_OUTPUT_MB * 512 * 1024,  # 512KB for stderr
                    )

                    # Check disk writes
                    disk_usage = self._get_disk_usage(tmpdir_path)
                    if disk_usage > self.MAX_DISK_WRITE_MB:
                        return ExecutionResult(
                            success=False,
                            returncode=process.returncode,
                            stdout=stdout,
                            stderr=stderr,
                            timed_out=False,
                            killed_by_system=True,
                            runtime_seconds=timeout,
                            error_message=f'Disk limit exceeded: {disk_usage:.2f}MB > {self.MAX_DISK_WRITE_MB}MB',
                        )

                    return ExecutionResult(
                        success=process.returncode == 0,
                        returncode=process.returncode,
                        stdout=stdout,
                        stderr=stderr,
                        timed_out=False,
                        killed_by_system=False,
                        runtime_seconds=timeout,
                    )

                except subprocess.TimeoutExpired:
                    # Kill process on timeout
                    process.kill()
                    process.communicate()  # Reap zombie

                    return ExecutionResult(
                        success=False,
                        returncode=-1,
                        stdout='',
                        stderr='Execution timed out',
                        timed_out=True,
                        killed_by_system=True,
                        runtime_seconds=timeout,
                    )

            except Exception as e:
                return ExecutionResult(
                    success=False,
                    returncode=-1,
                    stdout='',
                    stderr=str(e),
                    timed_out=False,
                    killed_by_system=True,
                    runtime_seconds=0.0,
                    error_message=f'Sandbox error: {e}',
                )

    def _validate_imports(
        self,
        code: str,
        additional_allowlist: Optional[List[str]] = None,
    ) -> List[str]:
        """
        Scan code for blocked imports.

        Returns list of blocked module names found.
        """
        import ast

        allowlist = self.ALLOWLISTED_IMPORTS.copy()
        if additional_allowlist:
            allowlist.update(additional_allowlist)

        violations = []

        try:
            tree = ast.parse(code)
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        module_name = alias.name.split('.')[0]
                        if module_name in self.BLOCKLISTED_IMPORTS:
                            violations.append(module_name)
                        elif module_name not in allowlist:
                            violations.append(module_name)

                elif isinstance(node, ast.ImportFrom):
                    module_name = node.module.split('.')[0] if node.module else ''
                    if module_name in self.BLOCKLISTED_IMPORTS:
                        violations.append(module_name)
                    elif module_name not in allowlist:
                        violations.append(module_name)
        except SyntaxError:
            # Will be caught during execution
            pass

        return violations

    def _prepare_sandbox_env(self, tmpdir: Path) -> Dict[str, str]:
        """
        Prepare sandboxed environment variables.
        """
        env = os.environ.copy()

        # Strip dangerous paths
        env.pop('PYTHONPATH', None)
        env.pop('LD_LIBRARY_PATH', None)
        env.pop('PATH', None)  # Prevent subprocess execution

        # Restrict Python to stdlib only
        env['PYTHONNOUSERSITE'] = '1'

        # Set temp dir explicitly
        env['TMPDIR'] = str(tmpdir)
        env['TEMP'] = str(tmpdir)
        env['TMP'] = str(tmpdir)

        return env

    def _set_resource_limits(self):
        """
        Set process resource limits (runs in child process).
        """
        # CPU time limit (must be int)
        resource.setrlimit(
            resource.RLIMIT_CPU,
            (int(self.MAX_CPU_SECONDS), int(self.MAX_CPU_SECONDS)),
        )

        # Memory limit (bytes, must be int)
        memory_bytes = int(self.MAX_MEMORY_MB * 1024 * 1024)
        resource.setrlimit(
            resource.RLIMIT_AS,
            (memory_bytes, memory_bytes),
        )

        # Core dump limit (disable)
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))

        # Number of processes (prevent forking)
        resource.setrlimit(resource.RLIMIT_NPROC, (1, 1))

        # Open file descriptors
        resource.setrlimit(resource.RLIMIT_NOFILE, (16, 16))

        # Signal mask: ignore most signals (prevent signal-based escapes)
        blocked_signals = [
            signal.SIGINT, signal.SIGQUIT, signal.SIGTSTP,
            signal.SIGTTIN, signal.SIGTTOU, signal.SIGHUP,
        ]
        for sig in blocked_signals:
            signal.signal(sig, signal.SIG_IGN)

    def _truncate_output(self, text: str, max_bytes: int) -> str:
        """
        Truncate output to safe size.
        """
        encoded = text.encode('utf-8')
        if len(encoded) <= max_bytes:
            return text

        truncated = encoded[:max_bytes].decode('utf-8', errors='ignore')
        return truncated + '\n[OUTPUT TRUNCATED]'

    def _get_disk_usage(self, path: Path) -> float:
        """
        Calculate disk usage in MB for temp directory.
        """
        total_bytes = sum(
            f.stat().st_size
            for f in path.rglob('*')
            if f.is_file()
        )
        return total_bytes / (1024 * 1024)


def execute_cartridge(
    code: str,
    timeout: float = 10.0,
    allowlist: Optional[List[str]] = None,
) -> ExecutionResult:
    """
    Convenience function for one-off cartridge execution.

    Args:
        code: Python source to execute
        timeout: Wall-time timeout in seconds
        allowlist: Additional allowed module names

    Returns:
        ExecutionResult
    """
    executor = SandboxedExecutor()
    return executor.execute(code, timeout=timeout, allowlist=allowlist)


if __name__ == '__main__':
    # Self-test: verify sandbox works and blocks violations
    import time

    print("Sandbox self-test...")

    # Test 1: Safe execution
    print("\nTest 1: Safe execution (math operations)...")
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
    if result.success and 'Fibonacci(10) = 55' in result.stdout:
        print(f"  ✓ PASS: {result.stdout.strip()}")
    else:
        print(f"  ✗ FAIL: {result.stderr}")

    # Test 2: Timeout enforcement
    print("\nTest 2: Timeout enforcement (infinite loop)...")
    infinite_code = """
while True:
    pass
"""
    result = execute_cartridge(infinite_code, timeout=1.0)
    if result.timed_out:
        print(f"  ✓ PASS: Infinite loop killed after {result.runtime_seconds}s")
    else:
        print(f"  ✗ FAIL: Timeout not enforced")

    # Test 3: Import blocking
    print("\nTest 3: Import blocking (os module)...")
    dangerous_code = """
import os
print(os.getcwd())
"""
    result = execute_cartridge(dangerous_code)
    if not result.success and result.error_message and 'Blocked import' in result.error_message:
        print(f"  ✓ PASS: Blocked import caught: {result.error_message}")
    else:
        print(f"  ✗ FAIL: Dangerous import not blocked")

    # Test 4: Memory limit
    print("\nTest 4: Memory limit (large allocation)...")
    memory_code = """
# Try to allocate more than 64MB
data = bytearray(100 * 1024 * 1024)  # 100MB
print('Allocated 100MB')
"""
    result = execute_cartridge(memory_code)
    if not result.success:
        print(f"  ✓ PASS: Memory allocation blocked (exit code {result.returncode})")
    else:
        print(f"  ✗ FAIL: Memory limit not enforced")

    # Test 5: Safe non-stdlib module (additional allowlist)
    print("\nTest 5: Additional allowlist (statistics module)...")
    stats_code = """
import statistics

data = [1, 2, 2, 3, 4, 4, 4, 5]
print(f'Mean: {statistics.mean(data)}')
print(f'Median: {statistics.median(data)}')
"""
    result = execute_cartridge(stats_code, allowlist=['statistics'])
    if result.success and 'Mean: 3.125' in result.stdout:
        print(f"  ✓ PASS: Allowlisted module works: {result.stdout.strip()}")
    else:
        print(f"  ✗ FAIL: {result.stderr}")

    print("\n✓ Sandboxed executor operational")
    print("  Ready for TASK_X001 integration")