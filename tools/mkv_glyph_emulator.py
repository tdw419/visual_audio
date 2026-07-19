#!/usr/bin/env python3
"""
Spatial Glyph Emulator — Execute code directly from visual audio pixels.

The MKV file acts as ROM/VRAM. Each pixel color is a glyph opcode.
The Program Counter is a 2D coordinate (x, y), not a 1D address.

Architecture:
- Pixel → Opcode: RGB color maps to glyph instruction (via wordbase.db)
- Spatial PC: Program counter = (x, y) coordinate on image
- Registers: r0-r7 (integer registers)
- Memory: 1KB addressable memory
- Output: stdout for print operations

Proof of concept: Semantic visual audio programming.
"""

import sys
from pathlib import Path
import numpy as np
from typing import List, Tuple, Dict, Optional
from PIL import Image

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.pixel_tokenizer import PixelTokenizer
from tools.wordbase import WordbaseManager


class OpcodeMap:
    """
    Map visual audio colors to glyph opcodes.

    This creates a tiny instruction set where each opcode has a specific
    color. The color is derived from the wordbase.db entry for that opcode name.
    """

    # Core opcodes and their wordbase word names
    OPCODES = {
        'LDI': 'load',         # LDI r, imm: Load immediate into register
        'ADD': 'add',          # ADD r1, r2: r1 = r1 + r2
        'SUB': 'subtract',     # SUB r1, r2: r1 = r1 - r2
        'MUL': 'multiply',     # MUL r1, r2: r1 = r1 * r2
        'JMP': 'jump',         # JMP x, y: Jump to coordinate
        'JZ': 'jump_if',       # JZ x, y: Jump if r0 == 0
        'CMP': 'compare',      # CMP r1, r2: Set r0 = (r1 == r2 ? 1 : 0)
        'MOV': 'move',         # MOV r1, r2: r1 = r2
        'PRT': 'print',        # PRT r: Print register value
        'HALT': 'stop',        # Halt execution
    }

    def __init__(self, wordbase_path: Optional[Path] = None):
        """
        Initialize opcode map with wordbase connection.

        Args:
            wordbase_path: Path to wordbase database
        """
        if wordbase_path is None:
            wordbase_path = Path(__file__).parent.parent / "db" / "wordbase.db"
        self.wordbase = WordbaseManager(wordbase_path)
        self._opcode_to_rgb: Dict[str, Tuple[int, int, int]] = {}
        self._rgb_to_opcode: Dict[Tuple[int, int, int], str] = {}

        self._build_maps()

    def _build_maps(self):
        """Build bidirectional opcode↔RGB mappings from wordbase."""
        for opcode, word in self.OPCODES.items():
            result = self.wordbase.get_word(word)
            if result:
                # Parse color hex (e.g., "#FF5733" → (255, 87, 51))
                color_hex = result['color_hex']
                if color_hex and color_hex.startswith('#'):
                    rgb_tuple = tuple(int(color_hex[i:i+2], 16) for i in (1, 3, 5))
                    rgb = (rgb_tuple[0], rgb_tuple[1], rgb_tuple[2])
                    self._opcode_to_rgb[opcode] = rgb
                    self._rgb_to_opcode[rgb] = opcode
                else:
                    # Fallback: generate deterministic RGB from opcode name
                    rgb = self._deterministic_rgb(opcode)
                    self._opcode_to_rgb[opcode] = rgb
                    self._rgb_to_opcode[rgb] = opcode
            else:
                # Fallback: generate deterministic RGB
                rgb = self._deterministic_rgb(opcode)
                self._opcode_to_rgb[opcode] = rgb
                self._rgb_to_opcode[rgb] = opcode

    def _deterministic_rgb(self, opcode: str) -> Tuple[int, int, int]:
        """Generate deterministic RGB from opcode string."""
        hash_val = sum(ord(c) * (i + 1) for i, c in enumerate(opcode))
        r = (hash_val * 7) % 256
        g = (hash_val * 13) % 256
        b = (hash_val * 17) % 256
        return (r, g, b)

    def opcode_to_rgb(self, opcode: str) -> Tuple[int, int, int]:
        """Get RGB color for an opcode."""
        return self._opcode_to_rgb.get(opcode, (0, 0, 0))

    def rgb_to_opcode(self, rgb: Tuple[int, int, int]) -> Optional[str]:
        """Get opcode from RGB color."""
        # Ensure rgb is a tuple of 3 ints
        rgb_tuple = (int(rgb[0]), int(rgb[1]), int(rgb[2]))
        return self._rgb_to_opcode.get(rgb_tuple)

    def get_all_opcodes(self) -> List[str]:
        """Get list of all opcodes."""
        return list(self.OPCODES.keys())

    def close(self):
        """Close wordbase connection."""
        self.wordbase.close()


