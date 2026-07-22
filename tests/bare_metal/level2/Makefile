CC = riscv64-unknown-elf-gcc
CFLAGS = -march=rv64ima_zicsr -mabi=lp64 -mcmodel=medany -ffreestanding -O0 -nostdlib

all: level2.elf

level2.elf: entry.S main.c link.ld
	$(CC) $(CFLAGS) -T link.ld entry.S main.c -o level2.elf

clean:
	rm -f level2.elf
