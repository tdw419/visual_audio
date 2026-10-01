"""
End-to-end differential test suite for RV32I/RV64I to Glyph ISA v2 transpiler (tools/rv64i_to_glyph.py).

Verifies bit-for-bit differential execution between:
1. GPU SpatialRV64ICore (hardware WGPU / WGSL compute execution)
2. GlyphCPUv2 (Geometry OS Spatial Glyph ISA v2 interpreter)
"""

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import pytest

from tools.glyph_isa_v2 import GlyphCPUv2, OpcodeMapV2
from tools.rv64i_to_glyph import (
    assemble_glyph_to_pixels,
    parse_elf,
    transpile_elf_to_glyph,
    transpile_rv32i_to_glyph,
)
from tools.spatial_rv64i_cpu import SpatialRV64ICore

_FIXTURES_DIR = Path(__file__).parent / "fixtures"
_GCC_BIN = shutil.which("riscv64-unknown-elf-gcc")
_OBJCOPY_BIN = shutil.which("riscv64-unknown-elf-objcopy")


@pytest.fixture
def requires_riscv_gcc():
    if not _GCC_BIN or not _OBJCOPY_BIN:
        pytest.skip("riscv64-unknown-elf toolchain not found")


def test_transpile_arithmetic():
    """Verify basic arithmetic instructions transpile and execute correctly."""
    # Program:
    #   addi a0, zero, 15    ; a0 = 15
    #   addi a1, zero, 25    ; a1 = 25
    #   add  a2, a0, a1      ; a2 = 40
    #   sub  a3, a2, a0      ; a3 = 25
    #   andi a4, a3, 0x0F    ; a4 = 25 & 15 = 9
    #   xori a5, a4, 0xFF    ; a5 = 9 ^ 255 = 246
    #   slli a6, a4, 2       ; a6 = 9 << 2 = 36
    #   ecall                ; halt
    instrs = [
        0x00F00513,  # addi a0, zero, 15
        0x01900593,  # addi a1, zero, 25
        0x00B50633,  # add  a2, a0, a1
        0x40A606B3,  # sub  a3, a2, a0
        0x00F6F713,  # andi a4, a3, 15
        0x0FF74793,  # xori a5, a4, 255
        0x00271813,  # slli a6, a4, 2
        0x00000073,  # ecall
    ]
    raw_bytes = b"".join(i.to_bytes(4, "little") for i in instrs)

    glyph_code = transpile_rv32i_to_glyph(raw_bytes, entry_symbol=None)
    pixels, _ = assemble_glyph_to_pixels(glyph_code, cols_instrs=32, min_rows=8)

    op_map = OpcodeMapV2()
    cpu = GlyphCPUv2(op_map, cols_instrs=32)
    cpu.pc = (0, 0)
    cpu.running = True

    for _ in range(200):
        if not cpu.step(pixels):
            break

    # Check register values: a0-a6 map to r10-r16
    assert cpu.registers[10] == 15
    assert cpu.registers[11] == 25
    assert cpu.registers[12] == 40
    assert cpu.registers[13] == 25
    assert cpu.registers[14] == 9
    assert cpu.registers[15] == 246
    assert cpu.registers[16] == 36


