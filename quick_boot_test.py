#!/usr/bin/env python3
"""
Quick boot test with LUI fix to see actual behavior.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / 'tools'))
from boot_xv6_gpu import boot_xv6_on_gpu

# Run a short boot test
boot_xv6_on_gpu('/tmp/xv6-riscv/kernel/kernel', command=None, autonomous=False)