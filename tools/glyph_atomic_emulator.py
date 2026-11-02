#!/usr/bin/env python3
"""
Glyph-Atomic Spatial Emulator (Format 3 Native Execution)

This emulator fulfills the "Fully Native Glyph-Based OS" vision.
It does not execute dense pixels. It executes human-readable font glyphs.
The screen UI *is* the executable code.
"""

import sys
import os
import numpy as np
from PIL import Image, ImageDraw, ImageFont

class GlyphAtomicCPU:
    def __init__(self):
        self.registers = [0] * 8
        self.pc = (0, 0)
        # We use a 32x32 block for high legibility on the glass
        self.tile_size = 32
        self.image = None
        
        # Build an internal dictionary of glyphs by rendering them
        self.glyph_templates = {}
        self.token_to_img = {}
        
        # Try to load a default font, otherwise use PIL's basic font
        try:
            self.font = ImageFont.truetype("DejaVuSansMono.ttf", 20)
        except:
            self.font = ImageFont.load_default()
            
        self._build_glyph_templates()
        
    def _build_glyph_templates(self):
        # We render these text strings into 32x32 tiles to act as our "Font-Atomic" instruction set.
        instructions = [
            "LDI", "ADD", "SUB", "PRT", "HLT", "JMP", "JZ",
            "0", "1", "2", "3", "4", "5", "6", "7", "8", "9",
            "r0", "r1", "r2", "r3", "r4", "r5", "r6", "r7"
        ]
        
        for inst in instructions:
            # Create a blank black tile
            img = Image.new('L', (self.tile_size, self.tile_size), color=0)
            d = ImageDraw.Draw(img)
            
            # Draw the text glyph centered-ish
            d.text((4, 4), inst, fill=255, font=self.font)
            
            # Store the raw byte signature of this visual glyph
            self.glyph_templates[img.tobytes()] = inst
            self.token_to_img[inst] = img

    def compile_to_glass(self, assembly_lines, output_path="glass_stratum.png"):
        """Compiles text assembly into a literal visual 2D grid of readable glyphs."""
        width = 10 * self.tile_size
        height = len(assembly_lines) * self.tile_size
        img = Image.new('L', (width, height), color=0)
        
        for y, line in enumerate(assembly_lines):
            tokens = line.strip().split()
            for x, token in enumerate(tokens):
                if token in self.token_to_img:
                    tile_img = self.token_to_img[token]
                    img.paste(tile_img, (x * self.tile_size, y * self.tile_size))
                
        img.save(output_path)
        print(f"✓ Compiled Glyph Assembly to {output_path} (Human-Readable UI Matrix)")
        return output_path
        
    def decode_tile(self, x, y):
        """Reads a tile from the screen and matches it against known visual font glyphs."""
        # Check bounds
        if x * self.tile_size >= self.image.width or y * self.tile_size >= self.image.height:
            return None
            
        box = (x * self.tile_size, y * self.tile_size, (x+1) * self.tile_size, (y+1) * self.tile_size)
        tile = self.image.crop(box)
        signature = tile.tobytes()
        
        return self.glyph_templates.get(signature, None)

    def execute_glass(self, image_path):
        """Executes the program directly from the human-readable font image."""
        self.image = Image.open(image_path).convert('L')
        self.pc = (0, 0)
        
        print(f"\n--- BEGIN GLYPH-ATOMIC EXECUTION ({image_path}) ---")
        
        step = 0
        while True:
            # Fetch the visual tile at the current 2D Program Counter
            opcode = self.decode_tile(self.pc[0], self.pc[1])
            
            if opcode is None:
                # Blank tile or out of bounds, step to next line
                self.pc = (0, self.pc[1] + 1)
                if self.pc[1] * self.tile_size >= self.image.height:
                    break
                continue
                
            print(f"Step {step:02d} | PC:{self.pc} | Vision Match: [{opcode}]")
            step += 1
            
            if opcode == "HLT":
                print(" > HALT ENCOUNTERED")
                break
                
            elif opcode == "LDI":
                reg_glyph = self.decode_tile(self.pc[0] + 1, self.pc[1])
                val_glyph = self.decode_tile(self.pc[0] + 2, self.pc[1])
                reg_idx = int(reg_glyph.replace('r', ''))
                val = int(val_glyph)
                self.registers[reg_idx] = val
                
                # Advance PC to next line
                self.pc = (0, self.pc[1] + 1)
                
            elif opcode == "ADD":
                reg_glyph1 = self.decode_tile(self.pc[0] + 1, self.pc[1])
                reg_glyph2 = self.decode_tile(self.pc[0] + 2, self.pc[1])
                r1 = int(reg_glyph1.replace('r', ''))
                r2 = int(reg_glyph2.replace('r', ''))
                self.registers[r1] += self.registers[r2]
                self.pc = (0, self.pc[1] + 1)
                
            elif opcode == "PRT":
                reg_glyph = self.decode_tile(self.pc[0] + 1, self.pc[1])
                r_idx = int(reg_glyph.replace('r', ''))
                print(f" > TERMINAL OUTPUT: {self.registers[r_idx]}")
                self.pc = (0, self.pc[1] + 1)
                
            elif opcode == "JMP":
                # Geometric branch
                y_target = int(self.decode_tile(self.pc[0] + 1, self.pc[1]))
                print(f" > BRANCHING SPATIALLY to Y={y_target}")
                self.pc = (0, y_target)
                
            else:
                self.pc = (0, self.pc[1] + 1)
                
        print(f"--- END GLYPH-ATOMIC EXECUTION ---")
        print(f"Final CPU State (Registers): {self.registers}")


if __name__ == '__main__':
    # A program that loads values, adds them, and prints.
    # Note: This text is rendered visually to a PNG, and the CPU reads the PNG!
    glyph_program = [
        "LDI r0 5",
        "LDI r1 4",
        "ADD r0 r1",
        "PRT r0",
        "HLT"
    ]
    
    cpu = GlyphAtomicCPU()
    
    # 1. Compile text to a visual UI element (PNG)
    img_path = "glass_stratum_demo.png"
    cpu.compile_to_glass(glyph_program, img_path)
    
    # 2. Execute directly from the visual UI element
    cpu.execute_glass(img_path)
