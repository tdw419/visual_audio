#!/usr/bin/env python3
"""
Launch QEMU with GDB stub to capture state at PC = 0x80201048.
This allows synchronized memory comparison with GPU emulator.

Usage:
    python3 capture_qemu_at_pc.py

Output:
    qemu_regs_at_0x80201048.txt - Register dump
    qemu_csr_at_0x80201048.txt - CSR dump
    qemu_mem_at_0x80201048.bin - 16 bytes around the instruction
"""
import subprocess
import time
import os

# Target address: secondary hart entry stub
TARGET_PC = "0x80201048"

def write_gdb_script(script_path):
    """Write GDB script to capture state."""
    with open(script_path, "w") as f:
        f.write(f"""# Don't use set architecture - let GDB auto-detect from target

# Set breakpoint at target
break *{TARGET_PC}

# Continue to breakpoint
continue

# When we hit the breakpoint, capture registers
shell echo "=== REGISTERS ===" > /home/jericho/projects/zion/projects/visual_audio/qemu_regs_at_0x80201048.txt
info registers >> /home/jericho/projects/zion/projects/visual_audio/qemu_regs_at_0x80201048.txt

# Capture CSRs
shell echo "=== CSRS ===" > /home/jericho/projects/zion/projects/visual_audio/qemu_csr_at_0x80201048.txt
info csr >> /home/jericho/projects/zion/projects/visual_audio/qemu_csr_at_0x80201048.txt

# Capture memory around instruction
dump binary memory /tmp/qemu_mem.bin 0x80201048 0x80201058
shell cp /tmp/qemu_mem.bin /home/jericho/projects/zion/projects/visual_audio/qemu_mem_at_0x80201048.bin

# Quit
quit
""")

def run_qemu_capture():
    """Run QEMU with GDB and capture state."""
    # Write GDB script
    gdb_script = "/tmp/qemu_capture.gdb"
    write_gdb_script(gdb_script)

    print("Starting QEMU with GDB stub on port 1234...")
    qemu_proc = subprocess.Popen([
        "qemu-system-riscv64",
        "-nographic",
        "-machine", "virt",
        "-kernel", "boot_images/alpine_Image",
        "-initrd", "boot_images/alpine_initrd",
        "-m", "512M",
        "-s",  # Enable GDB stub
        "-S",  # Start paused
    ], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, cwd="/home/jericho/projects/zion/projects/visual_audio")

    # Give QEMU time to start
    time.sleep(3)

    print(f"Connecting GDB to capture state at PC = {TARGET_PC}...")

    # Run GDB with script
    try:
        gdb_proc = subprocess.Popen([
            "gdb-multiarch",
            "-batch",
            "-nx",  # Don't read .gdbinit
            "-x", gdb_script,
        ], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

        gdb_output = gdb_proc.communicate(timeout=30)[0]
        print(gdb_output)

        # Check if we captured files
        for filename in ["qemu_regs_at_0x80201048.txt", "qemu_csr_at_0x80201048.txt", "qemu_mem_at_0x80201048.bin"]:
            filepath = f"/home/jericho/projects/zion/projects/visual_audio/{filename}"
            if os.path.exists(filepath):
                size = os.path.getsize(filepath)
                print(f"  ✓ Captured {filename} ({size:,} bytes)")
            else:
                print(f"  ✗ Missing {filename}")

        # Try to extract key CSRs
        if os.path.exists("/home/jericho/projects/zion/projects/visual_audio/qemu_csr_at_0x80201048.txt"):
            with open("/home/jericho/projects/zion/projects/visual_audio/qemu_csr_at_0x80201048.txt", "r") as f:
                csr_content = f.read()
                print("\n  Key CSRs:")
                for line in csr_content.split('\n'):
                    line = line.strip()
                    if any(csr in line.lower() for csr in ['satp', 'mstatus', 'mepc', 'mcause', 'mtvec', 'pc']):
                        print(f"    {line}")

    except subprocess.TimeoutExpired:
        print("  ✗ GDB timed out (QEMU may be stuck or breakpoint not reached)")
        try:
            gdb_proc.kill()
        except:
            pass

    # Kill QEMU
    print("\nStopping QEMU...")
    qemu_proc.terminate()
    try:
        qemu_proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        qemu_proc.kill()
        qemu_proc.wait()

    print("\n✓ QEMU capture complete!")
    return True

if __name__ == "__main__":
    run_qemu_capture()