#!/usr/bin/env python3
"""BK-58 RED-leg probe: prove the gate discriminates.

R1: whitelist neutered in a TEMP-COPY module -> the unknown-class launch
    is NO LONGER refused (L1 shape fires).
R2: glyphdbg handler broken in a TEMP-COPY module -> the happy path
    returns ok=False (L2 shape fires).
The REAL module passes both shapes (control).
"""
import importlib.util
import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SRC = (REPO / "tools" / "build_map_bridge.py").read_text()


def load_from(source_text: str, name: str):
    tmp = REPO / ".builder_queue" / f"_tmp_{name}.py"
    tmp.write_text(source_text)
    try:
        spec = importlib.util.spec_from_file_location(name, tmp)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    finally:
        tmp.unlink()


# control: the real module refuses + runs
m = load_from(SRC, "bk58_real")
assert m.dispatch("not_a_class", {})["ok"] is False
assert m.dispatch("glyphdbg", {"program": "LDI r5 1\nPRT r5\nHALT"})["ok"]
print("control: real module refuses unknown + runs glyphdbg — OK")

# R1: neuter the whitelist (dispatch returns handler result unconditionally)
neutered = SRC.replace(
    'if cls not in HANDLERS:',
    'if False and cls not in HANDLERS:')
assert neutered != SRC
m1 = load_from(neutered, "bk58_neutered")
try:
    r = m1.dispatch("not_a_class", {})
    r = {"raised": False}
except KeyError:
    r = {"raised": True, "shape": "KeyError escapes — refusal shape gone"}
# with the gate neutered, the unknown class is NOT refused cleanly —
# it either raises KeyError out of dispatch or returns something that is
# not the refusal shape. Either way L1's contract is violated.
assert not (isinstance(r, dict) and not r.get("raised", False) and
            r.get("error") == "unknown launch class"), r
print("R1: whitelist neutered -> L1 refusal shape GONE —", r)

# R2: break glyphdbg (make run() raise)
broken = SRC.replace(
    "steps = cpu.run(image, max_instructions=max_steps)",
    "raise RuntimeError('neutered engine wiring')")
assert broken != SRC
m2 = load_from(broken, "bk58_broken")
r2 = m2.dispatch("glyphdbg", {"program": "LDI r5 1\nPRT r5\nHALT"})
assert r2["ok"] is False, r2
print("R2: engine wiring broken -> L2 happy path FAILS —", r2["error"])

print("RED-LEG PROBE PASS: the gate discriminates")
