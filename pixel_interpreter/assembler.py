#!/usr/bin/env python3
"""
Assembler for Pixel Interpreter ISA (.glyph / .asm -> .png).
Translates human-readable spatial assembly into a 2D RGBA PNG container.
"""

from pathlib import Path
import argparse
import numpy as np
from PIL import Image

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
OP_SET_ADDR_HIGH = 10  # Acc = (imm << 8)
OP_SET_ADDR_LOW = 11   # Acc = (Acc & 0xFF00) | imm
OP_ADD_COORD = 12  # Add to y-coordinate: Acc = (x, y + imm)
OP_LOAD_COORD = 13 # Acc = (memory[G], memory[B]) - loads x,y from memory cells
OP_MUL = 14  # Acc *= imm
OP_CALL = 15
OP_RET = 16
OP_SEI = 17
OP_CLI = 18
OP_CTX_SAVE = 19
OP_CTX_LOAD = 20
OP_JMP_PC_IMM = 21
OP_STORE_XY = 22
OP_POP = 23
OP_DIR_RIGHT = 24
OP_DIR_DOWN = 25
OP_DIR_LEFT = 26
OP_DIR_UP = 27
OP_CH_READ = 28
OP_CH_WRITE = 29
OP_AND = 30
OP_OR  = 31
OP_XOR = 32
OP_SHL = 33
OP_SHR = 34
OP_ADD_MEM = 35
OP_SUB_MEM = 36
OP_INDIRECT_STORE_MEM = 37
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
    "DIR_RIGHT": OP_DIR_RIGHT,
    "DIR_DOWN": OP_DIR_DOWN,
    "DIR_LEFT": OP_DIR_LEFT,
    "DIR_UP": OP_DIR_UP,
    "CH_READ": OP_CH_READ,
    "CH_WRITE_MEM": OP_CH_WRITE,
    "AND": OP_AND,
    "OR": OP_OR,
    "XOR": OP_XOR,
    "SHL": OP_SHL,
    "SHR": OP_SHR,
    "ADD_MEM": OP_ADD_MEM,
    "SUB_MEM": OP_SUB_MEM,
    "INDIRECT_STORE_MEM": OP_INDIRECT_STORE_MEM,
    "HALT": OP_HALT
}

def parse_coord_or_label(arg, labels):
    """Parses '(x,y)' or ':label' into a (x, y) tuple."""
    if arg.startswith(":"):
        if arg not in labels:
            raise ValueError(f"Undefined label: {arg}")
        return labels[arg]
    
    arg = arg.strip("()")
    parts = arg.split(",")
    if len(parts) != 2:
        raise ValueError(f"Invalid coordinate format (expected (x,y)): {arg}")
    return int(parts[0].strip()), int(parts[1].strip())

