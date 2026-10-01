#!/usr/bin/env python3
"""RED-first evidence for the BK-62/63 twin frame gate (af3e62239ce2):
run L1b's exact program + stamps against a TEMP-COPY module whose
paged_paddr_out_of_tile is neutered (the pre-fix walk shape) — the gate's
refusal assertions must FAIL (canary delivered, no fault). The landed gate
on the real tree passes (L1b GREEN); this probe shows the same assertions
go RED on the pre-fix shape, i.e. they are falsifiable, not vacuous.
Real tree md5-pinned before/after; nothing on disk is modified.
"""
import hashlib
import importlib.util
import sys
import tempfile
from pathlib import Path

REPO = Path("/home/jericho/projects/zion/projects/visual_audio")
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tools"))
sys.path.insert(0, str(REPO / "tests"))

real = REPO / "tools" / "wgsl_glyph_isa_v2.py"
before = hashlib.md5(real.read_bytes()).hexdigest()

import test_bk62_bk63_hilb_pix_frame_fence_twin as g  # noqa: E402

src = real.read_text()
neutered = src.replace(g.NEUTER_SNIPPET,
                       "fn paged_paddr_out_of_tile(paddr_word: u32, "
                       "is_super: bool) -> bool {\n    return false; "
                       "// TEMP-COPY neuter: consult disabled", 1)
assert neutered != src
with tempfile.TemporaryDirectory() as td:
    mod_dir = Path(td) / "tools"
    mod_dir.mkdir()
    (mod_dir / "wgsl_glyph_isa_v2.py").write_text(neutered)
    spec = importlib.util.spec_from_file_location(
        "wgsl_neutered_red62", mod_dir / "wgsl_glyph_isa_v2.py")
    saved = sys.path[:]
    try:
        sys.path.insert(0, str(mod_dir.parent))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        va = 0x300
        rec = g.run_twin_seeded(
            "RED62", g.PROG_LD % va,
            {**g.TILE_MMIO, g.PAGE_TABLE_WORD - g.MMIO_LO: g.PT_BASE},
            ram_seed=g._pt_stamps(3, g._hilb_pte(g.HILB_PFN_D5, g.PTE_V | g.PTE_U)),
            img_seed={1280: g.CANARY}, module_override=mod)
        red_ld = (rec["fault_addr_word"] == 0 and rec["r6"] == g.CANARY
                  and rec["mode_final"] == 1)
        print("RED leg (HILB LD, pre-fix shape): fault=%d r6=%#x mode=%d -> "
              "L1b assertions %s" % (rec["fault_addr_word"], rec["r6"],
                                     rec["mode_final"],
                                     "FAIL (RED confirmed)" if red_ld
                                     else "unexpected shape"))
        rec2 = g.run_twin_seeded(
            "RED62st", g.PROG_ST % (g.CANARY, va),
            {**g.TILE_MMIO, g.PAGE_TABLE_WORD - g.MMIO_LO: g.PT_BASE},
            ram_seed=g._pt_stamps(3, g._hilb_pte(g.HILB_PFN_D5,
                                                 g.PTE_V | g.PTE_W | g.PTE_U)),
            module_override=mod)
        landed = rec2["img_words"][1280 % len(rec2["img_words"])]
        red_st = (rec2["fault_addr_word"] == 0 and landed == g.CANARY
                  and rec2["mode_final"] == 1)
        print("RED leg (HILB ST, pre-fix shape): fault=%d landed=%#x mode=%d "
              "-> L1c assertions %s" % (rec2["fault_addr_word"], landed,
                                        rec2["mode_final"],
                                        "FAIL (RED confirmed)" if red_st
                                        else "unexpected shape"))
        if not (red_ld and red_st):
            sys.exit("RED probe did not reproduce the pre-fix shape — "
                     "investigate before landing")
    finally:
        sys.path[:] = saved
        after = hashlib.md5(real.read_bytes()).hexdigest()
        assert after == before, f"real module mutated ({before} -> {after})"
print("real tree md5 unchanged:", before)
