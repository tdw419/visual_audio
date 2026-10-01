#!/usr/bin/env python3
"""GH-12 capstone gate: AutoAtlasIngest — the loop closes.

Option 3 implementation (RULING_gh12_gate_determinism.md):
Split the claim into:
  1. Deterministic leg (load-bearing, in the arc): scripted candidate fed to
     ingest(), assert admission (OK) and offline replay reproduces the atlas
     byte-identically. Passes model-free.
  2. Negative leg: scripted candidate that cannot reach the bar is rejected
     with E_ATLAS_UNVERIFIED and no tile is written (atlas untouched).
  3. Live-draft smoke leg (non-blocking, out of the arc): records outcome to
     output/gh12_live_smoke_<head>.txt and never gates.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
for _p in (str(_REPO), str(_REPO / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from tools.glyph_gpt.atlas import build_default_atlas, RoutineAtlas  # noqa: E402
from tools.glyph_gpt.autoatlas import (                               # noqa: E402
    ingest, ESCALATABLE_FAMILIES, _pixel_words,
    GH9_ARGV_WORD, GH9_ARGV_RESULT, GH9_EXIT_WORD, GH9_EXIT_OK,
    KERNEL_STATUS_WORD, KERNEL_OK,
)
from tools.glyph_gpt.baker import loader_kernel_image                 # noqa: E402
from tools.glyph_gpt.runner import GlyphRunner                        # noqa: E402
import glyph_gpt.escalate as esc1                                    # noqa: E402
import tools.glyph_gpt.escalate as esc2                               # noqa: E402


def _ollama_available() -> bool:
    try:
        with urllib.request.urlopen(
                "http://localhost:11434/api/tags", timeout=3) as r:
            return bool(json.loads(r.read()).get("models"))
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

# Canonical scripted candidate: passes contract + admission vectors + KERNEL ABI
SCRIPTED_POPCOUNT_CANDIDATE = """\
LDI r15 750
LD r1 r15
LDI r3 1
LDI r4 0
LDI r6 32
XOR r2 r2
:loop
CMP r6 r4
JZ :done
XOR r5 r5
ADD r5 r1
AND r5 r3
CMP r5 r4
JZ :skip
ADD r2 r3
:skip
SHR r1 r3
SUB r6 r3
JMP :loop
:done
LDI r15 754
ST r15 r2
LDI r14 4276944905
LDI r15 703
ST r15 r14
HALT
"""

EXPECTED_POPCOUNT_BYTES = SCRIPTED_POPCOUNT_CANDIDATE.strip().encode("utf-8")


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
    from tools.glyph_gpt.escalate import EscalationResult

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


def test_negative_scripted_candidate_unverified_never_written(monkeypatch):
    """Gate Leg 3: Negative leg.
    A scripted candidate that cannot reach the bar is rejected with
    E_ATLAS_UNVERIFIED and no tile is written (assert the atlas is unchanged)."""
    bad_candidate = "LDI r2 0\nHALT\n"
    monkeypatch.setattr("tests.test_gh12_autoatlas._ollama_available", lambda: False)
    monkeypatch.setattr(esc1, "OLLAMA_URL", "http://127.0.0.1:9")
    monkeypatch.setattr(esc2, "OLLAMA_URL", "http://127.0.0.1:9")
    monkeypatch.setattr(esc1, "_ollama", lambda *a, **k: bad_candidate)
    monkeypatch.setattr(esc2, "_ollama", lambda *a, **k: bad_candidate)

    with tempfile.TemporaryDirectory() as d:
        atlas = build_default_atlas()
        initial_tiles = dict(atlas.tiles)
        runner = _baked_runner(Path(d))
        res = ingest(atlas, "popcount", "bitops", POPCOUNT_CONTRACT,
                     {2: POPCOUNT_GOLDEN}, input_registers=POPCOUNT_INPUT,
                     runner=runner, argv=POPCOUNT_ARGV, max_attempts=2,
                     admission_vectors=[
                         {"seed_memory": {GH9_ARGV_WORD: 0x0000F000},
                          "expect_registers": {2: 4}},
                     ])
        assert res.code == "E_ATLAS_UNVERIFIED", f"expected E_ATLAS_UNVERIFIED, got {res.code}"
        assert not res.ok
        assert "popcount" not in atlas.tiles, "unverified tile must not be in atlas"
        assert atlas.tiles == initial_tiles, "atlas must remain completely unchanged"


def test_full_loop_miss_to_verified_kernel_dispatch(monkeypatch):
    """Gate Leg 1: Deterministic admission, model-free.
    With the model unavailable (_ollama_available() forced False or endpoint
    pointed at a dead port), the scripted candidate ingests -> res.code == 'OK'
    and a tile is written."""
    monkeypatch.setattr("tests.test_gh12_autoatlas._ollama_available", lambda: False)
    monkeypatch.setattr(esc1, "OLLAMA_URL", "http://127.0.0.1:9")
    monkeypatch.setattr(esc2, "OLLAMA_URL", "http://127.0.0.1:9")
    monkeypatch.setattr(esc1, "_ollama", lambda *a, **k: SCRIPTED_POPCOUNT_CANDIDATE)
    monkeypatch.setattr(esc2, "_ollama", lambda *a, **k: SCRIPTED_POPCOUNT_CANDIDATE)
    assert not _ollama_available(), "model must be forced unavailable"

    with tempfile.TemporaryDirectory() as d:
        atlas = build_default_atlas()
        assert "popcount" not in atlas.tiles, "precondition: the miss"
        runner = _baked_runner(Path(d))
        res = ingest(atlas, "popcount", "bitops", POPCOUNT_CONTRACT,
                     {2: POPCOUNT_GOLDEN}, input_registers=POPCOUNT_INPUT,
                     runner=runner, argv=POPCOUNT_ARGV)
        assert res.code == "OK", f"{res.code}: {res.detail}"
        assert res.escalations == 1
        assert "popcount" in atlas.tiles, "verified tile registered"
        assert res.oracle_registers and res.oracle_registers[2] == POPCOUNT_GOLDEN
        assert res.kernel_result == POPCOUNT_GOLDEN, (
            f"kernel {res.kernel_result:#x} != oracle {POPCOUNT_GOLDEN:#x}")
        assert res.kernel_exit == GH9_EXIT_OK
        assert res.kernel_status == KERNEL_OK


def test_registered_tile_persists_and_replays_offline(monkeypatch):
    """Gate Leg 2: Byte-identical offline replay.
    Replay the written atlas offline and compare against the expected bytes
    exactly (not 'contains') — this is the property the gate exists to protect."""
    monkeypatch.setattr("tests.test_gh12_autoatlas._ollama_available", lambda: False)
    monkeypatch.setattr(esc1, "OLLAMA_URL", "http://127.0.0.1:9")
    monkeypatch.setattr(esc2, "OLLAMA_URL", "http://127.0.0.1:9")
    monkeypatch.setattr(esc1, "_ollama", lambda *a, **k: SCRIPTED_POPCOUNT_CANDIDATE)
    monkeypatch.setattr(esc2, "_ollama", lambda *a, **k: SCRIPTED_POPCOUNT_CANDIDATE)

    with tempfile.TemporaryDirectory() as d:
        atlas = build_default_atlas()
        runner = _baked_runner(Path(d))
        res = ingest(atlas, "popcount", "bitops", POPCOUNT_CONTRACT,
                     {2: POPCOUNT_GOLDEN}, input_registers=POPCOUNT_INPUT,
                     runner=runner, argv=POPCOUNT_ARGV,
                     admission_vectors=[
                         {"seed_memory": {GH9_ARGV_WORD: 0x0000F000},
                          "expect_registers": {2: 4}},
                     ])
        assert res.code == "OK", res.detail

        # 1. Assert tile was written and compare bytes exactly against expected bytes
        tile = atlas.tiles["popcount"]["tile_text"]
        tile_bytes = tile.encode("utf-8")
        assert tile_bytes == EXPECTED_POPCOUNT_BYTES, (
            f"tile bytes mismatch:\nactual: {tile_bytes}\nexpected: {EXPECTED_POPCOUNT_BYTES}"
        )

        # 2. Persist the atlas to disk (written atlas)
        atlas_path = Path(d) / "written_atlas.jsonl"
        atlas.save(atlas_path)
        written_bytes = atlas_path.read_bytes()

        # 3. Reload the written atlas offline
        reloaded_atlas = RoutineAtlas.load(atlas_path)
        reloaded_tile = reloaded_atlas.tiles["popcount"]["tile_text"]
        assert reloaded_tile.encode("utf-8") == EXPECTED_POPCOUNT_BYTES, (
            "reloaded tile must match expected bytes exactly"
        )

        # 4. Save reloaded atlas and assert byte-identical serialization
        reloaded_path = Path(d) / "reloaded_atlas.jsonl"
        reloaded_atlas.save(reloaded_path)
        assert reloaded_path.read_bytes() == written_bytes, (
            "offline reload must reproduce atlas byte-identically"
        )

        # 5. Offline replay via oracle on the reloaded tile text with different input
        from tools.glyph_gpt.oracle import run_oracle
        replay = run_oracle(reloaded_tile, expect_registers={2: 4},
                            seed_memory={GH9_ARGV_WORD: 0x0000F000})
        assert replay.passed, f"offline replay diverged: {replay.error}"
        assert replay.registers[2] == 4


@pytest.mark.live_smoke
def test_live_draft_smoke_nonblocking():
    """Gate Leg 4: Non-blocking smoke.
    The live leg, when it runs, writes output/gh12_live_smoke_<head>.txt
    (model tag, candidates tried, rc, seconds) and its exit status does not
    affect the arc. It never gates."""
    from tools.glyph_gpt.escalate import OLLAMA_MODEL

    try:
        head = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(_REPO), text=True
        ).strip()
    except Exception:
        head = "unknown"

    smoke_path = _REPO / "output" / f"gh12_live_smoke_{head}.txt"
    smoke_path.parent.mkdir(parents=True, exist_ok=True)

    if not _ollama_available():
        smoke_path.write_text(
            f"model: {OLLAMA_MODEL}\n"
            f"candidates_tried: 0\n"
            f"rc: 0\n"
            f"seconds: 0.00\n"
            f"note: skipped (ollama not available)\n"
        )
        return

    t0 = time.time()
    candidates = 0
    rc = 1
    try:
        with tempfile.TemporaryDirectory() as d:
            atlas = build_default_atlas()
            runner = _baked_runner(Path(d))
            res = ingest(atlas, "popcount", "bitops", POPCOUNT_CONTRACT,
                         {2: POPCOUNT_GOLDEN}, input_registers=POPCOUNT_INPUT,
                         runner=runner, argv=POPCOUNT_ARGV, max_attempts=6,
                         admission_vectors=[
                             {"seed_memory": {GH9_ARGV_WORD: 0x0000F000},
                              "expect_registers": {2: 4}},
                         ])
            candidates = res.escalations
            rc = 0 if res.code == "OK" else 1
    except Exception:
        rc = 1

    elapsed = time.time() - t0
    smoke_path.write_text(
        f"model: {OLLAMA_MODEL}\n"
        f"candidates_tried: {candidates}\n"
        f"rc: {rc}\n"
        f"seconds: {elapsed:.2f}\n"
    )
    # Never gates: its failure must not fail the run nor the arc.
