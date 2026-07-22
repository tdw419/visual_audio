#include <stdint.h>

#define UART_BASE 0x10000000
#define VIRTIO_BASE 0x10001000
#define PLIC_BASE 0x0C000000

#define VIRTIO_MAGIC   (VIRTIO_BASE + 0x000)
#define VIRTIO_VERSION (VIRTIO_BASE + 0x004)
#define VIRTIO_DEVICE  (VIRTIO_BASE + 0x008)

#define PLIC_PRIORITY_IRQ1 (PLIC_BASE + 0x000004)
#define PLIC_ENABLE_M      (PLIC_BASE + 0x002000)
#define PLIC_THRESHOLD_M   (PLIC_BASE + 0x200000)

volatile uint8_t *uart = (uint8_t *)UART_BASE;

void print_str(const char *str) {
    while (*str) {
        *uart = *str++;
    }
}

// Minimal hex printer to avoid pulling in printf
void print_hex32(uint32_t val) {
    char buf[9];
    buf[8] = 0;
    for (int i = 7; i >= 0; i--) {
        uint8_t nibble = val & 0xF;
        buf[i] = (nibble < 10) ? ('0' + nibble) : ('A' + (nibble - 10));
        val >>= 4;
    }
    print_str("0x");
    print_str(buf);
    print_str("\n");
}

int main() {
    print_str("Level 4a: Init\n");

    // 1. Read VirtIO MMIO registers
    print_str("VirtIO Magic: ");
    uint32_t magic = *(volatile uint32_t *)VIRTIO_MAGIC;
    print_hex32(magic);

    print_str("VirtIO Version: ");
    uint32_t version = *(volatile uint32_t *)VIRTIO_VERSION;
    print_hex32(version);

    print_str("VirtIO DeviceID: ");
    uint32_t device = *(volatile uint32_t *)VIRTIO_DEVICE;
    print_hex32(device);

    // 2. Configure PLIC for IRQ 1 (VirtIO Block on QEMU virt)
    print_str("Configuring PLIC...\n");
    
    // Set IRQ 1 priority to 1
    *(volatile uint32_t *)PLIC_PRIORITY_IRQ1 = 1;
    
    // Enable IRQ 1 for Hart 0 M-mode (bit 1)
    *(volatile uint32_t *)PLIC_ENABLE_M = (1 << 1);
    
    // Set M-mode threshold to 0 (accept all priorities > 0)
    *(volatile uint32_t *)PLIC_THRESHOLD_M = 0;

    // Read back what we just wrote - without this, a silently-ignored
    // write and a correctly-applied one look identical to the CPU (no
    // fault, no GPR/PC difference), so this is the only way this payload
    // can actually detect whether the M-mode PLIC context is implemented.
    print_str("PLIC Enable-M readback: ");
    print_hex32(*(volatile uint32_t *)PLIC_ENABLE_M);
    print_str("PLIC Threshold-M readback: ");
    print_hex32(*(volatile uint32_t *)PLIC_THRESHOLD_M);
    print_str("PLIC Priority-IRQ1 readback: ");
    print_hex32(*(volatile uint32_t *)PLIC_PRIORITY_IRQ1);

    print_str("Level 4a Complete.\n");
    return 0;
}
