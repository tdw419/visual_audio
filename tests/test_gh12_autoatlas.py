#!/usr/bin/env python3
"""GH-12 capstone gate: AutoAtlasIngest — the loop closes.

Proves, against the live substrate:
  1. whitelist gate: unknown family -> E_ATLAS_FAMILY, ZERO model calls
  2. hard-fail gate: unverified after N attempts -> E_ATLAS_UNVERIFIED,
     atlas untouched (negative control at the ingest layer)
  3. the full loop (live Ollama + live kernel): atlas-miss -> escalate ->
     oracle -> atlas.register -> GH-9 mailbox inject via GlyphRunner.drive
     -> kernel re-dispatch -> result word-exact vs the oracle
  4. registered tile replays offline (persistence model: in-image pixels)
Skips cleanly when localhost:11434 has no model.
"""
from __future__ import annotations

import sys
import tempfile
import urllib.request
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
for _p in (str(_REPO), str(_REPO / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from tools.glyph_gpt.atlas import build_default_atlas            # noqa: E402
from tools.glyph_gpt.autoatlas import (                          # noqa: E402
    ingest, ESCALATABLE_FAMILIES, _pixel_words,
    GH9_ARGV_WORD, GH9_ARGV_RESULT, GH9_EXIT_WORD, GH9_EXIT_OK,
    KERNEL_STATUS_WORD, KERNEL_OK,
)
from tools.glyph_gpt.baker import loader_kernel_image            # noqa: E402
from tools.glyph_gpt.runner import GlyphRunner                   # noqa: E402


def _ollama_available() -> bool:
    try:
        with urllib.request.urlopen(
                "http://localhost:11434/api/tags", timeout=3) as r:
        # any model at all — the router targets qwen2.5-coder:14b
            return bool(__import__("json").loads(r.read()).get("models"))
    except Exception:
        return False


def _baked_runner(tmp: Path) -> GlyphRunner:
    out = tmp / "gh12cap.glyph.npy"
    loader_kernel_image(build_default_atlas(), out_path=out)
    return GlyphRunner(out, ram_words=16384)


POPCOUNT_CONTRACT = "popcount(r1) -> r2: count the 1-bits of r1 into r2"
POPCOUNT_INPUT = {1: 0xF0F0F0F0}          # oracle ABI: input arrives in r1
POPCOUNT_ARGV = {0: 0xF0F0F0F0}           # kernel ABI: arg0 @ word 750
POPCOUNT_GOLDEN = 16


def test_family_whitelist_blocks_without_model_calls():
    """Frozen contract: a corrupted/unknown family can never trip the
    model. E_ATLAS_FAMILY with escalations == 0."""
    with tempfile.TemporaryDirectory() as d:
        atlas = build_default_atlas()
        res = ingest(atlas, "mystery_routine", "kernel_internal",
                     POPCOUNT_CONTRACT, {2: POPCOUNT_GOLDEN},
                     input_registers=POPCOUNT_INPUT)
        assert res.code == "E_ATLAS_FAMILY"
        assert res.escalations == 0, "model must not be invoked"
        assert "mystery_routine" not in atlas.tiles


def test_unverified_never_reaches_atlas(monkeypatch):
    """Negative control at the ingest layer: a router that can't verify
    leaves the atlas untouched and hard-fails (no frontier fallback)."""
    from tools.glyph_gpt import autoatlas as aa
    from tools.glyph_gpt.escalate import EscalationResult, OracleResult

    def _fail(*a, **k):
        return EscalationResult(
            contract=a[0] if a else "", verified=False, attempts=k.get(
                "max_attempts", 6), error="no candidate verified in N")

    monkeypatch.setattr(aa, "escalate", _fail)
    with tempfile.TemporaryDirectory() as d:
        atlas = build_default_atlas()
        res = ingest(atlas, "popcount", "bitops", POPCOUNT_CONTRACT,
                     {2: POPCOUNT_GOLDEN}, input_registers=POPCOUNT_INPUT)
        assert res.code == "E_ATLAS_UNVERIFIED"
        assert not res.ok
        assert "popcount" not in atlas.tiles, "atlas must stay untouched"


@pytest.mark.skipif(not _ollama_available(), reason="local Ollama not reachable")
def test_full_loop_miss_to_verified_kernel_dispatch():
    """THE LOOP: miss -> local draft -> oracle -> atlas -> mailbox inject
    -> kernel re-dispatch -> word-exact result."""
    with tempfile.TemporaryDirectory() as d:
        atlas = build_default_atlas()
        assert "popcount" not in atlas.tiles, "precondition: the miss"
        runner = _baked_runner(Path(d))
        res = ingest(atlas, "popcount", "bitops", POPCOUNT_CONTRACT,
                     {2: POPCOUNT_GOLDEN}, input_registers=POPCOUNT_INPUT,
                     runner=runner, argv=POPCOUNT_ARGV)
        assert res.code == "OK", f"{res.code}: {res.detail}"
        assert res.escalations >= 1
        assert "popcount" in atlas.tiles, "verified tile registered"
        assert res.oracle_registers and \
            res.oracle_registers[2] == POPCOUNT_GOLDEN
        assert res.kernel_result == POPCOUNT_GOLDEN, (
            f"kernel {res.kernel_result:#x} != oracle {POPCOUNT_GOLDEN:#x}")
        assert res.kernel_exit == GH9_EXIT_OK
        assert res.kernel_status == KERNEL_OK


@pytest.mark.skipif(not _ollama_available(), reason="local Ollama not reachable")
def test_registered_tile_persists_and_replays_offline():
    """After the loop closes, the admitted pixels are resident: a FRESH
    runner on the post-run image replays the same tile with new argv —
    byte-exact (GH-9 persistence model, now fed by escalated tiles).

    Gate 1.5 (2026-09-08): the admission itself now carries a second,
    NON-self-complementary vector. A single golden 0xF0F0F0F0 admitted an
    inverted-polarity popcount (16 set == 16 clear — the dual function
    passes a self-complementary vector), which then diverged here on
    0xF000. Admission vectors must be chosen so a function's dual fails
    at least one of them."""
    with tempfile.TemporaryDirectory() as d:
        atlas = build_default_atlas()
        runner = _baked_runner(Path(d))
        res = ingest(atlas, "popcount", "bitops", POPCOUNT_CONTRACT,
                     {2: POPCOUNT_GOLDEN}, input_registers=POPCOUNT_INPUT,
                     runner=runner, argv=POPCOUNT_ARGV,
                     admission_vectors=[
                         # non-complementary probe: popcount(0x0000F000)=4,
                         # its dual (clear-bit count) returns 27 — the dual
                         # cannot pass both vectors.
                         {"seed_memory": {GH9_ARGV_WORD: 0x0000F000},
                          "expect_registers": {2: 4}},
                     ])
        assert res.code == "OK", res.detail
        tile = atlas.tiles["popcount"]["tile_text"]
        # offline replay: oracle on the registered text, different input.
        # The tile was drafted under the KERNEL ABI — its first instruction
        # loads r1 from memory[750] — so the replay seeds the argv word
        # (GH-8b/GH-9 persistence model), not input_registers.
        from tools.glyph_gpt.oracle import run_oracle
        replay = run_oracle(tile, expect_registers={2: 4},
                            seed_memory={GH9_ARGV_WORD: 0x0000F000})
        assert replay.passed, f"offline replay diverged: {replay.error}"
