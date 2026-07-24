"""
Test suite for llm_to_glyph.py — LLM command to GlyphISA bridge

Verifies the translation layer that turns LLM JSON commands into
spatial CPU execution via pixel programs.
"""

import pytest
import json
import tempfile
import sys
from pathlib import Path

# Add visual_audio root to path for importing llm_to_glyph
sys.path.insert(0, str(Path(__file__).parent))

from tools.glyph_isa_v2 import OpcodeMapV2, GlyphAssemblerV2, GlyphCPUv2

# Import the llm_to_glyph functions directly
from llm_to_glyph import compile_llm_command, assemble_to_pixels, GLYPH_MACROS


class TestCompileLLMCommand:
    """Test LLM JSON command to glyph assembly compilation."""

    def test_clear_screen_macro(self):
        """CLEAR_SCREEN command maps to correct LDI instructions."""
        json_cmd = {"command": "CLEAR_SCREEN", "params": {"r": 0, "g": 0, "b": 255}}
        assembly = compile_llm_command(json_cmd)

        assert "LDI r1 0" in assembly
        assert "LDI r2 0" in assembly
        assert "LDI r3 255" in assembly
        assert "HALT" in assembly

    def test_set_pixel_macro(self):
        """SET_PIXEL command maps to correct LDI sequence."""
        json_cmd = {
            "command": "SET_PIXEL",
            "params": {"x": 100, "y": 200, "r": 128, "g": 64, "b": 32}
        }
        assembly = compile_llm_command(json_cmd)

        assert "LDI r1 100" in assembly
        assert "LDI r2 200" in assembly
        assert "LDI r3 128" in assembly
        assert "LDI r4 64" in assembly
        assert "LDI r5 32" in assembly
        assert "HALT" in assembly

    def test_unknown_command_raises(self):
        """Unknown command raises ValueError."""
        json_cmd = {"command": "INVALID_OP", "params": {}}

        with pytest.raises(ValueError, match="Unknown command"):
            compile_llm_command(json_cmd)

    def test_missing_params_uses_defaults(self):
        """Missing params use template defaults (if any)."""
        json_cmd = {"command": "HALT", "params": {}}
        assembly = compile_llm_command(json_cmd)

        assert assembly == "HALT"


class TestAssembleToPixels:
    """Test assembly to pixel image conversion."""

    def test_clear_screen_assembly_executes(self):
        """CLEAR_SCREEN assembly executes correctly on GlyphCPUv2."""
        op_map = OpcodeMapV2()
        cpu = GlyphCPUv2(op_map, cols_instrs=8)

        json_cmd = {"command": "CLEAR_SCREEN", "params": {"r": 255, "g": 0, "b": 0}}
        assembly = compile_llm_command(json_cmd)

        image = assemble_to_pixels(assembly)
        n = cpu.run(image)

        assert n == 4  # LDI r1, LDI r2, LDI r3, HALT
        assert cpu.registers[1] == 255
        assert cpu.registers[2] == 0
        assert cpu.registers[3] == 0

    def test_orange_screen_roundtrip(self):
        """Orange screen command executes and verifies correctly."""
        op_map = OpcodeMapV2()
        cpu = GlyphCPUv2(op_map, cols_instrs=8)

        json_cmd = {"command": "CLEAR_SCREEN", "params": {"r": 255, "g": 128, "b": 0}}
        assembly = compile_llm_command(json_cmd)

        image = assemble_to_pixels(assembly)
        cpu.run(image)

        assert cpu.registers[1] == 255
        assert cpu.registers[2] == 128
        assert cpu.registers[3] == 0

    def test_image_shape_correct(self):
        """Generated image has expected shape."""
        json_cmd = {"command": "CLEAR_SCREEN", "params": {"r": 0, "g": 255, "b": 0}}
        assembly = compile_llm_command(json_cmd)

        image = assemble_to_pixels(assembly)

        # Default width_instrs=8 in assemble_to_pixels
        # 8 instructions × 4 pixels each = 32 pixels wide
        # 1 row (all instructions fit)
        assert image.shape[1] == 32  # Width in pixels
        assert image.shape[0] == 1  # Height in rows


class TestFileInterface:
    """Test file-based JSON command processing."""

    def test_json_file_to_png(self):
        """Complete flow: JSON file → assembly → PNG → CPU execution."""
        op_map = OpcodeMapV2()
        cpu = GlyphCPUv2(op_map, cols_instrs=8)

        # Create temporary JSON file
        json_data = {"command": "CLEAR_SCREEN", "params": {"r": 128, "g": 128, "b": 128}}
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(json_data, f)
            json_path = f.name

        # Create temporary PNG output
        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as f:
            png_path = f.name

        try:
            # Process via llm_to_glyph (simulating main() logic)
            assembly = compile_llm_command(json_data)
            image = assemble_to_pixels(assembly, png_path)

            # Verify PNG exists and can be loaded
            from PIL import Image
            img = Image.open(png_path)
            assert img.size == (32, 1)  # 32×1 pixel image (8 instrs × 4 pixels)

            # Verify execution
            n = cpu.run(image)
            assert n == 4
            assert cpu.registers[1] == 128
            assert cpu.registers[2] == 128
            assert cpu.registers[3] == 128
        finally:
            # Cleanup
            Path(json_path).unlink(missing_ok=True)
            Path(png_path).unlink(missing_ok=True)


class TestMacroCoverage:
    """Verify all macros in GLYPH_MACROS are functional."""

    def test_all_macros_execute(self):
        """Every defined macro can be assembled and executed."""
        op_map = OpcodeMapV2()
        cpu = GlyphCPUv2(op_map, cols_instrs=8)

        for command, template in GLYPH_MACROS.items():
            # Build minimal params for each macro
            if command == "CLEAR_SCREEN":
                params = {"r": 0, "g": 0, "b": 0}
            elif command == "SET_PIXEL":
                params = {"x": 0, "y": 0, "r": 0, "g": 0, "b": 0}
            elif command == "DRAW_RECT":
                params = {"x": 0, "y": 0, "w": 10, "h": 10}
            elif command in ("HALT", "NOOP"):
                params = {}
            else:
                params = {}

            json_cmd = {"command": command, "params": params}
            assembly = compile_llm_command(json_cmd)

            # Should assemble without error
            image = assemble_to_pixels(assembly)

            # Should execute without error
            n = cpu.run(image)
            assert n > 0, f"{command} produced 0 instructions"