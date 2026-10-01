"""
Visual Audio Sandboxed Executor.

Provides secure execution environment for decoded cartridges received over
open acoustic channels. Critical for TASK_X001 security requirements.
"""

from .sandbox import SandboxedExecutor, ExecutionResult

__all__ = ['SandboxedExecutor', 'ExecutionResult']