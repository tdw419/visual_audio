# GPU Linux Shell — Quickstart

Boot Alpine Linux to an interactive shell on the WGSL GPU RV64 core, and
use it. Total prerequisite: an RTX/GPU with ~4GB free VRAM and this repo.

## 1. Build the shell container (~10 seconds)

The canonical Alpine blob's initramfs boots headless (no /init output —
see the offset note in `boot_alpine_gpu_fixed.py`). The builder overlays
a shell init and repacks a copy; the canonical blob and the frozen
BOOT_SMOKE md5 gate are never touched.

    venv/bin/python tools/build_gpu_shell_blob.py -o /tmp/h12/alpine_shell.lnx.bin

## 2. Boot to shell (one command; ~75 min first run, seconds after)

    ./hackathon/demo/BOOT_LINUX.sh

First run: full boot (~68 min on an RTX 5090 measured 2026-11-02), and
the at-prompt machine state is saved to
`/tmp/h12/shell_prompt_snapshot.npz`. Every later run resumes from that
snapshot — seconds to a working prompt (delete the file to force a
fresh boot).

That builds the container on first run and boots. Under the hood it is
just:

    venv/bin/python tools/build_gpu_shell_blob.py -o /tmp/h12/alpine_shell.lnx.bin
    venv/bin/python tools/gpu_shell_live.py --kernel /tmp/h12/alpine_shell.lnx.bin

The serial console streams to stdout. At ~94s of kernel time you land at:

    ==============================================
      GPU userspace shell - Alpine Linux on RISC-V
      running on the WGSL GPU RV64 core
    ==============================================
    gpu-rv64:~# uname -a
    Linux (none) 6.12.31-0-lts #1-Alpine SMP PREEMPT_DYNAMIC ... riscv64 Linux

## 3. Use it — what works

Boot the **live** driver and type at it yourself:

    venv/bin/python tools/gpu_shell_live.py \
        --kernel /tmp/h12/alpine_shell.lnx.bin --max-steps 2500000000

(The one-shot `boot_offload_alpine.py --kernel ...` path still works for
an unattended scripted session.)

When the prompt appears, you have the console. The whole busybox
toolbox resolves as real commands — `ls`, `cat`, `free`, `vi`, `grep`,
`awk`, `find` — verified transcript:
`hackathon/tests/fixtures/gpu_shell_live_interactive_2026-11-01.log`:

    gpu-rv64:~# ls /
    bin  dev  etc  init  lib  media  newroot  proc  root  sbin  sys  tmp  usr  var  note.txt
    gpu-rv64:~# cat note.txt
    hello GPU
    gpu-rv64:~# free
    Mem:  37580  8192  15940  0  13448  15244

The whole root filesystem is a writable ramdisk (the initramfs
itself); files persist for the life of the boot. The UART has no RX
interrupt in the DTB, so the init runs a background CR-flusher —
expect up to ~a minute of console silence before a keystroke echoes.

## Troubleshooting

- **`Not enough memory left` at core creation** — something is holding
  VRAM (in practice: an ollama model pinned with keep-alive forever).
  Check `nvidia-smi`, `ollama stop <model>`, retry.
- **Boot ends at "Waiting for root device /dev/vda"** — you are on the
  canonical blob (headless initramfs) or a pre-fix loader. The shell
  container from step 1 is required.
- **Want a persistent root disk?** Not yet: the initramfs ships without
  `virtio_mmio.ko`/`virtio_blk.ko`, so /dev/vda never appears. Injecting
  the two modules (matching 6.12.31-0-lts) into the overlay cpio is the
  documented next step — the overlay mechanism in
  `tools/build_gpu_shell_blob.py` is exactly where they go.

## Receipt

Full committed session: `hackathon/tests/fixtures/gpu_shell_session_2026-10-30.log`
(receipt: `hackathon/submission/GPU_SHELL_RECEIPT_2026-10-30.md`).
