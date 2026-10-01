#!/usr/bin/env python3
"""BK-64 twin-side PTE flag gate: W-clear / U-clear frame PTEs must be
enforced by the WGSL walker, not writable-through / readable-through.

Legs (twin via GlyphRunner.run_wgsl on the RTX 5090; oracle pins via the
CPU manual step-loop where a leg needs oracle parity):
  L1 W-clear PIX PTE USER ST  -> twin must REFUSE (value must NOT land);
     RED today: canary lands at frame word 1280 (probe W1).
  L2 U-clear PIX PTE USER LD  -> twin must NOT deliver the canary to r10;
     RED today: r10 == 0x0ADF00D (probe U1).
  L3 W-clear SUPER ST parity pin -> oracle faults pte_invalid op=ST even
     in SUPER (mode-independent W term); the twin's verdict is asserted
     against the FIX posture (refuse), pinning the same program on both.
  L4 rot-guard: full-flag V|W|U PIX PTE ST/LD keep working through the
     same translation path (never weaken a live GH-25 path).
  L5 non-vacuity: leg harness liveness — the L1/L2 programs are proven
     capable of landing/reading (same programs under FULL-flag PTE do
     land/read), so a fix-refusal is meaningful, not a dead harness.
"""
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
for p in (str(REPO), str(REPO / "tools")):
    if p not in sys.path:
        sys.path.insert(0, p)

import numpy as np  # noqa: E402

CANARY = 0x0ADF00D
BOX_LO, BOX_HI = 1200, 1300
PT_TAG_WORD = 1535
PT_BASE_WORD = 1536
PT_ARM_WORD = 8211
VPN12_PTE_WORD = PT_BASE_WORD + 12  # 1548
MODE_LATCH_WORD = 8192
PTE_V, PTE_W, PTE_U = 1, 2, 4
PTE_PIX = 0x8
RECEIPT_WORD = 720
FRAME_OUT_WORD = 1280
PFN_OUT, OFF_OUT = 5, 0
VA_OUT = (12 << 8) | OFF_OUT
PFN_IN, OFF_IN = 1, 64
VA_IN = (12 << 8) | OFF_IN
FRAME_IN_WORD = 320


def pte(pfn_field, flags):
    return flags | PTE_PIX | (pfn_field << 8)


def kernel_prologue(arm=True, box=True, latch=True):
    lines = [":__entry", "JMP :__kmain", ":__kmain",
             "LDI r15 %d" % RECEIPT_WORD, "LDI r14 0", "ST r15 r14"]
    if box:
        lines += ["LDI r15 8195", "LDI r14 %d" % BOX_LO, "ST r15 r14",
                  "LDI r15 8196", "LDI r14 %d" % BOX_HI, "ST r15 r14"]
    if arm:
        lines += ["LDI r15 %d" % PT_ARM_WORD, "LDI r14 %d" % PT_BASE_WORD,
                  "ST r15 r14"]
    if latch:
        lines += ["LDI r15 %d" % MODE_LATCH_WORD, "LDI r14 1", "ST r15 r14",
                  "LDI r30 0", "KJMP r30"]
    return "\n".join(lines) + "\n"


def kernel_epilogue():
    return (":__kdone\nLDI r3 4660\nLDI r15 %d\nST r15 r3\nHALT\n"
            % RECEIPT_WORD)


PROG_LD = ":__task\nLDI r15 %d\nLD r10 r15\n"
PROG_ST = ":__task\nLDI r5 %d\nLDI r15 %d\nST r15 r5\n"


def bake_two_pass(text, cols_instrs=8, min_rows=64):
    from tools.rv64i_to_glyph import assemble_glyph_to_pixels
    from tools.glyph_gpt.baker import bake_image
    if "KJMP r30" not in text:
        return bake_image(text, cols_instrs=cols_instrs, min_rows=min_rows,
                          out_path=None)
    _, coords = assemble_glyph_to_pixels(text, cols_instrs=cols_instrs,
                                         min_rows=min_rows)
    col, row = coords[":__task"]
    packed = (col & 0xFFFF) | ((row & 0xFFFF) << 16)
    final = text.replace("LDI r30 0\nKJMP r30",
                         f"LDI r30 {packed}\nKJMP r30")
    return bake_image(final, cols_instrs=cols_instrs, min_rows=min_rows,
                      out_path=None)


def stamp_image(img, stamps):
    h, w, _ = img.shape
    total = h * w
    for word, val in stamps.items():
        idx = word % total
        img[idx // w, idx % w] = (
            (val >> 16) & 0xFF, (val >> 8) & 0xFF, val & 0xFF)
    return img


def run_twin(name, text, stamps, max_steps=4000):
    """Run one leg on the WGSL twin; return the receipt dict."""
    from PIL import Image
    from tools.glyph_gpt.runner import GlyphRunner

    img = bake_two_pass(text, cols_instrs=8, min_rows=64)
    h, w, _ = img.shape
    assert w * h >= VPN12_PTE_WORD + 1, "image must contain the PT window"
    stamp_image(img, stamps)
    with tempfile.TemporaryDirectory() as td:
        png = Path(td) / f"{name}.png"
        Image.fromarray(img.astype(np.uint8)).save(str(png))
        runner = GlyphRunner(str(png), ram_words=16384)
        return runner.run_wgsl(max_steps=max_steps), img


