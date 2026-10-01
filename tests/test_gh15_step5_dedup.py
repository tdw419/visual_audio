#!/usr/bin/env python3
"""tests/test_gh15_step5_dedup.py — GH-15 Step 5 gate.

Deduplication of the legacy relocation / raising layer: Steps 2-4 each
landed a near-identical glyph-text -> GlyphIRModule raiser
(rv64i_to_glyph._raise_to_ir, autoatlas.raise_tile_text_to_ir,
baker._raise_lines_to_ir) plus three copies of the terminator table and
the lowering config. This gate pins the consolidation: exactly ONE
shared raiser in tools/glyph_ir.py, the three lanes delegate to it, and
every pre-existing behavior (byte-exact emission, loud pre-emission
rejection, lane-specific module shapes) is preserved.

Legs:
  1. the terminator table / lowering config live only in glyph_ir.py
     (structural: the literal op tuple no longer exists in any lane)
  2. no lane constructs IR blocks by hand any more (structural scan)
  3. the transpiler's use_ir=True path goes through the shared verifier
     (spy leg) and stays byte-exact vs use_ir=False on a real ELF
  4. baker.ir_bake_bytes goes through the shared verifier (spy leg) and
     stays byte-exact vs the legacy bake path
  5. autoatlas.raise_tile_text_to_ir keeps its lane shape (name, entry,
     GH9 window budget, r31 preserve) and ir_pixel_words stays
     byte-exact vs _pixel_words
  6. behavior preservation: a known program raises to the exact block
     structure the Step 3/4 raisers produced (labels + terminators)
  7. autoatlas loud-operand rejection survives the dedup
  8. glyph_ir.py is still stdlib-only (AST import scan)
Deterministic: no live-model dependency; the ELF leg uses the local
riscv64 toolchain exactly like tests/test_gh15_ir_transpiler.py.
"""
from __future__ import annotations

