#!/usr/bin/env python3
"""
Detailed analysis of kernel addresses at stall point

The stall is occurring with PC oscillating between addresses in the
0xffffffff808026xx range and other kernel addresses. Let's decode
what these addresses correspond to in the kernel.
"""

import struct
import subprocess
from pathlib import Path

KERNEL = Path('/home/jericho/projects/zion/projects/visual_audio/boot_images/alpine_riscv64.lnx.bin')

print("=" * 70)
print("KERNEL ADDRESS DECODING")
print("=" * 70)
print()

# Read the LNX header
data = KERNEL.read_bytes()

kernel_offset = struct.unpack('<I', data[4:8])[0]
kernel_size = struct.unpack('<I', data[8:12])[0]

print(f"LNX header:")
print(f"  Kernel offset: 0x{kernel_offset:x}")
print(f"  Kernel size: {kernel_size:,} bytes")
print()

# Extract kernel payload
kernel_pe = data[kernel_offset:kernel_offset + kernel_size]

# Check if this is PE format (EFI stubbed kernel)
e_lfanew = struct.unpack('<I', kernel_pe[0x3C:0x40])[0]
if kernel_pe[e_lfanew:e_lfanew+4] == b'PE\x00\x00':
    print("Kernel is PE format (EFI stubbed)")
    opt = e_lfanew + 24
    if struct.unpack('<H', kernel_pe[opt:opt+2])[0] == 0x20b:  # PE32+
        size_of_image = struct.unpack('<I', kernel_pe[opt+56:opt+60])[0]
    else:
        size_of_image = struct.unpack('<I', kernel_pe[opt+56:opt+60])[0]
    print(f"  SizeOfImage: {size_of_image:,} bytes")
else:
    print("Kernel is raw ELF or unknown format")
    size_of_image = kernel_size

# Key addresses from diagnosis
stall_addresses = [
    0xffffffff808026c0,
    0xffffffff80802664,
    0xffffffff80802692,
    0xffffffff808026c6,
    0xffffffff8080268a,
]

# Kernel virtual base is typically 0xffffffff80000000
KERNEL_BASE = 0xffffffff80000000

print()
print("STALL PC ADDRESSES (converting to file offsets):")
print()

for addr in stall_addresses:
    offset = addr - KERNEL_BASE
    print(f"  PC: 0x{addr:016x} -> file offset 0x{offset:08x}")
    
    if offset < len(kernel_pe):
        # Read instruction at this location (assuming little-endian RISC-V)
        inst_bytes = kernel_pe[offset:offset+4]
        if len(inst_bytes) == 4:
            inst = struct.unpack('<I', inst_bytes)[0]
            print(f"       Instruction: 0x{inst:08x}")

            # Try basic instruction decode
            opcode = inst & 0x7f
            rd = (inst >> 7) & 0x1f
            rs1 = (inst >> 15) & 0x1f
            rs2 = (inst >> 20) & 0x1f
            funct3 = (inst >> 12) & 0x7
            funct7 = (inst >> 25) & 0x7f

            if opcode == 0b0110011:  # R-type
                if funct3 == 0b000 and funct7 == 0b0000000:
                    print(f"       Likely: add x{rd}, x{rs1}, x{rs2}")
                elif funct3 == 0b101 and funct7 == 0b0000000:
                    print(f"       Likely: srl x{rd}, x{rs1}, x{rs2}")
                else:
                    print(f"       R-type: funct3={funct3:03b}, funct7={funct7:07b}")
            elif opcode == 0b0010011:  # I-type
                imm = (inst >> 20) & 0xfff
                sign_extended = imm - 4096 if imm >= 2048 else imm
                if funct3 == 0b000:
                    print(f"       Likely: addi x{rd}, x{rs1}, {sign_extended}")
                else:
                    print(f"       I-type: funct3={funct3:03b}, imm={sign_extended}")
            elif opcode == 0b0000011:  # Load
                imm = (inst >> 20) & 0xfff
                sign_extended = imm - 4096 if imm >= 2048 else imm
                print(f"       Load: funct3={funct3:03b}, offset={sign_extended}")
            elif opcode == 0b0100011:  # Store
                imm = ((inst >> 25) << 5) | ((inst >> 7) & 0x1f)
                sign_extended = imm - 4096 if imm >= 2048 else imm
                print(f"       Store: funct3={funct3:03b}, offset={sign_extended}")
            elif opcode == 0b0010111:  # AUIPC
                imm = ((inst >> 12) & 0xfffff) << 12
                sign_extended = imm - (1 << 31) if imm >= (1 << 20) else imm
                print(f"       auipc x{rd}, {sign_extended}")
            elif opcode == 0b1100111:  # JALR
                imm = (inst >> 20) & 0xfff
                sign_extended = imm - 4096 if imm >= 2048 else imm
                print(f"       jalr x{rd}, {sign_extended}(x{rs1})")
            elif opcode == 0b1101111:  # JAL
                imm = ((inst >> 31) << 20) | ((inst >> 21) & 0x3ff) << 1
                imm |= ((inst >> 20) & 0x1) << 11
                imm |= ((inst >> 12) & 0xff) << 12
                sign_extended = imm - (1 << 20) if imm >= (1 << 19) else imm
                print(f"       jal x{rd}, 0x{sign_extended:x}")
            else:
                print(f"       Opcode: {opcode:07b}")

            # Show hex dump of surrounding bytes
            start = max(0, offset - 8)
            end = min(len(kernel_pe), offset + 12)
            print(f"       Context: " + " ".join(f"{b:02x}" for b in kernel_pe[start:end]))
    print()