class GlyphAssembler:
    """
    Assemble glyph assembly text to 2D pixel image.

    Input:
        LDI r0, 5
        LDI r1, 3
        ADD r0, r1
        PRT r0
        HALT

    Output:
        2D image where each pixel encodes one instruction operand
    """

    def __init__(self, opcode_map: OpcodeMap):
        self.opcode_map = opcode_map

    def parse_line(self, line: str) -> Optional[List[str]]:
        """
        Parse a single assembly line.

        Args:
            line: Assembly text (e.g., "LDI r0 5" or "JZ 10,1")

        Returns:
            List of tokens or None if comment/empty
        """
        line = line.strip()

        # Skip comments and empty lines
        if not line or line.startswith('#'):
            return None

        tokens = []
        current_token = ""

        i = 0
        while i < len(line):
            char = line[i]

            if char == ',':
                # Keep comma as part of current token (for coordinates)
                current_token += char
                i += 1
            elif char in (' ', '\t'):
                # Whitespace ends current token
                if current_token:
                    tokens.append(current_token)
                    current_token = ""
                i += 1
            else:
                current_token += char
                i += 1

        # Don't forget last token
        if current_token:
            tokens.append(current_token)

        return tokens

    def _is_coordinate(self, token: str) -> bool:
        """
        Check if a token looks like a coordinate.

        Args:
            token: Token string (e.g., "10,1" or "10, 1")

        Returns:
            True if token is a coordinate pattern
        """
        # Check for "x,y" or "x, y" pattern (where x and y are numbers)
        if ',' in token:
            parts = token.split(',')
            if len(parts) == 2:
                try:
                    int(parts[0].strip())
                    int(parts[1].strip())
                    return True
                except ValueError:
                    pass
        return False

    def _parse_coordinate(self, token: str) -> Tuple[int, int]:
        """
        Parse coordinate from token.

        Args:
            token: Token string (e.g., "10,1")

        Returns:
            Tuple of (x, y) coordinates
        """
        parts = token.split(',')
        return (int(parts[0].strip()), int(parts[1].strip()))

    def assemble_to_pixels(self, assembly: List[str], width: int = 32) -> np.ndarray:
        """
        Assemble assembly program to 2D pixel image.

        Args:
            assembly: List of assembly lines
            width: Image width in pixels

        Returns:
            NumPy array shape (height, width, 3) of RGB pixels
        """
        # Parse all instructions
        all_tokens = []
        for line in assembly:
            tokens = self.parse_line(line)
            if tokens:
                all_tokens.extend(tokens)

        # Calculate height needed
        height = (len(all_tokens) + width - 1) // width

        # Create empty image
        image = np.zeros((height, width, 3), dtype=np.uint8)

        # Fill image with opcodes and operands
        for i, token in enumerate(all_tokens):
            x = i % width
            y = i // width

            # Check if token is an opcode
            rgb = None
            opcode = self.opcode_map.rgb_to_opcode((0, 0, 0))  # Placeholder
            if token in self.opcode_map.get_all_opcodes():
                rgb = self.opcode_map.opcode_to_rgb(token)
            elif token.startswith('r'):  # Register (r0-r7)
                # Encode register as shade of gray
                reg_num = int(token[1:])
                gray_val = 50 + reg_num * 25
                rgb = (gray_val, gray_val, gray_val)
            elif self._is_coordinate(token):
                # Encode coordinate: r=0, g=x+1, b=y+1 (offset by 1 to handle 0)
                x_coord, y_coord = self._parse_coordinate(token)
                rgb = (0, min(255, x_coord + 1), min(255, y_coord + 1))
            else:
                # Try to parse as number
                try:
                    num_val = int(token)
                    # Encode as blue channel (offset by 1 to handle 0)
                    rgb = (0, 0, min(255, num_val + 1))
                except ValueError:
                    # Unknown token: encode as white
                    rgb = (255, 255, 255)

            image[y, x] = rgb

        return image


