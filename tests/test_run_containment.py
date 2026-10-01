import os
from pathlib import Path
import subprocess
import types
from typing import Tuple
import numpy as np
import pytest

from tools.glyph_isa_v2 import OpcodeMapV2, GlyphCPUv2, GlyphAssemblerV2
import tools.glyph_isa_v2 as glyph_isa_v2
import tests.test_glyph_run_program as test_glyph_run_program


class RunnerDouble:
    """Mock runner to verify invocation without spawning processes."""
    def __init__(self, returncode: int = 0):
        self.returncode = returncode
        self.calls = []

    def __call__(self, argv, *args, **kwargs):
        self.calls.append({"argv": list(argv), "args": args, "kwargs": kwargs})
        return types.SimpleNamespace(
            returncode=self.returncode,
            args=argv,
            stdout=b"",
            stderr=b"",
        )


def inject_runner(monkeypatch, returncode: int = 0) -> RunnerDouble:
    """Inject runner double into glyph_isa_v2._RUNNER or subprocess.run."""
    double = RunnerDouble(returncode=returncode)
    monkeypatch.setattr(subprocess, "run", double)
    if hasattr(glyph_isa_v2, "_RUNNER"):
        monkeypatch.setattr(glyph_isa_v2, "_RUNNER", double)
    return double


def execute_syscall_run(path: str) -> Tuple[int, GlyphCPUv2]:
    """Assemble and run a Glyph CPU program that invokes SYSCALL_RUN (0x07)."""
    op_map = OpcodeMapV2()
    assembler = GlyphAssemblerV2(op_map)
    cols = 16
    cpu = GlyphCPUv2(op_map, cols_instrs=cols)
    width = cols * 4  # 64 pixels per row
    path_bytes = str(path).encode("utf-8") + b"\x00"
    path_addr = 64  # row 1, col 0

    needed_rows = (path_addr + len(path_bytes) + width - 1) // width
    total_rows = max(2, needed_rows + 1)

    program = [
        f"LDI r1 {path_addr}",
        "LDI r7 7",
        "SYSCALL r0 7",
        "HALT",
    ]
    while len(program) < cols:
        program.append("HALT")

    image = assembler.assemble(program, width_instrs=cols)
    if image.shape[0] < total_rows:
        pad = np.zeros((total_rows - image.shape[0], width, 3), dtype=np.uint8)
        image = np.vstack([image, pad])

    for i, b in enumerate(path_bytes):
        # PATH is data: seed the RAM view (DEFECT-23-ROOT convention).
        # Image-side seeding relied on _read_path's view-merge, retired
        # 2026-09-22 (claim-queue item 2 step 2).
        cpu.memory[path_addr + i] = b

    cpu.run(image)
    rc = cpu.registers[0]
    op_map.close()
    return rc, cpu


def test_l1_allowed_path_runs(tmp_path, monkeypatch):
    """L1: path is in allowlist -> injected runner called once, returns runner rc."""
    script = tmp_path / "allowed.sh"
    script.write_text("#!/bin/sh\nexit 0")
    os.chmod(script, 0o755)

    resolved_path = str(script.resolve())
    monkeypatch.setenv("GLYPH_RUN_ALLOW", resolved_path)
    double = inject_runner(monkeypatch, returncode=42)

    rc, _ = execute_syscall_run(resolved_path)
    assert rc == 42
    assert len(double.calls) == 1
    assert double.calls[0]["argv"] == [resolved_path]


def test_l2_default_deny(tmp_path, monkeypatch):
    """L2: GLYPH_RUN_ALLOW unset or empty string -> returns -1, runner never called."""
    script = tmp_path / "target.py"
    script.write_text("print('test')")
    os.chmod(script, 0o755)
    resolved_path = str(script.resolve())

    # Subcase A: GLYPH_RUN_ALLOW unset
    monkeypatch.delenv("GLYPH_RUN_ALLOW", raising=False)
    double_a = inject_runner(monkeypatch, returncode=42)
    rc_a, _ = execute_syscall_run(resolved_path)
    assert rc_a == -1
    assert len(double_a.calls) == 0

    # Subcase B: GLYPH_RUN_ALLOW empty string
    monkeypatch.setenv("GLYPH_RUN_ALLOW", "")
    double_b = inject_runner(monkeypatch, returncode=42)
    rc_b, _ = execute_syscall_run(resolved_path)
    assert rc_b == -1
    assert len(double_b.calls) == 0


