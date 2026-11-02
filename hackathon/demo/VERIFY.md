# Verify it yourself

Everything in the demo is real and reproducible. Four tests, ranked by
time to verdict — run as many as you like. All commands run from the
repo root. Requirements: Linux; tests 2 and 4 need an NVIDIA GPU with
~4GB free VRAM (close anything holding VRAM first).

## 1. ~7 seconds — the test suite (no GPU)

    python3 -m pytest hackathon/tests/ -q

Expected: **59 passed**. Includes the decoder fixtures, the production
fallback path, and a defensive scan asserting no key material in the
submission tree.

## 2. ~10 seconds — offline glyph decode (no GPU)

    ./hackathon/demo/freeze/FALLBACK_DEMO.sh

Expected: exit 0; the poster is decoded by the classical production
path (η≈0.90) and the framed payload's md5 is checked against the
committed fixture — in ~18ms.

## 3. ~90 seconds — one-command end-to-end (GPU)

    ./hackathon/demo/freeze/E2E.sh

Expected, printed at the end:

    E2E PASS: decode md5 3292333c9470c37fbf4960b07dbeea79 | boot rc 0 | ... | ~80s wall

This is the demo's spine in one shot: the SAM decode leg, then a real
RISC-V Linux kernel boot leg on the WGSL GPU core, checked against the
frozen md5 gate. Reproducible: the decode md5 is deterministic.

## 4. ~75 min unattended, then type — the live interactive shell (GPU)

One command (details: `hackathon/demo/SHELL_QUICKSTART.md`):

    ./hackathon/demo/BOOT_LINUX.sh

Builds the shell container on first run, boots unattended (~75 min —
the GPU core emulates ~250k RISC-V instructions per second; the serial
console streams live), then hands you the prompt. Type a command; it
is fed byte-by-byte into the guest UART (echo-acknowledged pacing; the
RX FIFO is one byte deep and the UART has no RX IRQ, so the init runs
a CR-flusher to keep the 8250 driver draining), the core executes, and
the answer streams back:

    gpu-rv64:~# ls /
    bin  init  newroot  root  sys
    dev  lib   note.txt run  usr
    etc  media proc     sbin var

    gpu-rv64:~# cat note.txt
    hello GPU

    gpu-rv64:~# free
    Mem:  37580  8192  15940  0  13448  15244

The whole busybox toolbox resolves (`ls`, `vi`, `grep`, `awk`, ...).
Committed transcript of this exact session:
`hackathon/tests/fixtures/gpu_shell_live_interactive_2026-11-01.log`.

## Test 5 (fast): machine-state snapshot resume — seconds, not 75 min

The whole machine is six GPU buffers (64MB memory surface, registers,
state, CSRs, TLB, UART). `BOOT_LINUX.sh` saves them the first time the
prompt is reached (`/tmp/h12/shell_prompt_snapshot.npz`) and every later
run resumes from that file instead of re-booting:

    ./hackathon/demo/BOOT_LINUX.sh          # second run: seconds to prompt

Verified 2026-11-02: restore + `ls /` + `cat note.txt` -> `hello GPU` in
124s wall (50.9M steps), vs a 68-min full boot. Cross-adapter check:
`GPU_POWER=high ./hackathon/demo/freeze/E2E.sh` on the RTX 5090 produced
serial sha256 `c94026581a174c3118df1ec65fec20fb7d289cfbd2f33d3d33f930c22c717219`
— byte-identical to the iGPU freeze. Determinism survives the adapter.

## Cross-checks without running anything

- Shell session log: `hackathon/tests/fixtures/gpu_shell_session_2026-10-30.log`
- Boot receipt: `hackathon/submission/GPU_SHELL_RECEIPT_2026-10-30.md`
- Video scene → artifact map: `hackathon/demo/video/PRODUCTION_RECEIPT.md`