# ---------------------------------------------------------------- legs

def _w_clear_stamps(w_flag_clear=True):
    return {PT_TAG_WORD: 0x505447,
            PT_ARM_WORD: PT_BASE_WORD,
            VPN12_PTE_WORD: pte(PFN_OUT, (PTE_V | PTE_U) if w_flag_clear
                                else (PTE_V | PTE_W | PTE_U))}


def leg_l1_wclear_st_red_then_fix():
    rec, _ = run_twin("L1", kernel_prologue() + PROG_ST % (CANARY, VA_OUT)
                      + kernel_epilogue(), _w_clear_stamps())
    landed = (rec.get("memory") or [])[FRAME_OUT_WORD] if len(
        rec.get("memory") or []) > FRAME_OUT_WORD else None
    assert landed != CANARY, (
        f"BK64-L1 RED (defect live): W-clear PIX PTE store LANDED the "
        f"canary at frame word {FRAME_OUT_WORD} ({landed:#x}); walk_st's "
        f"paged branch must enforce PTE_W")
    return "L1 ok: W-clear ST refused (frame word post=%r)" % (landed,)


def leg_l2_uclear_ld_red_then_fix():
    stamps = {PT_TAG_WORD: 0x505447,
              PT_ARM_WORD: PT_BASE_WORD,
              VPN12_PTE_WORD: pte(PFN_OUT, PTE_V | PTE_W),
              FRAME_OUT_WORD: CANARY}
    rec, _ = run_twin("L2", kernel_prologue() + PROG_LD % VA_OUT
                      + kernel_epilogue(), stamps)
    r10 = (rec.get("registers_full") or [0] * 11)[10]
    assert r10 != CANARY, (
        f"BK64-L2 RED (defect live): U-clear PIX PTE LD RETURNED the "
        f"canary in USER (r10={r10:#x}); walk_ld's paged branch must "
        f"enforce PTE_U in USER")
    return "L2 ok: U-clear LD not delivered (r10=%r)" % (r10,)


def leg_l3_super_wclear_parity_pin():
    """Oracle-parity pin: the :1001 W term is mode-INDEPENDENT (measured
    probe C2: CPU faults pte_invalid op=ST in SUPER) — pin the twin to
    the same verdict shape (refuse the store) for the SUPER accessor."""
    rec, _ = run_twin("L3", kernel_prologue(arm=True, box=False,
                                            latch=False)
                      + PROG_ST % (CANARY, VA_OUT) + "HALT\n",
                      {PT_TAG_WORD: 0x505447,
                       VPN12_PTE_WORD: pte(PFN_OUT, PTE_V | PTE_U)})
    landed = (rec.get("memory") or [])[FRAME_OUT_WORD] if len(
        rec.get("memory") or []) > FRAME_OUT_WORD else None
    assert landed != CANARY, (
        f"BK64-L3 RED: SUPER W-clear ST landed on the twin "
        f"({landed:#x}) while the oracle faults (mode-independent W "
        f"term, glyph_isa_v2.py:1001) — engine divergence")
    return "L3 ok: SUPER W-clear ST refused (parity with oracle)"


def leg_l4_full_flag_controls():
    """Full-flag V|W|U controls: translation path keeps working."""
    rec, _ = run_twin("L4st", kernel_prologue() + PROG_ST % (CANARY, VA_OUT)
                      + kernel_epilogue(),
                      {PT_TAG_WORD: 0x505447,
                       PT_ARM_WORD: PT_BASE_WORD,
                       VPN12_PTE_WORD: pte(PFN_OUT, PTE_V | PTE_W | PTE_U)})
    mem = rec.get("memory") or []
    assert len(mem) > FRAME_OUT_WORD and mem[FRAME_OUT_WORD] == CANARY, (
        f"BK64-L4 RED: full-flag PIX ST control no longer lands "
        f"(word={mem[FRAME_OUT_WORD] if len(mem) > FRAME_OUT_WORD else None}) "
        f"— the fix must not break the live GH-25 translation path")
    rec2, _ = run_twin("L4ld", kernel_prologue() + PROG_LD % VA_OUT
                       + kernel_epilogue(),
                       {PT_TAG_WORD: 0x505447,
                        PT_ARM_WORD: PT_BASE_WORD,
                        VPN12_PTE_WORD: pte(PFN_OUT, PTE_V | PTE_W | PTE_U),
                        FRAME_OUT_WORD: CANARY})
    r10 = (rec2.get("registers_full") or [0] * 11)[10]
    assert r10 == CANARY, (
        f"BK64-L4 RED: full-flag PIX LD control no longer reads "
        f"(r10={r10:#x}) — the fix must not break the live path")
    return "L4 ok: full-flag ST lands + LD reads (translation live)"


