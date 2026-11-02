#!/usr/bin/env python3
"""Resume preexec, run to just before the 'Mounting boot media' stall, then
sample pc / mode / a0-a7 repeatedly to see if the guest is in a poll loop
(kernel VA cycling) or the emulator is wedged (pc frozen)."""
import sys, collections
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from rv64i_checkpoint import load_checkpoint

core = load_checkpoint(".ckpt/v618_preexec.rv64ckpt")
uart = ""
steps = 0
BATCH = 2000
# run until we've seen 'Mounting boot media'
while steps < 200_000_000:
    core.step(steps=BATCH); steps += BATCH
    b = core.read_uart_output()
    if b:
        uart += b.decode("latin-1", "replace")
    if "Mounting boot media" in uart:
        break
print(f"reached 'Mounting boot media' at {steps:,} steps")

def regs(c):
    import numpy as np
    a = np.frombuffer(c.queue.read_buffer(c.registers.buffer), dtype=np.uint32)
    return [int(a[i*2]) | (int(a[i*2+1]) << 32) for i in range(32)]

pchist = collections.Counter()
modes = collections.Counter()
samples = []
for k in range(60):
    core.step(steps=50_000); steps += 50_000
    st = core.get_state()
    r = regs(core)
    pchist[st["pc"]] += 1
    modes[st["mode"]] += 1
    b = core.read_uart_output()
    if b:
        t = b.decode("latin-1", "replace")
        uart += t
        print(f"  [uart+] {t!r}")
    samples.append((steps, st["pc"], st["mode"], r[10], r[11], r[17]))

print("\nmode histogram:", dict(modes))
print("top pcs:")
for pc, n in pchist.most_common(12):
    print(f"  0x{pc:016x}  x{n}")
print("\nlast 12 samples (step pc mode a0 a1 a7):")
for s, pc, m, a0, a1, a7 in samples[-12:]:
    print(f"  {s:>12} 0x{pc:016x} m{m} a0=0x{a0:x} a1=0x{a1:x} a7=0x{a7:x}")
print(f"\nuart tail: {uart[-400:]!r}")
