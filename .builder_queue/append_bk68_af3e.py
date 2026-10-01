#!/usr/bin/env python3
"""Append the BK-68 candidate row (tick 10, af3e) to systems/GLYPH_BACKLOG.md,
directly after the BK-67 table row (line 492)."""
from pathlib import Path

p = Path("systems/GLYPH_BACKLOG.md")
lines = p.read_text().splitlines(keepends=True)

row = (
    "| BK-68 | **WGSL twin PC/fetch confinement: the shader's fetch and jump arms have NO "
    "consult — the twin REPRODUCES BK-67's verdict ON-DEVICE (RTX 5090): a seeded-USER task "
    "executes pre-baked out-of-box code pixels clean, and BK-49's fence-blind image-plane PUSH "
    "composes with JMPR into arbitrary code injection + execution in USER, no fault channel "
    "(measured engine parity for the execute-side gap)** — MEASURED at HEAD 89f0444a (probe "
    "`.builder_queue/probe_wgsl_fetch_confinement_af3e.py`; harness = the proven BK-49/50/51/55 "
    "device buffers + `build_shader(OpcodeMapV2())`, probe-only seeded `cpu.mode=1`, box "
    "[1200,1300) BYTES armed via mmio[3]/mmio[4]; bake cols_instrs=8 min_rows=64 — 32 px/row "
    "scanline units, same discipline as the oracle probe; canary 0x0ADF00D, injected opcode "
    "color resolved at runtime from OpcodeMapV2 (15487056 = 0xEC5050 = the real LDI color), "
    "never hand-encoded; verdicts from image/mmio READBACK BYTES, never stdout; 3 pinned runs "
    "byte-identical, stdout md5 b9ab21c8775cb170486595e3d0d346d1, results md5 "
    "4940f4344fa679a1a70e8f244b30f4c0): (1) S1 source — fetch block "
    "(wgsl_glyph_isa_v2.py:506-509) contains ZERO addr_in_box refs; JMPR :605 / JMP :686 / "
    "CALL / RET / CALLR each set next_pc with 0 refs; PUSH :636-638 is mem_write unguarded; "
    "(2) D1 — seeded-USER `LDI r15 (40<<16); JMPR r15` with the 4 canary-LDI pixels PRE-PAINTED "
    "at image row 40 (OUT of box): clean exit, 4 steps, r10=0x0ADF00D, mode USER, "
    "fault_addr_word=0, injected opcode pixel readback = the real LDI color — the GPU executes "
    "out-of-box code pixels from USER; (3) D2 — full injection composition: PUSH writes the 4 "
    "pixels to row 50 (r31=base+1..base+4 pre-decrement) then JMPR — clean exit, 16 steps, "
    "r10=0x0ADF00D, mode USER end-to-end, fault_addr_word=0, injected pixel = real LDI color: "
    "arbitrary code injection + execution on the GPU, no fence violation needed to trigger "
    "(r31 end 1603 = the PUSH footprint, disclosed); (4) C1 E-K1 control — plain seeded-USER ST "
    "to out-of-box RAM word 100 traps fault_addr_word=400 (RAW byte address, the BK-49-D4 "
    "shape), mode→SUPER, 3 steps: the box arming is LIVE in the exact harness where D1/D2 "
    "execute out-of-box — probe discriminating; (5) C2 in-box ST control clean. Probe defect "
    "disclosed: C1 v1's fired-predicate expected a box-relative fault (negative) — caught by "
    "run-1 showing fired:false alongside fault 400 + mode SUPER, fixed BEFORE the pinned runs. "
    "Consequence: the code plane has NO fence on EITHER engine — BK-67's tile-is-DATA-plane "
    "verdict extends to the twin at the box boundary (the twin has no tile predicate at all, "
    "BK-51); the BK-38..57 sequenced fence commit cannot be Python-only OR ST-only — fetch + "
    "jump arms are the last unconsulted execute-side surface on BOTH engines "
    "| `tests/test_bk67_fetch_confinement.py` — BK-67's gate grows TWIN legs (same file, no new "
    "gate): T-L1 seeded-USER twin JMPR to out-of-box pre-baked code pixels → refused/faulted "
    "(RED today: D1's clean r10); T-L2 PUSH-written pixels + JMPR → injected code must NOT "
    "execute (RED today: D2's canary); T-L3 C1 ST rot-guard green (never weaken the live data "
    "fence); the ORACLE legs L1-L6 of BK-67 are unchanged and this row takes BK-67's flagged "
    "posture decision (execute-confine PC vs code-plane box vs spawn-pinned executable rows) "
    "MECHANICALLY once decided for both engines in the same round — no new design judgment "
    "| BK-67 (same execute-side surface family, same sequenced fence commit; lands with BK-51's "
    "twin tile term so a tile-scoped twin leg becomes expressible); interacts with BK-52/53 "
    "(trap vectors) and BK-49 (the PUSH primitive D2 composes) "
    "| `.builder_queue/RESEARCH_wgsl_fetch_confinement_af3e.md` (2026-09-28 ~05:1x CDT, builder "
    "af3e62239ce2) |\n"
)

# insert after line 492 (1-indexed)
idx = 492
assert lines[idx - 1].startswith("| BK-67 |"), lines[idx - 1][:40]
lines.insert(idx, row)
p.write_text("".join(lines))
print("inserted BK-68 after line", idx)
