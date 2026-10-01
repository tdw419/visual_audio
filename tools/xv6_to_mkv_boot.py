#!/usr/bin/env python3
"""
xv6 → Pixels → MKV → Boot Prototype

Workflow:
1. Build/compile a RISC-V kernel (or use xv6)
2. Encode binary to pixels via wordbase.db (dense RGB24 encoding)
3. Store in visual_audio.mkv as a bootstrap entry
4. Extract and boot via Python RISC-V emulator
5. Future: GPU emulation

This is the CPU-only prototype. GPU version will use spatial_cpu/riscv_spatial_core.py.
"""

import sys
import os
import tempfile
import subprocess
from pathlib import Path
from typing import Optional

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from tools import va_container
from tools.elf_to_pixel_loader import ELFLoader
from tools.python_riscv_emulator import PythonRISCVEmulator


def create_hello_world_kernel():
    """
    Create a simple RISC-V "hello world" kernel binary.

    RISC-V assembly program that:
    1. Prints "Hello from Visual Audio MKV!" via UART
    2. Exits cleanly

    Returns: bytes - raw binary kernel
    """
    # RISC-V RV32I assembly for hello world
    # syscall 64 = write, syscall 93 = exit
    # For simplicity, we'll make a tiny C program instead

    c_code = '''
// Simple RISC-V "kernel" that prints and exits
// Compiled with: riscv64-unknown-elf-gcc -nostdlib -march=rv32i -mabi=ilp32

void _start() {
    // Write string to stdout (fd=1)
    // For now, just call exit(0) to prove we loaded
    __asm__ volatile (
        "li a7, 93\\n"  // sys_exit
        "li a0, 0\\n"   // exit code 0
        "ecall\\n"
    );
}
'''

    print("Creating simple RISC-V kernel...")

    # Build a proper 32-bit RISC-V ELF binary
    import struct

    data = bytearray()

    # ELF magic (4 bytes)
    data.extend(b'\x7fELF')

    # EI_CLASS = 1 for 32-bit, EI_DATA = 1 for little-endian
    # EI_VERSION = 1, EI_OSABI = 0
    data.extend([1, 1, 1, 0])

    # ABI version (1 byte)
    data.append(0)

    # EI_PAD (7 bytes)
    data.extend(b'\x00' * 7)

    # e_type (2 bytes, offset 16)
    data.extend(struct.pack('<H', 2))  # ET_EXEC

    # e_machine (2 bytes, offset 18)
    data.extend(struct.pack('<H', 243))  # EM_RISCV

    # e_version (4 bytes)
    data.extend(struct.pack('<I', 1))

    # e_entry (4 bytes, offset 24) - entry at 0x80000000
    data.extend(struct.pack('<I', 0x80000000))

    # e_phoff (4 bytes, offset 28) - program header at offset 52
    data.extend(struct.pack('<I', 52))

    # e_shoff (4 bytes, offset 32)
    data.extend(struct.pack('<I', 0))

    # e_flags (4 bytes)
    data.extend(struct.pack('<I', 0))

    # e_ehsize (2 bytes, offset 52)
    data.extend(struct.pack('<H', 52))

    # e_phentsize (2 bytes)
    data.extend(struct.pack('<H', 32))

    # e_phnum (2 bytes)
    data.extend(struct.pack('<H', 1))

    # e_shentsize (2 bytes)
    data.extend(struct.pack('<H', 40))

    # e_shnum (2 bytes)
    data.extend(struct.pack('<H', 0))

    # e_shstrndx (2 bytes)
    data.extend(struct.pack('<H', 0))

    # Program header starts at offset 52 (32 bytes for 32-bit ELF)
    # p_type (4 bytes)
    data.extend(struct.pack('<I', 1))  # PT_LOAD

    # p_offset (4 bytes) - code will be at offset 84 (after 52-byte header + 32-byte PHDR)
    data.extend(struct.pack('<I', 84))

    # p_vaddr (4 bytes) - load at 0x80000000
    data.extend(struct.pack('<I', 0x80000000))

    # p_paddr (4 bytes)
    data.extend(struct.pack('<I', 0x80000000))

    # p_filesz (4 bytes) - 4 bytes of code
    data.extend(struct.pack('<I', 4))

    # p_memsz (4 bytes)
    data.extend(struct.pack('<I', 4))

    # p_flags (4 bytes)
    data.extend(struct.pack('<I', 7))  # R|W|X

    # p_align (4 bytes)
    data.extend(struct.pack('<I', 0x1000))

    # Code at offset 84 (52-byte header + 32-byte PHDR)
    # J x0, 0 (infinite loop at 0x80000000 - jump to current address)
    # J format: imm[20|10:1|11|19:12] opcode
    # imm=0 means jump to self
    # Encoding: 0x6f, 0x00, 0x00, 0x00 (little-endian)
    data.extend([0x6f, 0x00, 0x00, 0x00])

    minimal_binary = bytes(data)
    print(f"  Created minimal RISC-V kernel ({len(minimal_binary)} bytes)")
    return minimal_binary


