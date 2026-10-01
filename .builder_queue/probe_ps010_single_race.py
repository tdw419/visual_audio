"""PS010 step 4 probe: single-buffer leg on the SAME pinned mailbox program.

Measures the actual race trace BEFORE the gate pins it (RED-leg evidence
record, step-2/3 probe precedent). Not part of the gate.
"""
import struct
import sys

sys.path.insert(0, ".")

from tests.test_pyshader_hart import (  # noqa: E402
    DMEM0, MAILBOX_A_WORDS, MAILBOX_B_WORDS, _words,
)
from tools.pyshader_hart import MAILBOX_PROG_A, MAILBOX_PROG_B, run_two_hart  # noqa: E402

assert MAILBOX_A_WORDS == _words(MAILBOX_PROG_A)
assert MAILBOX_B_WORDS == _words(MAILBOX_PROG_B)

dmem0 = list(DMEM0)
try:
    r = run_two_hart(MAILBOX_A_WORDS, MAILBOX_B_WORDS, dmem0, sync="single")
    print("single:", {k: r[k] for k in
                      ("completed", "rounds", "steps_a", "steps_b", "dmem")})
    print("regs_b x5,x6:", r["regs_b"][5], r["regs_b"][6])
    print("writes_a:", r["writes_a"], "writes_b:", r["writes_b"])
    print("dmem0 unmutated:", dmem0 == DMEM0)
except Exception as e:  # noqa: BLE001
    print("RAISED:", type(e).__name__, e)

# control: double-buffer still hits the pin
d = run_two_hart(MAILBOX_A_WORDS, MAILBOX_B_WORDS, list(DMEM0), sync="double")
print("double:", {k: d[k] for k in
                  ("completed", "rounds", "steps_a", "steps_b", "dmem")})
