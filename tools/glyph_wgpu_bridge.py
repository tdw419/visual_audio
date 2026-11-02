"""
Bridge from GlyphAssemblerV2's pixel-encoded program to the numeric
instruction buffer tools/glyph_coordinator.wgsl expects, plus a pure-Python
mirror of that shader's exact opcode logic.

Why the mirror exists: GPU compute submission hangs in this sandbox
(device.queue.submit() never completes — confirmed 2026-08-16, same as
the earlier GPU-compute-sandbox finding). That means the actual WGSL
execution path cannot be tested here. What CAN be verified without a
working GPU adapter:
  1. The WGSL is syntactically/structurally valid (`naga glyph_coordinator.wgsl`).
  2. The decode from assembled pixels to the numeric Instr buffer is correct.
  3. The *semantics* the shader implements produce the same results as
     the already-verified GlyphCPUv2 Python interpreter, by running an
     opcode-for-opcode mirror of the shader's loop in Python against the
     same decoded buffer.

(2) and (3) together are real evidence the port is correct; they are not
a substitute for (4) actually dispatching on a GPU, which remains
unverified until this sandbox's GPU restriction is resolved or this runs
on unblocked hardware.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from glyph_isa_v2 import GlyphAssemblerV2, OpcodeMapV2, INSTR_WIDTH, _unpack_immediate

# Must match the `const OP_*` table in tools/glyph_coordinator.wgsl exactly.
OPCODE_ID = {
    'HALT': 0,
    'LDI': 1,
    'ADD': 2,
    'SUB': 3,
    'CMP': 4,
    'JMP': 5,
    'JZ': 6,
    'LD': 7,
    'ST': 8,
    'CALL': 9,
    'RET': 10,
    'JMPR': 11,
    'CALLR': 12,
}

UNUSED_REGISTER = 0xFF


def assemble_with_labels(glyph_path, assembler, cols_instrs=64):
    """Same label-resolution preprocessing used by the test harnesses."""
    with open(glyph_path, "r") as f:
        raw_lines = [line.strip() for line in f if line.strip() and not line.startswith('#')]

    labels = {}
    instr_count = 0
    for line in raw_lines:
        if line.startswith(':'):
            labels[line.split()[0]] = instr_count
        else:
            instr_count += 1

    resolved = []
    for line in raw_lines:
        if line.startswith(':'):
            continue
        for label, idx in labels.items():
            if label in line:
                col, row = idx % cols_instrs, idx // cols_instrs
                line = line.replace(label, f"{col},{row}")
        resolved.append(line)

    pixels = assembler.assemble(resolved, width_instrs=cols_instrs)
    return pixels, len(resolved), labels


def decode_program(pixels, opcode_map, n_instrs, cols_instrs=64):
    """Re-decode the assembled pixel image into the numeric Instr buffer
    the WGSL shader consumes: (opcode_id, rs1, rs2, rd, imm) per
    instruction, in linear program order (row-major, matching how PC
    advances one instruction at a time in GlyphCPUv2.step)."""
    instrs = []
    height, width, _ = pixels.shape
    for idx in range(n_instrs):
        row = idx // cols_instrs
        col = idx % cols_instrs
        base_x = col * INSTR_WIDTH

        opcode_px = tuple(int(v) for v in pixels[row, base_x])
        reg_px = tuple(int(v) for v in pixels[row, base_x + 1])
        low_px = tuple(int(v) for v in pixels[row, base_x + 2])
        high_px = tuple(int(v) for v in pixels[row, base_x + 3])

        mnemonic = opcode_map.rgb_to_opcode(opcode_px)
        if mnemonic is None:
            raise ValueError(f"Unknown opcode color {opcode_px} at instruction {idx}")
        if mnemonic not in OPCODE_ID:
            raise ValueError(
                f"'{mnemonic}' has no numeric id for the WGSL bridge — "
                f"glyph_coordinator.wgsl only implements {sorted(OPCODE_ID)}"
            )

        rs1, rs2, rd = reg_px
        rs1 = -1 if rs1 == UNUSED_REGISTER else rs1
        rs2 = -1 if rs2 == UNUSED_REGISTER else rs2
        rd = -1 if rd == UNUSED_REGISTER else rd
        imm = _unpack_immediate(low_px, high_px)

        # JMP/JZ/CALL pack (col,row) into imm as (row<<16)|col at assemble
        # time, where col/row are already *instruction* indices (the
        # label-resolution preprocessor emits "col,row" directly from
        # instr_count, not pixel coordinates — GlyphAssemblerV2.assemble
        # stores that x,y pair verbatim into imm without scaling). The
        # shader's `imm` field for these needs to be the linear
        # instruction index (its `pc`), so no INSTR_WIDTH scaling here.
        if mnemonic in ('JMP', 'JZ', 'CALL'):
            tx = imm & 0xFFFF
            ty = (imm >> 16) & 0xFFFF
            imm = ty * cols_instrs + tx

        instrs.append({
            'opcode': OPCODE_ID[mnemonic],
            'rs1': rs1,
            'rs2': rs2,
            'rd': rd,
            'imm': imm,
        })
    return instrs


def run_shader_model(program, data_memory, max_steps=20000, stack_base=250, stack_size=64):
    """Pure-Python line-for-line mirror of glyph_coordinator.wgsl's main()
    loop. Used only to verify the WGSL's *semantics* without a working
    GPU adapter — this is not the WGSL executing, it's a cross-check that
    what the WGSL says it does matches what we intend."""
    registers = [0] * 32
    call_stack = [0] * stack_size
    pc = 0
    sp = stack_size  # index into call_stack; starts empty, mirrors WGSL's sp = STACK_BASE
    halted = False
    steps = 0

    def read_reg(i):
        return registers[i] if 0 <= i < 32 else 0

    def write_reg(i, v):
        if 0 <= i < 32:
            registers[i] = v

    while steps < max_steps and 0 <= pc < len(program):
        instr = program[pc]
        opcode = instr['opcode']
        next_pc = pc + 1

        if opcode == OPCODE_ID['HALT']:
            halted = True
            break
        elif opcode == OPCODE_ID['LDI']:
            write_reg(instr['rd'], instr['imm'])
        elif opcode == OPCODE_ID['ADD']:
            write_reg(instr['rd'], read_reg(instr['rd']) + read_reg(instr['rs2']))
        elif opcode == OPCODE_ID['SUB']:
            write_reg(instr['rd'], read_reg(instr['rd']) - read_reg(instr['rs2']))
        elif opcode == OPCODE_ID['CMP']:
            write_reg(0, 1 if read_reg(instr['rd']) == read_reg(instr['rs2']) else 0)
        elif opcode == OPCODE_ID['JMP']:
            next_pc = instr['imm']
        elif opcode == OPCODE_ID['JZ']:
            if read_reg(0) != 0:
                next_pc = instr['imm']
        elif opcode == OPCODE_ID['LD']:
            addr = read_reg(instr['rs2'])
            if 0 <= addr < len(data_memory):
                write_reg(instr['rd'], data_memory[addr])
        elif opcode == OPCODE_ID['ST']:
            addr = read_reg(instr['rs1'])
            if 0 <= addr < len(data_memory):
                data_memory[addr] = read_reg(instr['rs2'])
        elif opcode == OPCODE_ID['CALL']:
            sp -= 1
            if 0 <= sp < stack_size:
                call_stack[sp] = next_pc
            next_pc = instr['imm']
        elif opcode == OPCODE_ID['RET']:
            if 0 <= sp < stack_size:
                next_pc = call_stack[sp]
            sp += 1
        elif opcode == OPCODE_ID['JMPR']:
            next_pc = read_reg(instr['rd'])
        elif opcode == OPCODE_ID['CALLR']:
            sp -= 1
            if 0 <= sp < stack_size:
                call_stack[sp] = next_pc
            next_pc = read_reg(instr['rd'])

        pc = next_pc
        steps += 1

    return {'registers': registers, 'data_memory': data_memory, 'pc': pc,
            'steps': steps, 'halted': halted}
