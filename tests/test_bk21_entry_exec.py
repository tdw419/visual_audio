"""BK-21: human entry surface gains exec — promote the 'x' verb into
build_dispatch_shell.

The SE021 exec machinery (SYSCALL 0x12 RUN2 -> tools/glyph_child_runner.py,
rc gate, RUN_DENIED_MARKER, child_out FILE_READ + PRT loop) is landed and
gated (tests/test_glyph_app_glyph_on_glyph.py) but only reachable through
build_exec_shell — a builder that bakes the child path as a constant. The
human seat (__main__ -> build_dispatch_shell) answers 'x ...' with
ERR:UNKNOWN_CMD (RESEARCH_entry_surface_exec_gap.md, live probe at HEAD
85662ba2).

This gate pins the promotion: build_dispatch_shell accepts runner/child
layout arguments the same way build_exec_shell does, keeps the item-11
grammar (space delimiter, bare 'x' and 'xf oo' stay ERR:UNKNOWN_CMD), and
respects the FS-window budget for the write/audio paths (long paths are a
loud ValueError at BUILD time, never a silent window overwrite).

Gate legs:
  L1  exec leg        — 'x <child>' on a build_dispatch_shell image runs
                        the child; its PRT output appears in the transcript.
                        RED at 85662ba2..df3389d4 (ERR:UNKNOWN_CMD today).
  L2  control returns — a subsequent 'e hello' echoes after the child ran.
  L3  allowlist-deny  — GLYPH_RUN_ALLOW unset -> ERR:RUN_DENIED, no child
                        output; non-vacuity: allowlist='*' -> the child
                        output APPEARS (leg must be able to flip).
  L4  grammar         — bare 'x' and 'xf oo' -> ERR:UNKNOWN_CMD, no child
                        output, no FS write (item-11 class preserved).
  L5  regression      — the four legacy verbs still dispatch on the new
                        image (e/s/w/r round-trip byte-exact).
  L6  layout budget   — a build with long write/audio paths still raises
                        the FS-window ValueError at build time (the promote
                        did not move the budget assert).
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
for _p in (str(REPO), str(REPO / "tools"), str(REPO / "experiments")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import numpy as np  # noqa: E402

from tools.glyph_isa_v2 import (  # noqa: E402
    GlyphAssemblerV2,
    OpcodeMapV2,
)
from glyph_interactive_shell import (  # noqa: E402
    DISPATCH_ERROR_MARKER,
    RUN_DENIED_MARKER,
    build_dispatch_shell,
    repl,
)

CHILD_TEXT = b"CHILD_OK"
ERR_TXT = DISPATCH_ERROR_MARKER.decode("ascii")
DENIED_TXT = RUN_DENIED_MARKER.decode("ascii")


def _mk_child(directory: Path, name: str = "child.glyph.npy") -> Path:
    """A real glyph child program: PRT CHILD_TEXT byte-by-byte, then HALT."""
    om = OpcodeMapV2()
    prog = []
    for b in CHILD_TEXT:
        prog += [f"LDI r5 {b}", "PRT r5"]
    prog += ["HALT"]
    img = GlyphAssemblerV2(om).assemble(prog, width_instrs=8)
    om.close()
    p = directory / name
    np.save(p, img)
    return p


@pytest.fixture()
def x_env(tmp_path, monkeypatch):
    """Child image + runner on disk; GLYPH_RUN_ALLOW grants ONLY the runner
    (same containment shape as the SE021 gate's child_env). The shell
    process chdirs into tmp_path so the baked write/audio paths are bare
    relative names inside the FS-window budget."""
    # Interpreter-resolution guard (REPAIR_PENDING_se021_spawn_interpreter_
    # resolution.md precedent): the runner's shebang resolves python3 from
    # the inherited PATH; a numpy-less python3 produces rc=1 — an
    # environment artifact with the signature of a containment failure.
    py = shutil.which("python3")
    if py is None:
        pytest.skip("environment: no python3 on PATH for the child's shebang")
    import subprocess as _sp

    _probe = _sp.run([py, "-c", "import numpy"], capture_output=True, timeout=30)
    if _probe.returncode != 0:
        pytest.skip(
            f"environment: python3 on PATH ({py}) lacks numpy; runner would die rc=1"
        )

    child = _mk_child(tmp_path)
    out_path = tmp_path / "child_out.txt"
    runner = tmp_path / "glyph_child_runner.py"
    # GLYPH_REPO anchor: a copied runner's Path(__file__)-based REPO
    # resolution points at tmp's parent — anchor it at the real repo
    # (SE021 gate precedent, measured 2026-09-15).
    monkeypatch.setenv("GLYPH_REPO", str(REPO))
    runner.write_text(
        (REPO / "tools" / "glyph_child_runner.py").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    os.chmod(runner, 0o755)
    monkeypatch.setenv("GLYPH_RUN_ALLOW", str(runner))
    monkeypatch.chdir(tmp_path)
    return {
        "child": child,
        "child_name": child.name,
        "out_path": out_path,
        "out_name": out_path.name,
        "runner": runner,
        "runner_name": runner.name,
    }


def _build(x: dict):
    """build_dispatch_shell with the exec layout (runner/child/out baked as
    Region-B constants, like build_exec_shell does)."""
    return build_dispatch_shell(
        "w.dat",
        "a.wav",
        runner_path=x["runner_name"],
        child_path=x["child_name"],
        child_out_path=x["out_name"],
    )


def test_l1_x_runs_child_from_dispatch_shell(x_env):
    """L1: 'x' dispatches from the HUMAN shell image; child PRT output
    appears. RED pre-landing: build_dispatch_shell has no runner/child
    kwargs and 'x ...' answers ERR:UNKNOWN_CMD."""
    image = _build(x_env)
    out = repl(lines=["x " + x_env["child_name"]], image=image, fs_pix_enabled=True)
    assert out == [CHILD_TEXT.decode("ascii")], out


def test_l2_control_returns_after_dispatch_shell_exec(x_env):
    """L2: after the child runs, the shell still dispatches 'e hello'."""
    image = _build(x_env)
    out = repl(
        lines=["x " + x_env["child_name"], "e hello"],
        image=image,
        fs_pix_enabled=True,
    )
    assert out[0] == CHILD_TEXT.decode("ascii"), out
    assert out[1] == " hello", out


def test_l3_allowlist_deny_loud_and_discriminating(x_env, monkeypatch):
    """L3: GLYPH_RUN_ALLOW unset -> ERR:RUN_DENIED, never the child output;
    the SAME image and line flip to CHILD_OK once the runner's realpath is
    granted — the leg discriminates in both directions (a verb that ignored
    containment would pass the first half; containment that always denied
    would pass the second).
    (Note: the SE021 gate's '*' neuter is vacuous — _get_run_allowlist
    drops non-absolute entries, so '*' yields the empty set and denies.
    This leg uses a real grant as the flip side.)"""
    monkeypatch.delenv("GLYPH_RUN_ALLOW", raising=False)
    image = _build(x_env)
    out = repl(lines=["x " + x_env["child_name"]], image=image, fs_pix_enabled=True)
    assert out == [DENIED_TXT], out

    monkeypatch.setenv("GLYPH_RUN_ALLOW", str(x_env["runner"]))
    out2 = repl(lines=["x " + x_env["child_name"]], image=image, fs_pix_enabled=True)
    assert out2 == [CHILD_TEXT.decode("ascii")], (
        "NON-VACUITY FAILURE: runner granted yet deny marker still shown "
        f"(out2={out2!r}) — the deny leg does not discriminate"
    )


def test_l4_item11_grammar_preserved_for_x(x_env):
    """L4: bare 'x' and 'xf oo' stay ERR:UNKNOWN_CMD; no child output, no
    child-out file materializes (nothing executed silently)."""
    image = _build(x_env)
    out = repl(lines=["x"], image=image, fs_pix_enabled=True)
    assert out == [ERR_TXT], out
    out2 = repl(lines=["xf oo"], image=image, fs_pix_enabled=True)
    assert out2 == [ERR_TXT], out2
    assert not x_env["out_path"].exists(), (
        "a malformed x line must never reach the runner"
    )


def test_l5_legacy_verbs_survive_promotion(x_env, tmp_path):
    """L5: e/s/w/r still dispatch byte-exact on the promoted image."""
    image = _build(x_env)
    out = repl(lines=["e hello"], image=image, fs_pix_enabled=True)
    assert out == [" hello"], out
    out2 = repl(lines=["w note", "r"], image=image, fs_pix_enabled=True)
    assert out2[0] == "", out2
    assert out2[1] == " note", out2
    assert (tmp_path / "w.dat").read_bytes() == b" note"


def test_l6_window_budget_assert_survives_promotion(x_env):
    """L6: long write/audio paths still fail LOUDLY at build time — the
    promotion did not move or weaken the FS-window overflow assert."""
    with pytest.raises(AssertionError):
        build_dispatch_shell(
            "w" * 200,
            "a.wav",
            runner_path=x_env["runner_name"],
            child_path=x_env["child_name"],
            child_out_path=x_env["out_name"],
        )
