#!/usr/bin/env python3
"""
Spectrogram VM tests.

Tests for TASK_R002: Spectrogram as spatial VM — execute in the image.

Core concept: Frequency=register, Time=PC, Amplitude=value.
"""

import pytest
import numpy as np
from PIL import Image
from pathlib import Path

# Import the VM
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from tools.spatial_vm import SpectrogramVM


def test_vm_initialization():
    """Test that VM initializes correctly."""
    vm = SpectrogramVM(n_registers=16)
    
    assert vm.n_registers == 16
    assert vm.pc == 0
    assert vm.running == False
    assert len(vm.registers) == 16
    assert vm.spectrogram is None


def test_register_read_write():
    """Test register read/write operations."""
    vm = SpectrogramVM(n_registers=16)
    
    # Create minimal spectrogram
    vm.spectrogram = np.zeros((16, 10), dtype=np.float32)
    
    # Write and read
    vm._write_register(0, 0.5)
    assert vm._read_register(0) == pytest.approx(0.5)
    
    vm._write_register(5, 0.75)
    assert vm._read_register(5) == pytest.approx(0.75)


def test_image_load_and_save():
    """Test loading and saving spectrogram as PNG."""
    vm = SpectrogramVM(n_registers=16)
    
    # Create test spectrogram
    test_data = np.random.rand(16, 20).astype(np.float32)
    vm.spectrogram = test_data.copy()
    
    # Save
    output_path = '/tmp/test_spectrogram.png'
    img_array = (test_data * 255).astype(np.uint8)
    Image.fromarray(img_array, mode='L').save(output_path)
    
    # Load and verify
    vm2 = SpectrogramVM(n_registers=16)
    vm2.load_image(output_path)
    
    # Values may differ slightly due to quantization
    assert vm2.spectrogram is not None
    assert vm2.spectrogram.shape == test_data.shape
    
    # Check values are approximately correct
    diff = np.abs(vm2.spectrogram - test_data)
    assert np.mean(diff) < 0.01  # Average error < 1%


def test_simple_program_execution():
    """Test executing a minimal program that loads a value."""
    vm = SpectrogramVM(n_registers=16)
    
    # Create a program: SET r0 = 0.5
    # Opcode=1 (SET), rd=0, imm=0.5
    vm.spectrogram = np.zeros((16, 5), dtype=np.float32)
    vm.spectrogram[0, 0] = 0.1  # Opcode SET (0.1*10=1)
    vm.spectrogram[1, 0] = 0.0  # rd=r0
    vm.spectrogram[4, 0] = 0.5  # imm=0.5
    vm.spectrogram[0, 1] = 0.5  # Opcode HALT (0.5*10=5)
    
    # Execute
    steps = vm.run(max_frames=5)
    
    # Should have executed 2 instructions then halted
    # PC=1 after HALT (HALT doesn't increment PC)
    assert steps == 2
    assert vm.pc == 1
    assert not vm.running
    
    # r0 should be 0.5
    assert vm.registers[0] == pytest.approx(0.5, abs=0.1)


def test_counter_program_basic():
    """Test that a counter program can be generated and loaded."""
    vm = SpectrogramVM(n_registers=16)
    
    # Generate counter program
    output_path = '/tmp/test_counter.png'
    vm.generate_counter_program(output_path, frames=20)
    
    # Verify file exists
    assert Path(output_path).exists()
    
    # Load and verify shape
    vm2 = SpectrogramVM(n_registers=16)
    vm2.load_image(output_path)
    
    assert vm2.spectrogram is not None
    assert vm2.spectrogram.shape[0] == 16  # n_registers
    assert vm2.spectrogram.shape[1] == 20  # frames


def test_instruction_decode():
    """Test that instructions decode correctly from spectrogram values."""
    vm = SpectrogramVM(n_registers=16)
    
    # Create test spectrogram with known opcode values
    vm.spectrogram = np.zeros((16, 10), dtype=np.float32)
    
    # Test different opcodes (value * 10 = opcode)
    vm.spectrogram[0, 0] = 0.0   # NOOP
    vm.spectrogram[0, 1] = 0.1   # SET
    vm.spectrogram[0, 2] = 0.2   # SUB
    vm.spectrogram[0, 3] = 0.3   # CMP
    vm.spectrogram[0, 4] = 0.4   # JZ
    vm.spectrogram[0, 5] = 0.5   # HALT
    vm.spectrogram[0, 6] = 0.6   # ADD
    
    expected_opcodes = [0, 1, 2, 3, 4, 5, 6]
    
    for pc, expected in enumerate(expected_opcodes):
        vm.pc = pc
        opcode = round(vm._read_register(0) * 10)
        assert opcode == expected, f"PC={pc}: expected {expected}, got {opcode}"


