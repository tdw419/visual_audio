#!/usr/bin/env python3
"""BK-58 RED-leg probe: dispatch gate refusals + glyphdbg happy path."""
import importlib.util
spec = importlib.util.spec_from_file_location("bmb", "tools/build_map_bridge.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

# 1. unknown class refused
r = m.dispatch("not_a_class", {"x": 1})
assert r["ok"] is False and r["error"] == "unknown launch class", r
print("L-unknown refused:", r["evidence_hash"])

# 2. glyphdbg happy path (real assembler + engine)
r = m.dispatch("glyphdbg", {"program": "LDI r5 42\nPRT r5\nHALT\n",
                            "max_steps": 10})
assert r["ok"] is True, r
assert 42 in r["output"], r
print("L-glyphdbg ok:", r)

# 3. program charset validation (control chars refused)
r2 = m.dispatch("glyphdbg", {"program": "LDI r5 1\x00\x07bad"})
assert r2["ok"] is False, r2
print("L-charset refused:", r2["error"])

# 4. max_steps bound refusal
r3 = m.dispatch("glyphdbg", {"program": "HALT", "max_steps": 999999})
assert r3["ok"] is False, r3
print("L-bound refused:", r3["error"])

# 5. every launch logged — last 5 lines carry bk58 kind
lines = open(".builder_queue/decision_log.jsonl").read().splitlines()
kinds = [l for l in lines if "bk58_bridge_launch" in l]
assert len(kinds) >= 4, len(kinds)
print("L-logged:", len(kinds), "bridge records")
print("PROBE PASS")
