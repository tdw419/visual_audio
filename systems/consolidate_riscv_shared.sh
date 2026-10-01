#!/bin/bash
# Consolidate RISC-V bootloader to use virtio_pixel_rs_v3_shared
# Remove shadow modules (elf64.rs, handoff.rs, ecall.rs, uart.rs)
# Update main.rs to use shared crate

set -e

echo "=== Consolidating RISC-V Bootloader to Shared Crate ==="

# Remove shadow module files
echo "Removing shadow modules..."
cd /home/jericho/projects/zion/projects/visual_audio/systems/virtio_pixel_rs_v3_riscv/src
for file in elf64.rs handoff.rs ecall.rs uart.rs lib.rs; do
    if [ -f "$file" ]; then
        echo "  Removing $file"
        rm -f "$file"
    fi
done

echo "Shadow modules removed. Now main.rs needs manual update."
echo ""
echo "Next steps:"
echo "1. Update main.rs to use virtio_pixel_rs_v3_shared::uart::UART instead of virtio_pixel_rs_v3_riscv::println!"
echo "2. Remove println! macro references and use uart::UART.puts() directly"
echo "3. Build with: cd /home/jericho/projects/zion/projects/visual_audio/systems && cargo build -p virtio_pixel_rs_v3_riscv --release --target riscv64gc-unknown-none-elf"
echo "4. Test with: qemu-system-riscv64 -machine virt -bios default -kernel target/.../bootloader_riscv -nographic"