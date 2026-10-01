"""WGSL fleet functional probe — does the SHADER (the actual GPU-native
machine, not the CPU oracle) run the R1.2 fleet image?

R1.4 (2026-09-21): the twin converged (tools/wgsl_glyph_isa_v2.py --
RAM-first LD/ST, E-K1, GH-16 ticks). This probe is now the rung GATE:
exit 0 = MATCH (fleet receipt + done bits host-verified), exit 1 =
DIVERGENT/no-RAM. Task parity with R1.3: 4 tenants, seeds 2/3/4/5,
y=x*(x+1) via RES_FLEET_EXPECT on the same baked fleet image.
"""
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tools"))

from tools.glyph_gpt.atlas import build_default_atlas          # noqa: E402
from tools.glyph_gpt.runner import GlyphRunner                 # noqa: E402
from tools.glyph_gpt.agent_resident import (                   # noqa: E402
    resident_image, RES_FLEET_RCPT, RES_DONE_WORD, RES_FLEET_DONE,
    RES_FLEET_EXPECT, RES_FAULT_WORD,
)

with tempfile.TemporaryDirectory() as d:
    img = Path(d) / "fleet.npy"
    resident_image(build_default_atlas(), mode="fleet", timer_quantum=6,
                   out_path=img)
    r = GlyphRunner(img, ram_words=16384)
    rec = r.run_wgsl(max_steps=5000)
    ram = rec.get("ram") or []
    print(f"halted={rec.get('halted')} steps={rec.get('steps')} "
          f"err={rec.get('error')}")
    if ram:
        print(f"ram[765]=0x{ram[RES_FLEET_RCPT]:08x} "
              f"(expect 0x{RES_FLEET_DONE:08x}) "
              f"ram[717]=0b{ram[RES_DONE_WORD]:b} "
              f"ram[731]=0x{ram[RES_FAULT_WORD]:x}")
        print("results:", {w: ram[w] for w in RES_FLEET_EXPECT})
        ok = (ram[RES_FLEET_RCPT] == RES_FLEET_DONE
              and ram[RES_DONE_WORD] == 0b1011
              and {w: ram[w] for w in RES_FLEET_EXPECT} == RES_FLEET_EXPECT)
        print("WGSL FLEET:", "MATCH" if ok else "DIVERGENT")
        sys.exit(0 if ok else 1)
    else:
        print("no ram in receipt")
        sys.exit(1)
