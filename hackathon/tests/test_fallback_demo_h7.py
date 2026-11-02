"""h7 — risk/buffer hardening, OFFLINE tests (settle day, no new features).

Three hardened surfaces, all RED-first:

1. fallback demo script (classical decode path) — hackathon/demo/
   fallback_demo.py runs the h4 confidence-gated fallback ALONE on the
   committed lowconf fixtures, byte-checked against the fixture ground
   truth, wall-time accounted against the h6 decode budget. Entry script:
   hackathon/demo/freeze/FALLBACK_DEMO.sh.
2. e2e decode-stage hardening — decode_stage gains poster_png (the h4
   fallback becomes AVAILABLE in the demo chain; previously a low-conf
   response died with "no poster PNG available") and expected_md5 (the
   stage no longer hardcodes one ground truth).
3. e2e wall-budget enforcement — run_e2e gains budget_s (h6 receipt
   budget: decode 5s / boot 120s / total 150s); a run that blows the
   budget reads within_budget False and ok False, instead of a green
   demo over target.

Tests never run the real boot: the budget leg uses a sleeping stub runner
against a pinched budget, same pattern as the h6 suite.
"""
import hashlib
import json
import pathlib
import time

import pytest

FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures"
FREEZE = pathlib.Path(__file__).resolve().parents[2] / "hackathon" / "demo" / "freeze"

LOWCONF_MD5 = "cf09b99dee2b22834fe938f4238a511b"  # glyph_poster_lowconf.json

FAKE_SERIAL = (
    "[    0.000000] Linux version 6.12.31-0-lts (builder@host) (gcc) #1 SMP\n"
    "[    0.001000] smp: Brought up 1 node, 1 CPU\n"
)


def _fixture(name):
    return json.loads((FIXTURES / name).read_text())


@pytest.fixture(scope="module")
def fallback_demo():
    from hackathon.demo import fallback_demo as mod

    return mod


@pytest.fixture(scope="module")
def e2e():
    from hackathon.demo import e2e as e2e_mod

    return e2e_mod


# ---------------------------------------------------------------- surface 1


def test_fallback_demo_reproduces_lowconf_payload(fallback_demo):
    """The classical path ALONE recovers the lowconf payload byte-exactly,
    takes the pixels path (score 0.8977 < gate 0.90), and matches the
    fixture's measured Otsu eta."""
    lo = _fixture("glyph_poster_lowconf.json")
    result = fallback_demo.run_fallback_demo()
    assert result["ok"] is True
    assert result["path"] == "pixels"
    assert result["payload_md5"] == lo["payload_md5"] == LOWCONF_MD5
    assert result["payload_len"] == len(bytes.fromhex(lo["payload_hex"]))
    assert abs(result["otsu_eta"] - lo["otsu_eta"]) < 1e-6
    assert result["gt_md5"] == lo["payload_md5"]


def test_fallback_demo_detects_tamper(fallback_demo):
    """A corrupted poster must fail the demo, not pass silently. (The mask
    RLE is deliberately UNUSED on the classical path — pixels are the
    truth — so the tamper that matters here is the poster itself.)"""
    poster = bytearray((FIXTURES / "glyph_poster_lowconf.png").read_bytes())
    poster[200] ^= 0xFF
    result = fallback_demo.run_fallback_demo(poster_png=bytes(poster))
    assert result["ok"] is False
    assert result.get("error")


def test_fallback_demo_requires_poster(fallback_demo):
    """No poster PNG + low-conf response -> the h4 DecodeError is SURFACED
    by the demo wrapper (ok False + named error), never swallowed."""
    response = _fixture("glyph_response_lowconf.json")
    result = fallback_demo.run_fallback_demo(response=response, poster_png=None)
    assert result["ok"] is False
    assert "no poster PNG" in result.get("error", "")


