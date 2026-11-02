#!/usr/bin/env python3
"""
Spatial VM — Spectrogram as executable memory.

Core Concept:
- Frequency = register/memory address
- Time = program counter  
- Amplitude = value

The program executes by being played as audio. The spectrogram IS the running state:
- Each time slice (column) is a complete register state
- Each frequency bin (row) maps to a register/memory cell
- Amplitude at (time, frequency) is the value stored there

This is TASK_R002: Spectrogram as spatial VM — execute in the image.

Usage:
    python3 tools/spatial_vm.py execute program.png
    python3 tools/spatial_vm.py generate_counter --output counter.png --frames 100
"""

import argparse
import sys
import pathlib
from typing import Dict, List, Optional, Tuple

import numpy as np
from PIL import Image


class SpectrogramVM:
    """
    A virtual machine where memory layout is a spectrogram.
    
    Mapping:
    - X-axis (pixels/columns) → Program Counter (time)
    - Y-axis (pixels/rows) → Registers/Memory (frequency)
    - Pixel intensity (0-255) → Values
    
    Using PNG format since Visual Audio already has robust image handling.
    """
    
    def __init__(self, n_registers: int = 16):
        """
        Initialize the Spatial VM.
        
        Args:
            n_registers: Number of registers (height of spectrogram)
        """
        self.n_registers = n_registers
        
        # Register file: indexed by frequency bin (row)
        self.registers = np.zeros(n_registers, dtype=np.float32)
        
        # Program counter: current time frame (column)
        self.pc = 0
        
        # Output stream
        self.output = []
        
        # Running state
        self.running = False
        
        # Spectrogram storage (height x width grayscale)
        self.spectrogram: Optional[np.ndarray] = None
        
    def load_image(self, image_path: str) -> None:
        """
        Load PNG image as program spectrogram.
        
        Each column is a time frame, each row is a register.
        Pixel brightness (0-255) encodes values.
        """
        # Load as grayscale
        img = Image.open(image_path).convert('L')
        
        # Convert to numpy array (height x width)
        self.spectrogram = np.array(img, dtype=np.float32) / 255.0  # Normalize to [0,1]
        
        print(f"Loaded: {image_path}")
        print(f"  Image shape: {self.spectrogram.shape} (rows={self.n_registers}, cols=frames)")
        print(f"  Value range: [{self.spectrogram.min():.3f}, {self.spectrogram.max():.3f}]")
        print(f"  Max frames: {self.spectrogram.shape[1]}")
        
    def _read_register(self, reg_idx: int) -> float:
        """
        Read a register value from the spectrogram at current PC.
        
        Row (frequency bin) maps to register index.
        Column (time) is the PC.
        Pixel intensity is the value.
        """
        if reg_idx >= self.n_registers:
            raise ValueError(f"Register {reg_idx} out of range (0-{self.n_registers-1})")

        if self.spectrogram is None or self.pc >= self.spectrogram.shape[1]:
            return 0.0  # Past end of program or not loaded

        # Read pixel at (row=reg_idx, col=pc)
        value = self.spectrogram[reg_idx, self.pc]

        return float(value)
    
    def _write_register(self, reg_idx: int, value: float) -> None:
        """
        Write a register value to the spectrogram (modifies current frame).

        This enables the output re-encoding as next iteration's input.
        """
        if reg_idx >= self.n_registers:
            raise ValueError(f"Register {reg_idx} out of range (0-{self.n_registers-1})")

        if self.spectrogram is None or self.pc >= self.spectrogram.shape[1]:
            return  # Past end of program or not loaded

        # Write value to spectrogram
        self.spectrogram[reg_idx, self.pc] = float(value)
        self.registers[reg_idx] = float(value)
    
    def step(self) -> bool:
        """
        Execute one instruction at current PC.

        Instruction encoding in spectrogram:
        - Row 0: opcode (0=NOOP, 1=SET, 2=SUB, 3=CMP, 4=JZ, 5=HALT, 6=ADD)
        - Row 1: destination register (rd)
        - Row 2: source register 1 (rs1)
        - Row 3: source register 2 (rs2)
        - Row 4: immediate value (imm)
        - Row 5: jump target (for JMP/JZ)

        Returns: True if should continue, False if halted
        """
        if self.spectrogram is None or self.pc >= self.spectrogram.shape[1]:
            self.running = False
            return False

        # Decode instruction from spectrogram (decode: value * scale)
        opcode = round(self._read_register(0) * 10)  # Use round to handle quantization
        rd = int(self._read_register(1) * self.n_registers)
        rs1 = int(self._read_register(2) * self.n_registers)
        rs2 = int(self._read_register(3) * self.n_registers)
        imm = self._read_register(4)
        jump_target = int(self._read_register(5) * (self.spectrogram.shape[1] if self.spectrogram is not None else 1))

        # Debug: print instruction decode
        if self.pc < 20 or self.pc % 50 == 0:
            op_names = {0: 'NOOP', 1: 'SET', 2: 'SUB', 3: 'CMP', 4: 'JZ', 5: 'HALT', 6: 'ADD'}
            print(f"PC={self.pc:2d} | opcode={opcode} ({op_names.get(opcode, 'UNKNOWN')}) | rd={rd} rs1={rs1} rs2={rs2} imm={imm:.3f}")

        # Execute opcode
        if opcode == 0:  # NOOP
            pass
        elif opcode == 1:  # SET: rd = imm (immediate load)
            self._write_register(rd, imm)
        elif opcode == 2:  # SUB: rd = rs1 - rs2
            val = self._read_register(rs1) - self._read_register(rs2)
            self._write_register(rd, val)
        elif opcode == 3:  # CMP: set flag in r6 (1 if rs1 == rs2, else 0)
            flag = 1.0 if np.isclose(self._read_register(rs1), self._read_register(rs2), atol=1e-3) else 0.0
            self._write_register(6, flag)
        elif opcode == 4:  # JZ: if r6 flag set, jump to target
            if self._read_register(6) > 0.5:  # Flag set
                self.pc = jump_target
                return True
        elif opcode == 5:  # HALT
            self.running = False
            return False
        elif opcode == 6:  # ADD: rd = rs1 + rs2
            val = self._read_register(rs1) + self._read_register(rs2)
            self._write_register(rd, val)
        else:
            print(f"Unknown opcode {opcode} at PC={self.pc}, treating as NOOP")

        # Increment PC
        self.pc += 1

        return True

    def run(self, max_frames: int = 1000) -> int:
        """
        Execute program from current PC.

        Args:
            max_frames: Maximum frames to execute (safety limit)

        Returns:
            Number of instructions executed
        """
        self.running = True
        steps = 0

        print(f"\nStarting execution at PC={self.pc}")
        print(f"  Max frames: {max_frames}")
        print(f"  Registers: {self.n_registers}\n")

        while self.running and steps < max_frames:
            should_continue = self.step()

            # Print debug every 10 steps
            if steps % 10 == 0:
                regs_str = ", ".join(f"r{i}={self._read_register(i):.3f}" for i in range(min(8, self.n_registers)))
                print(f"  [{steps:3d}] PC={self.pc:3d} | {regs_str}")

            steps += 1

        print(f"\nHalted after {steps} instructions")
        print(f"Final registers: {self.registers[:8]}")
        print(f"PC: {self.pc} / {self.spectrogram.shape[1] if self.spectrogram is not None else 0}")

        return steps

    def generate_counter_program(self, output_path: str, frames: int = 100) -> None:
        """
        Generate a spectrogram that executes a counter program.

        Program: counts from 0 to 10, then halts.

        Simpler encoding: each row is a register value, each column is a time step.
        Opcode row (0) determines the operation.
        """
        print(f"Generating counter program: {frames} frames")

        # Create spectrogram: (height/rows=n_registers, width/cols=frames)
        spectrogram = np.zeros((self.n_registers, frames), dtype=np.float32)

        # Helper to set a value in the spectrogram
        def set(row, col, value):
            spectrogram[row, col] = float(value)

        # Direct opcode encoding: value = opcode (0-6)
        # r0 is the counter
        # r1 is the limit (0.5 = scaled 10)
        # r6 is the flag register
        
        # Frame 0: r0 = 0 (immediate load via row 4)
        set(0, 0, 0.1)  # Opcode: SET (1) = 0.1 * 10
        set(1, 0, 0.0)  # rd = r0
        set(4, 0, 0.0)  # imm = 0

        # Frame 1: r1 = 10 (scaled to 0.5)
        set(0, 1, 0.1)  # Opcode: SET (1)
        set(1, 1, 1.0 / self.n_registers)  # rd = r1
        set(4, 1, 0.5)  # imm = 0.5 (represents 10)

        # Frame 2: CMP r0 r1
        set(0, 2, 0.3)  # Opcode: CMP (3) = 0.3 * 10
        set(2, 2, 0.0)  # rs1 = r0
        set(3, 2, 1.0 / self.n_registers)  # rs2 = r1

        # Frame 3: JZ 9 (jump to HALT if equal)
        set(0, 3, 0.4)  # Opcode: JZ (4) = 0.4 * 10
        set(5, 3, 9.0 / frames)  # jump to frame 9 (HALT)

        # Frame 4: Print r0 (use a NOOP but we track it in debug)
        set(0, 4, 0.0)  # NOOP

        # Frame 5: r2 = 1 (scaled to 0.05)
        set(0, 5, 0.1)  # Opcode: SET (1)
        set(1, 5, 2.0 / self.n_registers)  # rd = r2
        set(4, 5, 0.05)  # imm = 0.05 (represents 1)

        # Frame 6: r0 = r0 + r2
        set(0, 6, 0.6)  # Opcode: ADD (6) = 0.6 * 10
        set(1, 6, 0.0)  # rd = r0
        set(2, 6, 0.0)  # rs1 = r0
        set(3, 6, 2.0 / self.n_registers)  # rs2 = r2

        # Frame 7: JMP 2
        set(0, 7, 0.4)  # Opcode: JMP/JZ (4)
        set(5, 7, 2.0 / frames)  # jump to frame 2

        # Frame 8: NOOP (padding)
        set(0, 8, 0.0)

        # Frame 9: HALT
        set(0, 9, 0.5)  # Opcode: HALT (5) = 0.5 * 10

        self.spectrogram = spectrogram

        # Convert to 8-bit grayscale image
        img_array = (spectrogram * 255).astype(np.uint8)
        img = Image.fromarray(img_array, mode='L')

        # Save to file
        img.save(output_path)
        print(f"Saved spectrogram program to: {output_path}")
        print(f"  Image shape: {img_array.shape}")
        print(f"  Value range: [{img_array.min()}, {img_array.max()}]")


