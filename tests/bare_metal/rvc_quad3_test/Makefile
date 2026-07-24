CROSS = riscv64-unknown-elf-
CC = $(CROSS)gcc
OBJCOPY = $(CROSS)objcopy
OBJDUMP = $(CROSS)objdump

CFLAGS = -Os -march=rv64imac -mabi=lp64 -ffreestanding -nostdlib -mcmodel=medany
LDFLAGS = -T link.ld -nostdlib

TARGET = test_rvc

all: $(TARGET).elf $(TARGET).npy

$(TARGET).elf: main.c link.ld
	$(CC) $(CFLAGS) $(LDFLAGS) -o $@ $<
	$(OBJDUMP) -d $@ > $(TARGET).dis

$(TARGET).npy: $(TARGET).elf
	$(OBJCOPY) -O binary $@ /tmp/test.bin
	python3 -c "import numpy as np; data = np.fromfile('/tmp/test.bin', dtype=np.uint8); 	aligned = np.zeros((len(data) + 7) // 8, dtype=np.uint32); 	for i in range(len(data)): aligned[i // 8] |= (data[i] << ((i % 8) * 32)); 	np.save('$@', aligned)"

clean:
	rm -f $(TARGET).elf $(TARGET).npy $(TARGET).dis /tmp/test.bin

.PHONY: all clean
