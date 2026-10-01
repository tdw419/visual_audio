"""Out-of-tree probe plugin for tests/test_gh12_autoatlas.py.

MODE=dead    -> make the local model genuinely unreachable through EVERY escalate
                module identity, then run the deterministic legs: if any leg
                silently needed a live model, it must go RED.
MODE=mutate  -> corrupt the scripted candidate, then run the deterministic legs:
                they must go RED (non-vacuity: the candidate really is executed
                through admission + offline replay).
"""
import os
import pytest

MODE = os.environ.get("GH12_PROBE_MODE", "dead")


def _escalate_modules():
    import importlib
    mods = []
    for name in ("glyph_gpt.escalate", "tools.glyph_gpt.escalate"):
        try:
            mods.append(importlib.import_module(name))
        except Exception:
            pass
    return mods


def pytest_configure(config):
    if MODE == "dead":
        for mod in _escalate_modules():
            mod.OLLAMA_URL = "http://127.0.0.1:9/api/generate"

            def _boom(*a, __m=mod, **k):
                raise RuntimeError("gh12-probe: model unreachable by construction")

            mod._ollama = _boom
        print("\n[gh12-probe] MODE=dead: all escalate identities point at port 9")
    elif MODE == "smoke_fail":
        # Force the LIVE smoke leg into its failure mode (dead endpoint, nothing substituted),
        # then check that the module verdict does not move.
        for mod in _escalate_modules():
            mod.OLLAMA_URL = "http://127.0.0.1:9/api/generate"
        print("\n[gh12-probe] MODE=smoke_fail: live endpoint dead, candidate path untouched")


def pytest_collection_modifyitems(session, config, items):
    if MODE == "mutate":
        import tests.test_gh12_autoatlas as t
        t.SCRIPTED_POPCOUNT_CANDIDATE = "LDI r2 0\nLDI r15 754\nST r15 r2\nHALT\n"
        t.EXPECTED_POPCOUNT_BYTES = t.SCRIPTED_POPCOUNT_CANDIDATE.strip().encode("utf-8")
        print("\n[gh12-probe] MODE=mutate: scripted candidate corrupted")
