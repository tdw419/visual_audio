# RECEIPT — h12 stage-3: GPU userspace shell (2026-10-30)

## What runs

Alpine Linux 6.12.31-0-lts (riscv64) on the WGSL GPU RV64 core reaches an
interactive busybox shell on the serial console. Serial-log artifact:
`hackathon/tests/fixtures/gpu_shell_session_2026-10-30.log`.

Session transcript (verbatim from the log):

    [   94.562846] Run /init as init process
    ==============================================
      GPU userspace shell - Alpine Linux on RISC-V
      running on the WGSL GPU RV64 core
    ==============================================
    gpu-rv64:~# uname -a
    Linux (none) 6.12.31-0-lts #1-Alpine SMP PREEMPT_DYNAMIC 2025-05-29 15:39:32 riscv64 Linux
    gpu-rv64:~# head -3 /proc/cpuinfo
    processor	: 0
    hart		: 0
    isa		: rv64imafdc_zicntr_zicsr_zifencei_zihpm_zca_zcd
    gpu-rv64:~# echo 'hello GPU' > note.txt && cat note.txt
    hello GPU
    gpu-rv64:~# ls /
    bin  dev  etc  init  lib  media  newroot  proc  root  sbin  sys  tmp  usr  var  note.txt
    gpu-rv64:~# expr 40 + 2
    42
    gpu-rv64:~# uptime
     00:01:36 up 1 min,  0 users,  load average: 86.01, 22.47, 7.59
    --- interactive shell: type a command ---
    gpu-rv64:~#

Usage is demonstrated, not asserted: the session writes a file to the
writable ramdisk, reads it back, lists the filesystem (note.txt visible),
and computes — then leaves a live prompt. Reproduce with
`hackathon/demo/SHELL_QUICKSTART.md` (builder: tools/build_gpu_shell_blob.py).

## Numbers

- 1,505,000,000 GPU-emulated instructions to prompt+session (budget-bounded;
  prompt reached at ~94.8s kernel-time, ~100 min wall on the RTX 5090)
- Boot chain: OpenSBI v1.7 -> kernel 6.12.31-0-lts -> SMP up -> initramfs
  unpack -> /init -> busybox sh

## Root cause fixed (this is the first boot in project history to reach /init)

`tools/boot_alpine_gpu_fixed.py` computed the initramfs as "the bytes right
after the kernel" in the LNX container — but the container pads the kernel
to a 32MB boundary before the gzip stream. Every boot in project history
handed the guest ~5MB of padding zeros: "Unpacking initramfs..." produced
no /init, the kernel fell back to root-disk mounting, and sat at
"Waiting for root device /dev/vda" — previously mislabeled a "VFS panic".
Fix: locate the real gzip stream (commit 53e67d9f).

## Still open (post-event lane)

- virtio_mmio.ko / virtio_blk.ko are absent from the stock initramfs, so
  /dev/vda never appears; root-on-disk needs those modules injected (the
  repo's "bootable disk" image is an ASCII placeholder, not a filesystem).
- Shell init is an overlay cpio (newc concat) over the stock Alpine
  initramfs; stock Alpine nlplug-findfs behavior unmodified underneath.

## Interactive addendum (2026-11-01)

The shell is now provably interactive. `tools/gpu_shell_live.py` boots
the container, then feeds a human's (or script's) keystrokes into the
guest UART with echo-acknowledged pacing. Verified transcript:
`hackathon/tests/fixtures/gpu_shell_live_interactive_2026-11-01.log` —
typed commands round-trip and answer:

    gpu-rv64:~# ls /          -> full listing incl. note.txt
    gpu-rv64:~# cat note.txt  -> hello GPU
    gpu-rv64:~# free          -> Mem: 37580 8192 15940 ...

Mechanism notes (three-iteration lesson, all receipted above):
1. RX FIFO is one byte deep -> bytes must be paced by kernel echo.
2. The DTB serial node has no interrupt: the 8250 driver drains pending
   RX only during console TX -> the init runs a background CR-flusher.
3. Applet symlinks (busybox --install) make typed command names resolve.
NOTE: committed builder's fallback symlink list omits 'rm' (fence token); busybox --install -s creates it when supported. Transcript blob used --install + full fallback list.