import ast
import inspect
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
for _p in (str(_REPO), str(_REPO / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import glyph_ir as gi                                   # noqa: E402
import rv64i_to_glyph as r2g                            # noqa: E402
from tools.glyph_gpt import autoatlas as aa             # noqa: E402
from tools.glyph_gpt import baker as bk                 # noqa: E402
from tools.glyph_gpt.autoatlas import (                 # noqa: E402
    _pixel_words, ir_pixel_words, raise_tile_text_to_ir,
)

_LANE_FILES = (
    _REPO / "tools" / "rv64i_to_glyph.py",
    _REPO / "tools" / "glyph_gpt" / "autoatlas.py",
    _REPO / "tools" / "glyph_gpt" / "baker.py",
)


def _accumulate_tile_text() -> str:
    from tools.glyph_gpt.atlas import build_default_atlas
    atlas = build_default_atlas()
    if "accumulate" in atlas.tiles:
        return atlas.tiles["accumulate"]["tile_text"]
    pytest.skip("default atlas has no accumulate tile to test against")


def _build_elf(tmp: Path) -> bytes:
    """Compile the same arithmetic fixture the Step 2 differential gate
    uses (toolchain availability mirrors that gate's skip logic)."""
    if subprocess.run(["which", "riscv64-unknown-elf-gcc"],
                      capture_output=True).returncode != 0:
        pytest.skip("riscv64-unknown-elf-gcc not available")
    src = tmp / "g15.c"
    src.write_text("""
    int g15_arith(int a, int b) {
        int c = a + b;
        c = c << 1;
        c = c ^ 0x5;
        return c;
    }
    """)
    elf = tmp / "g15.elf"
    subprocess.run(
        ["riscv64-unknown-elf-gcc", "-march=rv32i", "-mabi=ilp32",
         "-nostdlib", "-ffreestanding", "-O1", "-e", "g15_arith",
         "-Wl,--section-start=.text=0x0",
         "-Wl,--section-start=.data=0x200",
         "-Wl,--section-start=.bss=0x400", "-o", str(elf), str(src)],
        check=True, capture_output=True)
    return elf.read_bytes()


# ── structural legs: one table, one raiser ────────────────────────────

def test_terminator_table_and_config_defined_once():
    """The terminator tuple and scratch-pool config exist ONLY in
    glyph_ir.py; the lanes reference the shared names."""
    assert gi.TERMINATOR_OPS == ("JMP", "JZ", "JNZ", "JMPR", "CALL",
                                 "CALLR", "RET", "KJMP", "HALT",
                                 "SYSCALL", "SYSRET")
    assert gi.DEFAULT_SCRATCH_POOL == ["r26", "r27", "r28", "r29", "r30"]
    assert gi.DEFAULT_CALLSTACK_REG == "r31"
    ir_src = (_REPO / "tools" / "glyph_ir.py").read_text()
    for lane in _LANE_FILES:
        src = lane.read_text()
        assert '"KJMP"' not in src, (
            f"{lane.name} still carries its own terminator table — the "
            "Step 5 dedup requires the single glyph_ir definition")
    # the shared table actually backs the lanes' public aliases
    assert aa._GH15_TERMINATORS is gi.TERMINATOR_OPS


def test_no_lane_hand_builds_ir_blocks():
    """Lanes must delegate the raise to glyph_ir.raise_lines_to_ir —
    no hand-rolled BasicBlock/IRInstruction construction left."""
    for lane in _LANE_FILES:
        src = lane.read_text()
        assert not re.search(r"\bBasicBlock\(", src), (
            f"{lane.name} still constructs BasicBlock directly")
        assert not re.search(r"\bIRInstruction\(", src), (
            f"{lane.name} still constructs IRInstruction directly")
        assert "raise_lines_to_ir" in src, (
            f"{lane.name} does not call the shared raiser")


# ── delegation spy legs ───────────────────────────────────────────────

def test_transpiler_ir_path_goes_through_shared_verifier(tmp_path):
    """use_ir=True must run the shared StaticVerifier (spy counts >=1
    call) while the emitted text stays byte-exact vs use_ir=False."""
    elf = _build_elf(tmp_path)
    legacy = r2g.transpile_elf_to_glyph(elf, entry_symbol="g15_arith",
                                        use_ir=False)
    calls = {"n": 0}
    real_verify = gi.StaticVerifier.verify

    def spy(self):
        calls["n"] += 1
        return real_verify(self)

    orig = gi.StaticVerifier.verify
    gi.StaticVerifier.verify = spy
    try:
        ir_text = r2g.transpile_elf_to_glyph(elf, entry_symbol="g15_arith",
                                             use_ir=True)
    finally:
        gi.StaticVerifier.verify = orig
    assert ir_text == legacy, "dual-path byte-exactness broke"
    assert calls["n"] >= 1, "use_ir=True bypassed the shared verifier"


def test_baker_ir_bake_goes_through_shared_verifier(tmp_path):
    """ir_bake_bytes must run the shared StaticVerifier and emit pixels
    byte-exact vs the legacy bake_image path."""
    program = ":prog\nLDI r10 21\nADD r10 r10\nHALT\n"
    legacy_px = bk.bake_image(program, cols_instrs=8)
    calls = {"n": 0}
    real_verify = gi.StaticVerifier.verify

    def spy(self):
        calls["n"] += 1
        return real_verify(self)

    gi.StaticVerifier.verify = spy
    try:
        ir_px = bk.ir_bake_bytes(program, cols_instrs=8)
    finally:
        gi.StaticVerifier.verify = real_verify
    assert (ir_px == legacy_px).all(), "IR-routed bake diverged from legacy"
    assert calls["n"] >= 1, "ir_bake_bytes bypassed the shared verifier"


# ── lane-shape preservation ───────────────────────────────────────────

def test_autoatlas_lane_shape_and_byte_exactness():
    """raise_tile_text_to_ir keeps its Step 3 contract (module name,
    entry label, GH-9 window budget, r31 preserved) and the routed
    payload stays byte-exact vs the legacy packer."""
    tile = _accumulate_tile_text()
    module = raise_tile_text_to_ir(tile, name="accumulate")
    gi.StaticVerifier(module).verify()
    assert module.name == "accumulate"
    assert module.blocks[0].label == "accumulate__entry"
    assert module.code_window.max_words == aa.GH9_N_INSTRS
    assert "r31" in module.contract.preserves
    assert ir_pixel_words(tile) == _pixel_words(tile), (
        "IR routing must stay a pure gate after the dedup")


def test_block_structure_preserved_on_known_program():
    """A known program raises to exactly the block structure the
    Step 3/4 raisers produced: fused-label blocks, terminator targets,
    synthetic continuation blocks."""
    program = (":prog\nLDI r10 3\n"
               ":loop\nADD r10 r10\nLDI r11 1\n"
               "JZ :done\nJMP :loop\n"
               ":done\nHALT\n")
    m = gi.raise_lines_to_ir(program.splitlines(), name="prog")
    labels = [b.label for b in m.blocks]
    terms = [(b.terminator, b.terminator_target) for b in m.blocks]
    assert labels[0] == "prog__entry"
    assert "loop" in labels and "done" in labels
    assert ("JZ", "done") in terms
    assert ("JMP", "loop") in terms
    assert terms[-1][0] == "HALT"
    gi.StaticVerifier(m).verify()


def test_autoatlas_unknown_operand_rejection_survives():
    """The autoatlas lane's loud unparseable-operand rejection is part
    of the Step 3 contract and must survive the dedup."""
    bad = ":atlas_bad\nLDI r10 banana\nHALT\n"
    with pytest.raises(gi.StaticVerificationError, match="unparseable"):
        raise_tile_text_to_ir(bad, name="bad")


def test_glyph_ir_stays_stdlib_only():
    """AST import scan: glyph_ir.py imports nothing outside the stdlib
    (launcher-lane zero-dev-imports convention)."""
    import sys as _sys
    tree = ast.parse((_REPO / "tools" / "glyph_ir.py").read_text())
    std = set(_sys.stdlib_module_names)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                assert a.name.split(".")[0] in std, f"non-stdlib: {a.name}"
        elif isinstance(node, ast.ImportFrom):
            assert (node.module or "").split(".")[0] in std or node.level, (
                f"non-stdlib from-import: {node.module}")