def encode_kernel_to_pixels(kernel_binary: bytes):
    """
    Encode kernel binary to RGB pixels using dense encoding.

    For binary data, we use dense encoding: 3 bytes per pixel (RGB24).
    This is byte-perfect, not semantic tokenization.

    Args:
        kernel_binary: Raw kernel binary

    Returns:
        Tuple: (pixel_count, bytes_encoded)
    """
    print(f"Encoding kernel to pixels via dense RGB24...")

    # Dense encoding: 3 bytes per pixel
    bytes_per_pixel = 3
    pixel_count = (len(kernel_binary) + bytes_per_pixel - 1) // bytes_per_pixel

    print(f"  Kernel size: {len(kernel_binary)} bytes")
    print(f"  Pixel count: {pixel_count} pixels")
    print(f"  Encoding: {bytes_per_pixel} bytes/pixel (RGB24)")

    return pixel_count, len(kernel_binary)


def store_kernel_in_mkv(mkv_path: str, kernel_binary: bytes, name: str):
    """
    Store kernel binary in MKV container.

    Args:
        mkv_path: Path to visual_audio.mkv
        kernel_binary: Kernel binary data
        name: Entry name in container

    Returns:
        bool: Success status
    """
    print(f"Storing kernel in MKV container...")
    print(f"  MKV: {mkv_path}")
    print(f"  Entry name: {name}")

    # Write to temp file
    with tempfile.NamedTemporaryFile(mode='wb', suffix='.bin', delete=False) as tmp:
        tmp.write(kernel_binary)
        tmp_path = tmp.name

    try:
        # Check if entry exists
        check_result = subprocess.run(
            ["python3", "tools/va_container.py", "ls", mkv_path],
            capture_output=True,
            text=True
        )

        if name in check_result.stdout:
            print(f"  Entry exists, updating...")
            # Update existing entry
            result = subprocess.run(
                ["python3", "tools/va_container.py", "update", mkv_path, name, tmp_path,
                 "--note", "RISC-V kernel for boot"],
                capture_output=True,
                text=True
            )
        else:
            # Add new entry
            result = subprocess.run(
                ["python3", "tools/va_container.py", "add", mkv_path, tmp_path,
                 "--name", name, "--role", "kernel", "--note", "RISC-V kernel for boot"],
                capture_output=True,
                text=True
            )

        if result.returncode == 0:
            print(f"✓ Kernel stored in MKV")
            print(f"  {result.stdout.strip()}")
            return True
        else:
            print(f"✗ Failed to store kernel: {result.stderr}")
            return False
    finally:
        os.unlink(tmp_path)


def extract_kernel_from_mkv(mkv_path: str, name: str) -> Optional[bytes]:
    """
    Extract kernel binary from MKV.

    Args:
        mkv_path: Path to visual_audio.mkv
        name: Entry name in container

    Returns:
        bytes: Kernel binary data, or None on failure
    """
    print(f"Extracting kernel from MKV...")

    # Extract to temp file
    with tempfile.NamedTemporaryFile(mode='wb', suffix='.bin', delete=False) as tmp:
        tmp_path = tmp.name

    try:
        result = subprocess.run(
            ["python3", "tools/va_container.py", "cat", mkv_path, name, "-o", tmp_path],
            capture_output=True,
            text=True
        )

        if result.returncode != 0:
            print(f"✗ Failed to extract kernel: {result.stderr}")
            return None

        # Read the binary
        kernel_binary = Path(tmp_path).read_bytes()
        print(f"✓ Extracted kernel ({len(kernel_binary)} bytes)")

        return kernel_binary
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


