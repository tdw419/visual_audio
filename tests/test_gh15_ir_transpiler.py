"""tests/test_gh15_ir_transpiler.py — GH-15 gate.

Unified GlyphIR: the RV64I transpiler's lowering must pass through the
GlyphIR static verifier (dual-path) byte-exact vs the legacy path, and
must reject contract violations loudly BEFORE pixel emission.

Dual-path contract:
  - transpile_elf_to_glyph(..., use_ir=False) == use_ir=True text
    (byte-exact) on every differential fixture.
  - A lowering that breaks an IR invariant (scratch pool intersecting
    contract.preserves, callstack_reg in scratch pool, data section in
    a reserved kernel range, code window overflow) raises
    StaticVerificationError at the IR stage — never a silent bad image.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
for _p in (str(_REPO), str(_REPO / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import glyph_ir as gi                                   # noqa: E402
import rv64i_to_glyph as r2g                            # noqa: E402

# Reuse one compiled differential fixture (the arithmetic/shift suite is
# the fastest to build and exercises immediates, branches, calls, shifts).
FIXTURE_C = r"""
int main(void) {
    volatile int a = 0x00FF00F0;
    volatile int b = 12;
    int acc = 0;
    for (int i = 0; i < b; i++) {
        int sh = a >> i;         /* exercises shifts + sign logic */
        if (a & (1 << i)) acc += sh + i;   /* no __mulsi3: rv32i libgcc gap */
        else acc ^= (a << i) | i;
    }
    return acc == 12345;
}
int _start_body(void) { return main(); }
"""


def _build_elf(tmp: Path) -> bytes:
    """Compile the fixture rv32i the way the differential suites do."""
    src = tmp / "g15.c"
    elf = tmp / "g15.elf"
    src.write_text(FIXTURE_C)
    cmd = [
        "riscv64-unknown-elf-gcc", "-march=rv32i", "-mabi=ilp32",
        "-O1", "-nostdlib", "-e", "_start_body",
        "-Wl,-Ttext=0x0", "-Wl,--section-start=.sbss=0x300",
        "-Wl,--section-start=.bss=0x400", "-o", str(elf), str(src),
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=60)
    except (FileNotFoundError, subprocess.CalledProcessError) as e:
        pytest.skip(f"riscv toolchain unavailable: {e}")
    return elf.read_bytes()


def test_gh15_ir_spec_dataclasses():
    """The IR's structural invariants hold on a well-formed module and
    fail loudly on malformed ones."""
    # Address: exactly one of base/flat
    with pytest.raises(gi.StaticVerificationError):
        gi.Address()
    with pytest.raises(gi.StaticVerificationError):
        gi.Address(base_reg="r5", flat_addr=100)
    # Operand: exactly one payload
    with pytest.raises(gi.StaticVerificationError):
        gi.Operand(imm=1, phys_reg="r2")
    # Block label sanity
    with pytest.raises(gi.StaticVerificationError):
        gi.BasicBlock(label="9bad label")
    # Appending after a terminator is a hard error
    b = gi.BasicBlock(label="blk")
    b.terminator = "JMP"
    with pytest.raises(gi.StaticVerificationError):
        b.append(gi.IRInstruction(op="LDI"))


def test_gh15_ir_reloc_resolution():
    """SymbolReloc resolves hi20/lo12/word_addr/abs32 and rejects
    unresolved or unaligned symbols."""
    syms = {"base": 0x12345000, "unaligned": 0x1002}
    assert gi.SymbolReloc("base", gi.RelocType.ABS32).resolve(syms) \
        == 0x12345000
    assert gi.SymbolReloc("base", gi.RelocType.HI20).resolve(syms) \
        == 0x12345
    assert gi.SymbolReloc("base", gi.RelocType.WORD_ADDR).resolve(syms) \
        == 0x48D1400
    with pytest.raises(gi.StaticVerificationError):
        gi.SymbolReloc("missing").resolve(syms)
    with pytest.raises(gi.StaticVerificationError):
        gi.SymbolReloc("unaligned", gi.RelocType.WORD_ADDR).resolve(syms)


def test_gh15_dual_path_byte_exact():
    """use_ir=True must produce byte-identical text to the legacy path
    on a real differential fixture."""
    elf = _build_elf(Path(__file__).parent)
    legacy = r2g.transpile_elf_to_glyph(elf, entry_symbol="_start_body")
    ir_path = r2g.transpile_elf_to_glyph(elf, entry_symbol="_start_body",
                                         use_ir=True)
    assert legacy == ir_path, "IR path must be a pure verification gate"
    assert legacy.strip(), "transpiler emitted nothing"


def test_gh15_scratch_pool_vs_preserves_rejected():
    """scratch_pool ∩ contract.preserves != ∅ is a loud rejection."""
    mod = gi.GlyphIRModule(
        name="bad_scratch",
        blocks=[gi.BasicBlock(label="blk")],
        contract=gi.IRContract(preserves=["r28", "s0"]),
        lowering=gi.LoweringConfig(scratch_pool=["r28", "r29"],
                                   callstack_reg="r31"),
    )
    with pytest.raises(gi.StaticVerificationError, match="preserves"):
        gi.StaticVerifier(mod).verify()


def test_gh15_callstack_in_scratch_rejected():
    """callstack_reg ∈ scratch_pool is a loud rejection."""
    mod = gi.GlyphIRModule(
        name="bad_callstack",
        blocks=[gi.BasicBlock(label="blk")],
        lowering=gi.LoweringConfig(scratch_pool=["r29", "r31"],
                                   callstack_reg="r31"),
    )
    with pytest.raises(gi.StaticVerificationError, match="callstack_reg"):
        gi.StaticVerifier(mod).verify()


def test_gh15_mailbox_collision_rejected():
    """A data section landing in a reserved kernel range — e.g. the
    GH-9 mailbox window at words [800, 896), the exact GH-12-era bug
    class — is rejected at the IR stage, before any pixels exist."""
    mod = gi.GlyphIRModule(
        name="mailbox_collide",
        blocks=[gi.BasicBlock(label="blk")],
        data_sections=[gi.DataSection(symbol="mb", base_word=820,
                                      words=[1, 2, 3])],
    )
    with pytest.raises(gi.StaticVerificationError, match="reserved"):
        gi.StaticVerifier(mod).verify()


def test_gh15_fs_window_collision_rejected():
    """Same class, GH-8b flavor: data in the pixel-FS window
    [1024, 1280) must be rejected."""
    mod = gi.GlyphIRModule(
        name="fs_collide",
        blocks=[gi.BasicBlock(label="blk")],
        data_sections=[gi.DataSection(symbol="fs", base_word=1100,
                                      words=[4, 5])],
    )
    with pytest.raises(gi.StaticVerificationError, match="reserved"):
        gi.StaticVerifier(mod).verify()


def test_gh15_window_overflow_rejected():
    """A module needing more words than its CodeWindow holds is
    rejected before emission."""
    mod = gi.GlyphIRModule(
        name="too_big",
        blocks=[gi.BasicBlock(
            label="blk",
            instructions=[gi.IRInstruction(op="LDI",
                                           dests=(gi.Operand.reg("r2"),),
                                           sources=(gi.Operand.const(1),))
                          for _ in range(5)])],
        code_window=gi.CodeWindow(max_words=4),
    )
    with pytest.raises(gi.StaticVerificationError, match="window holds"):
        gi.StaticVerifier(mod).verify()


def test_gh15_terminator_target_unknown_rejected():
    """A jump to a block label that doesn't exist is rejected."""
    blk = gi.BasicBlock(label="a", terminator="JMP",
                        terminator_target="nowhere")
    mod = gi.GlyphIRModule(name="bad_target", blocks=[blk])
    with pytest.raises(gi.StaticVerificationError, match="nowhere"):
        gi.StaticVerifier(mod).verify()


def test_gh15_zero_dev_imports():
    """glyph_ir.py is toolchain-lane: stdlib only (AST gate)."""
    import ast
    src = (_REPO / "tools" / "glyph_ir.py").read_text()
    tree = ast.parse(src)
    allowed_stdlib = {"__future__", "dataclasses", "enum", "re",
                      "typing"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                assert root in allowed_stdlib, f"glyph_ir imports {root}"
        elif isinstance(node, ast.ImportFrom):
            root = (node.module or "").split(".")[0]
            assert root in allowed_stdlib, f"glyph_ir imports from {root}"
