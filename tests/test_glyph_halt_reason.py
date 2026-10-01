"""Standing gate: GlyphCPUv2.halt_reason names silent halts.

The engine had a "silent halt" class - running=False with no fault, no
error, no output difference from a normal HALT: opcode-None (walked into a
zeroed/never-assembled pixel) and walk-off (PC outside the image bounds).
This exact class cost the SE021 session multi-turn debugging (turn 2 walked
into an opcode-None pixel and silently stopped; nothing distinguished it
from a clean HALT until someone read the engine source). halt_reason names
it, mirroring self.fault_reason's existing shape.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
for _p in (str(REPO), str(REPO / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from tools.glyph_isa_v2 import GlyphAssemblerV2, GlyphCPUv2, OpcodeMapV2  # noqa: E402

W = 8


def test_normal_halt_leaves_reason_none():
    om = OpcodeMapV2()
    asm = GlyphAssemblerV2(om)
    img = asm.assemble(["LDI r5 1", "HALT"], width_instrs=W)
    cpu = GlyphCPUv2(OpcodeMapV2(), cols_instrs=W)
    cpu.run(img, max_instructions=10)
    assert cpu.halt_reason is None
    assert cpu.running is False


def test_opcode_none_pixel_is_named():
    """The exact SE021 failure mode: a program with no HALT walks into a
    zeroed pixel the assembler never wrote an opcode into."""
    om = OpcodeMapV2()
    asm = GlyphAssemblerV2(om)
    img = asm.assemble(["LDI r5 1"], width_instrs=W)  # no HALT
    cpu = GlyphCPUv2(OpcodeMapV2(), cols_instrs=W)
    cpu.run(img, max_instructions=10)
    assert cpu.running is False
    assert cpu.faulted is False  # this class is NOT a fault - that's the point
    assert cpu.halt_reason is not None
    assert "opcode-None" in cpu.halt_reason


def test_walk_off_bounds_is_named():
    """PC advances past the image's actual dimensions."""
    om = OpcodeMapV2()
    asm = GlyphAssemblerV2(om)
    img = asm.assemble(["LDI r5 1"], width_instrs=W)
    cpu = GlyphCPUv2(OpcodeMapV2(), cols_instrs=W)
    cpu.pc = (0, img.shape[0])  # one row past the actual image
    cpu.running = True
    cpu.run(img, max_instructions=1)
    assert cpu.halt_reason is not None
    assert "walk-off" in cpu.halt_reason


def test_non_vacuity_neutered_reason_stays_none():
    """Prove the two assertions above depend on the real fix: exec a
    neutered in-memory copy (the two 'self.halt_reason = ...' lines removed,
    live file untouched) and confirm the SAME opcode-None program now
    reports halt_reason=None - i.e. the real code's non-None result is the
    fix firing, not luck or a default."""
    import types

    src_path = REPO / "tools" / "glyph_isa_v2.py"
    source = src_path.read_text()
    target = (
        '            self.halt_reason = f"opcode-None pixel at ({x},{y}): '
        'rgb={opcode_px} is not a known opcode color"\n'
    )
    assert target in source, "non-vacuity probe's anchor text is stale - re-sync with the real fix"
    neutered_source = source.replace(target, "")
    assert neutered_source != source

    mod = types.ModuleType("glyph_isa_v2_halt_reason_probe")
    mod.__file__ = str(src_path)
    exec(compile(neutered_source, str(src_path), "exec"), mod.__dict__)

    img = mod.GlyphAssemblerV2(mod.OpcodeMapV2()).assemble(["LDI r5 1"], width_instrs=W)
    cpu = mod.GlyphCPUv2(mod.OpcodeMapV2(), cols_instrs=W)
    cpu.run(img, max_instructions=10)
    assert cpu.halt_reason is None, "neutered code should have lost the naming, proving it was real"

    assert src_path.read_text() == source  # live file untouched