def main():
    parser = argparse.ArgumentParser(description='Spatial VM — Spectrogram as executable memory')
    subparsers = parser.add_subparsers(dest='command', help='Command to execute')

    # Execute command
    exec_parser = subparsers.add_parser('execute', help='Execute a spectrogram program')
    exec_parser.add_argument('program', help='Path to PNG file containing program spectrogram')
    exec_parser.add_argument('--max-frames', type=int, default=1000, 
                            help='Maximum frames to execute (default: 1000)')

    # Generate command
    gen_parser = subparsers.add_parser('generate_counter', help='Generate counter program')
    gen_parser.add_argument('--output', '-o', default='counter.png', 
                           help='Output PNG file (default: counter.png)')
    gen_parser.add_argument('--frames', type=int, default=20,
                           help='Number of frames (default: 20)')
    gen_parser.add_argument('--n-registers', type=int, default=16,
                           help='Number of registers (default: 16)')

    args = parser.parse_args()

    if args.command == 'execute':
        vm = SpectrogramVM()
        vm.load_image(args.program)
        vm.run(max_frames=args.max_frames)

    elif args.command == 'generate_counter':
        vm = SpectrogramVM(n_registers=args.n_registers)
        vm.generate_counter_program(args.output, frames=args.frames)

        # Verify by executing
        print("\n" + "="*60)
        print("Verifying generated program...")
        print("="*60)
        vm.load_image(args.output)
        vm.run(max_frames=args.frames)

    else:
        parser.print_help()
        sys.exit(1)


if __name__ == '__main__':
    main()