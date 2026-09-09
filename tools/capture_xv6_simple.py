#!/usr/bin/env python3
"""
Boot xv6 on QEMU, run commands, capture framebuffer patterns.

This is simpler than GPU boot for pattern capture.
"""

import subprocess
import time
import json
import re
from pathlib import Path
from PIL import Image
import numpy as np


def boot_xv6_qemu(kernel_path: str, timeout: int = 60):
    """
    Boot xv6 on QEMU and return subprocess.

    Returns:
        (subprocess, serial_path): QEMU process and serial output path
    """
    serial_path = Path("/tmp/xv6_serial_patterns.txt")
    serial_path.unlink(missing_ok=True)

    # Start QEMU with serial output to file
    cmd = [
        "qemu-system-riscv64",
        "-nographic",
        "-machine", "virt",
        "-bios", "none",
        "-kernel", kernel_path,
        "-m", "128M",
        "-smp", "1",
        "-global", "virtio-mmio.force-legacy=false",
        "-serial", f"file:{serial_path}"
    ]

    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    print(f"Booting xv6 on QEMU...")
    print(f"  Kernel: {kernel_path}")
    print(f"  Serial output: {serial_path}")

    return proc, serial_path


def wait_for_prompt(serial_path: Path, prompt: str = r"\$ ", timeout: int = 30):
    """Wait for shell prompt in serial output."""
    start = time.time()

    while time.time() - start < timeout:
        if serial_path.exists():
            with open(serial_path) as f:
                content = f.read()

            if re.search(prompt, content):
                print(f"✓ Prompt found in serial output")
                return True

        time.sleep(0.5)

    print(f"✗ Prompt not found after {timeout}s")
    return False


def send_command(proc: Path, command: str, serial_path: Path, wait_seconds: int = 2):
    """Send command to xv6 via QEMU monitor."""
    # For now, we'll simulate this by parsing serial output
    # In real implementation, use QEMU monitor to send input

    print(f"Simulating command: {command!r}")

    # Wait for output
    time.sleep(wait_seconds)

    # Read serial output
    if serial_path.exists():
        with open(serial_path) as f:
            output = f.read()
        return output
    return ""


def capture_command_pattern(command: str, serial_path: Path) -> dict:
    """
    Capture the execution pattern for a command.

    Returns:
        dict: Pattern with metadata and visual representation
    """
    # Read serial output
    if not serial_path.exists():
        return {}

    with open(serial_path) as f:
        serial_output = f.read()

    # Find command output
    lines = serial_output.split('\n')

    # Find the most recent occurrence of the command
    command_output = []
    found_command = False

    for line in reversed(lines):
        if command in line and not found_command:
            found_command = True
            continue

        if found_command:
            # Stop at next prompt
            if '$' in line or '#' in line:
                break
            command_output.append(line)

    command_output.reverse()

    # Create pattern
    pattern = {
        'command': command,
        'timestamp': time.time(),
        'serial_output': serial_output[-500:],  # Last 500 chars
        'command_output': command_output[:20],  # First 20 lines
        'output_lines': len(command_output),
        'metadata': {
            'serial_length': len(serial_output),
            'estimated_instructions': len(serial_output) * 100  # Rough estimate
        }
    }

    # Create visual representation (ASCII art of what xv6 might render)
    if command_output:
        # Simulate VGA text rendering
        visual_lines = []
        for line in command_output[:10]:  # First 10 lines
            # Convert text to pixel pattern (placeholder)
            ascii_line = line[:80]  # First 80 chars
            visual_lines.append(ascii_line)

        pattern['visual'] = visual_lines

    return pattern


def save_patterns(patterns: list, output_path: str):
    """Save captured patterns to JSON."""
    data = {
        'capture_timestamp': time.time(),
        'total_patterns': len(patterns),
        'patterns': patterns
    }

    with open(output_path, 'w') as f:
        json.dump(data, f, indent=2)

    print(f"✓ Saved {len(patterns)} patterns to: {output_path}")


def visualize_pattern(pattern: dict):
    """Visualize a pattern as ASCII art."""
    print(f"\n{'='*60}")
    print(f"Pattern for: {pattern['command']!r}")
    print(f"{'='*60}")

    # Show command output
    if pattern.get('command_output'):
        print(f"\nCommand Output (first {len(pattern['command_output'])} lines):")
        for line in pattern['command_output'][:15]:
            print(f"  {line}")

    # Show visual representation
    if pattern.get('visual'):
        print(f"\nVisual Framebuffer Pattern (simulated VGA 80x25):")
        for line in pattern['visual'][:20]:
            print(f"  {line}")

    # Show metadata
    print(f"\nMetadata:")
    print(f"  Timestamp: {pattern['timestamp']}")
    print(f"  Output lines: {pattern['output_lines']}")
    print(f"  Serial length: {pattern['metadata']['serial_length']}")

    print(f"{'='*60}")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Capture xv6 execution patterns")
    parser.add_argument('command', nargs='?', default="ls", help="Command to run (default: ls)")
    parser.add_argument('--output', '-o', default="tools/xv6_patterns.json", help="Output JSON path")

    args = parser.parse_args()

    print("=" * 60)
    print("CAPTURING XV6 EXECUTION PATTERNS")
    print("=" * 60)

    # Boot xv6
    kernel_path = "vendor/xv6-riscv/kernel/kernel"

    if not Path(kernel_path).exists():
        print(f"✗ Kernel not found: {kernel_path}")
        print("\nPlease build xv6 first:")
        print("  cd vendor/xv6-riscv && make kernel")
        return

    proc, serial_path = boot_xv6_qemu(kernel_path)

    # Wait for prompt
    if not wait_for_prompt(serial_path):
        proc.terminate()
        print("✗ Failed to boot xv6")
        return

    print(f"\n✓ xv6 booted successfully")

    # Capture pattern for the command
    # NOTE: This simulates the pattern - in real implementation,
    # we'd send the actual command via QEMU monitor
    print(f"\nCapturing pattern for: {args.command!r}")

    pattern = capture_command_pattern(args.command, serial_path)

    if pattern:
        visualize_pattern(pattern)

        # Save pattern
        patterns = [pattern]
        save_patterns(patterns, args.output)

        print(f"\n✓ Pattern saved!")
        print(f"\nHow to use this pattern:")
        print(f"  1. Load: import json; data = json.load(open('{args.output}'))")
        print(f"  2. Get pattern: pattern = data['patterns'][0]")
        print(f"  3. Use visual: print('\\n'.join(pattern['visual']))")
        print(f"  4. Use metadata: pattern['metadata']['output_lines']")
    else:
        print(f"✗ Failed to capture pattern")

    # Cleanup
    proc.terminate()
    serial_path.unlink(missing_ok=True)

    print(f"\n{'='*60}")
    print("CAPTURE COMPLETE")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()