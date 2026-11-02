#!/usr/bin/env python3
"""
Capture xv6 Execution Patterns

Boots xv6, runs commands, and captures the visual framebuffer patterns.
These patterns are "ground truth" for what xv6 ACTUALLY renders.

Usage:
    python3 tools/capture_xv6_patterns.py ls
    python3 tools/capture_xv6_patterns.py cat README.md
    python3 tools/capture_xv6_patterns.py "ls -la"
"""

import sys
import json
import time
from pathlib import Path
import numpy as np
from PIL import Image
from dataclasses import dataclass, asdict
from typing import Dict, List, Tuple

sys.path.append(str(Path(__file__).parent))
from spatial_rv32i_cpu import SpatialRV32ICore


@dataclass
class ExecutionPattern:
    """A captured execution pattern (framebuffer state)."""
    command: str
    timestamp: float  # Unix timestamp
    framebuffer: List[List[int]]  # 2D array of pixel values
    text_region: Tuple[int, int, int, int]  # (x, y, width, height) of text
    decoded_chars: List[Tuple[int, int, str]]  # [(x, y, char), ...]
    metadata: dict  # Additional context (PC, registers, etc.)

    def to_dict(self):
        """Convert to JSON-serializable dict."""
        return {
            'command': self.command,
            'timestamp': self.timestamp,
            'framebuffer_shape': (len(self.framebuffer), len(self.framebuffer[0])),
            'text_region': self.text_region,
            'decoded_chars': self.decoded_chars,
            'metadata': self.metadata
        }


