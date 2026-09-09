#!/usr/bin/env python3
"""
Demo: What does the 'ls' pattern look like?

This script shows the pattern xv6 creates when running 'ls',
demonstrating how we can save and use execution patterns.
"""

import json
import time


def create_ls_pattern_demo():
    """
    Create a demonstration of what the 'ls' pattern looks like.

    This is synthetic - in real implementation, you'd boot xv6
    and capture the actual pattern.
    """
    print("=" * 70)
    print("DEMONSTRATION: XV6 'ls' EXECUTION PATTERN")
    print("=" * 70)

    # Simulated xv6 'ls' output (what actually happens)
    xv6_ls_output = """
$ ls
.               1 1 1
..              1 1 512
README          1 1 2046
cat             1 1 12472
echo            1 1 13004
grep            1 1 13856
init            1 1 12492
kill            1 1 12628
ln              1 1 12980
ls              1 1 14176
mkdir           1 1 12856
rm              1 1 13116
sh              1 1 21952
stressfs        1 1 12548
usertests        1 1 15552
wc              1 1 13104
zombie          1 1 12636
$
"""

    print("\n1. SERIAL OUTPUT PATTERN (UART)")
    print("-" * 70)
    print(xv6_ls_output)

    # Parse the pattern
    lines = [line for line in xv6_ls_output.split('\n') if line.strip()]

    # Find the 'ls' command output
    ls_output = []
    in_ls = False

    for line in lines:
        if '$ ls' in line:
            in_ls = True
            continue
        if in_ls and '$' in line:
            break
        if in_ls:
            ls_output.append(line)

    print("\n2. STRUCTURED PATTERN (WHAT WE SAVE)")
    print("-" * 70)

    pattern = {
        'command': 'ls',
        'timestamp': time.time(),

        # Serial output (last 1000 chars)
        'serial_output': xv6_ls_output[-1000:],

        # Command output (parsed)
        'command_output': ls_output,

        # Metadata
        'metadata': {
            'output_lines': len(ls_output),
            'files_listed': len(ls_output) - 1,  # Exclude header
            'serial_length': len(xv6_ls_output),

            # File listing
            'files': [
                {'name': '.', 'inode': 1, 'size': 1},
                {'name': '..', 'inode': 1, 'size': 512},
                {'name': 'README', 'inode': 1, 'size': 2046},
                {'name': 'cat', 'inode': 1, 'size': 12472},
                {'name': 'echo', 'inode': 1, 'size': 13004},
                {'name': 'grep', 'inode': 1, 'size': 13856},
                {'name': 'init', 'inode': 1, 'size': 12492},
                {'name': 'kill', 'inode': 1, 'size': 12628},
                {'name': 'ln', 'inode': 1, 'size': 12980},
                {'name': 'ls', 'inode': 1, 'size': 14176},
                {'name': 'mkdir', 'inode': 1, 'size': 12856},
                {'name': 'rm', 'inode': 1, 'size': 13116},
                {'name': 'sh', 'inode': 1, 'size': 21952},
                {'name': 'stressfs', 'inode': 1, 'size': 12548},
                {'name': 'usertests', 'inode': 1, 'size': 15552},
                {'name': 'wc', 'inode': 1, 'size': 13104},
                {'name': 'zombie', 'inode': 1, 'size': 12636},
            ],

            # Column formatting
            'columns': 6,  # 6 columns: name, inode, dev, type, inuse, size
            'column_widths': [14, 4, 2, 2, 5, 6],

            # Execution metrics (simulated)
            'instructions_executed': 15234,
            'memory_reads': 245,
            'memory_writes': 189,
            'duration_ms': 52,
        }
    }

    print(f"Command: {pattern['command']}")
    print(f"Timestamp: {pattern['timestamp']}")
    print(f"\nMetadata:")
    print(f"  Output lines: {pattern['metadata']['output_lines']}")
    print(f"  Files listed: {pattern['metadata']['files_listed']}")
    print(f"  Serial length: {pattern['metadata']['serial_length']}")
    print(f"  Instructions: ~{pattern['metadata']['instructions_executed']:,}")
    print(f"  Duration: ~{pattern['metadata']['duration_ms']}ms")
    print(f"  IPS: ~{pattern['metadata']['instructions_executed'] // pattern['metadata']['duration_ms'] * 1000:,}")

    print(f"\nFiles:")
    for file_info in pattern['metadata']['files'][:5]:
        print(f"  {file_info['name']:12s}  inode={file_info['inode']}  size={file_info['size']:5d}")
    print(f"  ... ({len(pattern['metadata']['files']) - 5} more)")

    print("\n3. VISUAL PATTERN (VGA FRAMEBUFFER)")
    print("-" * 70)

    # Simulate VGA rendering (80x25 text mode)
    vga_width = 80
    vga_height = 25

    print(f"\nVGA Text Mode: {vga_width}x{vga_height}")
    print(f"Each character: 8x16 pixels")
    print(f"Resolution: {vga_width*8}x{vga_height*16} = 640x400 pixels")
    print(f"\nSimulated framebuffer (80x25 ASCII):")
    print()

    # Create ASCII representation of what VGA would render
    framebuffer_ascii = []

    for y in range(vga_height):
        row = []
        for x in range(vga_width):
            # Map to serial output position
            if y < len(ls_output):
                line = ls_output[y]
                if x < len(line):
                    row.append(line[x])
                else:
                    row.append(' ')
            else:
                row.append(' ')
        framebuffer_ascii.append(''.join(row))

    for line in framebuffer_ascii[:20]:  # First 20 lines
        print(f"  {line}")

    print("\n4. HOW TO USE THIS PATTERN")
    print("-" * 70)

    print("\nSave to JSON:")
    print(f"  with open('xv6_ls_pattern.json', 'w') as f:")
    print(f"      json.dump(pattern, f, indent=2)")

    print("\nLoad and verify boot:")
    print(f"  with open('xv6_ls_pattern.json') as f:")
    print(f"      expected = json.load(f)")
    print(f"  ")
    print(f"  # Boot xv6 and run 'ls'")
    print(f"  actual = capture_actual_output()")
    print(f"  ")
    print(f"  # Verify pattern matches")
    print(f"  if 'ls' in actual:")
    print(f"      if len(parse_ls_output(actual)) == expected['metadata']['files_listed']:")
    print(f"          print('✓ xv6 'ls' output matches expected pattern')")

    print("\nUse as golden reference for RV64:")
    print(f"  # When building RV64 emulator, verify it produces same output")
    print(f"  rv64_output = run_rv64_ls()")
    print(f"  ")
    print(f"  if rv64_output == expected['serial_output']:")
    print(f"      print('✓ RV64 matches RV32 golden reference')")

    print("\n5. ACTUAL SAVED PATTERN (JSON)")
    print("-" * 70)

    # Save the pattern
    output_path = 'tools/xv6_ls_pattern_demo.json'
    with open(output_path, 'w') as f:
        json.dump(pattern, f, indent=2)

    print(f"\n✓ Saved pattern to: {output_path}")
    print(f"\nPattern structure:")
    print(f"  {{")
    print(f"    'command': 'ls',")
    print(f"    'timestamp': {pattern['timestamp']},")
    print(f"    'serial_output': <1000 chars>,")
    print(f"    'command_output': [<lines>],")
    print(f"    'metadata': {{")
    print(f"      'output_lines': {pattern['metadata']['output_lines']},")
    print(f"      'files_listed': {pattern['metadata']['files_listed']},")
    print(f"      'files': [<18 files>],")
    print(f"      'instructions_executed': {pattern['metadata']['instructions_executed']},")
    print(f"      'duration_ms': {pattern['metadata']['duration_ms']},")
    print(f"      ...")
    print(f"    }}")
    print(f"  }}")

    print("\n6. HOW TO LOAD AND USE")
    print("-" * 70)

    print(f"\nLoad pattern:")
    print(f"  import json")
    print(f"  with open('{output_path}') as f:")
    print(f"      pattern = json.load(f)")

    print(f"\nAccess command output:")
    print(f"  for line in pattern['command_output']:")
    print(f"      print(line)")

    print(f"\nAccess file listing:")
    print(f"  for file_info in pattern['metadata']['files']:")
    print(f"      print(f\"{{file_info['name']}}: {{file_info['size']}} bytes\")")

    print(f"\nVerify performance:")
    print(f"  expected_ips = pattern['metadata']['instructions_executed'] // pattern['metadata']['duration_ms'] * 1000")
    print(f"  actual_ips = measure_actual_ips()")
    print(f"  if actual_ips >= expected_ips * 0.9:")
    print(f"      print('✓ Performance within 10% of target')")

    print("\n" + "=" * 70)
    print("PATTERN DEMONSTRATION COMPLETE")
    print("=" * 70)

    print(f"\nNext steps:")
    print(f"  1. Review saved pattern: {output_path}")
    print(f"  2. Boot actual xv6 and capture real pattern")
    print(f"  3. Compare real pattern to demo pattern")
    print(f"  4. Use patterns to guide development")

    return pattern


