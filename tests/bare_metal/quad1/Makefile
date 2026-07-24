CROSS = riscv64-unknown-elf-
CC = $(CROSS)gcc
AS = $(CROSS)as
OBJCOPY = $(CROSS)objcopy
OBJDUMP = $(CROSS)objdump

# Use RVC extension flags
CFLAGS = -Os -march=rv64imac_zca -mabi=lp64 -ffreestanding -nostdlib -mcmodel=medany
ASFLAGS = -march=rv64imac_zca -mabi=lp64
LDFLAGS = -T link.ld -nostdlib

TARGET = test_rvc

all: $(TARGET).elf $(TARGET).npy stats

$(TARGET).elf: main.S link.ld
	$(CC) $(ASFLAGS) $(LDFLAGS) -o $@ main.S
	$(OBJDUMP) -d $@ > $(TARGET).dis

$(TARGET).npy: $(TARGET).elf
	$(OBJCOPY) -O binary $(TARGET).elf /tmp/test.bin
	python3 -c "import numpy as np; data = np.fromfile('/tmp/test.bin', dtype=np.uint8); aligned = np.zeros((len(data) + 7) // 8, dtype=np.uint32); [exec(f'aligned[i // 8] |= (data[i] << ((i % 8) * 32))') for i in range(len(data))]; np.save('$(TARGET).npy', aligned)"

stats: $(TARGET).elf
	@echo "=== Instruction Statistics ==="
	@$(OBJDUMP) -d $< | grep -c "(c." || echo "0 RVC instructions"
	@$(OBJDUMP) -d $< | grep -E "^\s+[0-9a-f]+:\s+[0-9a-f]" | wc -l
	@echo "Total instructions (above count)"
	@echo ""
	@echo "RVC instruction types:"
	@$(OBJDUMP) -d $< | grep "(c." | sed 's/.*(c\.[^)]*).*/\1/' | sort | uniq -c

clean:
	rm -f $(TARGET).elf $(TARGET).npy $(TARGET).dis /tmp/test.bin

.PHONY: all clean stats
