#!/usr/bin/env python3
"""tests/test_gh15_step3_autoatlas.py — GH-15 Step 3 gate.

AutoAtlas migration: every glyph program the ingest pipeline emits
(drafted tiles AND loader-bound mailbox payloads) must be raised into a
GlyphIRModule and pass the StaticVerifier BEFORE pixel emission, with
byte-exact pixels vs the legacy path.

Legs:
  1. a real, oracle-passing atlas tile verifies through the IR stage
  2. IR-routed pixel payload is byte-exact vs the legacy path
  3. a tile whose data lands in the reserved mailbox window is rejected
     loudly at the IR stage (the exact GH-12-era bug class)
  4. a tile needing more words than the GH-9 patch window is rejected
     at the IR stage, before any pixels exist
  5. a jump to a block label that does not exist is rejected
  6. ingest() end-to-end with the IR gate on: a (monkeypatched) verified
     tile dispatches through the live kernel; result word-exact
  7. ingest() refuses a tile the IR rejects — it never reaches pixels
Deterministic: no live-model dependency (gate 6 monkeypatches the
router's escalate, exactly like the GH-12 negative-control leg).
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
for _p in (str(_REPO), str(_REPO / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import glyph_ir as gi                                   # noqa: E402
from tools.glyph_gpt.atlas import build_default_atlas   # noqa: E402
from tools.glyph_gpt.autoatlas import (                 # noqa: E402
    ingest, _pixel_words, ir_pixel_words,
    raise_tile_text_to_ir,
    GH9_ARGV_WORD, GH9_EXIT_OK, KERNEL_OK,
)
from tools.glyph_gpt.escalate import EscalationResult   # noqa: E402
from tools.glyph_gpt.baker import loader_kernel_image   # noqa: E402
from tools.glyph_gpt.runner import GlyphRunner          # noqa: E402

# The atlas's own worked accumulate tile: exercises a loop, both branch
# forms (JZ + JMP), CALL-free leaf structure — the exact shape a drafted
# kernel tile takes. It is oracle-passing by construction (it ships in
# the default atlas behind a green registration harness).

def _accumulate_tile_text() -> str:
    atlas = build_default_atlas()
    if "accumulate" in atlas.tiles:
        return atlas.tiles["accumulate"]["tile_text"]
    pytest.skip("default atlas has no accumulate tile to test against")


def test_tile_verifies_through_ir_stage():
    """A real atlas tile raises to a GlyphIRModule that passes the
    StaticVerifier — the IR stage is green on everything the pipeline
    already ships."""
    tile = _accumulate_tile_text()
    module = raise_tile_text_to_ir(tile, name="accumulate")
    gi.StaticVerifier(module).verify()      # must not raise
    assert any(b.terminator == "JZ" for b in module.blocks), \
        "the raise must capture the tile's conditional branch"
    assert any(b.terminator == "RET" or b.terminator == "HALT"
               for b in module.blocks), "the raise must capture the exit"


def test_ir_routed_payload_byte_exact_vs_legacy():
    """ir_pixel_words() (raises to IR, verifies, then emits) produces the
    identical jump-relocated mailbox payload as the legacy-only path."""
    tile = _accumulate_tile_text()
    assert ir_pixel_words(tile) == _pixel_words(tile), \
        "IR routing must be a pure gate: same pixels, same relocation"


def test_tile_mailbox_collision_rejected_at_ir_stage():
    """Negative: a mutated tile whose data section lands inside the
    reserved GH-9 mailbox window [800,896) — the exact GH-12-era bug —
    is rejected at the IR stage with zero pixels emitted."""
    tile = _accumulate_tile_text()
    module = raise_tile_text_to_ir(tile, name="collider")
    # simulate the bug: a payload word parked in the mailbox window
    module.data_sections.append(
        gi.DataSection(symbol="payload", base_word=850, words=[1, 2, 3]))
    with pytest.raises(gi.StaticVerificationError, match="reserved"):
        gi.StaticVerifier(module).verify()


def test_tile_window_overflow_rejected_at_ir_stage():
    """Negative: a tile needing more words than the 24-instruction GH-9
    patch window is rejected before pixel emission."""
    lines = [f"LDI r{3 + i % 20} {i}" for i in range(30)]  # 30 straight-line
    lines += ["HALT"]
    tile = ":atlas_too_big\n" + "\n".join(lines) + "\n"
    with pytest.raises(gi.StaticVerificationError, match="window holds"):
        ir_pixel_words(tile)


def test_tile_unknown_jump_target_rejected_at_ir_stage():
    """Negative: a JZ to a label that no longer exists (the classic
    hand-edit dangling branch) is rejected before pixels."""
    tile = _accumulate_tile_text()
    module = raise_tile_text_to_ir(tile, name="dangler")
    for b in module.blocks:
        if b.terminator == "JZ" and b.terminator_target:
            b.terminator_target += "_missing"
            break
    else:
        pytest.fail("fixture tile has no JZ to mutate")
    with pytest.raises(gi.StaticVerificationError):
        gi.StaticVerifier(module).verify()


def _fake_verified_escalate(monkeypatch, tile_text: str, golden: int):
    """Swap the live-model router for a deterministic one that returns a
    pre-verified tile — same EscalationResult shape, zero model calls."""
    from tools.glyph_gpt import autoatlas as aa

    def _fake(task, expect_registers=None, seed_memory=None,
              input_registers=None, max_attempts=6, model="x",
              extra_vectors=None):
        return EscalationResult(
            contract=task, verified=True, attempts=1,
            glyph_text=tile_text,
            oracle=None)        # gate 3 (kernel dispatch) still runs

    monkeypatch.setattr(aa, "escalate", _fake)


# A kernel-ABI popcount tile — exactly the shape escalate() + the ISA
# primer produce for POPCOUNT-style contracts (24 instructions, the full
# GH-9 window budget: load arg0 from mem[750], count bits into r2, store
# to mem[754], write exit word 0xFEED0009 to mem[703], HALT).
KERNEL_ABI_POPCOUNT = (""":atlas_popcount
LDI r15 750
LD r1 r15
LDI r3 1
LDI r4 0
LDI r6 32
LDI r7 1
XOR r2 r2
:__pc_loop
CMP r6 r4
JZ :__pc_done
XOR r5 r5
ADD r5 r1
AND r5 r3
CMP r5 r4
JZ :__pc_skip
ADD r2 r7
:__pc_skip
SHR r1 r3
SUB r6 r7
JMP :__pc_loop
:__pc_done
LDI r15 754
ST r15 r2
LDI r14 4276944905
LDI r15 703
ST r15 r14
HALT
""")


def test_ingest_dispatches_kernel_through_ir_gate(monkeypatch):
    """End-to-end ingest with the IR gate on: a verified tile is
    IR-checked, packed, mailbox-injected, and the kernel re-dispatches it
    word-exactly (deterministic — router monkeypatched)."""
    _fake_verified_escalate(monkeypatch, KERNEL_ABI_POPCOUNT, 16)
    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "gh15step3.glyph.npy"
        loader_kernel_image(build_default_atlas(), out_path=out)
        runner = GlyphRunner(out, ram_words=16384)
        res = ingest(build_default_atlas(), "popcount", "bitops",
                     "popcount(r1) -> r2", {2: 16},
                     input_registers={1: 0xF0F0F0F0},
                     runner=runner, argv={0: 0xF0F0F0F0})
        assert res.code == "OK", f"{res.code}: {res.detail}"
        assert res.kernel_result == 16, hex(res.kernel_result or 0)
        assert res.kernel_exit == GH9_EXIT_OK
        assert res.kernel_status == KERNEL_OK


def test_ingest_refuses_ir_rejected_tile(monkeypatch):
    """A candidate the IR rejects (window overflow) never reaches pixels:
    E_ATLAS_INJECT with the window verdict, atlas untouched."""
    lines = [f"LDI r{3 + i % 20} {i}" for i in range(30)] + ["HALT"]
    too_big = ":atlas_too_big\n" + "\n".join(lines) + "\n"
    _fake_verified_escalate(monkeypatch, too_big, 16)
    with tempfile.TemporaryDirectory() as d:
        atlas = build_default_atlas()
        out = Path(d) / "gh15step3b.glyph.npy"
        loader_kernel_image(build_default_atlas(), out_path=out)
        runner = GlyphRunner(out, ram_words=16384)
        res = ingest(atlas, "too_big", "bitops",
                     "popcount(r1) -> r2", {2: 16},
                     input_registers={1: 0xF0F0F0F0},
                     runner=runner, argv={0: 0xF0F0F0F0})
        assert res.code == "E_ATLAS_INJECT"
        assert "window holds" in res.detail
        assert "too_big" not in atlas.tiles, "atlas must stay untouched"