class GlyphCPU:
    """
    Spatial Glyph CPU emulator.

    Reads instructions spatially from a 2D pixel image and executes them.
    """

    def __init__(self, opcode_map: OpcodeMap):
        self.opcode_map = opcode_map
        self.registers = [0] * 8  # r0-r7
        self.memory = [0] * 1024  # 1KB memory
        self.pc = (0, 0)  # Program counter as (x, y) coordinate
        self.running = False
        self.output = []

    def reset(self):
        """Reset CPU state."""
        self.registers = [0] * 8
        self.memory = [0] * 1024
        self.pc = (0, 0)
        self.running = False
        self.output = []

    def get_pixel(self, image: np.ndarray, x: int, y: int) -> Tuple[int, int, int]:
        """Get pixel value at (x, y) coordinate."""
        height, width, _ = image.shape
        if x >= width or y >= height:
            return (0, 0, 0)  # Out of bounds
        return tuple(image[y, x])

    def fetch_operand(self, image: np.ndarray) -> Tuple[str, any]:
        """
        Fetch next operand from current PC position and advance.

        Returns:
            (type, value) where type is 'reg', 'imm', 'coord', or 'unknown'
        """
        x, y = self.pc
        pixel = self.get_pixel(image, x, y)

        # Advance PC
        x += 1
        self.pc = (x, y)

        r, g, b = pixel

        # Check for immediate value (only blue channel, r=0, g=0, b>0) - check FIRST
        if r == 0 and g == 0 and b > 0:
            # Subtract 1 to handle offset encoding (0 is stored as 1)
            return ('imm', b - 1)

        # Check for coordinate (r=0, g>0, b>0) - subtract 1 from each for offset
        if r == 0 and g > 0 and b > 0:
            return ('coord', (g - 1, b - 1))

        # Check for register (grayscale: r≈g≈b)
        if abs(r - g) < 10 and abs(g - b) < 10 and r > 40:
            reg_num = (r - 50) // 25
            if 0 <= reg_num <= 7:
                return ('reg', reg_num)

        return ('unknown', pixel)

    def execute_instruction(self, image: np.ndarray):
        """
        Fetch and execute one instruction from image at PC.

        Args:
            image: 2D pixel image containing the program

        Returns:
            True if execution continues, False if halted
        """
        # Fetch opcode
        x, y = self.pc
        opcode_pixel = self.get_pixel(image, x, y)
        opcode = self.opcode_map.rgb_to_opcode(opcode_pixel)

        # Advance PC past opcode
        x += 1
        self.pc = (x, y)

        if opcode is None:
            # Unknown opcode: halt
            self.running = False
            return False

        # Fetch operands based on opcode
        if opcode == 'LDI':
            reg_type, reg_num = self.fetch_operand(image)
            imm_type, imm_val = self.fetch_operand(image)
            if reg_type == 'reg':
                self.registers[reg_num] = int(imm_val)

        elif opcode == 'ADD':
            reg1_type, reg1 = self.fetch_operand(image)
            reg2_type, reg2 = self.fetch_operand(image)
            if reg1_type == 'reg' and reg2_type == 'reg':
                self.registers[reg1] = int(self.registers[reg1]) + int(self.registers[reg2])

        elif opcode == 'SUB':
            reg1_type, reg1 = self.fetch_operand(image)
            reg2_type, reg2 = self.fetch_operand(image)
            if reg1_type == 'reg' and reg2_type == 'reg':
                self.registers[reg1] = int(self.registers[reg1]) - int(self.registers[reg2])

        elif opcode == 'MUL':
            reg1_type, reg1 = self.fetch_operand(image)
            reg2_type, reg2 = self.fetch_operand(image)
            if reg1_type == 'reg' and reg2_type == 'reg':
                self.registers[reg1] = int(self.registers[reg1]) * int(self.registers[reg2])

        elif opcode == 'CMP':
            reg1_type, reg1 = self.fetch_operand(image)
            reg2_type, reg2 = self.fetch_operand(image)
            if reg1_type == 'reg' and reg2_type == 'reg':
                val1 = int(self.registers[reg1])
                val2 = int(self.registers[reg2])
                self.registers[0] = 1 if val1 == val2 else 0

        elif opcode == 'MOV':
            reg1_type, reg1 = self.fetch_operand(image)
            reg2_type, reg2 = self.fetch_operand(image)
            if reg1_type == 'reg' and reg2_type == 'reg':
                self.registers[reg1] = int(self.registers[reg2])

        elif opcode == 'PRT':
            reg_type, reg_num = self.fetch_operand(image)
            if reg_type == 'reg':
                val = int(self.registers[reg_num])
                self.output.append(val)
                print(f"OUTPUT: r{reg_num} = {val}")

        elif opcode == 'JMP':
            coord_type, coord_val = self.fetch_operand(image)
            if coord_type == 'coord':
                tx, ty = coord_val
                self.pc = (int(tx), int(ty))

        elif opcode == 'JZ':
            coord_type, coord_val = self.fetch_operand(image)
            if coord_type == 'coord' and int(self.registers[0]) == 0:
                tx, ty = coord_val
                self.pc = (int(tx), int(ty))

        elif opcode == 'HALT':
            self.running = False
            return False

        return True

    def run(self, image: np.ndarray, max_instructions: int = 1000):
        """
        Run program from image until halt or max instructions.

        Args:
            image: 2D pixel image containing the program
            max_instructions: Maximum instructions to execute
        """
        self.running = True
        instructions = 0

        print(f"Starting execution at PC={self.pc}")
        print(f"Initial registers: {self.registers}")

        while self.running and instructions < max_instructions:
            self.execute_instruction(image)
            instructions += 1

        print(f"Execution halted after {instructions} instructions")
        print(f"Final registers: {self.registers}")
        print(f"Output: {self.output}")