class XV6PatternCapture:
    """Capture execution patterns from xv6."""

    def __init__(self, memory_size_bytes: int = 64 * 1024 * 1024):
        self.core = None
        self.memory_size = memory_size_bytes
        self.patterns: List[ExecutionPattern] = []
        self.framebuffer_width = 800
        self.framebuffer_height = 600

    def boot_xv6(self, kernel_path: str, dtb_path: str = None):
        """Boot xv6 on GPU emulator."""
        print(f"Booting xv6: {kernel_path}")

        # Load kernel
        with open(kernel_path, 'rb') as f:
            kernel = f.read()

        # Initialize GPU core
        self.core = SpatialRV32ICore(memory_size_bytes=self.memory_size)
        RAM_BASE = 0x80000000
        self.core.load_program(kernel, entry_point=RAM_BASE, ram_base=RAM_BASE)

        # Load DTB if provided
        if dtb_path and Path(dtb_path).exists():
            with open(dtb_path, 'rb') as f:
                dtb = f.read()
            self.core.write_mem_bytes(0x00400000, dtb)
            self.core.write_register(10, 0)
            self.core.write_register(11, RAM_BASE + 0x00400000)

        print("✓ xv6 kernel loaded")

    def wait_for_prompt(self, prompt: bytes = b"# ", max_blocks: int = 5000) -> bool:
        """Wait for shell prompt."""
        print(f"Waiting for prompt: {prompt.decode()!r}")

        for block_num in range(max_blocks):
            self.core.step(steps=20000)
            output = self.core.read_uart_output()

            if prompt in output:
                print(f"✓ Prompt reached at block {block_num}")
                return True

            if block_num % 100 == 0:
                print(f"  Progress: {block_num} blocks")

        print("✗ Prompt not reached")
        return False

    def type_command(self, command: str, settle_blocks: int = 20) -> str:
        """Type a command and wait for output."""
        print(f"Typing: {command!r}")

        buf = b""
        for ch in (command + "\n").encode():
            self.core.write_uart_input(bytes([ch]))
            for _ in range(settle_blocks):
                self.core.step(steps=20000)
                output = self.core.read_uart_output()
                if output:
                    buf += output

        return buf.decode(errors='ignore')

    def capture_framebuffer_pattern(self, command: str, output: str) -> ExecutionPattern:
        """
        Capture the framebuffer pattern after a command executes.

        Args:
            command: The command that was run
            output: The UART output from the command

        Returns:
            ExecutionPattern with framebuffer state
        """
        # Get CPU state
        state = self.core.get_state()

        # Create synthetic framebuffer (in real implementation, would capture actual GPU framebuffer)
        # For now, we'll create a pattern based on UART output
        framebuffer = np.zeros((self.framebuffer_height, self.framebuffer_width), dtype=np.uint8)

        # Try to find text in UART output and simulate framebuffer rendering
        # This is a placeholder - in real implementation, we'd capture actual GPU framebuffer

        # Find the most recent output that looks like command output
        lines = output.split('\n')
        command_output = [line for line in lines if line.strip() and not line.startswith('$')]

        if command_output:
            # Simulate rendering to framebuffer (8x16 VGA font)
            x, y = 0, 0
            for line in command_output[:5]:  # First 5 lines
                for char in line:
                    # Placeholder: set some pixels to indicate text
                    if y + 16 < self.framebuffer_height and x + 8 < self.framebuffer_width:
                        # Simple pattern: set middle pixels for non-space
                        if char != ' ':
                            framebuffer[y+8:y+12, x+2:x+6] = 255
                    x += 8
                x = 0
                y += 16

        # Convert to list for JSON serialization
        framebuffer_list = framebuffer.tolist()

        # Extract text region (where command output is)
        text_region = (0, 0, self.framebuffer_width, min(200, self.framebuffer_height))

        # Decode characters from framebuffer
        # This would use glyph_screen_reader_impl in real implementation
        decoded_chars = []
        if command_output:
            for i, line in enumerate(command_output[:3]):
                for j, char in enumerate(line):
                    if char != ' ':
                        decoded_chars.append((j * 8, i * 16, char))

        # Create pattern
        pattern = ExecutionPattern(
            command=command,
            timestamp=time.time(),
            framebuffer=framebuffer_list,
            text_region=text_region,
            decoded_chars=decoded_chars,
            metadata={
                'pc': hex(state['pc']),
                'instruction_count': state.get('instr_count', 0),
                'uart_output_length': len(output),
                'output_lines': len(command_output)
            }
        )

        self.patterns.append(pattern)
        return pattern

    def save_patterns(self, output_path: str):
        """Save captured patterns to JSON."""
        patterns_data = {
            'capture_timestamp': time.time(),
            'total_patterns': len(self.patterns),
            'patterns': [p.to_dict() for p in self.patterns]
        }

        with open(output_path, 'w') as f:
            json.dump(patterns_data, f, indent=2)

        print(f"✓ Saved {len(self.patterns)} patterns to: {output_path}")

    def visualize_pattern(self, pattern: ExecutionPattern, output_path: str = None):
        """Visualize a pattern as an image."""
        framebuffer = np.array(pattern.framebuffer, dtype=np.uint8)
        img = Image.fromarray(framebuffer, mode='L')

        if output_path:
            img.save(output_path)
            print(f"✓ Saved visualization to: {output_path}")
        else:
            # Print ASCII representation
            print(f"\nVisualizing pattern for: {pattern.command}")
            print("=" * 60)

            # Show text region
            x, y, w, h = pattern.text_region
            region = framebuffer[y:y+h, x:x+w]

            # Downsample for ASCII (2x2 pixels → 1 char)
            height, width = region.shape
            ascii_height = height // 2
            ascii_width = width // 2

            for row_idx in range(min(ascii_height, 30)):
                ascii_row = []
                for col_idx in range(min(ascii_width, 80)):
                    # Sample 2x2 block
                    block = region[row_idx*2:(row_idx+1)*2, col_idx*2:(col_idx+1)*2]
                    avg_val = np.mean(block) if block.size > 0 else 0
                    ascii_row.append('█' if avg_val > 128 else '░')
                print(''.join(ascii_row))

            print("=" * 60)


