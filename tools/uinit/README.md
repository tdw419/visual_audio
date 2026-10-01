# uinit — freestanding static ET_EXEC init for GPU-emulator userspace bring-up

`/bin/sh` in Alpine's initramfs is a PIE, dynamically-linked binary, and the
GPU RV64 emulator currently EFAULTs loading PIE binaries (store page fault at
~ELF_ET_DYN_BASE during clear_user of the .bss). This is a minimal init that
uses the plain ET_EXEC load path (fixed low VAs, no interpreter, no ASLR,
no load_bias) to isolate whether userspace runs at all.

Build (needs gcc-riscv64-linux-gnu; no libc required):
    riscv64-linux-gnu-gcc -static -nostdlib -no-pie -Wl,-e_start -o uinit uinit.S

Package + boot:
    mkdir d && cp uinit d/init && (cd d && find . | cpio -o -H newc | gzip -9 > ../ird.gz)
    python3 tools/boot_alpine_v618_gpu.py --initrd ird.gz

It writes "*** USERSPACE RUNNING ON THE GPU ***" via raw write(2) then loops on
getpid(2). If that string appears, ET_EXEC userspace works and the EFAULT is
PIE/dynamic-load specific.