def demo():
    """Demonstrate spatial glyph emulator end-to-end."""

    print("=" * 60)
    print("SPATIAL GLYPH EMULATOR DEMO")
    print("=" * 60)

    # Initialize opcode map
    opcode_map = OpcodeMap()
    print(f"\nOpcode mappings:")
    for opcode in opcode_map.get_all_opcodes():
        rgb = opcode_map.opcode_to_rgb(opcode)
        print(f"  {opcode:4} → RGB{rgb}")

    # Simple assembly program: loop counter
    assembly = [
        "# Simple loop: count 0 to 4",
        "LDI r0 0",      # Initialize r0 = 0 (loop counter)
        "LDI r1 5",      # r1 = 5 (limit)
        "CMP r0 r1",     # Compare r0 with r1 (sets r0 = 1 if equal)
        "JZ 5,1",        # If equal, jump to coordinate (5, 1) [halt]
        "PRT r0",        # Print current counter
        "LDI r2 1",      # r2 = 1
        "ADD r0 r2",     # Increment counter
        "JMP 0,0",       # Jump back to start (0, 0)
        "HALT",         # End of program
    ]

    # Assemble to image
    assembler = GlyphAssembler(opcode_map)
    image = assembler.assemble_to_pixels(assembly, width=16)

    print(f"\nAssembled program: {len(assembly)} lines → {image.shape} pixel array")

    # Save image
    output_path = Path(__file__).parent.parent / "demo_glyph_program.png"
    Image.fromarray(image).save(output_path)
    print(f"Saved program image to: {output_path}")

    # Execute
    cpu = GlyphCPU(opcode_map)
    cpu.run(image)

    # Cleanup
    opcode_map.close()

    print("\n" + "=" * 60)
    print("DEMO COMPLETE")
    print("=" * 60)


if __name__ == '__main__':
    demo()