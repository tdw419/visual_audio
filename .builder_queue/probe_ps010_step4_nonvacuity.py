"""PS010 step 4 non-vacuity probe: mutate gate_mailbox / sync='single' and
prove the step-4 gate can go RED. Auto-reverts; backup /tmp/pyshader_hart_step4probe.py.
Not part of the gate."""
import shutil
import subprocess
import sys

sys.path.insert(0, ".")

SRC = "tools/pyshader_hart.py"
BAK = "/tmp/pyshader_hart_step4probe.py"

MUTATIONS = {
    "break_double_pin (rounds 7->6)": (
        '"rounds": 7,\n        "steps_a": 6,',
        '"rounds": 6,\n        "steps_a": 6,'),
    "silent hazard (torn -> always True)": (
        "torn = torn_s_seen != torn_d_seen and torn_d_seen == (0, 0) \\\n        and torn_s_seen[0] == 1 and torn_s_seen[1] == 0",
        "torn = False"),
    "single-buffer tolerates torn (visible == invisible)": (
        'torn_s_seen = (torn_s["regs_b"][5], torn_s["regs_b"][6])',
        'torn_s_seen = (torn_d["regs_b"][5], torn_d["regs_b"][6])'),
}


def run_gate():
    p = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_pyshader_hart.py::"
         "TestStep4GateMailbox::test_ps010_gate_mailbox", "-q",
         "--no-header", "-p", "no:cacheprovider"],
        capture_output=True, text=True)
    return p.returncode, p.stdout.strip().splitlines()[-1]


def main():
    shutil.copy(SRC, BAK)
    try:
        for name, (old, new) in MUTATIONS.items():
            with open(SRC) as f:
                body = f.read()
            assert old in body, f"mutation anchor not found: {name}"
            with open(SRC, "w") as f:
                f.write(body.replace(old, new))
            rc, tail = run_gate()
            verdict = "RED (gate able to fail)" if rc != 0 else \
                "!!! GREEN UNDER MUTATION — gate is decoration !!!"
            print(f"{name}\n  -> exit {rc}: {tail}\n  === {verdict} ===")
            shutil.copy(BAK, SRC)
    finally:
        shutil.copy(BAK, SRC)
    rc, tail = run_gate()
    print(f"restored clean tree: exit {rc}: {tail}")


if __name__ == "__main__":
    main()
