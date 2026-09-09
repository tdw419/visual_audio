#!/usr/bin/env python3
"""
ROADMAP item 3b oracle: the Route B shader routes the glyph dispatch MMIO
trigger to a host servicing turn instead of a silent RAM write.

The Route B core loads tools/SPATIAL_RV64I.wgsl (see qemu_gpu_offload.py:155).
Its `mmio_write(addr, val) -> bool` returns true for recognised device
addresses; on false the store falls through to a plain RAM write. The glyph
dispatch trigger (request_struct.MMIO_DISPATCH_TRIGGER) sits *inside* the
nominal RAM span, so without an explicit branch a guest write there is lost to
RAM and the host never gets a turn.

Checks:
  1. naga validates the shader (skipped, not failed, if naga is absent).
  2. `mmio_write` has a branch for the trigger address that sets
     `state.halted = 2u` (the same host-offload yield code VirtIO QueueNotify
     uses) and the `return false` fall-through is still intact.
  3. the trigger address really does fall inside [ram_base, ram_base+256MB),
     i.e. the hazard the branch guards against is real.

FAILS LOUDLY: AssertionError -> non-zero exit. Fails check 2 until the shader
is patched (oracles-first).
"""

import re
import shutil
import subprocess
import sys
from pathlib import Path

_GD_ROOT = Path(__file__).resolve().parents[1]
_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_GD_ROOT))

from src.dispatch.request_struct import MMIO_DISPATCH_TRIGGER

SHADER = _REPO_ROOT / "tools" / "SPATIAL_RV64I.wgsl"
RAM_BASE = 0x80000000
RAM_SIZE = 256 * 1024 * 1024


def _naga_bin():
    return shutil.which("naga") or (
        str(Path.home() / ".cargo" / "bin" / "naga")
        if (Path.home() / ".cargo" / "bin" / "naga").exists() else None)


def _mmio_write_body(text: str) -> str:
    start = text.index("fn mmio_write(")
    depth = 0
    i = text.index("{", start)
    for j in range(i, len(text)):
        if text[j] == "{":
            depth += 1
        elif text[j] == "}":
            depth -= 1
            if depth == 0:
                return text[i:j + 1]
    raise AssertionError("mmio_write body not found / unbalanced braces")


def test_naga_validates():
    naga = _naga_bin()
    if not naga:
        print("  naga not installed -> SKIP shader validation")
        return
    p = subprocess.run([naga, str(SHADER)], capture_output=True, text=True)
    assert p.returncode == 0, f"naga rejected {SHADER.name}:\n{p.stdout}\n{p.stderr}"
    print(f"  naga: {SHADER.name} validates")


def test_glyph_trigger_routes_to_host():
    assert SHADER.exists(), f"shader not found: {SHADER}"
    body = _mmio_write_body(SHADER.read_text())

    trig = f"0x{MMIO_DISPATCH_TRIGGER:08x}u"
    trig_alt = f"0x{MMIO_DISPATCH_TRIGGER >> 16:04x}_{MMIO_DISPATCH_TRIGGER & 0xFFFF:04x}u"
    refs = [m.start() for m in re.finditer(
        re.escape(trig) + "|" + re.escape(trig_alt) + r"|GLYPH_DISPATCH_TRIGGER", body)]
    assert refs, (
        f"mmio_write has no branch for the glyph trigger ({trig}); a guest write "
        f"there currently falls through to a silent RAM write")

    near = body[refs[0]: refs[0] + 400]
    assert re.search(r"state\.halted\s*=\s*2u", near), (
        "glyph trigger branch does not set state.halted = 2u (host offload yield)")
    assert "return false;" in body, "mmio_write lost its device fall-through"
    print(f"  mmio_write: {trig} -> state.halted = 2u  (host servicing turn)")


def test_trigger_is_inside_ram_span():
    assert RAM_BASE <= MMIO_DISPATCH_TRIGGER < RAM_BASE + RAM_SIZE, (
        f"trigger 0x{MMIO_DISPATCH_TRIGGER:x} outside [{RAM_BASE:#x}, "
        f"{RAM_BASE + RAM_SIZE:#x}); the explicit mmio_write branch would be "
        f"unnecessary")
    print(f"  trigger 0x{MMIO_DISPATCH_TRIGGER:08x} is inside RAM span "
          f"-> explicit decode required")


def main():
    print("=" * 70)
    print("ITEM 3b - Route B shader MMIO decode for the glyph trigger")
    print("=" * 70)
    test_naga_validates()
    test_glyph_trigger_routes_to_host()
    test_trigger_is_inside_ram_span()
    print("-" * 70)
    print("ITEM 3b: ALL CHECKS PASSED")


if __name__ == "__main__":
    try:
        main()
    except AssertionError as e:
        print(f"\nITEM 3b FAILED: {e}")
        sys.exit(1)
    sys.exit(0)