def test_transpile_branch_and_loop():
    """Verify branches (BEQ, BNE) and looping transpile and execute correctly."""
    # Program: sum numbers from 1 to 5
    #   addi a0, zero, 0     ; sum = 0
    #   addi a1, zero, 1     ; i = 1
    #   addi a2, zero, 6     ; limit = 6
    # loop:
    #   beq  a1, a2, done    ; if (i == 6) goto done
    #   add  a0, a0, a1      ; sum += i
    #   addi a1, a1, 1       ; i++
    #   jal  zero, loop      ; j loop
    # done:
    #   ecall                ; halt
    instrs = [
        0x00000513,  # 0x00: addi a0, zero, 0
        0x00100593,  # 0x04: addi a1, zero, 1
        0x00600613,  # 0x08: addi a2, zero, 6
        0x00C58863,  # 0x0C: beq  a1, a2, 0x10 (done at 0x1C)
        0x00B50533,  # 0x10: add  a0, a0, a1
        0x00158593,  # 0x14: addi a1, a1, 1
        0xFF5FF06F,  # 0x18: jal  zero, -12 (loop at 0x0C)
        0x00000073,  # 0x1C: ecall
    ]
    raw_bytes = b"".join(i.to_bytes(4, "little") for i in instrs)

    glyph_code = transpile_rv32i_to_glyph(raw_bytes, entry_symbol=None)
    pixels, _ = assemble_glyph_to_pixels(glyph_code, cols_instrs=32, min_rows=8)

    op_map = OpcodeMapV2()
    cpu = GlyphCPUv2(op_map, cols_instrs=32)
    cpu.pc = (0, 0)
    cpu.running = True

    for _ in range(500):
        if not cpu.step(pixels):
            break

    # Sum of 1+2+3+4+5 = 15
    assert cpu.registers[10] == 15
    assert cpu.registers[11] == 6