print()
print("=" * 70)
print("NEXT: Investigating what function 0x80802600 belongs to")
print("=" * 70)

# Search for kernel symbols if we have them
try:
    # Look for vmlinux or System.map in boot_images
    boot_dir = Path('/home/jericho/projects/zion/projects/visual_audio/boot_images')
    
    system_map = boot_dir / 'System.map'
    if system_map.exists():
        print("\nFound System.map - decoding addresses...")
        
        # Read and find addresses near our stall point
        lines = system_map.read_text().splitlines()
        
        # Find the function containing 0x808026c0
        target_addr = 0x808026c0  # Drop the high 0xffffffff00000000 for matching
        
        for line in lines:
            parts = line.split()
            if len(parts) >= 2:
                addr_str = parts[0]
                try:
                    addr = int(addr_str, 16)
                    if addr <= target_addr < addr + 0x100:  # Within 256 bytes
                        symbol = parts[1]
                        print(f"  0x{addr:016x} {symbol} (near stall PC)")
                except ValueError:
                    pass
    else:
        print("\nNo System.map found in boot_images/")
        
        # Try to extract symbols from kernel
        print("Attempting to extract kernel ELF symbols...")
        
        # Write kernel payload to temp file for analysis
        temp_kernel = '/tmp/alpine_kernel_extracted.bin'
        with open(temp_kernel, 'wb') as f:
            f.write(kernel_pe[:size_of_image])
        
        # Try to analyze with objdump (may fail if not ELF)
        result = subprocess.run(
            ['file', temp_kernel],
            capture_output=True,
            text=True
        )
        print(f"  File type: {result.stdout}")
        
        if 'ELF' in result.stdout:
            # Try objdump
            result = subprocess.run(
                ['objdump', '-t', temp_kernel],
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0:
                print("\n  Symbols near 0x808026c0:")
                for line in result.stdout.splitlines():
                    if '808026' in line:
                        print(f"    {line}")
        
except Exception as e:
    print(f"Error during symbol extraction: {e}")

print()
print("=" * 70)
print("ANALYSIS COMPLETE")
print("=" * 70)
print()
print("HYPOTHESIS: The PC is in a tight loop in kernel code,")
print("possibly in the idle loop or a kernel daemon that's waiting")
print("for an interrupt that never fires (timer interrupt issue?)")
print()
print("The addresses 0x808026xx suggest we're in a specific kernel")
print("function. With no output, the kernel may be:")
print("  1. Waiting in idle/polling loop")
print("  2. Stuck in kernel thread scheduling")
print("  3. Deadlocked on a spinlock")
print("  4. Timer interrupt not being delivered correctly")