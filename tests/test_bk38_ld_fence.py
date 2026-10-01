"""BK-38 gate: LD tile-fence guard.

USER-mode LD from outside the armed GO-2 tile must trap (E-K1 path), not
silently return the word. Mirrors the ST-side trap that was already live;
LD was the read-side gap (see systems/GLYPH_BACKLOG.md BK-38, measured by
.builder_queue/probe_ld_fence_af3e.py at HEAD b2c00b68).
"""
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

from tools.glyph_isa_v2 import GlyphAssemblerV2, MODE_SUPER, OpcodeMapV2, W_MEM  # noqa: E402
from tools.glyph_process import EXIT_FAULT, EXIT_OK, GlyphProcessTable  # noqa: E402

OM = OpcodeMapV2()
TILE_ROW, TILE_COL, TILE_H, TILE_W = 5, 0, 2, 4
IN_TILE_WORD = TILE_ROW * W_MEM + TILE_COL          # 160
OUT_TILE_WORD = IN_TILE_WORD + TILE_W               # 164 (first word outside)
CANARY = 0x0BADF00D


def _build(prog_lines):
    asm = GlyphAssemblerV2(OM)
    return asm.assemble(prog_lines, width_instrs=8)


def _run(prog_lines, seed):
    img = _build(prog_lines)
    table = GlyphProcessTable()
    pid = table.spawn(img, name="bk38", tile=(TILE_ROW, TILE_COL, TILE_H, TILE_W))
    cpu = table.tasks[pid]["cpu"]
    for addr, val in seed.items():
        cpu.memory[addr] = val & 0xFFFFFFFF
    rc = table.wait(pid)
    return cpu, rc


def test_l1_out_of_tile_ld_traps():
    """RED today: clean exit, canary lands in-tile. Must now fault."""
    prog = [
        "LDI r2 %d" % OUT_TILE_WORD,
        "LD r3 r2",
        "LDI r2 %d" % IN_TILE_WORD,
        "ST r2 r3",
        "HALT",
    ]
    cpu, rc = _run(prog, {OUT_TILE_WORD: CANARY, IN_TILE_WORD: 0})
    assert rc == EXIT_FAULT
    assert cpu.faulted is True
    assert cpu.fault_addr == OUT_TILE_WORD * 4
    # the exfil ST never ran (fault dropped into the kernel reaper first)
    assert cpu.memory[IN_TILE_WORD] == 0


def test_l2_in_tile_ld_unchanged():
    prog = [
        "LDI r2 %d" % IN_TILE_WORD,
        "LD r3 r2",
        "LDI r2 %d" % (IN_TILE_WORD + 1),
        "ST r2 r3",
        "HALT",
    ]
    cpu, rc = _run(prog, {IN_TILE_WORD: CANARY, IN_TILE_WORD + 1: 0})
    assert rc == EXIT_OK
    assert cpu.faulted is False
    assert cpu.memory[IN_TILE_WORD + 1] == CANARY


def test_l3_boundary_word_traps_on_both_ld_and_st():
    st_prog = [
        "LDI r2 %d" % IN_TILE_WORD,
        "LDI r3 %d" % (CANARY & 0xFFFF),
        "LDI r2 %d" % OUT_TILE_WORD,
        "ST r2 r3",
        "HALT",
    ]
    cpu_st, rc_st = _run(st_prog, {OUT_TILE_WORD: 0})
    assert rc_st == EXIT_FAULT
    assert cpu_st.fault_addr == OUT_TILE_WORD * 4

    ld_prog = [
        "LDI r2 %d" % OUT_TILE_WORD,
        "LD r3 r2",
        "HALT",
    ]
    cpu_ld, rc_ld = _run(ld_prog, {OUT_TILE_WORD: CANARY})
    assert rc_ld == EXIT_FAULT
    assert cpu_ld.fault_addr == OUT_TILE_WORD * 4


def test_l4_super_mode_ld_unaffected():
    """Non-tiled / SUPER-mode LD (no isolation armed) must be untouched."""
    prog = [
        "LDI r2 %d" % OUT_TILE_WORD,
        "LD r3 r2",
        "LDI r2 %d" % IN_TILE_WORD,
        "ST r2 r3",
        "HALT",
    ]
    img = _build(prog)
    from tools.glyph_isa_v2 import GlyphCPUv2

    cpu = GlyphCPUv2(OM, cols_instrs=8)
    cpu.memory[OUT_TILE_WORD] = CANARY
    cpu.pc = (0, 0)
    cpu.running = True
    while cpu.running:
        cpu.step(img)
    assert cpu.faulted is False
    assert cpu.memory[IN_TILE_WORD] == CANARY


def test_f1_mmio_config_block_user_ld_reads_zero():
    """F1 falsifier: USER LD of MMIO config words (8192+) must return 0.

    De-fangs the BK-55 aim step without breaking general cooperative reads.
    """
    from tools.glyph_isa_v2 import GlyphCPUv2, MODE_USER, KFAULT_PC_ADDR, BOX0_HI_ADDR

    kf_word = KFAULT_PC_ADDR >> 2
    box_word = BOX0_HI_ADDR >> 2
    prog = [
        "LDI r2 %d" % kf_word,
        "LD r3 r2",
        "LDI r2 %d" % box_word,
        "LD r4 r2",
        "HALT",
    ]
    img = _build(prog)
    cpu = GlyphCPUv2(OM, cols_instrs=8)
    cpu.memory = [0] * (box_word + 10)
    cpu.memory[kf_word] = 0x1234
    cpu.memory[box_word] = 0x5678
    cpu.mode = MODE_USER
    cpu.pc = (0, 0)
    cpu.running = True
    while cpu.running:
        cpu.step(img)

    assert cpu.faulted is False
    assert cpu.registers[3] == 0, f"USER LD of KFAULT_PC leaked {cpu.registers[3]:#x} (expected 0)"
    assert cpu.registers[4] == 0, f"USER LD of BOX0_HI leaked {cpu.registers[4]:#x} (expected 0)"


def test_f2_cooperative_user_ld_global_succeeds():
    """F2 falsifier: xv6-nano cooperative model USER LD of word 1622 succeeds unchanged."""
    from tools.glyph_isa_v2 import GlyphCPUv2, MODE_USER, BOX0_LO_ADDR, BOX0_HI_ADDR

    curproc_word = 1622
    arena_word = 310
    prog = [
        "LDI r2 %d" % curproc_word,
        "LD r3 r2",
        "LDI r2 %d" % arena_word,
        "ST r2 r3",
        "HALT",
    ]
    img = _build(prog)
    cpu = GlyphCPUv2(OM, cols_instrs=8)
    cpu.memory = [0] * 16384
    # Arm box0 around arena
    cpu.memory[BOX0_LO_ADDR >> 2] = arena_word * 4
    cpu.memory[BOX0_HI_ADDR >> 2] = (arena_word + 10) * 4
    cpu.memory[curproc_word] = CANARY
    cpu.mode = MODE_USER
    cpu.pc = (0, 0)
    cpu.running = True
    while cpu.running:
        cpu.step(img)

    assert cpu.faulted is False
    assert cpu.memory[arena_word] == CANARY

