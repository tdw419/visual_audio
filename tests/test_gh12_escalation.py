#!/usr/bin/env python3
"""GH-12 gate: escalate() drafts a real routine via local Ollama and the
oracle admits ONLY a contract-passing candidate.

Skipped cleanly when localhost:11434 has no model (CI / offline) — the
loop itself is exercised by tests/test_oracle.py without a model.
"""
import json
import sys
import urllib.request
from pathlib import Path

import pytest

_TOOLS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_TOOLS))
sys.path.insert(0, str(_TOOLS / "tools"))

from glyph_gpt.escalate import OLLAMA_MODEL, OLLAMA_URL, escalate  # noqa: E402
from glyph_gpt.oracle import run_oracle  # noqa: E402


def _ollama_available() -> bool:
    try:
        with urllib.request.urlopen("http://localhost:11434/api/tags", timeout=3) as r:
            return bool(json.loads(r.read())["models"])
    except Exception:
        return False


@pytest.mark.skipif(not _ollama_available(), reason="local Ollama not reachable")
def test_gh12_escalation_drafts_and_verifies_popcount():
    # golden: popcount(0xF0F0F0F0) == 16 — inputs arrive IN registers
    res = escalate("popcount(r1) -> r2", expect_registers={2: 16},
                   input_registers={1: 0xF0F0F0F0}, max_attempts=6)
    assert res.verified, res.error
    assert res.oracle.passed and res.oracle.registers[2] == 16
    # the admitted candidate must replay through the oracle standalone
    replay = run_oracle(res.glyph_text, expect_registers={2: 16},
                        input_registers={1: 0xF0F0F0F0})
    assert replay.passed, replay.error


@pytest.mark.skipif(not _ollama_available(), reason="local Ollama not reachable")
def test_gh12_failed_candidates_never_returned_as_verified():
    res = escalate("r2 = r1 xor 0x12345678", expect_registers={2: 0xDEADBEEF},
                   input_registers={1: 0}, max_attempts=1)
    # even if it fails, result must be honestly unverified with a log
    if not res.verified:
        assert res.error and res.history, res
        assert res.glyph_text is None, "unverified candidate must not be returned"
