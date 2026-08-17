#!/usr/bin/env python3
"""Add debug output to assembler."""

import sys
import argparse
import numpy as np
from PIL import Image
from pathlib import Path

# Opcodes
OP_NOP   = 0
OP_SET   = 1
OP_ADD   = 2
OP_SUB   = 3
OP_LOAD  = 4
OP_STORE = 5
OP_JMP   = 6
OP_JZ    = 7
OP_INDIRECT_LOAD = 8
OP_INDIRECT_STORE = 9
OP_SET_ADDR_HIGH = 10
OP_SET_ADDR_LOW = 11
OP_ADD_COORD = 12
OP_LOAD_COORD = 13
OP_MUL = 14
OP_CALL = 15
OP_RET = 16
OP_SEI = 17
OP_CLI = 18
OP_CTX_SAVE = 19
OP_CTX_LOAD = 20
OP_JMP_PC_IMM = 21
OP_STORE_XY = 22
OP_POP = 23
OP_HALT  = 255

OPCODE_MAP = {
    "NOP": OP_NOP,
    "SET": OP_SET,
    "ADD": OP_ADD,
    "SUB": OP_SUB,
    "MUL": OP_MUL,
    "LOAD": OP_LOAD,
    "STORE": OP_STORE,
    "JMP": OP_JMP,
    "JZ": OP_JZ,
    "INDIRECT_LOAD": OP_INDIRECT_LOAD,
    "INDIRECT_STORE": OP_INDIRECT_STORE,
    "SET_ADDR_HIGH": OP_SET_ADDR_HIGH,
    "SET_ADDR_LOW": OP_SET_ADDR_LOW,
    "ADD_COORD": OP_ADD_COORD,
    "LOAD_COORD": OP_LOAD_COORD,
    "CALL": OP_CALL,
    "RET": OP_RET,
    "SEI": OP_SEI,
    "CLI": OP_CLI,
    "CTX_SAVE": OP_CTX_SAVE,
    "CTX_LOAD": OP_CTX_LOAD,
    "JMP_PC_IMM": OP_JMP_PC_IMM,
    "STORE_XY": OP_STORE_XY,
    "POP": OP_POP,
    "HALT": OP_HALT
}

def parse_coord_or_label(arg, labels):
    if arg.startswith(":"):
        if arg not in labels:
            raise ValueError(f"Undefined label: {arg}")
        return labels[arg]
    
    arg = arg.strip("()")
    parts = arg.split(",")
    if len(parts) != 2:
        raise ValueError(f"Invalid coordinate format (expected (x,y)): {arg}")
    return int(parts[0].strip()), int(parts[1].strip())

def assemble_debug(src: str, width: int = 256, height: int = 256) -> np.ndarray:
    mem = np.zeros((height, width, 4), dtype=np.uint8)
    
    # State row (y=0)
    mem[0, 0] = [0, 1, 0, 0]  # PC at (0, 1)
    mem[0, 1] = [0, 0, 0, 0]  # Acc = 0
    mem[0, 2] = [0, 0, 0, 0]  # ZF = 0

    lines = []
    for line in src.splitlines():
        line = line.split(";")[0].strip()
        if line:
            lines.append(line)
            
    # Pass 1: Resolve Labels
    labels = {}
    x, y = 0, 1
    
    clean_instructions = []
    vector_directives = []
    for line in lines:
        if line.startswith(":"):
            label_name = line.split()[0]
            labels[label_name] = (x, y)
            print(f"DEBUG Pass1: Label {label_name} at ({x}, {y})")
        elif line.split()[0].upper() == "VECTOR":
            vector_directives.append(line)
        else:
            clean_instructions.append(line)
            x += 1
            if x >= width:
                x = 0
                y += 1
                if y >= height:
                    raise MemoryError("Program too large for the grid.")

    # Interrupt vector table
    IVT_ROW = 254
    print(f"\nDEBUG: Processing {len(vector_directives)} vector directives")
    for line in vector_directives:
        parts = line.split()
        irq_num = int(parts[1])
        hx, hy = parse_coord_or_label(parts[2], labels)
        mem[IVT_ROW, irq_num] = [hx, hy, 0, 0]
        print(f"DEBUG: VECTOR {irq_num} -> ({hx}, {hy}) stored at mem[{IVT_ROW}, {irq_num}] = {mem[IVT_ROW, irq_num]}")

    # Pass 2: Assemble
    x, y = 0, 1
    for i, line in enumerate(clean_instructions):
        parts = line.split()
        mnemonic = parts[0].upper()
        if mnemonic not in OPCODE_MAP:
            raise ValueError(f"Unknown opcode: {mnemonic}")
            
        opcode = OPCODE_MAP[mnemonic]
        r, g, b, a = opcode, 0, 0, 0
        
        # Simplified: just write opcode
        mem[y, x] = [r, g, b, a]
        
        x += 1
        if x >= width:
            x = 0
            y += 1

    print(f"\nDEBUG: Final vector table at row {IVT_ROW}:")
    for i in range(5):
        v = mem[IVT_ROW, i]
        print(f"  IRQ {i}: ({v[0]}, {v[1]})")

    return mem

if __name__ == "__main__":
    src = Path("scheduler_fixed.glyph").read_text()
    mem = assemble_debug(src, 256, 256)
    
    img = Image.fromarray(mem)
    img.save("/tmp/scheduler_debug_full.png")
    print(f"\nSaved to /tmp/scheduler_debug_full.png")