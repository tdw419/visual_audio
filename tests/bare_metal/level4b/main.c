#include <stdint.h>

#define UART0_BASE 0x10000000
#define UART0_TX   (*(volatile uint8_t *)(UART0_BASE))
#define UART0_LSR  (*(volatile uint8_t *)(UART0_BASE + 5))

#define VIRTIO_MMIO_START  0x10001000
#define VIRTIO_MMIO_STRIDE 0x1000
#define VIRTIO_NUM_SLOTS   8
#define VIRTIO_MAGIC_OFF   0x00
#define VIRTIO_VERSION_OFF 0x04
#define VIRTIO_DEVID_OFF   0x08

// Legacy (v0.95) VirtIO MMIO register offsets
#define VIRTIO_DEVICE_FEATURES 0x10
#define VIRTIO_DRIVER_FEATURES 0x20
#define VIRTIO_GUEST_PAGE_SIZE 0x28
#define VIRTIO_QUEUE_SEL    0x30
#define VIRTIO_QUEUE_NUM_MAX 0x34
#define VIRTIO_QUEUE_NUM    0x38
#define VIRTIO_QUEUE_ALIGN  0x3C
#define VIRTIO_QUEUE_PFN    0x40
#define VIRTIO_QUEUE_NOTIFY 0x50
#define VIRTIO_STATUS       0x70

// PLIC MMIO registers (M-mode context)
#define PLIC_BASE       0x0c000000
#define PLIC_PRIORITY   (*(volatile uint32_t *)(PLIC_BASE + 0x0))
#define PLIC_PENDING    (*(volatile uint32_t *)(PLIC_BASE + 0x1000))
#define PLIC_MENABLE    (*(volatile uint32_t *)(PLIC_BASE + 0x2000))
#define PLIC_MTHRESHOLD (*(volatile uint32_t *)(PLIC_BASE + 0x200000))
#define PLIC_MCLAIM     (*(volatile uint32_t *)(PLIC_BASE + 0x200004))

static volatile uint32_t *virtio = 0;

void putc(char c) {
    while ((UART0_LSR & 0x20) == 0);
    UART0_TX = c;
}

void print(const char *s) {
    while (*s) putc(*s++);
}

void print_hex32(uint32_t val) {
    const char hex_chars[] = "0123456789ABCDEF";
    for (int i = 7; i >= 0; i--) {
        putc(hex_chars[(val >> (i * 4)) & 0xF]);
    }
}

#define VQ_SIZE 8

// Legacy VirtIO ring layout (all in one page using PFN-based addressing):
//   Descriptor table at PFN+0 (16 bytes * VQ_SIZE)
//   Avail ring right after desc table
//   Used ring aligned to QUEUE_ALIGN

#define RING_PAGE_SIZE 4096
static uint8_t ring_page[RING_PAGE_SIZE] __attribute__((aligned(4096)));

#define DESC_SIZE  (VQ_SIZE * 16)
#define DESC_END   ((DESC_SIZE + 63) & ~63)

struct virtq_desc {
    uint64_t addr;
    uint32_t len;
    uint16_t flags;
    uint16_t next;
};

// Packed rings match Legacy layout exactly
struct __attribute__((packed)) virtq_avail {
    uint16_t flags;
    uint16_t idx;
    uint16_t ring[VQ_SIZE];
};

struct __attribute__((packed)) virtq_used_elem {
    uint32_t id;
    uint32_t len;
};

struct __attribute__((packed)) virtq_used {
    uint16_t flags;
    uint16_t idx;
    struct virtq_used_elem ring[VQ_SIZE];
};

// Used ring must be 64-byte aligned per QEMU's vring_align formula
#define AVAIL_OFFSET   DESC_END
#define AVAIL_END      (AVAIL_OFFSET + 2 + 2 + VQ_SIZE * 2)
#define USED_OFFSET    ((AVAIL_END + 63) & ~63)

#define vq_desc  ((struct virtq_desc *)ring_page)
#define vq_avail ((struct virtq_avail *)(ring_page + AVAIL_OFFSET))
#define vq_used  ((struct virtq_used *)(ring_page + USED_OFFSET))

struct virtio_blk_outhdr {
    uint32_t type;
    uint32_t ioprio;
    uint64_t sector;
};

#define VIRTIO_BLK_T_IN 0
#define VRING_DESC_F_NEXT 1
#define VRING_DESC_F_WRITE 2

static struct virtio_blk_outhdr req_hdr __attribute__((aligned(64)));
static uint8_t req_data[512] __attribute__((aligned(64)));
static uint8_t req_status __attribute__((aligned(64)));

volatile int dma_completed = 0;
volatile uint32_t irq_claimed = 0;

void c_trap_handler(void) {
    uint64_t mcause;
    asm volatile("csrr %0, mcause" : "=r"(mcause));
    
    // Machine external interrupt is 11 (or 0x800000000000000B)
    if ((mcause & 0xF) == 11) {
        uint32_t irq = PLIC_MCLAIM;
        irq_claimed = irq;
        if (irq == 1) { // VirtIO IRQ
            // Ack VirtIO interrupt by reading ISR status
            uint32_t isr = virtio[0x60 / 4];
            dma_completed = 1;
        }
        PLIC_MCLAIM = irq;
    }
}