def test_register_bounds():
    """Test that register bounds are enforced."""
    vm = SpectrogramVM(n_registers=16)
    vm.spectrogram = np.zeros((16, 10), dtype=np.float32)
    
    # Out of bounds should raise
    with pytest.raises(ValueError):
        vm._read_register(20)
    
    with pytest.raises(ValueError):
        vm._write_register(20, 0.5)


def test_run_halt():
    """Test that HALT stops execution."""
    vm = SpectrogramVM(n_registers=16)
    
    # Create program: NOOP, NOOP, HALT, NOOP
    vm.spectrogram = np.zeros((16, 10), dtype=np.float32)
    vm.spectrogram[0, 0] = 0.0  # NOOP
    vm.spectrogram[0, 1] = 0.0  # NOOP
    vm.spectrogram[0, 2] = 0.5  # HALT
    vm.spectrogram[0, 3] = 0.0  # NOOP (should not execute)
    
    steps = vm.run(max_frames=100)
    
    # Should stop at PC=2 after HALT (HALT doesn't increment)
    assert steps == 3
    assert vm.pc == 2
    assert not vm.running


def test_frequency_register_mapping():
    """Verify the core mapping: frequency=register, time=PC, amplitude=value."""
    vm = SpectrogramVM(n_registers=16)
    
    # Create a program where each register has a different value
    vm.spectrogram = np.zeros((16, 2), dtype=np.float32)
    
    # Frame 0: Set each register to a unique value via amplitudes
    for i in range(16):
        vm.spectrogram[i, 0] = i / 20.0  # Register i has value i/20
    
    # Verify mapping by reading registers
    vm.pc = 0
    for i in range(16):
        value = vm._read_register(i)
        expected = i / 20.0
        assert value == pytest.approx(expected, abs=0.01), \
            f"Register {i}: expected {expected}, got {value}"


def test_time_pc_mapping():
    """Verify that time axis maps to program counter."""
    vm = SpectrogramVM(n_registers=16)
    
    # Create a program with distinct values at different time steps
    vm.spectrogram = np.zeros((16, 5), dtype=np.float32)
    
    # Each time step has a unique marker value
    for t in range(5):
        vm.spectrogram[0, t] = t / 5.0
    
    # Verify PC increments through time
    vm.pc = 0
    assert vm._read_register(0) == pytest.approx(0.0)
    
    vm.pc = 2
    assert vm._read_register(0) == pytest.approx(0.4)
    
    vm.pc = 4
    assert vm._read_register(0) == pytest.approx(0.8)


def test_end_to_end_spectrogram_execution():
    """
    End-to-end test: generate program -> save as PNG -> load -> execute.
    
    This verifies the complete pipeline of:
    1. Program encoding as spectrogram
    2. Persistence as PNG
    3. Loading from PNG
    4. Decoding and execution
    """
    # Create a simple program
    vm_gen = SpectrogramVM(n_registers=16)
    vm_gen.spectrogram = np.zeros((16, 3), dtype=np.float32)
    
    # Program: SET r0 = 0.75, HALT
    vm_gen.spectrogram[0, 0] = 0.1  # SET
    vm_gen.spectrogram[1, 0] = 0.0  # rd=r0
    vm_gen.spectrogram[4, 0] = 0.75  # imm=0.75
    vm_gen.spectrogram[0, 1] = 0.5  # HALT
    
    # Save as PNG
    img_path = '/tmp/test_e2e.png'
    img_array = (vm_gen.spectrogram * 255).astype(np.uint8)
    Image.fromarray(img_array, mode='L').save(img_path)
    
    # Load and execute
    vm_exec = SpectrogramVM(n_registers=16)
    vm_exec.load_image(img_path)
    steps = vm_exec.run(max_frames=10)
    
    # Verify execution
    assert steps == 2
    assert not vm_exec.running
    assert vm_exec.registers[0] == pytest.approx(0.75, abs=0.1)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])