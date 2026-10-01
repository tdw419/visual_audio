#!/usr/bin/env python3
"""JZ targets are FINE (row 112 = cell 3589, fall-through+8). So exits
jump to cell 3589 — the code after the loop. Then why 9354 iterations?

Per decode: loop = scan byte; JZ (byte==delim) exit; then CMP r29 vs
r28? second JZ exit; JMP back. Exit condition depends on CMP flags.
CMP sets r0. JZ jumps when r0!=0.

Register snapshots: r5=0 always, r16=0, vol2_n never written. And r31
(sp) DOES decrement per iteration: 0x51f->0x51a in 5 iterations? That's
-1/iter. With 3 pushes/2 pops = net -1/iter CONFIRMED by engine PUSH/
POP semantics. After gate max 300000 steps ≈ 9375 iters, sp has lost
9375 words. The data is 22 chars; the loop should have exited after
~10-22 iterations. So the EXITS aren't firing — CMP/JZ conditions never
satisfied. Why? Look at decode:
3581 CMP rs2=7 rd=29 — compares r29 with r7 (rs1=255 means? reg_px =
(rs1,rs2,rd); CMP uses rs1 vs rs2! rs1=255?? CMP takes registers[r s1]
vs [rs2]. rs1 pixel = 255? The rd pixel position holds rs2=7...

CMP rs1=255 -> registers[255]?! Index 255 out of range for 32 regs —
would crash. Unless CMP reads different pixel fields. Let me stop
second-guessing pixel decode — the reg_px layout may differ per op.

DECISIVE on the actual stall: iterate and dump r29 (the extracted
byte) each iteration. If r29 is always 0, the LD path loads zeros —
data-seed addressing wrong in this loop => infinite scanning of zeros.
r7=0xa, scanning zeros: exit only at byte==0xa — first byte of line 2?
Loop would exit at a '\n'... unless the loaded words are zero forever
(scan past the seeded data into empty RAM: 0 != 0xa, loop forever).
THAT MATCHES: bytes are all 0; JZ (== 0xa) never fires; JZ (== r28?)
never fires; infinite loop. The earlier mem dump showed data present
at word 0x199 (byte addr 0x664)?? but C reads from 0x67c. 0x199*4 =
0x664. Data found 'at word(s) 0x199' meaning the string STARTS mid-
chunk — dump showed offset: words 0x199+? 'root:x' appeared at byte
offset 24 of the dump starting 0x199*4=0x664 → 'root' at 0x67C ✓.
So data IS at 0x67c as C expects.

Then why zeros? The scan loop reads via r13=0x67c + index — but the
observed in-image loop's LD: 3575 LD rd=29 rs2=30: r30 = (r15? +
0xffffffff)/4 ... base r15: 3561 LDI r15 imm=0x0, 3562 ADD r15 r??,
3563 ADD r15 — the base register at loop entry holds...? At arrival 1,
regs: r15? not captured. Capture r11-r15 too. If the loop's base reg
is 0 (not 0x67c>>2), LD loads zeros forever => infinite scan. THE
SEED-VALUE for that base register was clobbered by the PUSH/POP
imbalance (r29 leaked, and one iteration's POP restored stale values
into r30/r28, but the BASE came from r15/r14...).

One more capture: full regs at arrivals 1..3 AND at arrivals 20,21
(after scanning past data)."""
import sys, tempfile
from pathlib import Path
REPO = Path('/home/jericho/projects/zion/projects/visual_audio')
sys.path.insert(0, str(REPO)); sys.path.insert(0, str(REPO / 'tools'))
from tools.glyph_gpt.atlas import build_default_atlas
from tools.glyph_gpt.runner import GlyphRunner
from tools.glyph_gpt.baker import libc_runtime_kernel_image
from tools.glyph_gpt.coreutils_port import coreutils2_tool_elf
from tests.test_gh23_libc_runtime import _load_posix_program

with tempfile.TemporaryDirectory() as d:
    tmp = Path(d)
    elf = tmp / 'x.elf'
    elf.write_bytes(coreutils2_tool_elf('cut', 'field2', tmp))
    program = _load_posix_program(elf.read_bytes())
    out = tmp / 'x.npy'
    libc_runtime_kernel_image(build_default_atlas(), out_path=out, user_program=program)
    runner = GlyphRunner(out, ram_words=16384)
    cpu = runner.get_cpu()
    cpu.running = True
    steps = 0
    arrivals = 0
    want = {1, 2, 3, 10, 30}
    while cpu.running and steps < 100000 and arrivals < 31:
        x, y = cpu.pc
        cell = y * 32 + (x // 4)
        if cell == 3561:
            arrivals += 1
            if arrivals in want:
                r = cpu.registers
                print(f'arrival {arrivals} step {steps}:',
                      {i: hex(v) for i, v in enumerate(r) if v})
        cpu.step(runner.image)
        steps += 1
