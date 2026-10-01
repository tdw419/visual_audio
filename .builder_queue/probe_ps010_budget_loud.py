"""Non-vacuity probe for PS010 step 3 (budget-exhaustion-is-loud).

Mutates the loud RuntimeError in run_two_hart into a silent
completed=False return (the exact failure mode step 3 refuses), runs the
step-3 test, expects it to FAIL, auto-reverts from backup.
Precedent: step 2's merge-order probe (receipt :162-174).
"""
import shutil
import subprocess
import sys

SRC = "tools/pyshader_hart.py"
BAK = "/tmp/pyshader_hart_step3probe.py"
OLD = '''        raise RuntimeError(
            f"run_two_hart: round budget {max_rounds} exhausted with "
            f"hart(s) still live (a halted={halted['a']}, "
            f"b halted={halted['b']}) — livelock/deadlock must be loud")'''
NEW = '''        return TwoHartResult(completed=False, rounds=max_rounds,
                             dmem=list(shared), sync=sync)'''

shutil.copy(SRC, BAK)
try:
    src = open(SRC).read()
    assert OLD in src, "raise block not found — probe aborted, nothing mutated"
    open(SRC, "w").write(src.replace(OLD, NEW))
    r = subprocess.run(
        [sys.executable, "-m", "pytest",
         "tests/test_pyshader_hart.py::TestStep3BudgetExhaustion", "-q"],
        capture_output=True, text=True)
    print("=== MUTATED (silent completed=False) RUN ===")
    print(r.stdout[-1500:])
    print("exit:", r.returncode)
    print("=== PROBE VERDICT: RED (gate able to fail) ==="
          if r.returncode != 0 else
          "=== PROBE VERDICT: GREEN — GATE IS VACUOUS, DO NOT TRUST ===")
finally:
    shutil.copy(BAK, SRC)
    r2 = subprocess.run(
        [sys.executable, "-m", "pytest",
         "tests/test_pyshader_hart.py::TestStep3BudgetExhaustion", "-q"],
        capture_output=True, text=True)
    print("=== REVERTED, clean-tree re-run ===")
    print(r2.stdout[-300:])
    print("exit:", r2.returncode)
