#!/bin/bash
# Start QEMU in background with GDB stub
qemu-system-riscv64 -machine virt -bios default -kernel target/riscv64gc-unknown-none-elf/debug/bootloader_riscv -nographic -serial stdio -S -s > /tmp/qemu_gdb.log 2>&1 &
QEMU_PID=$!

sleep 1

# Connect GDB and run until after handoff, then check LAST_TRAP
gdb -batch -ex "target remote localhost:1234" -ex "b *virtio_pixel_rs_v3_riscv::ecall::riscv_ecall::trap_handler" -ex "c" -ex "p/x *frame" -ex "c" -ex "p/x virtio_pixel_rs_v3_riscv::ecall::riscv_ecall::LAST_TRAP" -ex "q"

kill -9 $QEMU_PID
