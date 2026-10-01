"""BK-39 gate (step 1 of the sequenced fence commit): the oracle engine's
guest-reachable WRITE/READ arms consult the E-K1 fence.

Landed state this gate closes (measured, probes probe_pst_fence_af3e.py /
probe_wgsl_stack_fence_af3e.md at HEAD bf6f2b6e / 8f5f2e47):
  - PARALLEL_ST writes self.memory with a bounds check only -> a tiled USER
    task stores out-of-tile clean AND can self-grant BOX0 (words 8195/8196),
    rewriting its own confinement.
  - PARALLEL_LD reads out-of-tile clean (read-side parity with BK-38's
    scalar-LD gap, aligned to the SAME landed semantics: tile-spawn LD
    confinement per RULING_BK38_READ_POSTURE clause 3).
  - PUSH/POP/CALL/RET/CALLR touch the IMAGE plane via _mem_write/_mem_read
    with no box consult -> the cross-fence stack word lands/reads clean.
The WGSL twin's equivalents are ALREADY LANDED (BK-49 stack_fence_fault at
wgsl_glyph_isa_v2.py:625, BK-51 tile term); this gate pins the oracle to
the same posture. Consult term = GlyphCPUv2._addr_in_box (boxes + GO-2
tile), USER-only, SUPER exempt (kernel stacks untouched) — the twin's
exact shape. PARALLEL refs refuse the whole op at the first offending
word (nothing lands — E-K1's "the store is abandoned" discipline); stack
ops consult the exact stack word BEFORE the pre-decrement/read so a
refused op mutates nothing (twin posture, wgsl_glyph_isa_v2.py:607-628).
"""
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

import numpy as np  # noqa: E402

from tools.glyph_isa_v2 import (  # noqa: E402
    GlyphAssemblerV2, GlyphCPUv2, MODE_SUPER,
    OpcodeMapV2, W_MEM,
)
from tools.glyph_process import EXIT_FAULT, EXIT_OK, GlyphProcessTable  # noqa: E402

OM = OpcodeMapV2()
TILE_ROW, TILE_COL, TILE_H, TILE_W = 5, 0, 2, 4
IN_TILE_WORD = TILE_ROW * W_MEM + TILE_COL          # 160
OUT_TILE_WORD = IN_TILE_WORD + TILE_W               # 164 (first word outside)
CANARY = 0x0BADF00D
BOX0_LO_WORD = 0x800C >> 2                          # 8195
BOX0_HI_WORD = 0x8010 >> 2                          # 8196
SP_OUT = 200                                        # row 6 col 8 — outside tile cols
SP_IN = TILE_ROW * W_MEM + 2                        # 162 — inside tile


def _build(prog_lines):
    asm = GlyphAssemblerV2(OM)
    return asm.assemble(prog_lines, width_instrs=8)


def _spawn(prog_lines, neuter=False):
    img = _build(prog_lines)
    table = GlyphProcessTable()
    pid = table.spawn(img, name="bk39", tile=(TILE_ROW, TILE_COL, TILE_H, TILE_W))
    cpu = table.tasks[pid]["cpu"]
    if neuter:
        # Non-vacuity instrument: consults admit everything -> the fence
        # must go silent and the pre-fix behavior must reappear.
        cpu._addr_in_box = lambda byte_addr: True
        cpu._addr_in_tile = lambda word_addr: True
    for addr, val in seed_words.items():
        cpu.memory[addr] = val & 0xFFFFFFFF
    rc = table.wait(pid)
    return table, cpu, rc


def _run(prog_lines, seed=None, neuter=False):
    global seed_words
    seed_words = seed or {}
    return _spawn(prog_lines, neuter=neuter)


seed_words = {}


# ── L1: tiled USER PARALLEL_ST out-of-tile → refused ────────────────────
def test_l1_parallel_st_out_of_tile_traps():
    """RED today: clean exit, value lands at 164."""
    prog = [
        "LDI r2 %d" % OUT_TILE_WORD,
        "LDI r3 %d" % CANARY,
        "PARALLEL_ST r2 r3 1",
        "HALT",
    ]
    table, cpu, rc = _run(prog)
    assert rc == EXIT_FAULT
    assert cpu.faulted
    assert cpu.fault_addr == OUT_TILE_WORD * 4
    assert cpu.memory[OUT_TILE_WORD] == 0  # nothing landed


# ── L2: the BOX0 self-grant is dead — PARALLEL_ST cannot re-arm the box ──
def test_l2_box_self_grant_traps():
    """RED today: box re-armed, out-of-box ST lands at 999."""
    prog = [
        "LDI r2 %d" % BOX0_LO_WORD,
        "LDI r3 0",
        "PARALLEL_ST r2 r3 1",      # BOX0_LO := 0
        "LDI r2 %d" % BOX0_HI_WORD,
        "LDI r3 65536",
        "PARALLEL_ST r2 r3 1",      # BOX0_HI := 65536 (all RAM)
        "LDI r2 999",
        "LDI r3 %d" % CANARY,
        "ST r2 r3",                 # plain ST — out-of-box pre-grant
        "HALT",
    ]
    table, cpu, rc = _run(prog)
    assert rc == EXIT_FAULT
    assert cpu.fault_addr == BOX0_LO_WORD * 4  # refused at the FIRST offending word
    assert cpu.memory[BOX0_HI_WORD] == 0       # box never re-armed
    assert cpu.memory[999] == 0                # the escalation store never fired


