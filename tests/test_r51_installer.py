"""R5.1 gate — installer/launcher artifact (PRODUCT_ROADMAP.md P5 R5.1).

The artifact under test is glyphos_installer.py at the repo root: ONE file
that verifies its embedded payload against a sha256 manifest, extracts the
boot chain to a private temp dir, boots the agent fleet on the WGSL shader
path, and host-verifies the frozen fleet words.

Legs:
  L1 GREEN  --skip-boot: payload integrity verifies, exit 0.
  L2 RED    --corrupt-verify --skip-boot: corrupted manifest REJECTS the
            good payload, exit 1. (If this leg fails to fail, the gate is
            decoration.)
  L3 GREEN  full boot (one representative run; the probe receipt is the
            full-fidelity record): exit 0, fleet_ready_verified, frozen
            words 0x5EED0005 / 0b1011 / {714:6, 728:12, 748:20, 763:30}.
  L4 GREEN  --json leg: parses, status fleet_ready_verified.
  L5 RED    torn payload: one flipped byte in the EMBEDDED PAYLOAD bytes
            (not the manifest) -> exit 1 + PAYLOAD REJECTED + no boot.

Skipped (with reason) when glyphos_installer.py is absent.
Full-boot legs are gated on wgpu availability; L1/L2/L5 (integrity) are not.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
INSTALLER = REPO / "glyphos_installer.py"

FROZEN_RESULTS = {"714": 6, "728": 12, "748": 20, "763": 30}

pytestmark = pytest.mark.skipif(not INSTALLER.exists(),
                                reason="glyphos_installer.py not built")


def _run(*flags: str, timeout: int = 480) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(INSTALLER), *flags],
                          capture_output=True, text=True, timeout=timeout)


def test_l1_skip_boot_verifies_payload():
    p = _run("--skip-boot")
    assert p.returncode == 0, p.stdout + p.stderr
    assert "payload verified" in p.stdout
    assert "manifest OK" in p.stdout


def test_l2_corrupt_manifest_rejected():
    p = _run("--corrupt-verify", "--skip-boot")
    assert p.returncode == 1, p.stdout + p.stderr
    assert "PAYLOAD REJECTED" in p.stdout
    assert "sha256 mismatch" in p.stdout


@pytest.mark.skipif(__import__("importlib.util", fromlist=["util"])
                    .find_spec("wgpu") is None,
                    reason="wgpu not installed")
def test_l3_full_boot_fleet_ready():
    p = _run()
    assert p.returncode == 0, p.stdout + p.stderr
    assert "fleet_ready_verified" in p.stdout
    assert "0x5eed0005" in p.stdout
    assert "0b1011" in p.stdout
    for w, v in FROZEN_RESULTS.items():
        assert f"result[{w}]  : {v}" in p.stdout
    assert "VERIFY_FAILED" not in p.stdout


@pytest.mark.skipif(__import__("importlib.util", fromlist=["util"])
                    .find_spec("wgpu") is None,
                    reason="wgpu not installed")
def test_l4_json_receipt():
    p = _run("--json")
    assert p.returncode == 0, p.stdout + p.stderr
    d = json.loads(p.stdout)
    assert d["status"] == "fleet_ready_verified"
    assert d["receipt_word"] == "0x5eed0005"
    assert d["done_word"] == "0b1011"
    assert d["results"] == FROZEN_RESULTS
    assert d["halted"] is True


def test_l5_torn_payload_rejected():
    # One flipped byte in the EMBEDDED PAYLOAD bytes (not the manifest):
    # the installer must refuse before any boot.
    import base64
    import re
    text = INSTALLER.read_text()
    m = re.search(r'PAYLOAD_B64 = "([A-Za-z0-9+/=]+)"', text)
    assert m, "payload line not found"
    raw = bytearray(base64.b64decode(m.group(1)))
    raw[len(raw) // 2] ^= 0x01
    torn = base64.b64encode(bytes(raw)).decode()
    torn_text = text[:m.start(1)] + torn + text[m.end(1):]
    torn_path = Path("/tmp/glyphos_installer_torn_gate.py")
    torn_path.write_text(torn_text)
    p = subprocess.run([sys.executable, str(torn_path)],
                       capture_output=True, text=True, timeout=300)
    out = p.stdout + p.stderr
    assert p.returncode == 1, out
    assert "PAYLOAD REJECTED" in out
    assert "fleet_ready_verified" not in out
