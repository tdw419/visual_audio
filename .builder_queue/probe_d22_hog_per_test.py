"""DEFECT-22 next_step (a), leg 2: per-test VmHWM attribution inside test_gh18_syscall_abi.py.

Foreground on purpose (uncapped scope). For each test id: fork a fresh interpreter,
run ONLY that test, read ru_maxrss (kB) via resource in the child, print one line.
Child rc and verdict recorded. Output: output/d22_hog_per_test.txt
"""
import os
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IDS = [
    "test_gh18_admitted_tile_computes_word_exact",
    "test_gh18_dispatch_rewrite_is_table_lookup_not_selector_chain",
    "test_gh18_bakes_and_abi_version_word",
    "test_gh18_runner_line_budget_and_clean_imports",
    "test_gh18_unknown_syscall_hits_handler_clean",
    "test_gh18_two_syscalls_still_dispatch",
    "test_gh18_tile_preserves_returning_task_a0",
    "test_gh18_syscall_table_window_reserved",
    "test_gh18_mid_syscall_tick_deferred",
    "test_gh18_dispatch_identity_mapped_with_paging_armed",
    "test_gh18_admit_syscall_deterministic_end_to_end",
    "test_gh18_negative_and_huge_sysn_trap_clean",
    "test_gh18_patch_isolation_positive_whitelist",
    "test_gh18_unproven_tile_rejected_table_untouched",
]

CHILD = r"""
import resource, sys
import pytest
tid = sys.argv[1]
rc = pytest.main([tid, "-q", "--no-header", "--tb=no", "-p", "no:cacheprovider"])
hwm_kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
print(f"VMHWM_KB={hwm_kb}")
sys.exit(0 if rc == 0 else 1)
"""

OUT = os.path.join(REPO, "output", "d22_hog_per_test.txt")


def main():
    lines = []
    for tid in IDS:
        full = f"tests/test_gh18_syscall_abi.py::{tid}"
        p = subprocess.run([sys.executable, "-c", CHILD, full],
                           capture_output=True, text=True, cwd=REPO, timeout=600)
        hwm = "?"
        for ln in p.stdout.splitlines():
            if ln.startswith("VMHWM_KB="):
                hwm = ln.split("=", 1)[1]
        verdict = "PASS" if p.returncode == 0 else f"RC={p.returncode}"
        try:
            mb = int(hwm) / 1024.0
            lines.append(f"{mb:9.1f} MB  {verdict}  {tid}")
        except ValueError:
            lines.append(f"{'?':>9}  {verdict}  {tid}  (no VMHWM line)")
        print(lines[-1], flush=True)
    with open(OUT, "w") as f:
        f.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