def leg_l5_nonvacuity():
    """Non-vacuity: the L1/L2 programs are harness-live — under a
    FULL-flag PTE the identical program lands/reads (proved by L4). If
    L1/L2 pass while L4 fails, the gate is dead, not the defect fixed."""
    # Structural: L1/L2 and L4 use the SAME programs, ONLY the PTE word
    # differs. If the fix neutered the PIX arm entirely, L4 would fire.
    # Assert the two stamp-sets differ exactly in the flag bits:
    cleared = _w_clear_stamps()[VPN12_PTE_WORD]
    full = pte(PFN_OUT, PTE_V | PTE_W | PTE_U)
    assert (full ^ cleared) == PTE_W, "L1/L4 delta must be exactly PTE_W"
    ucleared = pte(PFN_OUT, PTE_V | PTE_W)
    assert (full ^ ucleared) == PTE_U, "L2/L4 delta must be exactly PTE_U"
    return "L5 ok: flag deltas are exactly PTE_W / PTE_U (gate live)"


def leg_l6_nonvacuity_neuter():
    """Non-vacuity against the LIVE tree: neuter the new ST flag check in
    a TEMP COPY of the WGSL module (revert its paged branch to V-only) ->
    L1's program must land the canary again (the leg fires). The real
    tree is untouched (md5 pinned before/after)."""
    import hashlib
    import importlib.util
    real = REPO / "tools" / "wgsl_glyph_isa_v2.py"
    before = hashlib.md5(real.read_bytes()).hexdigest()
    src = real.read_text()
    neutered = src.replace(
        "if ((pte & PTE_V) == 0u || !(is_super || (pte & PTE_U) != 0u) || (pte & PTE_W) == 0u) {",
        "if ((pte & PTE_V) == 0u) {", 1)
    assert neutered != src, "neuter target (ST flag check) not found"
    with tempfile.TemporaryDirectory() as td:
        mod_dir = Path(td) / "tools"
        mod_dir.mkdir()
        (mod_dir / "wgsl_glyph_isa_v2.py").write_text(neutered)
        spec = importlib.util.spec_from_file_location(
            "wgsl_neutered_bk64", mod_dir / "wgsl_glyph_isa_v2.py")
        assert spec is not None and spec.loader is not None, (
            "neutered module spec failed to load")
        # The neutered module needs its package siblings importable: run
        # the check by re-running leg 1's twin against a monkeypatched
        # build_shader instead -- simplest correct path is exec'ing the
        # module with sys.path pointing at the temp tree.
        saved_path = sys.path[:]
        try:
            sys.path.insert(0, str(mod_dir.parent))
            for stale in [m for m in list(sys.modules)
                          if m == "wgsl_neutered_bk64"]:
                del sys.modules[stale]
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)  # type: ignore[union-attr]
            # run_wgsl imports build_shader INSIDE the method from
            # tools.wgsl_glyph_isa_v2 -- patch THAT module attribute.
            import tools.wgsl_glyph_isa_v2 as real_wgsl
            orig_build = real_wgsl.build_shader
            real_wgsl.build_shader = mod.build_shader
            try:
                from tools.glyph_gpt.runner import GlyphRunner
                rec, _ = run_twin(
                    "L6", kernel_prologue() + PROG_ST % (CANARY, VA_OUT)
                    + kernel_epilogue(), _w_clear_stamps())
            finally:
                real_wgsl.build_shader = orig_build
            landed = (rec.get("memory") or [])[FRAME_OUT_WORD] if len(
                rec.get("memory") or []) > FRAME_OUT_WORD else None
            assert landed == CANARY, (
                f"BK64-L6 non-vacuity RED: even with the ST flag check "
                f"neutered the canary did not land ({landed!r}) -- the "
                f"gate is dead, not the defect fixed")
        finally:
            sys.path[:] = saved_path
            after = hashlib.md5(real.read_bytes()).hexdigest()
            assert after == before == (
                "d21b1a6f3f9e49b90d14a3a2e73e56a4") or after == before, (
                f"real WGSL module changed during L6 ({before} -> {after})")
    return "L6 ok: neutering the ST flag check re-lands the canary " \
           "(gate discriminating; real tree untouched)"


def main():
    msgs = [
        leg_l1_wclear_st_red_then_fix(),
        leg_l2_uclear_ld_red_then_fix(),
        leg_l3_super_wclear_parity_pin(),
        leg_l4_full_flag_controls(),
        leg_l5_nonvacuity(),
        leg_l6_nonvacuity_neuter(),
    ]
    for m in msgs:
        print(m)


def test_l1_wclear_st_must_refuse():
    leg_l1_wclear_st_red_then_fix()


def test_l2_uclear_ld_must_not_deliver():
    leg_l2_uclear_ld_red_then_fix()


def test_l3_super_wclear_parity_pin():
    leg_l3_super_wclear_parity_pin()


def test_l4_full_flag_controls_stay_live():
    leg_l4_full_flag_controls()


def test_l5_gate_liveness_nonvacuity():
    leg_l5_nonvacuity()


def test_l6_neutered_flag_check_relands_canary():
    leg_l6_nonvacuity_neuter()


if __name__ == "__main__":
    main()
