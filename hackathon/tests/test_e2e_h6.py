"""h6 — end-to-end v1, OFFLINE tests.

One command from hackathon/demo/freeze: poster -> SAM segments -> glyph
decode -> kernel boots -> serial log. The decode leg runs entirely on
committed fixtures (same ground truth as h3/h4). The boot leg is the frozen
h1 BOOT_SMOKE gate; tests NEVER run it (90s+ live, and lane verify is
offline/fast) — they inject a stub boot runner and check the orchestration:
milestone extraction from the serial log, artifact preservation, ok/fail
propagation, and wall-time accounting.
"""
import hashlib
import json
import pathlib

import pytest

FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures"
FREEZE = pathlib.Path(__file__).resolve().parents[2] / "hackathon" / "demo" / "freeze"

FAKE_SERIAL = (
    "[    0.000000] Linux version 6.12.31-0-lts (builder@host) (gcc) #1 SMP\n"
    "[    0.001000] smp: Brought up 1 node, 1 CPU\n"
    "[    0.002000] Freeing unused kernel memory\n"
)


def _fixture(name):
    return json.loads((FIXTURES / name).read_text())


@pytest.fixture(scope="module")
def e2e():
    from hackathon.demo import e2e as e2e_mod

    return e2e_mod


def _stub_boot_runner(log_text=FAKE_SERIAL, rc=0):
    def runner(cmd, timeout):
        log_path = pathlib.Path("/tmp") / (
            "h6_stub_serial_%d.log" % (abs(hash(log_text)) % 999999)
        )
        log_path.write_text(log_text)
        return rc, str(log_path)

    return runner


def test_decode_stage_reproduces_ground_truth(e2e):
    """Poster fixture + recorded SAM response -> payload matches frozen md5."""
    gt = _fixture("glyph_poster_gt.json")
    result = e2e.decode_stage()
    assert result["ok"] is True
    assert result["path"] == "sam"
    assert result["payload_md5"] == gt["payload_md5"]
    assert result["payload_len"] == len(bytes.fromhex(gt["payload_hex"]))


def test_decode_stage_detects_tamper(e2e):
    """A tampered SAM response must fail the stage, not pass silently."""
    response = _fixture("glyph_response_gt.json")
    text = response["output"][0]["content"][0]["text"]
    response["output"][0]["content"][0]["text"] = text.replace("1,0", "1,1", 1)
    result = e2e.decode_stage(response=response)
    assert result["ok"] is False


def test_run_e2e_wires_decode_and_boot(e2e, tmp_path):
    """Orchestration: decode ok + boot ok -> overall ok, milestones parsed,
    serial log preserved as an artifact, wall time accounted."""
    summary = e2e.run_e2e(
        out_dir=str(tmp_path), boot_runner=_stub_boot_runner()
    )
    assert summary["ok"] is True
    assert summary["decode"]["ok"] is True
    assert summary["boot"]["ok"] is True
    assert summary["boot"]["milestones"]["kernel_banner"].startswith(
        "Linux version 6.12.31-0-lts"
    )
    assert summary["boot"]["milestones"]["smp_up"] == "smp: Brought up 1 node, 1 CPU"
    serial = pathlib.Path(summary["boot"]["serial_log"])
    assert serial.exists()
    assert serial.read_text() == FAKE_SERIAL
    assert summary["boot"]["serial_sha256"] == hashlib.sha256(
        FAKE_SERIAL.encode()
    ).hexdigest()
    assert summary["wall_s"]["total"] >= summary["wall_s"]["decode"]
    assert summary["wall_s"]["decode"] >= 0.0 and summary["wall_s"]["boot"] >= 0.0


def test_run_e2e_boot_failure_is_not_ok(e2e, tmp_path):
    """A boot leg that exits nonzero (or misses milestones) must fail the
    run even when decode is green — the negative leg of the gate."""
    summary = e2e.run_e2e(
        out_dir=str(tmp_path), boot_runner=_stub_boot_runner(rc=1)
    )
    assert summary["ok"] is False
    assert summary["decode"]["ok"] is True
    assert summary["boot"]["ok"] is False

    summary2 = e2e.run_e2e(
        out_dir=str(tmp_path),
        boot_runner=_stub_boot_runner(
            log_text="[    0.0] nothing relevant here\n"
        ),
    )
    assert summary2["ok"] is False
    assert summary2["boot"]["ok"] is False
    assert summary2["boot"]["milestones"]["kernel_banner"] is None


def test_entry_script_exists_and_boots_smoke_gate(e2e):
    """The ONE command lives in hackathon/demo/freeze and drives BOOT_SMOKE."""
    script = FREEZE / "E2E.sh"
    assert script.exists(), f"missing entry script: {script}"
    assert script.stat().st_mode & 0o111, "entry script not executable"
    body = script.read_text()
    assert "BOOT_SMOKE" in body
    assert "hackathon.demo.e2e" in body
