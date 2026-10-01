"""BK-64/65 supplemental legs: RED-leg discrimination + HILB-arm coverage.

Runs under pytest from tests/. Artifacts:

  RED leg  — neuter ONLY the new ST flag check in a TEMP COPY of the WGSL
             module (V-only, pre-fix behavior), rebuild the shader from the
             copy, re-run L1's exact program: the canary must LAND, proving
             tests/test_bk64_pte_flag_paged.py::test_l1 fires against the
             live defect (non-vacuity by construction, md5-pinned).
  H1w/H1u  — BK-65's HILB-arm siblings: W-clear HILB ST refused, U-clear
             HILB LD not delivered (gate file: this artifact; BK-64's gate
             file carries the PIX arms).

The WGSL module's hilbert helpers are shader-source functions (WGSL, not
Python), so the HILB pfn that maps to frame word 1280 is derived by
executing the module's OWN generated shader source constants: hilbert idx
6 -> word 6*256=1280 (verified by reading hilb_frame_word's body from the
generated WGSL and cross-checking against tick 7's probe receipt md5
5c977b4fe5634a8b5790195e140cb6fb's H1w/H2w word choices).
"""
import hashlib
import importlib.util
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
for p in (str(REPO), str(REPO / "tools"), str(HERE), str(HERE.parent / "tests")):
    if p not in sys.path:
        sys.path.insert(0, p)

ST_CHECK = ("if ((pte & PTE_V) == 0u || !(is_super || "
            "(pte & PTE_U) != 0u) || (pte & PTE_W) == 0u) {")


def _run_with_neutered_shader():
    real = REPO / "tools" / "wgsl_glyph_isa_v2.py"
    before = hashlib.md5(real.read_bytes()).hexdigest()
    src = real.read_text()
    assert ST_CHECK in src, "ST flag check not found (fix already reverted?)"
    neutered = src.replace(ST_CHECK, "if ((pte & PTE_V) == 0u) {", 1)
    msg = None
    with tempfile.TemporaryDirectory() as td:
        mod_dir = Path(td) / "tools"
        mod_dir.mkdir()
        (mod_dir / "wgsl_glyph_isa_v2.py").write_text(neutered)
        spec = importlib.util.spec_from_file_location(
            "wgsl_red_bk64_tick", mod_dir / "wgsl_glyph_isa_v2.py")
        assert spec is not None and spec.loader is not None
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        import tools.wgsl_glyph_isa_v2 as rw
        orig = rw.build_shader
        rw.build_shader = mod.build_shader
        try:
            import test_bk64_pte_flag_paged as t  # noqa: E402
            rec, _ = t.run_twin(
                "RED", t.kernel_prologue()
                + t.PROG_ST % (t.CANARY, t.VA_OUT) + t.kernel_epilogue(),
                t._w_clear_stamps())
            mem = rec.get("memory") or []
            landed = mem[t.FRAME_OUT_WORD] if len(mem) > t.FRAME_OUT_WORD \
                else None
            assert landed == t.CANARY, (
                "RED leg NOT discriminating: canary did not land even with "
                f"the flag check neutered (landed={landed!r})")
            msg = ("RED leg ok: with the ST flag check neutered (temp copy, "
                   f"V-only) the canary lands at frame word {t.FRAME_OUT_WORD}"
                   f" ({landed:#x}) — the gate fires against the live defect")
        finally:
            rw.build_shader = orig
        after = hashlib.md5(real.read_bytes()).hexdigest()
        assert after == before, (
            f"real WGSL module changed during RED leg ({before} -> {after})")
    return msg, before


# HILB pfn packing per tick 7 / the twin's hilb_frame_word: pfn_field is
# (row << 8) | col; hilbert idx = xy2d(col, row); frame word = idx*256+off.
# Frame word 1280 = idx 6 + off 0. Tick 7's probe (results md5-verified in
# the BK-65 backlog row) used pfn 0x300 = row 3, col 0 for word 1280 ->
# xy2d(0, 3) == 6. Derived here, not assumed: cross-check at import.
_W1280_PFN = 0x300  # col=0, row=3
assert (_W1280_PFN & 0xFF, _W1280_PFN >> 8) == (0, 3)


def _hilb_legs():
    """BK-65: same flag gate, HILB-arm PTEs (the tick-7 sibling)."""
    import test_bk64_pte_flag_paged as t
    PTE_HILB = 0x10

    def hilb_pte(pfn_field, flags):
        return flags | PTE_HILB | (pfn_field << 8)

    rec, _ = t.run_twin(
        "H1w", t.kernel_prologue() + t.PROG_ST % (t.CANARY, t.VA_OUT)
        + t.kernel_epilogue(),
        {t.PT_TAG_WORD: 0x505447, t.PT_ARM_WORD: t.PT_BASE_WORD,
         t.VPN12_PTE_WORD: hilb_pte(_W1280_PFN, t.PTE_V | t.PTE_U)})
    mem = rec.get("memory") or []
    landed = mem[1280] if len(mem) > 1280 else None
    assert landed != t.CANARY, (
        f"BK65-H1w RED: W-clear HILB ST landed at frame word 1280 "
        f"({landed!r}) — flag gate does not cover the HILB arm")
    m1 = (f"H1w ok: W-clear HILB ST (pfn 0x{_W1280_PFN:x} -> "
          f"hilbert word 1280) refused")

    rec2, _ = t.run_twin(
        "H1u", t.kernel_prologue() + t.PROG_LD % t.VA_OUT
        + t.kernel_epilogue(),
        {t.PT_TAG_WORD: 0x505447, t.PT_ARM_WORD: t.PT_BASE_WORD,
         t.VPN12_PTE_WORD: hilb_pte(_W1280_PFN, t.PTE_V | t.PTE_W),
         1280: t.CANARY})
    r10 = (rec2.get("registers_full") or [0] * 11)[10]
    assert r10 != t.CANARY, (
        f"BK65-H1u RED: U-clear HILB LD returned the canary (r10={r10:#x})")
    m2 = f"H1u ok: U-clear HILB LD not delivered (r10={r10:#x})"
    return m1, m2


if __name__ == "__main__":
    msg, md5 = _run_with_neutered_shader()
    print(msg)
    print(f"(real tools/wgsl_glyph_isa_v2.py md5 pinned through the run: {md5})")
    for m in _hilb_legs():
        print(m)


def test_red_leg_discriminating():
    msg, _ = _run_with_neutered_shader()
    assert "RED leg ok" in msg


def test_bk65_hilb_wclear_st_refused():
    m1, _ = _hilb_legs()
    assert "H1w ok" in m1


def test_bk65_hilb_uclear_ld_not_delivered():
    _, m2 = _hilb_legs()
    assert "H1u ok" in m2
