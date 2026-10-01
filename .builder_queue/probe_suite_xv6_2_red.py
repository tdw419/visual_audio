#!/usr/bin/env python3
"""Probe to demonstrate RED for L1, L2, L4 against pre-fix test_xv6_boot_regression.py.

Evaluates HEAD:tests/test_xv6_boot_regression.py and HEAD:tools/boot_xv6_gpu.py:
- L1: Verify that pre-fix lacks SHA256 pin assertion (only checks exists / ELF magic).
- L2: Verify that pre-fix tools/boot_xv6_gpu.py hardcodes /tmp/xv6-riscv/fs.img without caller control.
- L4: Verify that pre-fix fails with bare AssertionError without machine-readable verdict tokens.
"""

import hashlib
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

def check_l1_red():
    # Read HEAD:tests/test_xv6_boot_regression.py
    cmd = ["git", "show", "HEAD:tests/test_xv6_boot_regression.py"]
    res = subprocess.run(cmd, capture_output=True, text=True, cwd=REPO_ROOT, check=True)
    content = res.stdout

    # Pinned hashes from spec
    kernel_sha = "9ca0c366a69833f511b4a2848cb3038c1e816ee8ce9c3ac9cad07fd726ed6a27"
    fs_sha = "f31516ca7bb190f38d6ef71ef7e488ee4d07d50700dd06c6ecbec53e0d4841ed"

    has_kernel_sha = kernel_sha in content
    has_fs_sha = fs_sha in content

    if not has_kernel_sha and not has_fs_sha:
        print("[L1 RED] Pre-fix test has no sha256 pin for kernel or fs image (checks exists() only)")
        return True
    return False

def check_l2_red():
    # Read HEAD:tools/boot_xv6_gpu.py
    cmd = ["git", "show", "HEAD:tools/boot_xv6_gpu.py"]
    res = subprocess.run(cmd, capture_output=True, text=True, cwd=REPO_ROOT, check=True)
    content = res.stdout

    # Pre-fix has hardcoded Path('/tmp/xv6-riscv/fs.img')
    has_env_fs = "XV6_FS_PATH" in content
    has_tmp_hardcode = "Path('/tmp/xv6-riscv/fs.img')" in content

    if not has_env_fs and has_tmp_hardcode:
        print("[L2 RED] Pre-fix tools/boot_xv6_gpu.py hardcodes /tmp/xv6-riscv/fs.img without XV6_FS_PATH")
        return True
    return False

def check_l4_red():
    # Read HEAD:tests/test_xv6_boot_regression.py
    cmd = ["git", "show", "HEAD:tests/test_xv6_boot_regression.py"]
    res = subprocess.run(cmd, capture_output=True, text=True, cwd=REPO_ROOT, check=True)
    content = res.stdout

    # Pre-fix has bare AssertionError without verdict tokens
    tokens = [
        "XV6_VERDICT: SHELL_REACHED",
        "NO_SHELL_STALL_PC",
        "NO_SHELL_TIMEOUT",
        "INPUT_SHA_MISMATCH",
        "FS_ABSENT",
        "LSB_FORMAT_UNSUPPORTED",
    ]
    present_tokens = [t for t in tokens if t in content]
    has_bare_assert = 'assert False, f"xv6 did not reach shell: {prompt_msg}"' in content

    if not present_tokens and has_bare_assert:
        print(f"[L4 RED] Pre-fix test uses bare AssertionError without verdict tokens (found bare assert, 0 tokens)")
        return True
    return False

if __name__ == "__main__":
    r1 = check_l1_red()
    r2 = check_l2_red()
    r4 = check_l4_red()
    if r1 and r2 and r4:
        print("\nPROBE_VERDICT: ALL LEGS RED PRE-FIX")
        sys.exit(0)
    else:
        print(f"\nPROBE_VERDICT: UNEXPECTED (r1={r1}, r2={r2}, r4={r4})")
        sys.exit(1)
