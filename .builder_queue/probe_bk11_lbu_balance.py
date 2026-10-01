"""BK-11 run probe: prove the LBU/LHU PUSH/POP imbalance (DEFECT-16c regression).

The WIP DEFECT-16c fix pushes r28/r29/r30 unconditionally but pops only the
registers != rd:

    for _r in (28, 29, 30): PUSH r{_r}          # always 3 pushes
    ...
    _pop = [r for r in (28, 29, 30) if r != rd]
    for _r in reversed(_pop): POP r{_r}          # 2 pops when rd in {28,29,30}

so every LBU/LHU whose destination is t3/t4/t5 (RV x28/x29/x30) leaves an
entry leaked on the hardware r31 call stack (and restores r28 from the wrong
slot). A leaked frame per loop iteration derails the enclosing CALL/RET chain
-- which is why BK-1 leg2 (timer_quantum=12, the only landed gate that runs
transpiled C under a preempting tick) turns CORRUPT while the BK-11 coreutils
gate stays green (its LBUs land in other destination registers).

This probe (a) transpiles the real BK-1 C program and reports PUSH/POP balance,
(b) lists every LBU/LHU lowering whose rd is 28/29/30, (c) shows the defective
emission for a forced `unsigned char c = *p;` into t3.

usage: python3 .builder_queue/probe_bk11_lbu_balance.py
"""
import contextlib
import io
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, ".")
sys.path.insert(0, "tools")
sys.path.insert(0, "tests")

from rv64i_to_glyph import parse_elf, transpile_rv32i_to_glyph  # noqa: E402
import test_bk1_argv as T  # noqa: E402


def _transpile_c(text, syms, base, cols_instrs=16):
    return transpile_rv32i_to_glyph(text, symbols=syms, base_addr=base,
                                    cols_instrs=cols_instrs)


def _balance(body_lines):
    p = sum(1 for l in body_lines if l.strip().startswith("PUSH "))
    q = sum(1 for l in body_lines if l.strip().startswith("POP "))
    return p, q


def _lbu_blocks(glyph_txt):
    """Find each sub-word-extract lowering: the 'SHL r28 r29' (or LHU's
    'SHL r28 r29') marker followed by the LD into rd."""
    out = []
    lines = [l.strip() for l in glyph_txt.splitlines()]
    for i, l in enumerate(lines):
        if l.startswith("SHL r") and i + 3 < len(lines):
            nxt = lines[i + 1:i + 6]
            for j, cand in enumerate(nxt):
                m = re.match(r"(?:LD|SHR) r(\d+) ", cand)
                if m and cand.startswith("LD "):
                    out.append((i, int(m.group(1)), lines[max(0, i - 8):i + 8]))
                    break
    return out


print("=== (a) BK-1 argv C program: PUSH/POP balance ===")
with tempfile.TemporaryDirectory() as td:
    tmp = Path(td)
    base, text, syms = T._compile_c_elf(tmp)
    glyph = _transpile_c(text, {a: n for a, n in syms.items()
                                if not n.startswith("$")}, base)
body = [l for l in glyph.splitlines() if l.strip()
        and not l.strip().startswith(":") and not l.strip().startswith("#")]
p, q = _balance(body)
print(f"PUSH={p} POP={q} balance={'OK' if p == q else 'UNBALANCED leak=%d' % (p - q)}")

print("\n=== (b) LBU/LHU lowerings by destination register ===")
for idx, rd, ctx in _lbu_blocks(glyph):
    tag = "COLLIDES with scratch" if rd in (28, 29, 30) else "ok"
    print(f"  at body-line {idx}: destination r{rd} -> {tag}")
    if rd in (28, 29, 30):
        for c in ctx:
            print(f"      {c}")

print("\n=== (c) forced `lbu` into t3 (RV x28) ===")
src = r"""
extern int write(int, const void *, unsigned);
void _start(void) {
    const char *p = "AaBb";
    unsigned h = 0, i = 0;
    for (i = 0; i < 4; i++) { unsigned char c = p[i]; h = h * 31 + c; }
    write(1, &h, 4);
    __asm__ volatile("ebreak");
}
"""
with tempfile.TemporaryDirectory() as td:
    tmp = Path(td)
    (tmp / "t.c").write_text(src)
    import subprocess
    subprocess.run(["riscv64-unknown-elf-gcc", "-march=rv32i", "-mabi=ilp32",
                    "-O1", "-nostdlib", "-fno-builtin", "-ffreestanding",
                    "-w", "-c", str(tmp / "t.c"), "-o", str(tmp / "t.o")],
                   check=True)
    subprocess.run(["riscv64-unknown-elf-gcc", "-march=rv32i", "-mabi=ilp32",
                    "-nostdlib", "-Wl,-Ttext=0x0", "-Wl,--entry=_start",
                    "-w", str(tmp / "t.o"), "-o", str(tmp / "t.elf")],
                   check=True)
    b2, t2, s2 = parse_elf((tmp / "t.elf").read_bytes())
    with contextlib.redirect_stdout(io.StringIO()):
        g2 = transpile_rv32i_to_glyph(t2, symbols={a: n for a, n in s2.items()
                                                   if not n.startswith("$")},
                                      base_addr=b2, cols_instrs=16)
    body2 = [l for l in g2.splitlines() if l.strip()
             and not l.strip().startswith(":") and not l.strip().startswith("#")]
    p2, q2 = _balance(body2)
    print(f"PUSH={p2} POP={q2} balance={'OK' if p2 == q2 else 'UNBALANCED leak=%d' % (p2 - q2)}")
    for idx, rd, ctx in _lbu_blocks(g2):
        print(f"  LBU dest r{rd} {'COLLIDES' if rd in (28, 29, 30) else 'ok'}")
