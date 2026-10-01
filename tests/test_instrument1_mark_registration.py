#!/usr/bin/env python3
"""tests/test_instrument1_mark_registration.py — gate for INSTRUMENT-1 mark registration.

Carries four independent legs verifying registration of the `live_smoke` pytest mark:
- L1: strict-markers collection over the 4 live_smoke-carrying arc files passes cleanly (rc 0).
- L2: discriminating leg — synthetic removal via `-o markers=` reproduces collection failure (rc != 0).
- L3: non-vacuity — misspelled mark (@pytest.mark.live_smok) fails, correct mark passes.
- L4: name-match — marker registered in pytest.ini equals deselector token in tools/arc_lega.sh.
"""
import configparser
from pathlib import Path
import re
import subprocess
import pytest

_REPO = Path(__file__).resolve().parent.parent
PYTHON = "/usr/bin/python3"

LIVE_SMOKE_FILES = [
    "tests/test_gh20_fs_v2.py",
    "tests/test_gh18_syscall_abi.py",
    "tests/test_gh12_escalation.py",
    "tests/test_gh12_autoatlas.py",
]


def test_l1_registered():
    """L1: --strict-markers --collect-only -q over the 4 live_smoke arc files returns rc 0."""
    cmd = [
        PYTHON,
        "-m",
        "pytest",
        *LIVE_SMOKE_FILES,
        "--strict-markers",
        "--collect-only",
        "-q",
    ]
    res = subprocess.run(cmd, cwd=_REPO, capture_output=True, text=True)
    combined = res.stdout + res.stderr
    assert "not found in `markers` configuration option" not in combined, (
        f"Unexpected missing marker in output:\n{combined}"
    )
    assert res.returncode == 0, (
        f"Expected rc 0 from strict-markers collect, got {res.returncode}:\n{combined}"
    )


def test_l2_red_first_discriminating():
    """L2: The same subprocess with -o markers= returns rc != 0 and names live_smoke."""
    cmd = [
        PYTHON,
        "-m",
        "pytest",
        *LIVE_SMOKE_FILES,
        "--strict-markers",
        "--collect-only",
        "-q",
        "-o",
        "markers=",
    ]
    res = subprocess.run(cmd, cwd=_REPO, capture_output=True, text=True)
    combined = res.stdout + res.stderr
    assert res.returncode != 0, (
        f"Expected non-zero returncode with synthetic -o markers=, got 0:\n{combined}"
    )
    assert "live_smoke" in combined, (
        f"Expected 'live_smoke' to be named in failure output:\n{combined}"
    )
    assert "not found in `markers` configuration option" in combined, (
        f"Expected missing marker error in output:\n{combined}"
    )


def test_l3_nonvacuity(tmp_path: Path):
    """L3: Misspelled mark (@pytest.mark.live_smok) returns rc != 0; twin with live_smoke returns rc 0."""
    bad_test = tmp_path / "test_misspelled.py"
    bad_test.write_text(
        "import pytest\n\n@pytest.mark.live_smok\ndef test_stub():\n    pass\n",
        encoding="utf-8",
    )
    cmd_bad = [
        PYTHON,
        "-m",
        "pytest",
        str(bad_test),
        "-c",
        str(_REPO / "pytest.ini"),
        "--strict-markers",
        "--collect-only",
        "-q",
    ]
    res_bad = subprocess.run(cmd_bad, cwd=_REPO, capture_output=True, text=True)
    combined_bad = res_bad.stdout + res_bad.stderr
    assert res_bad.returncode != 0, (
        f"Expected non-zero returncode for misspelled mark live_smok, got 0:\n{combined_bad}"
    )
    assert "live_smok" in combined_bad, (
        f"Expected 'live_smok' to be named in error output:\n{combined_bad}"
    )
    assert "not found in `markers` configuration option" in combined_bad, (
        f"Expected missing marker error for misspelled mark:\n{combined_bad}"
    )

    good_test = tmp_path / "test_correct.py"
    good_test.write_text(
        "import pytest\n\n@pytest.mark.live_smoke\ndef test_stub():\n    pass\n",
        encoding="utf-8",
    )
    cmd_good = [
        PYTHON,
        "-m",
        "pytest",
        str(good_test),
        "-c",
        str(_REPO / "pytest.ini"),
        "--strict-markers",
        "--collect-only",
        "-q",
    ]
    res_good = subprocess.run(cmd_good, cwd=_REPO, capture_output=True, text=True)
    combined_good = res_good.stdout + res_good.stderr
    assert "not found in `markers` configuration option" not in combined_good, (
        f"Unexpected missing marker error for registered mark:\n{combined_good}"
    )
    assert res_good.returncode == 0, (
        f"Expected rc 0 for registered mark live_smoke, got {res_good.returncode}:\n{combined_good}"
    )


def test_l4_name_match():
    """L4: Registered marker name in pytest.ini equals deselector token in tools/arc_lega.sh."""
    ini_path = _REPO / "pytest.ini"
    assert ini_path.is_file(), f"Missing pytest.ini at {ini_path}"
    cp = configparser.ConfigParser()
    cp.read(ini_path)
    assert "pytest" in cp, "Missing [pytest] section in pytest.ini"
    assert "markers" in cp["pytest"], "Missing 'markers' in [pytest] section of pytest.ini"
    markers_val = cp["pytest"]["markers"]

    m_ini = re.search(r"^\s*([a-zA-Z0-9_]+)\s*:", markers_val, re.MULTILINE)
    assert m_ini, f"Could not parse marker name from pytest.ini markers entry: {markers_val!r}"
    registered_marker = m_ini.group(1)

    runner_path = _REPO / "tools" / "arc_lega.sh"
    assert runner_path.is_file(), f"Missing tools/arc_lega.sh at {runner_path}"
    runner_content = runner_path.read_text(encoding="utf-8")
    m_runner = re.search(r'-m\s+"not\s+([a-zA-Z0-9_]+)"', runner_content)
    assert m_runner, "Could not parse deselector token from tools/arc_lega.sh"
    deselected_marker = m_runner.group(1)

    assert registered_marker == deselected_marker == "live_smoke", (
        f"Marker name mismatch: registered in pytest.ini: {registered_marker!r}, "
        f"deselected in tools/arc_lega.sh: {deselected_marker!r}"
    )
