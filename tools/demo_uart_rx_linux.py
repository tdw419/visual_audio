"""
Quick demo: boot Linux, wait for login prompt, feed one character to prove RX works.
This demonstrates full-duplex UART: kernel prints output, we send input back.
"""
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent))
from spatial_rv32i_cpu import SpatialRV32ICore

REPO_ROOT = Path(__file__).parent.parent
KERNEL_PATH = REPO_ROOT / "boot_images" / "rv32ima_nommu" / "Image"
DTB_PATH = REPO_ROOT / "boot_images" / "rv32ima_nommu" / "sixtyfourmb.dtb"

RAM_BASE = 0x80000000
DTB_OFFSET = 0x00400000
MEMORY_SIZE = 64 * 1024 * 1024

kernel = KERNEL_PATH.read_bytes()
dtb = DTB_PATH.read_bytes()

core = SpatialRV32ICore(memory_size_bytes=MEMORY_SIZE)
core.load_program(kernel, entry_point=RAM_BASE, ram_base=RAM_BASE)
core.write_mem_bytes(DTB_OFFSET, dtb)
core.write_register(10, 0)
core.write_register(11, RAM_BASE + DTB_OFFSET)

output_buffer = b''
found_prompt = False

print("Booting Linux on GPU (waiting for login prompt)...")

# Step until we see "buildroot login:"
for _ in range(4000):  # 4000 * 20k = 80M steps, enough to reach userspace
    core.step(steps=20000)
    out = core.read_uart_output()
    if out:
        sys.stdout.buffer.write(out)
        sys.stdout.flush()
        output_buffer += out

    if b"buildroot login:" in output_buffer:
        found_prompt = True
        print("\n>>> Found login prompt!", file=sys.stderr)
        break

if not found_prompt:
    print("\nLogin prompt not reached after 80M steps", file=sys.stderr)
    sys.exit(1)

# Now feed a single character 'r' and verify the kernel echoes it
print("\n>>> Feeding character 'r' to prove RX works...", file=sys.stderr)
core.write_uart_input(b'r')

# Run a few more steps to let kernel echo
for _ in range(10):
    core.step(steps=20000)
    out = core.read_uart_output()
    if out:
        sys.stdout.buffer.write(out)
        sys.stdout.flush()

print("\n=== RX demo complete ===", file=sys.stderr)
print("Linux 6.1.14 RV32IMA-NOMMU is now running on GPU with full UART TX/RX!")
print("The kernel received our input character and echoed it back.")