import pytest
from pathlib import Path
import numpy as np
from tools.glyph_isa_v2 import GlyphAssemblerV2, GlyphCPUv2, OpcodeMapV2

# Resolve from tests/ -> tools/spatial_examples/
PROJECT_ROOT = Path(__file__).parent.parent
EXAMPLE_DIR = PROJECT_ROOT / "tools" / "spatial_examples"


def load_and_run(asm_file: str, width_instrs: int = 8):
    """Helper to load, assemble, and run a program."""
    with open(EXAMPLE_DIR / asm_file) as f:
        lines = [line.strip() for line in f if line.strip() and not line.startswith('#')]
    
    opcode_map = OpcodeMapV2()
    assembler = GlyphAssemblerV2(opcode_map)
    image = assembler.assemble(lines, width_instrs=width_instrs)
    
    cpu = GlyphCPUv2(opcode_map, cols_instrs=width_instrs)
    cpu.run(image, max_instructions=1000)
    
    return cpu, image


class TestExampleArithmetic:
    """01_arithmetic.asm - Basic arithmetic operations."""
    
    def test_execution(self):
        cpu, _ = load_and_run("01_arithmetic.asm")
        # r1 = 5 + 3 = 8, r2 = 5 - 3 = 2, r3 is unused but has old value from padding
        assert cpu.registers[1] == 8
        assert cpu.registers[2] == 3  # The immediate 3 was loaded
        assert cpu.output == [8]
    
    def test_tile_dimensions(self):
        cpu, image = load_and_run("01_arithmetic.asm")
        # 7 instructions packed at 8 per row = 1 row
        assert image.shape[0] == 1
        assert image.shape[1] == 32  # 8 instructions * 4 pixels each


class TestExampleMemory:
    """04_memory.asm - Indirect memory load/store."""
    
    def test_execution(self):
        cpu, _ = load_and_run("04_memory.asm")
        # r1 = 100 (address), r2 = 42 (value stored), r3 = 42 (value loaded back)
        assert cpu.registers[1] == 100
        assert cpu.registers[2] == 42
        assert cpu.registers[3] == 42
        assert cpu.output == [42]


class TestSpatialIDERoundTrip:
    """Test spatial_ide.py produces consistent results."""
    
    def test_01_arithmetic_via_ide(self):
        import subprocess
        result = subprocess.run(
            ["python3", "tools/spatial_ide.py", "tools/spatial_examples/01_arithmetic.asm", "--no-audio", "--no-gpu"],
            capture_output=True,
            text=True
        )
        
        assert result.returncode == 0
        assert "CPU run:" in result.stdout
        # Check for expected register values in output
        assert "8" in result.stdout  # Output value


class TestExampleBranch:
    """02_branch.asm - CMP/JZ/JMP. Coordinates are (idx % width, idx // width)
    instruction units, not source line numbers - that mismatch was the bug."""

    def test_execution(self):
        cpu, _ = load_and_run("02_branch.asm")
        # r1 == r2 == 10, so JZ taken: r3 = 1, r0 (compare flag) = 1
        assert cpu.registers[0] == 1
        assert cpu.registers[3] == 1
        assert cpu.output == [1]

    def test_tile_dimensions(self):
        cpu, image = load_and_run("02_branch.asm")
        assert image.shape[0] == 2  # 13 instructions at 8/row = 2 rows
        assert image.shape[1] == 32


class TestExampleSubroutine:
    """03_subroutine.asm - CALL/RET/PUSH/POP. PUSH must save the
    post-increment value, not the pre-call one, or POP silently reverts it."""

    def test_execution(self):
        cpu, _ = load_and_run("03_subroutine.asm")
        assert cpu.registers[1] == 2  # accumulated across two CALLs
        assert cpu.output == [2]

    def test_tile_dimensions(self):
        cpu, image = load_and_run("03_subroutine.asm")
        assert image.shape[0] == 3  # 21 instructions at 8/row = 3 rows
        assert image.shape[1] == 32