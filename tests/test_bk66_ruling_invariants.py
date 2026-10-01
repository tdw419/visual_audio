#!/usr/bin/env python3
"""BK-66 DESIGN RULING (2026-09-28, commit 9714a363) clause 2b/2c invariant legs.

The BK-66 landing gate (tests/test_bk66_paged_tile_fence.py L1-L7) proved the
paddr consult itself; the ruling's clause 2 invariant legs were named but not
yet authored. This file lands them — ADD, don't swap (directive clause 3).

Legs:
  T1  clause 2b — cross-task PT-window exclusion. Task A (tile-armed, paged)
      maps a vaddr ONTO ITS OWN PT header paddr (pt_base-1 = 1535) via a
      plain PTE and stores a canary: the paddr fence must refuse the access
      itself (clause 2a — the fence gates the ACCESS, no implicit gap for
      PT-window words). Task B, spawned on the SAME process table with its
      own image + PT window, must be unaffected: lawful paged ST+LD through
      its own PT lands clean USER and its header readback carries no trace
      of A's canary (a leaked write would flip B's tag check to
      pt_tag_mismatch -> fault -> exit 1).
  T2  clause 2c — the PAGE_TABLE_TAG header check (pt_base-1) still fires
      when the header word itself HAS BEEN written: with a WRONG tag stamped
      where the header lives (RAM-first/image-fallback read), the next paged
      access faults pt_tag_mismatch with fault_addr = vaddr<<2 — the header
      check has teeth over a written header, not just an absent one.
  T3  non-vacuity — the consult is neutered in a TEMP-COPY module
      (_physical_in_tile -> always True) and T1's Task-A program re-runs:
      the canary must LAND at RAM word 1535 (the pre-ruling implicit gap
      reproduced — proving T1's refusal assertion discriminates). The real
      engine md5 is pinned before/after.

Encoding note (learned from the BK-48 gate-draft defect, receipted there):
LD/ST pack rd=A/rs2=B — the ADDRESS travels in rs2 for LD and rs1 for ST;
the assembler (glyph_isa_v2.py GlyphAssemblerV2) takes "LD rd addr_reg" /
"ST addr_reg val_reg". Programs below hold addresses in the correct slots.

Determinism: no LLM/network/GPU; pinned probe programs; verdicts from
exit_status + fault fields + RAM readbacks, never stdout.
"""
import hashlib
import importlib.util
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
for p in (str(REPO), str(REPO / "tools")):
    if p not in sys.path:
        sys.path.insert(0, p)

CANARY = 0x0ADF00D
PT_TAG = 0x505447
PT_TAG_WORD = 1535            # pt_base - 1 — the header
PT_BASE_WORD = 1536
PT_ARM_WORD = 8211            # PAGE_TABLE_WORD (in-tile: the lawful arm)
TILE = (256, 19, 1, 2)        # covers RAM words 8211..8212 only
HEADER_VADDR = 1535           # vpn 5, offset 255 -> paddr 5*256+255 = 1535
VPN5_PTE_WORD = PT_BASE_WORD + 5      # 1541
VPN5_PTE_PLAIN = 0x7 | (5 << 8)       # V|W|U, pfn 5 -> paddr = 5*256+off
VPN32_PTE_WORD = PT_BASE_WORD + 32    # 1568
VPN32_PTE_PLAIN = 0x7 | (32 << 8)     # V|W|U, pfn 32 -> paddr = 8192+off
IN_TILE_WORD = 8212
WRONG_TAG = 0xDEAD00

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


def _spawn_and_run(table, text, stamps):
    """Bake, stamp, spawn tile-armed on `table`, run to completion.
    Returns (task_dict, cpu) with readback access to the task's OWN RAM."""
    img = _bake(text)
    h, w, _ = img.shape
    assert w * h >= 1569, "image must contain the PT window unwrapped"
    _stamp(img, stamps)
    pid = table.spawn(image=img, tile=TILE, max_instructions=500)
    task = table.tasks[pid]
    table._run_task(pid)
    return task, task["cpu"]


# --------------------------------------------------------------- T1: clause 2b
def test_t1_cross_task_pt_window_exclusion():
    from tools.glyph_process import GlyphProcessTable

    # Task A: map a vaddr onto its own PT header paddr, store the canary.
    # Clause 2a: the paddr fence must refuse the ACCESS itself (no implicit
    # PT-window gap); clause 2b: the refusal must be the paddr-side one.
    prog_a = (":__entry\n" + ARM_SNIPPET
              + "LDI r5 %d\nLDI r15 %d\nST r15 r5\nHALT\n" % (CANARY, HEADER_VADDR))
    table = GlyphProcessTable(memory_words=16384)
    task_a, cpu_a = _spawn_and_run(
        table, prog_a,
        {PT_TAG_WORD: PT_TAG, VPN5_PTE_WORD: VPN5_PTE_PLAIN})
    assert task_a["exit_status"] == 1, "A's header-window ST must fault"
    assert cpu_a.faulted is True
    assert cpu_a.fault_addr == HEADER_VADDR * 4, (
        "fence must judge the header PADDR 1535 (byte %d)" % (HEADER_VADDR * 4))
    assert "paged_paddr_fence" in (cpu_a.fault_reason or "")
    assert "paddr=1535" in (cpu_a.fault_reason or "")
    assert (cpu_a.memory[PT_TAG_WORD] & 0xFFFFFFFF) != CANARY, \
        "the canary must not land in A's own PT header either"

    # Task B: same table, own image + PT window, lawful paged ST+LD in-tile.
    prog_b = (":__entry\n" + ARM_SNIPPET
              + "LDI r5 4660\nLDI r15 %d\nST r15 r5\nLD r10 r15\nHALT\n"
              % IN_TILE_WORD)
    task_b, cpu_b = _spawn_and_run(
        table, prog_b,
        {PT_TAG_WORD: PT_TAG, VPN32_PTE_WORD: VPN32_PTE_PLAIN})
    assert task_b["exit_status"] == 0, \
        "B must be unaffected by A's refused header write: %s" % cpu_b.fault_reason
    assert cpu_b.faulted is False
    assert (cpu_b.registers[10] & 0xFFFFFFFF) == 4660, \
        "B's lawful paged ST+LD must land clean USER"
    assert (cpu_b.memory[PT_TAG_WORD] & 0xFFFFFFFF) != CANARY, \
        "cross-task PT-window leak: A's canary reached B's header word"
    assert (cpu_b.memory[VPN5_PTE_WORD] & 0xFFFFFFFF) != CANARY, \
        "cross-task PT-window leak: A's canary reached B's PTE slot"


