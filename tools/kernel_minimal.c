// Minimal RISC-V kernel for GPU execution
// Compile with riscv32-unknown-linux-gnu-gcc -nostdlib -static -o kernel_minimal.elf kernel_minimal.c

// RISC-V Linux syscall numbers
#define SYS_WRITE  64
#define SYS_EXIT   93

// System call wrapper
static inline void syscall3(long num, long arg0, long arg1, long arg2) {
    asm volatile (
        "mv a7, %0\n"
        "mv a0, %1\n"
        "mv a1, %2\n"
        "mv a2, %3\n"
        "ecall"
        :
        : "r" (num), "r" (arg0), "r" (arg1), "r" (arg2)
        : "a0", "a1", "a2", "a7", "memory"
    );
}

// Simple write syscall
static inline void write(int fd, const char *buf, long len) {
    syscall3(SYS_WRITE, fd, (long)buf, len);
}

// Simple exit syscall
static inline void exit(int status) {
    asm volatile (
        "mv a7, %0\n"
        "mv a0, %1\n"
        "ecall"
        :
        : "r" (SYS_EXIT), "r" (status)
        : "a0", "a7", "memory"
    );
    __builtin_unreachable();
}

// Entry point
void _start() {
    const char msg[] = "Hello from RISC-V in MKV!\n";
    write(1, msg, sizeof(msg) - 1);
    exit(0);
}