def test_transpile_bump_alloc_differential(requires_riscv_gcc):
    """
    Gold-standard differential test oracle.

    Compiles tests/fixtures/bump_alloc.c to an RV32I ELF, runs it on GPU
    SpatialRV64ICore, transpiles it with rv64i_to_glyph.py, runs it on
    GlyphCPUv2, and asserts bit-identical return values and memory layout.
    """
    c_source = _FIXTURES_DIR / "bump_alloc.c"
    assert c_source.exists(), f"Fixture {c_source} not found"

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        elf_path = tmp / "bump_alloc.elf"
        bin_path = tmp / "bump_alloc.bin"
        glyph_path = tmp / "bump_alloc.glyph"

        # 1. Compile C code with riscv64 GCC (-march=rv32i)
        compile_cmd = [
            _GCC_BIN,
            "-march=rv32i",
            "-mabi=ilp32",
            "-O1",
            "-nostdlib",
            "-Wl,-Ttext=0x0",
            "-Wl,--section-start=.data=0x200",
            "-Wl,--section-start=.sdata=0x208",
            "-Wl,--section-start=.sbss=0x210",
            "-Wl,--section-start=.bss=0x218",
            str(c_source),
            "-o", str(elf_path),
        ]
        res = subprocess.run(compile_cmd, capture_output=True, text=True)
        assert res.returncode == 0, f"Compilation failed: {res.stderr}"

        # 2. Extract binary memory image for SpatialRV64ICore
        objcopy_cmd = [
            _OBJCOPY_BIN,
            "-O", "binary",
            str(elf_path),
            str(bin_path),
        ]
        res = subprocess.run(objcopy_cmd, capture_output=True, text=True)
        assert res.returncode == 0, f"Objcopy failed: {res.stderr}"
        bin_data = bin_path.read_bytes()

        # Parse symbols to get entry point for SpatialRV64ICore
        elf_bytes = elf_path.read_bytes()
        text_vaddr, text_bytes, symbols = parse_elf(elf_bytes)
        entry_addr = None
        for addr, name in symbols.items():
            if name == "_start":
                entry_addr = addr
                break
        assert entry_addr is not None, "Could not find _start in ELF symbols"

        # 3. Execute on GPU SpatialRV64ICore
        core = SpatialRV64ICore(4096)
        core.load_program(bin_data, entry_point=entry_addr)
        gpu_state = core.run_until_halt(max_cycles=10000, chunk_size=64)

        gpu_halted = gpu_state["halted"]
        gpu_a0 = gpu_state["regs"][10][0]
        gpu_mem_100 = core.read_mem_word(0x100)
        gpu_mem_104 = core.read_mem_word(0x104)
        gpu_mem_108 = core.read_mem_word(0x108)
        gpu_mem_118 = core.read_mem_word(0x118)
        gpu_mem_208 = core.read_mem_word(0x208)

        assert gpu_halted == 1, "GPU SpatialRV64ICore failed to halt cleanly"

        # Expected return checksum: 0xAA11BB22 ^ 0xDEADBEEF ^ 0xCAFEBABE
        expected_checksum = 0xAA11BB22 ^ 0xDEADBEEF ^ 0xCAFEBABE
        assert gpu_a0 == expected_checksum
        assert gpu_mem_100 == 0xAA11BB22
        assert gpu_mem_104 == 0x33445566
        assert gpu_mem_108 == 0xDEADBEEF
        assert gpu_mem_118 == 0xCAFEBABE
        assert gpu_mem_208 == 284

        # 4. Transpile ELF to Glyph Assembly using rv64i_to_glyph
        glyph_source = transpile_elf_to_glyph(
            elf_bytes,
            entry_symbol="_start",
            byte_to_word_mem=True,
        )
        glyph_path.write_text(glyph_source)

        # 5. Assemble to 2D spatial pixel buffer
        pixels, _ = assemble_glyph_to_pixels(glyph_source, cols_instrs=64, min_rows=16)

        # 6. Execute on GlyphCPUv2
        op_map = OpcodeMapV2()
        cpu = GlyphCPUv2(op_map, cols_instrs=64)
        cpu.memory = [0] * 8192
        cpu.pc = (0, 0)
        cpu.running = True

        for _ in range(5000):
            if not cpu.step(pixels):
                break

        assert not cpu.running, "GlyphCPUv2 failed to halt cleanly"

        glyph_a0 = cpu.registers[10]
        glyph_mem_100 = cpu.memory[0x100 >> 2]
        glyph_mem_104 = cpu.memory[0x104 >> 2]
        glyph_mem_108 = cpu.memory[0x108 >> 2]
        glyph_mem_118 = cpu.memory[0x118 >> 2]
        glyph_mem_208 = cpu.memory[0x208 >> 2]

        # 7. Assert bit-identical results between GPU and Glyph CPU
        assert glyph_a0 == gpu_a0 == expected_checksum, (
            f"Checksum mismatch: GPU 0x{gpu_a0:08x} vs Glyph 0x{glyph_a0:08x}"
        )
        assert glyph_mem_100 == gpu_mem_100 == 0xAA11BB22
        assert glyph_mem_104 == gpu_mem_104 == 0x33445566
        assert glyph_mem_108 == gpu_mem_108 == 0xDEADBEEF
        assert glyph_mem_118 == gpu_mem_118 == 0xCAFEBABE
        assert glyph_mem_208 == gpu_mem_208 == 284


def test_cli_interface(requires_riscv_gcc):
    """Test tools/rv64i_to_glyph.py command-line interface."""
    c_source = _FIXTURES_DIR / "bump_alloc.c"

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        elf_path = tmp / "bump_alloc.elf"
        glyph_out = tmp / "test.glyph"
        png_out = tmp / "test.png"

        # Compile
        subprocess.run([
            _GCC_BIN, "-march=rv32i", "-mabi=ilp32", "-O1", "-nostdlib",
            str(c_source), "-o", str(elf_path)
        ], check=True)

        # CLI: generate .glyph
        res = subprocess.run([
            sys.executable, "tools/rv64i_to_glyph.py",
            str(elf_path), "-o", str(glyph_out)
        ], capture_output=True, text=True)
        assert res.returncode == 0
        assert glyph_out.exists()
        assert ":bump_alloc" in glyph_out.read_text()

        # CLI: generate .png
        res = subprocess.run([
            sys.executable, "tools/rv64i_to_glyph.py",
            str(elf_path), "--assemble", "-o", str(png_out)
        ], capture_output=True, text=True)
        assert res.returncode == 0
        assert png_out.exists()
        assert png_out.stat().st_size > 0