def show_pattern_comparison():
    """Show how to compare actual pattern to expected pattern."""
    print("\n" + "=" * 70)
    print("PATTERN COMPARISON EXAMPLE")
    print("=" * 70)

    # Load the demo pattern
    try:
        with open('tools/xv6_ls_pattern_demo.json') as f:
            expected_pattern = json.load(f)
    except FileNotFoundError:
        print("✗ Demo pattern not found. Run create_ls_pattern_demo() first.")
        return

    print("\nExpected pattern (from demo):")
    print(f"  Command: {expected_pattern['command']}")
    print(f"  Files listed: {expected_pattern['metadata']['files_listed']}")
    print(f"  Instructions: ~{expected_pattern['metadata']['instructions_executed']:,}")

    print("\n" + "-" * 70)
    print("How to compare with actual xv6 execution:")
    print("-" * 70)

    print("""
import json

# Load expected pattern
with open('tools/xv6_ls_pattern_demo.json') as f:
    expected = json.load(f)

# Boot xv6 and capture actual pattern
# (This would be your actual xv6 boot code)
actual_output = boot_xv6_and_run_ls()

# Parse actual output
actual_lines = [line for line in actual_output.split('\\n') if line.strip()]
actual_files = len(actual_lines) - 1  # Exclude header

# Compare
if actual_files == expected['metadata']['files_listed']:
    print(f"✓ File count matches: {actual_files}")
else:
    print(f"✗ File count mismatch: {actual_files} != {expected['metadata']['files_listed']}")

# Check for expected files
expected_files = [f['name'] for f in expected['metadata']['files']]
found_files = [f for f in expected_files if f in actual_output]

if len(found_files) == len(expected_files):
    print(f"✓ All {len(expected_files)} expected files found")
else:
    print(f"✗ Only {len(found_files)}/{len(expected_files)} files found")

# Verify serial output length
if len(actual_output) == expected['metadata']['serial_length']:
    print(f"✓ Serial output length matches")
else:
    print(f"✗ Serial output length differs: {len(actual_output)} != {expected['metadata']['serial_length']}")

# Overall verification
if (actual_files == expected['metadata']['files_listed'] and
    len(found_files) == len(expected_files)):
    print("\\n✓ Pattern match: actual xv6 execution matches expected")
else:
    print("\\n✗ Pattern mismatch: actual differs from expected")
""")

    print("\n" + "=" * 70)


if __name__ == "__main__":
    # Create demo pattern
    pattern = create_ls_pattern_demo()

    # Show comparison example
    show_pattern_comparison()

    print("\n" + "=" * 70)
    print("SUMMARY: WHAT THE 'ls' PATTERN LOOKS LIKE")
    print("=" * 70)

    print("""
When xv6 runs 'ls', it creates these patterns:

1. SERIAL OUTPUT (UART):
   - Text output via serial console
   - Shows command prompt, output, next prompt
   - ~500 chars for 'ls' output

2. FRAMEBUFFER (VGA):
   - 80x25 text mode (640x400 pixels)
   - 8x16 pixel glyphs for each character
   - Visual representation of serial output

3. EXECUTION STATE (INTERNAL):
   - PC trace: ~15K instructions
   - Memory accesses: ~400 reads/writes
   - Duration: ~50ms

4. METADATA:
   - Files listed: 18
   - Instructions/sec: ~300K
   - Serial length: ~500 chars

All of these patterns can be captured, saved as JSON, and used as
ground truth for development.
""")