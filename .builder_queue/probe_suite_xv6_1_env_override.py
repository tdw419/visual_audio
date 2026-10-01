"""Non-vacuity probe for SUITE-XV6-1 (orchestrator, builder cron af3e62239ce2).

Claims under test:
  C1: the skip decision in tests/test_xv6_boot_regression.py is INPUT-CONDITIONAL,
      i.e. a caller can point the check at a real (ELF) kernel and the skip will NOT fire.
  C2: the KNOWN-BROKEN-INPUT fallback never runs a boot (no 300s x 2 burn).

Method: set XV6_KERNEL_PATH to a temp file carrying the ELF magic, import the test
module, and call its check function directly. Pure function, no GPU, no network.

Expectation BEFORE the fix (RED): env var is ignored -> returns exists=False
  (proves the probe discriminates: it can go red).
Expectation AFTER the fix (GREEN): returns exists=True with the temp ELF path.
"""
import importlib.util
import os
import sys
import tempfile
from pathlib import Path

REPO = Path("/home/jericho/projects/zion/projects/visual_audio")
TEST_FILE = REPO / "tests" / "test_xv6_boot_regression.py"


def load_module():
    spec = importlib.util.spec_from_file_location("xv6_boot_reg_mod", TEST_FILE)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["xv6_boot_reg_mod"] = mod
    spec.loader.exec_module(mod)
    return mod


def main():
    tmpdir = tempfile.mkdtemp(prefix="xv6_nonvacuity_")
    elf = Path(tmpdir) / "fake_kernel_elf"
    elf.write_bytes(b"\x7fELF" + b"\x02\x01\x01\x00" + b"\x00" * 64)
    notelf = Path(tmpdir) / "fake_kernel_txt"
    notelf.write_bytes(b"NOPE" + b"\x00" * 64)

    os.environ["XV6_KERNEL_PATH"] = str(elf)
    mod = load_module()

    print(f"probe: XV6_KERNEL_PATH={os.environ['XV6_KERNEL_PATH']}")
    print(f"probe: module XV6_KERNEL={getattr(mod, 'XV6_KERNEL', '<absent>')}")

    exists, msg, path = mod.check_xv6_kernel_exists()
    print(f"C1 env-override honored : exists={exists} path={path}")
    print(f"   msg: {msg[:160]}")

    os.environ["XV6_KERNEL_PATH"] = str(notelf)
    mod2 = load_module()
    exists2, msg2, path2 = mod2.check_xv6_kernel_exists()
    print(f"C1b non-ELF rejected    : exists={exists2} path={path2}")
    print(f"   msg: {msg2[:160]}")

    ok = bool(exists) and str(path) == str(elf) and (not exists2)
    print(f"PROBE_VERDICT={'GREEN' if ok else 'RED'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
