"""Oracle-twin controls for the BK-51 WGSL tile-fence probe: the SAME
programs (tile (5,0,2,4) armed at RAM words 8280..8283, arm_tile
semantics) on GlyphCPUv2.step. The oracle's _addr_in_box DOES contain
the 2D tile predicate (glyph_isa_v2.py:734-747), so: out-of-tile ST to
word 164 fires E-K1 at the store step (byte 656 outside tile and boxes),
while in-tile ST to word 160 LANDS clean (lawful store, mode stays USER,
no fault). Both controls run with KFAULT_PC == 0, so the out-of-tile leg
also exhibits the BK-50-disclosed continuation quirk: after the trap
the task keeps stepping in SUPER and re-executes the same ST, which then
lands (word164 nonzero at readback). The fence EVIDENCE is the fault
record (faulted=True, fault_addr=656, mode drop) at the store step, not
the post-replay memory image."""
import sys
import tempfile
from pathlib import Path

REPO = Path("/home/jericho/projects/zion/projects/visual_audio")
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tools"))

import numpy as np  # noqa: E402

from tools.glyph_isa_v2 import (  # noqa: E402
    TILE_COL_ADDR,
    TILE_H_ADDR,
    TILE_ROW_ADDR,
    TILE_W_ADDR,
    GlyphCPUv2,
    OpcodeMapV2,
)
from tools.glyph_gpt.baker import bake_image  # noqa: E402


def run_case(label, target_word, value=11399181):
    prog = f"""
:__entry
LDI r5 {value}
LDI r6 {target_word}
ST r6 r5
HALT
"""
    img = bake_image(prog, cols_instrs=8)
    cpu = GlyphCPUv2(OpcodeMapV2(), cols_instrs=8)
    cpu.memory = np.zeros(16384, dtype=np.uint64).tolist()
    # arm_tile semantics (glyph_containment.py:91-96): tile words + USER.
    cpu.memory[TILE_ROW_ADDR >> 2] = 5
    cpu.memory[TILE_COL_ADDR >> 2] = 0
    cpu.memory[TILE_H_ADDR >> 2] = 2
    cpu.memory[TILE_W_ADDR >> 2] = 4
    cpu.mode = 1  # MODE_USER
    cpu.run(img, max_instructions=40)
    print(label, "->", "faulted:", cpu.faulted,
          "fault_addr:", cpu.fault_addr,
          "mode_final:", cpu.mode,
          f"word{target_word}:", cpu.memory[target_word])


# OUT-of-tile (word 164, byte 656): E-K1 must fire at the store step.
run_case("oracle_st_out_of_tile_164", 164)
# IN-tile control (word 160, byte 640): must land clean, mode stays USER.
run_case("oracle_st_in_tile_160_control", 160, 4660)
