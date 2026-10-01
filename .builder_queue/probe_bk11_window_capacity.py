"""BK-11 run probe: does BK-1 leg2 fail because the DEFECT-16c fix grows the
injected window program to exactly WINDOW_N_INSTRS (96), i.e. a capacity
limit rather than a register/tick corruption?

Sweeps WINDOW_N_INSTRS (monkeypatched before the helper call) and reports the
leg2 outcome plus the transpiled program's instruction count, on the CURRENT
tree.

usage: python3 .builder_queue/probe_bk11_window_capacity.py
"""
import contextlib
import io
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, ".")
sys.path.insert(0, "tools")
sys.path.insert(0, "tests")

from rv64i_to_glyph import transpile_rv32i_to_glyph  # noqa: E402
import test_bk1_argv as T  # noqa: E402

print(f"test constant WINDOW_N_INSTRS = {T.WINDOW_N_INSTRS}")

with tempfile.TemporaryDirectory() as td:
    tmp = Path(td)
    base, text, syms = T._compile_c_elf(tmp)
    g = transpile_rv32i_to_glyph(text, symbols={a: n for a, n in syms.items()
                                                if not n.startswith("$")},
                                 base_addr=base, cols_instrs=T.COLS_INSTRS)
    n_pushes = sum(1 for l in g.splitlines() if l.strip().startswith("PUSH "))
    n_pops = sum(1 for l in g.splitlines() if l.strip().startswith("POP "))
    words = T._assemble_injected_program(text, syms, base, 0)
    print(f"transpiled program: {len(words)//4} instructions "
          f"(PUSH={n_pushes} POP={n_pops})")

op, payload = 0x11, 0x2A
want = T._native_gcc_reference(op, payload)
print(f"native reference = {want:#010x}")
for n in (96, 104, 112, 128, 160, 192):
    T.WINDOW_N_INSTRS = n
    with tempfile.TemporaryDirectory() as td:
        with contextlib.redirect_stdout(io.StringIO()):
            runner, cpu = T._run_loader_online(
                Path(td), op=op, payload=payload, timer_quantum=12,
                name=f"w{n}.npy")
        got = cpu.memory[T.GH9_ARGV_RESULT]
        print(f"window={n:4d} ticks={cpu.memory[T.GH9_TICKS_COUNT]:6d} "
              f"halted={not cpu.running} faulted={cpu.faulted} "
              f"result={got:#010x} {'OK' if got == want else 'CORRUPT'} "
              f"exit={cpu.memory[T.GH9_EXIT_WORD]:#x}")
