"""BK-11 run probe: is BK-1 leg2's preemption result a timing lottery?

Calls the REAL test helper `test_bk1_argv._run_loader_online` verbatim (no
re-implementation) across a sweep of timer_quantum values, so a pass can be
told apart from a lucky quantum.

The GH-16 tick handler (baker.py `_gh9_kernel_program_text`, timer_quantum>0)
uses glyph r25/r26/r27/r28 as scratch -- which are ALSO the glyph names of RV
x25/x26/x27/x28 (s9/s10/s11/t3) under the transpiler's identity register map.
A tick landing while transpiled code holds a live value in one of those
registers corrupts the user program.

usage: python3 .builder_queue/probe_bk11_leg2_sweep.py
"""
import contextlib
import io
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, ".")
sys.path.insert(0, "tools")
sys.path.insert(0, "tests")

import test_bk1_argv as T  # noqa: E402

QUANTA = [2, 3, 4, 6, 8, 10, 12, 16, 20, 30, 60]
op, payload = 0x11, 0x2A
want = T._native_gcc_reference(op, payload)

print(f"native reference = {want:#010x}")
for q in QUANTA:
    with tempfile.TemporaryDirectory() as td:
        with contextlib.redirect_stdout(io.StringIO()):
            runner, cpu = T._run_loader_online(
                Path(td), op=op, payload=payload, timer_quantum=q,
                name=f"l{q}.npy")
        got = cpu.memory[T.GH9_ARGV_RESULT]
        print(f"q={q:3d} ticks={cpu.memory[T.GH9_TICKS_COUNT]:6d} "
              f"halted={not cpu.running} faulted={cpu.faulted} "
              f"result={got:#010x} {'OK' if got == want else 'CORRUPT'} "
              f"exit={cpu.memory[T.GH9_EXIT_WORD]:#x}")
