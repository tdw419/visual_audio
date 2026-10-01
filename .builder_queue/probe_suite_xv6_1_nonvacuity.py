"""Non-vacuity proof for the NEW leg (test_xv6_kernel_check_nonvacuity).

Question: can the new pure-function leg go RED? If not, it is decoration.

Method: copy tests/test_xv6_boot_regression.py into a scratch dir, apply a
targeted mutation to the COPY, run the copy's leg, and require a FAILURE.

  M1 = pre-fix behaviour restored (env var ignored)
  M2 = over-permissive check (non-ELF file accepted)

A mutant that still PASSES proves the leg is vacuous.
"""
import re
import shutil
import subprocess
import sys
from pathlib import Path

SRC = Path("/home/jericho/projects/zion/projects/visual_audio/tests/test_xv6_boot_regression.py")
SCRATCH = Path("/tmp/orch_nonvacuity_mutants")


def run(path: Path) -> tuple[int, str]:
    r = subprocess.run(
        ["/usr/bin/python3", "-m", "pytest", path.name, "-q", "-p", "no:randomly", "--no-header"],
        cwd=str(path.parent), capture_output=True, text=True, timeout=180,
    )
    tail = (r.stdout + r.stderr).strip().splitlines()
    return r.returncode, " | ".join(tail[-3:])


def main() -> int:
    src = SRC.read_text()
    if SCRATCH.exists():
        shutil.rmtree(SCRATCH)
    SCRATCH.mkdir(parents=True)

    # M1: ignore the env override (pre-fix behaviour)
    m1 = src.replace(
        'kernel_path = Path(os.environ.get("XV6_KERNEL_PATH", str(XV6_KERNEL)))',
        'kernel_path = Path("/tmp/xv6-riscv/kernel/kernel")',
    ).replace(
        'XV6_KERNEL = Path(os.environ.get("XV6_KERNEL_PATH", "/tmp/xv6-riscv/kernel/kernel"))',
        'XV6_KERNEL = Path("/tmp/xv6-riscv/kernel/kernel")',
    )
    assert m1 != src, "M1 mutation did not apply"
    p1 = SCRATCH / "m1_test_xv6_boot_regression.py"
    p1.write_text(m1)

    # M2: accept a non-ELF file (over-permissive)
    m2 = src.replace(
        'return False, f"{kernel_path} is not a valid ELF file", None',
        'return True, f"OK - using {kernel_path}", kernel_path',
    )
    assert m2 != src, "M2 mutation did not apply"
    p2 = SCRATCH / "m2_test_xv6_boot_regression.py"
    p2.write_text(m2)

    rc1, t1 = run(p1)
    rc2, t2 = run(p2)
    print(f"M1 env-ignored (pre-fix)  : rc={rc1}  {t1}")
    print(f"M2 over-permissive check  : rc={rc2}  {t2}")
    ok = rc1 != 0 and rc2 != 0
    print(f"NONVACUITY_VERDICT={'LEG IS DISCRIMINATING' if ok else 'LEG IS VACUOUS (BAD)'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
