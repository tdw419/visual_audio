#!/usr/bin/env python3
"""Resume .ckpt/v618_preexec.rv64ckpt and run forward, streaming UART, until a
shell prompt / login / panic / long stall."""
from __future__ import annotations
import sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from rv64i_checkpoint import load_checkpoint

CKPT = sys.argv[1] if len(sys.argv) > 1 else ".ckpt/v618_preexec.rv64ckpt"
MAX_STEPS = int(sys.argv[2]) if len(sys.argv) > 2 else 4_000_000_000
# NOTE: the shader's per-instruction mtime jitter LCG is var<private> and resets
# every dispatch, so batch size changes the timer-tick timing and thus the
# execution path. 2000 matches tools/trace_preexec_efault.py, which reaches
# Alpine Init cleanly; large batches diverge into a jitter-dependent stall.
BATCH = int(sys.argv[3]) if len(sys.argv) > 3 else 2000
STALL_S = int(sys.argv[4]) if len(sys.argv) > 4 else 240

core = load_checkpoint(CKPT)
print(f"resumed {CKPT}")
uart = ""
steps = 0
last_out = time.time()
t0 = time.time()
while steps < MAX_STEPS:
    core.step(steps=BATCH)
    steps += BATCH
    b = core.read_uart_output()
    if b:
        txt = b.decode("latin-1", "replace")
        uart += txt
        sys.stdout.write(txt); sys.stdout.flush()
        last_out = time.time()
    st = core.get_state()
    if st["halted"]:
        print(f"\n[HALTED pc=0x{st['pc']:x} steps={steps:,}]"); break
    low = uart.lower()
    for marker in ("kernel panic", "attempted to kill", "unhandled signal",
                   "call trace:", "/ #", "~ #", "localhost login", "sh: can't",
                   "please press enter", "welcome to alpine"):
        if marker in low:
            print(f"\n[MARKER '{marker}' @ {steps:,} steps, {time.time()-t0:.0f}s]")
            steps = MAX_STEPS
            break
    if time.time() - last_out > STALL_S:
        print(f"\n[STALL: no UART for {STALL_S}s @ {steps:,} steps]"); break

print(f"\n=== stopped: steps={steps:,} pc=0x{core.get_state()['pc']:x} uart={len(uart)}B {time.time()-t0:.0f}s ===")