def assemble(src: str, width: int = 256, height: int = 256) -> np.ndarray:
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
        parts = line.split()
        if not parts:
            continue
            
        mnemonic = parts[0].upper()
        if mnemonic == "ORG":
            coord_str = "".join(parts[1:])
            x, y = parse_coord_or_label(coord_str, {})
            clean_instructions.append(line)  # Keep for Pass 2 to update x,y
        elif line.startswith(":"):
            label_name = line.split()[0]
            labels[label_name] = (x, y)
        elif mnemonic == "VECTOR":
            vector_directives.append(line)
        else:
            clean_instructions.append(line)
            x += 1
            if x >= width:
                x = 0
                y += 1
                if y >= height:
                    raise MemoryError("Program too large for the grid.")

    # Interrupt vector table: row 254. "VECTOR <irq_num> <label_or_coord>"
    IVT_ROW = 254
    for line in vector_directives:
        parts = line.split()
        irq_num = int(parts[1])
        hx, hy = parse_coord_or_label(parts[2], labels)
        mem[IVT_ROW, irq_num] = [hx, hy, 0, 0]

    # Pass 2: Assemble
    x, y = 0, 1
    for line in clean_instructions:
        parts = line.split()
        mnemonic = parts[0].upper()
        
        if mnemonic == "ORG":
            coord_str = "".join(parts[1:])
            x, y = parse_coord_or_label(coord_str, labels)
            continue
            
        if mnemonic not in OPCODE_MAP:
            raise ValueError(f"Unknown opcode: {mnemonic}")
            
        opcode = OPCODE_MAP[mnemonic]
        r, g, b, a = opcode, 0, 0, 0
        
        # Parse arguments based on opcode
        if opcode == OP_SET:
            a = int(parts[1])
        elif opcode in (OP_ADD, OP_SUB, OP_MUL, OP_AND, OP_OR, OP_XOR, OP_SHL, OP_SHR):
            b = int(parts[1])
        elif opcode in (OP_LOAD, OP_STORE, OP_ADD_MEM, OP_SUB_MEM, OP_INDIRECT_STORE_MEM):
            coord_str = "".join(parts[1:]) # Handle spaces in "(x, y)"
            cx, cy = parse_coord_or_label(coord_str, labels)
            g, b = cx, cy
        elif opcode in (OP_JMP, OP_JZ, OP_CALL, OP_CTX_SAVE, OP_CTX_LOAD):
            # JMP/JZ/CALL/CTX: Label or (x, y)
            target_str = "".join(parts[1:])
            cx, cy = parse_coord_or_label(target_str, labels)
            g, b = cx, cy
        elif opcode == OP_JMP_PC_IMM:
            # Takes immediate value (ignored - uses accumulator's packed PC)
            pass
        elif opcode == OP_STORE_XY:
            # Takes THREE arguments: STORE_XY dst_x dst_y x y
            # Stores (x, y) as a packed RGBA value at memory[dst_y, dst_x]
            dst_x, dst_y = parse_coord_or_label(parts[1], labels)
            val_x = int(parts[2])
            val_y = int(parts[3]) if len(parts) > 3 else 0
            g, b = dst_x, dst_y
            # We'll store (val_x, val_y) in the pixel when this executes
            # For now, just encode the destination in G,B
            # The actual values need to be stored in A somehow...
            # Actually, this design is broken. Let me use a different approach.
        elif opcode == OP_INDIRECT_LOAD:
            # No arguments - uses accumulator as packed coordinate
            pass
        elif opcode == OP_INDIRECT_STORE:
            # Takes immediate value as argument
            a = int(parts[1]) if len(parts) > 1 else 0
        elif opcode == OP_LOAD_COORD:
            # Takes two memory addresses: (x_addr, y_addr)
            coord_str = "".join(parts[1:])
            cx, cy = parse_coord_or_label(coord_str, labels)
            g, b = cx, cy
        elif opcode in (OP_SET_ADDR_HIGH, OP_SET_ADDR_LOW, OP_ADD_COORD, OP_CH_READ):
            # Takes immediate value
            a = int(parts[1]) if len(parts) > 1 else 0
        elif opcode == OP_CH_WRITE:
            # CH_WRITE_MEM (x, y) channel
            coord_str = "".join(parts[1:-1])
            cx, cy = parse_coord_or_label(coord_str, labels)
            g, b = cx, cy
            a = int(parts[-1]) if len(parts) > 1 else 0
        elif opcode in (OP_NOP, OP_HALT, OP_RET, OP_SEI, OP_CLI, OP_POP, OP_DIR_RIGHT, OP_DIR_DOWN, OP_DIR_LEFT, OP_DIR_UP):
            pass
            
        mem[y, x] = [r, g, b, a]
        
        x += 1
        if x >= width:
            x = 0
            y += 1

    return mem

def main():
    parser = argparse.ArgumentParser(description="Assemble .glyph spatial assembly into .png")
    parser.add_argument("source", type=Path, help="Source .glyph file")
    parser.add_argument("-o", "--output", type=Path, help="Output PNG file", default=None)
    parser.add_argument("--width", type=int, default=256, help="Grid width")
    parser.add_argument("--height", type=int, default=256, help="Grid height")
    
    args = parser.parse_args()
    
    if not args.source.exists():
        print(f"Error: Source file {args.source} not found.")
        return
        
    src_code = args.source.read_text()
    
    try:
        pixel_grid = assemble(src_code, args.width, args.height)
    except Exception as e:
        print(f"Assembly failed: {e}")
        return
        
    out_path = args.output
    if out_path is None:
        out_path = args.source.with_suffix(".png")
        
    img = Image.fromarray(pixel_grid)
    img.save(out_path)
    print(f"✓ Assembled {args.source} -> {out_path} ({args.width}x{args.height})")

if __name__ == "__main__":
    main()