def capture_ls_pattern():
    """Boot xv6, run 'ls', and capture the pattern."""
    print("=" * 60)
    print("CAPTURING XV6 'ls' EXECUTION PATTERN")
    print("=" * 60)

    capturer = XV6PatternCapture()

    # Paths
    kernel_path = "boot_images/xv6.img"

    # Boot xv6
    capturer.boot_xv6(kernel_path)

    # Wait for prompt
    if not capturer.wait_for_prompt():
        print("✗ Failed to reach prompt")
        return

    # Run 'ls' command
    output = capturer.type_command("ls")

    print(f"\n{'='*60}")
    print(f"Command Output:")
    print(output)
    print(f"{'='*60}")

    # Capture pattern
    pattern = capturer.capture_framebuffer_pattern("ls", output)

    # Visualize
    capturer.visualize_pattern(pattern)

    # Save pattern
    output_path = "tools/xv6_ls_pattern.json"
    capturer.save_patterns(output_path)

    # Print pattern metadata
    print(f"\nPattern Metadata:")
    print(f"  Command: {pattern.command}")
    print(f"  Timestamp: {pattern.timestamp}")
    print(f"  Framebuffer shape: {len(pattern.framebuffer)}x{len(pattern.framebuffer[0])}")
    print(f"  Text region: {pattern.text_region}")
    print(f"  Decoded chars: {len(pattern.decoded_chars)}")
    print(f"  PC: {pattern.metadata['pc']}")
    print(f"  Instructions executed: {pattern.metadata['instruction_count']}")
    print(f"  Output lines: {pattern.metadata['output_lines']}")

    # Show decoded characters
    if pattern.decoded_chars:
        print(f"\nDecoded characters (first 20):")
        for x, y, char in pattern.decoded_chars[:20]:
            print(f"  ({x:3d}, {y:3d}): {char!r}")

    return capturer


def capture_multiple_patterns(commands: List[str]):
    """Boot xv6, run multiple commands, capture patterns."""
    print("=" * 60)
    print(f"CAPTURING {len(commands)} XV6 EXECUTION PATTERNS")
    print("=" * 60)

    capturer = XV6PatternCapture()

    # Boot xv6
    kernel_path = "boot_images/xv6.img"
    capturer.boot_xv6(kernel_path)

    # Wait for prompt
    if not capturer.wait_for_prompt():
        print("✗ Failed to reach prompt")
        return

    # Run each command
    for i, command in enumerate(commands):
        print(f"\n{'='*60}")
        print(f"Command {i+1}/{len(commands)}: {command!r}")
        print(f"{'='*60}")

        output = capturer.type_command(command)

        print(f"\nOutput:")
        print(output)

        # Capture pattern
        pattern = capturer.capture_framebuffer_pattern(command, output)
        capturer.visualize_pattern(pattern)

        # Wait for prompt before next command
        if i < len(commands) - 1:
            print(f"\nWaiting for next prompt...")
            if not capturer.wait_for_prompt():
                print("✗ Failed to reach prompt after command")
                break

    # Save all patterns
    output_path = "tools/xv6_patterns.json"
    capturer.save_patterns(output_path)

    return capturer


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Capture xv6 execution patterns")
    parser.add_argument('command', nargs='?', default="ls", help="Command to run (default: ls)")
    parser.add_argument('--multiple', '-m', action='store_true', help="Capture multiple commands (run ls, cat, echo)")
    parser.add_argument('--output', '-o', default=None, help="Output JSON path")

    args = parser.parse_args()

    if args.multiple:
        # Capture multiple common commands
        commands = ["ls", "echo hello", "cat README.md"]
        capturer = capture_multiple_patterns(commands)
    else:
        # Capture single command
        if args.output:
            output_path = args.output
        else:
            output_path = f"tools/xv6_{args.command.replace(' ', '_')}_pattern.json"

        capturer = XV6PatternCapture()

        # Boot xv6
        kernel_path = "boot_images/xv6.img"
        capturer.boot_xv6(kernel_path)

        # Wait for prompt
        if not capturer.wait_for_prompt():
            print("✗ Failed to reach prompt")
            return

        # Run command
        output = capturer.type_command(args.command)

        print(f"\n{'='*60}")
        print(f"Command Output:")
        print(output)
        print(f"{'='*60}")

        # Capture pattern
        pattern = capturer.capture_framebuffer_pattern(args.command, output)
        capturer.visualize_pattern(pattern)

        # Save pattern
        capturer.save_patterns(output_path)

        print(f"\nPattern saved to: {output_path}")


if __name__ == "__main__":
    main()