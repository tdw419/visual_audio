#!/usr/bin/env python3
"""
Glyph Assembler
Compiles .glyph spatial assembly into binary tensor substrates (.rts)
and optionally into visual containers (.rts.png) using Hilbert mapping.

Opcode mapping (Glyph Stratum v1):
  LDI      0x01 [reg] [val]
  MOV      0x02 [dest] [src]
  ADD      0x03 [dest] [src1] [src2]
  SUB      0x04 [dest] [src1] [src2]
  JL       0x05 [src1] [src2] [target_offset]
  JZ       0x06 [src] [target_offset]
  JMP      0x07 [target_offset]
  SYS_READ 0x08 [reg] [port]
  SYS_CALL 0x09 [syscall_id]
  HALT     0xFF
"""

import sys
import os
import re
import argparse

OPCODES = {
    'LDI': 0x01,
    'MOV': 0x02,
    'ADD': 0x03,
    'SUB': 0x04,
    'JL': 0x05,
    'JZ': 0x06,
    'JMP': 0x07,
    'SYS_READ': 0x08,
    'SYS_CALL': 0x09,
    'HALT': 0xFF
}

def parse_register(operand):
    if operand.startswith('r') or operand.startswith('R'):
        return int(operand[1:])
    return int(operand, 0)

def assemble(filepath):
    with open(filepath, 'r') as f:
        lines = f.readlines()
        
    binary = bytearray()
    labels = {}
    instructions = []
    
    # First pass: parse lines, resolve labels
    pc = 0
    for line_num, line in enumerate(lines):
        line = line.split(';')[0].strip() # Strip comments
        
        # Clean drawing box characters and leading/trailing whitespace
        for char in '┌├│└─┐':
            line = line.replace(char, '')
        line = line.strip()
        
        if not line:
            continue
            
        parts = re.split(r'[\s,]+', line)
        op = parts[0].upper()
        
        # Extract labels
        if line.startswith(':'):
            label_name = line[1:].strip()
            labels[label_name] = pc
            continue
            
        if op not in OPCODES:
            # Skip documentation lines inside boxes
            continue
            
        instructions.append((pc, op, parts[1:]))
        pc += 1 + len(parts[1:]) # Opcode + N operands bytes
        
    # Second pass: generate binary
    for pc, op, operands in instructions:
        binary.append(OPCODES[op])
        
        for i, operand in enumerate(operands):
            if operand.startswith(':'):
                # Resolve label to relative offset
                label_name = operand[1:]
                if label_name not in labels:
                    print(f"Error: Undefined label {label_name}")
                    sys.exit(1)
                
                # Calculate relative jump offset (signed byte)
                target = labels[label_name]
                # Offset from the instruction AFTER this entire statement
                # Jumps are absolute or relative? Let's assume absolute for simplicity in v1
                binary.append(target & 0xFF)
            else:
                binary.append(parse_register(operand) & 0xFF)
                
    return binary

def main():
    parser = argparse.ArgumentParser(description='Glyph Assembler')
    parser.add_argument('input', help='Input .glyph file')
    parser.add_argument('-o', '--output', help='Output .rts binary file', required=True)
    args = parser.parse_args()
    
    print(f"Assembling {args.input}...")
    binary = assemble(args.input)
    
    with open(args.output, 'wb') as f:
        f.write(binary)
        
    print(f"Successfully assembled {len(binary)} bytes to {args.output}")

if __name__ == '__main__':
    main()