volatile uint32_t *find_virtio_device(void) {
    for (int i = 0; i < VIRTIO_NUM_SLOTS; i++) {
        volatile uint32_t *base = (uint32_t *)(VIRTIO_MMIO_START + i * VIRTIO_MMIO_STRIDE);
        uint32_t magic = base[VIRTIO_MAGIC_OFF / 4];
        uint32_t devid = base[VIRTIO_DEVID_OFF / 4];
        if (magic == 0x74726976 && devid != 0) {
            print("Found VirtIO at slot ");
            print_hex32(i);
            print(" DevID=");
            print_hex32(devid);
            print("\n");
            return base;
        }
    }
    return 0;
}

void main() {
    print("Level 4b-ii: DMA Kick and Poll...\n");

    virtio = find_virtio_device();
    if (!virtio) {
        print("ERROR: No VirtIO device found!\n");
        while (1) asm volatile("wfi");
    }

    uint32_t version = virtio[VIRTIO_VERSION_OFF / 4];
    print("VirtIO Version: ");
    print_hex32(version);
    print("\n");

    // Setup PLIC for VirtIO (IRQ 1)
    (&PLIC_PRIORITY)[1] = 1;  // Priority 1 for IRQ 1
    PLIC_MENABLE = 2;         // Enable IRQ 1 (bit 1)
    PLIC_MTHRESHOLD = 0;      // Threshold 0

    // Enable Machine External Interrupts (MEIE = bit 11 in mie)
    asm volatile("csrs mie, %0" :: "r"(1 << 11));
    // Enable Global Machine Interrupts (MIE = bit 3 in mstatus)
    asm volatile("csrs mstatus, %0" :: "r"(1 << 3));

    // Init
    virtio[VIRTIO_STATUS / 4] = 0x03;

    // Features
    uint32_t dev_features = virtio[VIRTIO_DEVICE_FEATURES / 4];
    print("DevFeatures: ");
    print_hex32(dev_features);
    print("\n");
    virtio[VIRTIO_DRIVER_FEATURES / 4] = dev_features;
    virtio[VIRTIO_GUEST_PAGE_SIZE / 4] = 4096;

    // Queue setup (before DRIVER_OK)
    virtio[VIRTIO_QUEUE_SEL / 4] = 0;
    uint32_t max_q = virtio[VIRTIO_QUEUE_NUM_MAX / 4];
    print("QueueNumMax: ");
    print_hex32(max_q);
    print("\n");

    virtio[VIRTIO_QUEUE_NUM / 4] = VQ_SIZE;
    virtio[VIRTIO_QUEUE_ALIGN / 4] = 64;

    uint32_t desc_pfn = (uint32_t)(uint64_t)ring_page >> 12;
    virtio[VIRTIO_QUEUE_PFN / 4] = desc_pfn;

    print("QueuePFN=");
    print_hex32(desc_pfn);
    print("  (addr 0x");
    print_hex32(desc_pfn << 12);
    print(")\n");

    virtio[VIRTIO_STATUS / 4] = 0x0F;
    print("Status: ");
    print_hex32(virtio[VIRTIO_STATUS / 4]);
    print("\n");

    // Zero all rings
    for (int i = 0; i < VQ_SIZE; i++) {
        vq_desc[i].addr = 0;
        vq_desc[i].len = 0;
        vq_desc[i].flags = 0;
        vq_desc[i].next = 0;
    }
    vq_avail->flags = 0;
    vq_avail->idx = 0;
    vq_used->flags = 0;
    vq_used->idx = 0;

    // Build VirtIO block read request
    req_hdr.type = VIRTIO_BLK_T_IN;
    req_hdr.ioprio = 0;
    req_hdr.sector = 0;
    req_status = 0xFF;
    for (int i = 0; i < 512; i++) req_data[i] = 0;

    // Desc 0: Header (device-readable)
    vq_desc[0].addr = (uint64_t)&req_hdr;
    vq_desc[0].len = sizeof(req_hdr);
    vq_desc[0].flags = VRING_DESC_F_NEXT;
    vq_desc[0].next = 1;

    // Desc 1: Data Buffer (device-writable)
    vq_desc[1].addr = (uint64_t)req_data;
    vq_desc[1].len = sizeof(req_data);
    vq_desc[1].flags = VRING_DESC_F_NEXT | VRING_DESC_F_WRITE;
    vq_desc[1].next = 2;

    // Desc 2: Status (device-writable)
    vq_desc[2].addr = (uint64_t)&req_status;
    vq_desc[2].len = sizeof(req_status);
    vq_desc[2].flags = VRING_DESC_F_WRITE;
    vq_desc[2].next = 0;

    // Make available
    vq_avail->ring[vq_avail->idx] = 0;
    vq_avail->idx = 1;

    print("Avail.idx=");
    print_hex32(vq_avail->idx);
    print("\n");

    print("Kicking...\n");
    virtio[VIRTIO_QUEUE_NOTIFY / 4] = 0;

    // Wait for interrupt
    print("Waiting for interrupt (wfi)...\n");
    while (!dma_completed) {
        asm volatile("wfi");
    }

    print("Interrupt received! Claimed IRQ: ");
    print_hex32(irq_claimed);
    print("\n");

    print("Used.idx=");
    print_hex32(vq_used->idx);
    print("\n");

    print("DMA Complete! Status: 0x");
    print_hex32(req_status);
    print("\n");

    print("Data[0-3]: 0x");
    print_hex32(*(uint32_t*)req_data);
    print("\n");

    // Also dump first 16 bytes as hex
    print("Data hex: ");
    for (int i = 0; i < 16; i++) {
        putc("0123456789ABCDEF"[(req_data[i] >> 4) & 0xF]);
        putc("0123456789ABCDEF"[req_data[i] & 0xF]);
    }
    print("\n");

    print("Halting.\n");

    while (1) {
        asm volatile("wfi");
    }
}
