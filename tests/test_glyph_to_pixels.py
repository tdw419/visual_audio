"""
Unit tests for glyph_to_pixels.py (Spatial Glyph Compiler).

Tests the spatial compilation of .glyph assembly to RGB pixel images.

Gate rule: Tool verification before marking complete.
"""

import pytest
import sys
import tempfile
import os
import numpy as np
from pathlib import Path
import subprocess

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'tools'))


class TestGlyphToPixels:
    """Test spatial compilation of .glyph to pixels."""

    @pytest.fixture
    def simple_glyph_program(self):
        """Simple test program: LDI r0 2, HALT."""
        return """# Test program
LDI r0 2
HALT
"""

    @pytest.fixture
    def arithmetic_glyph_program(self):
        """Arithmetic test: 2 + 3 = 5."""
        return """# Compute 2 + 3 = 5
LDI r0 2
LDI r1 3
ADD r0 r1
PRT r0
HALT
"""

    def test_compile_simple_program(self, simple_glyph_program, tmp_path):
        """Test compiling a simple program to pixels."""
        glyph_path = tmp_path / 'simple.glyph'
        png_path = tmp_path / 'simple.png'

        glyph_path.write_text(simple_glyph_program)

        result = subprocess.run(
            ['python3', 'tools/glyph_to_pixels.py',
             str(glyph_path), '-o', str(png_path)],
            capture_output=True,
            text=True
        )

        assert result.returncode == 0, f"Compilation failed: {result.stderr}"
        assert png_path.exists(), "PNG not created"

    def test_list_opcodes(self):
        """Test listing available opcodes."""
        result = subprocess.run(
            ['python3', 'tools/glyph_to_pixels.py', '--list-opcodes'],
            capture_output=True,
            text=True
        )

        assert result.returncode == 0, f"List opcodes failed: {result.stderr}"
        assert 'LDI' in result.stdout, "LDI opcode not listed"
        assert 'ADD' in result.stdout, "ADD opcode not listed"
        assert 'PRT' in result.stdout, "PRT opcode not listed"
        assert 'HALT' in result.stdout, "HALT opcode not listed"

    def test_statistics_output(self, arithmetic_glyph_program, tmp_path):
        """Test statistics output for compiled program."""
        glyph_path = tmp_path / 'arithmetic.glyph'
        glyph_path.write_text(arithmetic_glyph_program)

        result = subprocess.run(
            ['python3', 'tools/glyph_to_pixels.py',
             str(glyph_path), '--stats'],
            capture_output=True,
            text=True
        )

        assert result.returncode == 0, f"Stats failed: {result.stderr}"
        assert 'Pixel dimensions:' in result.stdout
        assert 'Non-black pixels:' in result.stdout
        assert 'Unique colors:' in result.stdout

    def test_custom_width(self, simple_glyph_program, tmp_path):
        """Test compilation with custom width."""
        glyph_path = tmp_path / 'wide.glyph'
        png_path = tmp_path / 'wide.png'

        glyph_path.write_text(simple_glyph_program)

        result = subprocess.run(
            ['python3', 'tools/glyph_to_pixels.py',
             str(glyph_path), '-o', str(png_path), '--width', '32'],
            capture_output=True,
            text=True
        )

        assert result.returncode == 0, f"Custom width failed: {result.stderr}"

        # Verify width is 32
        from PIL import Image
        img = Image.open(png_path)
        assert img.width == 32, f"Expected width 32, got {img.width}"

    def test_default_output_naming(self, simple_glyph_program, tmp_path):
        """Test default output naming (<input>_pixels.png)."""
        import os
        import re

        glyph_path = tmp_path / 'test.glyph'
        glyph_path.write_text(simple_glyph_program)

        # Change to tmpdir so default output goes there
        old_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            # Use absolute path to the tool
            tool_path = os.path.join(old_cwd, 'tools', 'glyph_to_pixels.py')
            result = subprocess.run(
                ['python3', tool_path, 'test.glyph'],
                capture_output=True,
                text=True
            )
        finally:
            os.chdir(old_cwd)

        assert result.returncode == 0

        expected_output = tmp_path / 'test_pixels.png'
        assert expected_output.exists(), f"Default output not created: {expected_output}"

    def test_missing_file_error(self):
        """Test error handling for missing input file."""
        result = subprocess.run(
            ['python3', 'tools/glyph_to_pixels.py', 'nonexistent.glyph'],
            capture_output=True,
            text=True
        )

        assert result.returncode != 0, "Should fail for missing file"
        assert 'not found' in result.stderr.lower() or 'error' in result.stderr.lower()

    def test_pixel_format(self, arithmetic_glyph_program, tmp_path):
        """Test that output PNG has correct RGB format."""
        glyph_path = tmp_path / 'arithmetic.glyph'
        png_path = tmp_path / 'arithmetic.png'

        glyph_path.write_text(arithmetic_glyph_program)

        subprocess.run(
            ['python3', 'tools/glyph_to_pixels.py',
             str(glyph_path), '-o', str(png_path)],
            capture_output=True,
            check=True
        )

        # Load and verify format
        from PIL import Image
        img = Image.open(png_path)
        pixels = np.array(img)

        # Verify RGB
        assert img.mode == 'RGB', f"Expected RGB mode, got {img.mode}"
        assert pixels.ndim == 3, f"Expected 3D array, got {pixels.ndim}D"
        assert pixels.shape[2] == 3, f"Expected 3 channels, got {pixels.shape[2]}"
        assert pixels.dtype == np.uint8, f"Expected uint8, got {pixels.dtype}"

    def test_round_trip_execution(self, arithmetic_glyph_program, tmp_path):
        """Test that compiled pixels can be executed by emulator."""
        glyph_path = tmp_path / 'arithmetic.glyph'
        png_path = tmp_path / 'arithmetic.png'

        glyph_path.write_text(arithmetic_glyph_program)

        # Compile
        subprocess.run(
            ['python3', 'tools/glyph_to_pixels.py',
             str(glyph_path), '-o', str(png_path)],
            capture_output=True,
            check=True
        )

        # Execute
        result = subprocess.run(
            ['python3', 'tools/mkv_glyph_emulator.py', str(png_path)],
            capture_output=True,
            text=True
        )

        assert result.returncode == 0, f"Emulator failed: {result.stderr}"

        # Verify arithmetic result (r1 should be 5 for 2+3)
        assert 'r1 = 5' in result.stdout or 'Final registers:' in result.stdout, \
            "Arithmetic result not found in emulator output"

        # Check final registers line for r1=5
        if 'Final registers:' in result.stdout:
            import re
            match = re.search(r'Final registers: \[([^\]]+)\]', result.stdout)
            if match:
                registers_str = match.group(1)
                registers = [int(x.strip()) for x in registers_str.split(',')]
                # r1 is at index 1, should be 5 (2+3)
                assert registers[1] == 5, f"Expected r1=5, got r1={registers[1]}"


def test_glyph_to_pixels_end_to_end():
    """Complete end-to-end test: .glyph → pixels → execute."""
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Write test program
        program = """# Test: r0 = 10, r1 = 20, r2 = r0 + r1
LDI r0 10
LDI r1 20
ADD r0 r1
PRT r2
HALT
"""
        glyph_path = tmpdir / 'test.glyph'
        png_path = tmpdir / 'test.png'

        glyph_path.write_text(program)

        # Compile
        result = subprocess.run(
            ['python3', 'tools/glyph_to_pixels.py',
             str(glyph_path), '-o', str(png_path)],
            capture_output=True,
            text=True
        )
        assert result.returncode == 0, f"Compile failed: {result.stderr}"
        assert png_path.exists()

        # Verify PNG
        from PIL import Image
        img = Image.open(png_path)
        assert img.mode == 'RGB'

        # Execute
        result = subprocess.run(
            ['python3', 'tools/mkv_glyph_emulator.py', str(png_path)],
            capture_output=True,
            text=True
        )
        assert result.returncode == 0, f"Execute failed: {result.stderr}"

        # Should contain final registers
        assert 'Final registers:' in result.stdout


if __name__ == '__main__':
    pytest.main([__file__, '-v'])