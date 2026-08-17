#!/usr/bin/env python3
"""Debug assembler to see why VECTOR directive isn't working."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

import numpy as np

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
        print(f"Label: {label_name} -> ({x}, {y})")
    elif line.split()[0].upper() == "VECTOR":
        vector_directives.append(line)
        print(f"Vector directive: {line}")
    else:
        clean_instructions.append(line)
        x += 1
        if x >= 256:
            x = 0
            y += 1

print(f"\nFinal labels:")
for k, v in labels.items():
    print(f"  {k}: {v}")

print(f"\nVector directives: {vector_directives}")

# Process vector table
IVT_ROW = 254
for line in vector_directives:
    parts = line.split()
    irq_num = int(parts[1])
    target = parts[2]
    print(f"\nProcessing VECTOR {irq_num} {target}")
    
    if target.startswith(":"):
        if target not in labels:
            print(f"  ERROR: Undefined label {target}")
        else:
            hx, hy = labels[target]
            print(f"  Resolved to ({hx}, {hy})")
            mem[IVT_ROW, irq_num] = [hx, hy, 0, 0]
            print(f"  Set mem[{IVT_ROW}, {irq_num}] = [{hx}, {hy}, 0, 0]")
    else:
        print(f"  Direct coordinate (not implemented)")

print(f"\nFinal vector table at row {IVT_ROW}:")
for i in range(5):
    v = mem[IVT_ROW, i]
    print(f"  IRQ {i}: ({v[0]}, {v[1]})")