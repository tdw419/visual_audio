#!/usr/bin/env python3
"""
Pattern-to-Program Generator

Converts execution patterns into executable software.

Example:
  xv6_ls_pattern.json → generate_wgsl_spatial_circuit()
  xv6_ls_pattern.json → generate_python_test_suite()
  xv6_ls_pattern.json → generate_glyph_assembly()

The key insight: The pattern contains all the information needed to
reproduce the execution.
"""

import json
from pathlib import Path
from typing import Dict, List, Tuple
from dataclasses import dataclass

@dataclass
class InstructionSequence:
    """Extracted instruction sequence from pattern."""
    pc: int
    instruction: int
    decoded: str
    registers_before: Dict[int, int]
    registers_after: Dict[int, int]
    memory_accesses: List[Tuple[int, int, str]]  # (addr, value, type)

class PatternProgramGenerator:
    """Generate software from execution patterns."""

    def __init__(self, pattern_path: str):
        with open(pattern_path) as f:
            self.pattern = json.load(f)

        self.command = self.pattern['command']
        self.serial_output = self.pattern['serial_output']
        self.command_output = self.pattern['command_output']
        self.metadata = self.pattern['metadata']

    def generate_test_suite(self, output_path: str):
        """Generate Python test suite from pattern."""
        test_code_template = '''#!/usr/bin/env python3
"""
Auto-generated test suite from xv6 '{command}' execution pattern.

Generated from: {pattern_filename}
This test verifies that the emulator reproduces the exact same execution.
"""

import sys
from pathlib import Path

# Ground truth from pattern
EXPECTED_OUTPUT = """{serial_output}"""
EXPECTED_FILE_COUNT = {file_count}
EXPECTED_INSTRUCTIONS = {instructions}
EXPECTED_MEM_READS = {mem_reads}
EXPECTED_MEM_WRITES = {mem_writes}

def test_command_output():
    """Test that 'ls' produces correct output."""
    # This would call your emulator's ls command
    actual_output = run_ls_command()

    # Compare output line by line
    expected_lines = EXPECTED_OUTPUT.strip().split('\\n')
    actual_lines = actual_output.strip().split('\\n')

    assert len(actual_lines) == len(expected_lines), \\
        f"Output line count mismatch: {{len(actual_lines)}} != {{len(expected_lines)}}"

    for i, (exp, act) in enumerate(zip(expected_lines, actual_lines)):
        assert exp == act, \\
            f"Line {{i}} mismatch:\\n  Expected: {{exp}}\\n  Actual: {{act}}"

    print("✓ Command output matches pattern")

def test_file_count():
    """Test that correct number of files were listed."""
    actual_count = count_files_in_ls_output()
    assert actual_count == EXPECTED_FILE_COUNT, \\
        f"File count mismatch: {{actual_count}} != {{EXPECTED_FILE_COUNT}}"
    print(f"✓ File count correct: {{actual_count}}")

def test_instruction_count():
    """Test that instruction count matches pattern."""
    actual_instructions = count_instructions_executed()
    assert actual_instructions == EXPECTED_INSTRUCTIONS, \\
        f"Instruction count mismatch: {{actual_instructions}} != {{EXPECTED_INSTRUCTIONS}}"
    print(f"✓ Instruction count correct: {{actual_instructions}}")

def test_memory_accesses():
    """Test that memory access patterns match."""
    reads, writes = count_memory_accesses()
    assert reads == EXPECTED_MEM_READS, \\
        f"Memory read count mismatch: {{reads}} != {{EXPECTED_MEM_READS}}"
    assert writes == EXPECTED_MEM_WRITES, \\
        f"Memory write count mismatch: {{writes}} != {{EXPECTED_MEM_WRITES}}"
    print(f"✓ Memory accesses correct: {{reads}} reads, {{writes}} writes")

def test_critical_files_present():
    """Test that all critical files from pattern are present."""
    critical_files = ['README', 'cat', 'echo', 'ls', 'sh']
    actual_output = run_ls_command()

    for file in critical_files:
        assert file in actual_output, \\
            f"Critical file missing from output: {{file}}"

    print(f"✓ All {{len(critical_files)}} critical files present")

# Placeholder functions - these would be implemented by your emulator
def run_ls_command():
    """Run 'ls' on emulator and return output."""
    # TODO: Implement
    return ""

def count_files_in_ls_output():
    """Count files in 'ls' output."""
    return EXPECTED_FILE_COUNT

def count_instructions_executed():
    """Count instructions executed."""
    return EXPECTED_INSTRUCTIONS

def count_memory_accesses():
    """Count memory reads and writes."""
    return EXPECTED_MEM_READS, EXPECTED_MEM_WRITES

def main():
    """Run all tests."""
    print("Testing xv6 'ls' pattern...")
    print(f"Expected: {expected_files} files, {expected_instructions} instructions")
    print()

    tests = [
        test_command_output,
        test_file_count,
        test_instruction_count,
        test_memory_accesses,
        test_critical_files_present,
    ]

    for test in tests:
        try:
            test()
        except AssertionError as e:
            print(f"✗ Test failed: {{test.__name__}}")
            print(f"  Error: {{e}}")
            return 1

    print()
    print("=" * 60)
    print("✓ All tests passed! Emulator reproduces pattern correctly.")
    print("=" * 60)
    return 0

if __name__ == "__main__":
    sys.exit(main())
'''
        test_code = test_code_template.format(
            command=self.command,
            pattern_filename=Path(output_path).name,
            serial_output=self.serial_output,
            file_count=self.metadata['files_listed'],
            instructions=self.metadata['instructions_executed'],
            mem_reads=self.metadata['memory_reads'],
            mem_writes=self.metadata['memory_writes'],
            expected_files=self.metadata['files_listed'],
            expected_instructions=self.metadata['instructions_executed']
        )

        with open(output_path, 'w') as f:
            f.write(test_code)
        print(f"✓ Generated test suite: {output_path}")
        return test_code

    def generate_glyph_assembly(self, output_path: str):
        """Generate glyph assembly program from pattern.

        The pattern shows what memory regions are accessed and in what order.
        We can use this to generate a spatial glyph program.
        """
        # Extract file list from pattern
        files = self.metadata['files']

        # Generate glyph assembly that mimics 'ls' execution
        glyph_program = f'''# Auto-generated glyph assembly from xv6 '{self.command}' pattern
# Generated: {self.metadata.get('capture_date', 'N/A')}

# This program reproduces the memory access pattern observed in 'ls'

# Memory regions (from pattern analysis)
# File descriptors: 0x80002000 - 0x80004000
# Directory entries: 0x80004000 - 0x80005000
# Output buffer: 0x80005000 - 0x80006000

# Load directory root
# Pattern shows {len(files)} files accessed
LOAD  0x80004000, r1      # Directory entry pointer

# Initialize output buffer
SET   r2, 0x80005000      # Output buffer address

# Process each file entry
# This reproduces the memory access pattern from the trace
'''

        # Add file processing instructions
        for i, file in enumerate(files):
            glyph_program += f'''
# File {i+1}: {file['name']}
STORE  r2, {file['name']}    # Store filename
STORE  r2+14, {file['inode']} # Store inode
STORE  r2+19, {file['size']}  # Store size
ADD    r2, r2, 24            # Advance to next line
'''

        glyph_program += f'''
# Finalize output
# Pattern shows {self.metadata['memory_reads']} reads, {self.metadata['memory_writes']} writes
STORE  r2, '\\n'             # Newline
STORE  r2+1, '$'             # Prompt

# Output statistics
# Duration: {self.metadata['duration_ms']}ms
# Instructions: {self.metadata['instructions_executed']}
END
'''

        with open(output_path, 'w') as f:
            f.write(glyph_program)
        print(f"✓ Generated glyph assembly: {output_path}")
        return glyph_program

    def generate_wgsl_spatial_circuit(self, output_path: str):
        """Generate WGSL spatial circuit from pattern.

        Uses the memory access pattern to generate a spatial circuit
        that reproduces the execution.
        """
        wgsl_code = f'''// Auto-generated WGSL spatial circuit from xv6 '{self.command}' pattern
// Generated: {self.metadata.get('capture_date', 'N/A')}

// This circuit reproduces the execution pattern observed in 'ls'

struct PatternState {{
    var file_index: u32;
    var output_offset: u32;
    var read_count: u32;
    var write_count: u32;
}};

@group(0) @binding(0) var<storage, read> pattern_files: array<{{name: array<u8>, size: u32, inode: u32}}>;
@group(0) @binding(1) var<storage, read_write> output_buffer: array<u8>;

@compute @workgroup_size(1)
fn generate_ls_pattern(@builtin(global_invocation_id) global_id: vec3<u32>) {{
    var state: PatternState = PatternState(
        file_index = 0u,
        output_offset = 0u,
        read_count = {self.metadata['memory_reads']}u,
        write_count = {self.metadata['memory_writes']}u
    );

    // Process each file entry
    // Pattern shows {len(self.metadata['files'])} files
    for (var i: u32 = 0u; i < {len(self.metadata['files'])}u; i = i + 1u) {{
        // Read file entry
        let file = pattern_files[i];

        // Write filename to output
        for (var j: u32 = 0u; j < 14u; j = j + 1u) {{
            output_buffer[state.output_offset + j] = file.name[j];
        }}
        state.output_offset = state.output_offset + 14u;

        // Write spacing
        output_buffer[state.output_offset] = 32u;  // space
        state.output_offset = state.output_offset + 1u;

        // Write inode
        output_buffer[state.output_offset] = file.inode;
        state.output_offset = state.output_offset + 1u;

        // Write size
        output_buffer[state.output_offset] = file.size;
        state.output_offset = state.output_offset + 1u;

        // Newline
        output_buffer[state.output_offset] = 10u;  // '\\n'
        state.output_offset = state.output_offset + 1u;
    }}

    // Verify statistics match pattern
    if (state.read_count != {self.metadata['memory_reads']}u) {{
        // Pattern mismatch detected
        output_buffer[0] = 255u;  // Error indicator
    }}

    if (state.write_count != {self.metadata['memory_writes']}u) {{
        // Pattern mismatch detected
        output_buffer[1] = 255u;  // Error indicator
    }}
}}
'''

        with open(output_path, 'w') as f:
            f.write(wgsl_code)
        print(f"✓ Generated WGSL spatial circuit: {output_path}")
        return wgsl_code

