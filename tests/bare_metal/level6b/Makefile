CC = riscv64-unknown-elf-gcc
CFLAGS = -march=rv64ima_zicsr -mabi=lp64 -mcmodel=medany -ffreestanding -O0 -nostdlib

all: level6b.elf

level6b.elf: entry.S main.c link.ld
	$(CC) $(CFLAGS) -T link.ld entry.S main.c -o level6b.elf

clean:
	rm -f level6b.elf level6b.npy
