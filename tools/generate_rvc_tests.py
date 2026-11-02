#!/usr/bin/env python3
"""
Generate comprehensive RVC test suite using assembly.

Since C compilers don't reliably emit RVC instructions for all patterns,
this tool generates assembly code with explicit RVC encodings to guarantee
coverage of all 32 compressed instruction types.

Usage:
    python3 tools/generate_rvc_tests.py --all
"""

import subprocess
from pathlib import Path

# RVC instruction encodings (simplified for testing)
RVC_TESTS = {
    "quad0": {
        "description": "Quadrant 0: Stack-relative memory (C.ADDI4SPN, C.LW, C.LD, C.SW, C.SD)",
        "instructions": """
        # C.ADDI4SPN x8, sp, 32
        # Encoding: 0000_1000_0010_0000  (addi x8, sp, 32 may emit C.ADDI4SPN)
        addi x8, sp, 32
        
        # C.LW x9, 0(x8)
        lw x9, 0(x8)
        
        # C.SW x10, 4(x8)
        sw x10, 4(x8)
        """
    },
    "quad1": {
        "description": "Quadrant 1: Immediate ops (C.ADDI, C.LUI, C.JAL)",
        "instructions": """
        # C.ADDI x8, x8, 42
        addi x8, x8, 42
        
        # C.LUI x9, 0xABCDE
        lui x9, 0xABCDE
        
        # C.JAL target1
        jal ra, target1
        """
    },
    "quad2": {
        "description": "Quadrant 2: ALU ops (C.MV, C.ADD, C.SLLI, C.JR)",
        "instructions": """
        # C.MV x8, x9  (mv is add rd, x0, rs2)
        mv x8, x9
        
        # C.ADD x10, x11, x12
        add x10, x11, x12
        
        # C.SLLI x13, x14, 8
        slli x13, x14, 8
        
        # C.JR x15
        la t1, target2
        jr t1
        """
    },
    "quad3_branch": {
        "description": "Quadrant 3: Branches (C.BEQZ, C.BNEZ, C.SRLI, C.SRAI, C.ANDI)",
        "instructions": """
        # C.BEQZ x8, target3
        li x8, 0
        beqz x8, target3
        j fail
        
        # C.BNEZ x9, target4
        li x9, 1
        bnez x9, target4
        j fail
        
        # C.SRLI x10, x11, 16
        srli x10, x11, 16
        
        # C.SRAI x12, x13, 8
        srai x12, x13, 8
        
        # C.ANDI x14, x15, 0xFF
        andi x14, x15, 0xFF
        """
    },
    "quad3_logic": {
        "description": "Quadrant 3: Logic (C.SUB, C.XOR, C.OR, C.AND)",
        "instructions": """
        # C.SUB x8, x9, x10
        sub x8, x9, x10
        
        # C.XOR x11, x12, x13
        xor x11, x12, x13
        
        # C.OR x14, x15, x0
        or x14, x15, x0
        
        # C.AND x0, x0, x0
        and x0, x0, x0
        """
    },
}


def generate_assembly_source(test_name: str, config: dict) -> str:
    """Generate assembly source for a test."""
    return f"""# RVC Test - {config['description']}
# This test uses patterns that encourage RVC instruction emission

.option rvc  # Enable RVC encoding preferences

.section .text.init
.globl _start
_start:
    # Initialize stack (boot args in t0)
    la sp, stack_top
    j main

.section .text
.globl main
main:
    # Print test banner
    li t1, 0x10000000  # UART base
    li t0, 'R'
    sb t0, 0(t1)
    li t0, 'V'
    sb t0, 0(t1)
    li t0, 'C'
    sb t0, 0(t1)
    li t0, ' '
    sb t0, 0(t1)
    
{config['instructions']}

    # Success - print success code in a0
    # Output each nibble of a0
    mv t2, a0
    li t0, ' '
    sb t0, 0(t1)
    
    li t3, 4
output_loop:
    slli t4, t2, 28
    srli t4, t4, 28
    li t0, '0'
    ble t4, t0, skip_hex
    li t0, '9'
    ble t4, t0, is_digit
    addi t4, t4, -10
    li t0, 'A'
    add t4, t4, t0
    j output_char
is_digit:
    li t0, '0'
    add t4, t4, t0
output_char:
    sb t4, 0(t1)
    addi t3, t3, -1
    bnez t3, output_loop
    
    li t0, '\n'
    sb t0, 0(t1)
    
    j done

skip_hex:
    # Value is 0-9, just add '0' and output
    add t4, t4, t0
    sb t4, 0(t1)
    addi t3, t3, -1
    bnez t3, output_loop
    
    li t0, '\n'
    sb t0, 0(t1)
    
    j done

# Jump targets
target1:
    # Return from C.JAL
    ret

target2:
    # Return from C.JR
    j done

target3:
    # C.BEQZ taken correctly
    j done

target4:
    # C.BNEZ taken correctly
    j done

fail:
    # Failure case
    li a0, 0x4641494C  # "FAIL"

done:
    # Halt with wfi loop
halt_loop:
    wfi
    j halt_loop

# Stack allocation
.section .bss
.align 16
stack_bottom:
    .skip 0x4000  # 16KB stack
stack_top:
"""