def test_fallback_demo_wrong_box_cannot_pass_silently(fallback_demo):
    """h4 proof-limit said a wrong box origin 'cannot self-correct' — here
    we prove it also cannot PASS silently: a shifted box trips framing and
    the demo reports not-ok with the framing error."""
    response = _fixture("glyph_response_lowconf.json")
    png = str(FIXTURES / "glyph_poster_lowconf.png")
    # shift the box 8 px into the decorative border region
    response["output"][0]["content"][0]["text"] = response["output"][0][
        "content"][0]["text"].replace("x=48;", "x=56;").replace("y=48;", "y=56;")
    result = fallback_demo.run_fallback_demo(response=response, poster_png=png)
    assert result["ok"] is False
    assert result.get("error")


def test_fallback_decode_wall_under_budget(fallback_demo):
    """Timing leg: the decode-side fallback runs far inside the h6 decode
    budget (5s) and reports it."""
    result = fallback_demo.run_fallback_demo()
    assert result["wall_s"] < fallback_demo.DECODE_BUDGET_S
    assert result["within_budget"] is True


def test_fallback_entry_script_exists(fallback_demo):
    """The ONE command for the classical path lives in freeze/."""
    script = FREEZE / "FALLBACK_DEMO.sh"
    assert script.exists(), f"missing entry script: {script}"
    assert script.stat().st_mode & 0o111, "entry script not executable"
    body = script.read_text()
    assert "hackathon.demo.fallback_demo" in body


# ---------------------------------------------------------------- surface 2


def test_decode_stage_hardened_fallback_available_and_expected_md5(e2e):
    """The demo chain can now take the fallback: a low-conf response with
    its poster decodes through pixels and is checked against ITS ground
    truth (expected_md5), instead of dying on 'no poster PNG available'."""
    result = e2e.decode_stage(
        response=_fixture("glyph_response_lowconf.json"),
        poster_png=(FIXTURES / "glyph_poster_lowconf.png").read_bytes(),
        expected_md5=LOWCONF_MD5,
    )
    assert result["ok"] is True
    assert result["path"] == "pixels"
    assert result["payload_md5"] == LOWCONF_MD5
    assert result["gt_md5"] == LOWCONF_MD5


# ---------------------------------------------------------------- surface 3


def _sleepy_boot_runner(seconds):
    """Boot leg that is GREEN (rc 0 + milestones present) but takes
    `seconds` wall — isolates the budget gate from boot success."""
    def runner(cmd, timeout):
        time.sleep(seconds)
        log_path = pathlib.Path("/tmp") / "h7_stub_serial.log"
        log_path.write_text(FAKE_SERIAL)
        return 0, str(log_path)

    return runner


def test_run_e2e_reports_within_budget_default(e2e, tmp_path):
    """Default budget: the h6 receipt numbers; a fast stub run is inside."""
    summary = e2e.run_e2e(
        out_dir=str(tmp_path),
        boot_runner=_sleepy_boot_runner(0.0),
    )
    assert summary["ok"] is True
    assert summary["within_budget"] is True
    assert summary["budget_s"] == {
        "decode": 5.0, "boot": 120.0, "total": 150.0
    }


def test_run_e2e_budget_blowup_is_not_ok(e2e, tmp_path):
    """A boot leg that exceeds its budget fails the run even with decode
    green and the boot runner exiting 0 — the negative leg of the
    wall-time gate."""
    summary = e2e.run_e2e(
        out_dir=str(tmp_path),
        boot_runner=_sleepy_boot_runner(0.05),
        budget_s={"decode": 5.0, "boot": 0.001, "total": 150.0},
    )
    assert summary["ok"] is False
    assert summary["boot"]["ok"] is True          # boot itself was green
    assert summary["within_budget"] is False
    assert summary["wall_s"]["boot"] >= 0.05


def test_run_e2e_decode_budget_blowup_is_not_ok(e2e, tmp_path):
    """Same gate on the decode leg: pinch the decode budget to zero —
    the run reads not-ok via within_budget False."""
    summary = e2e.run_e2e(
        out_dir=str(tmp_path),
        boot_runner=_sleepy_boot_runner(0.0),
        budget_s={"decode": 0.0, "boot": 120.0, "total": 150.0},
    )
    assert summary["ok"] is False
    assert summary["decode"]["ok"] is True
    assert summary["within_budget"] is False