# ── L3: in-tile PARALLEL_ST control lands ───────────────────────────────
def test_l3_parallel_st_in_tile_lands():
    prog = [
        "LDI r2 %d" % IN_TILE_WORD,
        "LDI r3 %d" % CANARY,
        "PARALLEL_ST r2 r3 2",      # stores r3 AND r4 (r4=0) — count 2
        "LDI r5 0",
        "PARALLEL_ST r2 r5 1",      # reset word 160 via count-1 store... r5=0
        "LDI r2 %d" % (IN_TILE_WORD + 1),
        "LDI r6 %d" % CANARY,
        "PARALLEL_ST r2 r6 1",
        "HALT",
    ]
    table, cpu, rc = _run(prog)
    assert rc == EXIT_OK, "in-tile PARALLEL_ST must stay lawful"
    assert cpu.memory[IN_TILE_WORD + 1] == CANARY


# ── L4: tiled USER PARALLEL_LD out-of-tile → refused (BK-38 alignment) ──
def test_l4_parallel_ld_out_of_tile_traps():
    """RED today: canary enters r4 and lands in-tile at 160."""
    prog = [
        "PARALLEL_LD r4 %d 1" % OUT_TILE_WORD,
        "LDI r2 %d" % IN_TILE_WORD,
        "ST r2 r4",                 # in-tile exfil ST
        "HALT",
    ]
    table, cpu, rc = _run(prog, seed={OUT_TILE_WORD: CANARY})
    assert rc == EXIT_FAULT
    assert cpu.fault_addr == OUT_TILE_WORD * 4
    assert cpu.memory[IN_TILE_WORD] == 0  # exfil closed


def test_l4b_parallel_ld_in_tile_lands():
    prog = [
        "PARALLEL_LD r4 %d 1" % IN_TILE_WORD,
        "HALT",
    ]
    table, cpu, rc = _run(prog, seed={IN_TILE_WORD: CANARY})
    assert rc == EXIT_OK
    assert cpu.registers[4] == CANARY


# ── L5: the stack path consults the fence (twin BK-49 posture) ──────────
def test_l5a_push_out_of_tile_traps():
    prog = [
        "LDI r31 %d" % SP_OUT,
        "LDI r5 77",
        "PUSH r5",
        "HALT",
    ]
    table, cpu, rc = _run(prog)
    assert rc == EXIT_FAULT
    assert cpu.fault_addr == (SP_OUT - 1) * 4  # judged word is the post-decrement slot


def test_l5b_pop_out_of_tile_traps():
    prog = [
        "LDI r31 %d" % SP_OUT,
        "POP r5",
        "HALT",
    ]
    table, cpu, rc = _run(prog)
    assert rc == EXIT_FAULT
    assert cpu.fault_addr == SP_OUT * 4


def test_l5c_in_tile_stack_roundtrip_lands():
    """Control: USER stack inside the tile (BOX2/stack-page class) works."""
    prog = [
        "LDI r31 %d" % SP_IN,
        "LDI r5 77",
        "PUSH r5",
        "POP r6",
        "LDI r2 %d" % IN_TILE_WORD,
        "ST r2 r6",
        "HALT",
    ]
    table, cpu, rc = _run(prog)
    assert rc == EXIT_OK, "in-tile USER stack must stay lawful"
    assert cpu.memory[IN_TILE_WORD] == 77


def test_l5d_super_stack_exempt():
    """SUPER (no tile confinement) stack ops are untouched — kernel KJMP/
    entry stacks must not fault. Plain spawn (tile=None) runs SUPER."""
    img = _build([
        "LDI r31 %d" % SP_OUT,
        "LDI r5 77",
        "PUSH r5",
        "POP r6",
        "HALT",
    ])
    table = GlyphProcessTable()
    pid = table.spawn(img, name="bk39super")
    cpu = table.tasks[pid]["cpu"]
    rc = table.wait(pid)
    assert rc == EXIT_OK
    assert cpu.mode == MODE_SUPER


# ── L6: non-vacuity — neuter the consults → the pre-fix shape returns ───
def test_l6_nonvacuity_neutered_consults_land():
    prog = [
        "LDI r2 %d" % OUT_TILE_WORD,
        "LDI r3 %d" % CANARY,
        "PARALLEL_ST r2 r3 1",
        "HALT",
    ]
    table, cpu, rc = _run(prog, neuter=True)
    assert rc == EXIT_OK, "with the consult neutered the store must LAND (fence is the blocker)"
    assert cpu.memory[OUT_TILE_WORD] == CANARY


# ── L7: family — landed fence gates stay green (run in-process set) ─────
def test_l7_family_import_and_engine_md5_mirror():
    """The glyph_dispatch mirror must stay byte-identical to the engine
    (BK-52/BK-76 sync discipline)."""
    main = os.path.join(REPO, "tools", "glyph_isa_v2.py")
    mirror = os.path.join(REPO, "glyph_dispatch", "src", "glyph", "glyph_isa_v2.py")
    with open(main, "rb") as f:
        h1 = __import__("hashlib").md5(f.read()).hexdigest()
    with open(mirror, "rb") as f:
        h2 = __import__("hashlib").md5(f.read()).hexdigest()
    assert h1 == h2, f"engine mirror drift: {h1} != {h2}"
