#!/usr/bin/env python3
"""DEFECT-23-ROOT step 1: instrument the low-byte PTE acceptance misread at the paged walk.

Direct-engine probe (no pytest).
See .builder_queue/brief_defect23root_pte_acceptance.md and
systems/GLYPH_SELF_HOSTING_ROADMAP.md:360.

Pins the exact decode defect:
- Acceptance depends on the low byte (PTE_V, PTE_W, PTE_U) alone; nothing about the word's
  provenance is examined.
- High bits (pfn = pte >> 8) are accepted unconditionally.
- ST ceiling containment (pfn > 65536) catches pfn 67593 (G1), but small-pfn garbage
  like pfn 9 (G2) causes silent misdirection: store lands at bogus frame 2394 with no
  fault and no growth, leaving legit word 1370 untouched.
- LD has no ceiling guard: G3 silently reads bogus frame, G4 silently returns 0.

Writes output/defect23_pte_acceptance_probe.json.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
for _p in (str(REPO), str(REPO / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

try:
    from tools.glyph_isa_v2 import PAGE_TABLE_TAG
except ImportError:
    PAGE_TABLE_TAG = 0x505447

from tools.glyph_isa_v2 import (  # noqa: E402
    FAULT_ADDR_ADDR,
    GlyphAssemblerV2,
    GlyphCPUv2,
    MODE_SUPER,
    MODE_USER,
    PAGE_TABLE_ADDR,
    OpcodeMapV2,
)

RAM_WORDS = 16384
PT_BASE = 120
VPN = 5
OFFSET = 0x5A
VADDR = (VPN << 8) | OFFSET  # 1370
VAL = 0xDEADBEEF
COLS = 16
LEGIT_FRAME_WORD = 5 * 256 + OFFSET  # 1370
BOGUS_FRAME_WORD = 9 * 256 + OFFSET  # 2394


def _drive(
    op: str,
    pte: int,
    val: int = VAL,
    mode: int = MODE_SUPER,
    pre_seed: dict[int, int] | None = None,
) -> GlyphCPUv2:
    """Execute one paged LD or ST instruction using the public cpu.run()."""
    assembler = GlyphAssemblerV2(OpcodeMapV2())
    lines = [f"{op} r10 r11"] + ["HALT"] * (COLS - 1)
    image = assembler.assemble(lines, width_instrs=COLS)

    cpu = GlyphCPUv2(OpcodeMapV2(), cols_instrs=COLS)
    cpu.memory = [0] * RAM_WORDS
    cpu.memory[PAGE_TABLE_ADDR >> 2] = PT_BASE
    cpu.memory[PT_BASE - 1] = PAGE_TABLE_TAG
    cpu.memory[PT_BASE + VPN] = pte
    if pre_seed:
        for k, v in pre_seed.items():
            cpu.memory[k] = v
    cpu.mode = mode
    cpu.pc = (0, 0)
    if op == "ST":
        cpu.registers[10] = VADDR  # address in rs1
        cpu.registers[11] = val    # value in rs2
    elif op == "LD":
        cpu.registers[10] = 0      # rd
        cpu.registers[11] = VADDR  # address in rs2
    cpu.run(image, max_instructions=1)
    return cpu


def run_probe() -> dict:
    cases = {}

    # N1: legit identity PTE (5<<8)|0x7 = 0x507 — ST: expect word 1370 == VAL, no fault, memory stays 16384 words
    cpu_n1 = _drive("ST", (VPN << 8) | 0x7, val=VAL, mode=MODE_SUPER)
    cases["N1"] = {
        "case": "N1",
        "op": "ST",
        "pte": (VPN << 8) | 0x7,
        "pte_hex": f"0x{((VPN << 8) | 0x7):08x}",
        "mode": "SUPER",
        "faulted": cpu_n1.faulted,
        "len_memory": len(cpu_n1.memory),
        "growth": len(cpu_n1.memory) - RAM_WORDS,
        "fault_reason": getattr(cpu_n1, "fault_reason", None),
        "word_1370": cpu_n1.memory[LEGIT_FRAME_WORD] if len(cpu_n1.memory) > LEGIT_FRAME_WORD else None,
        "word_2394": cpu_n1.memory[BOGUS_FRAME_WORD] if len(cpu_n1.memory) > BOGUS_FRAME_WORD else None,
    }

    # G1: measured garbage 0x01080907 (pfn 67593) — ST: record faulted, growth, fault_reason
    cpu_g1 = _drive("ST", 0x01080907, val=VAL, mode=MODE_SUPER)
    cases["G1"] = {
        "case": "G1",
        "op": "ST",
        "pte": 0x01080907,
        "pte_hex": "0x01080907",
        "mode": "SUPER",
        "faulted": cpu_g1.faulted,
        "len_memory": len(cpu_g1.memory),
        "growth": len(cpu_g1.memory) - RAM_WORDS,
        "fault_reason": getattr(cpu_g1, "fault_reason", None),
        "word_1370": cpu_g1.memory[LEGIT_FRAME_WORD] if len(cpu_g1.memory) > LEGIT_FRAME_WORD else None,
        "word_2394": cpu_g1.memory[BOGUS_FRAME_WORD] if len(cpu_g1.memory) > BOGUS_FRAME_WORD else None,
    }

    # G2: small-pfn garbage 0x00000907 (pfn 9) — ST: does the store land at 2394 with no fault and no growth?
    cpu_g2 = _drive("ST", 0x00000907, val=VAL, mode=MODE_SUPER)
    cases["G2"] = {
        "case": "G2",
        "op": "ST",
        "pte": 0x00000907,
        "pte_hex": "0x00000907",
        "mode": "SUPER",
        "faulted": cpu_g2.faulted,
        "len_memory": len(cpu_g2.memory),
        "growth": len(cpu_g2.memory) - RAM_WORDS,
        "fault_reason": getattr(cpu_g2, "fault_reason", None),
        "word_1370": cpu_g2.memory[LEGIT_FRAME_WORD] if len(cpu_g2.memory) > LEGIT_FRAME_WORD else None,
        "word_2394": cpu_g2.memory[BOGUS_FRAME_WORD] if len(cpu_g2.memory) > BOGUS_FRAME_WORD else None,
    }

    # G3: LD twin, 0x00000907 — pre-seed memory[1370]=0x12345678, memory[2394]=0xCAFEBABE
    cpu_g3 = _drive(
        "LD",
        0x00000907,
        mode=MODE_SUPER,
        pre_seed={LEGIT_FRAME_WORD: 0x12345678, BOGUS_FRAME_WORD: 0xCAFEBABE},
    )
    cases["G3"] = {
        "case": "G3",
        "op": "LD",
        "pte": 0x00000907,
        "pte_hex": "0x00000907",
        "mode": "SUPER",
        "faulted": cpu_g3.faulted,
        "len_memory": len(cpu_g3.memory),
        "growth": len(cpu_g3.memory) - RAM_WORDS,
        "fault_reason": getattr(cpu_g3, "fault_reason", None),
        "registers_10": cpu_g3.registers[10],
    }

    # G4: LD twin, 0x01080907 — LD is uncontained; record registers[10] and faulted
    cpu_g4 = _drive("LD", 0x01080907, mode=MODE_SUPER)
    cases["G4"] = {
        "case": "G4",
        "op": "LD",
        "pte": 0x01080907,
        "pte_hex": "0x01080907",
        "mode": "SUPER",
        "faulted": cpu_g4.faulted,
        "len_memory": len(cpu_g4.memory),
        "growth": len(cpu_g4.memory) - RAM_WORDS,
        "fault_reason": getattr(cpu_g4, "fault_reason", None),
        "registers_10": cpu_g4.registers[10],
    }

    # C1: V-clear control, 0x01080900, SUPER — must fault
    cpu_c1 = _drive("ST", 0x01080900, val=VAL, mode=MODE_SUPER)
    cases["C1"] = {
        "case": "C1",
        "op": "ST",
        "pte": 0x01080900,
        "pte_hex": "0x01080900",
        "mode": "SUPER",
        "faulted": cpu_c1.faulted,
        "len_memory": len(cpu_c1.memory),
        "growth": len(cpu_c1.memory) - RAM_WORDS,
        "fault_reason": getattr(cpu_c1, "fault_reason", None),
        "word_1370": cpu_c1.memory[LEGIT_FRAME_WORD] if len(cpu_c1.memory) > LEGIT_FRAME_WORD else None,
        "word_2394": cpu_c1.memory[BOGUS_FRAME_WORD] if len(cpu_c1.memory) > BOGUS_FRAME_WORD else None,
    }

    # C2: USER-mode mechanism pin, 0x01080906 (V|W, no U) vs 0x01080907 (V|W|U)
    cpu_c2_refuse = _drive("LD", 0x01080906, mode=MODE_USER)
    cpu_c2_trans = _drive("LD", 0x01080907, mode=MODE_USER)
    cases["C2_refuse"] = {
        "case": "C2_refuse",
        "op": "LD",
        "pte": 0x01080906,
        "pte_hex": "0x01080906",
        "mode": "USER",
        "faulted": cpu_c2_refuse.faulted,
        "len_memory": len(cpu_c2_refuse.memory),
        "growth": len(cpu_c2_refuse.memory) - RAM_WORDS,
        "fault_reason": getattr(cpu_c2_refuse, "fault_reason", None),
        "registers_10": cpu_c2_refuse.registers[10],
    }
    cases["C2_trans"] = {
        "case": "C2_trans",
        "op": "LD",
        "pte": 0x01080907,
        "pte_hex": "0x01080907",
        "mode": "USER",
        "faulted": cpu_c2_trans.faulted,
        "len_memory": len(cpu_c2_trans.memory),
        "growth": len(cpu_c2_trans.memory) - RAM_WORDS,
        "fault_reason": getattr(cpu_c2_trans, "fault_reason", None),
        "registers_10": cpu_c2_trans.registers[10],
    }
    cases["C2"] = {
        "case": "C2",
        "mode": "USER",
        "refuse_pte": "0x01080906",
        "refuse_faulted": cpu_c2_refuse.faulted,
        "translate_pte": "0x01080907",
        "translate_faulted": cpu_c2_trans.faulted,
        "mechanism_pin_discriminating": bool(cpu_c2_refuse.faulted and not cpu_c2_trans.faulted),
    }

    # Print PROBE lines
    for case_name in ("N1", "G1", "G2", "G3", "G4", "C1", "C2_refuse", "C2_trans"):
        c = cases[case_name]
        kvs = [
            f"op={c['op']}",
            f"pte={c['pte_hex']}",
            f"mode={c['mode']}",
            f"faulted={c['faulted']}",
            f"len={c['len_memory']}",
            f"growth={c['growth']}",
        ]
        if c["op"] == "ST":
            w1370 = f"0x{c['word_1370']:08x}" if c["word_1370"] is not None else "None"
            w2394 = f"0x{c['word_2394']:08x}" if c["word_2394"] is not None else "None"
            kvs.extend([f"word_1370={w1370}", f"word_2394={w2394}"])
        else:
            r10 = f"0x{c['registers_10']:08x}" if c["registers_10"] is not None else "None"
            kvs.append(f"r10={r10}")
        kvs.append(f"fault_reason={c['fault_reason']}")
        print(f"PROBE {case_name} {' '.join(kvs)}")

    c2_disc = cases["C2"]["mechanism_pin_discriminating"]
    print(
        f"PROBE C2 mode=USER pte_refuse=0x01080906(faulted={cpu_c2_refuse.faulted}) "
        f"pte_trans=0x01080907(faulted={cpu_c2_trans.faulted}) discriminating={c2_disc}"
    )

    # Verdict
    g2 = cases["G2"]
    g2_misdirected = (
        not g2["faulted"]
        and g2["growth"] == 0
        and g2["word_2394"] == VAL
        and g2["word_1370"] == 0
    )
    verdict = (
        f"SILENT_MISDIRECTION_CONFIRMED — G2 faulted={g2['faulted']} growth={g2['growth']} "
        f"word_2394=0x{g2['word_2394']:08x} word_1370=0x{g2['word_1370']:08x} "
        "(store misdirected to bogus frame 2394; ceiling guard blind to small-pfn garbage)"
        if g2_misdirected
        else "UNEXPECTED_PROBE_OUTCOME"
    )
    print(f"PROBE_VERDICT: {verdict}")

    out_data = {
        "cases": cases,
        "verdict": verdict,
        "g2_silent_misdirection": g2_misdirected,
    }

    out_dir = REPO / "output"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "defect23_pte_acceptance_probe.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out_data, f, indent=2)

    return out_data


if __name__ == "__main__":
    run_probe()
