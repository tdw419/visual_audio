"""
Test real SYSCALL_FILE_WRITE and SYSCALL_FILE_READ.

This proves spatial programs can actually write and read files from the host
filesystem, not just print stub messages.
"""
import os
import tempfile
from pathlib import Path

import numpy as np
import pytest

from tools.glyph_isa_v2 import GlyphAssemblerV2, GlyphCPUv2, OpcodeMapV2


def test_syscall_file_write_read():
    """Spatial program writes a file, reads it back, verifies roundtrip."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Simpler approach: pre-load path and data via direct memory writes,
        # then use a tiny program to invoke the syscalls
        opcode_map = OpcodeMapV2()
        assembler = GlyphAssemblerV2(opcode_map)

        test_path = Path(tmpdir) / "spatial_test.txt"
        test_data = b"Hello from spatial memory!"
        test_len = len(test_data)  # 26 bytes

        # BK-44: the engine's 0x03/0x04 host arms require the path under a
        # GLYPH_FS_ALLOW root (deny-by-default, same model as 0x13). Arm
        # the fixture root for this roundtrip; restored after.
        _old_allow = os.environ.get("GLYPH_FS_ALLOW")
        os.environ["GLYPH_FS_ALLOW"] = str(Path(tmpdir).resolve())
        try:
            _run_roundtrip(opcode_map, assembler, test_path, test_data)
        finally:
            if _old_allow is None:
                os.environ.pop("GLYPH_FS_ALLOW", None)
            else:
                os.environ["GLYPH_FS_ALLOW"] = _old_allow


def _run_roundtrip(opcode_map, assembler, test_path, test_data):
        # Minimal syscall program: invoke FILE_WRITE (0x03)
        # Use addresses that fit within the instruction image width (32 pixels per row)
        # Instructions take 8*4=32 pixels, so we use addresses starting at 32 (row 1, col 0)
        syscall_program = [
            "LDI r1 32",           # r1 = path address (row 1, col 0)
            "LDI r2 96",           # r2 = data address (row 3, col 0)
            "LDI r3 26",           # r3 = length (26 bytes for "Hello from spatial memory!")
            "SYSCALL r0 0x03",     # FILE_WRITE
            "LDI r1 32",           # r1 = path address (read back)
            "LDI r2 128",          # r2 = destination address (row 4, col 0)
            "LDI r3 26",           # r3 = length
            "SYSCALL r4 0x04",     # FILE_READ, result in r4
            "HALT",
        ]
        
        # Create a larger image with enough rows for our data
        # We need at least row 4 (addr 128) for the read destination
        # Instructions take 8*4=32 pixels per row
        image = assembler.assemble(syscall_program, width_instrs=8)
        
        # Extend the image to have enough rows (5 rows minimum)
        current_rows = image.shape[0]
        if current_rows < 5:
            new_image = np.zeros((5, image.shape[1], 3), dtype=np.uint8)
            new_image[:current_rows] = image
            image = new_image
        
        cpu = GlyphCPUv2(opcode_map, cols_instrs=8)
        
        # Pre-load path string into memory (addr 32+). PATH is data: seed
        # the RAM view directly (DEFECT-23-ROOT convention); image-side
        # seeding relied on _read_path's view-merge, retired 2026-09-22
        # (claim-queue item 2 step 2).
        path_str = str(test_path)
        for i, ch in enumerate(path_str + '\0'):
            cpu.memory[32 + i] = ord(ch)
        
        # backlog(d)/DEFECT-D (2026-09-16, handler 3/5): FILE_WRITE's data
        # arg migrated from image space to RAM - seed cpu.memory directly
        # (the pre-migration _mem_write image-seeding is now invisible to
        # the handler: addr 96 is below the FS window, so there is no
        # write-through mirror and the RAM read would see zeros).
        for i, byte_val in enumerate(test_data):
            cpu.memory[96 + i] = byte_val
        
        # Run the program
        cpu.run(image)
        
        # Verify the file was actually written
        assert test_path.exists(), f"File not created: {test_path}"
        actual = test_path.read_bytes()
        assert actual == test_data, f"Data mismatch: {actual!r} != {test_data!r}"
        
        # Verify the read syscall returned the correct length
        read_len = cpu.registers[4]  # result from FILE_READ
        assert read_len == len(test_data), f"Read length mismatch: {read_len} != {len(test_data)}"
        
        # Verify the data was read back into RAM (addr 128+). FILE_READ's
        # dest migrated from image space to RAM 2026-09-16 (backlog (d)
        # handler 2/5) - cpu.memory, not _mem_read(image, ...), is where
        # it lands now. FILE_WRITE's (0x03) data arg migrated the same
        # day (handler 3/5) - the data seeded into cpu.memory above is
        # what reached the disk.
        for i, byte_val in enumerate(test_data):
            mem_val = cpu.memory[128 + i] & 0xFF
            assert mem_val == byte_val, f"RAM mismatch at {128+i}: {mem_val} != {byte_val}"
        
        opcode_map.close()


def test_syscall_file_read_not_found():
    """Verify FILE_READ returns -1 for missing files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        missing_path = Path(tmpdir) / "does_not_exist.txt"
        
        opcode_map = OpcodeMapV2()
        assembler = GlyphAssemblerV2(opcode_map)
        
        syscall_program = [
            "LDI r1 32",
            "LDI r2 96",
            "LDI r3 10",
            "SYSCALL r0 0x04",     # FILE_READ, result in r0
            "HALT",
        ]
        
        image = assembler.assemble(syscall_program, width_instrs=8)
        
        # Extend for data
        current_rows = image.shape[0]
        if current_rows < 3:
            new_image = np.zeros((3, image.shape[1], 3), dtype=np.uint8)
            new_image[:current_rows] = image
            image = new_image
        
        cpu = GlyphCPUv2(opcode_map, cols_instrs=8)
        
        # Pre-load path
        for i, ch in enumerate(str(missing_path) + '\0'):
            cpu.memory[32 + i] = ord(ch)
        
        cpu.run(image)
        
        # Should return -1 (file not found)
        assert cpu.registers[0] == -1, "FILE_READ should return -1 for missing file"
        
        opcode_map.close()


if __name__ == '__main__':
    test_syscall_file_write_read()
    test_syscall_file_read_not_found()
    print("All file I/O tests passed!")