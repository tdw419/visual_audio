CC = riscv64-unknown-elf-gcc
CFLAGS = -march=rv64ima_zicsr -mabi=lp64 -mcmodel=medany -ffreestanding -O0 -nostdlib

all: level6a.elf

level6a.elf: entry.S main.c link.ld
	$(CC) $(CFLAGS) -T link.ld entry.S main.c -o level6a.elf

clean:
	rm -f level6a.elf level6a.npy
