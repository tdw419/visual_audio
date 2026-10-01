#!/usr/bin/env python3
"""Gate for BK-66 — paged x tile fence composition (oracle, tools/glyph_isa_v2.py).

Ruling: DESIGN RULING 2026-09-28 (Jericho, commit 9714a363) — paged fence
consults PADDR post-translation; PTE writes paddr-fenced by the same consult;
lawful paged work preserved (L3); MMIO exemption untouched (SUPER branch).

Legs:
  L1  paged out-of-tile USER LD must trap (was RED: T1's clean read, r10=canary).
  L2  paged out-of-tile USER ST must not land (was RED: T2's landing at image
      word 1280).
  L3  mapped in-tile paged access stays green: in-tile vaddr -> plain PTE ->
      in-tile paddr lands clean USER; AND T3's unmapped-vpn translation fault
      is preserved byte-for-byte (translation semantics, NOT the fence's job).
  L4  unpaged rot-guards: C1 out-of-tile LD traps (BK-38), C2 out-of-tile ST
      traps (item-29), C3 in-tile LD+ST clean — never weaken the landed fences.
  L5  non-vacuity: the consult is neutered in a TEMP-COPY module (consult
      forced True) and L1's program re-runs — the canary must come back
      (pre-fix behavior reproduced). The real module's md5 is pinned
      before/after.
  L6  family: test_bk38_ld_fence.py + test_bk64_pte_flag_paged.py green.
  L7  ruling invariant: a vaddr-side implementation must FAIL L1 — simulated
      by the L5 temp-copy neutering plus the L1 fault_reason asserting the
      consult judged PADDR (paddr=1280), not vaddr (0x3000).

Determinism: no LLM/network/GPU; pinned probe programs; verdicts from
exit_status + fault fields + RAM/image readbacks, never stdout.
"""
import hashlib
import importlib.util
import sys
from pathlib import Path

import numpy as np
import pytest

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
for p in (str(REPO), str(REPO / "tools")):
    if p not in sys.path:
        sys.path.insert(0, p)

CANARY = 0x0ADF00D
PT_TAG_WORD = 1535
PT_BASE_WORD = 1536
PT_ARM_WORD = 8211            # PAGE_TABLE_WORD
TILE = (256, 19, 1, 2)        # covers RAM words 8211, 8212 only
VA_OUT = (12 << 8) | 0        # vaddr 3072: vpn 12, offset 0
VPN12_PTE_WORD = PT_BASE_WORD + 12   # 1548
VPN0_PTE_WORD = PT_BASE_WORD
PTE_PIX_FULL = 0xF | (5 << 8)        # V|W|U|PIX, pfn 5 -> image word 1280
PTE_PLAIN_VPN0 = 0x7                 # V|W|U, pfn 0 -> paddr = offset
CANARY_IMG_WORD = 1280
IN_TILE_WORD = 8212           # row 256, col 20 — inside tile (256,19,1,2)
OUT_TILE_LD_WORD = 4000

ARM_SNIPPET = "LDI r15 %d\nLDI r14 %d\nST r15 r14\n" % (PT_ARM_WORD, PT_BASE_WORD)


def _bake(text):
    from tools.glyph_gpt.baker import bake_image
    return bake_image(text, cols_instrs=8, min_rows=64, out_path=None)


