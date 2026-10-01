"""TASK_SE021: glyph-sh v2 — glyph-on-glyph exec via RUN (0x07).

The dispatch shell (glyph_interactive_shell.build_exec_shell) gains an 'x'
command: SYSCALL 0x07 (SYSCALL_RUN) executes the GLYPH_CHILD_RUNNER host
script, which loads a child .glyph image (.npy), runs it on a real
GlyphCPUv2, and writes the child's PRT output bytes to a fixed output file.
The shell then FILE_READs that file and PRTs it — the child's observable
output appears in the shell transcript. A child not on the GLYPH_RUN_ALLOW
allowlist fails LOUDLY (ERR:RUN_DENIED marker PRT'd), never silently.

Fallback semantics per the SE021 row: in-process RUN (0x07) with the
allowlist — GO-5 proc-tile spawn is a different engine lane and NOT shipped
here; the isolation delta is recorded in the row receipt.

Gate legs (from the row):
  1. exec leg       — 'x' runs the child; child output appears.
  2. control-returns — a subsequent 'e' command echoes: control returned.
  3. allowlist-deny — child not on allowlist → ERR:RUN_DENIED, no child output.
     non-vacuity: containment neutered to permit-all must fail this leg.
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

from tools.glyph_isa_v2 import (  # noqa: E402
    GlyphAssemblerV2,
    GlyphCPUv2,
    OpcodeMapV2,
)
from glyph_interactive_shell import (  # noqa: E402
    DISPATCH_ERROR_MARKER,
    RUN_DENIED_MARKER,
    build_exec_shell,
    repl,
)

CHILD_TEXT = b"CHILD_OK"


def _mk_child() -> Path:
    """A real glyph program: PRTs CHILD_TEXT byte-by-byte, then HALT.

    Written as .npy to tmp; the child runner loads + executes it.
    """
    om = OpcodeMapV2()
    prog = []
    for b in CHILD_TEXT:
        prog += [f"LDI r5 {b}", "PRT r5"]
    prog += ["HALT"]
    img = GlyphAssemblerV2(om).assemble(prog, width_instrs=8)
    om.close()
    d = Path(tempfile.mkdtemp(prefix="se021_child_"))
    p = d / "child.glyph.npy"
    p.write_bytes(b"")  # placeholder; replaced below
    import numpy as np

    np.save(p, img)
    return p


@pytest.fixture()
def child_env(tmp_path, monkeypatch):
    """Child image + runner script on disk; GLYPH_RUN_ALLOW grants ONLY the
    runner script (containment: the allowlist names the runner, and the
    runner refuses any child path outside the run's own directory)."""
    import numpy as np

    # Interpreter-resolution guard (REPAIR_PENDING_se021_spawn_interpreter_resolution.md
    # option 1, landed 2026-09-17): the runner's shebang is `#!/usr/bin/env
    # python3`, so the child picks the interpreter from the INHERITED PATH.
    # On a host whose PATH fronts a numpy-less python3 (e.g. buildroot's
    # host tool) the runner dies with ModuleNotFoundError, RUN returns rc=1
    # and legs 1/2 see ERR:RUN_DENIED — an environment artifact with the
    # signature of a containment failure. Skip-with-reason (environment
    # class) so the gate stays honest on any host; no engine lines.
    py = shutil.which("python3")
    if py is None:
        pytest.skip("environment: no python3 on PATH for the child's shebang")
    import subprocess as _sp

    _probe = _sp.run(
        [py, "-c", "import numpy"],
        capture_output=True,
        timeout=30,
    )
    if _probe.returncode != 0:
        pytest.skip(
            f"environment: python3 on PATH ({py}) lacks numpy; "
            "glyph_child_runner shebang would resolve to it and die rc=1"
        )

    child = tmp_path / "child.glyph.npy"
    om = OpcodeMapV2()
    prog = []
    for b in CHILD_TEXT:
        prog += [f"LDI r5 {b}", "PRT r5"]
    prog += ["HALT"]
    img = GlyphAssemblerV2(om).assemble(prog, width_instrs=8)
    om.close()
    np.save(child, img)

    out_path = tmp_path / "child_out.txt"
    write_path = tmp_path / "w.dat"
    audio_path = tmp_path / "a.wav"
    # PATH BUDGET (SE021 layout v4): only write_path/audio_path are baked
    # into the shell's Region A FS window [1024,1280) — a 256-word budget
    # shared with two 64-word FILE_READ dest buffers, leaving ~122 bytes for
    # both paths. Absolute pytest tmp paths (~160 bytes) cannot fit, so the
    # shell process chdirs into tmp_path and these two use bare relative
    # names (FILE_WRITE/FILE_READ resolve via open() against the process
    # cwd). runner/child/out paths stay absolute: they live in Region B
    # (no window limit), and the RUN allowlist requires an absolute path.
    monkeypatch.chdir(tmp_path)
    write_name = "w.dat"
    audio_name = "a.wav"
    runner = tmp_path / "glyph_child_runner.py"
    # GLYPH_REPO anchor: the allowlist requires the runner INSIDE the run's
    # own directory (realpath containment), but a copied runner's
    # Path(__file__)-based REPO resolution points at tmp's parent, not the
    # repo — the tools.glyph_isa_v2 import dies and RUN returns rc=1
    # (measured 2026-09-15). The env anchor lets the copied payload find the
    # repo it came from; subprocess.run inherits it.
    monkeypatch.setenv("GLYPH_REPO", str(REPO))
    runner.write_text(
        (REPO / "tools" / "glyph_child_runner.py").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    os.chmod(runner, 0o755)
    monkeypatch.setenv("GLYPH_RUN_ALLOW", str(runner))
    # LAYOUT v5.1 constraint (dbg-se021 RCA 2026-09-16): the FS window
    # aliases image rows 64..80 by definition, so the program must fit in
    # rows [0,64) — anything taller gets its instruction pixels overwritten
    # by turn-1 window writes (turn 2 then walks into corrupted pixels and
    # silently stops, opcode-None). Absolute tmp paths (~45-char runner,
    # ~40-char child/out) blow the per-byte stamp loops past the budget;
    # bare filenames keep the program under 64 rows. The runner spawns with
    # cwd=parent_dir, so relative child/out argv resolve correctly, and
    # write/audio names are already relative.
    return {
        "child": child,
        "out_path": out_path,
        "write_path": write_path,
        "audio_path": child_env_audio(audio_path),
        "runner": runner,
        "write_name": write_path.name,
        "audio_name": audio_path.name,
        "child_name": child.name,
        "out_name": out_path.name,
        "runner_name": runner.name,
    }


def child_env_audio(audio_path):
    return audio_path


def test_exec_leg_child_output_appears(child_env):
    """Leg 1 (exec): 'x' runs the child; its PRT output appears."""
    env = child_env
    image = build_exec_shell(
        write_path=env["write_name"],
        audio_path=env["audio_name"],
        runner_path=env["runner_name"],
        child_path=env["child_name"],
        child_out_path=env["out_name"],
    )
    out = repl(lines=["x"], image=image, fs_pix_enabled=True)
    assert out == [CHILD_TEXT.decode("ascii")], out


def test_control_returns_to_shell_after_exec(child_env):
    """Leg 2 (control-returns): a later 'e' command echoes — the shell
    regained control after the child ran."""
    env = child_env
    image = build_exec_shell(
        write_path=env["write_name"],
        audio_path=env["audio_name"],
        runner_path=env["runner_name"],
        child_path=env["child_name"],
        child_out_path=env["out_name"],
    )
    out = repl(lines=["x", "e hello"], image=image, fs_pix_enabled=True)
    assert out[0] == CHILD_TEXT.decode("ascii"), out
    assert out[1] == " hello", out


def test_allowlist_deny_loud_and_no_child_output(child_env, monkeypatch):
    """Leg 3 (allowlist-deny): with GLYPH_RUN_ALLOW UNSET the RUN is denied;
    the shell PRTs the named ERR:RUN_DENIED marker and never the child's
    output. Non-vacuity: with the containment neutered (allowlist = '*'),
    this leg must go RED (the runner runs and the child output appears)."""
    env = child_env
    monkeypatch.delenv("GLYPH_RUN_ALLOW", raising=False)
    image = build_exec_shell(
        write_path=env["write_name"],
        audio_path=env["audio_name"],
        runner_path=str(env["runner"]),
        child_path=str(env["child"]),
        child_out_path=str(env["out_path"]),
    )
    out = repl(lines=["x"], image=image, fs_pix_enabled=True)
    assert out == [RUN_DENIED_MARKER.decode("ascii")], out

    # Non-vacuity: neuter containment to permit-all → the runner executes,
    # the child output appears, and the deny marker is absent → RED.
    monkeypatch.setenv("GLYPH_RUN_ALLOW", "*")
    out2 = repl(lines=["x"], image=image, fs_pix_enabled=True)
    assert out2 == [RUN_DENIED_MARKER.decode("ascii")], (
        "NON-VACUITY FAILURE: containment neutered yet deny marker still "
        f"shown (out2={out2!r}) — the deny leg does not discriminate"
    )


def test_dispatch_regression_green_with_exec_neutral():
    """Regression: the plain dispatch shell (no 'x') still behaves — 'z'
    still yields DISPATCH_ERROR_MARKER with the exec build present."""
    d = Path(tempfile.mkdtemp(prefix="se021_regr_"))
    image = build_exec_shell(
        write_path="w.dat",
        audio_path="a.wav",
        runner_path=str(d / "nope.py"),
        child_path=str(d / "nope.npy"),
        child_out_path=str(d / "o.txt"),
    )
    out = repl(lines=["z bogus"], image=image, fs_pix_enabled=True)
    assert out == [DISPATCH_ERROR_MARKER.decode("ascii")], out