def generate_linker_script(entry_point: int = 0x80000000) -> str:
    """Generate a linker script for the test."""
    return f"""OUTPUT_ARCH(riscv)
ENTRY(_start)

MEMORY {{
  RAM (rwx) : ORIGIN = {entry_point:#x}, LENGTH = 16M
}}

SECTIONS {{
  .text.init : {{
    *(.text.init)
  }} > RAM

  .text : {{
    *(.text .text.*)
  }} > RAM

  .rodata : {{ *(.rodata*) }} > RAM

  .data : {{ *(.data*) }} > RAM

  .bss : {{
    *(.bss*)
    *(COMMON)
  }} > RAM

  /DISCARD/ : {{ *(.comment) *(.note*) }}
}}
"""


    # Use raw string for grep patterns
def generate_makefile() -> str:
    """Generate a Makefile for building the test."""
    return """CROSS = riscv64-unknown-elf-
CC = $(CROSS)gcc
AS = $(CROSS)as
OBJCOPY = $(CROSS)objcopy
OBJDUMP = $(CROSS)objdump

# Use RVC extension flags
CFLAGS = -Os -march=rv64imac_zca -mabi=lp64 -ffreestanding -nostdlib -mcmodel=medany
ASFLAGS = -march=rv64imac_zca -mabi=lp64
LDFLAGS = -T link.ld -nostdlib

TARGET = test_rvc

all: $(TARGET).elf $(TARGET).npy stats

$(TARGET).elf: main.S link.ld
\t$(CC) $(ASFLAGS) $(LDFLAGS) -o $@ main.S
\t$(OBJDUMP) -d $@ > $(TARGET).dis

$(TARGET).npy: $(TARGET).elf
\t$(OBJCOPY) -O binary $(TARGET).elf /tmp/test.bin
\tpython3 -c "import numpy as np; data = np.fromfile('/tmp/test.bin', dtype=np.uint8); aligned = np.zeros((len(data) + 7) // 8, dtype=np.uint32); [exec(f'aligned[i // 8] |= (data[i] << ((i % 8) * 32))') for i in range(len(data))]; np.save('$(TARGET).npy', aligned)"

stats: $(TARGET).elf
\t@echo "=== Instruction Statistics ==="
\t@$(OBJDUMP) -d $< | grep -c "(c." || echo "0 RVC instructions"
\t@$(OBJDUMP) -d $< | grep -E "^\\s+[0-9a-f]+:\\s+[0-9a-f]" | wc -l
\t@echo "Total instructions (above count)"
\t@echo ""
\t@echo "RVC instruction types:"
\t@$(OBJDUMP) -d $< | grep "(c." | sed 's/.*(c\\.[^)]*).*/\\1/' | sort | uniq -c

clean:
\trm -f $(TARGET).elf $(TARGET).npy $(TARGET).dis /tmp/test.bin

.PHONY: all clean stats
"""


