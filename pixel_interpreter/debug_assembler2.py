#!/usr/bin/env python3
"""Debug assembler with actual PNG save."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

import numpy as np
from PIL import Image

# Import assembler's parse_coord_or_label function
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

# Read source
source = Path("scheduler_fixed.glyph").read_text()

mem = np.zeros((256, 256, 4), dtype=np.uint8)

lines = []
for line in source.splitlines():
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
    elif line.split()[0].upper() == "VECTOR":
        vector_directives.append(line)
    else:
        clean_instructions.append(line)
        x += 1
        if x >= 256:
            x = 0
            y += 1

# Pass 2: Assemble instructions
x, y = 0, 1
for line in clean_instructions:
    parts = line.split()
    mnemonic = parts[0].upper()
    
    # Simplified assembly - just track x
    x += 1
    if x >= 256:
        x = 0
        y += 1

# Process vector table AFTER instruction assembly
IVT_ROW = 254
print(f"\nSetting vector table at row {IVT_ROW}:")
for line in vector_directives:
    parts = line.split()
    irq_num = int(parts[1])
    target = parts[2]
    
    if target.startswith(":"):
        hx, hy = labels[target]
        print(f"  IRQ {irq_num}: {target} -> ({hx}, {hy})")
        mem[IVT_ROW, irq_num] = [hx, hy, 0, 0]
        print(f"    mem[{IVT_ROW}, {irq_num}] = {mem[IVT_ROW, irq_num]}")

# Save PNG
img = Image.fromarray(mem)
img.save("/tmp/scheduler_debug_vt.png")
print(f"\nSaved to /tmp/scheduler_debug_vt.png")

# Verify
v = mem[IVT_ROW, 1]
print(f"\nVerification: mem[{IVT_ROW}, 1] = {v}")

# Read back and check
img_check = Image.open("/tmp/scheduler_debug_vt.png")
mem_check = np.asarray(img_check, dtype=np.uint8)
v_check = mem_check[IVT_ROW, 1]
print(f"Read back: mem_check[{IVT_ROW}, 1] = {v_check}")