def test_l3_not_allowlisted(tmp_path, monkeypatch):
    """L3: file exists and executable, not in allowlist -> returns -1, runner never called."""
    script = tmp_path / "not_allowed.sh"
    script.write_text("#!/bin/sh\nexit 0")
    os.chmod(script, 0o755)

    other = tmp_path / "other.sh"
    other.write_text("#!/bin/sh\nexit 0")
    os.chmod(other, 0o755)

    monkeypatch.setenv("GLYPH_RUN_ALLOW", str(other.resolve()))
    double = inject_runner(monkeypatch, returncode=42)

    rc, _ = execute_syscall_run(str(script.resolve()))
    assert rc == -1
    assert len(double.calls) == 0


def test_l4_no_prefix_smuggling(tmp_path, monkeypatch):
    """L4: no path traversal smuggling and no prefix matching."""
    dir_x = tmp_path / "x"
    dir_x.mkdir()
    ok_script = dir_x / "ok.py"
    ok_script.write_text("print('ok')")
    os.chmod(ok_script, 0o755)

    evil_script = tmp_path / "evil.py"
    evil_script.write_text("print('evil')")
    os.chmod(evil_script, 0o755)

    ok2_script = dir_x / "ok2.py"
    ok2_script.write_text("print('ok2')")
    os.chmod(ok2_script, 0o755)

    monkeypatch.setenv("GLYPH_RUN_ALLOW", str(ok_script.resolve()))
    double = inject_runner(monkeypatch, returncode=42)

    # Traversal smuggling attempt: /tmp/x/ok.py/../evil.py
    smuggle_path = str(ok_script.resolve()) + "/../evil.py"
    rc1, _ = execute_syscall_run(smuggle_path)
    assert rc1 == -1
    assert len(double.calls) == 0

    # Prefix match attempt: /tmp/x/ok2.py vs /tmp/x/ok.py
    rc2, _ = execute_syscall_run(str(ok2_script.resolve()))
    assert rc2 == -1
    assert len(double.calls) == 0


def test_l5_no_chmod(tmp_path, monkeypatch):
    """L5: target mode 0o644 stat st_mode is identical before and after call."""
    script = tmp_path / "readonly.py"
    script.write_text("print('test')")
    os.chmod(script, 0o644)
    mode_before = script.stat().st_mode & 0o777
    assert mode_before == 0o644

    monkeypatch.setenv("GLYPH_RUN_ALLOW", str(script.resolve()))
    inject_runner(monkeypatch, returncode=0)

    execute_syscall_run(str(script.resolve()))

    mode_after = script.stat().st_mode & 0o777
    assert mode_after == mode_before


def test_l6_pinned_test_unchanged(tmp_path_factory):
    """L6: tests/test_glyph_run_program.py passes unmodified."""
    t = tmp_path_factory.mktemp("p")
    test_glyph_run_program.test_syscall_run(t)


def test_l7_refusal_is_return(tmp_path, monkeypatch, capsys):
    """L7: denial yields -1, exactly one reason line, and no exception propagates."""
    script = tmp_path / "denied.sh"
    script.write_text("#!/bin/sh\nexit 0")
    os.chmod(script, 0o755)

    monkeypatch.delenv("GLYPH_RUN_ALLOW", raising=False)
    double = inject_runner(monkeypatch, returncode=0)

    capsys.readouterr()  # clear buffer
    rc, _ = execute_syscall_run(str(script.resolve()))
    assert rc == -1
    assert len(double.calls) == 0

    captured = capsys.readouterr()
    lines = [line.strip() for line in captured.out.strip().splitlines() if line.strip()]
    assert len(lines) == 1
    assert "[SYSCALL] RUN" in lines[0]
    assert ("denied" in lines[0].lower() or "not allowed" in lines[0].lower() or "allow" in lines[0].lower())


def test_l8_invariant():
    """L8: handler source contains no shell=True and no os.chmod."""
    src_path = Path(glyph_isa_v2.__file__).resolve()
    content = src_path.read_text(encoding="utf-8")

    marker_start = "elif syscall_num == 0x07:"
    marker_end = "elif syscall_num == 0x08:"
    assert marker_start in content, "Could not find 0x07 syscall handler"
    assert marker_end in content, "Could not find 0x08 syscall handler"

    handler_source = content.split(marker_start)[1].split(marker_end)[0]
    assert "shell=True" not in handler_source, "Found shell=True in 0x07 handler"
    assert "os.chmod" not in handler_source, "Found os.chmod in 0x07 handler"
