"""R2.2 gate (PRODUCT_ROADMAP.md R2.2 — "Toolchain UX: one command compiles a
program to a glyph/tile artifact and runs it. Target: someone who has never
read this repo.")

Gates tools/glyph_run.py, the single entry point over the landed bake + run
stack (bake_image + GlyphRunner + GlyphCPUv2 — the same engines the frozen
R2.1 box-ABI stack runs on).

Legs:
  GREEN
   1. compile+run from source: examples/sum_1_to_5.glyph -> artifact written,
      receipt HALT, output [15] (the PRT'd result), exit 0.
   2. run artifact alone (no source): the baked .png from leg 1 re-executes
      standalone — the artifact IS the program. Same result.
   3. artifact-only run picks up .npy too (round-trips the container).
  RED (non-vacuity — policy rule 4, shown at landing time)
   4. bad source (undefined label) -> exit 2, no artifact written, message
      names the failure.
   5. faulting source (USER store is fine here; use a jump out of bounds via
      a hand-written coordinate — the SE023 silent-corruption vector — so the
      assembler REJECTS it; instead: out-of-RAM LD is a legal wrap... use the
      real fault path: budget) — see leg 5: a never-terminating program hits
      the instruction budget -> exit 3 (the "still running" diagnosis).
   6. missing file -> exit 4.
   7. --json emits parseable JSON with the required keys.

What this does NOT prove: WGSL-shader-path parity (the CPU oracle only —
known open lane defect), box-ABI supervisor behavior (this is the plain
single-box path), rate/floor claims.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
GLYPH_RUN = REPO / "tools" / "glyph_run.py"
EXAMPLE = REPO / "examples" / "sum_1_to_5.glyph"


def _run_cli(*argv: str, cwd: Path = REPO):
    return subprocess.run(
        [sys.executable, str(GLYPH_RUN), *argv],
        capture_output=True, text=True, cwd=str(cwd), timeout=120,
    )


def test_compile_and_run_from_source(tmp_path):
    """Leg 1: source -> artifact -> HALT with PRT'd output 15, exit 0."""
    out = tmp_path / "sum.glyph.png"
    r = _run_cli(str(EXAMPLE), "-o", str(out))
    assert r.returncode == 0, f"expected exit 0, got {r.returncode}: {r.stderr}"
    assert out.exists(), "artifact not written"
    assert "result   : HALT" in r.stdout
    assert "output   : 15" in r.stdout


def test_run_artifact_without_source(tmp_path):
    """Leg 2: the baked .png artifact alone re-executes — artifact IS program."""
    out = tmp_path / "sum.glyph.png"
    r1 = _run_cli(str(EXAMPLE), "-o", str(out))
    assert r1.returncode == 0
    r2 = _run_cli(str(out))
    assert r2.returncode == 0, f"artifact-only run failed: {r2.stderr}"
    assert "result   : HALT" in r2.stdout
    assert "output   : 15" in r2.stdout


def test_run_artifact_npy_roundtrip(tmp_path):
    """Leg 3: .npy container round-trips through the artifact-only path."""
    np = pytest.importorskip("numpy")
    out_png = tmp_path / "sum.glyph.png"
    r1 = _run_cli(str(EXAMPLE), "-o", str(out_png))
    assert r1.returncode == 0
    out_npy = tmp_path / "sum.glyph.npy"
    sys.path.insert(0, str(REPO))
    from PIL import Image
    np.save(out_npy, np.array(Image.open(out_png).convert("RGB")))
    r2 = _run_cli(str(out_npy))
    assert r2.returncode == 0
    assert "output   : 15" in r2.stdout


def test_red_bad_source_rejected(tmp_path):
    """RED leg: bad source -> exit 2, refusal names the failure, no artifact."""
    bad = tmp_path / "bad.glyph"
    bad.write_text(":__entry\n    JMP :nowhere\n    HALT\n")
    out = tmp_path / "bad.glyph.png"
    r = _run_cli(str(bad), "-o", str(out))
    assert r.returncode == 2, f"expected exit 2, got {r.returncode}"
    assert not out.exists(), "artifact must NOT be written for bad source"
    assert "compile failed" in r.stderr


def test_red_nonterminating_program_hits_budget(tmp_path):
    """RED leg: never-halting program -> exit 3 with the NO HALT diagnosis."""
    loop = tmp_path / "loop.glyph"
    loop.write_text(":__entry\n    JMP :__entry\n")
    r = _run_cli(str(loop), "-o", str(tmp_path / "loop.glyph.png"),
                 "--max-instructions", "5000")
    assert r.returncode == 3, f"expected exit 3, got {r.returncode}"
    assert "NO HALT" in r.stdout


def test_red_corrupted_artifact_produces_no_result(tmp_path):
    """RED leg: overwriting the artifact's first instruction pixel with an
    unknown opcode (1,1,1) must change the outcome — proves the artifact-only
    run executes THIS artifact's pixels, not a rebuilt/cached program."""
    np = pytest.importorskip("numpy")
    out = tmp_path / "sum.glyph.png"
    assert _run_cli(str(EXAMPLE), "-o", str(out)).returncode == 0
    from PIL import Image
    img = np.array(Image.open(out).convert("RGB"))
    img[0, 0] = (1, 1, 1)  # canonical unknown-opcode pixel (ENG-1 harness)
    corrupt = tmp_path / "corrupt.glyph.png"
    Image.fromarray(img).save(corrupt)
    r = _run_cli(str(corrupt))
    assert "output   : 15" not in r.stdout, \
        "corrupted artifact still produced 15 — artifact-only run is not real"


def test_red_missing_file(tmp_path):
    """RED leg: missing input -> exit 4."""
    r = _run_cli(str(tmp_path / "does_not_exist.glyph"))
    assert r.returncode == 4


def test_json_receipt(tmp_path):
    """Leg 7: --json emits parseable JSON carrying the required keys."""
    out = tmp_path / "sum.glyph.png"
    r = _run_cli(str(EXAMPLE), "-o", str(out), "--json")
    assert r.returncode == 0
    rec = json.loads(r.stdout)
    for key in ("artifact", "halted", "faulted", "steps", "output", "registers"):
        assert key in rec, f"receipt missing '{key}'"
    assert rec["halted"] is True and rec["faulted"] is False
    assert rec["output"] == [15]
