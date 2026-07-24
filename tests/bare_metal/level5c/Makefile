CC = riscv64-unknown-elf-gcc
CFLAGS = -march=rv64ima_zicsr -mabi=lp64 -mcmodel=medany -ffreestanding -O0 -nostdlib

all: level5c.elf

level5c.elf: entry.S main.c link.ld
	$(CC) $(CFLAGS) -T link.ld entry.S main.c -o level5c.elf

clean:
	rm -f level5c.elf level5c.npy
