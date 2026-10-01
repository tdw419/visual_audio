"""Gate tests for SWEEP-CONTAIN-1: tools/suite_sweep.sh preflight and refusal.

Roadmap row: SWEEP-CONTAIN-1 in systems/GLYPH_SELF_HOSTING_ROADMAP.md
Spec: .builder_queue/RULING_worker_memory_containment.md

Legs:
  L1: refuse-nowhere-to-widen (R1, R2, R3)
  L2: widening path unchanged/positive (R7, R8)
  L3: worker cap (R4)
  L4: per-child cap + bad budget (R5, R6)
  L5: non-vacuity against the pre-fix fixture (discriminating control)
"""

import hashlib
import os
from pathlib import Path
import subprocess
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SUITE_SWEEP = REPO_ROOT / "tools" / "suite_sweep.sh"
PREFIX_FIXTURE = REPO_ROOT / "tests" / "fixtures" / "suite_sweep_prefix_1833ba0.sh"
PREFIX_FIXTURE_SHA256 = "826a9cdb0f912d8cabbcffd79957f6eaf740bd3c23fcdfe51520d3f7a41f4f69"


def make_shim_env(tmp_path: Path, systemd_run_mode: str = "fail", cap_value: str = "4294967296"):
    """Create a hermetic environment with a PATH shim for systemd-run and SWEEP_CAP_FILE."""
    shim_dir = tmp_path / "bin"
    shim_dir.mkdir(parents=True, exist_ok=True)
    log_file = tmp_path / "systemd_run.log"

    # Fake systemd-run script: records argv; if fail mode exits 1; if succeed mode executes command after '--'
    is_fail = "1" if systemd_run_mode == "fail" else "0"
    script_content = f"""#!/usr/bin/env bash
echo "$*" >> "{log_file}"
if [ "{is_fail}" = "1" ]; then
  exit 1
fi
while [ $# -gt 0 ]; do
  if [ "$1" = "--" ]; then
    shift
    exec "$@"
  fi
  shift
done
exit 0
"""
    systemd_run_path = shim_dir / "systemd-run"
    systemd_run_path.write_text(script_content)
    systemd_run_path.chmod(0o755)

    env = os.environ.copy()
    env["PATH"] = f"{shim_dir}:{env.get('PATH', '')}"

    if cap_value is not None:
        cap_file = tmp_path / "memory.max"
        cap_file.write_text(f"{cap_value}\n")
        env["SWEEP_CAP_FILE"] = str(cap_file)
    else:
        env.pop("SWEEP_CAP_FILE", None)

    return env, log_file


def test_l1_refuse_nowhere_to_widen(tmp_path):
    """L1: When widening is unavailable and BUDGET > CAP, refuse with code 3,
    print budget, cap, path, workers on stderr, and DO NOT run command.
    When widening is unavailable and BUDGET <= CAP, proceed (R3).
    Also test R1 (default cgroup path is printed on stderr).
    """
    marker = tmp_path / "marker_l1"
    env, _ = make_shim_env(tmp_path, systemd_run_mode="fail", cap_value="4294967296")
    cap_file_path = env["SWEEP_CAP_FILE"]

    # Case 1: BUDGET (12G) > CAP (4 GiB), widening unavailable -> REFUSE with exit code 3
    res = subprocess.run(
        ["bash", str(SUITE_SWEEP), "-b", "12G", "-w", "4", "--", "touch", str(marker)],
        env=env,
        capture_output=True,
        text=True,
    )

    assert res.returncode == 3, f"Expected rc=3 on refusal, got {res.returncode}. Stderr:\n{res.stderr}"
    assert not marker.exists(), "Command must NOT be executed when refusing"
    assert "enclosing scope memory.max =" in res.stderr
    assert cap_file_path in res.stderr
    # Refusal line must name requested budget, resolved cap, path, and workers
    assert "12G" in res.stderr or "12884901888" in res.stderr
    assert "4294967296" in res.stderr or "4G" in res.stderr
    assert "4" in res.stderr  # worker count

    # Case 2: BUDGET (2G) <= CAP (4 GiB), widening unavailable -> PROCEED (R3)
    marker_ok = tmp_path / "marker_l1_proceed"
    res_ok = subprocess.run(
        ["bash", str(SUITE_SWEEP), "-b", "2G", "-w", "2", "--", "touch", str(marker_ok)],
        env=env,
        capture_output=True,
        text=True,
    )
    assert res_ok.returncode == 0, f"Expected rc=0 when budget <= cap, got {res_ok.returncode}. Stderr:\n{res_ok.stderr}"
    assert marker_ok.exists(), "Command should have executed when budget <= cap"

    # Case 3: R1 default cgroup path assertable on stderr when SWEEP_CAP_FILE is unset
    env_no_cap, _ = make_shim_env(tmp_path, systemd_run_mode="fail", cap_value=None)
    res_default = subprocess.run(
        ["bash", str(SUITE_SWEEP), "-b", "1G", "-w", "1", "--", "true"],
        env=env_no_cap,
        capture_output=True,
        text=True,
    )
    assert "enclosing scope memory.max =" in res_default.stderr
    assert "/sys/fs/cgroup" in res_default.stderr


