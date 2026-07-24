CC = riscv64-unknown-elf-gcc
CFLAGS = -march=rv64imac_zicsr -mabi=lp64 -mcmodel=medany -ffreestanding -O0 -fomit-frame-pointer -nostdlib

all: level8_rvc.elf

level8_rvc.elf: entry.S main.c link.ld
	$(CC) $(CFLAGS) -T link.ld entry.S main.c -o level8_rvc.elf

clean:
	rm -f level8_rvc.elf level8_rvc.npy