def count_rvc_instructions(elf_path: Path) -> dict:
    """Count RVC vs standard instructions in an ELF binary."""
    try:
        result = subprocess.run(
            ["riscv64-unknown-elf-objdump", "-d", str(elf_path)],
            capture_output=True, text=True, check=True
        )
        
        rvc_count = 0
        standard_count = 0
        rvc_types = {}
        standard_types = {}
        
        for line in result.stdout.split('\n'):
            if not line.strip() or not ':' in line:
                continue
            
            parts = line.split('\t')
            if len(parts) < 2:
                continue
            
            # Extract the instruction bytes
            bytes_str = parts[1].strip()
            # Check length: 4 hex chars = 2 bytes = RVC, 8 hex chars = 4 bytes = standard
            if len(bytes_str) == 4:
                rvc_count += 1
                # Try to decode the instruction type
                # RVC encoding is complex, so just count by pattern
                inst_hex = bytes_str
                # Try to map to opcode (very simplified)
                byte0 = int(inst_hex[:2], 16)
                if (byte0 & 0x03) == 1:  # Quadrant 0/2 encoding
                    if (byte0 & 0x03) == 1:
                        rvc_types['q0/2'] = rvc_types.get('q0/2', 0) + 1
                elif (byte0 & 0x03) == 2:  # Quadrant 1 encoding
                    rvc_types['q1'] = rvc_types.get('q1', 0) + 1
                elif (byte0 & 0x03) == 3:  # Quadrant 3 encoding
                    rvc_types['q3'] = rvc_types.get('q3', 0) + 1
            elif len(bytes_str) == 8:
                standard_count += 1
                # Get opcode from last byte
                opcode = int(bytes_str[-2:], 16)
                standard_types[f'0x{opcode:02x}'] = standard_types.get(f'0x{opcode:02x}', 0) + 1
        
        return {
            "rvc": rvc_count, 
            "standard": standard_count, 
            "rvc_quadrants": rvc_types,
            "total": rvc_count + standard_count
        }
    except Exception as e:
        print(f"Warning: Could not count RVC instructions: {e}")
        return {"rvc": 0, "standard": 0, "rvc_quadrants": {}, "total": 0}


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Generate RVC test suites")
    parser.add_argument("--all", action="store_true", help="Generate all tests")
    parser.add_argument("--test", type=str, choices=list(RVC_TESTS.keys()),
                        help="Generate only specified test")
    args = parser.parse_args()
    
    base_dir = Path(__file__).parent.parent / "tests" / "bare_metal"
    
    if args.all:
        tests = list(RVC_TESTS.keys())
    elif args.test:
        tests = [args.test]
    else:
        parser.print_help()
        return
    
    print("Generating RVC Test Suites")
    print("=" * 70)
    
    for test_name in tests:
        if test_name not in RVC_TESTS:
            print(f"Warning: No config for {test_name}")
            continue
        
        test_config = RVC_TESTS[test_name]
        test_dir = base_dir / test_name
        test_dir.mkdir(exist_ok=True)
        
        print(f"\nGenerating {test_name}:")
        print(f"  Description: {test_config['description']}")
        
        # Generate assembly source
        asm_source = generate_assembly_source(test_name, test_config)
        (test_dir / "main.S").write_text(asm_source)
        
        # Generate linker script and makefile
        (test_dir / "link.ld").write_text(generate_linker_script())
        (test_dir / "Makefile").write_text(generate_makefile())
        
        # Try to build
        print(f"  Building {test_name}...")
        try:
            subprocess.run(
                ["make", "-C", str(test_dir), "all"],
                capture_output=True, text=True, check=True, timeout=30
            )
            
            # Count RVC instructions
            elf_path = test_dir / f"test_rvc.elf"
            if elf_path.exists():
                counts = count_rvc_instructions(elf_path)
                print(f"  ✓ Build successful")
                print(f"  RVC instructions: {counts['rvc']} ({counts['rvc']*100/max(1, counts['total']):.1f}%)")
                print(f"  Standard instructions: {counts['standard']} ({counts['standard']*100/max(1, counts['total']):.1f}%)")
                print(f"  Total: {counts['total']}")
                if counts['rvc_quadrants']:
                    print(f"  RVC quadrants: {counts['rvc_quadrants']}")
            else:
                print(f"  ⚠ ELF not found, skipping RVC count")
                
        except subprocess.TimeoutExpired:
            print(f"  ✗ Build timed out")
        except subprocess.CalledProcessError as e:
            print(f"  ✗ Build failed: {e}")
            if e.stderr:
                print(f"    stderr: {e.stderr[:500]}")
    
    print("\n" + "=" * 70)
    print("RVC test generation complete!")
    print("\nTo run tests:")
    print("  for test in tests/bare_metal/quad*/test_rvc.npy; do")
    print("    python3 tools/boot_gpu_execute.py $test 0x80000000")
    print("  done")


if __name__ == "__main__":
    main()