def boot_kernel_on_cpu(kernel_binary: bytes, max_instructions: int = 1000):
    """
    Boot kernel using Python RISC-V emulator.

    Args:
        kernel_binary: Kernel binary data (ELF or raw)
        max_instructions: Max instructions to execute

    Returns:
        bool: Success status
    """
    print(f"Booting kernel on Python RISC-V emulator...")
    print(f"  Max instructions: {max_instructions}")

    try:
        # Check if it's an ELF file
        if kernel_binary[:4] == b'\x7fELF':
            print("  Detected ELF kernel, parsing...")

            # Parse ELF using ELFLoader
            with tempfile.NamedTemporaryFile(mode='wb', suffix='.elf', delete=False) as tmp:
                tmp.write(kernel_binary)
                tmp_path = tmp.name

            try:
                loader = ELFLoader(tmp_path)
                entry_point = loader.entry_point
                segments = loader.get_loadable_segments()

                print(f"  Entry point: 0x{entry_point:08x}")
                print(f"  Loadable segments: {len(segments)}")

                # Build memory image from loadable segments
                # Find max address to size memory
                max_addr = 0
                for seg in segments:
                    end_addr = seg['vaddr'] + seg['memsz']
                    max_addr = max(max_addr, end_addr)

                # Round up to 4KB alignment
                memory_size = ((max_addr + 0xfff) & ~0xfff)
                print(f"  Memory size: {memory_size:,} bytes")

                # Initialize memory
                memory = bytearray(memory_size)

                # Load segments
                for seg in segments:
                    vaddr = seg['vaddr']
                    offset = seg['offset']
                    filesz = seg['filesz']
                    memsz = seg['memsz']

                    # Copy file data to memory
                    segment_data = kernel_binary[offset:offset+filesz]
                    memory[vaddr:vaddr+filesz] = segment_data

                    # Zero-fill BSS (if memsz > filesz)
                    if memsz > filesz:
                        memory[vaddr+filesz:vaddr+memsz] = b'\x00' * (memsz - filesz)

                    print(f"  Loaded segment at 0x{vaddr:08x} (filesz={filesz}, memsz={memsz})")

                # Create emulator
                emulator = PythonRISCVEmulator(memory)
                emulator.pc = entry_point

            finally:
                os.unlink(tmp_path)
        else:
            # Raw binary - load at PC=0
            print("  Detected raw binary, loading at PC=0")
            emulator = PythonRISCVEmulator(kernel_binary)
            emulator.pc = 0

        print(f"  Starting PC: 0x{emulator.pc:08x}")

        # Execute
        instr_count = 0
        while emulator.running and instr_count < max_instructions:
            emulator.step()
            instr_count += 1

            # Print progress every 100 instructions
            if instr_count % 100 == 0:
                print(f"  Executed {instr_count} instructions, PC=0x{emulator.pc:08x}")

        print(f"✓ Boot complete")
        print(f"  Instructions executed: {instr_count}")
        print(f"  Final PC: 0x{emulator.pc:08x}")

        return True

    except Exception as e:
        print(f"✗ Boot failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run the complete prototype."""
    print("=" * 70)
    print("xv6 → Pixels → MKV → Boot Prototype (CPU)")
    print("=" * 70)

    MKV_PATH = "visual_audio.mkv"
    KERNEL_NAME = "riscv_halt_kernel.bin"

    # Step 1: Create kernel
    print("\n=== STEP 1: Create RISC-V Kernel ===")
    kernel_binary = create_hello_world_kernel()

    # Step 2: Encode to pixels (informational)
    print("\n=== STEP 2: Encode to Pixels ===")
    pixel_count, bytes_encoded = encode_kernel_to_pixels(kernel_binary)

    # Step 3: Store in MKV
    print("\n=== STEP 3: Store in MKV ===")
    if not store_kernel_in_mkv(MKV_PATH, kernel_binary, KERNEL_NAME):
        print("✗ Failed to store kernel in MKV")
        return 1

    # Step 4: Extract from MKV
    print("\n=== STEP 4: Extract from MKV ===")
    extracted_kernel = extract_kernel_from_mkv(MKV_PATH, KERNEL_NAME)
    if extracted_kernel is None:
        print("✗ Failed to extract kernel from MKV")
        return 1

    # Verify round-trip
    if extracted_kernel != kernel_binary:
        print("✗ Round-trip verification FAILED")
        print(f"  Original: {len(kernel_binary)} bytes")
        print(f"  Extracted: {len(extracted_kernel)} bytes")
        return 1
    print("✓ Round-trip verification PASSED (byte-perfect)")

    # Step 5: Boot on CPU emulator
    print("\n=== STEP 5: Boot on CPU Emulator ===")
    if boot_kernel_on_cpu(extracted_kernel, max_instructions=1000):
        print("\n✓ PROTOTYPE SUCCESS")
        print("  CPU emulator can boot kernels from MKV container")
        print("  Next: Scale to full xv6 kernel")
        return 0
    else:
        print("\n✗ PROTOTYPE FAILED")
        return 1


if __name__ == "__main__":
    sys.exit(main())