def test_l2_widening_path_positive(tmp_path):
    """L2: When widening is available, run systemd-run with:
    -p MemoryMax=<budget> -p MemoryHigh=<budget>
    --setenv=SWEEP_BUDGET=<budget> --setenv=SWEEP_WORKERS=<n>
    --quiet -- <command...>
    Assert recorded argv on the shim, and test R8 byte parsing suffixes.
    """
    marker = tmp_path / "marker_l2"
    env, log_file = make_shim_env(tmp_path, systemd_run_mode="succeed", cap_value="4294967296")

    res = subprocess.run(
        ["bash", str(SUITE_SWEEP), "-b", "12G", "-w", "4", "--", "touch", str(marker)],
        env=env,
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0, f"Expected rc=0 on success, got {res.returncode}. Stderr:\n{res.stderr}"
    assert marker.exists(), "Command should have executed via fake systemd-run"

    assert log_file.exists()
    log_lines = log_file.read_text().splitlines()
    assert len(log_lines) >= 2, f"Expected probe and exec invocations, got {log_lines}"

    exec_line = log_lines[-1]
    assert "MemoryMax=12G" in exec_line
    assert "MemoryHigh=12G" in exec_line
    assert "--setenv=SWEEP_BUDGET=12G" in exec_line
    assert "--setenv=SWEEP_WORKERS=4" in exec_line
    assert "--quiet" in exec_line
    assert "--" in exec_line
    assert f"touch {marker}" in exec_line

    # Test R8 suffixes (M, K, plain bytes) with successful widening
    res_m = subprocess.run(
        ["bash", str(SUITE_SWEEP), "-b", "4096M", "-w", "2", "--", "true"],
        env=env,
        capture_output=True,
        text=True,
    )
    assert res_m.returncode == 0


def test_l3_worker_cap(tmp_path):
    """L3: -w greater than 4 -> refuse with non-zero, message naming max (4),
    command NOT run. Default stays 4.
    """
    env, _ = make_shim_env(tmp_path, systemd_run_mode="succeed", cap_value="17179869184")

    # Case 1: -w 12 -> Refuse loudly naming max 4
    marker12 = tmp_path / "marker_w12"
    res12 = subprocess.run(
        ["bash", str(SUITE_SWEEP), "-w", "12", "-b", "12G", "--", "touch", str(marker12)],
        env=env,
        capture_output=True,
        text=True,
    )
    assert res12.returncode != 0, f"Expected non-zero exit for -w 12, got {res12.returncode}"
    assert not marker12.exists(), "Command must NOT run when -w > 4"
    assert "4" in res12.stderr, f"Refusal must name max 4 in stderr:\n{res12.stderr}"

    # Case 2: -w 5 -> Refuse loudly naming max 4
    marker5 = tmp_path / "marker_w5"
    res5 = subprocess.run(
        ["bash", str(SUITE_SWEEP), "-w", "5", "-b", "10G", "--", "touch", str(marker5)],
        env=env,
        capture_output=True,
        text=True,
    )
    assert res5.returncode != 0, f"Expected non-zero exit for -w 5, got {res5.returncode}"
    assert not marker5.exists(), "Command must NOT run when -w > 4"
    assert "4" in res5.stderr, f"Refusal must name max 4 in stderr:\n{res5.stderr}"

    # Case 3: Default worker count is 4
    _, log_file = make_shim_env(tmp_path / "default_w", systemd_run_mode="succeed", cap_value="17179869184")
    env_def = os.environ.copy()
    env_def["PATH"] = f"{(tmp_path / 'default_w' / 'bin')}:{env_def.get('PATH', '')}"
    res_def = subprocess.run(
        ["bash", str(SUITE_SWEEP), "-b", "12G", "--", "true"],
        env=env_def,
        capture_output=True,
        text=True,
    )
    assert res_def.returncode == 0
    exec_line = log_file.read_text().splitlines()[-1]
    assert "--setenv=SWEEP_WORKERS=4" in exec_line


def test_l4_per_child_cap_and_bad_budget(tmp_path):
    """L4: budget / workers < 1 GiB -> refuse with non-zero, naming both numbers,
    command NOT run.
    1 GiB exactly is acceptable.
    Unparseable/zero/negative -b value -> refuse with usage-style error.
    """
    env, _ = make_shim_env(tmp_path, systemd_run_mode="succeed", cap_value="17179869184")

    # Case 1: budget / workers < 1 GiB (3G / 4 = 768 MiB < 1 GiB)
    marker_ratio = tmp_path / "marker_bad_ratio"
    res_ratio = subprocess.run(
        ["bash", str(SUITE_SWEEP), "-b", "3G", "-w", "4", "--", "touch", str(marker_ratio)],
        env=env,
        capture_output=True,
        text=True,
    )
    assert res_ratio.returncode != 0, f"Expected non-zero exit for ratio < 1 GiB, got {res_ratio.returncode}"
    assert not marker_ratio.exists(), "Command must NOT run when per-worker budget < 1 GiB"
    # Stderr must name both numbers
    assert "3G" in res_ratio.stderr or "3221225472" in res_ratio.stderr
    assert "4" in res_ratio.stderr

    # Case 2: budget / workers == 1 GiB exactly (4G / 4 = 1 GiB) is acceptable
    marker_exact = tmp_path / "marker_1gib_exact"
    res_exact = subprocess.run(
        ["bash", str(SUITE_SWEEP), "-b", "4G", "-w", "4", "--", "touch", str(marker_exact)],
        env=env,
        capture_output=True,
        text=True,
    )
    assert res_exact.returncode == 0, f"1 GiB per child must be accepted. Stderr:\n{res_exact.stderr}"
    assert marker_exact.exists()

    # Case 3: Bad budget values (zero, negative, unparseable)
    for bad_b in ["0", "-1G", "invalid", "10X"]:
        marker_bad = tmp_path / f"marker_bad_{bad_b}"
        res_bad = subprocess.run(
            ["bash", str(SUITE_SWEEP), "-b", bad_b, "-w", "1", "--", "touch", str(marker_bad)],
            env=env,
            capture_output=True,
            text=True,
        )
        assert res_bad.returncode != 0, f"Expected non-zero exit for bad budget '{bad_b}', got {res_bad.returncode}"
        assert not marker_bad.exists(), f"Command must NOT run for bad budget '{bad_b}'"


def test_l5_non_vacuity_discriminating(tmp_path):
    """L5: Discriminating non-vacuity leg against pre-fix fixture:
    tests/fixtures/suite_sweep_prefix_1833ba0.sh.
    Under unavailable widening and 4 GiB cap, -b 12G:
    - Pre-fix fixture runs the command (rc == 0, marker created).
    - Fixed script refuses (rc != 0, marker NOT created).
    Also asserts the sha256 of the pre-fix fixture.
    """
    assert PREFIX_FIXTURE.exists(), f"Fixture missing: {PREFIX_FIXTURE}"
    fixture_hash = hashlib.sha256(PREFIX_FIXTURE.read_bytes()).hexdigest()
    assert fixture_hash == PREFIX_FIXTURE_SHA256, (
        f"Fixture drifted! Got {fixture_hash}, expected {PREFIX_FIXTURE_SHA256}"
    )

    env, _ = make_shim_env(tmp_path, systemd_run_mode="fail", cap_value="4294967296")

    # 1. Run pre-fix fixture: it must NOT refuse (rc == 0, command executed)
    marker_prefix = tmp_path / "marker_prefix"
    res_prefix = subprocess.run(
        ["bash", str(PREFIX_FIXTURE), "-b", "12G", "-w", "4", "--", "touch", str(marker_prefix)],
        env=env,
        capture_output=True,
        text=True,
    )
    assert res_prefix.returncode == 0, (
        f"Pre-fix fixture was expected to exit 0 (defect), but exited {res_prefix.returncode}"
    )
    assert marker_prefix.exists(), "Pre-fix fixture must execute command despite cap (the defect)"

    # 2. Run current script under test: it MUST refuse (rc != 0, command not executed)
    marker_fixed = tmp_path / "marker_fixed"
    res_fixed = subprocess.run(
        ["bash", str(SUITE_SWEEP), "-b", "12G", "-w", "4", "--", "touch", str(marker_fixed)],
        env=env,
        capture_output=True,
        text=True,
    )
    assert res_fixed.returncode != 0, (
        f"Script under test did not refuse! rc={res_fixed.returncode}. Stderr:\n{res_fixed.stderr}"
    )
    assert not marker_fixed.exists(), "Fixed script must NOT execute command when refusing"