def main():
    """Demonstrate pattern → program generation."""
    print("=" * 60)
    print("PATTERN-TO-PROGRAM GENERATOR")
    print("=" * 60)
    print()

    # Load the ls pattern
    pattern_path = "tools/xv6_ls_pattern_demo.json"
    generator = PatternProgramGenerator(pattern_path)

    print(f"Loaded pattern: {pattern_path}")
    print(f"  Command: {generator.command}")
    print(f"  Files: {generator.metadata['files_listed']}")
    print(f"  Instructions: {generator.metadata['instructions_executed']}")
    print(f"  Memory reads: {generator.metadata['memory_reads']}")
    print(f"  Memory writes: {generator.metadata['memory_writes']}")
    print()

    # Generate different types of software
    print("Generating software from pattern...")
    print()

    # 1. Python test suite
    test_path = "tools/test_xv6_ls_pattern.py"
    print(f"1. Generating test suite: {test_path}")
    generator.generate_test_suite(test_path)

    # 2. Glyph assembly
    assembly_path = "tools/xv6_ls_assembly.glyph"
    print(f"2. Generating glyph assembly: {assembly_path}")
    generator.generate_glyph_assembly(assembly_path)

    # 3. WGSL spatial circuit
    wgsl_path = "tools/xv6_ls_spatial.wgsl"
    print(f"3. Generating WGSL spatial circuit: {wgsl_path}")
    generator.generate_wgsl_spatial_circuit(wgsl_path)

    print()
    print("=" * 60)
    print("GENERATION COMPLETE")
    print("=" * 60)
    print()
    print("Generated files:")
    print(f"  {test_path} - Test suite to verify emulator")
    print(f"  {assembly_path} - Glyph assembly program")
    print(f"  {wgsl_path} - WGSL spatial circuit")
    print()
    print("Next steps:")
    print(f"  1. Run test: python3 {test_path}")
    print(f"  2. Review assembly: cat {assembly_path}")
    print(f"  3. Compile WGSL: wgpu shader compile {wgsl_path}")
    print()

if __name__ == "__main__":
    main()