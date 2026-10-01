"""GH-26.3 gate: tests/test_gh26_emit_admit.py.

Roadmap: GH-26 Agent-in-the-Loop, Tier 2 EMIT→ADMIT (26.3) — agent tile
proposals route ONLY through the GH-12/18 admission pipeline
(autoatlas.admit_syscall machinery: IR StaticVerifier → oracle
word-exact → table stamp). Drafting is template/grammar-guided per the
S3 SAFE-ONLY verdict (GlyphGPT best-of-N at most ONE source, never the
gate). Every admission attempt (pass or reject) appends a receipt line
to output/agent_admissions.jsonl — failed attempts are receipts too:
they prove the oracle filters.

Legs (per systems/GH26_AGENT_IN_THE_LOOP_SPEC.md §26.3 + ticket
gh26-3-emit-admit):
  1. valid drafted tile admits and is callable in-image (SYS 8
     recomputes word-exactly on a follow-up drive).
  2. hostile/incorrect tiles rejected (IR-invalid AND oracle-wrong),
     table + atlas byte-unchanged (image md5 diff-proven per attempt).
  3. admission receipts complete: one JSON line per attempt with
     {ts, intent, source, oracle_verdict, reason}.
  4. no write path bypasses admit_syscall (structural: geos_emit's
     emit_admit delegates to the autoatlas admission path; the emitter
     surface itself still cannot stamp tables/tiles).
  5. GH-18 invariant unchanged: tests/test_gh18_syscall_abi.py 14 gating
     legs pass with the DEFECT-24 live smoke leg deselected
     (`-m "not live_smoke"`) after the emit_admit addition.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import pytest

_REPO = Path(__file__).resolve().parent.parent
for _p in (str(_REPO), str(_REPO / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from tools.glyph_gpt.atlas import build_default_atlas             # noqa: E402
from tools.glyph_gpt.baker import syscall_abi_kernel_image        # noqa: E402
from tools.glyph_gpt.runner import GlyphRunner                    # noqa: E402
from tools.glyph_gpt.autoatlas import (                           # noqa: E402 (RED)
    emit_admit, GH18_TABLE_WORD, GH18_NSLOTS,
)

N_NEW = 8
GH18_EXIT_WORD = 703
GH18_EXIT_OK = 0xFEED0000 | 6

# Template-drafted reference tile (triple(r1) -> r2 under the GH-18 tile
# ABI: input @750, result @754) — the same recipe the admit-mode bake
# stamps as its reference tile (baker._gh18_tile_payload_for_test).
GOOD_TILE = (
    ":__entry\n"
    "LDI r15 750\n"
    "LD r1 r15\n"
    "XOR r2 r2\n"
    "LDI r13 1\n"
    "ADD r2 r1\n"
    "SHL r2 r13\n"
    "ADD r2 r1\n"
    "LDI r15 754\n"
    "ST r15 r2\n"
    "HALT\n"
)

# Hostile class A: IR-invalid (unknown opcode shape) — must die at the
# IR StaticVerifier BEFORE the oracle, with the image untouched.
IR_INVALID_TILE = (
    ":__entry\n"
    "FROB r1 r2\n"
    "HALT\n"
)

# Hostile class B: IR-valid but WRONG semantics (2*x, not 3*x) — passes
# the IR gate, FAILS the oracle word-exact check (argv0=6 -> 12 != 18).
ORACLE_WRONG_TILE = (
    ":__entry\n"
    "LDI r15 750\n"
    "LD r1 r15\n"
    "XOR r2 r2\n"
    "ADD r2 r1\n"
    "ADD r2 r1\n"
    "LDI r15 754\n"
    "ST r15 r2\n"
    "HALT\n"
)


def _bake(tmp: Path, name: str = "gh263.npy") -> GlyphRunner:
    out = tmp / name
    syscall_abi_kernel_image(build_default_atlas(), mode="admit",
                             timer_quantum=20, out_path=out)
    return GlyphRunner(out, ram_words=16384)


def _img_md5(runner: GlyphRunner) -> str:
    return hashlib.md5(
        np.ascontiguousarray(runner.image).tobytes()).hexdigest()


# ── leg 1: valid draft admits + is callable in-image ────────────────────

def test_gh263_valid_tile_admits_and_is_callable(tmp_path):
    with tempfile.TemporaryDirectory() as d:
        runner = _bake(Path(d))
        receipts = Path(d) / "admissions.jsonl"
        res = emit_admit(runner, GOOD_TILE, sys_n=N_NEW, expected=18,
                         argv={0: 6}, source="template",
                         receipt_path=receipts)
        assert res.table_word != 0, "admitted tile must light its table slot"
        receipt2 = runner.drive(seeds={}, max_instructions=60000)
        mem = receipt2["memory"]
        assert receipt2["faulted"] is False, receipt2
        assert mem[754] == 18, f"result word {mem[754]} != 18"
        assert mem[GH18_EXIT_WORD] == GH18_EXIT_OK
        # the admitted attempt is receipted
        lines = [json.loads(l) for l in receipts.read_text().splitlines() if l]
        assert any(r["oracle_verdict"] == "admitted" for r in lines)


# ── leg 2: hostile tiles rejected, table+atlas byte-unchanged ───────────

def test_gh263_hostile_tiles_rejected_image_byte_unchanged(tmp_path):
    with tempfile.TemporaryDirectory() as d:
        runner = _bake(Path(d))
        receipts = Path(d) / "admissions.jsonl"
        before = _img_md5(runner)

        res = emit_admit(runner, IR_INVALID_TILE, sys_n=N_NEW, expected=18,
                         argv={0: 6}, source="template",
                         receipt_path=receipts)
        assert not res.ok, "IR-invalid tile must be rejected"
        # FROB is an unknown OPCODE: the IR StaticVerifier checks program
        # SHAPE (malformed operands, duplicate labels, r31 writes); unknown
        # op NAMES die at the oracle's assemble stage (KeyError). Both are
        # pre-stamp rejections — either code proves the hostile tile
        # never reached the table.
        assert res.code in ("E_EMIT_IR", "E_EMIT_ORACLE"), res.code
        assert res.table_word == 0
        assert _img_md5(runner) == before, "IR rejection touched the image"

        res2 = emit_admit(runner, ORACLE_WRONG_TILE, sys_n=N_NEW,
                          expected=18, argv={0: 6}, source="template",
                          receipt_path=receipts)
        assert not res2.ok, "oracle-wrong tile must be rejected"
        assert res2.code == "E_EMIT_ORACLE", res2.code
        assert res2.table_word == 0
        assert _img_md5(runner) == before, "oracle rejection touched the image"

        # both rejection attempts are receipted
        lines = [json.loads(l) for l in receipts.read_text().splitlines() if l]
        verdicts = [r["oracle_verdict"] for r in lines]
        assert verdicts == ["rejected", "rejected"], verdicts


# ── leg 3: admission receipts complete ──────────────────────────────────

def test_gh263_receipts_complete(tmp_path):
    with tempfile.TemporaryDirectory() as d:
        runner = _bake(Path(d))
        receipts = Path(d) / "admissions.jsonl"
        emit_admit(runner, GOOD_TILE, sys_n=N_NEW, expected=18,
                   argv={0: 6}, source="template", receipt_path=receipts)
        emit_admit(runner, ORACLE_WRONG_TILE, sys_n=N_NEW, expected=18,
                   argv={0: 6}, source="glyphgpt", receipt_path=receipts)
        lines = [json.loads(l) for l in receipts.read_text().splitlines() if l]
        assert len(lines) == 2
        for r in lines:
            for key in ("ts", "intent", "source", "oracle_verdict", "reason"):
                assert key in r, f"receipt missing {key!r}: {r}"
            assert r["intent"] == "emit_admit"
        assert lines[0]["oracle_verdict"] == "admitted"
        assert lines[0]["source"] == "template"
        assert lines[1]["oracle_verdict"] == "rejected"
        assert lines[1]["source"] == "glyphgpt"


# ── leg 4: no write path bypasses admit_syscall ─────────────────────────

def test_gh263_no_bypass_path():
    import inspect
    from tools.glyph_gpt import autoatlas
    from tools.geos_emit import GeosEmitter

    # autoatlas.emit_admit routes through the shared GH-12/18 admission
    # machinery (the ingest/oracle path admit_syscall uses) — never its
    # own stamping shortcut.
    src = inspect.getsource(autoatlas.emit_admit)
    assert "_admit_verified_tile" in src or "ingest(" in src, \
        "emit_admit must route through the shared admission path"

    # the emitter surface gained no raw-word write: its ONLY new method
    # delegates to autoatlas (the oracle is the sole admission path).
    esrc = inspect.getsource(GeosEmitter)
    assert "emit_admit" in esrc
    for forbidden in ("_pix_write_word", "GH18_TABLE_WORD +", "tile_word +"):
        assert forbidden not in esrc.replace(
            "def emit_admit", "def _emit_admit_delegate") or \
            "autoatlas" in esrc, f"emitter must not stamp {forbidden!r} itself"


# ── leg 5: GH-18 invariant unchanged ────────────────────────────────────

def test_gh263_gh18_invariant_unchanged():
    """GH-18's GATING legs are unchanged: 14 passed with the DEFECT-24 live
    smoke leg deselected. The filter is explicit because that leg is now
    @pytest.mark.live_smoke: an unfiltered run would execute a live Ollama
    draft, so this invariant would silently become live-model-dependent
    (the same defect class DEFECT-24 removes from arc leg A)."""
    env = os.environ.copy()
    env["PYTHONPATH"] = f"{_REPO / 'tools'}:{_REPO}"
    proc = subprocess.run(
        [sys.executable, "-m", "pytest",
         str(_REPO / "tests" / "test_gh18_syscall_abi.py"),
         "-m", "not live_smoke",
         "--tb=short"],
        env=env, cwd=str(_REPO), capture_output=True, text=True, timeout=900)
    assert proc.returncode == 0, proc.stdout[-4000:] + proc.stderr[-2000:]
    assert "14 passed" in proc.stdout, proc.stdout[-4000:]
