# Level 1 bare-metal stepladder payload.
#
# level1_rv64ima.elf  - no C extension; this is the standing regression
#                       target (clean 30/30 trace-diff parity vs QEMU).
# level1_rv64imac.elf - C extension enabled; kept deliberately as a
#                       regression trigger for the known missing-RVC-decoder
#                       bug in tools/RISCV_CPU_MMU.wgsl (halts after 4
#                       instructions on c.addi). Do not "fix" by removing.

CC = riscv64-unknown-elf-gcc
CFLAGS = -mabi=lp64 -static -mcmodel=medany -nostdlib -nostartfiles \
         -ffreestanding -fno-builtin -Wl,-T,link.ld

all: level1_rv64ima.elf level1_rv64imac.elf

level1_rv64ima.elf: entry.S main.c link.ld
	$(CC) -march=rv64ima $(CFLAGS) -o $@ entry.S main.c

level1_rv64imac.elf: entry.S main.c link.ld
	$(CC) -march=rv64imac $(CFLAGS) -o $@ entry.S main.c

clean:
	rm -f level1_rv64ima.elf level1_rv64imac.elf

.PHONY: all clean