def _stamp(img, stamps):
    h, w, _ = img.shape
    for word, val in stamps.items():
        idx = word % (h * w)
        img[idx // w, idx % w] = ((val >> 16) & 0xFF, (val >> 8) & 0xFF, val & 0xFF)
    return img


def _run(text, stamps):
    """Run a program in the real contained-spawn posture. Returns a dict of
    readback verdicts (exit status, fault fields, RAM + image words)."""
    from tools.glyph_process import GlyphProcessTable
    img = _bake(text)
    h, w, _ = img.shape
    assert w * h >= 1549, "image must contain the PT window unwrapped"
    _stamp(img, stamps)
    table = GlyphProcessTable(memory_words=16384)
    pid = table.spawn(image=img, tile=TILE, max_instructions=500)
    cpu = table.tasks[pid]["cpu"]
    task = table.tasks[pid]
    table._run_task(pid)
    mem = cpu.memory
    timg = task["image"]
    idx = CANARY_IMG_WORD % (timg.shape[0] * timg.shape[1])
    px = timg[idx // timg.shape[1], idx % timg.shape[1]]
    return {
        "exit": task["exit_status"],
        "faulted": bool(cpu.faulted),
        "fault_addr": int(cpu.fault_addr) if cpu.fault_addr is not None else None,
        "fault_reason": cpu.fault_reason,
        "mode": "USER" if cpu.mode == 1 else "SUPER",
        "r10": int(cpu.registers[10]) & 0xFFFFFFFF,
        "canary_word": (int(px[0]) << 16) | (int(px[1]) << 8) | int(px[2]),
        "in_tile_word": int(mem[IN_TILE_WORD]) & 0xFFFFFFFF,
    }


def _stamped_engine_copy(tmp_path):
    """Import a TEMP COPY of the engine with the BK-66 consult neutered
    (physical_in_tile -> always True), proving the gate discriminates."""
    src = (REPO / "tools" / "glyph_isa_v2.py").read_text()
    needle = "def _physical_in_tile(self, word_addr: int) -> bool:"
    assert needle in src, "consult helper missing — gate must pin its target"
    neutered = src.replace(
        needle,
        "def _physical_in_tile(self, word_addr: int) -> bool:\n"
        "        return True  # NEUTERED for non-vacuity probe\n"
        "    def _physical_in_tile_original_unused(self, word_addr: int) -> bool:",
        1)
    assert neutered != src
    mod_path = tmp_path / "glyph_isa_v2_neutered.py"
    mod_path.write_text(neutered)
    spec = importlib.util.spec_from_file_location("glyph_isa_v2_neutered", mod_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------- L1: paged out-of-tile LD traps
def test_l1_paged_out_of_tile_ld_traps():
    r = _run(
        ":__entry\n" + ARM_SNIPPET
        + "LDI r15 %d\nLD r10 r15\nHALT\n" % VA_OUT,
        {PT_TAG_WORD: 0x505447, VPN12_PTE_WORD: PTE_PIX_FULL,
         CANARY_IMG_WORD: CANARY})
    assert r["faulted"] is True, r
    assert r["exit"] == 1, r
    assert r["r10"] != CANARY, "out-of-tile paged LD must not deliver the word"
    assert r["fault_addr"] == CANARY_IMG_WORD * 4, r  # fence judged the PADDR (1280*4)
    assert "paged_paddr_fence" in (r["fault_reason"] or ""), r
    assert "paddr=1280" in (r["fault_reason"] or ""), r  # L7: consult saw the PADDR, not vaddr 0x3000


# ---------------------------------------------------------------- L2: paged out-of-tile ST does not land
def test_l2_paged_out_of_tile_st_refused():
    r = _run(
        ":__entry\n" + ARM_SNIPPET
        + "LDI r5 %d\nLDI r15 %d\nST r15 r5\nHALT\n" % (CANARY, VA_OUT),
        {PT_TAG_WORD: 0x505447, VPN12_PTE_WORD: PTE_PIX_FULL})
    assert r["faulted"] is True, r
    assert r["exit"] == 1, r
    assert r["canary_word"] != CANARY, "out-of-tile paged ST must not land at the frame word"
    assert r["fault_addr"] == CANARY_IMG_WORD * 4, r
    assert "paged_paddr_fence" in (r["fault_reason"] or ""), r


# ---------------------------------------------------------------- L3: lawful paged work preserved
def test_l3a_mapped_in_tile_paged_access_lands():
    # in-tile vaddr (8212) through a plain PTE mapping to the in-tile paddr
    # (pfn 32 -> paddr 32*256+off covers word 8212 with offset 20).
    vpn32_pte_word = PT_BASE_WORD + 32  # 1568 — vaddr 8212 = vpn 32, offset 20
    pte_plain_vpn32 = 0x7 | (32 << 8)   # V|W|U, pfn 32 -> paddr 8192+off
    r = _run(
        ":__entry\n" + ARM_SNIPPET
        + "LDI r5 4660\nLDI r15 %d\nST r15 r5\nHALT\n" % 8212,
        {PT_TAG_WORD: 0x505447, vpn32_pte_word: pte_plain_vpn32})
    assert r["faulted"] is False, r
    assert r["exit"] == 0, r
    assert r["in_tile_word"] == 4660, "lawful mapped in-tile paged ST must land"
    assert r["mode"] == "USER", r


def test_l3b_unmapped_translation_fault_unchanged():
    # T3's shape: paged ST to in-tile vaddr 8212 with NO PTE for vpn 32 ->
    # pte_invalid translation fault (translation semantics, NOT the fence).
    r = _run(
        ":__entry\n" + ARM_SNIPPET
        + "LDI r5 4660\nLDI r15 %d\nST r15 r5\nHALT\n" % 8212,
        {PT_TAG_WORD: 0x505447, VPN0_PTE_WORD: PTE_PLAIN_VPN0})
    assert r["faulted"] is True, r
    assert "pte_invalid" in (r["fault_reason"] or ""), r
    assert r["fault_addr"] == 8212 * 4, r  # 32848 — byte-identical to the probe


# ---------------------------------------------------------------- L4: unpaged rot-guards
def test_l4_unpaged_fences_live():
    c1 = _run(":__entry\nLDI r15 %d\nLD r10 r15\nHALT\n" % OUT_TILE_LD_WORD, {})
    assert c1["faulted"] is True and c1["fault_addr"] == OUT_TILE_LD_WORD * 4, c1
    c2 = _run(":__entry\nLDI r5 4660\nLDI r15 164\nST r15 r5\nHALT\n", {})
    assert c2["faulted"] is True and c2["fault_addr"] == 656, c2
    c3 = _run(
        ":__entry\nLDI r15 %d\nLD r10 r15\nLDI r5 4660\nST r15 r5\nHALT\n"
        % IN_TILE_WORD, {})
    assert c3["faulted"] is False and c3["exit"] == 0 and c3["mode"] == "USER", c3
    assert c3["in_tile_word"] == 4660, c3


# ---------------------------------------------------------------- L5: non-vacuity (temp-copy neuter)
def test_l5_neutered_consult_reproduces_red(tmp_path):
    real_md5_before = hashlib.md5(
        (REPO / "tools" / "glyph_isa_v2.py").read_bytes()).hexdigest()
    neutered = _stamped_engine_copy(tmp_path)

    from tools.glyph_gpt.baker import bake_image
    text = ":__entry\n" + ARM_SNIPPET + "LDI r15 %d\nLD r10 r15\nHALT\n" % VA_OUT
    img = bake_image(text, cols_instrs=8, min_rows=64, out_path=None)
    h, w, _ = img.shape
    _stamp(img, {PT_TAG_WORD: 0x505447, VPN12_PTE_WORD: PTE_PIX_FULL,
                 CANARY_IMG_WORD: CANARY})

    from tools.glyph_containment import arm_tile  # noqa: F401  (parity with spawn path)
    from tools.glyph_process import GlyphProcessTable
    # Spawn through the REAL table, then swap the engine module class is not
    # possible post-construction — instead run the neutered class directly in
    # the same contained posture (arm_tile + reaper arming, mirroring spawn).
    from tools.glyph_isa_v2 import GlyphCPUv2, OpcodeMapV2
    from tools.glyph_containment import wrap_with_reaper
    img2 = wrap_with_reaper(_stamp(
        bake_image(text, cols_instrs=8, min_rows=64, out_path=None),
        {PT_TAG_WORD: 0x505447, VPN12_PTE_WORD: PTE_PIX_FULL,
         CANARY_IMG_WORD: CANARY}), 30, OpcodeMapV2())
    cpu = neutered.GlyphCPUv2(OpcodeMapV2(), cols_instrs=8)
    cpu.memory = [0] * 16384
    arm_tile(cpu, TILE)
    cpu.memory[8193] = 30 << 16  # KFAULT_PC -> reaper row 30 (spawn's posture)
    img2 = np.concatenate([img, np.zeros((img2.shape[0] - img.shape[0],
                                          img2.shape[1], 3), dtype=np.uint8)]) \
        if img2.shape[0] > img.shape[0] else img2
    cpu.running = True  # cpu.run() would set this; the manual loop mirrors it
    steps = 0
    while cpu.running and steps < 500:
        cpu.step(img2)
        steps += 1
    assert cpu.faulted is False, \
        "neutered consult must reproduce the RED (clean out-of-tile paged LD)"
    assert (int(cpu.registers[10]) & 0xFFFFFFFF) == CANARY, \
        "neutered consult must deliver the canary (pre-fix behavior)"
    real_md5_after = hashlib.md5(
        (REPO / "tools" / "glyph_isa_v2.py").read_bytes()).hexdigest()
    assert real_md5_before == real_md5_after, "real engine mutated by the probe"


# ---------------------------------------------------------------- L6: family regression
def test_l6_family_gates_green():
    import subprocess
    for gate in ("tests/test_bk38_ld_fence.py", "tests/test_bk64_pte_flag_paged.py"):
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "-x", "-q", str(REPO / gate)],
            capture_output=True, text=True, timeout=600, cwd=str(REPO))
        assert proc.returncode == 0, f"{gate} regressed:\n{proc.stdout[-2000:]}"
