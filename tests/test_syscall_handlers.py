#!/usr/bin/env python3
"""
Test suite for SYSCALL handlers in GlyphCPUv2.

Tests:
  1. SYSCALL_BOOT_LINUX (0x10) - Boot Linux from spatial block device
  2. SYSCALL_STORE_CODE (0x11) - Write code payload to memory region
"""

import pytest
import numpy as np
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))
from glyph_isa_v2 import OpcodeMapV2, GlyphAssemblerV2, GlyphCPUv2


class TestBootLinuxSyscall:
    """Test SYSCALL_BOOT_LINUX (0x10)"""

    def test_boot_linux_invalid_signature(self):
        """Test BOOT_LINUX syscall with invalid VAC2 signature"""
        op_map = OpcodeMapV2()
        assembler = GlyphAssemblerV2(op_map)

        program = [
            'LDI r1 0x1000',      # container_addr at 0x1000 (invalid signature)
            'LDI r2 0x05',        # flags: graphical + cognitive
            'SYSCALL r3 0x10',    # BOOT_LINUX syscall
            'HALT',
        ]

        image = assembler.assemble(program, width_instrs=4)
        if image.shape[0] * image.shape[1] <= 0x1001:
            min_rows = (0x1001 // image.shape[1]) + 2
            image = np.pad(image, ((0, min_rows - image.shape[0]), (0, 0), (0, 0)))
        cpu = GlyphCPUv2(op_map, cols_instrs=4)
        cpu.run(image)

        # Should return -1 for invalid signature
        assert cpu.registers[3] == -1

        op_map.close()

    def test_boot_linux_valid_vac2_container(self):
        """Test BOOT_LINUX syscall with valid VAC2 container signature"""
        op_map = OpcodeMapV2()
        assembler = GlyphAssemblerV2(op_map)

        # VAC2 signature = 0x56414332 ('VAC2')
        # Storage format: byte[0]=0x56, byte[1]=0x41, byte[2]=0x43, byte[3]=0x32
        # Pixel 0: B=byte[0], G=byte[1], R=byte[2] → B=0x56, G=0x41, R=0x43 → 0x434156
        # Pixel 1: B=byte[3] → B=0x32 → 0x000032
        sig_pixel0 = 0x434156

        # offset = 346 frames * 4096 pixels/frame * 3 bytes/pixel = 4259840
        payload_offset = 4259840
        payload_low = payload_offset & 0xFFFFFF
        payload_high = (payload_offset >> 24) & 0xFFFFFF

        # 638MB = 668379136 bytes
        weights_size = 668379136
        weights_low = weights_size & 0xFFFFFF
        weights_high = (weights_size >> 24) & 0xFFFFFF

        program = [
            # Call BOOT_LINUX syscall
            'LDI r1 0x1000',     # container_addr
            'LDI r2 0x05',       # flags: graphical + cognitive
            'SYSCALL r6 0x10',   # BOOT_LINUX syscall, result in r6
            'HALT',
        ]

        image = assembler.assemble(program, width_instrs=8)
        if image.shape[0] * image.shape[1] <= 0x100D:
            min_rows = (0x100D // image.shape[1]) + 2
            image = np.pad(image, ((0, min_rows - image.shape[0]), (0, 0), (0, 0)))

        cpu = GlyphCPUv2(op_map, cols_instrs=8)
        # Seed VAC2 container header in RAM (backlog (d) residual,
        # 2026-09-22: 0x10's header read migrated from image space to
        # RAM, one byte per word, low byte first). 0x1000 exceeds the
        # default 1024-word RAM, so widen it first (no auto-growth).
        cpu.memory = [0] * 16384
        for i, byte_val in enumerate(b"VAC2"):
            cpu.memory[0x1000 + i] = byte_val
        cpu.memory[0x1004] = payload_low
        cpu.memory[0x1005] = payload_high
        cpu.memory[0x100C] = weights_low
        cpu.memory[0x100D] = weights_high

        cpu.run(image)

        # Should return 0 for successful syscall recognition
        assert cpu.registers[6] == 0

        op_map.close()

    def test_boot_linux_cognitive_payload_flag(self):
        """Test BOOT_LINUX syscall with cognitive payload flag (0x04)"""
        op_map = OpcodeMapV2()
        assembler = GlyphAssemblerV2(op_map)

        # VAC2 signature = 0x56414332
        # Pixel 0: B=0x56, G=0x41, R=0x43 → 0x434156
        # Pixel 1: B=0x32 → 0x000032
        sig_pixel0 = 0x434156

        program = [
            # Call BOOT_LINUX syscall with cognitive flag only
            'LDI r1 0x1000',     # container_addr
            'LDI r2 0x04',       # flags: cognitive only
            'SYSCALL r6 0x10',   # BOOT_LINUX syscall, result in r6
            'HALT',
        ]

        image = assembler.assemble(program, width_instrs=8)
        if image.shape[0] * image.shape[1] <= 0x1001:
            min_rows = (0x1001 // image.shape[1]) + 2
            image = np.pad(image, ((0, min_rows - image.shape[0]), (0, 0), (0, 0)))

        cpu = GlyphCPUv2(op_map, cols_instrs=8)
        # Seed VAC2 container header in RAM (backlog (d) residual,
        # 2026-09-22: image-space seeding replaced per the 0x10
        # migration; one byte per word, low byte first). 0x1000 exceeds
        # the default 1024-word RAM, so widen it first.
        cpu.memory = [0] * 16384
        for i, byte_val in enumerate(b"VAC2"):
            cpu.memory[0x1000 + i] = byte_val

        cpu.run(image)

        # Should return 0 for cognitive boot mode
        assert cpu.registers[6] == 0

        op_map.close()


class TestStoreCodeSyscall:
    """Test SYSCALL_STORE_CODE (0x11)"""

    def test_store_code_basic_copy(self):
        """Test STORE_CODE syscall with basic copy operation"""
        op_map = OpcodeMapV2()
        assembler = GlyphAssemblerV2(op_map)

        test_value = 0xABCDE  # 24-bit value

        program = [
            'LDI r1 100',         # dest_addr
            'LDI r2 200',         # src_addr
            'LDI r3 1',           # length = 1 pixel (3 bytes)
            'SYSCALL r4 0x11',    # STORE_CODE syscall
            'HALT',
        ]

        image = assembler.assemble(program, width_instrs=4)
        if image.shape[0] * image.shape[1] <= 200:
            min_rows = (200 // image.shape[1]) + 2
            image = np.pad(image, ((0, min_rows - image.shape[0]), (0, 0), (0, 0)))

        cpu = GlyphCPUv2(op_map, cols_instrs=4)
        cpu._mem_write(image, 200, test_value)
        cpu.run(image)

        # Verify copy succeeded
        assert cpu.registers[4] == 0  # syscall result
        assert cpu._mem_read(image, 100) == test_value  # copied value

        op_map.close()

    def test_store_code_multi_byte(self):
        """Test STORE_CODE syscall with multi-pixel copy"""
        op_map = OpcodeMapV2()
        assembler = GlyphAssemblerV2(op_map)

        # Use addresses that fit within data memory region
        # Code uses 20 pixels (0x00-0x13)
        # Source at 0x50 (80), dest at 0x55 (85), length 5
        program = [
            # Copy 5 pixels to destination
            'LDI r1 0x55',       # dest_addr
            'LDI r2 0x50',       # src_addr
            'LDI r3 5',          # length = 5 pixels
            'SYSCALL r4 0x11',   # STORE_CODE syscall
            'HALT',
        ]

        image = assembler.assemble(program, width_instrs=8)
        if image.shape[0] * image.shape[1] <= 0x5F:
            min_rows = (0x5F // image.shape[1]) + 2
            image = np.pad(image, ((0, min_rows - image.shape[0]), (0, 0), (0, 0)))

        cpu = GlyphCPUv2(op_map, cols_instrs=8)

        # Seed source pixels in pixel space
        values = [0x0000AA, 0x0000BB, 0x0000CC, 0x0000DD, 0x0000EE]
        for i, val in enumerate(values):
            cpu._mem_write(image, 0x50 + i, val)

        cpu.run(image)

        # Verify syscall succeeded
        assert cpu.registers[4] == 0

        # Verify each pixel was copied correctly
        dest_addr = 0x55
        for expected in values:
            x, y = cpu._addr_to_xy(image, dest_addr)
            val = cpu._mem_read(image, dest_addr)
            assert val == expected, f"Expected 0x{expected:06X}, got 0x{val:06X}"
            dest_addr += 1

        op_map.close()

    def test_store_code_invalid_length(self):
        """Test STORE_CODE syscall with invalid length"""
        op_map = OpcodeMapV2()
        assembler = GlyphAssemblerV2(op_map)

        program = [
            'LDI r1 100',         # dest_addr
            'LDI r2 200',         # src_addr
            'LDI r3 0',           # length = 0 (invalid)
            'SYSCALL r4 0x11',    # STORE_CODE syscall
            'HALT',
        ]

        image = assembler.assemble(program, width_instrs=4)
        cpu = GlyphCPUv2(op_map, cols_instrs=4)
        cpu.run(image)

        # Should return -1 for invalid length
        assert cpu.registers[4] == -1

        op_map.close()

    def test_store_code_overlapping_regions(self):
        """Test STORE_CODE syscall with overlapping source/dest regions"""
        op_map = OpcodeMapV2()
        assembler = GlyphAssemblerV2(op_map)

        program = [
            # Copy 100->102 (overlapping)
            'LDI r1 102',         # dest_addr (overlaps src)
            'LDI r2 100',         # src_addr
            'LDI r3 3',           # length = 3 pixels
            'SYSCALL r4 0x11',    # STORE_CODE syscall
            'HALT',
        ]

        image = assembler.assemble(program, width_instrs=8)
        if image.shape[0] * image.shape[1] <= 105:
            min_rows = (105 // image.shape[1]) + 2
            image = np.pad(image, ((0, min_rows - image.shape[0]), (0, 0), (0, 0)))

        cpu = GlyphCPUv2(op_map, cols_instrs=8)

        # Seed source pattern at address 100-104 in pixel space
        values = [0x000011, 0x000022, 0x000033, 0x000044, 0x000055]
        for i, val in enumerate(values):
            cpu._mem_write(image, 100 + i, val)

        cpu.run(image)

        # Syscall should succeed even with overlap (copy is byte-by-byte forward)
        assert cpu.registers[4] == 0
        # Forward copy: 100->102 (0x11), 101->103 (0x22), 102->104 (now 0x11)
        assert cpu._mem_read(image, 102) == 0x000011
        assert cpu._mem_read(image, 103) == 0x000022
        assert cpu._mem_read(image, 104) == 0x000011

        op_map.close()


if __name__ == '__main__':
    pytest.main([__file__, '-v'])