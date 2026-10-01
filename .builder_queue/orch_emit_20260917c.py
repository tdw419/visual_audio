"""orch emit 20260917c — SE021 maildrop re-emit (write_id 13 target).

Re-runs the maildrop's disclosed sole action (word 700 = 0x3b00112a), byte-identical
payload, arg-guarded. Same action every HOLD tick since ~tick 1; no self-ratification.
"""
import sys

sys.path.insert(0, "tools")
from geos_emit import GeosEmitter

WORD = 700
# committed word 0x3b00112a = cksum 0x3b=(0x11+0x2a)&0xFF | op 0x11 | payload 0x2a
OP = 0x11
PAYLOAD = 0x2A

e = GeosEmitter()
r = e.emit({
    "kind": "post",
    "box": 0,
    "op": OP,
    "payload": PAYLOAD,
    "writer": "builder-cron-af3e62239ce2/se021-maildrop-reemit",
})
print("emit result:", r)
print("expected word:", hex((0x3B << 24) | (OP << 8) | PAYLOAD))
