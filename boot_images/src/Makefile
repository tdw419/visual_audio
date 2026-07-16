# Build the demo boot images for the signed boot manifest (TASK_C033).
#
#   make            -> build both kernels into ../
#   make clean      -> remove built images
#   make run-hello  -> boot hello.img under qemu (default OpenSBI firmware)
#   make run-bare   -> boot bare.img under qemu with -bios none
#
# hello.img : S-mode kernel loaded by OpenSBI at 0x80200000, prints via SBI.
# bare.img  : M-mode kernel at 0x80000000 for `-bios none`, prints via raw UART.

CROSS   ?= riscv64-unknown-elf-
CC      := $(CROSS)gcc
CFLAGS  := -march=rv64g -mabi=lp64 -mcmodel=medany -nostdlib -ffreestanding -Wall -O2
OUT     := ..

all: $(OUT)/hello.img $(OUT)/bare.img

$(OUT)/hello.img: entry.S main.c linker.ld
	$(CC) $(CFLAGS) -T linker.ld entry.S main.c -o $@

$(OUT)/bare.img: bare_entry.S bare_main.c bare_linker.ld
	$(CC) $(CFLAGS) -T bare_linker.ld bare_entry.S bare_main.c -o $@

run-hello: $(OUT)/hello.img
	qemu-system-riscv64 -nographic -machine virt -kernel $(OUT)/hello.img

run-bare: $(OUT)/bare.img
	qemu-system-riscv64 -nographic -machine virt -bios none -kernel $(OUT)/bare.img

clean:
	rm -f $(OUT)/hello.img $(OUT)/bare.img

.PHONY: all clean run-hello run-bare