# --------------------------------------------------------------- T2: clause 2c
def test_t2_header_tag_check_fires_over_written_header():
    from tools.glyph_process import GlyphProcessTable

    # The header word HAS BEEN written (wrong tag) — the check_pt_tag
    # RAM-first/image-fallback read consults the written value and must
    # refuse the paged access. Simulates the post-write state clause 2c
    # pins: the header check survives header mutation.
    prog = (":__entry\n" + ARM_SNIPPET
            + "LDI r15 %d\nLD r10 r15\nHALT\n" % IN_TILE_WORD)
    table = GlyphProcessTable(memory_words=16384)
    task, cpu = _spawn_and_run(
        table, prog,
        {PT_TAG_WORD: WRONG_TAG, VPN32_PTE_WORD: VPN32_PTE_PLAIN})
    assert task["exit_status"] == 1
    assert cpu.faulted is True
    assert "pt_tag_mismatch" in (cpu.fault_reason or "")
    assert ("got=0xdead00" in (cpu.fault_reason or "")), cpu.fault_reason
    assert cpu.fault_addr == IN_TILE_WORD * 4  # vaddr 8212 -> byte 32848

    # Control: the SAME program with the CORRECT tag passes the header.
    table2 = GlyphProcessTable(memory_words=16384)
    task2, cpu2 = _spawn_and_run(
        table2, prog,
        {PT_TAG_WORD: PT_TAG, VPN32_PTE_WORD: VPN32_PTE_PLAIN})
    assert task2["exit_status"] == 0, cpu2.fault_reason
    assert cpu2.faulted is False


# ------------------------------------------------------- T3: non-vacuity (RED)
def test_t3_neutered_consult_reproduces_implicit_gap(tmp_path):
    real_md5_before = hashlib.md5(
        (REPO / "tools" / "glyph_isa_v2.py").read_bytes()).hexdigest()

    src = (REPO / "tools" / "glyph_isa_v2.py").read_text()
    needle = "def _physical_in_tile(self, word_addr: int) -> bool:"
    assert needle in src, "consult helper missing — gate must pin its target"
    neutered_src = src.replace(
        needle,
        "def _physical_in_tile(self, word_addr: int) -> bool:\n"
        "        return True  # NEUTERED for non-vacuity probe\n"
        "    def _physical_in_tile_original_unused(self, word_addr: int) -> bool:",
        1)
    assert neutered_src != src
    mod_path = tmp_path / "glyph_isa_v2_neutered_t3.py"
    mod_path.write_text(neutered_src)
    spec = importlib.util.spec_from_file_location("glyph_isa_v2_neutered_t3",
                                                  mod_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    prog_a = (":__entry\n" + ARM_SNIPPET
              + "LDI r5 %d\nLDI r15 %d\nST r15 r5\nHALT\n" % (CANARY, HEADER_VADDR))
    from tools.glyph_isa_v2 import OpcodeMapV2
    from tools.glyph_containment import arm_tile, wrap_with_reaper
    img = wrap_with_reaper(
        _stamp(_bake(prog_a),
               {PT_TAG_WORD: PT_TAG, VPN5_PTE_WORD: VPN5_PTE_PLAIN}),
        30, OpcodeMapV2())
    cpu = mod.GlyphCPUv2(OpcodeMapV2(), cols_instrs=8)
    cpu.memory = [0] * 16384
    arm_tile(cpu, TILE)
    cpu._tile_confinement = True  # spawn(tile=...) sets this; arm_tile alone does not
    cpu.memory[8193] = 30 << 16  # KFAULT_PC -> reaper row 30 (spawn posture)
    cpu.running = True
    steps = 0
    while cpu.running and steps < 500:
        cpu.step(img)
        steps += 1
    # Pre-ruling behavior reproduced: with the consult gone, the PT-window
    # word is writable THROUGH TRANSLATION — the implicit gap clause 2a closes.
    assert cpu.faulted is False, \
        "neutered consult must reproduce the RED (clean header-window paged ST)"
    assert (cpu.memory[PT_TAG_WORD] & 0xFFFFFFFF) == CANARY, \
        "neutered consult must let the canary LAND in the PT header word"

    real_md5_after = hashlib.md5(
        (REPO / "tools" / "glyph_isa_v2.py").read_bytes()).hexdigest()
    assert real_md5_before == real_md5_after, "real engine mutated by the probe"
