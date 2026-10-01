#!/usr/bin/env python3
"""Append the BK-50 twin RESOLUTION tail to GLYPH_BACKLOG.md row BK-50 (line 79)."""
from pathlib import Path

p = Path("systems/GLYPH_BACKLOG.md")
src = p.read_text()

TAIL = (
    " **RESOLUTION (2026-10-01, builder af3e62239ce2): the WGSL walk_st MMIO-door lock "
    "LANDED (twin parity for BK-41's config block; the last open fence-family row) — "
    "`BK50_LOCKED_WORDS` (11 words: 8193, 8194, 8195-8198, 8202-8203, 8207-8209; MODE_LATCH "
    "8192 + TILE 8280..8283 EXCLUDED per BK-41's measured scope amendment) + "
    "`bk50_config_write_refused()` consulted additively at the ST dispatch arm after the "
    "landed BK-76-twin vector-word clause; refusal = the Option A shape (store dropped, "
    "FAULT_ADDR=word<<2, FAULT_PC packed, mode->SUPER, stop, NO vector). Scope term set = "
    "bk76_ever_user latch + TILE_H!=0 + 160-word MMIO window + locked set; NO mode term — "
    "the measured door is a USER-mode store through walk_st's mode-blind MMIO branch "
    "(:604-605), and the oracle locks BOTH post-USER arms (USER :1041, SUPER :968). "
    "GATE-DRAFT DEFECT caught by the gate's own L1: the in-flight first draft (found "
    "uncommitted in the mainline tree, completed per the finish-in-flight rule) gated on "
    "cpu.mode==0u/SUPER and stayed RED with the clause present (canary landed at BOX0_HI, "
    "mmio[4]=11399181) — polarity flipped to mode-agnostic, scope lives in the function. "
    "Gate tests/test_bk50_wgsl_config_door.py 6/6 GREEN x2 pinned runs, every leg on the "
    "real WGSL device (BK-48/49/50/51/76 harness). RED-first at landing (fix stashed, "
    "engine md5 c96ac0149289828574281ef78d20409a): L1 FAILED (USER canary 0xadf00d LANDED "
    "at BOX0_HI), L2 FAILED (self-grant BOX0_HI=65536 landed), L5 errored on the absent "
    "clause marker; fix -> 6/6. LIVE-GUARD INTERACTION receipted: BK-76-twin TW-L5 went RED "
    "post-landing because the additive clause also refuses KSYS_PC (8194 is in both sets — "
    "that overlap IS the BK-50 thesis); TW-L5 amended to neuter BOTH refusal sites (never "
    "weakened; BK-76 clause semantics for the trio byte-identical, still first). Family on "
    "this tree: BK-50 6/6 x2; twin+oracle fence anchors 50 passed one run; sequenced fence "
    "family BK-39..45 + BK-50 = 53 passed; xv6-nano 18p/2s. Triple-synced md5 "
    "1aa4d0407600131ce53c2c8ff5b23458 x3. Numbers structural, rule-1 floors do not attach. "
    "NOT proved / still open: walk_ld's symmetric MMIO READ branch (:361-363) stays "
    "unmode-gated (config-read channel, source-read disclosed — candidate research item, "
    "no measured defect); no live-kernel twin workload (xv6-nano is oracle-side; L3's "
    "lawful TILE_H re-arm leg is the over-confinement guard); paged-path MMIO composition "
    "not re-probed (BK-66 owns the paged consult, green).** |"
)

lines = src.split("\n")
idx = 79 - 1  # 0-based index of the BK-50 row (line 79)
assert lines[idx].startswith("| BK-50 |"), lines[idx][:40]
assert lines[idx].rstrip().endswith("|"), lines[idx][-40:]
lines[idx] = lines[idx].rstrip() + TAIL + "\n"
p.write_text("\n".join(lines))
print("BK-50 row tail appended; row line length:", len(lines[idx]))
